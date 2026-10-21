"""OpenAI-compatible content-part builders for multimodal Token Factory requests.

Audio has two candidate wire formats; Phase 0 (T7/T8) records which one Nemotron Nano Omni accepts:
- ``input_audio``: ``{"type": "input_audio", "input_audio": {"data": "<b64>", "format": "wav"}}``
- ``audio_url``:   ``{"type": "audio_url", "audio_url": {"url": "data:audio/wav;base64,<b64>"}}``
"""

from __future__ import annotations

import base64
from typing import Any

AUDIO_VARIANTS: tuple[str, ...] = ("input_audio", "audio_url")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def text_part(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def image_part(data: bytes, mime: str = "image/jpeg") -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{_b64(data)}"}}


def audio_part(wav: bytes, variant: str = "input_audio") -> dict[str, Any]:
    if variant == "input_audio":
        return {"type": "input_audio", "input_audio": {"data": _b64(wav), "format": "wav"}}
    if variant == "audio_url":
        return {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{_b64(wav)}"}}
    raise ValueError(f"Unknown audio variant: {variant}")


def video_part(mp4: bytes) -> dict[str, Any]:
    return {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{_b64(mp4)}"}}


def user_message(*parts: dict[str, Any]) -> dict[str, Any]:
    return {"role": "user", "content": list(parts)}


def system_message(text: str) -> dict[str, Any]:
    return {"role": "system", "content": text}


def redact_for_log(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy of ``messages`` with base64 media replaced by a short placeholder (for debug logs)."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                kind = part.get("type")
                if kind in ("image_url", "audio_url", "video_url", "input_audio"):
                    parts.append({"type": kind, "data": "<omitted>"})
                else:
                    parts.append(part)
            out.append({**msg, "content": parts})
        else:
            out.append(dict(msg))
    return out
