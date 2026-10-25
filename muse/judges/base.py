"""The listening boundary every judge implements."""

from __future__ import annotations

from typing import Protocol

from ..types import MusicRequest, Track, Verdict


class MusicJudge(Protocol):
    name: str
    model: str

    def judge(self, track: Track, request: MusicRequest) -> Verdict:
        """Listen to the track and score how well it serves the request's theme."""
        ...
