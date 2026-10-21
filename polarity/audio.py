"""WAV helpers: read/resample/write PCM and validate uploaded voice clips (standard library + numpy only)."""

from __future__ import annotations

import io
import wave
from pathlib import Path

import numpy as np

TARGET_SR = 16000
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


class AudioError(ValueError):
    """An uploaded clip is not a usable WAV file."""


def _decode(raw: bytes, sw: int, ch: int) -> np.ndarray:
    if sw == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        ints = b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16)
        ints = np.where(ints & 0x800000, ints - 0x1000000, ints)
        data = ints.astype(np.float32) / 8388608.0
    elif sw == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise AudioError(f"Unsupported WAV sample width: {sw}")
    if ch > 1:
        data = data[: len(data) - len(data) % ch].reshape(-1, ch).mean(axis=1)
    return data


def read_wav_bytes(data: bytes) -> tuple[np.ndarray, int]:
    """Decode PCM WAV bytes to mono float32 in [-1, 1]."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            sr, ch, sw = wf.getframerate(), wf.getnchannels(), wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
    except (wave.Error, EOFError) as exc:
        raise AudioError(f"Not a PCM WAV file ({exc}).") from exc
    return _decode(raw, sw, ch), sr


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    return read_wav_bytes(path.read_bytes())


def resample_linear(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Linear-interpolation resampler (adequate for speech intelligibility)."""
    if sr_in == sr_out or x.size == 0:
        return x.astype(np.float32)
    n_out = max(1, round(x.size * sr_out / sr_in))
    t_in = np.arange(x.size, dtype=np.float64) / sr_in
    t_out = np.arange(n_out, dtype=np.float64) / sr_out
    return np.interp(t_out, t_in, x).astype(np.float32)


def encode_wav_pcm16(samples: np.ndarray, sr: int) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def write_wav_pcm16(path: Path, samples: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_wav_pcm16(samples, sr))


def validate_wav(data: bytes, max_seconds: float = 15.0) -> tuple[bytes, float]:
    """Check an uploaded voice clip and return it as 16 kHz mono PCM16 plus its duration in seconds."""
    if not data:
        raise AudioError("Empty audio upload.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AudioError("Audio file is too large.")
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AudioError("Audio must be a WAV file.")
    samples, sr = read_wav_bytes(data)
    if sr < 8000 or sr > 96000:
        raise AudioError(f"Unsupported sample rate: {sr} Hz.")
    duration = samples.size / float(sr)
    if duration > max_seconds + 0.5:
        raise AudioError(f"Audio is {duration:.1f} s long; the limit is {max_seconds:.0f} s.")
    if duration < 0.2:
        raise AudioError("Audio is too short.")
    return encode_wav_pcm16(resample_linear(samples, sr, TARGET_SR), TARGET_SR), duration
