"""Requirement-based analysis: does a rendered track serve the consuming project?"""

from __future__ import annotations

import json
import math
import operator
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .types import Fit

MAX_REQUIREMENTS_BYTES = 64_000
REQUIREMENT_KEYS = (
    "min_duration",
    "max_duration",
    "min_sample_rate",
    "sample_rates",
    "channels",
    "sample_width_bits",
    "min_rms_dbfs",
    "max_peak_dbfs",
    "max_size_mb",
    "require_accepted",
    "min_score",
)
READ_CHUNK_FRAMES = 65_536
# Limits a provider fixes for every take, so rendering again cannot change the result.
FORMAT_LIMITS = frozenset({"channels", "sample_width_bits", "min_sample_rate", "sample_rates"})


@dataclass(frozen=True)
class TrackRequirements:
    """Optional limits a consuming project states for one or more tracks."""

    min_duration: float | None = None
    max_duration: float | None = None
    min_sample_rate: int | None = None
    channels: tuple[int, ...] | None = None
    sample_width_bits: tuple[int, ...] | None = None
    min_rms_dbfs: float | None = None
    max_peak_dbfs: float | None = None
    max_size_mb: float | None = None
    require_accepted: bool | None = None
    min_score: int | None = None
    sample_rates: tuple[int, ...] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.min_duration is not None:
            payload["min_duration"] = self.min_duration
        if self.max_duration is not None:
            payload["max_duration"] = self.max_duration
        if self.min_sample_rate is not None:
            payload["min_sample_rate"] = self.min_sample_rate
        if self.sample_rates is not None:
            payload["sample_rates"] = list(self.sample_rates)
        if self.channels is not None:
            payload["channels"] = list(self.channels)
        if self.sample_width_bits is not None:
            payload["sample_width_bits"] = list(self.sample_width_bits)
        if self.min_rms_dbfs is not None:
            payload["min_rms_dbfs"] = self.min_rms_dbfs
        if self.max_peak_dbfs is not None:
            payload["max_peak_dbfs"] = self.max_peak_dbfs
        if self.max_size_mb is not None:
            payload["max_size_mb"] = self.max_size_mb
        if self.require_accepted is not None:
            payload["require_accepted"] = self.require_accepted
        if self.min_score is not None:
            payload["min_score"] = self.min_score
        return payload


@dataclass(frozen=True)
class AudioProfile:
    duration: float
    sample_rate: int
    channels: int
    sample_width: int
    peak_dbfs: float
    rms_dbfs: float
    clipped_percent: float
    size_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "duration_seconds": round(self.duration, 3),
            "sample_rate_hz": self.sample_rate,
            "channels": self.channels,
            "sample_width_bits": self.sample_width * 8,
            "peak_dbfs": round(self.peak_dbfs, 2),
            "rms_dbfs": round(self.rms_dbfs, 2),
            "clipped_percent": round(self.clipped_percent, 4),
            "size_bytes": self.size_bytes,
        }


def load_requirements(path: Path) -> TrackRequirements:
    source = Path(path)
    try:
        # hygiene: allow binary read is capped at MAX_REQUIREMENTS_BYTES + 1; UTF-8 is decoded below
        with source.open("rb") as handle:
            raw = handle.read(MAX_REQUIREMENTS_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"could not read the requirements file: {source}: {exc}") from exc
    if len(raw) > MAX_REQUIREMENTS_BYTES:
        raise ValueError(
            f"the requirements file is above the {MAX_REQUIREMENTS_BYTES} byte limit"
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("the requirements file is not UTF-8 text") from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"the requirements file is not valid JSON: {exc}") from exc
    return requirements_from_mapping(payload)


