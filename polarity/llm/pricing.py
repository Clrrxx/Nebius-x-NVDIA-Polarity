"""Per-model pricing from ``config/pricing.yaml`` (team fills real prices from the Token Factory console).

No prices are invented: a model without both prices yields ``None`` and the UI shows "n/a".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Price:
    input_per_million: float
    output_per_million: float


def load_pricing(path: Path) -> dict[str, Price]:
    """Load prices keyed by lower-cased model ID. Missing file, missing PyYAML or nulls → no entry."""
    try:
        import yaml
    except ImportError:
        return {}
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    models = raw.get("models") or {}
    prices: dict[str, Price] = {}
    for model_id, entry in models.items():
        if not isinstance(entry, dict):
            continue
        inp, out = entry.get("input_per_million"), entry.get("output_per_million")
        if inp is None or out is None:
            continue
        prices[str(model_id).lower()] = Price(float(inp), float(out))
    return prices


def estimate_cost(model_id: str | None, prompt_tokens: int, completion_tokens: int,
                  prices: dict[str, Price]) -> float | None:
    """USD estimate for one call, or ``None`` when the model has no configured price."""
    if not model_id:
        return None
    price = prices.get(model_id.lower())
    if price is None:
        return None
    return (prompt_tokens * price.input_per_million + completion_tokens * price.output_per_million) / 1_000_000
