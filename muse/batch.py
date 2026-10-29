"""Batch manifest parsing: one JSON file, many themed tracks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigurationError, MuseError
from .types import MusicRequest

MAX_BATCH_TRACKS = 50
MAX_MANIFEST_BYTES = 1_000_000
TRACK_KEYS = {"prompt", "theme", "duration", "name"}


def load_manifest(path: Path) -> tuple[MusicRequest, ...]:
    """Read a JSON manifest and return one validated request per track."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise MuseError(
            f"batch manifest not found or unreadable: {source}",
            exc.strerror or "the file could not be read",
            "pass a readable JSON file, for example tracks.json",
        ) from exc
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ConfigurationError(
            f"the batch manifest is above the {MAX_MANIFEST_BYTES} byte limit",
            f"got {len(raw)} bytes",
            f"split the manifest into files below {MAX_MANIFEST_BYTES} bytes",
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigurationError(
            "the batch manifest is not UTF-8 text",
            str(exc),
            "save the manifest as UTF-8 and retry",
        ) from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ConfigurationError(
            "the batch manifest is not valid JSON",
            str(exc),
            "fix the JSON syntax and retry",
        ) from exc
    if not isinstance(payload, Mapping):
        raise ConfigurationError(
            "the batch manifest must be a JSON object",
            f"got {type(payload).__name__}",
            'wrap the track list in an object: {"tracks": [...]}',
        )
    unknown = sorted(set(payload) - {"tracks"})
    if unknown:
        raise ConfigurationError(
            f"the batch manifest has unknown keys: {', '.join(unknown)}",
            "only a tracks array is supported at the top level",
            'remove the extra keys and keep {"tracks": [...]}',
        )
    tracks = payload.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise ConfigurationError(
            "the batch manifest needs a non-empty tracks array",
            f"tracks was {type(tracks).__name__}",
            "add at least one track object with a prompt",
        )
    if len(tracks) > MAX_BATCH_TRACKS:
        raise ConfigurationError(
            f"the batch manifest has {len(tracks)} tracks, above the {MAX_BATCH_TRACKS} limit",
            "every track costs a provider prediction and a judge call",
            f"split the manifest into batches of at most {MAX_BATCH_TRACKS}",
        )
    return tuple(_request(track, index) for index, track in enumerate(tracks, 1))


def _request(track: object, index: int) -> MusicRequest:
    if not isinstance(track, Mapping):
        raise ConfigurationError(
            f"track {index} must be a JSON object",
            f"got {type(track).__name__}",
            'use {"prompt": "...", "theme": "...", "duration": 30}',
        )
    unknown = sorted(set(track) - TRACK_KEYS)
    if unknown:
        raise ConfigurationError(
            f"track {index} has unknown keys: {', '.join(unknown)}",
            f"allowed keys are {', '.join(sorted(TRACK_KEYS))}",
            "remove the extra keys or fix their spelling",
        )
    prompt = track.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ConfigurationError(
            f"track {index} needs a non-empty prompt",
            f"prompt was {prompt!r}",
            "give every track a prompt string",
        )
    theme = _text(track, "theme", index)
    name = _text(track, "name", index)
    duration = track.get("duration", 30.0)
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ConfigurationError(
            f"track {index} has an invalid duration",
            f"duration was {duration!r}; expected a number of seconds",
            "set duration to a number such as 30",
        )
    try:
        seconds = float(duration)
    except (OverflowError, ValueError) as exc:
        raise ConfigurationError(
            f"track {index} has an invalid duration",
            str(exc),
            "set duration to a number of seconds such as 30",
        ) from exc
    try:
        return MusicRequest(
            prompt=prompt,
            theme=theme,
            duration=seconds,
            name=name,
        )
    except ValueError as exc:
        raise ConfigurationError(
            f"track {index} is invalid",
            str(exc),
            "give every track a non-empty prompt and a duration between 0 and 190 seconds",
        ) from exc


def _text(track: Mapping[str, Any], key: str, index: int) -> str:
    value = track.get(key, "")
    if not isinstance(value, str):
        raise ConfigurationError(
            f"track {index} has an invalid {key}",
            f"{key} was {value!r}; expected a string",
            f"set {key} to a string, or remove it",
        )
    return value