def requirements_from_mapping(payload: object) -> TrackRequirements:
    if not isinstance(payload, Mapping):
        raise ValueError("the requirements document must be a JSON object")
    unknown = sorted(set(payload) - set(REQUIREMENT_KEYS))
    if unknown:
        raise ValueError(
            f"unknown requirement(s): {', '.join(unknown)}; "
            f"known keys are {', '.join(REQUIREMENT_KEYS)}"
        )
    if not payload:
        raise ValueError("the requirements document needs at least one key")
    min_duration = _number(payload, "min_duration", positive=True)
    max_duration = _number(payload, "max_duration", positive=True)
    if (
        min_duration is not None
        and max_duration is not None
        and min_duration > max_duration
    ):
        raise ValueError("min_duration must not be greater than max_duration")
    channels = _channels(payload)
    return TrackRequirements(
        min_duration=min_duration,
        max_duration=max_duration,
        min_sample_rate=_whole(payload, "min_sample_rate", low=1, high=384_000),
        channels=channels,
        sample_rates=_rates(payload),
        sample_width_bits=_widths(payload),
        min_rms_dbfs=_number(payload, "min_rms_dbfs", low=-120.0, high=0.0),
        max_peak_dbfs=_number(payload, "max_peak_dbfs", low=-120.0, high=0.0),
        max_size_mb=_number(payload, "max_size_mb", positive=True),
        require_accepted=_flag(payload, "require_accepted"),
        min_score=_whole(payload, "min_score", low=0, high=100),
    )


