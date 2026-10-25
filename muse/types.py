"""Public data types shared by providers, judges and the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

VERDICT_FITS = "fits"
VERDICT_PARTIAL = "partially_fits"
VERDICT_MISS = "does_not_fit"
VERDICTS = (VERDICT_FITS, VERDICT_PARTIAL, VERDICT_MISS)

MAX_DURATION = 190.0


@dataclass(frozen=True)
class MusicRequest:
    """A prompt plus the theme it must serve."""

    prompt: str
    theme: str = ""
    duration: float = 30.0
    name: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        prompt = self.prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be empty")
        if not 0 < self.duration <= MAX_DURATION:
            raise ValueError(f"duration must be between 0 and {MAX_DURATION:g} seconds")
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "theme", self.theme.strip())

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

    @property
    def accepted(self) -> bool:
        return self.score >= self.threshold


@dataclass(frozen=True)
class CompositionResult:
    track: Track
    verdict: Verdict | None
    metadata_path: Path
    judge_error: str | None = None

    @property
    def accepted(self) -> bool:
        return self.verdict is not None and self.verdict.accepted
