import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from muse.config import MuseConfig
from muse.errors import ConfigurationError, GenerationError, JudgeError, MuseError
from muse.judges.mock import MockJudge
from muse.pipeline import PROMPT_LIMIT, compose, judge_track, revise_prompt
from muse.providers.mock import MockMusicProvider
from muse.types import MAX_ATTEMPTS, VERDICT_FITS, VERDICT_MISS, MusicRequest, Track, Verdict


class FailingJudge:
    name = "failing"
    model = "failing"

    def judge(self, track, request):
        raise JudgeError("judge unavailable", "the service is down", "retry later")


class FailingProvider:
    name = "failing"
    model = "failing"

    def generate(self, request, destination):
        raise GenerationError("render failed", "the model is down", "retry later")


class CountingProvider:
    name = "counting"
    model = "counting"

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    def generate(self, request, destination):
        self.calls += 1
        return self.inner.generate(request, destination)


class ScriptedJudge:
    name = "scripted"
    model = "scripted"

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.requests = []

    def judge(self, track, request):
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.verdicts) - 1)
        return self.verdicts[index]


def verdict(score, kind=VERDICT_MISS, suggestions=()):
    return Verdict(
        score=score,
        verdict=kind,
        summary="scripted verdict",
        strengths=(),
        issues=(),
        suggestions=tuple(suggestions),
        judge="scripted",
        model="scripted",
        threshold=60,
    )


class PipelineTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.output = Path(folder.name)
        self.config = MuseConfig(output_dir=self.output, provider="mock", judge="mock", env={})
        self.provider = MockMusicProvider(self.config)
        self.judge = MockJudge(self.config)

    def test_compose_writes_audio_verdict_and_metadata(self):
        request = MusicRequest("dark cave drones", theme="cave level", duration=1, name="Cave")
        result = compose(request, self.config, provider=self.provider, judge=self.judge)
        self.assertTrue(result.track.path.is_file())
        self.assertTrue(result.accepted)
        self.assertEqual(result.track.path.parent.name, "cave")
        payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], 2)
        self.assertEqual(payload["attempt"]["number"], 1)
        self.assertEqual(payload["attempt"]["planned"], 1)
        self.assertEqual(payload["request"]["theme"], "cave level")
        self.assertEqual(payload["track"]["provider"], "mock")
        self.assertEqual(payload["verdict"]["score"], 88)
        self.assertTrue(payload["accepted"])
        self.assertIsNone(payload["judge_error"])
        self.assertNotIn("key", json.dumps(payload["settings"]).lower())

    def test_second_composition_gets_a_unique_folder(self):
        request = MusicRequest("cave", theme="cave", duration=1)
        first = compose(request, self.config, provider=self.provider, judge=self.judge)
        second = compose(request, self.config, provider=self.provider, judge=self.judge)
        self.assertNotEqual(first.track.path.parent, second.track.path.parent)

    def test_judge_none_skips_listening(self):
        config = self.config.with_overrides(judge="none")
        result = compose(MusicRequest("x"), config, provider=self.provider)
        self.assertIsNone(result.verdict)
        self.assertFalse(result.accepted)
        payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        self.assertIsNone(payload["verdict"])

    def test_required_judge_failure_raises_but_keeps_evidence(self):
        with self.assertRaises(JudgeError):
            compose(
                MusicRequest("x", duration=1),
                self.config,
                provider=self.provider,
                judge=FailingJudge(),
            )
        folders = list(self.output.iterdir())
        self.assertEqual(len(folders), 1)
        payload = json.loads((folders[0] / "muse.json").read_text(encoding="utf-8"))
        self.assertIsNone(payload["verdict"])
        self.assertEqual(payload["judge_error"], "judge unavailable")
        self.assertTrue((folders[0] / "track.wav").is_file())

    def test_optional_judge_failure_keeps_audio(self):
        result = compose(
            MusicRequest("x", duration=1),
            self.config,
            provider=self.provider,
            judge=FailingJudge(),
            require_judge=False,
        )
        self.assertTrue(result.track.path.is_file())
        self.assertIsNone(result.verdict)
        self.assertEqual(result.judge_error, "judge unavailable")
        payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["judge_error"], "judge unavailable")

    def test_required_judge_is_built_before_rendering(self):
        config = self.config.with_overrides(judge="gemini")
        provider = CountingProvider(self.provider)
        with self.assertRaises(ConfigurationError) as caught:
            compose(MusicRequest("x", duration=1), config, provider=provider)
        self.assertIn("GEMINI_API_KEY", caught.exception.what)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_allow_unjudged_renders_when_the_judge_cannot_be_built(self):
        config = self.config.with_overrides(judge="gemini")
        provider = CountingProvider(self.provider)
        result = compose(
            MusicRequest("x", duration=1),
            config,
            provider=provider,
            require_judge=False,
        )
        self.assertEqual(provider.calls, 1)
        self.assertTrue(result.track.path.is_file())
        self.assertIsNone(result.verdict)
        self.assertIn("GEMINI_API_KEY", result.judge_error)
        payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        self.assertIn("GEMINI_API_KEY", payload["judge_error"])

    def test_tokens_never_reach_metadata(self):
        config = self.config.with_overrides(env={"GEMINI_API_KEY": "top-secret", "REPLICATE_API_TOKEN": "other"})
        result = compose(MusicRequest("x", duration=1), config, provider=self.provider, judge=self.judge)
        text = result.metadata_path.read_text(encoding="utf-8")
        self.assertNotIn("top-secret", text)
        self.assertNotIn("other", text)

    def test_failed_generation_removes_empty_run_folder(self):
        with self.assertRaises(GenerationError):
            compose(
                MusicRequest("x", duration=1),
                self.config,
                provider=FailingProvider(),
                judge=self.judge,
            )
        self.assertEqual(list(self.output.iterdir()), [])

    def test_judge_track_uses_injected_judge(self):
        track = Track(Path("x.wav"), "mock", "m", 1.0, "cave", "cave")
        result = judge_track(track, MusicRequest("cave", theme="cave"), self.config, self.judge)
        self.assertEqual(result.judge, "mock")

    def test_attempts_stop_after_acceptance(self):
        judge = ScriptedJudge([verdict(88, VERDICT_FITS)])
        request = MusicRequest("cave drones", theme="cave level", duration=1)
        result = compose(
            request,
            self.config,
            provider=self.provider,
            judge=judge,
            max_attempts=3,
        )
        self.assertTrue(result.accepted)
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(len(list(self.output.iterdir())), 1)

    def test_rejected_track_is_retried_with_judge_suggestions(self):
        judge = ScriptedJudge(
            [
                verdict(40, suggestions=("include cave drones",)),
                verdict(90, VERDICT_FITS),
            ]
        )
        request = MusicRequest("sunny beach", theme="cave level", duration=1, name="take")
        result = compose(
            request,
            self.config,
            provider=self.provider,
            judge=judge,
            max_attempts=3,
        )
        self.assertEqual([item.prompt for item in judge.requests], ["sunny beach", "sunny beach; include cave drones"])
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual(result.verdict.score, 90)
        self.assertTrue(result.accepted)
        self.assertEqual(result.attempts[-1].number, 2)
        payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], 2)
        self.assertEqual(payload["selected_attempt"], 2)
        self.assertEqual([item["number"] for item in payload["attempts"]], [1, 2])
        self.assertTrue(payload["attempts"][0]["audio"].endswith("track.wav"))
        first = json.loads(result.attempts[0].metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(first["attempt"]["number"], 1)
        self.assertEqual(first["attempt"]["planned"], 3)
        self.assertNotEqual(result.attempts[0].metadata_path, result.metadata_path)

    def test_history_read_failure_is_a_muse_error(self):
        judge = ScriptedJudge(
            [
                verdict(40, suggestions=("include cave",)),
                verdict(90, VERDICT_FITS),
            ]
        )
        with patch("muse.pipeline.Path.read_text", side_effect=OSError("denied")):
            with self.assertRaises(MuseError) as caught:
                compose(
                    MusicRequest("sunny beach", theme="cave level", duration=1),
                    self.config,
                    provider=self.provider,
                    judge=judge,
                    max_attempts=2,
                )
        self.assertIn("could not update", caught.exception.what)

    def test_best_attempt_wins_when_none_are_accepted(self):
        judge = ScriptedJudge(
            [
                verdict(30, suggestions=("add strings",)),
                verdict(50, suggestions=("add brass",)),
            ]
        )
        result = compose(
            MusicRequest("sunny beach", theme="cave level", duration=1),
            self.config,
            provider=self.provider,
            judge=judge,
            max_attempts=2,
        )
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual(result.verdict.score, 50)
        self.assertFalse(result.accepted)
        self.assertEqual(result.metadata_path, result.attempts[1].metadata_path)
        payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["selected_attempt"], 2)

    def test_attempts_stop_when_the_judge_offers_no_suggestions(self):
        judge = ScriptedJudge([verdict(40)])
        result = compose(
            MusicRequest("sunny beach", theme="cave level", duration=1),
            self.config,
            provider=self.provider,
            judge=judge,
            max_attempts=3,
        )
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(len(list(self.output.iterdir())), 1)

    def test_attempts_without_a_judge_are_refused(self):
        config = self.config.with_overrides(judge="none")
        with self.assertRaises(ConfigurationError) as caught:
            compose(
                MusicRequest("x", duration=1),
                config,
                provider=self.provider,
                max_attempts=2,
            )
        self.assertIn("listening judge", caught.exception.what)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_attempt_count_is_bounded(self):
        with self.assertRaises(ValueError):
            compose(
                MusicRequest("x", duration=1),
                self.config,
                provider=self.provider,
                judge=self.judge,
                max_attempts=MAX_ATTEMPTS + 1,
            )
        self.assertEqual(list(self.output.iterdir()), [])

    def test_mock_judge_refinement_reaches_fit_offline(self):
        request = MusicRequest("sunny beach", theme="cave level", duration=1)
        result = compose(
            request,
            self.config,
            provider=self.provider,
            judge=self.judge,
            max_attempts=2,
        )
        self.assertEqual(len(result.attempts), 2)
        self.assertIn("cave", result.attempts[1].prompt.lower())
        self.assertTrue(result.accepted)


class RevisePromptTests(unittest.TestCase):
    def test_returns_the_prompt_when_nothing_is_actionable(self):
        base = "cave drones"
        result = revise_prompt(base, verdict(40, suggestions=("cave drones", "  ", "")))
        self.assertEqual(result, base)

    def test_appends_distinct_suggestions_once(self):
        result = revise_prompt("cave drones", verdict(40, suggestions=("Add strings", "add strings")))
        self.assertEqual(result, "cave drones; Add strings")

    def test_keeps_the_prompt_within_the_limit(self):
        base = "x" * (PROMPT_LIMIT - 5)
        result = revise_prompt(base, verdict(40, suggestions=("add a choir", "add brass")))
        self.assertEqual(result, base)
