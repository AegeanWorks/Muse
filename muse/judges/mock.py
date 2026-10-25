"""Deterministic offline judge used by tests and demos."""

from __future__ import annotations

import re

from ..config import MuseConfig
from ..types import VERDICT_FITS, VERDICT_MISS, VERDICT_PARTIAL, MusicRequest, Track, Verdict


class MockJudge:
    name = "mock"
    model = "mock-judge"

    def __init__(self, config: MuseConfig | None = None) -> None:
        self.config = config or MuseConfig()

    def judge(self, track: Track, request: MusicRequest) -> Verdict:
        shared = _words(request.theme) & _words(request.prompt)
        if shared:
            score, verdict = 88, VERDICT_FITS
            summary = f"Prompt and theme agree on: {', '.join(sorted(shared))}."
            strengths = (f"shared intent: {', '.join(sorted(shared))}",)
            issues: tuple[str, ...] = ()
        elif request.theme:
            score, verdict = 45, VERDICT_MISS
            summary = "The prompt and the theme share no concrete terms."
            strengths = ()
            issues = ("the theme is not reflected in the prompt",)
        else:
            score, verdict = 70, VERDICT_PARTIAL
            summary = "No theme was supplied, so only the prompt was considered."
            strengths = ("prompt is present",)
            issues = ("add a theme for a meaningful judgement",)
        suggestions = () if score >= self.config.min_score else ("add theme words to the prompt",)
        return Verdict(
            score=score,
            verdict=verdict,
            summary=summary,
            strengths=strengths,
            issues=issues,
            suggestions=suggestions,
            judge=self.name,
            model=self.model,
            threshold=self.config.min_score,
        )


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]{3,}", text.lower())}
