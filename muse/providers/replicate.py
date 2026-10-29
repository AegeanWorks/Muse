"""Music generation through Replicate-hosted models."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from ..audio import wav_duration
from ..config import MuseConfig
from ..errors import ConfigurationError, GenerationError
from ..net import HttpClient
from ..types import MusicRequest, Track

BASE_URL = "https://api.replicate.com/v1"
FINISHED = frozenset({"succeeded", "failed", "canceled"})


class ReplicateMusicProvider:
    name = "replicate"

    def __init__(
        self,
        config: MuseConfig,
        http: HttpClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = 2.0,
    ) -> None:
        if (
            isinstance(poll_interval, bool)
            or not isinstance(poll_interval, (int, float))
            or not math.isfinite(poll_interval)
            or poll_interval <= 0
        ):
            raise ConfigurationError(
                "the poll interval must be a positive number",
                f"got {poll_interval!r}",
                "pass a positive number of seconds such as 2",
            )
        self.config = config
        self.model = config.music_model
        self._http = http or HttpClient(timeout=config.http_timeout)
        self._sleep = sleep
        self._poll_interval = poll_interval
        self._headers = {
            "Authorization": f"Bearer {config.replicate_token()}",
            "User-Agent": "muse",
        }

    def generate(self, request: MusicRequest, destination: Path) -> Track:
        payload = self._create(request)
        final = self._wait(payload)
        url = self._output_url(final)
        suffix = Path(urlparse(url).path).suffix.lower()
        extension = suffix if suffix in {".wav", ".mp3"} else ".wav"
        path = destination / f"track{extension}"
        self._http.download(url, path)
        duration = wav_duration(path) or float(request.duration)
        return Track(
            path=path,
            provider=self.name,
            model=self.model,
            duration_seconds=duration,
            prompt=request.prompt,
            theme=request.theme,
            source_url=url,
        )

    def _create(self, request: MusicRequest) -> Mapping[str, Any]:
        payload = {
            **dict(request.extra),
            "prompt": request.prompt,
            "duration": max(1, int(round(float(request.duration)))),
        }
        if self.config.replicate_version:
            body = {"version": self.config.replicate_version, "input": payload}
            endpoint = f"{BASE_URL}/predictions"
        else:
            body = {"input": payload}
            endpoint = f"{BASE_URL}/models/{self.model}/predictions"
        result = self._http.json("POST", endpoint, body, self._headers)
        urls = result.get("urls") if isinstance(result, Mapping) else None
        if not isinstance(urls, Mapping) or not isinstance(urls.get("get"), str):
            raise GenerationError(
                "Replicate did not return a prediction handle",
                f"response was {str(result)[:200]}",
                "verify MUSE_MUSIC_MODEL names an official Replicate model, or set MUSE_REPLICATE_VERSION",
            )
        return result

    def _wait(self, created: Mapping[str, Any]) -> Mapping[str, Any]:
        poll_url = created["urls"]["get"]
        deadline_attempts = max(1, int(self.config.poll_timeout / self._poll_interval) + 1)
        current: Mapping[str, Any] = created
        for _ in range(deadline_attempts):
            if not isinstance(current, Mapping):
                raise GenerationError(
                    "Replicate returned a malformed prediction",
                    f"expected an object, got {type(current).__name__}",
                    "retry; if it persists, check the Replicate service status",
                )
            status = current.get("status")
            if status in FINISHED:
                break
            self._sleep(self._poll_interval)
            current = self._http.json("GET", poll_url, None, self._headers)
        else:
            if not isinstance(current, Mapping):
                raise GenerationError(
                    "Replicate returned a malformed prediction",
                    f"expected an object, got {type(current).__name__}",
                    "retry; if it persists, check the Replicate service status",
                )
            if current.get("status") not in FINISHED:
                raise GenerationError(
                    "music generation timed out",
                    f"Replicate did not finish within {self.config.poll_timeout:g}s",
                    "retry with a shorter --duration or raise MUSE_POLL_TIMEOUT",
                )
        if current.get("status") != "succeeded":
            detail = current.get("error") or current.get("status") or "unknown state"
            raise GenerationError(
                "music generation failed",
                f"Replicate reported {detail}",
                "rephrase the prompt, lower --duration, or check the model on Replicate",
            )
        return current

    def _output_url(self, final: Mapping[str, Any]) -> str:
        output = final.get("output")
        if isinstance(output, list):
            output = output[0] if output else None
        if not isinstance(output, str) or not output:
            raise GenerationError(
                "Replicate returned no audio file",
                f"output was {str(output)[:200]}",
                "retry; if it persists, pick another MUSE_MUSIC_MODEL",
            )
        return output
