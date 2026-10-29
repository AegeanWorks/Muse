import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from muse.cli import main
from muse.config import MuseConfig
from muse.errors import JudgeError


def write_artifact(root, folder, *, prompt, theme, score=45, accepted=False, verdict="does_not_fit", schema=2):
    path = root / folder
    path.mkdir(parents=True)
    (path / "track.wav").write_bytes(b"RIFF")
    payload = {
        "schema": schema,
        "created_at": "2026-01-01T00:00:00+00:00",
        "request": {"prompt": prompt, "theme": theme, "duration": 1, "name": folder},
        "track": {
            "file": "track.wav",
            "provider": "mock",
            "model": "mock-tone",
            "duration_seconds": 1,
            "source_url": None,
        },
        "verdict": {
            "score": score,
            "verdict": verdict,
            "summary": "old summary",
            "strengths": [],
            "issues": [],
            "suggestions": [],
            "judge": "mock",
            "model": "mock-judge",
            "threshold": 60,
        },
        "accepted": accepted,
        "judge_error": None,
        "settings": {"provider": "mock", "music_model": "old", "judge": "mock", "judge_model": "old"},
    }
    if schema == 2:
        payload["attempt"] = {"number": 1, "planned": 1, "prompt": prompt}
    (path / "muse.json").write_text(json.dumps(payload), encoding="utf-8")
    return path


class FailingJudge:
    name = "failing"
    model = "failing"

    def judge(self, track, request):
        raise JudgeError("judge unavailable", "service down", "retry later")


class RejudgeCliTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.config = MuseConfig(output_dir=self.root, provider="mock", judge="mock", env={})

    def run_cli(self, argv, judge=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv, config=self.config, judge=judge)
        return code, out.getvalue(), err.getvalue()

    def test_rejudge_updates_metadata_and_history(self):
        write_artifact(self.root, "cave", prompt="cave drones", theme="cave level")
        code, out, err = self.run_cli(["rejudge", "cave", "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["artifacts"][0]["old_score"], 45)
        self.assertEqual(payload["artifacts"][0]["score"], 88)
        self.assertTrue(payload["accepted"])

        metadata = json.loads((self.root / "cave" / "muse.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["schema"], 3)
        self.assertEqual(metadata["verdict"]["score"], 88)
        self.assertTrue(metadata["accepted"])
        self.assertEqual(len(metadata["history"]), 1)
        self.assertEqual(metadata["history"][0]["verdict"]["score"], 45)
        self.assertEqual(metadata["settings"]["judge"], "mock")

        code, listed, err = self.run_cli(["list", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(listed)["artifacts"][0]["score"], 88)

    def test_rejudge_multiple_and_strict(self):
        write_artifact(self.root, "cave", prompt="cave drones", theme="cave level")
        write_artifact(self.root, "sunny", prompt="sunny beach", theme="cave level")
        code, out, err = self.run_cli(["rejudge", "cave", "sunny", "--strict", "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["accepted"], 1)
        self.assertEqual([item["score"] for item in payload["artifacts"]], [88, 45])

    def test_rejudge_failure_leaves_evidence_unchanged(self):
        write_artifact(self.root, "cave", prompt="cave drones", theme="cave level")
        before = (self.root / "cave" / "muse.json").read_text(encoding="utf-8")
        code, _, err = self.run_cli(["rejudge", "cave"], judge=FailingJudge())
        self.assertEqual(code, 1)
        self.assertIn("judge unavailable", err)
        self.assertEqual((self.root / "cave" / "muse.json").read_text(encoding="utf-8"), before)

    def test_rejudge_twice_appends_history(self):
        write_artifact(self.root, "cave", prompt="cave drones", theme="cave level")
        code, _, err = self.run_cli(["rejudge", "cave"])
        self.assertEqual(code, 0, err)
        code, _, err = self.run_cli(["rejudge", "cave"])
        self.assertEqual(code, 0, err)
        metadata = json.loads((self.root / "cave" / "muse.json").read_text(encoding="utf-8"))
        self.assertEqual(len(metadata["history"]), 2)
        self.assertEqual(metadata["history"][0]["verdict"]["score"], 45)
        self.assertEqual(metadata["history"][1]["verdict"]["score"], 88)

    def test_rejudge_missing_and_judge_none(self):
        code, _, err = self.run_cli(["rejudge", "nope"])
        self.assertEqual(code, 1)
        self.assertIn("artifact not found", err)
        code, _, err = self.run_cli(["rejudge", "nope", "--judge", "none"])
        self.assertEqual(code, 1)
        self.assertIn("needs a listening judge", err)
