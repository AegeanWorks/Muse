"""Read-only local configuration checks for the doctor command."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import MuseConfig
from .errors import MuseError
from .judges.registry import judges
from .providers.registry import providers


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "ok": self.ok, "detail": self.detail}
        if not self.ok and self.fix:
            data["fix"] = self.fix
        return data


def run_checks(config: MuseConfig | None = None) -> list[Check]:
    try:
        settings = config or MuseConfig.from_env()
    except MuseError as exc:
        return [Check("configuration", False, exc.what, exc.fix)]
    checks = [
        _python_check(),
        _output_check(settings.output_dir),
        _provider_check(settings),
        _judge_check(settings),
    ]
    checks.extend(_key_checks(settings))
    return checks


def _python_check() -> Check:
    version = sys.version_info
    current = f"{version.major}.{version.minor}"
    return Check(
        "python",
        (version.major, version.minor) >= (3, 10),
        current,
        "use Python 3.10 or newer",
    )


def _output_check(output_dir: Path) -> Check:
    path = Path(output_dir)
    if path.exists():
        if not path.is_dir():
            return Check("output", False, f"{path} is not a directory", "choose a writable directory")
        writable = os.access(path, os.W_OK)
    else:
        parent = path
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        writable = parent.is_dir() and os.access(parent, os.W_OK)
    return Check(
        "output",
        writable,
        str(path),
        "choose a writable directory, for example with --out output",
    )


def _provider_check(settings: MuseConfig) -> Check:
    known = providers()
    return Check(
        "provider",
        settings.provider in known,
        settings.provider or "(empty)",
        f"use one of: {', '.join(sorted(known))}",
    )


def _judge_check(settings: MuseConfig) -> Check:
    known = judges()
    return Check(
        "judge",
        settings.judge in known,
        settings.judge or "(empty)",
        f"use one of: {', '.join(sorted(known))}",
    )


def _key_checks(settings: MuseConfig) -> list[Check]:
    checks: list[Check] = []
    if settings.provider == "replicate":
        try:
            settings.replicate_token()
        except MuseError as exc:
            checks.append(Check("REPLICATE_API_TOKEN", False, exc.what, exc.fix))
        else:
            checks.append(Check("REPLICATE_API_TOKEN", True, "set"))
    if settings.judge == "gemini":
        try:
            settings.gemini_key()
        except MuseError as exc:
            checks.append(Check("GEMINI_API_KEY", False, exc.what, exc.fix))
        else:
            checks.append(Check("GEMINI_API_KEY", True, "set"))
    return checks
