"""Configuration: merges ``.env`` (secrets, per-machine switches), ``config/settings.yaml`` (thresholds)
and ``data/capabilities.json`` (what Phase 0 verified). ``APP_NAME`` is defined here, once.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from polarity import paths
from polarity.llm.pricing import Price, load_pricing
from polarity.models.capabilities import ROLES, Capabilities

APP_NAME = "Polarity"  # working name: rename the product here and only here
TAGLINE = ("An AI lab partner that catches wiring mistakes before the circuit fails, "
           "and shows the TA where the class is stuck.")


class EnvSettings(BaseSettings):
    """Values from the environment / ``.env`` (see ``.env.example``). Real env vars win over the file."""

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore", case_sensitive=False,
                                      env_ignore_empty=True)

    nebius_api_key: SecretStr | None = None
    nebius_base_url: str | None = None
    polarity_model_perception: str | None = None
    polarity_model_fast_text: str | None = None
    polarity_model_reasoning: str | None = None
    polarity_model_deep: str | None = None
    tavily_api_key: SecretStr | None = None
    polarity_mock_models: bool = False
    polarity_mock_latency_ms: int = 600
    camera_source: Literal["opencv", "demo"] = "opencv"
    camera_index: int = 0
    camera_width: int = 1920
    camera_height: int = 1080
    markers_enabled: bool = True
    audio_mode: Literal["auto", "omni_combined", "omni_separate", "browser_stt", "typed"] = "auto"
    default_lab: str = "lab1"
    port: int = 8765
    ta_pin: SecretStr = SecretStr("2468")
    budget_session_usd: float = 1.00
    budget_day_usd: float = 5.00
    media_retention_days: int = 14


class QualitySettings(BaseModel):
    blur_var_min: float = 80.0
    brightness_min: float = 70
    brightness_max: float = 200
    glare_ratio_max: float = 0.02
    markers_min: int = 3
    motion_max: float = 6.0


class DecisionSettings(BaseModel):
    pass_min_conf: float = 0.75
    fix_min_conf: float = 0.60
    grey_zone: tuple[float, float] = (0.50, 0.80)
    second_look_zoom: float = 1.6
    second_look_temperature: float = 0.2


class LedSettings(BaseModel):
    min_area_px: int = 25
    max_area_px: int = 4000
    v_delta_min: float = 45
    red_hue_ranges: list[tuple[int, int]] = Field(default_factory=lambda: [(0, 12), (165, 180)])
    s_min: int = 70
    core_v_min: int = 245
    strong_min: float = 0.60
    skin_reject: bool = True


class ImageSettings(BaseModel):
    max_long_side: int = 1280
    jpeg_quality: int = 85


class AudioSettings(BaseModel):
    max_seconds: float = 15
    sample_rate: int = 16000


class TimeoutSettings(BaseModel):
    perception: float = 30
    fast_text: float = 15
    reasoning: float = 45
    deep: float = 120


class RetrySettings(BaseModel):
    interactive: int = 2
    background: int = 3


class UiSettings(BaseModel):
    theme: Literal["dark", "light"] = "dark"
    speak_feedback: bool = True


class BoardSettings(BaseModel):
    warp_width: int = 1024
    warp_height: int = 768
    marker_ids: list[int] = Field(default_factory=lambda: [0, 1, 2, 3])
    roi: tuple[float, float, float, float] = (0.15, 0.10, 0.70, 0.80)


class CameraSettings(BaseModel):
    ring_frames: int = 15
    ring_hz: float = 15
    stream_fps: float = 12
    stream_width: int = 960
    quality_hz: float = 2


class EscalationSettings(BaseModel):
    fix_count: int = 3
    uncertain_streak: int = 3
    power_test_fails: int = 2


class HubSettings(BaseModel):
    send_thumbnails: bool = False
    retry_seconds: float = 10


class AppSettings(BaseModel):
    quality: QualitySettings = Field(default_factory=QualitySettings)
    decision: DecisionSettings = Field(default_factory=DecisionSettings)
    led: LedSettings = Field(default_factory=LedSettings)
    images: ImageSettings = Field(default_factory=ImageSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    timeouts_s: TimeoutSettings = Field(default_factory=TimeoutSettings)
    retries: RetrySettings = Field(default_factory=RetrySettings)
    ui: UiSettings = Field(default_factory=UiSettings)
    board: BoardSettings = Field(default_factory=BoardSettings)
    camera: CameraSettings = Field(default_factory=CameraSettings)
    escalation: EscalationSettings = Field(default_factory=EscalationSettings)
    hub: HubSettings = Field(default_factory=HubSettings)

    @classmethod
    def load(cls, path: Path) -> AppSettings:
        if not path.exists():
            return cls()
        with path.open("r", encoding="utf-8") as fh:
            return cls.model_validate(yaml.safe_load(fh) or {})


@dataclass(frozen=True)
class ResolvedModel:
    role: str
    id: str
    case: str | None


@dataclass
class Paths:
    root: Path
    data: Path
    docs: Path
    labs: Path
    config: Path
    media: Path
    db: Path
    demo: Path
    eval: Path
    drafts: Path
    logs: Path
    capabilities: Path
    web: Path

    @classmethod
    def discover(cls) -> Paths:
        root = paths.repo_root()
        data = paths.data_dir()
        web = Path(__file__).resolve().parent / "web"
        return cls(root=root, data=data, docs=paths.docs_dir(), labs=paths.labs_dir(), config=paths.config_dir(),
                   media=data / "media", db=data / "polarity.db", demo=data / "demo", eval=data / "eval",
                   drafts=data / "lab_drafts", logs=data / "logs", capabilities=paths.capabilities_file(), web=web)


@dataclass
class Config:
    env: EnvSettings
    settings: AppSettings
    capabilities: Capabilities
    prices: dict[str, Price]
    paths: Paths
    role_override: str = "standalone"          # standalone | bench | hub (set by `polarity run`)
    hub_url: str | None = None
    bench_id: str | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def app_name(self) -> str:
        return APP_NAME

    @property
    def mock(self) -> bool:
        return bool(self.env.polarity_mock_models)

    @property
    def api_key(self) -> str | None:
        key = self.env.nebius_api_key.get_secret_value() if self.env.nebius_api_key else ""
        return key.strip() or None

    @property
    def tavily_key(self) -> str | None:
        key = self.env.tavily_api_key.get_secret_value() if self.env.tavily_api_key else ""
        return key.strip() or None

    @property
    def base_url(self) -> str | None:
        return (self.env.nebius_base_url or "").strip() or self.capabilities.base_url

    def model_for(self, role: str) -> ResolvedModel | None:
        """Model for a role: env override first, then capabilities.json. ``None`` if unknown."""
        override = getattr(self.env, f"polarity_model_{role}", None)
        if override and override.strip():
            info = self.capabilities.models.get(role)
            case = info.case if info and info.id == override.strip() else None
            return ResolvedModel(role, override.strip(), case)
        info = self.capabilities.models.get(role)
        if info and info.id:
            if role == "deep" and info.available is False:
                return None
            return ResolvedModel(role, info.id, info.case)
        return None

    def audio_mode(self) -> str:
        """Effective AUDIO_MODE: explicit .env value, else the mode Phase 0 recommended."""
        if self.env.audio_mode != "auto":
            return self.env.audio_mode
        return self.capabilities.audio_mode_recommended

    def routing_table(self) -> list[dict[str, str | None]]:
        """Role → model table for the Debug panel and README."""
        uses = {
            "perception": "Step verification (image ± student audio), voice Q&A, lab-sheet pages, chip markings",
            "fast_text": "Intent classification, shortening long spoken feedback",
            "reasoning": "TA help-request diagnosis, lab-compiler structuring, Tavily tool agent",
            "deep": "End-of-class TA report",
        }
        rows = []
        for role in ROLES:
            model = self.model_for(role)
            rows.append({"role": role, "model": ("MOCK" if self.mock else (model.id if model else None)),
                         "case": model.case if model else None, "used_for": uses[role]})
        return rows


_config: Config | None = None
_config_lock = threading.Lock()


def load_config() -> Config:
    """Build a fresh :class:`Config` from disk and the environment."""
    p = Paths.discover()
    env_path = paths.env_file()
    env = EnvSettings(_env_file=env_path if env_path.exists() else None)  # type: ignore[call-arg]
    settings = AppSettings.load(p.config / "settings.yaml")
    caps = Capabilities.load(p.capabilities)
    prices = load_pricing(p.config / "pricing.yaml")
    return Config(env=env, settings=settings, capabilities=caps, prices=prices, paths=p)


def get_config() -> Config:
    """Process-wide configuration (loaded once; ``reset_config()`` reloads)."""
    global _config
    with _config_lock:
        if _config is None:
            _config = load_config()
        return _config


def reset_config() -> None:
    global _config
    with _config_lock:
        _config = None


def mock_enabled() -> bool:
    """Cheap check usable before the config is built."""
    return os.environ.get("POLARITY_MOCK_MODELS", "0").strip().lower() in ("1", "true", "yes", "on")
