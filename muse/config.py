"""Configuration resolved from explicit values, environment variables and defaults."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping

from .errors import ConfigurationError

DEFAULT_MUSIC_MODEL = "stability-ai/stable-audio-2.5"
DEFAULT_JUDGE_MODEL = "gemini-2.5-flash"


@dataclass(frozen=True)
class MuseConfig:
    output_dir: Path = Path("output")
    provider: str = "replicate"
    judge: str = "gemini"
    music_model: str = DEFAULT_MUSIC_MODEL
    replicate_version: str | None = None
    judge_model: str = DEFAULT_JUDGE_MODEL
    min_score: int = 60
    http_timeout: float = 120.0
    poll_timeout: float = 600.0
    env: Mapping[str, str] = field(default_factory=lambda: os.environ, repr=False, compare=False)

    def __post_init__(self) -> None:
        if isinstance(self.min_score, bool) or not isinstance(self.min_score, int):
            raise ConfigurationError(
                "MUSE_MIN_SCORE must be a whole number",
                f"got {self.min_score!r}",
                "set --min-score or MUSE_MIN_SCORE to an integer between 0 and 100",
            )
        if not 0 <= self.min_score <= 100:
            raise ConfigurationError(
                f"acceptance threshold {self.min_score} is outside 0-100",
                "a verdict score is always 0-100, so no track could satisfy this threshold",
                "set --min-score or MUSE_MIN_SCORE to an integer between 0 and 100",
            )
        for name, value in (("MUSE_HTTP_TIMEOUT", self.http_timeout), ("MUSE_POLL_TIMEOUT", self.poll_timeout)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ConfigurationError(
                    f"{name} must be a positive number",
                    f"got {value!r}",
                    f"set {name} to a positive number of seconds such as 120",
                )
        try:
            output_dir = Path(self.output_dir)
        except TypeError as exc:
            raise ConfigurationError(
                "MUSE_OUTPUT_DIR must be a filesystem path",
                f"got {self.output_dir!r}",
                "set MUSE_OUTPUT_DIR to a directory such as output",
            ) from exc
        object.__setattr__(self, "output_dir", output_dir)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "MuseConfig":
        source = os.environ if env is None else env
        return cls(
            env=source,
            output_dir=Path(source.get("MUSE_OUTPUT_DIR") or "output"),
            provider=source.get("MUSE_PROVIDER") or "replicate",
            judge=source.get("MUSE_JUDGE") or "gemini",
            music_model=source.get("MUSE_MUSIC_MODEL") or DEFAULT_MUSIC_MODEL,
            replicate_version=source.get("MUSE_REPLICATE_VERSION") or None,
            judge_model=source.get("MUSE_JUDGE_MODEL") or DEFAULT_JUDGE_MODEL,
            min_score=_int(source.get("MUSE_MIN_SCORE"), 60, "MUSE_MIN_SCORE"),
            http_timeout=_float(source.get("MUSE_HTTP_TIMEOUT"), 120.0, "MUSE_HTTP_TIMEOUT"),
            poll_timeout=_float(source.get("MUSE_POLL_TIMEOUT"), 600.0, "MUSE_POLL_TIMEOUT"),
        )

    def with_overrides(self, **changes: object) -> "MuseConfig":
        return replace(self, **{key: value for key, value in changes.items() if value is not None})

    def replicate_token(self) -> str:
        token = self.env.get("REPLICATE_API_TOKEN", "").strip()
        if not token:
            raise ConfigurationError(
                "REPLICATE_API_TOKEN is not set",
                "the Replicate provider needs it to generate music",
                "create a token at https://replicate.com/account/api-tokens and set REPLICATE_API_TOKEN",
            )
        return token

    def gemini_key(self) -> str:
        key = self.env.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise ConfigurationError(
                "GEMINI_API_KEY is not set",
                "the Gemini judge needs it to listen to the rendered track",
                "create a key at https://aistudio.google.com/apikey and set GEMINI_API_KEY",
            )
        return key


def _int(raw: str | None, default: int, name: str) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(
            f"{name} is not a whole number",
            f"got {raw!r}",
            f"set {name} to an integer such as 60",
        ) from exc


def _float(raw: str | None, default: float, name: str) -> float:
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(
            f"{name} is not a number",
            f"got {raw!r}",
            f"set {name} to a number such as 120",
        ) from exc
