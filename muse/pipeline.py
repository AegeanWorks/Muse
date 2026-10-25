"""Orchestration: render a prompt, listen to it, and persist the evidence."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .artifacts import unique_directory, write_json_atomic
from .config import MuseConfig
from .errors import MuseError
from .judges.base import MusicJudge
from .judges.registry import build_judge
from .providers.base import MusicProvider
from .providers.registry import build_provider
from .types import CompositionResult, MusicRequest, Track, Verdict

METADATA_NAME = "muse.json"


def compose(
    request: MusicRequest,
    config: MuseConfig | None = None,
    provider: MusicProvider | None = None,
    judge: MusicJudge | None = None,
    require_judge: bool = True,
) -> CompositionResult:
    settings = config or MuseConfig.from_env()
    engine = provider or build_provider(settings.provider, settings)
    destination = unique_directory(settings.output_dir, request.label)
    try:
        track = engine.generate(request, destination)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    metadata = destination / METADATA_NAME
    try:
        verdict, judge_error = _listen(track, request, settings, judge, require_judge)
    except MuseError as exc:
        write_json_atomic(metadata, _metadata(request, track, None, exc.what, settings))
        raise
    write_json_atomic(metadata, _metadata(request, track, verdict, judge_error, settings))
    return CompositionResult(
        track=track,
        verdict=verdict,
        metadata_path=metadata,
        judge_error=judge_error,
    )


def judge_track(
    track: Track,
    request: MusicRequest,
    config: MuseConfig | None = None,
    judge: MusicJudge | None = None,
) -> Verdict:
    settings = config or MuseConfig.from_env()
    listener = judge or build_judge(settings.judge, settings)
    return listener.judge(track, request)


def _listen(
    track: Track,
    request: MusicRequest,
    settings: MuseConfig,
    judge: MusicJudge | None,
    require_judge: bool,
) -> tuple[Verdict | None, str | None]:
    if judge is None and settings.judge == "none":
        return None, None
    listener = judge or build_judge(settings.judge, settings)
    try:
        return listener.judge(track, request), None
    except MuseError as exc:
        if require_judge:
            raise
        return None, exc.what


def _metadata(
    request: MusicRequest,
    track: Track,
    verdict: Verdict | None,
    judge_error: str | None,
    settings: MuseConfig,
) -> Mapping[str, Any]:
    return {
        "schema": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request": {
            "prompt": request.prompt,
            "theme": request.theme,
            "duration": request.duration,
            "name": request.name,
        },
        "track": {
            "file": Path(track.path).name,
            "provider": track.provider,
            "model": track.model,
            "duration_seconds": track.duration_seconds,
            "source_url": track.source_url,
        },
        "verdict": None
        if verdict is None
        else {
            "score": verdict.score,
            "verdict": verdict.verdict,
            "summary": verdict.summary,
            "strengths": list(verdict.strengths),
            "issues": list(verdict.issues),
            "suggestions": list(verdict.suggestions),
            "judge": verdict.judge,
            "model": verdict.model,
            "threshold": verdict.threshold,
        },
        "accepted": verdict is not None and verdict.accepted,
        "judge_error": judge_error,
        "settings": {
            "provider": settings.provider,
            "music_model": settings.music_model,
            "judge": settings.judge,
            "judge_model": settings.judge_model,
        },
    }
