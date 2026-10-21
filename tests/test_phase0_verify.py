"""Phase 0 verifier: exit codes and the full T1–T12 pipeline against a local fake Token Factory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polarity.verify import assets, run_verify


def _fake_speech(path: Path, record: bool = False) -> assets.AudioAsset:
    # The fake server "hears" banana in any audio, so a short tone stands in for TTS on every OS.
    assets._tone(path, seconds=0.5)
    return assets.AudioAsset(path=path, method="test", modality_proof=True, seconds=0.5)


def test_no_key_exits_4(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_verify.main([]) == run_verify.EXIT_NO_KEY
    assert "NEBIUS_API_KEY" in capsys.readouterr().out


def test_unreachable_exits_3(monkeypatch: pytest.MonkeyPatch, isolated_env: Path) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-0000-1234")
    monkeypatch.setenv("NEBIUS_BASE_URL", "http://127.0.0.1:9/v1/")  # discard port: nothing listens
    assert run_verify.main(["--skip-video"]) == run_verify.EXIT_UNREACHABLE
    report = (isolated_env / "docs" / "PHASE0_REPORT.md").read_text(encoding="utf-8")
    assert "none reachable" in report
    assert "test-key-0000-1234" not in report  # key is masked
    assert not (isolated_env / "data" / "capabilities.json").exists()


def test_full_pipeline_against_fake_server(fake_token_factory: str, monkeypatch: pytest.MonkeyPatch,
                                           isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-0000-1234")
    monkeypatch.setenv("NEBIUS_BASE_URL", fake_token_factory)
    monkeypatch.setattr(assets, "make_speech_wav", _fake_speech)

    code = run_verify.main(["--skip-video"])
    out = capsys.readouterr().out
    assert code == run_verify.EXIT_OK, out

    caps = json.loads((isolated_env / "data" / "capabilities.json").read_text(encoding="utf-8"))
    assert caps["base_url"] == fake_token_factory
    assert caps["models"]["perception"]["id"] == "nvidia/Nemotron-3-Nano-Omni-30B-A3B"
    assert caps["models"]["perception"]["case"] == "lowercase"  # exact ID was rejected, lowercase worked
    assert caps["models"]["fast_text"]["id"] == "nvidia/nvidia-nemotron-3-nano-30b-a3b"
    assert caps["models"]["reasoning"]["id"] == "nvidia/nemotron-3-super-120b-a12b"
    assert caps["models"]["deep"] == {**caps["models"]["deep"], "id": "nvidia/nemotron-3-ultra-253b", "available": True}
    assert caps["image_input"] is True
    assert caps["audio_input"] == {"supported": True, "variant": "audio_url"}
    assert caps["combined_image_audio"] == "VERIFIED"
    assert caps["video_input"] == "SKIPPED"
    assert caps["json_mode"] == "json_object"
    assert caps["tools_mode"] == "native"
    assert caps["thinking_control"] == "chat_template_kwargs"
    assert caps["audio_mode_recommended"] == "omni_combined"

    report = (isolated_env / "docs" / "PHASE0_REPORT.md").read_text(encoding="utf-8")
    assert "OMNI COMBINED IMAGE+AUDIO:** `VERIFIED`" in report
    assert "test-key-0000-1234" not in report

    assert ("MODEL IDS → perception=nvidia/Nemotron-3-Nano-Omni-30B-A3B | reasoning=nvidia/nemotron-3-super-120b-a12b"
            " | deep=nvidia/nemotron-3-ultra-253b | fast_text=nvidia/nvidia-nemotron-3-nano-30b-a3b") in out
    assert "OMNI COMBINED IMAGE+AUDIO → VERIFIED" in out


def test_board_asset_is_png(tmp_path: Path) -> None:
    path = assets.make_board_png(tmp_path / "board.png")
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_wav_normalisation_roundtrip(tmp_path: Path) -> None:
    import numpy as np

    src = tmp_path / "in.wav"
    t = np.arange(22050, dtype=np.float32) / 22050
    assets.write_wav_pcm16(src, 0.5 * np.sin(2 * np.pi * 440 * t), 22050)
    seconds = assets.normalise_wav(src, tmp_path / "out.wav")
    data, sr = assets.read_wav_mono(tmp_path / "out.wav")
    assert sr == 16000
    assert abs(seconds - 1.0) < 0.01
    assert abs(float(np.max(np.abs(data))) - 0.5) < 0.05
