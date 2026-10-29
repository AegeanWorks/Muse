"""Read-only discovery of scored artifacts under an output directory."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MAX_METADATA_BYTES = 2_000_000
SCHEMAS = (1, 2)


@dataclass(frozen=True)
class Artifact:
    folder: str
    metadata_path: Path
    audio_path: Path
    name: str
    prompt: str
    theme: str
    duration: float
    score: int | None
    verdict: str | None
    accepted: bool
    created_at: str
    provider: str
    model: str
    attempts: int
    audio_exists: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "folder": self.folder,
            "name": self.name,
            "prompt": self.prompt,
            "theme": self.theme,
            "duration_seconds": self.duration,
            "score": self.score,
            "verdict": self.verdict,
            "accepted": self.accepted,
            "created_at": self.created_at,
            "provider": self.provider,
            "model": self.model,
            "attempts": self.attempts,
            "audio": str(self.audio_path),
            "metadata": str(self.metadata_path),
            "audio_exists": self.audio_exists,
        }


def load_artifacts(
    output_dir: Path,
    accepted_only: bool = False,
    limit: int | None = None,
) -> tuple[list[Artifact], list[str]]:
    """Scan one output directory level and return scored artifacts plus warnings."""
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("limit must be a positive whole number")
    root = Path(output_dir)
    if not root.is_dir():
        return [], []
    try:
        paths = sorted(root.glob("*/muse.json"))
    except OSError as exc:
        return [], [f"{root}: could not scan the output directory: {exc}"]
    entries: list[Artifact] = []
    warnings: list[str] = []
    for metadata in paths:
        try:
            payload = _read_metadata(metadata)
        except (OSError, ValueError) as exc:
            warnings.append(f"{metadata}: {exc}")
            continue
        entry, reason = _entry(metadata, payload)
        if entry is None:
            warnings.append(f"{metadata}: {reason}")
            continue
        if accepted_only and not entry.accepted:
            continue
        entries.append(entry)
    entries.sort(key=lambda entry: (entry.created_at, entry.folder), reverse=True)
    if limit is not None:
        entries = entries[:limit]
    return entries, warnings


def _read_metadata(path: Path) -> Mapping[str, Any]:
    # hygiene: allow binary read is capped at MAX_METADATA_BYTES + 1; UTF-8 is decoded below
    with path.open("rb") as handle:
        raw = handle.read(MAX_METADATA_BYTES + 1)
    if len(raw) > MAX_METADATA_BYTES:
        raise ValueError(f"metadata is above the {MAX_METADATA_BYTES} byte limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("metadata is not UTF-8 text") from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"metadata is not valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("metadata is not a JSON object")
    schema = payload.get("schema")
    if type(schema) is not int or schema not in SCHEMAS:
        raise ValueError(f"unsupported metadata schema {schema!r}")
    return payload


def _entry(metadata: Path, payload: Mapping[str, Any]) -> tuple[Artifact | None, str]:
    request = payload.get("request")
    track = payload.get("track")
    if not isinstance(request, Mapping) or not isinstance(track, Mapping):
        return None, "request or track is missing"
    file_name = track.get("file")
    if not isinstance(file_name, str) or not file_name or Path(file_name).name != file_name:
        return None, "track.file is not a plain file name"
    score: int | None = None
    verdict: str | None = None
    verdict_data = payload.get("verdict")
    if verdict_data is not None:
        if not isinstance(verdict_data, Mapping):
            return None, "verdict is not an object"
        raw_score = verdict_data.get("score")
        if isinstance(raw_score, bool) or not isinstance(raw_score, int) or not 0 <= raw_score <= 100:
            return None, "verdict score is not an integer between 0 and 100"
        score = raw_score
        raw_verdict = verdict_data.get("verdict")
        verdict = raw_verdict if isinstance(raw_verdict, str) else None
    duration = track.get("duration_seconds", request.get("duration", 0.0))
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration < 0
    ):
        duration = 0.0
    attempts = payload.get("attempts")
    takes = len(attempts) if isinstance(attempts, list) and attempts else 1
    folder = metadata.parent.name
    return (
        Artifact(
            folder=folder,
            metadata_path=metadata,
            audio_path=metadata.parent / file_name,
            name=_text(request.get("name")) or folder,
            prompt=_text(request.get("prompt")),
            theme=_text(request.get("theme")),
            duration=float(duration),
            score=score,
            verdict=verdict,
            accepted=payload.get("accepted") is True,
            created_at=_text(payload.get("created_at")),
            provider=_text(track.get("provider")),
            model=_text(track.get("model")),
            attempts=takes,
            audio_exists=(metadata.parent / file_name).is_file(),
        ),
        "",
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""
