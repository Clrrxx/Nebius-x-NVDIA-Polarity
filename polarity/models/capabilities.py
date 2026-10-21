"""Capabilities discovered by Phase 0 (``data/capabilities.json``).

When the file is missing (no key yet), conservative defaults are used and ``verified`` is False:
prompt-only JSON with a repair call, no thinking control, manual tools, browser speech recognition.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROLES = ("perception", "fast_text", "reasoning", "deep")
AudioMode = Literal["omni_combined", "omni_separate", "browser_stt", "typed"]


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    case: Literal["exact", "lowercase"] | None = None
    latency_ms: int | None = None
    available: bool | None = None


class AudioInput(BaseModel):
    supported: bool = False
    variant: Literal["input_audio", "audio_url"] | None = None


def _default_models() -> dict[str, ModelInfo]:
    return {role: ModelInfo() for role in ROLES}


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="allow")

    generated_at: str | None = None
    base_url: str | None = None
    models: dict[str, ModelInfo] = Field(default_factory=_default_models)
    all_model_ids: list[str] = Field(default_factory=list)
    perception_fallback_vl: bool = False
    image_input: bool = False
    audio_input: AudioInput = Field(default_factory=AudioInput)
    combined_image_audio: str = "UNPROVEN"
    video_input: str = "SKIPPED"
    json_mode: Literal["json_schema", "json_object", "prompt_only"] = "prompt_only"
    tools_mode: Literal["native", "manual"] = "manual"
    thinking_control: Literal["chat_template_kwargs", "system_flag", "none"] = "none"
    audio_mode_recommended: AudioMode = "browser_stt"
    verified: bool = False

    @classmethod
    def load(cls, path: Path) -> Capabilities:
        """Load ``capabilities.json``; return unverified defaults if it is missing or unreadable."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        data.setdefault("verified", True)
        caps = cls.model_validate(data)
        for role in ROLES:
            caps.models.setdefault(role, ModelInfo())
        return caps
