"""ModelRouter: budget guard, mock path, and the live path over HTTP against the fake Token Factory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from polarity import config as config_mod
from polarity.llm.router import (
    BudgetExceeded,
    InvalidModelOutput,
    MemoryRecorder,
    ModelCallFailed,
    ModelRouter,
    ModelUnavailable,
)
from polarity.models.verdict import ShortText
from tests import fake_token_factory as fake

MESSAGES = [{"role": "system", "content": "Reply as JSON."}, {"role": "user", "content": "hi"}]


def _live_config(monkeypatch: pytest.MonkeyPatch, data_dir: Path, base_url: str, models: dict[str, str],
                 json_mode: str = "json_schema", deep_available: bool = True) -> config_mod.Config:
    monkeypatch.setenv("POLARITY_MOCK_MODELS", "0")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-0000-5678")
    monkeypatch.setenv("NEBIUS_BASE_URL", base_url)
    caps = {"base_url": base_url, "json_mode": json_mode, "thinking_control": "chat_template_kwargs",
            "models": {role: {"id": mid, "case": "exact"} for role, mid in models.items()}}
    if "deep" in caps["models"]:
        caps["models"]["deep"]["available"] = deep_available
    (data_dir / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")
    config_mod.reset_config()
    return config_mod.get_config()


def test_budget_guard_day_and_session(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = config_mod.get_config()
    rec = MemoryRecorder()
    router = ModelRouter(cfg, recorder=rec)
    rec.record_model_call(role="perception", model_id="m", ok=True, latency_ms=1, prompt_tokens=1, completion_tokens=1,
                          cost_usd=0.6, error=None, session_id="s1")
    rec.record_model_call(role="perception", model_id="m", ok=True, latency_ms=1, prompt_tokens=1, completion_tokens=1,
                          cost_usd=0.5, error=None, session_id="s1")
    with pytest.raises(BudgetExceeded) as exc:
        router.call("fast_text", MESSAGES, schema=ShortText, session_id="s1")
    assert exc.value.scope == "Session"
    router.call("fast_text", MESSAGES, schema=ShortText, session_id="other-session")  # day budget still fine
    cfg.env.budget_day_usd = 1.0
    with pytest.raises(BudgetExceeded) as exc2:
        router.call("fast_text", MESSAGES, schema=ShortText, session_id="other-session")
    assert exc2.value.scope == "Day"


def test_unknown_prices_do_not_count_toward_budget() -> None:
    rec = MemoryRecorder()
    rec.record_model_call(role="perception", model_id="m", ok=True, latency_ms=1, prompt_tokens=10**6,
                          completion_tokens=10**6, cost_usd=None, error=None, session_id="s")
    assert rec.spend("s") == (0.0, 0.0)


def test_mock_call_is_labelled_and_recorded() -> None:
    cfg = config_mod.get_config()
    rec = MemoryRecorder()
    events: list[tuple[float, float, str | None]] = []
    router = ModelRouter(cfg, recorder=rec, on_cost=lambda s, d, sid: events.append((s, d, sid)))
    res = router.call("fast_text", [{"role": "system", "content": "x"},
                                    {"role": "user", "content": '{"text": "one two three", "max_words": 2}'}],
                      schema=ShortText, session_id="s")
    assert res.model_id == "MOCK" and res.parsed is not None
    assert rec.calls[0]["model_id"] == "MOCK" and events


def test_live_without_key_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLARITY_MOCK_MODELS", "0")
    config_mod.reset_config()
    with pytest.raises(ModelUnavailable):
        ModelRouter(config_mod.get_config()).call("perception", MESSAGES)


class ColourCount(BaseModel):
    colour: str
    count: int


def test_live_case_fallback(fake_token_factory: str, monkeypatch: pytest.MonkeyPatch, isolated_env: Path) -> None:
    cfg = _live_config(monkeypatch, isolated_env / "data", fake_token_factory, {"fast_text": fake.OMNI})
    router = ModelRouter(cfg, sleep=lambda s: None)
    # The fake lists a mixed-case ID but only accepts it lowercased: exact → 404 → lowercase works.
    res = router.call("fast_text", MESSAGES)
    assert (res.case_used, res.model_id) == ("lowercase", fake.OMNI.lower())
    res2 = router.call("fast_text", MESSAGES)  # the working case is remembered
    assert res2.case_used == "lowercase"


def test_live_json_schema_downgrade(fake_token_factory: str, monkeypatch: pytest.MonkeyPatch,
                                    isolated_env: Path) -> None:
    cfg = _live_config(monkeypatch, isolated_env / "data", fake_token_factory, {"fast_text": fake.NANO},
                       json_mode="json_schema")
    rec = MemoryRecorder()
    router = ModelRouter(cfg, recorder=rec, sleep=lambda s: None)
    res = router.call("fast_text", MESSAGES, schema=ColourCount)  # fake answers 400 to json_schema
    assert res.parsed == ColourCount(colour="red", count=3)
    assert router.effective_json_mode() == "json_object"
    assert [c["ok"] for c in rec.calls] == [False, True]


def test_live_retry_on_429_then_success(fake_token_factory: str, monkeypatch: pytest.MonkeyPatch,
                                        isolated_env: Path) -> None:
    cfg = _live_config(monkeypatch, isolated_env / "data", fake_token_factory, {"fast_text": fake.FLAKY},
                       json_mode="json_object")
    rec = MemoryRecorder()
    sleeps: list[float] = []
    res = ModelRouter(cfg, recorder=rec, sleep=sleeps.append).call("fast_text", MESSAGES, schema=ShortText)
    assert res.parsed is not None and res.parsed.text == "ok"  # type: ignore[union-attr]
    assert len(sleeps) == 1 and sleeps[0] > 0  # exponential backoff with jitter
    assert [c["ok"] for c in rec.calls] == [False, True]


def test_live_repair_call_fixes_invalid_json(fake_token_factory: str, monkeypatch: pytest.MonkeyPatch,
                                             isolated_env: Path) -> None:
    cfg = _live_config(monkeypatch, isolated_env / "data", fake_token_factory, {"fast_text": fake.BADJSON},
                       json_mode="prompt_only")
    res = ModelRouter(cfg, sleep=lambda s: None).call("fast_text", MESSAGES, schema=ShortText)
    assert res.repaired is True and res.parsed.text == "ok"  # type: ignore[union-attr]


def test_live_down_raises_after_retries(fake_token_factory: str, monkeypatch: pytest.MonkeyPatch,
                                        isolated_env: Path) -> None:
    cfg = _live_config(monkeypatch, isolated_env / "data", fake_token_factory, {"perception": fake.DOWN})
    rec = MemoryRecorder()
    with pytest.raises(ModelCallFailed):
        ModelRouter(cfg, recorder=rec, sleep=lambda s: None).call("perception", MESSAGES)
    assert len(rec.calls) == 3  # 1 try + 2 interactive retries, all recorded as failures
    assert not any(c["ok"] for c in rec.calls)


def test_deep_falls_back_to_reasoning(fake_token_factory: str, monkeypatch: pytest.MonkeyPatch,
                                      isolated_env: Path) -> None:
    cfg = _live_config(monkeypatch, isolated_env / "data", fake_token_factory,
                       {"deep": fake.DOWN, "reasoning": fake.SUPER}, json_mode="json_object")
    res = ModelRouter(cfg, sleep=lambda s: None).call("deep", MESSAGES, interactive=False)
    assert res.model_id == fake.SUPER and res.fallback_from == "deep"


def test_perception_has_no_text_fallback(fake_token_factory: str, monkeypatch: pytest.MonkeyPatch,
                                         isolated_env: Path) -> None:
    cfg = _live_config(monkeypatch, isolated_env / "data", fake_token_factory,
                       {"perception": fake.DOWN, "fast_text": fake.NANO})
    with pytest.raises(ModelCallFailed):
        ModelRouter(cfg, sleep=lambda s: None).call("perception", MESSAGES)


def test_invalid_output_after_repair_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = config_mod.get_config()
    from polarity.llm import mock

    monkeypatch.setattr(mock, "respond", lambda *a, **k: ("not json", []))
    with pytest.raises(InvalidModelOutput):
        ModelRouter(cfg).call("fast_text", MESSAGES, schema=ShortText)
