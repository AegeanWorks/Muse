"""Re-score existing artifacts and keep every previous verdict in history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import write_json_atomic
from .catalog import Artifact, load_artifact
from .config import MuseConfig
from .errors import ConfigurationError, MuseError
from .judges.base import MusicJudge
from .judges.registry import build_judge
from .types import MusicRequest, Track, Verdict


@dataclass(frozen=True)
class RejudgeResult:
    entry: Artifact
    old_score: int | None
    verdict: Verdict
    history_count: int


def rejudge_artifacts(
    metadata_paths: Sequence[Path],
    settings: MuseConfig,
    judge: MusicJudge | None = None,
) -> list[RejudgeResult]:
    if settings.judge == "none" and judge is None:
        raise ConfigurationError(
            "rejudge needs a listening judge",
            "'none' disables listening, so there is no new verdict to record",
            "omit --judge none, or pass --judge gemini or --judge mock",
        )
    listener = judge or build_judge(settings.judge, settings)
    prepared: list[tuple[Artifact, Mapping[str, Any], MusicRequest, Track]] = []
    for metadata in metadata_paths:
        try:
            entry, payload = load_artifact(metadata)
        except (OSError, ValueError) as exc:
            raise MuseError(
                f"could not read artifact metadata: {metadata}",
                str(exc),
                "repair or remove the artifact folder, then retry",
            ) from exc
        if not entry.audio_exists:
            raise MuseError(
                f"audio file is missing for {entry.name}",
                str(entry.audio_path),
                "restore the audio file, or generate the track again",
            )
        request = _request(payload, entry)
        prepared.append((entry, payload, request, _track(payload, entry, request)))
    verdicts = [listener.judge(track, request) for _, _, request, track in prepared]
    now = datetime.now(timezone.utc).isoformat()
    results: list[RejudgeResult] = []
    for (entry, payload, request, _), verdict in zip(prepared, verdicts):
        history = payload.get("history")
        history = list(history) if isinstance(history, list) else []
        old_settings = payload.get("settings")
        old_settings = dict(old_settings) if isinstance(old_settings, Mapping) else {}
        history.append(
            {
                "verdict": payload.get("verdict"),
                "accepted": payload.get("accepted"),
                "judge_error": payload.get("judge_error"),
                "settings": old_settings,
                "recorded_at": now,
            }
        )
        new_settings = dict(old_settings)
        new_settings["judge"] = verdict.judge
        new_settings["judge_model"] = verdict.model
        updated = dict(payload)
        updated["schema"] = 3
        updated["verdict"] = _verdict_payload(verdict)
        updated["accepted"] = verdict.accepted
        updated["judge_error"] = None
        updated["settings"] = new_settings
        updated["history"] = history
        updated["rejudged_at"] = now
        write_json_atomic(entry.metadata_path, updated)
        results.append(
            RejudgeResult(
                entry=entry,
                old_score=entry.score,
                verdict=verdict,
                history_count=len(history),
            )
        )
    return results


def _request(payload: Mapping[str, Any], entry: Artifact) -> MusicRequest:
    data = payload.get("request")
    if not isinstance(data, Mapping):
        raise MuseError(
            f"artifact request is missing for {entry.name}",
            "muse.json has no request object",
            "repair or remove the artifact folder, then retry",
        )
    try:
        return MusicRequest(
            prompt=data.get("prompt", ""),
            theme=data.get("theme", ""),
            duration=data.get("duration", entry.duration or 30.0),
            name=data.get("name", ""),
        )
    except (TypeError, ValueError) as exc:
        raise MuseError(
            f"artifact request is invalid for {entry.name}",
            str(exc),
            "repair the request fields in muse.json, then retry",
        ) from exc


def _track(payload: Mapping[str, Any], entry: Artifact, request: MusicRequest) -> Track:
    data = payload.get("track")
    source = data.get("source_url") if isinstance(data, Mapping) else None
    return Track(
        path=entry.audio_path,
        provider=entry.provider or "file",
        model=entry.model or "unknown",
        duration_seconds=entry.duration,
        prompt=request.prompt,
        theme=request.theme,
        source_url=source if isinstance(source, str) else None,
    )


def _verdict_payload(verdict: Verdict) -> Mapping[str, Any]:
    return {
        "score": verdict.score,
        "verdict": verdict.verdict,
        "summary": verdict.summary,
        "strengths": list(verdict.strengths),
        "issues": list(verdict.issues),
        "suggestions": list(verdict.suggestions),
        "judge": verdict.judge,
        "model": verdict.model,
        "threshold": verdict.threshold,
    }
