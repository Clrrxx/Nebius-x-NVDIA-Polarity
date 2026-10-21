"""Robust handling of model text output: strip reasoning, extract JSON, validate, build strict schemas.

Rules (BUILD_PROMPT.md 9.7):
- strip ``<think>...</think>`` blocks and ignore any ``reasoning_content`` field;
- extract the first balanced ``{...}`` object (``` fences, leading/trailing prose, smart quotes);
- validate with Pydantic; on failure the router makes ONE repair call; if that fails the caller returns
  ``uncertain`` with ``reason="model:invalid_output"``. Nothing here ever raises on bad model text.

Only the standard library and pydantic are imported (pydantic ships with the openai SDK), so the
standalone Phase 0 script can use this module.
"""

from __future__ import annotations

import ast
import copy
import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)

_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.S | re.I)
_FENCE = re.compile(r"```(?:json|JSON|javascript|js)?\s*\n?(.*?)```", re.S)
_SMART = {"“": '"', "”": '"', "„": '"', "″": '"', "‘": "'", "’": "'"}
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def strip_think(text: str | None) -> str:
    """Remove reasoning traces (``<think>`` blocks, orphan closing tags, truncated openings)."""
    if not text:
        return ""
    out = _THINK_BLOCK.sub("", text)
    low = out.lower()
    if "</think>" in low:  # opening tag was in a previous chunk / omitted by the template
        out = out[low.rfind("</think>") + len("</think>"):]
    elif "<think>" in low:  # thinking was cut off: no answer after it
        out = out[: low.find("<think>")]
    return out.strip()


def find_balanced_object(text: str) -> str | None:
    """Return the first complete, balanced ``{...}`` substring (string- and escape-aware)."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        start = text.find("{", start + 1)
    return None


def _loads_lenient(candidate: str) -> Any | None:
    attempts = [candidate]
    smart = candidate
    for k, v in _SMART.items():
        smart = smart.replace(k, v)
    attempts.append(smart)
    attempts.append(_TRAILING_COMMA.sub(r"\1", smart))
    for attempt in attempts:
        try:
            return json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue
    try:  # single-quoted Python-style dicts
        value = ast.literal_eval(_TRAILING_COMMA.sub(r"\1", smart))
        return value if isinstance(value, dict) else None
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None


def extract_json(text: str | None) -> dict[str, Any] | None:
    """Extract the first JSON object from model output, tolerating fences, prose and smart quotes."""
    cleaned = strip_think(text)
    if not cleaned:
        return None
    sources: list[str] = [m.group(1) for m in _FENCE.finditer(cleaned)]
    sources.append(cleaned)
    for src in sources:
        for variant in (src, _replace_smart(src)):
            obj = find_balanced_object(variant)
            if obj is None:
                continue
            value = _loads_lenient(obj)
            if isinstance(value, dict):
                return value
    return None


def _replace_smart(text: str) -> str:
    for k, v in _SMART.items():
        text = text.replace(k, v)
    return text


def format_validation_errors(err: ValidationError, limit: int = 8) -> str:
    """Compact, model-readable list of validation errors."""
    items = []
    for e in err.errors()[:limit]:
        loc = ".".join(str(p) for p in e.get("loc", ())) or "(root)"
        items.append(f"{loc}: {e.get('msg')}")
    more = len(err.errors()) - limit
    if more > 0:
        items.append(f"... and {more} more")
    return "; ".join(items)


def parse_model(text: str | None, schema: type[M]) -> tuple[M | None, str | None]:
    """Validate model output against ``schema``. Returns ``(parsed, None)`` or ``(None, error)``."""
    data = extract_json(text)
    if data is None:
        return None, "No JSON object found in the output."
    try:
        return schema.model_validate(data), None
    except ValidationError as err:
        return None, format_validation_errors(err)


_DROP_KEYWORDS = {"default", "title", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                  "minLength", "maxLength", "minItems", "maxItems", "pattern", "format"}


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema for ``response_format=json_schema``.

    Generated with ``model_json_schema()``; ``$defs`` are inlined, every object gets
    ``additionalProperties: false`` and lists all properties as required (nullable fields stay nullable).
    Numeric/length constraints are dropped from the wire schema for backend compatibility; Pydantic still
    enforces them on the response.
    """
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node: Any, is_properties: bool = False) -> Any:
        if isinstance(node, dict):
            if is_properties:  # keys here are field names (e.g. "title"), never schema keywords
                return {name: walk(sub) for name, sub in node.items()}
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return walk(copy.deepcopy(defs[name]))
            out = {k: walk(v, is_properties=(k == "properties")) for k, v in node.items() if k not in _DROP_KEYWORDS}
            if out.get("type") == "object" or "properties" in out:
                out["type"] = "object"
                out["additionalProperties"] = False
                props = out.get("properties", {})
                out["required"] = list(props.keys())
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(raw)


def schema_hint(model: type[BaseModel]) -> str:
    """Compact JSON Schema text to append to a prompt when the API cannot enforce JSON."""
    return json.dumps(strict_json_schema(model), separators=(",", ":"))
