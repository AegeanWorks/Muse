import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from muse.audio import write_tone
from muse.cli import main
from muse.config import MuseConfig
from muse.judges.mock import MockJudge
from muse.providers.mock import MockMusicProvider
from muse.types import VERDICT_FITS, VERDICT_MISS, Verdict


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


class CliTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.output = Path(folder.name)
        self.config = MuseConfig(output_dir=self.output, provider="mock", judge="mock", env={})
        self.provider = MockMusicProvider(self.config)
        self.judge = MockJudge(self.config)

    def run_cli(self, argv, judge=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv, config=self.config, provider=self.provider, judge=judge or self.judge)
        return code, out.getvalue(), err.getvalue()

    def test_generate_json(self):
        code, out, err = self.run_cli(
            ["generate", "cave drones", "--theme", "cave level", "--duration", "1", "--json"]
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["provider"], "mock")
        self.assertEqual(payload["verdict"]["score"], 88)
        self.assertTrue(payload["accepted"])
        self.assertTrue(Path(payload["audio"]).is_file())
        self.assertTrue(Path(payload["metadata"]).is_file())

    def test_strict_rejects_low_score(self):
        code, out, _ = self.run_cli(
            ["generate", "sunny beach", "--theme", "cave level", "--duration", "1", "--strict"]
        )
        self.assertEqual(code, 1)
        self.assertIn("Accepted: no", out)

    def test_judge_existing_file(self):
        path = self.output / "existing.wav"
        write_tone(path, 0.2)
        code, out, err = self.run_cli(
            ["judge", str(path), "--theme", "cave", "--prompt", "cave drones", "--json"]
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["verdict"]["score"], 88)
        self.assertEqual(payload["audio"], str(path))

    def test_judge_missing_file_exits_one(self):
        code, _, err = self.run_cli(["judge", str(self.output / "nope.wav"), "--theme", "cave"])
        self.assertEqual(code, 1)
        self.assertIn("audio file not found", err)

    def test_judge_none_is_explained(self):
        path = self.output / "existing.wav"
        write_tone(path, 0.2)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["judge", str(path), "--theme", "cave", "--judge", "none"], config=self.config)
        self.assertEqual(code, 1)
        self.assertIn("needs a listening judge", err.getvalue())

    def test_providers_json(self):
        code, out, _ = self.run_cli(["providers", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("replicate", payload["providers"])
        self.assertIn("gemini", payload["judges"])

    def test_version_exits_zero(self):
        code, out, _ = self.run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("muse", out)

    def test_empty_prompt_is_misuse_without_traceback(self):
        code, _, err = self.run_cli(["generate", "   ", "--duration", "1"])
        self.assertEqual(code, 2)
        self.assertIn("invalid request", err)
        self.assertIn("Fix:", err)
        self.assertNotIn("Traceback", err)

    def test_duration_beyond_model_limit_is_misuse(self):
        code, _, err = self.run_cli(["generate", "x", "--duration", "500"])
        self.assertEqual(code, 2)
        self.assertIn("duration", err)

    def test_min_score_outside_percent_is_reported(self):
        code, _, err = self.run_cli(["generate", "x", "--min-score", "101", "--duration", "1"])
        self.assertEqual(code, 1)
        self.assertIn("outside 0-100", err)

    def test_judge_reports_strengths(self):
        path = self.output / "existing.wav"
        write_tone(path, 0.2)
        code, out, _ = self.run_cli(
            ["judge", str(path), "--theme", "cave", "--prompt", "cave drones"]
        )
        self.assertEqual(code, 0)
        self.assertIn("Strengths:", out)

    def test_unknown_flag_is_misuse(self):
        code, _, _ = self.run_cli(["generate", "x", "--nope"])
        self.assertEqual(code, 2)

    def test_unknown_provider_exits_one(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["generate", "x", "--provider", "sunos", "--duration", "1"], config=self.config)
        self.assertEqual(code, 1)
        self.assertIn("unknown music provider", err.getvalue())
        self.assertIn("Fix:", err.getvalue())

    def test_allow_unjudged_missing_key_exits_zero(self):
        config = self.config.with_overrides(judge="gemini")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(
                ["generate", "x", "--duration", "1", "--provider", "mock", "--allow-unjudged"],
                config=config,
                provider=self.provider,
            )
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("Verdict: none", out.getvalue())
        self.assertIn("GEMINI_API_KEY", out.getvalue())

    def test_filesystem_failure_is_explained(self):
        with patch("muse.providers.mock.write_tone", side_effect=OSError("disk full")):
            code, _, err = self.run_cli(["generate", "x", "--duration", "1"])
        self.assertEqual(code, 1)
        self.assertIn("filesystem", err)
        self.assertIn("Fix:", err)
        self.assertNotIn("Traceback", err)

    def test_attempts_json_reports_every_take(self):
        judge = ScriptedJudge(
            [
                verdict(40, suggestions=("include cave",)),
                verdict(90, VERDICT_FITS),
            ]
        )
        code, out, err = self.run_cli(
            ["generate", "sunny beach", "--theme", "cave level", "--duration", "1", "--attempts", "2", "--json"],
            judge=judge,
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["accepted"])
        self.assertEqual(len(payload["attempts"]), 2)
        self.assertFalse(payload["attempts"][0]["accepted"])
        self.assertTrue(payload["attempts"][1]["accepted"])
        self.assertEqual(payload["attempts"][1]["score"], 90)

    def test_attempts_human_output_lists_takes(self):
        judge = ScriptedJudge(
            [
                verdict(40, suggestions=("include cave",)),
                verdict(90, VERDICT_FITS),
            ]
        )
        code, out, err = self.run_cli(
            ["generate", "sunny beach", "--theme", "cave level", "--duration", "1", "--attempts", "2"],
            judge=judge,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Attempts:", out)
        self.assertIn("<- selected", out)

    def test_attempts_out_of_range_is_misuse(self):
        code, _, err = self.run_cli(["generate", "x", "--duration", "1", "--attempts", "0"])
        self.assertEqual(code, 2)
        self.assertIn("attempts", err)
        self.assertNotIn("Traceback", err)

    def test_attempts_with_judge_none_is_explained(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(
                ["generate", "x", "--duration", "1", "--judge", "none", "--attempts", "2"],
                config=self.config,
                provider=self.provider,
            )
        self.assertEqual(code, 1)
        self.assertIn("listening judge", err.getvalue())
        self.assertIn("Fix:", err.getvalue())
