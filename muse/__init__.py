"""Muse: prompt-driven music with an automated listener."""

from __future__ import annotations

from .config import MuseConfig
from .errors import ConfigurationError, GenerationError, JudgeError, MuseError
from .pipeline import compose, judge_track
from .types import Attempt, CompositionResult, MusicRequest, Track, Verdict

__all__ = [
    "Attempt",
    "CompositionResult",
    "ConfigurationError",
    "GenerationError",
    "JudgeError",
    "MuseConfig",
    "MuseError",
    "MusicRequest",
    "Track",
    "Verdict",
    "compose",
    "judge_track",
]

__version__ = "0.9.1"
