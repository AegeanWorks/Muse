"""Artifact directories and crash-safe JSON metadata."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from .audio import slugify


def unique_directory(parent: Path, label: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    slug = slugify(label)
    candidate = parent / slug
    counter = 2
    while candidate.exists():
        candidate = parent / f"{slug}-{counter}"
        counter += 1
    candidate.mkdir(parents=True)
    return candidate


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp_{uuid.uuid4().hex[:8]}")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
