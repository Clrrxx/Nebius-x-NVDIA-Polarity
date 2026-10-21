"""OpenAI-compatible client factory for Nebius Token Factory.

Token Factory exposes an OpenAI-compatible API (confirmed), so the official ``openai`` SDK is used with
a custom ``base_url``. Retries are disabled in the SDK because :class:`polarity.llm.router.ModelRouter`
implements its own retry/backoff/budget policy and needs to see every attempt.
"""

from __future__ import annotations

from openai import OpenAI

# Base URLs documented by Nebius, probed in this order by Phase 0 when NEBIUS_BASE_URL is blank.
#  - us-central1 host: listed on the Nebius Nemotron page.
#  - tokenfactory host: seen in an older marketing snippet.
#  - studio host: legacy "AI Studio" endpoint.
KNOWN_BASE_URLS: tuple[str, ...] = (
    "https://api.tokenfactory.us-central1.nebius.com/v1/",
    "https://api.tokenfactory.nebius.com/v1/",
    "https://api.studio.nebius.com/v1/",
)


def mask_secret(value: str | None) -> str:
    """Mask a secret for display: ``****abcd`` (last four characters only)."""
    if not value:
        return "(not set)"
    tail = value[-4:] if len(value) >= 8 else ""
    return f"****{tail}"


def make_client(base_url: str, api_key: str, timeout: float = 30.0) -> OpenAI:
    """Create an OpenAI SDK client pointed at Token Factory.

    ``max_retries=0``: the router owns retries so attempts, latency and cost are logged accurately.
    """
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)
