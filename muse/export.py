"""Export a rendered WAV as the mono 16-bit PCM file an engine loader expects."""

from __future__ import annotations

import os
import struct
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .analysis import READ_CHUNK_FRAMES, pcm_values
from .errors import ConfigurationError, ExportError

MIN_RATE = 8_000
MAX_RATE = 96_000
OUT_SCALE = 32_767


@dataclass(frozen=True)
class ExportResult:
    source: Path
    destination: Path
    rate: int
    frames: int

    @property
    def duration(self) -> float:
        return self.frames / float(self.rate)


def export_wav(
    source: Path,
    destination: Path,
    rate: int,
    chunk_frames: int = READ_CHUNK_FRAMES,
) -> ExportResult:
    """Mix `source` down to mono, resample it to `rate` Hz and write 16-bit PCM atomically.

    The source is read in chunks, so memory stays bounded however long the track is, and the
    result does not depend on the chunk size. Resampling is linear interpolation: fine for game
    music and effects, not for mastering.
    """
    _check_rate(rate)
    origin, target = Path(source), Path(destination)
    if _same_file(origin, target):
        raise ExportError(
            f"the export would overwrite its source: {origin}",
            "the output path is the file being read",
            "pass --out with a different file name",
        )
    temporary = target.with_name(f".{target.name}.tmp_{uuid.uuid4().hex[:8]}")
    try:
        frames = _convert(origin, temporary, rate, chunk_frames)
        descriptor = os.open(temporary, os.O_RDWR)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, target)
    except OSError as exc:
        raise ExportError(
            f"could not write the export: {target}",
            str(exc),
            "check free disk space and folder permissions, then retry",
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return ExportResult(source=origin, destination=target, rate=rate, frames=frames)


def _check_rate(rate: object) -> None:
    if isinstance(rate, bool) or not isinstance(rate, int) or not MIN_RATE <= rate <= MAX_RATE:
        raise ConfigurationError(
            f"unsupported sample rate: {rate!r}",
            f"a rate must be a whole number of Hz from {MIN_RATE} to {MAX_RATE}",
            "pass a rate such as 22050 or 44100",
        )


def _same_file(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except OSError:
        return first.absolute() == second.absolute()


def _convert(source: Path, temporary: Path, rate: int, chunk_frames: int) -> int:
    try:
        with wave.open(str(source), "rb") as reader:
            frames = _stream(reader, source, temporary, rate, chunk_frames)
    except (OSError, EOFError, wave.Error, struct.error) as exc:
        raise ExportError(
            f"could not read the audio: {source}",
            f"the file is not an intact PCM WAV this exporter can open: {exc}",
            "render with a WAV provider, or convert the file to PCM WAV first",
        ) from exc
    if not frames:
        raise ExportError(
            f"the audio holds no samples: {source}",
            "the WAV file has a header but no sample data",
            "render the track again",
        )
    return frames


def _stream(reader: wave.Wave_read, source: Path, temporary: Path, rate: int, chunk_frames: int) -> int:
    channels, width, source_rate = reader.getnchannels(), reader.getsampwidth(), reader.getframerate()
    if width not in (1, 2, 3, 4) or channels < 1 or source_rate < 1:
        raise ExportError(
            f"the WAV header is not usable: {source}",
            f"{channels} channel(s), {width * 8}-bit, {source_rate} Hz",
            "convert the file to PCM WAV with 8, 16, 24 or 32-bit samples",
        )
    mono = _mono_chunks(reader, channels, width, chunk_frames)
    stream = mono if source_rate == rate else _resample(mono, source_rate, rate)
    frames = 0
    with wave.open(str(temporary), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        for block in stream:
            if block:
                try:
                    writer.writeframes(_quantize(block))
                except OSError as exc:
                    raise ExportError(
                        f"could not write the export: {temporary.name}",
                        str(exc),
                        "check free disk space and folder permissions, then retry",
                    ) from exc
                frames += len(block)
    return frames


def _mono_chunks(reader: wave.Wave_read, channels: int, width: int, chunk_frames: int) -> Iterator[list[float]]:
    scale = float((1 << (width * 8 - 1)) - 1)
    while True:
        # hygiene: allow bounded streaming read; only PCM samples are converted
        data = reader.readframes(chunk_frames)
        if not data:
            return
        values = pcm_values(data[: len(data) - len(data) % width], width)
        values = values[: len(values) - len(values) % channels]
        if channels == 1:
            yield [value / scale for value in values]
        else:
            groups = zip(*(values[channel::channels] for channel in range(channels)))
            yield [sum(group) / (channels * scale) for group in groups]


def _resample(chunks: Iterator[list[float]], source_rate: int, target_rate: int) -> Iterator[list[float]]:
    """Linear interpolation with integer positions, so the output ignores chunk boundaries."""
    carry: float | None = None
    base = 0
    produced = 0
    for chunk in chunks:
        data = chunk if carry is None else [carry, *chunk]
        if not data:
            continue
        last = base + len(data) - 1
        block: list[float] = []
        while True:
            numerator = produced * source_rate
            index = numerator // target_rate
            if index + 1 > last:
                break
            fraction = (numerator % target_rate) / target_rate
            low = data[index - base]
            block.append(low + (data[index - base + 1] - low) * fraction)
            produced += 1
        carry = data[-1]
        base = last
        yield block


def _quantize(block: list[float]) -> bytes:
    ints = [max(-OUT_SCALE, min(OUT_SCALE, round(value * OUT_SCALE))) for value in block]
    return struct.pack(f"<{len(ints)}h", *ints)
