"""Artifact directories and crash-safe JSON metadata."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

from .audio import slugify
from .errors import MuseError


def unique_directory(parent: Path, label: str) -> Path:
    parent = Path(parent)
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MuseError(
            f"could not create the output folder: {parent}",
            str(exc),
            "check that the path is a writable directory and retry",
        ) from exc
    slug = slugify(label)
    candidate = parent / slug
    counter = 2
    while True:
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            candidate = parent / f"{slug}-{counter}"
            counter += 1
        except OSError as exc:
            raise MuseError(
                f"could not create the track folder: {candidate}",
                str(exc),
                "check that the output folder is writable and retry",
            ) from exc


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MuseError(
            f"could not create the artifact folder: {path.parent}",
            str(exc),
            "check that the path is writable and the disk has free space, then retry",
        ) from exc
    temporary = path.with_name(f"{path.name}.tmp_{uuid.uuid4().hex[:8]}")
    try:
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise MuseError(
                f"could not write the artifact file: {path}",
                str(exc),
                "check that the disk has free space and the folder is writable, then retry",
            ) from exc
        try:
            _fsync_directory(path.parent)
        except OSError as exc:
            raise MuseError(
                f"could not flush the artifact folder: {path.parent}",
                str(exc),
                "retry; if it persists, move the output to a local disk",
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    if sys.platform == "win32":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
