"""Crash-safe progress state for resumable batch runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import write_json_atomic
from .errors import ConfigurationError, MuseError
from .types import MusicRequest

STATE_SCHEMA = 1
MAX_STATE_BYTES = 8_000_000
STATUSES = ("accepted", "rejected", "failed")


def manifest_fingerprint(requests: Sequence[MusicRequest]) -> str:
    """Hash the validated requests so a changed manifest cannot reuse old progress."""
    canonical = [
        {
            "prompt": request.prompt,
            "theme": request.theme,
            "duration": request.duration,
            "name": request.name,
        }
        for request in requests
    ]
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def state_path(output_dir: Path, fingerprint: str) -> Path:
    return Path(output_dir) / f".muse-batch-{fingerprint[:16]}.json"


def load_state(path: Path, fingerprint: str) -> dict[int, dict[str, Any]]:
    """Load a batch state file, keyed by 1-based track index."""
    source = Path(path)
    if not source.is_file():
        raise ConfigurationError(
            "no batch state to resume",
            f"{source} does not exist",
            "run the batch without --resume to start a new run",
        )
    try:
        # hygiene: allow binary read is capped at MAX_STATE_BYTES + 1; UTF-8 is decoded below
        with source.open("rb") as handle:
            raw = handle.read(MAX_STATE_BYTES + 1)
    except OSError as exc:
        raise MuseError(
            f"the batch state could not be read: {source}",
            exc.strerror or "the file could not be read",
            "check permissions or run the batch without --resume",
        ) from exc
    if len(raw) > MAX_STATE_BYTES:
        raise ConfigurationError(
            f"the batch state is above the {MAX_STATE_BYTES} byte limit",
            f"got {len(raw)} bytes",
            "delete the state file or run without --resume",
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigurationError(
            "the batch state is not UTF-8 text",
            str(exc),
            "delete the state file or run without --resume",
        ) from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ConfigurationError(
            "the batch state is not valid JSON",
            str(exc),
            "delete the state file or run without --resume",
        ) from exc
    if not isinstance(payload, Mapping):
        raise ConfigurationError(
            "the batch state is not a JSON object",
            f"got {type(payload).__name__}",
            "delete the state file or run without --resume",
        )
    if type(payload.get("schema")) is not int or payload.get("schema") != STATE_SCHEMA:
        raise ConfigurationError(
            "the batch state has an unknown schema",
            f"schema was {payload.get('schema')!r}",
            "delete the state file or run without --resume",
        )
    if payload.get("manifest") != fingerprint:
        raise ConfigurationError(
            "the batch state belongs to a different manifest",
            "the current manifest fingerprint does not match the saved state",
            "restore the manifest, or run without --resume to start a new run",
        )
    tracks = payload.get("tracks")
    if not isinstance(tracks, list):
        raise ConfigurationError(
            "the batch state has no tracks array",
            f"tracks was {type(tracks).__name__}",
            "delete the state file or run without --resume",
        )
    entries: dict[int, dict[str, Any]] = {}
    for item in tracks:
        if not isinstance(item, Mapping):
            raise ConfigurationError(
                "the batch state has an invalid track entry",
                f"got {type(item).__name__}",
                "delete the state file or run without --resume",
            )
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 1:
            raise ConfigurationError(
                "the batch state has an invalid track index",
                f"index was {index!r}",
                "delete the state file or run without --resume",
            )
        status = item.get("status")
        if status not in STATUSES:
            raise ConfigurationError(
                f"the batch state has an unknown status for track {index}",
                f"status was {status!r}",
                "delete the state file or run without --resume",
            )
        if status == "failed" and not isinstance(item.get("error"), str):
            raise ConfigurationError(
                f"the batch state has no error for failed track {index}",
                "a failed entry must record why it failed",
                "delete the state file or run without --resume",
            )
        payload = item.get("payload")
        if status != "failed" and not isinstance(payload, Mapping):
            raise ConfigurationError(
                f"the batch state has no payload for track {index}",
                "an accepted or rejected entry must keep its result",
                "delete the state file or run without --resume",
            )
        if status != "failed" and payload.get("accepted") is not (status == "accepted"):
            raise ConfigurationError(
                f"the batch state is inconsistent for track {index}",
                f"status {status!r} does not match the stored acceptance flag",
                "delete the state file or run without --resume",
            )
        entries[index] = dict(item)
    return entries


def save_state(
    path: Path,
    fingerprint: str,
    entries: Sequence[Mapping[str, Any]],
) -> None:
    """Write progress atomically so a crash leaves the last completed track reusable."""
    ordered = sorted((dict(entry) for entry in entries), key=lambda entry: int(entry.get("index", 0)))
    write_json_atomic(
        Path(path),
        {
            "schema": STATE_SCHEMA,
            "manifest": fingerprint,
            "tracks": ordered,
        },
    )
