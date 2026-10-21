"""Model discovery heuristics and the exact-first / lowercase-fallback case policy."""

from __future__ import annotations

import pytest

from polarity.llm.resolver import (
    apply_case,
    call_with_case_policy,
    is_model_not_found,
    param_count_b,
    resolve_roles,
)

MIXED_CASE_IDS = [
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning",
    "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
    "nvidia/Nemotron-3-Ultra-253B",
    "nvidia/Nemotron-3-Ultra-49B",
    "nvidia/Nemotron-Nano-12B-v2-VL",
    "meta-llama/Llama-3.3-70B-Instruct",
    "Qwen/Qwen3-32B",
]


def test_roles_resolved_from_mixed_case_list() -> None:
    res = resolve_roles(MIXED_CASE_IDS)
    assert res.ids["perception"] == "nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning"
    assert res.ids["fast_text"] == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"  # not the Omni, not the VL
    assert res.ids["reasoning"] == "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B"
    assert res.ids["deep"] == "nvidia/Nemotron-3-Ultra-253B"  # largest parameter count wins
    assert res.perception_fallback_vl is False


def test_vl_fallback_when_no_omni() -> None:
    ids = [m for m in MIXED_CASE_IDS if "omni" not in m.lower()]
    res = resolve_roles(ids)
    assert res.ids["perception"] == "nvidia/Nemotron-Nano-12B-v2-VL"
    assert res.perception_fallback_vl is True


def test_no_perception_model() -> None:
    res = resolve_roles(["meta-llama/Llama-3.3-70B-Instruct"])
    assert res.ids["perception"] is None
    assert all(v is None for v in res.ids.values())


def test_env_override_wins() -> None:
    res = resolve_roles(MIXED_CASE_IDS, {"reasoning": "custom/model-x", "deep": "  "})
    assert res.ids["reasoning"] == "custom/model-x"
    assert res.ids["deep"] == "nvidia/Nemotron-3-Ultra-253B"  # blank override ignored
    assert any("custom/model-x" in n for n in res.notes)


def test_base_models_are_avoided() -> None:
    res = resolve_roles(["nvidia/nemotron-3-super-120b-base", "nvidia/nemotron-3-super-120b-instruct"])
    assert res.ids["reasoning"] == "nvidia/nemotron-3-super-120b-instruct"


def test_param_count() -> None:
    assert param_count_b("nvidia/Nemotron-3-Nano-30B-A3B") == 30
    assert param_count_b("x/ultra-253b-v1") == 253
    assert param_count_b("x/no-size") == 0


class FakeStatusError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_not_found_detection() -> None:
    assert is_model_not_found(FakeStatusError(404, "nope"))
    assert is_model_not_found(FakeStatusError(400, "The model `X` does not exist"))
    assert is_model_not_found(FakeStatusError(400, "Unknown model: X"))
    assert not is_model_not_found(FakeStatusError(429, "rate limited"))


def test_exact_first_then_lowercase_fallback() -> None:
    sent: list[str] = []

    def fn(model: str) -> str:
        sent.append(model)
        if model != model.lower():
            raise FakeStatusError(404, "model not found")
        return "ok"

    result, case, model = call_with_case_policy(fn, "nvidia/Nemotron-X")
    assert (result, case, model) == ("ok", "lowercase", "nvidia/nemotron-x")
    assert sent == ["nvidia/Nemotron-X", "nvidia/nemotron-x"]


def test_exact_works_no_fallback() -> None:
    sent: list[str] = []

    def fn(model: str) -> str:
        sent.append(model)
        return "ok"

    assert call_with_case_policy(fn, "nvidia/Nemotron-X") == ("ok", "exact", "nvidia/Nemotron-X")
    assert sent == ["nvidia/Nemotron-X"]


def test_recorded_lowercase_used_first_and_other_errors_propagate() -> None:
    def fn(model: str) -> str:
        raise FakeStatusError(500, "server error")

    with pytest.raises(FakeStatusError):
        call_with_case_policy(fn, "nvidia/Nemotron-X", "lowercase")
    assert apply_case("A/B", "lowercase") == "a/b"
    assert apply_case("A/B", "exact") == "A/B"
