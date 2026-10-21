"""Model discovery heuristics and the model-ID case policy.

Facts vs assumptions (BUILD_PROMPT.md Section 8.1):
- TEAM-REPORTED, UNVERIFIED: model IDs in completion payloads must be lowercase.
- Some Nebius IDs have historically used mixed case (e.g. ``nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B``), so
  blindly lowercasing could itself cause "model not found".

Policy implemented here: **exact first, lowercase fallback**. We send the exact ID returned by ``/models``;
if the API answers 404 or the error text says the model is unknown, we retry once with ``.lower()``.
Whichever worked is recorded per model in ``data/capabilities.json`` and reused automatically.

This module only depends on the standard library so the standalone Phase 0 script can import it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TypeVar

ROLES: tuple[str, ...] = ("perception", "fast_text", "reasoning", "deep")

NOT_FOUND_MARKERS: tuple[str, ...] = (
    "not found",
    "does not exist",
    "unknown model",
    "no such model",
    "model_not_found",
)

T = TypeVar("T")


def _tokens(model_id: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", model_id.lower()) if t]


def param_count_b(model_id: str) -> int:
    """Largest ``<N>b`` parameter count in an ID (``nemotron-3-ultra-253b`` → 253); 0 if none."""
    counts = [int(n) for n in re.findall(r"(\d+)b(?![a-z])", model_id.lower())]
    return max(counts) if counts else 0


def _is_base_model(model_id: str) -> bool:
    return "base" in _tokens(model_id)


def _is_vision_variant(model_id: str) -> bool:
    toks = _tokens(model_id)
    return "vl" in toks or any(t.endswith("vl") and len(t) <= 4 for t in toks) or "vision" in model_id.lower()


@dataclass
class RoleResolution:
    """Result of mapping the ``/models`` list onto Polarity's four roles."""

    ids: dict[str, str | None]
    perception_fallback_vl: bool = False
    candidates: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _best(cands: list[tuple[float, str]]) -> str | None:
    if not cands:
        return None
    # Highest score first, then alphabetical for determinism.
    cands.sort(key=lambda c: (-c[0], c[1]))
    return cands[0][1]


def resolve_roles(model_ids: Iterable[str], overrides: dict[str, str | None] | None = None) -> RoleResolution:
    """Resolve role → exact model ID using the Phase 0 heuristics (env overrides win).

    - perception: contains ``omni`` (prefer also ``nano``); else a Nemotron ``vl``/``vision`` model
      (sets ``perception_fallback_vl``); else unresolved.
    - reasoning: ``nemotron`` + ``super`` (prefer ``120b``).
    - deep: ``nemotron`` + ``ultra`` (prefer the largest parameter count).
    - fast_text: ``nemotron`` + ``nano`` and not ``omni``/``vl``/``vision`` (prefer ``30b``).
    """
    ids = sorted(set(model_ids))
    overrides = {k: (v.strip() if v else None) for k, v in (overrides or {}).items()}
    res = RoleResolution(ids={r: None for r in ROLES})

    def low(mid: str) -> str:
        return mid.lower()

    # perception
    omni = [(2.0 * ("nano" in low(m)) + 1.0 * ("nemotron" in low(m)) - 3.0 * _is_base_model(m), m)
            for m in ids if "omni" in low(m)]
    res.candidates["perception"] = [m for _, m in omni]
    perception = _best(omni)
    if perception is None:
        vl = [(1.0 * ("nano" in low(m)) - 3.0 * _is_base_model(m), m)
              for m in ids if "nemotron" in low(m) and _is_vision_variant(m)]
        res.candidates["perception"] = [m for _, m in vl]
        perception = _best(vl)
        if perception is not None:
            res.perception_fallback_vl = True
            res.notes.append("No Nemotron Omni model listed; using a Nemotron VL model for perception.")
    res.ids["perception"] = perception

    # reasoning
    sup = [(2.0 * ("120b" in low(m)) - 3.0 * _is_base_model(m), m)
           for m in ids if "nemotron" in low(m) and "super" in low(m)]
    res.candidates["reasoning"] = [m for _, m in sup]
    res.ids["reasoning"] = _best(sup)

    # deep
    ultra = [(float(param_count_b(m)) - 1000.0 * _is_base_model(m), m)
             for m in ids if "nemotron" in low(m) and "ultra" in low(m)]
    res.candidates["deep"] = [m for _, m in ultra]
    res.ids["deep"] = _best(ultra)

    # fast_text
    nano = [(2.0 * ("30b" in low(m)) - 3.0 * _is_base_model(m), m)
            for m in ids
            if "nemotron" in low(m) and "nano" in low(m) and "omni" not in low(m) and not _is_vision_variant(m)]
    res.candidates["fast_text"] = [m for _, m in nano]
    res.ids["fast_text"] = _best(nano)

    for role, value in overrides.items():
        if role in res.ids and value:
            if value not in ids:
                res.notes.append(f"Override for {role} ({value}) is not in the /models list; using it anyway.")
            res.ids[role] = value
            if role == "perception":
                res.perception_fallback_vl = "omni" not in value.lower() and _is_vision_variant(value)
    return res


def error_text(exc: BaseException) -> str:
    """Best-effort error body text for an SDK exception (never includes request headers)."""
    parts = [str(exc)]
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            parts.append(response.text)
        except Exception:  # noqa: BLE001 - body may be unreadable/streamed
            pass
    body = getattr(exc, "body", None)
    if body:
        parts.append(str(body))
    return " | ".join(p for p in parts if p)


def is_model_not_found(exc: BaseException) -> bool:
    """True when an API error means "this model ID does not exist" (404 or not-found wording)."""
    if getattr(exc, "status_code", None) == 404:
        return True
    text = error_text(exc).lower()
    return any(marker in text for marker in NOT_FOUND_MARKERS)


def apply_case(model_id: str, case: str | None) -> str:
    """Return the ID to send for a recorded case policy (``exact`` or ``lowercase``)."""
    return model_id.lower() if case == "lowercase" else model_id


def call_with_case_policy(fn: Callable[[str], T], model_id: str, case: str | None = None) -> tuple[T, str, str]:
    """Call ``fn(model)`` using exact-first / lowercase-fallback.

    If ``case`` was already recorded we try that form first, and still fall back to the other form once
    if the API says the model does not exist. Returns ``(result, case_used, model_sent)``.
    """
    first_case = "lowercase" if case == "lowercase" else "exact"
    first = apply_case(model_id, first_case)
    try:
        return fn(first), first_case, first
    except Exception as exc:  # noqa: BLE001 - decide on retry, otherwise re-raise unchanged
        other_case = "exact" if first_case == "lowercase" else "lowercase"
        other = apply_case(model_id, other_case)
        if other != first and is_model_not_found(exc):
            return fn(other), other_case, other
        raise
