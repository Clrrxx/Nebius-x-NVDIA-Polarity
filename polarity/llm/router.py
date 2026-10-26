"""ModelRouter: the single gateway for every model call (BUILD_PROMPT.md 9.6).

Responsibilities: resolve role → model ID (capabilities/env), apply the case policy, thinking control and JSON
mode, retry with exponential backoff + jitter on 429/5xx/timeouts, enforce the session/day budget guard, estimate
cost from config/pricing.yaml, record every HTTP call in ``model_calls`` and emit ``cost_update`` events.

Mock behaviour lives in :mod:`polarity.llm.mock` and is used ONLY when ``POLARITY_MOCK_MODELS=1``.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel

from polarity.llm.jsonio import parse_model, schema_hint, strict_json_schema, strip_think
from polarity.llm.pricing import estimate_cost
from polarity.llm.prompts import REPAIR_INSTRUCTION
from polarity.llm.resolver import call_with_case_policy, error_text, is_model_not_found

log = logging.getLogger(__name__)

FALLBACK_CHAIN: dict[str, list[str]] = {
    "deep": ["reasoning", "fast_text"],
    "reasoning": ["fast_text"],
    "fast_text": ["reasoning"],  # Nano on Token Factory can hang for minutes; Super answers the same small jobs
    "perception": [],  # no text fallback for perception: the UI offers a retry instead
}
# After a timeout, network error or 5xx, a role that has a fallback is skipped for this long, so one hung model
# costs one timeout instead of one per call. The last role in a chain is always tried.
COOLDOWN_S = 120.0


class RouterError(Exception):
    """Base class for router failures the UI turns into friendly states."""


class BudgetExceeded(RouterError):
    def __init__(self, scope: str, spent: float, limit: float) -> None:
        super().__init__(f"{scope} budget reached: ${spent:.2f} of ${limit:.2f}")
        self.scope, self.spent, self.limit = scope, spent, limit


class ModelUnavailable(RouterError):
    """No key, no capabilities, or no model resolved for the role."""


class ModelCallFailed(RouterError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class InvalidModelOutput(RouterError):
    def __init__(self, message: str, text: str = "") -> None:
        super().__init__(message)
        self.text = text


@dataclass
class RouterResult:
    text: str
    parsed: BaseModel | None
    model_id: str
    case_used: str | None
    latency_ms: int
    usage: dict[str, int]
    cost_usd: float | None
    raw_finish_reason: str | None
    role: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    assistant_message: dict[str, Any] | None = None
    repaired: bool = False
    fallback_from: str | None = None


class CallRecorder(Protocol):
    def record_model_call(self, *, role: str, model_id: str, ok: bool, latency_ms: int, prompt_tokens: int,
                          completion_tokens: int, cost_usd: float | None, error: str | None,
                          session_id: str | None) -> None: ...

    def spend(self, session_id: str | None) -> tuple[float, float]: ...


class MemoryRecorder:
    """In-memory recorder used when no database is attached (CLI eval, tests)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def record_model_call(self, **kw: Any) -> None:
        with self._lock:
            self.calls.append({**kw, "created_at": datetime.now().astimezone().isoformat()})

    def spend(self, session_id: str | None) -> tuple[float, float]:
        today = datetime.now().astimezone().date().isoformat()
        with self._lock:
            day = sum(c["cost_usd"] or 0.0 for c in self.calls if c["created_at"][:10] == today)
            sess = sum(c["cost_usd"] or 0.0 for c in self.calls if session_id and c["session_id"] == session_id)
        return sess, day


