"""The generation boundary every music provider implements."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..types import MusicRequest, Track


class MusicProvider(Protocol):
    name: str
    model: str

    def generate(self, request: MusicRequest, destination: Path) -> Track:
        """Render the request into a file inside destination."""
        ...
