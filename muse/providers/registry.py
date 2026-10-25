"""Name-to-provider lookup so callers never import adapters directly."""

from __future__ import annotations

from ..config import MuseConfig
from ..errors import ConfigurationError
from .base import MusicProvider
from .mock import MockMusicProvider
from .replicate import ReplicateMusicProvider

_BUILDERS = {
    "replicate": ReplicateMusicProvider,
    "mock": MockMusicProvider,
}


def build_provider(name: str, config: MuseConfig) -> MusicProvider:
    builder = _BUILDERS.get(name)
    if builder is None:
        choices = ", ".join(sorted(_BUILDERS))
        raise ConfigurationError(
            f"unknown music provider {name!r}",
            f"available providers are {choices}",
            f"pass --provider {sorted(_BUILDERS)[0]} or set MUSE_PROVIDER",
        )
    return builder(config)


def providers() -> dict[str, str]:
    return {
        "replicate": f"hosted models via Replicate (default: {MuseConfig().music_model})",
        "mock": "offline sine tone for tests and demos",
    }
