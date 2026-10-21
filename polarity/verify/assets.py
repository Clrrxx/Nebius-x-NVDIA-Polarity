"""Phase 0 test assets, designed so that each answer *proves* the modality was processed.

- ``board.png``: a drawn breadboard with a clearly RED LED and the label "TEST BOARD 7".
- ``speech.wav``: 16 kHz mono PCM16 speech, "Hello, this is a test. The secret word is banana."
- ``count.mp4``: optional 3 s clip showing large digits 1 → 2 → 3.

Dependencies: Pillow, numpy and the standard library (OpenCV only for the optional video).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from polarity.audio import read_wav_mono, resample_linear, write_wav_pcm16  # noqa: F401 - re-exported
from polarity.imaging import get_font

SPEECH_TEXT = "Hello, this is a test. The secret word is banana."
TARGET_SR = 16000


@dataclass
class AudioAsset:
    path: Path
    method: str           # say | powershell | espeak-ng | record | tone
    modality_proof: bool  # False when only a tone could be produced (cannot prove audio understanding)
    seconds: float


# ── image ────────────────────────────────────────────────────────────────────────────────────────

def make_board_png(path: Path) -> Path:
    """Draw a 1024×768 test breadboard with a red LED, a resistor and a big "TEST BOARD 7" label."""
    w, h = 1024, 768
    img = Image.new("RGB", (w, h), (58, 62, 70))
    d = ImageDraw.Draw(img)

    # Label card sized to the measured text so every character (especially the "7") sits on white
    font = get_font(72, bold=True)
    text = "TEST BOARD 7"
    left, top, right, bottom = d.textbbox((0, 0), text, font=font)
    tw, th = right - left, bottom - top
    pad_x, pad_y = 40, 26
    cx0 = (w - tw) / 2 - pad_x
    cy0 = 34
    d.rounded_rectangle((cx0, cy0, cx0 + tw + 2 * pad_x, cy0 + th + 2 * pad_y), radius=16,
                        fill=(248, 246, 240), outline=(30, 30, 30), width=4)
    d.text((cx0 + pad_x - left, cy0 + pad_y - top), text, fill=(15, 15, 15), font=font)

    # Breadboard body
    x0, y0, x1, y1 = 80, 200, 944, 720
    d.rounded_rectangle((x0, y0, x1, y1), radius=14, fill=(232, 229, 220), outline=(170, 166, 156), width=3)
    pitch = 26
    cols = list(range(x0 + 40, x1 - 30, pitch))

    def holes(y: int) -> None:
        for x in cols:
            d.rectangle((x - 5, y - 5, x + 5, y + 5), fill=(70, 70, 70))

    # Top rails: red (+) line and blue (−) line
    d.line((x0 + 20, y0 + 22, x1 - 20, y0 + 22), fill=(220, 30, 30), width=5)
    holes(y0 + 42)
    holes(y0 + 68)
    d.line((x0 + 20, y0 + 88, x1 - 20, y0 + 88), fill=(30, 70, 220), width=5)
    # Main area rows a–e
    for i in range(5):
        holes(y0 + 130 + i * pitch)
    # Centre channel
    d.rectangle((x0 + 10, y0 + 252, x1 - 10, y0 + 272), fill=(205, 201, 190))
    # Rows f–j
    for i in range(5):
        holes(y0 + 300 + i * pitch)
    # Bottom rails
    d.line((x0 + 20, y0 + 438, x1 - 20, y0 + 438), fill=(30, 70, 220), width=5)
    holes(y0 + 458)
    holes(y0 + 484)
    d.line((x0 + 20, y0 + 504, x1 - 20, y0 + 504), fill=(220, 30, 30), width=5)

    # Resistor (beige body, brown-black-brown-gold bands) spanning two holes on row b
    ry = y0 + 130 + pitch
    rx0, rx1 = cols[6], cols[11]
    d.line((rx0, ry, rx1, ry), fill=(150, 150, 150), width=4)
    d.rounded_rectangle((rx0 + 28, ry - 13, rx1 - 28, ry + 13), radius=10, fill=(214, 186, 140), outline=(120, 95, 60))
    bx = rx0 + 42
    for colour in ((120, 66, 20), (20, 20, 20), (120, 66, 20), (200, 160, 40)):
        d.rectangle((bx, ry - 13, bx + 8, ry + 13), fill=colour)
        bx += 16

    # Clearly RED LED (5 mm dome seen from above) on row c
    lx, ly = cols[16], y0 + 130 + 2 * pitch + 13
    d.ellipse((lx - 34, ly - 34, lx + 34, ly + 34), fill=(200, 10, 10), outline=(120, 0, 0), width=4)
    d.ellipse((lx - 16, ly - 22, lx + 2, ly - 6), fill=(255, 140, 140))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")
    return path


# ── audio ────────────────────────────────────────────────────────────────────────────────────────

def normalise_wav(src: Path, dst: Path, sr_out: int = TARGET_SR) -> float:
    """Convert any PCM WAV to 16 kHz mono PCM16. Returns the duration in seconds."""
    data, sr = read_wav_mono(src)
    out = resample_linear(data, sr, sr_out)
    write_wav_pcm16(dst, out, sr_out)
    return out.size / float(sr_out)


def _tts_macos(text: str, out: Path) -> bool:
    if not shutil.which("say"):
        return False
    cmd = ["say", "-o", str(out), "--file-format=WAVE", "--data-format=LEI16@16000", text]
    proc = subprocess.run(cmd, capture_output=True, timeout=60)
    return proc.returncode == 0 and out.exists() and out.stat().st_size > 1000


def _tts_windows(text: str, out: Path) -> bool:
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        return False
    p = str(out).replace("'", "''")
    t = text.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{p}'); "
        f"$s.Speak('{t}'); "
        "$s.Dispose()"
    )
    proc = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, timeout=90)
    return proc.returncode == 0 and out.exists() and out.stat().st_size > 1000


def _tts_linux(text: str, out: Path) -> bool:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        return False
    proc = subprocess.run([exe, "-w", str(out), text], capture_output=True, timeout=60)
    return proc.returncode == 0 and out.exists() and out.stat().st_size > 1000


def _record_mic(out: Path, seconds: float = 5.0) -> bool:
    try:
        import sounddevice as sd  # optional extra: requirements-audio.txt
    except ImportError:
        print("sounddevice is not installed: pip install -r requirements-audio.txt")
        return False
    print(f'Recording {seconds:.0f} s now. Please say: "{SPEECH_TEXT}"')
    rec = sd.rec(int(seconds * TARGET_SR), samplerate=TARGET_SR, channels=1, dtype="float32")
    sd.wait()
    write_wav_pcm16(out, rec[:, 0], TARGET_SR)
    return True


def _tone(out: Path, seconds: float = 2.0, freq: float = 1000.0) -> None:
    t = np.arange(int(seconds * TARGET_SR), dtype=np.float32) / TARGET_SR
    write_wav_pcm16(out, 0.3 * np.sin(2 * np.pi * freq * t), TARGET_SR)


def make_speech_wav(path: Path, record: bool = False) -> AudioAsset:
    """Produce the spoken test phrase as 16 kHz mono PCM16, using the best method for this OS.

    Order: ``--record`` (mic) → macOS ``say`` → Windows System.Speech → Linux ``espeak-ng`` →
    a 1 kHz tone flagged ``modality_proof=False`` (acceptance only; cannot prove understanding).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.wav"
        method = None
        if record and _record_mic(raw):
            method = "record"
        elif sys.platform == "darwin" and _tts_macos(SPEECH_TEXT, raw):
            method = "say"
        elif os.name == "nt" and _tts_windows(SPEECH_TEXT, raw):
            method = "powershell"
        elif sys.platform.startswith("linux") and _tts_linux(SPEECH_TEXT, raw):
            method = "espeak-ng"
        if method:
            try:
                seconds = normalise_wav(raw, path)
                return AudioAsset(path=path, method=method, modality_proof=True, seconds=seconds)
            except (wave.Error, ValueError, EOFError) as exc:
                print(f"Could not read the generated speech ({exc}); falling back to a tone.")
    _tone(path)
    return AudioAsset(path=path, method="tone", modality_proof=False, seconds=2.0)


# ── video (optional) ─────────────────────────────────────────────────────────────────────────────

def make_count_mp4(path: Path) -> Path | None:
    """3 s, 10 fps clip showing big digits 1 → 2 → 3. Returns None if OpenCV cannot write MP4 here."""
    try:
        import cv2
    except ImportError:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    size = (640, 480)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, size)
    if not writer.isOpened():
        return None
    try:
        for digit in ("1", "2", "3"):
            frame = np.full((size[1], size[0], 3), 245, dtype=np.uint8)
            cv2.putText(frame, digit, (220, 360), cv2.FONT_HERSHEY_SIMPLEX, 10.0, (20, 20, 20), 24, cv2.LINE_AA)
            for _ in range(10):
                writer.write(frame)
    finally:
        writer.release()
    if not path.exists() or path.stat().st_size == 0:
        return None
    return path
