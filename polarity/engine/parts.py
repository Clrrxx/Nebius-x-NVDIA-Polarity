"""Part / datasheet lookup with Tavily (BUILD_PROMPT.md 13.2, P1 — "Best Use of Tavily").

A real runtime call to the Tavily Search API fetches pinout/datasheet pages; Nemotron Super then summarises ONLY
what those sources say, with citations. Two modes, chosen by Phase 0:
- ``native``: Super is given a ``lookup_part`` tool; our code executes the tool call against Tavily.
- ``manual``: our code calls Tavily directly, then Super summarises the results.
Results are cached per part number. Without ``TAVILY_API_KEY`` the feature is hidden.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from polarity.llm import prompts
from polarity.llm.router import RouterError
from polarity.models.verdict import PartSummary

log = logging.getLogger(__name__)
PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-./+]{1,23}$")
TOOL = [{"type": "function", "function": {
    "name": "lookup_part", "description": "Search the web for an electronic part's datasheet and pinout.",
    "parameters": {"type": "object", "properties": {"part_number": {"type": "string"}}, "required": ["part_number"]}}}]


class PartsUnavailable(Exception):
    pass


def make_tavily_client(api_key: str) -> Any:
    from tavily import TavilyClient

    return TavilyClient(api_key=api_key)


def tavily_search(api_key: str, part: str) -> list[dict[str, str]]:
    """The runtime Tavily call. Returns ``[{title, url, content}]`` (content trimmed)."""
    client = make_tavily_client(api_key)
    raw = client.search(query=f"{part} pinout datasheet", max_results=5, search_depth="basic", include_answer=False)
    out = []
    for r in (raw or {}).get("results", [])[:5]:
        url = str(r.get("url") or "")
        if not url.startswith(("http://", "https://")):
            continue
        out.append({"title": str(r.get("title") or "")[:200], "url": url, "content": str(r.get("content") or "")[:1500]})
    return out


def _summary_messages(part: str, results: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [{"role": "system", "content": prompts.PART_LOOKUP_SYSTEM},
            {"role": "user", "content": json.dumps({"part": part, "results": results}, ensure_ascii=False)}]


def _clean(summary: PartSummary, results: list[dict[str, str]]) -> PartSummary:
    """Only cite URLs that Tavily actually returned (never a URL the model made up)."""
    allowed = {r["url"] for r in results}
    sources = [u for u in summary.sources if u in allowed] or [r["url"] for r in results[:3]]
    return summary.model_copy(update={"sources": sources})


def lookup(rt: Any, part: str) -> dict[str, Any]:
    part = part.strip().upper()
    if not PART_RE.match(part):
        raise ValueError("That doesn't look like a part number.")
    key = rt.config.tavily_key
    if not key:
        raise PartsUnavailable("Part lookup needs TAVILY_API_KEY in .env.")
    cached = rt.db.get_part(part)
    if cached:
        return {**cached, "cached": True}
    results: list[dict[str, str]] = []
    model_id = None
    try:
        if rt.config.capabilities.tools_mode == "native" and not rt.config.mock:
            first = rt.router.call("reasoning", [
                {"role": "system", "content": prompts.PART_TOOL_SYSTEM},
                {"role": "user", "content": f"What is the pinout of the {part}? Use the tool."}],
                tools=TOOL, tool_choice="auto", max_tokens=400, interactive=True)
            model_id = first.model_id
            messages: list[dict[str, Any]] = [{"role": "system", "content": prompts.PART_TOOL_SYSTEM},
                                              {"role": "user", "content": f"What is the pinout of the {part}?"}]
            if first.tool_calls:
                messages.append(first.assistant_message or {"role": "assistant", "content": None,
                                                            "tool_calls": first.tool_calls})
                for call in first.tool_calls:
                    try:
                        args = json.loads(call["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    found = tavily_search(key, str(args.get("part_number") or part))
                    results += found
                    messages.append({"role": "tool", "tool_call_id": call.get("id") or "call_1",
                                     "content": json.dumps(found, ensure_ascii=False)})
            else:  # model answered without the tool: fall back to a direct search so facts stay sourced
                results = tavily_search(key, part)
                messages = _summary_messages(part, results)
            final = rt.router.call("reasoning", messages + [{"role": "user", "content": "Now answer as the JSON object."}],
                                   schema=PartSummary, max_tokens=600)
        else:
            results = tavily_search(key, part)
            final = rt.router.call("reasoning", _summary_messages(part, results), schema=PartSummary, max_tokens=600)
        model_id = final.model_id
        summary = _clean(final.parsed, results)  # type: ignore[arg-type]
    except RouterError:
        raise
    except Exception as exc:  # noqa: BLE001 - Tavily network/API errors become a friendly message
        log.warning("part lookup failed: %s", exc)
        raise PartsUnavailable(f"Couldn't look up {part} right now.") from exc
    payload = {"part": part, **summary.model_dump(), "model_id": model_id, "mode": rt.config.capabilities.tools_mode,
               "result_count": len(results)}
    if results:
        rt.db.put_part(part, payload)
    return payload
