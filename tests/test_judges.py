import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from muse.audio import write_tone
from muse.config import MuseConfig
from muse.errors import ConfigurationError, JudgeError, MuseError
from muse.judges.gemini import GeminiJudge
from muse.judges.mock import MockJudge
from muse.judges.registry import build_judge
from muse.types import VERDICT_FITS, VERDICT_MISS, MusicRequest, Track


class FakeHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def json(self, method, url, payload=None, headers=None):
        self.calls.append({"method": method, "url": url, "payload": payload, "headers": headers})
        return self.response


def reply(**changes):
    data = {
        "score": 84,
        "verdict": "fits",
        "summary": "Brooding drones match the cave.",
        "strengths": ["low register", "slow pulse"],
        "issues": [],
        "suggestions": [],
    }
    data.update(changes)
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}


class GeminiTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "track.wav"
        write_tone(self.path, 0.2)
        self.track = Track(self.path, "mock", "mock-tone", 0.2, "dark cave", "cave")
        self.request = MusicRequest("dark cave drones", theme="cave", duration=30)
        self.config = MuseConfig(env={"GEMINI_API_KEY": "judge-key"}, min_score=80)

    def test_sends_audio_and_returns_verdict(self):
        http = FakeHttp(reply())
        verdict = GeminiJudge(self.config, http=http).judge(self.track, self.request)
        self.assertEqual(verdict.score, 84)
        self.assertTrue(verdict.accepted)
        self.assertEqual(verdict.strengths, ("low register", "slow pulse"))
        call = http.calls[0]
        self.assertEqual(call["headers"]["x-goog-api-key"], "judge-key")
        self.assertNotIn("judge-key", call["url"])
        parts = call["payload"]["contents"][0]["parts"]
        self.assertIn("cave", parts[0]["text"])
        self.assertEqual(parts[1]["inlineData"]["mimeType"], "audio/wav")
        decoded = base64.b64decode(parts[1]["inlineData"]["data"])
        self.assertEqual(decoded, self.path.read_bytes())
        self.assertEqual(call["payload"]["generationConfig"]["responseMimeType"], "application/json")

    def test_invalid_score_is_rejected(self):
        with self.assertRaises(MuseError) as caught:
            GeminiJudge(self.config, http=FakeHttp(reply(score=150))).judge(self.track, self.request)
        self.assertIn("invalid score", caught.exception.what)

    def test_boolean_score_is_rejected(self):
        with self.assertRaises(MuseError) as caught:
            GeminiJudge(self.config, http=FakeHttp(reply(score=True))).judge(self.track, self.request)
        self.assertIn("invalid score", caught.exception.what)

    def test_unknown_verdict_is_rejected(self):
        with self.assertRaises(MuseError):
            GeminiJudge(self.config, http=FakeHttp(reply(verdict="great"))).judge(self.track, self.request)

    def test_missing_candidate_is_rejected(self):
        with self.assertRaises(MuseError) as caught:
            GeminiJudge(self.config, http=FakeHttp({"candidates": []})).judge(self.track, self.request)
        self.assertIn("no candidate", caught.exception.what)

    def test_non_object_reply_is_rejected(self):
        with self.assertRaises(MuseError) as caught:
            GeminiJudge(self.config, http=FakeHttp([])).judge(self.track, self.request)
        self.assertIn("non-object", caught.exception.what)

    def test_malformed_candidate_is_rejected(self):
        with self.assertRaises(MuseError) as caught:
            GeminiJudge(
                self.config,
                http=FakeHttp({"candidates": [{"content": []}]}),
            ).judge(self.track, self.request)
        self.assertIn("malformed", caught.exception.what)

    def test_oversized_audio_is_rejected_before_upload(self):
        with patch("muse.judges.gemini.MAX_INLINE_BYTES", 10):
            with self.assertRaises(JudgeError) as caught:
                GeminiJudge(self.config, http=FakeHttp(reply())).judge(self.track, self.request)
        self.assertIn("too large", caught.exception.what)

    def test_oversized_audio_is_rejected_before_reading(self):
        with patch("muse.judges.gemini.MAX_INLINE_BYTES", 10):
            with patch.object(Path, "read_bytes", side_effect=AssertionError("read too early")):
                with self.assertRaises(JudgeError):
                    GeminiJudge(self.config, http=FakeHttp(reply())).judge(self.track, self.request)

    def test_unreadable_track_is_explained(self):
        folder = Path(self.path).parent / "not-a-file"
        folder.mkdir()
        track = Track(folder, "file", "local", 1.0, "x", "x")
        with self.assertRaises(MuseError) as caught:
            GeminiJudge(self.config, http=FakeHttp(reply())).judge(track, self.request)
        self.assertIn("could not read", caught.exception.what)

    def test_empty_verdict_text_is_rejected(self):
        with self.assertRaises(MuseError) as caught:
            GeminiJudge(self.config, http=FakeHttp({"candidates": [{"content": {"parts": []}}]})).judge(
                self.track, self.request
            )
        self.assertIn("no verdict text", caught.exception.what)


class MockJudgeTests(unittest.TestCase):
    def setUp(self):
        self.judge = MockJudge(MuseConfig(env={}, min_score=60))

    def track(self):
        return Track(Path("x.wav"), "mock", "m", 1.0, "", "")

    def test_shared_terms_fit(self):
        verdict = self.judge.judge(self.track(), MusicRequest("cave drones", theme="cave level"))
        self.assertEqual(verdict.verdict, VERDICT_FITS)
        self.assertTrue(verdict.accepted)

    def test_disjoint_terms_miss(self):
        verdict = self.judge.judge(self.track(), MusicRequest("sunny beach", theme="cave level"))
        self.assertEqual(verdict.verdict, VERDICT_MISS)
        self.assertFalse(verdict.accepted)

    def test_disjoint_terms_suggest_the_theme_words(self):
        verdict = self.judge.judge(self.track(), MusicRequest("sunny beach", theme="cave level"))
        suggestion = " ".join(verdict.suggestions).lower()
        self.assertIn("cave", suggestion)
        self.assertIn("level", suggestion)

    def test_missing_theme_is_partial(self):
        verdict = self.judge.judge(self.track(), MusicRequest("cave drones"))
        self.assertEqual(verdict.verdict, "partially_fits")

    def test_unicode_terms_are_shared(self):
        verdict = self.judge.judge(
            self.track(),
            MusicRequest("ağaç", theme="ağaç ormanı"),
        )
        self.assertEqual(verdict.verdict, VERDICT_FITS)
        self.assertTrue(verdict.accepted)


class JudgeRegistryTests(unittest.TestCase):
    def test_unknown_judge_is_explained(self):
        with self.assertRaises(ConfigurationError) as caught:
            build_judge("ears", MuseConfig(env={}))
        self.assertIn("ears", caught.exception.what)

    def test_mock_judge_is_pickable(self):
        self.assertEqual(build_judge("mock", MuseConfig(env={})).name, "mock")
