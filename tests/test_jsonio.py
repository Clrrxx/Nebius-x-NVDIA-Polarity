"""Model-output handling: think tags, fences, prose, smart quotes, broken JSON, strict schemas."""

from __future__ import annotations

import json

from polarity.llm.jsonio import (
    extract_json,
    find_balanced_object,
    parse_model,
    strict_json_schema,
    strip_think,
)
from polarity.models.lab import LabDefinition
from polarity.models.verdict import PerceptionVerdict, ShortText


def test_strip_think_variants() -> None:
    assert strip_think("<think>reasoning</think>Answer") == "Answer"
    assert strip_think("<THINK attr='x'>a\nb</think>\n\n{\"a\":1}") == '{"a":1}'
    assert strip_think("orphan reasoning</think>final") == "final"
    assert strip_think("<think>cut off mid thought") == ""
    assert strip_think(None) == ""


def test_fenced_json() -> None:
    assert extract_json('Here you go:\n```json\n{"text": "hi"}\n```\nThanks') == {"text": "hi"}


def test_prose_around_json_and_nested_braces_in_strings() -> None:
    text = 'Sure! {"text": "use {curly} braces", "n": {"x": 1}} hope that helps'
    assert extract_json(text) == {"text": "use {curly} braces", "n": {"x": 1}}


def test_think_then_json() -> None:
    assert extract_json('<think>{"wrong": true}</think>{"text": "right"}') == {"text": "right"}


def test_smart_quotes_and_trailing_commas() -> None:
    assert extract_json("{“text”: “hello”,}") == {"text": "hello"}


def test_smart_quotes_inside_valid_json_are_kept() -> None:
    assert extract_json('{"text": "the “+” rail"}') == {"text": "the “+” rail"}


def test_single_quoted_python_dict() -> None:
    assert extract_json("{'text': 'ok', 'flag': True}") == {"text": "ok", "flag": True}


def test_broken_json_returns_none() -> None:
    assert extract_json('{"text": "unterminated') is None
    assert extract_json("no json here") is None
    assert find_balanced_object('{"a": "}"') is None


def test_parse_model_validates() -> None:
    parsed, err = parse_model('{"text": "ok"}', ShortText)
    assert parsed is not None and parsed.text == "ok" and err is None
    parsed, err = parse_model('{"txt": "ok"}', ShortText)
    assert parsed is None and "text" in (err or "")
    parsed, err = parse_model("nothing", ShortText)
    assert parsed is None and err


def test_verdict_confidence_bounds_enforced() -> None:
    raw = {"step_id": "s1", "checks": [], "confidence": 1.4, "spoken_feedback": "x"}
    parsed, err = parse_model(json.dumps(raw), PerceptionVerdict)
    assert parsed is None and "confidence" in (err or "")


def _walk(node, fn):  # noqa: ANN001, ANN202
    fn(node)
    if isinstance(node, dict):
        for value in node.values():
            _walk(value, fn)
    elif isinstance(node, list):
        for value in node:
            _walk(value, fn)


def test_strict_schema_for_perception_verdict() -> None:
    schema = strict_json_schema(PerceptionVerdict)
    assert "$defs" not in json.dumps(schema) and "$ref" not in json.dumps(schema)

    def check(node):  # noqa: ANN001, ANN202
        if isinstance(node, dict) and node.get("type") == "object" and "properties" in node:
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])

    _walk(schema, check)
    assert set(schema["properties"]) >= {"step_id", "checks", "confidence", "spoken_feedback", "evidence_region"}


def test_strict_schema_keeps_fields_named_like_keywords() -> None:
    schema = strict_json_schema(LabDefinition)
    assert "title" in schema["properties"]  # a property called "title" must survive keyword stripping
