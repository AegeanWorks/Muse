"""Small audio helpers that need no third-party packages."""

from __future__ import annotations

import math
import os
import re
import struct
import unicodedata
import uuid
import wave
from pathlib import Path

_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}

_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)

_TURKISH = str.maketrans({"ı": "i", "İ": "I", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"})


def slugify(text: str, fallback: str = "track") -> str:
    transliterated = unicodedata.normalize("NFKD", text.translate(_TURKISH))
    ascii_text = transliterated.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    slug = slug[:48].rstrip("-") or fallback
    return f"{slug}-track" if slug in _WINDOWS_RESERVED else slug


def mime_type(path: Path) -> str:
    return _MIME.get(path.suffix.lower(), "audio/wav")


def wav_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            return handle.getnframes() / float(rate) if rate else None
    except (wave.Error, OSError, EOFError):
        return None


def write_tone(path: Path, seconds: float, sample_rate: int = 8000) -> None:
    """Write a quiet sine chord so offline mocks produce a valid WAV."""
    path = Path(path)
    frames = max(1, int(seconds * sample_rate))
    data = bytearray()
    for index in range(frames):
        sample = math.sin(2 * math.pi * 220 * index / sample_rate)
        sample += 0.5 * math.sin(2 * math.pi * 277.18 * index / sample_rate)
        data += struct.pack("<h", int(sample / 1.5 * 6000))
    temporary = path.with_name(f".{path.name}.tmp_{uuid.uuid4().hex[:8]}")
    try:
        with wave.open(str(temporary), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(bytes(data))
        descriptor = os.open(temporary, os.O_RDWR)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
