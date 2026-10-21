"""README live blocks: model table after verify, eval headline after a real eval; mock runs never touch it."""

from __future__ import annotations

from pathlib import Path

from polarity import docs_sync
from polarity.engine.evaluate import Prediction, summarise

README = """# Title
before
<!-- MODELS:START -->
old models
<!-- MODELS:END -->
middle
<!-- EVAL:START -->
old eval
<!-- EVAL:END -->
after
"""


def test_models_block_replaced_only_between_markers(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(README, encoding="utf-8")
    caps = {"generated_at": "2026-10-22T10:00:00+08:00", "base_url": "https://api.example/v1/",
            "combined_image_audio": "VERIFIED", "json_mode": "json_schema", "thinking_control": "chat_template_kwargs",
            "tools_mode": "native", "audio_mode_recommended": "omni_combined",
            "models": {"perception": {"id": "nvidia/omni-x", "case": "exact", "latency_ms": 1234}}}
    assert docs_sync.update_readme_models(caps, readme)
    text = readme.read_text(encoding="utf-8")
    assert "`nvidia/omni-x`" in text and "1234 ms" in text and "old models" not in text
    assert text.startswith("# Title\nbefore\n") and text.endswith("after\n") and "old eval" in text


def test_eval_block_real_only(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(README, encoding="utf-8")
    preds = [Prediction("s3", "correct", "a.jpg", "pass", "pass", "model:pass", 0.9, [], None, False, "m", 1000, None, True)]
    mock = summarise(preds, "20261026-101500_mock", True, "data/demo/lab1")
    assert not docs_sync.update_readme_eval(mock, readme) and "old eval" in readme.read_text(encoding="utf-8")
    real = summarise(preds, "20261026-101500", False, "data/eval/lab1")
    assert docs_sync.update_readme_eval(real, readme)
    assert "Selective accuracy" in readme.read_text(encoding="utf-8")


def test_default_readme_path_follows_docs_dir(isolated_env: Path) -> None:
    assert docs_sync.readme_path() == isolated_env / "README.md"  # tests can never edit the repo README
