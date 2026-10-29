import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from muse.catalog import load_artifacts
from muse.cli import main
from muse.config import MuseConfig


def write_artifact(
    root,
    folder,
    *,
    schema=2,
    accepted=True,
    score=88,
    verdict="fits",
    created="2026-01-01T00:00:00+00:00",
    audio=True,
):
    path = root / folder
    path.mkdir(parents=True)
    if audio:
        (path / "track.wav").write_bytes(b"RIFF")
    payload = {
        "schema": schema,
        "created_at": created,
        "request": {"prompt": f"{folder} prompt", "theme": f"{folder} theme", "duration": 1, "name": folder},
        "track": {
            "file": "track.wav",
            "provider": "mock",
            "model": "mock-tone",
            "duration_seconds": 1,
            "source_url": None,
        },
        "verdict": None
        if score is None
        else {
            "score": score,
            "verdict": verdict,
            "summary": "summary",
            "strengths": [],
            "issues": [],
            "suggestions": [],
            "judge": "mock",
            "model": "mock-judge",
            "threshold": 60,
        },
        "accepted": accepted,
        "judge_error": None,
        "settings": {},
    }
    if schema == 2:
        payload["attempt"] = {"number": 1, "planned": 1, "prompt": f"{folder} prompt"}
    (path / "muse.json").write_text(json.dumps(payload), encoding="utf-8")
    return path


class CatalogTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_reads_filters_and_limits(self):
        write_artifact(self.root, "cave")
        write_artifact(self.root, "sunny", accepted=False, score=45, verdict="does_not_fit")
        write_artifact(self.root, "village", score=70, verdict="partially_fits")
        entries, warnings = load_artifacts(self.root)
        self.assertEqual(len(entries), 3)
        self.assertEqual(warnings, [])
        accepted, _ = load_artifacts(self.root, accepted_only=True)
        self.assertEqual(len(accepted), 2)
        limited, _ = load_artifacts(self.root, limit=1)
        self.assertEqual(len(limited), 1)

    def test_sorts_newest_first(self):
        write_artifact(self.root, "old", created="2026-01-01T00:00:00+00:00")
        write_artifact(self.root, "new", created="2026-02-01T00:00:00+00:00")
        entries, _ = load_artifacts(self.root)
        self.assertEqual([entry.folder for entry in entries], ["new", "old"])

    def test_skips_corrupt_oversized_and_unknown_schema(self):
        bad = self.root / "bad"
        bad.mkdir()
        (bad / "muse.json").write_text("{not json", encoding="utf-8")
        huge = self.root / "huge"
        huge.mkdir()
        with patch("muse.catalog.MAX_METADATA_BYTES", 10):
            (huge / "muse.json").write_text("x" * 11, encoding="utf-8")
            entries, warnings = load_artifacts(self.root)
        self.assertEqual(entries, [])
        self.assertEqual(len(warnings), 2)
        write_artifact(self.root, "future", schema=3)
        entries, warnings = load_artifacts(self.root)
        self.assertEqual(entries, [])
        self.assertEqual(len(warnings), 3)

    def test_schema_one_and_missing_audio(self):
        write_artifact(self.root, "legacy", schema=1, audio=False)
        entries, warnings = load_artifacts(self.root)
        self.assertEqual(len(entries), 1)
        self.assertEqual(warnings, [])
        entry = entries[0]
        self.assertFalse(entry.audio_exists)
        self.assertEqual(entry.score, 88)
        self.assertEqual(entry.verdict, "fits")
        self.assertEqual(entry.provider, "mock")
        self.assertEqual(entry.attempts, 1)

    def test_counts_attempt_history(self):
        path = write_artifact(self.root, "retry")
        payload = json.loads((path / "muse.json").read_text(encoding="utf-8"))
        payload["attempts"] = [{"number": 1}, {"number": 2}]
        (path / "muse.json").write_text(json.dumps(payload), encoding="utf-8")
        entries, _ = load_artifacts(self.root)
        self.assertEqual(entries[0].attempts, 2)

    def test_rejects_windows_separator_in_file_name(self):
        path = write_artifact(self.root, "traversal")
        payload = json.loads((path / "muse.json").read_text(encoding="utf-8"))
        payload["track"]["file"] = "..\\track.wav"
        (path / "muse.json").write_text(json.dumps(payload), encoding="utf-8")
        entries, warnings = load_artifacts(self.root)
        self.assertEqual(entries, [])
        self.assertIn("plain file name", warnings[0])

    def test_limit_must_be_positive_when_given(self):
        for limit in (0, -1, True):
            with self.assertRaises(ValueError):
                load_artifacts(self.root, limit=limit)


class ListCliTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.output = self.root / "out"
        self.config = MuseConfig(output_dir=self.output, provider="mock", judge="mock", env={})

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv, config=self.config)
        return code, out.getvalue(), err.getvalue()

    def test_list_json(self):
        write_artifact(self.output, "cave")
        write_artifact(self.output, "sunny", accepted=False, score=45, verdict="does_not_fit")
        code, out, err = self.run_cli(["list", "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["total"], 2)
        self.assertEqual({artifact["folder"] for artifact in payload["artifacts"]}, {"cave", "sunny"})
        self.assertTrue(payload["artifacts"][0]["audio_exists"])

    def test_list_filters_and_limits(self):
        write_artifact(self.output, "cave")
        write_artifact(self.output, "sunny", accepted=False, score=45, verdict="does_not_fit")
        code, out, err = self.run_cli(["list", "--accepted-only", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["total"], 1)
        code, out, err = self.run_cli(["list", "--limit", "1", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["total"], 1)

    def test_list_empty_and_corrupt(self):
        code, out, err = self.run_cli(["list"])
        self.assertEqual(code, 0)
        self.assertIn("No artifacts", out)
        bad = self.output / "bad"
        bad.mkdir(parents=True)
        (bad / "muse.json").write_text("{not json", encoding="utf-8")
        code, out, err = self.run_cli(["list", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["total"], 0)
        self.assertIn("Warning", err)

    def test_list_limit_zero_is_misuse(self):
        code, _, err = self.run_cli(["list", "--limit", "0"])
        self.assertEqual(code, 2)
        self.assertIn("limit", err)
        self.assertNotIn("Traceback", err)


class ShowCliTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.output = self.root / "out"
        self.config = MuseConfig(output_dir=self.output, provider="mock", judge="mock", env={})

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv, config=self.config)
        return code, out.getvalue(), err.getvalue()

    def test_show_human_and_json(self):
        write_artifact(self.output, "cave")
        code, out, err = self.run_cli(["show", "cave"])
        self.assertEqual(code, 0, err)
        self.assertIn("Verdict: 88/100 fits", out)
        self.assertIn("Prompt: cave prompt", out)
        self.assertIn("accepted", out)

        code, out, err = self.run_cli(["show", "cave", "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["schema"], 2)
        self.assertEqual(payload["request"]["prompt"], "cave prompt")
        self.assertEqual(payload["verdict"]["score"], 88)

    def test_show_accepts_a_folder_or_metadata_path(self):
        path = write_artifact(self.output, "cave")
        for argument in (str(path), str(path / "muse.json"), str(path / "track.wav")):
            code, out, err = self.run_cli(["show", argument])
            self.assertEqual(code, 0, err)
            self.assertIn("cave prompt", out)

    def test_show_marks_missing_audio(self):
        write_artifact(self.output, "cave", audio=False)
        code, out, err = self.run_cli(["show", "cave"])
        self.assertEqual(code, 0, err)
        self.assertIn("[audio missing]", out)

    def test_show_missing_and_corrupt(self):
        code, _, err = self.run_cli(["show", "nope"])
        self.assertEqual(code, 1)
        self.assertIn("artifact not found", err)
        bad = self.output / "bad"
        bad.mkdir(parents=True)
        (bad / "muse.json").write_text("{not json", encoding="utf-8")
        code, _, err = self.run_cli(["show", "bad"])
        self.assertEqual(code, 1)
        self.assertIn("could not read", err)
        self.assertIn("Fix:", err)