def analyze_audio(path: Path) -> tuple[AudioProfile | None, str]:
    """Measure a WAV file; return the profile and an empty reason, or None and why not."""
    source = Path(path)
    try:
        size_bytes = source.stat().st_size
    except OSError as exc:
        return None, f"the audio file could not be read: {exc}"
    try:
        with wave.open(str(source), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            if width not in (1, 2, 3, 4):
                return None, f"{width * 8}-bit PCM is not analysed"
            if rate <= 0 or channels <= 0:
                return None, "the WAV header has an invalid rate or channel count"
            full_scale = float(1 << (width * 8 - 1))
            peak = 0
            square_sum = 0
            samples = 0
            clipped = 0
            high = int(full_scale) - 1
            low = -int(full_scale)
            while True:
                # hygiene: allow bounded streaming read; only PCM statistics are computed
                data = handle.readframes(READ_CHUNK_FRAMES)
                if not data:
                    break
                # A file cut mid-sample leaves a partial sample at the end; drop it.
                values = pcm_values(data[: len(data) - len(data) % width], width)
                if not values:
                    break
                chunk_peak = max(map(abs, values))
                if chunk_peak > peak:
                    peak = chunk_peak
                square_sum += sum(map(operator.mul, values, values))
                clipped += values.count(high) + values.count(low)
                samples += len(values)
    except (wave.Error, EOFError, OSError, struct.error) as exc:
        return None, f"the WAV file could not be decoded: {exc}"
    if not samples:
        return None, "the WAV file holds no samples"
    # The header may promise more frames than the file holds; measure what is really there.
    duration = (samples // channels) / float(rate)
    peak_dbfs = _dbfs(peak / full_scale)
    rms_dbfs = _dbfs(math.sqrt(square_sum / samples) / full_scale)
    profile = AudioProfile(
        duration=duration,
        sample_rate=rate,
        channels=channels,
        sample_width=width,
        peak_dbfs=peak_dbfs,
        rms_dbfs=rms_dbfs,
        clipped_percent=100.0 * clipped / samples,
        size_bytes=size_bytes,
    )
    return profile, ""


def evaluate(
    profile: AudioProfile | None,
    requirements: TrackRequirements,
    evidence: Mapping[str, Any] | None,
    reason: str = "",
) -> dict[str, Any]:
    """Return one artifact's checks: passed when no check fails."""
    checks: list[dict[str, Any]] = []
    unavailable = reason or "the audio is not a WAV file this analyzer can read"

    def measure(check: str, expected: Any, actual: Any, ok: bool, detail: str) -> None:
        checks.append(
            {
                "check": check,
                "status": "pass" if ok else "fail",
                "expected": expected,
                "actual": actual,
                "detail": detail,
            }
        )

    def skip(check: str, expected: Any) -> None:
        checks.append(
            {
                "check": check,
                "status": "skipped",
                "expected": expected,
                "actual": None,
                "detail": unavailable,
            }
        )

    if requirements.min_duration is not None:
        if profile is None:
            skip("min_duration", requirements.min_duration)
        else:
            measure(
                "min_duration",
                requirements.min_duration,
                profile.duration,
                profile.duration >= requirements.min_duration,
                f"the track is {profile.duration:.2f}s",
            )
    if requirements.max_duration is not None:
        if profile is None:
            skip("max_duration", requirements.max_duration)
        else:
            measure(
                "max_duration",
                requirements.max_duration,
                profile.duration,
                profile.duration <= requirements.max_duration,
                f"the track is {profile.duration:.2f}s",
            )
    if requirements.min_sample_rate is not None:
        if profile is None:
            skip("min_sample_rate", requirements.min_sample_rate)
        else:
            measure(
                "min_sample_rate",
                requirements.min_sample_rate,
                profile.sample_rate,
                profile.sample_rate >= requirements.min_sample_rate,
                f"the track is {profile.sample_rate} Hz",
            )
    if requirements.sample_rates is not None:
        if profile is None:
            skip("sample_rates", list(requirements.sample_rates))
        else:
            measure(
                "sample_rates",
                list(requirements.sample_rates),
                profile.sample_rate,
                profile.sample_rate in requirements.sample_rates,
                f"the track is {profile.sample_rate} Hz",
            )
    if requirements.channels is not None:
        if profile is None:
            skip("channels", list(requirements.channels))
        else:
            measure(
                "channels",
                list(requirements.channels),
                profile.channels,
                profile.channels in requirements.channels,
                f"the track has {profile.channels} channel(s)",
            )
    if requirements.sample_width_bits is not None:
        if profile is None:
            skip("sample_width_bits", list(requirements.sample_width_bits))
        else:
            bits = profile.sample_width * 8
            measure(
                "sample_width_bits",
                list(requirements.sample_width_bits),
                bits,
                bits in requirements.sample_width_bits,
                f"the track is {bits}-bit PCM",
            )
    if requirements.min_rms_dbfs is not None:
        if profile is None:
            skip("min_rms_dbfs", requirements.min_rms_dbfs)
        else:
            measure(
                "min_rms_dbfs",
                requirements.min_rms_dbfs,
                round(profile.rms_dbfs, 2),
                profile.rms_dbfs >= requirements.min_rms_dbfs,
                f"RMS loudness is {profile.rms_dbfs:.2f} dBFS",
            )
    if requirements.max_peak_dbfs is not None:
        if profile is None:
            skip("max_peak_dbfs", requirements.max_peak_dbfs)
        else:
            measure(
                "max_peak_dbfs",
                requirements.max_peak_dbfs,
                round(profile.peak_dbfs, 2),
                profile.peak_dbfs <= requirements.max_peak_dbfs,
                f"peak level is {profile.peak_dbfs:.2f} dBFS",
            )
    if requirements.max_size_mb is not None:
        if profile is None:
            skip("max_size_mb", requirements.max_size_mb)
        else:
            limit = requirements.max_size_mb * 1_000_000
            measure(
                "max_size_mb",
                requirements.max_size_mb,
                round(profile.size_bytes / 1_000_000, 3),
                profile.size_bytes <= limit,
                f"the file is {profile.size_bytes} bytes",
            )
    accepted = evidence.get("accepted") if isinstance(evidence, Mapping) else None
    score = evidence.get("score") if isinstance(evidence, Mapping) else None
    if isinstance(accepted, bool):
        if requirements.require_accepted:
            measure(
                "require_accepted",
                True,
                accepted,
                accepted,
                "the judge accepted the track" if accepted else "the judge rejected the track",
            )
    elif requirements.require_accepted:
        checks.append(
            {
                "check": "require_accepted",
                "status": "skipped",
                "expected": True,
                "actual": None,
                "detail": "no judge evidence; run `muse judge` or pass an artifact folder",
            }
        )
    if requirements.min_score is not None:
        if isinstance(score, int) and not isinstance(score, bool):
            measure(
                "min_score",
                requirements.min_score,
                score,
                score >= requirements.min_score,
                f"the judge scored {score}/100",
            )
        else:
            checks.append(
                {
                    "check": "min_score",
                    "status": "skipped",
                    "expected": requirements.min_score,
                    "actual": None,
                    "detail": "no judge score; run `muse judge` or pass an artifact folder",
                }
            )
    failed = [check["check"] for check in checks if check["status"] == "fail"]
    skipped = [check["check"] for check in checks if check["status"] == "skipped"]
    return {
        "ok": not failed,
        "checks": checks,
        "failed": failed,
        "skipped": skipped,
        "profile": None if profile is None else profile.as_dict(),
    }


def requirement_fit(result: Mapping[str, Any]) -> Fit:
    """Summarise an `evaluate` result as a Fit, with prompt hints for the misses a prompt can fix.

    A track that misses a format limit is blocked and carries no hint, since no retry can fix it.
    Only duration misses carry a hint: loudness, sample rate, channels and bit depth are
    provider or format settings, so rewording the prompt cannot change them. A low judge score
    is retried through the judge's own suggestions, so it needs no hint here.
    """
    failed = tuple(str(name) for name in result.get("failed", ()))
    blocked = tuple(name for name in failed if name in FORMAT_LIMITS)
    hints: list[str] = []
    for check in result.get("checks", ()):
        if check.get("status") != "fail":
            continue
        expected, actual = check.get("expected"), check.get("actual")
        if check.get("check") == "min_duration" and isinstance(actual, (int, float)):
            hints.append(f"make the track at least {expected:g} seconds long (the last take was {actual:.1f}s)")
        elif check.get("check") == "max_duration" and isinstance(actual, (int, float)):
            hints.append(f"keep the track under {expected:g} seconds (the last take was {actual:.1f}s)")
    return Fit(ok=not failed, failed=failed, hints=() if blocked else tuple(hints), blocked=blocked)


def pcm_values(data: bytes, width: int) -> list[int]:
    if width == 1:
        return [value - 128 for value in data]
    if width == 2:
        return list(struct.unpack(f"<{len(data) // 2}h", data))
    if width == 3:
        return [
            int.from_bytes(data[index : index + 3], "little", signed=True)
            for index in range(0, len(data) - 2, 3)
        ]
    return list(struct.unpack(f"<{len(data) // 4}i", data))


def _dbfs(ratio: float) -> float:
    if ratio <= 0:
        return -120.0
    return max(-120.0, 20.0 * math.log10(ratio))


def _number(
    payload: Mapping[str, Any],
    key: str,
    *,
    positive: bool = False,
    low: float | None = None,
    high: float | None = None,
) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    if positive and number <= 0:
        raise ValueError(f"{key} must be greater than 0")
    if low is not None and number < low:
        raise ValueError(f"{key} must be at least {low:g}")
    if high is not None and number > high:
        raise ValueError(f"{key} must be at most {high:g}")
    return number


def _whole(
    payload: Mapping[str, Any], key: str, *, low: int, high: int
) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be a whole number")
    if not low <= value <= high:
        raise ValueError(f"{key} must be between {low} and {high}")
    return value


def _channels(payload: Mapping[str, Any]) -> tuple[int, ...] | None:
    value = payload.get("channels")
    if value is None:
        return None
    values = [value] if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(values, list) or not values:
        raise ValueError("channels must be a channel count or a non-empty list of counts")
    counts: list[int] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 8:
            raise ValueError("each channel count must be a whole number between 1 and 8")
        if item not in counts:
            counts.append(item)
    return tuple(counts)


def _rates(payload: Mapping[str, Any]) -> tuple[int, ...] | None:
    value = payload.get("sample_rates")
    if value is None:
        return None
    values = [value] if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(values, list) or not values:
        raise ValueError("sample_rates must be a rate in Hz or a non-empty list of rates")
    rates: list[int] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 384_000:
            raise ValueError("each sample rate must be a whole number of Hz from 1 to 384000")
        if item not in rates:
            rates.append(item)
    return tuple(rates)


def _widths(payload: Mapping[str, Any]) -> tuple[int, ...] | None:
    value = payload.get("sample_width_bits")
    if value is None:
        return None
    values = [value] if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(values, list) or not values:
        raise ValueError(
            "sample_width_bits must be a bit depth or a non-empty list of bit depths"
        )
    widths: list[int] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, int) or item not in (8, 16, 24, 32):
            raise ValueError("each sample width must be 8, 16, 24 or 32 bits")
        if item not in widths:
            widths.append(item)
    return tuple(widths)


def _flag(payload: Mapping[str, Any], key: str) -> bool | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false")
    if not value:
        raise ValueError(f"{key} must be true; omit it to skip the check")
    return value
