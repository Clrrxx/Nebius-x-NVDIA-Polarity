"""Lab definition schema (BUILD_PROMPT.md 9.1).

Two optional fields extend the spec and are logged in docs/DECISIONS.md:
- ``CommonError.related_checks``: which check(s) the error violates (used by the mock, the eval harness and
  the UI hint); never sent to the model.
- ``LabDefinition.ai_drafted``: true for lab-compiler output until a TA publishes it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class CommonError(BaseModel):
    id: str                     # e.g. "E_LED_REVERSED"
    description: str            # what it looks like
    visual_cue: str             # how to spot it from above
    fix_hint_l1: str            # where to look
    fix_hint_l2: str            # what's wrong
    fix_hint_l3: str            # exact fix
    related_checks: list[str] = Field(default_factory=list)

    def hint(self, level: int) -> str:
        """Hint text for ladder level 1–3 (clamped)."""
        return {1: self.fix_hint_l1, 2: self.fix_hint_l2}.get(max(1, min(3, level)), self.fix_hint_l3)


class Check(BaseModel):
    id: str                     # e.g. "c_anode_row"
    statement: str              # visually verifiable statement that should be TRUE
    required: bool = True
    allow_uncertain: bool = False   # inherently hard to see; can't-tell won't block pass_partial


class LedCheck(BaseModel):
    expect_lit: bool
    colour: Literal["red", "green", "yellow", "blue", "white"] = "red"
    instruction_for_capture: str    # e.g. "Hold the button down, then press Check"


class Step(BaseModel):
    id: str
    title: str
    instruction: str
    illustration: str | None = None    # svg filename in static/img/steps/
    checks: list[Check]
    common_errors: list[CommonError] = Field(default_factory=list)
    led_check: LedCheck | None = None
    capture_tip: str = "Keep the whole board inside the four markers."

    @model_validator(mode="after")
    def _validate(self) -> Step:
        ids = [c.id for c in self.checks]
        if len(ids) != len(set(ids)):
            raise ValueError(f"step {self.id}: duplicate check ids")
        if not self.checks:
            raise ValueError(f"step {self.id}: at least one check is required")
        for err in self.common_errors:
            unknown = [c for c in err.related_checks if c not in ids]
            if unknown:
                raise ValueError(f"step {self.id}: {err.id} references unknown checks {unknown}")
        return self

    def check(self, check_id: str) -> Check | None:
        return next((c for c in self.checks if c.id == check_id), None)

    def error(self, error_id: str) -> CommonError | None:
        return next((e for e in self.common_errors if e.id == error_id), None)


class LabDefinition(BaseModel):
    id: str
    title: str
    version: str
    summary: str
    kit: list[str]
    safety_notes: list[str]
    breadboard_conventions: str
    steps: list[Step]
    ai_drafted: bool = False

    @model_validator(mode="after")
    def _validate(self) -> LabDefinition:
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate step ids")
        if not self.steps:
            raise ValueError("a lab needs at least one step")
        return self

    def step(self, step_id: str) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def step_index(self, step_id: str) -> int:
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                return i
        raise KeyError(step_id)

    def error_label(self, error_id: str) -> str:
        """Plain-English label for an error id (falls back to the id)."""
        for s in self.steps:
            err = s.error(error_id)
            if err:
                return err.description
        return error_id


def load_lab(path: Path) -> LabDefinition:
    """Load and validate a lab YAML file."""
    with path.open("r", encoding="utf-8") as fh:
        return LabDefinition.model_validate(yaml.safe_load(fh))


def dump_lab(lab: LabDefinition, path: Path) -> None:
    """Write a lab definition as YAML (UTF-8, stable key order)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = lab.model_dump(mode="json")
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True, width=110)


def list_labs(directory: Path) -> dict[str, Path]:
    """Map lab id → YAML path for every valid lab file in ``directory`` (invalid files are skipped)."""
    out: dict[str, Path] = {}
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.yaml")):
        try:
            lab = load_lab(path)
        except Exception:  # noqa: BLE001 - a broken draft must not hide the other labs
            continue
        out[lab.id] = path
    return out
