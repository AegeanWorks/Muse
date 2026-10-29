"""Orchestration: render a prompt, listen to it, and persist the evidence."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .artifacts import unique_directory, write_json_atomic
from .config import MuseConfig
from .errors import ConfigurationError, MuseError
from .judges.base import MusicJudge
from .judges.registry import build_judge
from .providers.base import MusicProvider
from .providers.registry import build_provider
from .types import MAX_ATTEMPTS, Attempt, CompositionResult, MusicRequest, Track, Verdict

METADATA_NAME = "muse.json"
PROMPT_LIMIT = 1000


def compose(
    request: MusicRequest,
    config: MuseConfig | None = None,
    provider: MusicProvider | None = None,
    judge: MusicJudge | None = None,
    require_judge: bool = True,
    max_attempts: int = 1,
) -> CompositionResult:
    _validate_attempts(max_attempts)
    settings = config or MuseConfig.from_env()
    if max_attempts > 1 and judge is None and settings.judge == "none":
        raise ConfigurationError(
            "attempts need a listening judge",
            f"--attempts {max_attempts} can only retry when a judge scores each take",
            "omit --attempts, or pass --judge gemini or --judge mock",
        )
    engine = provider or build_provider(settings.provider, settings)
    attempts: list[Attempt] = []
    prompt = request.prompt
    for number in range(1, max_attempts + 1):
        current = replace(request, prompt=prompt)
        attempt = _render_and_judge(
            current,
            settings,
            engine,
            judge,
            require_judge,
            number,
            max_attempts,
        )
        attempts.append(attempt)
        if attempt.accepted or attempt.verdict is None or number == max_attempts:
            break
        revised = revise_prompt(current.prompt, attempt.verdict)
        if revised == current.prompt:
            break
        prompt = revised
    best = max(attempts, key=lambda item: -1 if item.score is None else item.score)
    if len(attempts) > 1:
        _record_history(best, attempts, settings)
    return CompositionResult(
        track=best.track,
        verdict=best.verdict,
        metadata_path=best.metadata_path,
        judge_error=best.judge_error,
        attempts=tuple(attempts),
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


def revise_prompt(prompt: str, verdict: Verdict) -> str:
    """Append the judge's actionable suggestions without repeating or overlong text."""
    base = prompt.strip()
    additions: list[str] = []
    current = base.lower()
    for raw in verdict.suggestions:
        suggestion = " ".join(str(raw).split()).strip(" .;:")
        if not suggestion or suggestion.lower() in current:
            continue
        candidate = f"{base}; {'; '.join([*additions, suggestion])}"
        if len(candidate) > PROMPT_LIMIT:
            continue
        additions.append(suggestion)
        current = candidate.lower()
    return f"{base}; {'; '.join(additions)}" if additions else base


def _validate_attempts(max_attempts: int) -> None:
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
        raise ValueError("max_attempts must be a whole number")
    if not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise ValueError(f"max_attempts must be between 1 and {MAX_ATTEMPTS}")


def _render_and_judge(
    request: MusicRequest,
    settings: MuseConfig,
    engine: MusicProvider,
    judge: MusicJudge | None,
    require_judge: bool,
    number: int,
    planned: int,
) -> Attempt:
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
        write_json_atomic(
            metadata,
            _metadata(request, track, None, exc.what, settings, number, planned),
        )
        raise
    write_json_atomic(
        metadata,
        _metadata(request, track, verdict, judge_error, settings, number, planned),
    )
    return Attempt(
        number=number,
        prompt=request.prompt,
        track=track,
        verdict=verdict,
        metadata_path=metadata,
        judge_error=judge_error,
    )


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
    number: int,
    planned: int,
) -> Mapping[str, Any]:
    return {
        "schema": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "attempt": {
            "number": number,
            "planned": planned,
            "prompt": request.prompt,
        },
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


def _record_history(best: Attempt, attempts: list[Attempt], settings: MuseConfig) -> None:
    payload = json.loads(best.metadata_path.read_text(encoding="utf-8"))
    payload["selected_attempt"] = best.number
    payload["attempts"] = [_attempt_summary(item, settings) for item in attempts]
    write_json_atomic(best.metadata_path, payload)


def _attempt_summary(attempt: Attempt, settings: MuseConfig) -> Mapping[str, Any]:
    return {
        "number": attempt.number,
        "prompt": attempt.prompt,
        "audio": _display_path(attempt.track.path, settings.output_dir),
        "metadata": _display_path(attempt.metadata_path, settings.output_dir),
        "score": attempt.score,
        "verdict": None if attempt.verdict is None else attempt.verdict.verdict,
        "accepted": attempt.accepted,
    }


def _display_path(path: Path, root: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        if candidate.parent.name:
            return f"{candidate.parent.name}/{candidate.name}"
        return candidate.name
