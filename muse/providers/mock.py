"""Offline provider used by tests and demos."""

from __future__ import annotations

from pathlib import Path

from ..audio import write_tone
from ..config import MuseConfig
from ..types import MusicRequest, Track

DEMO_SECONDS = 2.0


class MockMusicProvider:
    name = "mock"
    model = "mock-tone"

    def __init__(self, config: MuseConfig | None = None) -> None:
        self.config = config

    def generate(self, request: MusicRequest, destination: Path) -> Track:
        path = destination / "track.wav"
        write_tone(path, min(request.duration, DEMO_SECONDS))
        return Track(
            path=path,
            provider=self.name,
            model=self.model,
            duration_seconds=min(request.duration, DEMO_SECONDS),
            prompt=request.prompt,
            theme=request.theme,
        )
