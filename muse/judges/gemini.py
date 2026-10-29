"""Gemini audio judge: listens to the rendered track and scores theme fit."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Mapping

from ..audio import mime_type
from ..config import MuseConfig
from ..errors import JudgeError, MuseError
from ..net import HttpClient
from ..types import VERDICTS, MusicRequest, Track, Verdict

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
# Gemini caps an inline request near 20 MB; base64 inflates raw bytes by about a third.
MAX_INLINE_BYTES = 14 * 1024 * 1024

SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "score": {"type": "INTEGER", "description": "0-100 fit score for the stated theme"},
        "verdict": {"type": "STRING", "enum": list(VERDICTS)},
        "summary": {"type": "STRING", "description": "One or two sentences on the overall fit"},
        "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
        "issues": {"type": "ARRAY", "items": {"type": "STRING"}},
        "suggestions": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["score", "verdict", "summary", "strengths", "issues", "suggestions"],
}


class GeminiJudge:
    name = "gemini"

    def __init__(self, config: MuseConfig, http: HttpClient | None = None) -> None:
        self.config = config
        self.model = config.judge_model
        self._http = http or HttpClient(timeout=config.http_timeout)
        self._key = config.gemini_key()

    def judge(self, track: Track, request: MusicRequest) -> Verdict:
        payload = self._payload(track, request)
        url = f"{BASE_URL}/{self.model}:generateContent"
        response = self._http.json("POST", url, payload, {"x-goog-api-key": self._key})
        data = self._parse(response)
        return Verdict(
            score=int(data["score"]),
            verdict=str(data["verdict"]),
            summary=str(data["summary"]).strip(),
            strengths=_strings(data.get("strengths")),
            issues=_strings(data.get("issues")),
            suggestions=_strings(data.get("suggestions")),
            judge=self.name,
            model=self.model,
            threshold=self.config.min_score,
        )

    def _payload(self, track: Track, request: MusicRequest) -> Mapping[str, Any]:
        path = Path(track.path)
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise MuseError(
                "the judge could not read the track",
                str(exc),
                "check that the rendered file still exists and is readable",
            ) from exc
        if size > MAX_INLINE_BYTES:
            raise JudgeError(
                "the track is too large for the Gemini audio judge",
                f"{size / 1048576:.1f} MB exceeds the {MAX_INLINE_BYTES / 1048576:g} MB inline limit",
                "render a shorter --duration",
            )
        try:
            audio = path.read_bytes()
        except OSError as exc:
            raise MuseError(
                "the judge could not read the track",
                str(exc),
                "check that the rendered file still exists and is readable",
            ) from exc
        if len(audio) > MAX_INLINE_BYTES:
            raise JudgeError(
                "the track is too large for the Gemini audio judge",
                f"{len(audio) / 1048576:.1f} MB exceeds the {MAX_INLINE_BYTES / 1048576:g} MB inline limit",
                "render a shorter --duration",
            )
        instruction = (
            "You are a music supervisor. Listen to the attached track and judge how well it "
            "serves the stated theme for a software project.\n"
            f"Theme: {request.intent}\n"
            f"Generation prompt: {request.prompt}\n"
            f"Requested length: {request.duration:g} seconds\n"
            "Score 0-100 where 80+ means the track clearly fits and is usable, 50-79 means "
            "partially usable, and below 50 means it misses the theme. Reply only with JSON "
            "matching the schema."
        )
        return {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": instruction},
                        {
                            "inlineData": {
                                "mimeType": mime_type(Path(track.path)),
                                "data": base64.b64encode(audio).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        }

    def _parse(self, response: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(response, Mapping):
            raise MuseError(
                "the judge returned a non-object response",
                f"got {type(response).__name__}",
                "retry; if it persists, check the Gemini service status",
            )
        candidates = response.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            feedback = response.get("promptFeedback") or {}
            raise MuseError(
                "the judge returned no candidate",
                f"prompt feedback: {str(feedback)[:200]}",
                "retry; if it persists, rephrase the theme",
            )
        candidate = candidates[0]
        if not isinstance(candidate, Mapping) or not isinstance(candidate.get("content"), Mapping):
            raise MuseError(
                "the judge returned a malformed candidate",
                f"candidate was {str(candidate)[:200]}",
                "retry; if it persists, use --judge mock or shorten the theme",
            )
        parts = candidate["content"].get("parts")
        if parts is None:
            parts = []
        if not isinstance(parts, list) or any(not isinstance(part, Mapping) for part in parts):
            raise MuseError(
                "the judge returned a malformed candidate",
                f"candidate parts were {str(parts)[:200]}",
                "retry; if it persists, use --judge mock or shorten the theme",
            )
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        if not text:
            reason = candidate.get("finishReason") or "unknown"
            raise MuseError(
                "the judge returned no verdict text",
                f"finish reason: {reason}",
                "retry; if it persists, use --judge mock or shorten the theme",
            )
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise MuseError(
                "the judge replied with invalid JSON",
                f"reply starts with {text[:160]!r}",
                "retry; if it persists, switch MUSE_JUDGE_MODEL",
            ) from exc
        _validate(data)
        return data


def _validate(data: object) -> None:
    if not isinstance(data, Mapping):
        raise MuseError("the judge reply is not an object", "expected JSON object", "retry the command")
    score = data.get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise MuseError(
            "the judge returned an invalid score",
            f"score was {score!r}; expected an integer 0-100",
            "retry; if it persists, switch MUSE_JUDGE_MODEL",
        )
    if data.get("verdict") not in VERDICTS:
        raise MuseError(
            "the judge returned an unknown verdict",
            f"verdict was {data.get('verdict')!r}",
            f"retry with a model that follows the schema ({', '.join(VERDICTS)})",
        )
    if not isinstance(data.get("summary"), str):
        raise MuseError("the judge returned no summary", "summary is missing", "retry the command")


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())
