"""Public data types shared by providers, judges and the pipeline."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

VERDICT_FITS = "fits"
VERDICT_PARTIAL = "partially_fits"
VERDICT_MISS = "does_not_fit"
VERDICTS = (VERDICT_FITS, VERDICT_PARTIAL, VERDICT_MISS)

MAX_DURATION = 190.0
MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class MusicRequest:
    """A prompt plus the theme it must serve."""

    prompt: str
    theme: str = ""
    duration: float = 30.0
    name: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str):
            raise ValueError("prompt must be a string")
        if not isinstance(self.theme, str):
            raise ValueError("theme must be a string")
        if not isinstance(self.name, str):
            raise ValueError("name must be a string")
        if not isinstance(self.extra, Mapping):
            raise ValueError("extra must be a mapping")
        duration = self.duration
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError("duration must be a number of seconds")
        duration = float(duration)
        if not math.isfinite(duration) or not 0 < duration <= MAX_DURATION:
            raise ValueError(f"duration must be between 0 and {MAX_DURATION:g} seconds")
        prompt = self.prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be empty")
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "theme", self.theme.strip())
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "duration", duration)

    @property
    def intent(self) -> str:
        """The theme when given, else the prompt."""
        return self.theme or self.prompt

    @property
    def label(self) -> str:
        return self.name or self.theme or self.prompt


@dataclass(frozen=True)
class Track:
    path: Path
    provider: str
    model: str
    duration_seconds: float
    prompt: str
    theme: str
    source_url: str | None = None


@dataclass(frozen=True)
class Verdict:
    score: int
    verdict: str
    summary: str
    strengths: tuple[str, ...]
    issues: tuple[str, ...]
    suggestions: tuple[str, ...]
    judge: str
    model: str
    threshold: int = 60

    def __post_init__(self) -> None:
        if isinstance(self.score, bool) or not isinstance(self.score, int) or not 0 <= self.score <= 100:
            raise ValueError("score must be an integer between 0 and 100")
        if self.verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
        if not isinstance(self.summary, str):
            raise ValueError("summary must be a string")
        if not isinstance(self.judge, str) or not isinstance(self.model, str):
            raise ValueError("judge and model must be strings")
        for name in ("strengths", "issues", "suggestions"):
            value = getattr(self, name)
            if not isinstance(value, (tuple, list)) or any(not isinstance(item, str) for item in value):
                raise ValueError(f"{name} must be a sequence of strings")
            object.__setattr__(self, name, tuple(value))
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, int) or not 0 <= self.threshold <= 100:
            raise ValueError("threshold must be an integer between 0 and 100")

    @property
    def accepted(self) -> bool:
        return self.score >= self.threshold


@dataclass(frozen=True)
class Attempt:
    """One rendered take and the verdict that judged it."""

    number: int
    prompt: str
    track: Track
    verdict: Verdict | None
    metadata_path: Path
    judge_error: str | None = None

    @property
    def accepted(self) -> bool:
        return self.verdict is not None and self.verdict.accepted

    @property
    def score(self) -> int | None:
        return None if self.verdict is None else self.verdict.score


@dataclass(frozen=True)
class CompositionResult:
    track: Track
    verdict: Verdict | None
    metadata_path: Path
    judge_error: str | None = None
    attempts: tuple[Attempt, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.verdict is not None and self.verdict.accepted
