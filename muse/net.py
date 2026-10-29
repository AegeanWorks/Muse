"""Minimal JSON and download HTTP client with retry and timeouts."""

from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from .errors import MuseError

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MuseError(
                "the service returned a non-JSON response",
                f"body starts with {self.body[:120]!r}",
                "retry once; if it persists, check the service status page",
            ) from exc


class HttpClient:
    def __init__(
        self,
        timeout: float = 120.0,
        retries: int = 3,
        backoff: float = 1.5,
        sleep: Callable[[float], None] = time.sleep,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._sleep = sleep
        self._opener = opener

    def json(
        self,
        method: str,
        url: str,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        response = self._send(method, url, payload, headers, retries=True)
        return response.json()

    def download(self, url: str, destination: Path, headers: Mapping[str, str] | None = None) -> None:
        scheme = urlparse(url).scheme.lower()
        if scheme not in {"http", "https"}:
            raise MuseError(
                "the download URL must use http or https",
                f"got scheme {scheme or 'missing'!r}",
                "use the https URL returned by the provider",
            )
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise MuseError(
                f"could not create the download folder: {destination.parent}",
                str(exc),
                "check that the output path is writable and is not a file",
            ) from exc
        temporary = destination.with_name(f"{destination.name}.part_{uuid.uuid4().hex[:8]}")
        request = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
        detail = "no response"
        for attempt in range(self.retries + 1):
            retryable = True
            try:
                self._stream(request, temporary)
                if temporary.stat().st_size == 0:
                    detail = "the service returned an empty file"
                else:
                    os.replace(temporary, destination)
                    return
            except urllib.error.HTTPError as exc:
                detail = f"HTTP {exc.code}: {_excerpt(exc.read())}"
                retryable = exc.code in RETRY_STATUS
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
                detail = f"{type(exc).__name__}: {exc}"
            finally:
                temporary.unlink(missing_ok=True)
            if attempt >= self.retries or not retryable:
                break
            self._sleep(self.backoff * (attempt + 1))
        raise MuseError(
            "could not download the generated audio",
            detail,
            "retry the command; if it persists, check the Replicate output URL",
        )

    def _stream(self, request: urllib.request.Request, path: Path) -> None:
        total = 0
        with self._opener(request, timeout=self.timeout) as response:
            # hygiene: allow binary audio stream, encoding does not apply
            with path.open("wb") as handle:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise MuseError(
                            "the downloaded audio is too large",
                            f"exceeded the {MAX_DOWNLOAD_BYTES} byte download limit",
                            "check the provider output URL, or render a shorter track",
                        )
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())

    def _send(
        self,
        method: str,
        url: str,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        retries: bool = False,
    ) -> HttpResponse:
        try:
            body = None if payload is None else json.dumps(payload).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise MuseError(
                "the request could not be encoded as JSON",
                str(exc),
                "pass only JSON-compatible values in the request payload",
            ) from exc
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        attempts = self.retries if retries else 0
        for attempt in range(attempts + 1):
            try:
                response = self._once(method, url, body, request_headers)
            except urllib.error.HTTPError as exc:
                response = HttpResponse(exc.code, dict(exc.headers or {}), exc.read())
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
                if attempt >= attempts:
                    raise MuseError(
                        "the service could not be reached",
                        f"{type(exc).__name__}: {exc}",
                        "check the network connection and retry",
                    ) from exc
                self._sleep(self.backoff * (attempt + 1))
                continue
            if response.status < 400:
                return response
            if response.status in RETRY_STATUS and attempt < attempts:
                self._sleep(self.backoff * (attempt + 1))
                continue
            raise MuseError(
                f"the service returned HTTP {response.status}",
                _excerpt(response.body),
                "retry once; if it persists, verify the API key and model name",
            )
        raise MuseError("request retries exhausted", "no response was accepted", "retry later")

    def _once(self, method: str, url: str, body: bytes | None, headers: Mapping[str, str]) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return HttpResponse(response.status, dict(response.headers), response.read())


def _excerpt(body: bytes, limit: int = 300) -> str:
    text = body.decode("utf-8", errors="replace").strip()
    return text[:limit] or "empty response body"