_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class ModelRouter:
    """Routes role-based calls to Token Factory (or to the mock when POLARITY_MOCK_MODELS=1)."""

    def __init__(self, config: Any, recorder: CallRecorder | None = None,
                 on_cost: Callable[[float, float, str | None], None] | None = None,
                 client_factory: Callable[[str, str], Any] | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.config = config
        self.recorder: CallRecorder = recorder or MemoryRecorder()
        self.on_cost = on_cost
        self._client_factory = client_factory
        self._client: Any = None
        self._client_lock = threading.Lock()
        self._sleep = sleep
        self._json_mode_downgrade: str | None = None
        self._case_cache: dict[str, str] = {}
        self._cooldown_until: dict[str, float] = {}  # role -> time.monotonic() until which it is skipped
        self.last_error: str | None = None

    # ── public API ───────────────────────────────────────────────────────────────────────────

    def call(self, role: str, messages: list[dict[str, Any]], schema: type[BaseModel] | None = None,
             tools: list[dict[str, Any]] | None = None, temperature: float = 0.0, max_tokens: int = 800,
             thinking: bool = False, timeout: float | None = None, *, interactive: bool = True,
             session_id: str | None = None, mock_hint: str | None = None,
             tool_choice: str | None = None) -> RouterResult:
        """Make one logical call (may involve retries, a JSON repair and a role fallback)."""
        self.check_budget(session_id)
        if self.config.mock:
            return self._mock_call(role, messages, schema, tools, session_id, mock_hint)
        chain = [role, *FALLBACK_CHAIN.get(role, [])]
        last_exc: Exception | None = None
        for i, current in enumerate(chain):
            model = self.config.model_for(current)
            if model is None:
                last_exc = ModelUnavailable(f"No model configured for role '{current}'. Run `python -m polarity verify`.")
                continue
            if i + 1 < len(chain) and self._cooldown_until.get(current, 0.0) > time.monotonic():
                last_exc = ModelCallFailed(f"Role '{current}' is cooling down after a failed call.")
                continue
            try:
                result = self._live_call(current, model.id, model.case, messages, schema, tools, temperature,
                                         max_tokens, thinking and current == "deep", timeout, interactive, session_id,
                                         tool_choice)
                self._cooldown_until.pop(current, None)
                if i > 0:
                    result.fallback_from = role
                return result
            except (ModelCallFailed, ModelUnavailable) as exc:
                last_exc = exc
                if isinstance(exc, ModelCallFailed) and (exc.status_code is None or exc.status_code in _RETRYABLE_STATUS):
                    self._cooldown_until[current] = time.monotonic() + COOLDOWN_S
                if i + 1 < len(chain):
                    log.warning("role %s failed (%s); falling back to %s", current, exc, chain[i + 1])
                continue
        assert last_exc is not None
        raise last_exc

    def check_budget(self, session_id: str | None) -> None:
        """Raise :class:`BudgetExceeded` once the session or day estimate has reached its limit."""
        sess, day = self.recorder.spend(session_id)
        env = self.config.env
        if day >= float(env.budget_day_usd):
            raise BudgetExceeded("Day", day, float(env.budget_day_usd))
        if session_id and sess >= float(env.budget_session_usd):
            raise BudgetExceeded("Session", sess, float(env.budget_session_usd))

    def effective_json_mode(self) -> str:
        return self._json_mode_downgrade or self.config.capabilities.json_mode

    # ── internals ────────────────────────────────────────────────────────────────────────────

    def _client_for(self) -> Any:
        with self._client_lock:
            if self._client is None:
                key, base = self.config.api_key, self.config.base_url
                if not key:
                    raise ModelUnavailable("NEBIUS_API_KEY is not set. Add it to .env (see .env.example).")
                if not base:
                    raise ModelUnavailable("No Token Factory base URL. Run `python -m polarity verify` first.")
                if self._client_factory:
                    self._client = self._client_factory(base, key)
                else:
                    from polarity.llm.client import make_client

                    self._client = make_client(base, key, timeout=60.0)
            return self._client

    def _thinking_args(self, messages: list[dict[str, Any]], thinking: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        control = self.config.capabilities.thinking_control
        if control == "chat_template_kwargs":
            return messages, {"extra_body": {"chat_template_kwargs": {"enable_thinking": bool(thinking)}}}
        if control == "system_flag" and not thinking and messages and messages[0].get("role") == "system":
            first = dict(messages[0])
            first["content"] = "/no_think\n" + str(first["content"])
            return [first, *messages[1:]], {}
        return messages, {}

    def _json_args(self, messages: list[dict[str, Any]], schema: type[BaseModel] | None,
                   mode: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if schema is None:
            return messages, {}
        if mode == "json_schema":
            return messages, {"response_format": {"type": "json_schema", "json_schema": {
                "name": schema.__name__, "strict": True, "schema": strict_json_schema(schema)}}}
        hint = f"\n\nJSON schema for your output:\n{schema_hint(schema)}"
        if messages and messages[0].get("role") == "system":
            first = dict(messages[0])
            first["content"] = str(first["content"]) + hint
            messages = [first, *messages[1:]]
        return messages, ({"response_format": {"type": "json_object"}} if mode == "json_object" else {})

    def _max_tokens(self, max_tokens: int, thinking: bool) -> int:
        if thinking:
            return max(max_tokens, 4096)
        if self.config.capabilities.thinking_control == "none":
            return min(8192, max(max_tokens * 3, 2048))  # reasoning text may precede the answer
        return max_tokens

    def _record(self, role: str, model_id: str, ok: bool, latency_ms: int, p: int, c: int, cost: float | None,
                error: str | None, session_id: str | None) -> None:
        try:
            self.recorder.record_model_call(role=role, model_id=model_id, ok=ok, latency_ms=latency_ms,
                                            prompt_tokens=p, completion_tokens=c, cost_usd=cost,
                                            error=(error[:500] if error else None), session_id=session_id)
        except Exception:  # noqa: BLE001 - logging must never break a check
            log.exception("could not record model call")
        if self.on_cost:
            try:
                sess, day = self.recorder.spend(session_id)
                self.on_cost(sess, day, session_id)
            except Exception:  # noqa: BLE001
                log.exception("cost event failed")

    def _live_call(self, role: str, model_id: str, case: str | None, messages: list[dict[str, Any]],
                   schema: type[BaseModel] | None, tools: list[dict[str, Any]] | None, temperature: float,
                   max_tokens: int, thinking: bool, timeout: float | None, interactive: bool,
                   session_id: str | None, tool_choice: str | None) -> RouterResult:
        import openai

        client = self._client_for()
        settings = self.config.settings
        per_attempt = float(timeout or getattr(settings.timeouts_s, role, 30.0))
        retries = settings.retries.interactive if interactive else settings.retries.background
        start = time.monotonic()
        deadline = start + per_attempt if interactive else None
        json_mode = self.effective_json_mode() if schema else "none"
        attempt = 0
        while True:
            msgs, think_kwargs = self._thinking_args(messages, thinking)
            msgs, json_kwargs = self._json_args(msgs, schema, json_mode)
            kwargs: dict[str, Any] = {**think_kwargs, **json_kwargs}
            if tools and self.config.capabilities.tools_mode == "native":
                kwargs["tools"] = tools
                if tool_choice:
                    kwargs["tool_choice"] = tool_choice
            remaining = (deadline - time.monotonic()) if deadline else per_attempt
            attempt_timeout = max(1.0, min(per_attempt, remaining))
            t0 = time.perf_counter()
            case_hint = self._case_cache.get(model_id, case)

            def _do(model: str, _msgs: list[dict[str, Any]] = msgs, _kw: dict[str, Any] = kwargs,
                    _t: float = attempt_timeout) -> Any:
                return client.chat.completions.create(model=model, messages=_msgs, temperature=temperature,
                                                      max_tokens=self._max_tokens(max_tokens, thinking),
                                                      timeout=_t, **_kw)

            try:
                resp, case_used, sent = call_with_case_policy(_do, model_id, case_hint)
            except openai.APIStatusError as exc:
                latency = int((time.perf_counter() - t0) * 1000)
                text = error_text(exc)
                self._record(role, model_id, False, latency, 0, 0, None, f"HTTP {exc.status_code}: {text}", session_id)
                if exc.status_code == 400 and schema and json_mode in ("json_schema", "json_object") \
                        and ("response_format" in text or "json" in text.lower() or "schema" in text.lower()):
                    json_mode = "json_object" if json_mode == "json_schema" else "prompt_only"
                    self._json_mode_downgrade = json_mode
                    log.warning("JSON mode rejected by the API; downgrading to %s", json_mode)
                    continue
                if exc.status_code in _RETRYABLE_STATUS and self._can_retry(attempt, retries, deadline):
                    self._backoff(attempt, interactive)
                    attempt += 1
                    continue
                self.last_error = f"HTTP {exc.status_code}"
                if is_model_not_found(exc):
                    raise ModelUnavailable(f"Model {model_id} not found (HTTP {exc.status_code}).") from exc
                raise ModelCallFailed(f"Token Factory returned HTTP {exc.status_code}.", exc.status_code) from exc
            except openai.APIConnectionError as exc:  # includes APITimeoutError
                latency = int((time.perf_counter() - t0) * 1000)
                self._record(role, model_id, False, latency, 0, 0, None, f"{type(exc).__name__}: {exc}", session_id)
                if self._can_retry(attempt, retries, deadline):
                    self._backoff(attempt, interactive)
                    attempt += 1
                    continue
                self.last_error = type(exc).__name__
                raise ModelCallFailed("Could not reach Token Factory (timeout or network error).") from exc

            latency = int((time.perf_counter() - t0) * 1000)
            self._case_cache[model_id] = case_used
            result = self._to_result(role, resp, sent, case_used, latency)
            self._record(role, sent, True, latency, result.usage["prompt_tokens"], result.usage["completion_tokens"],
                         result.cost_usd, None, session_id)
            if schema is not None and not result.tool_calls:
                result = self._parse_or_repair(result, schema, role, model_id, case_used, msgs, kwargs,
                                               max_tokens, thinking, attempt_timeout, session_id)
            return result

    def _can_retry(self, attempt: int, retries: int, deadline: float | None) -> bool:
        if attempt >= retries:
            return False
        return deadline is None or deadline - time.monotonic() > 2.0

    def _backoff(self, attempt: int, interactive: bool) -> None:
        base = 0.5 if interactive else 1.0
        delay = base * (2 ** attempt) + random.uniform(0, base)
        self._sleep(delay)

    def _to_result(self, role: str, resp: Any, sent: str, case_used: str | None, latency: int) -> RouterResult:
        choice = resp.choices[0] if resp.choices else None
        msg = choice.message if choice is not None else None
        content = (msg.content if msg is not None else None) or ""
        usage = getattr(resp, "usage", None)
        p = int(getattr(usage, "prompt_tokens", 0) or 0)
        c = int(getattr(usage, "completion_tokens", 0) or 0)
        tool_calls: list[dict[str, Any]] = []
        for tc in (msg.tool_calls if msg is not None and msg.tool_calls else []):
            fn = getattr(tc, "function", None)
            tool_calls.append({"id": getattr(tc, "id", None), "type": "function",
                               "function": {"name": getattr(fn, "name", None),
                                            "arguments": getattr(fn, "arguments", None) or "{}"}})
        assistant: dict[str, Any] = {"role": "assistant", "content": content or None}
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        return RouterResult(text=strip_think(content), parsed=None, model_id=sent, case_used=case_used,
                            latency_ms=latency, usage={"prompt_tokens": p, "completion_tokens": c},
                            cost_usd=estimate_cost(sent, p, c, self.config.prices),
                            raw_finish_reason=getattr(choice, "finish_reason", None), role=role,
                            tool_calls=tool_calls, assistant_message=assistant)

    def _parse_or_repair(self, result: RouterResult, schema: type[BaseModel], role: str, model_id: str,
                         case_used: str | None, msgs: list[dict[str, Any]], kwargs: dict[str, Any], max_tokens: int,
                         thinking: bool, timeout: float, session_id: str | None) -> RouterResult:
        parsed, err = parse_model(result.text, schema)
        if parsed is not None:
            result.parsed = parsed
            return result
        # One repair attempt with the same model (BUILD_PROMPT.md 9.7).
        import openai

        client = self._client_for()
        repair_msgs = [*msgs, {"role": "assistant", "content": result.text or "(empty)"},
                       {"role": "user", "content": REPAIR_INSTRUCTION.format(errors=err) + "\nSchema: "
                        + schema_hint(schema)}]
        t0 = time.perf_counter()
        try:
            resp = client.chat.completions.create(model=result.model_id, messages=repair_msgs, temperature=0.0,
                                                  max_tokens=self._max_tokens(max_tokens, thinking), timeout=timeout,
                                                  **kwargs)
        except (openai.APIStatusError, openai.APIConnectionError) as exc:
            self._record(role, result.model_id, False, int((time.perf_counter() - t0) * 1000), 0, 0, None,
                         f"repair failed: {exc}", session_id)
            raise InvalidModelOutput(f"Model output was not valid JSON ({err}); repair call failed.",
                                     result.text) from exc
        repaired = self._to_result(role, resp, result.model_id, case_used, int((time.perf_counter() - t0) * 1000))
        self._record(role, repaired.model_id, True, repaired.latency_ms, repaired.usage["prompt_tokens"],
                     repaired.usage["completion_tokens"], repaired.cost_usd, None, session_id)
        parsed, err2 = parse_model(repaired.text, schema)
        if parsed is None:
            raise InvalidModelOutput(f"Model output was not valid JSON after one repair ({err2}).", repaired.text)
        repaired.parsed = parsed
        repaired.repaired = True
        repaired.latency_ms += result.latency_ms
        if result.cost_usd is not None and repaired.cost_usd is not None:
            repaired.cost_usd += result.cost_usd
        repaired.usage = {k: repaired.usage[k] + result.usage[k] for k in repaired.usage}
        return repaired

    def _mock_call(self, role: str, messages: list[dict[str, Any]], schema: type[BaseModel] | None,
                   tools: list[dict[str, Any]] | None, session_id: str | None, mock_hint: str | None) -> RouterResult:
        from polarity.llm import mock

        delay = max(0, int(self.config.env.polarity_mock_latency_ms)) / 1000.0
        t0 = time.perf_counter()
        if delay:
            self._sleep(delay)
        text, tool_calls = mock.respond(role, messages, schema, tools, mock_hint, self.config)
        latency = int((time.perf_counter() - t0) * 1000)
        self._record(role, "MOCK", True, latency, 0, 0, 0.0, None, session_id)
        result = RouterResult(text=text, parsed=None, model_id="MOCK", case_used=None, latency_ms=latency,
                              usage={"prompt_tokens": 0, "completion_tokens": 0}, cost_usd=0.0,
                              raw_finish_reason="tool_calls" if tool_calls else "stop", role=role,
                              tool_calls=tool_calls,
                              assistant_message={"role": "assistant", "content": text or None,
                                                 **({"tool_calls": tool_calls} if tool_calls else {})})
        if schema is not None and not tool_calls:
            parsed, err = parse_model(text, schema)
            if parsed is None:
                raise InvalidModelOutput(f"Mock output invalid: {err}", text)
            result.parsed = parsed
        return result
