"""Name-to-judge lookup so callers never import adapters directly."""

from __future__ import annotations

from ..config import MuseConfig
from ..errors import ConfigurationError
from .base import MusicJudge
from .gemini import GeminiJudge
from .mock import MockJudge

_BUILDERS = {
    "gemini": GeminiJudge,
    "mock": MockJudge,
}


def build_judge(name: str, config: MuseConfig) -> MusicJudge:
    builder = _BUILDERS.get(name)
    if builder is None:
        choices = ", ".join(sorted(_BUILDERS))
        raise ConfigurationError(
            f"unknown judge {name!r}",
            f"available judges are {choices}, or 'none' to skip listening",
            f"pass --judge {sorted(_BUILDERS)[0]} or set MUSE_JUDGE",
        )
    return builder(config)


def judges() -> dict[str, str]:
    return {
        "gemini": f"Gemini listens to the audio and scores theme fit (default: {MuseConfig().judge_model})",
        "mock": "deterministic offline judge for tests and demos",
        "none": "skip judging (not listed as a builder)",
    }
