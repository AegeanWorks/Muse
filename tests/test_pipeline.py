import json
import tempfile
import unittest
from pathlib import Path

from muse.config import MuseConfig
from muse.errors import GenerationError, JudgeError
from muse.judges.mock import MockJudge
from muse.pipeline import compose, judge_track
from muse.providers.mock import MockMusicProvider
from muse.types import MusicRequest, Track


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
        self.assertEqual(payload["schema"], 1)
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
        verdict = judge_track(track, MusicRequest("cave", theme="cave"), self.config, self.judge)
        self.assertEqual(verdict.judge, "mock")
