import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from muse.batch import MAX_BATCH_TRACKS, MAX_MANIFEST_BYTES, load_manifest
from muse.batch_state import load_state, manifest_fingerprint, save_state, state_path
from muse.cli import main
from muse.config import MuseConfig
from muse.errors import ConfigurationError, GenerationError, MuseError
from muse.judges.mock import MockJudge
from muse.providers.mock import MockMusicProvider
from muse.types import MusicRequest


class CountingProvider:
    name = "counting"
    model = "counting"

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def generate(self, request, destination):
        self.calls.append(request.prompt)
        return self.inner.generate(request, destination)


class FlakyProvider:
    name = "flaky"
    model = "flaky"

    def __init__(self, inner, fail_prompt):
        self.inner = inner
        self.fail_prompt = fail_prompt
        self.failures = 1
        self.calls = []

    def generate(self, request, destination):
        self.calls.append(request.prompt)
        if request.prompt == self.fail_prompt and self.failures:
            self.failures -= 1
            raise GenerationError("render failed", "the model is down", "retry later")
        return self.inner.generate(request, destination)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def write(self, payload):
        path = self.root / "tracks.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_tracks_with_defaults(self):
        path = self.write(
            {
                "tracks": [
                    {"prompt": "warm pads", "theme": "village", "duration": 12, "name": "dawn"},
                    {"prompt": "low drones", "theme": "cave"},
                ]
            }
        )
        requests = load_manifest(path)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].name, "dawn")
        self.assertEqual(requests[0].duration, 12.0)
        self.assertEqual(requests[1].duration, 30.0)

    def test_missing_file_is_explained(self):
        with self.assertRaises(MuseError) as caught:
            load_manifest(self.root / "nope.json")
        self.assertIn("manifest", caught.exception.what)
        self.assertIn("Fix", caught.exception.render())

    def test_invalid_json_is_explained_with_position(self):
        path = self.root / "broken.json"
        path.write_text('{"tracks": [}', encoding="utf-8")
        with self.assertRaises(ConfigurationError) as caught:
            load_manifest(path)
        self.assertIn("line", caught.exception.why)

    def test_root_and_track_shape_are_checked(self):
        with self.assertRaises(ConfigurationError):
            load_manifest(self.write([]))
        with self.assertRaises(ConfigurationError):
            load_manifest(self.write({"tracks": []}))
        with self.assertRaises(ConfigurationError):
            load_manifest(self.write({"tracks": ["nope"]}))
        with self.assertRaises(ConfigurationError):
            load_manifest(self.write({"tracks": [{"prompt": "x"}], "extra": 1}))

    def test_unknown_track_keys_and_bad_values_are_rejected(self):
        with self.assertRaises(ConfigurationError) as caught:
            load_manifest(self.write({"tracks": [{"prompt": "x", "tempo": 90}]}))
        self.assertIn("tempo", caught.exception.what)
        with self.assertRaises(ConfigurationError) as caught:
            load_manifest(self.write({"tracks": [{"prompt": "   "}]}))
        self.assertIn("track 1", caught.exception.what)
        with self.assertRaises(ConfigurationError) as caught:
            load_manifest(self.write({"tracks": [{"prompt": "x", "duration": True}]}))
        self.assertIn("track 1", caught.exception.what)
        with self.assertRaises(ConfigurationError):
            load_manifest(self.write({"tracks": [{"prompt": "x", "duration": 500}]}))

    def test_overflowing_duration_is_rejected(self):
        path = self.root / "huge-duration.json"
        path.write_text(
            '{"tracks": [{"prompt": "x", "duration": 1' + "0" * 400 + "}]}",
            encoding="utf-8",
        )
        with self.assertRaises(ConfigurationError) as caught:
            load_manifest(path)
        self.assertIn("track 1", caught.exception.what)

    def test_track_count_is_capped(self):
        path = self.write({"tracks": [{"prompt": f"track {i}"} for i in range(MAX_BATCH_TRACKS + 1)]})
        with self.assertRaises(ConfigurationError) as caught:
            load_manifest(path)
        self.assertIn(str(MAX_BATCH_TRACKS), caught.exception.what)

    def test_manifest_size_is_capped(self):
        path = self.root / "huge.json"
        path.write_text("x" * (MAX_MANIFEST_BYTES + 1), encoding="utf-8")
        with self.assertRaises(ConfigurationError) as caught:
            load_manifest(path)
        self.assertIn("limit", caught.exception.what)

    def test_utf8_bom_is_accepted(self):
        path = self.root / "bom.json"
        path.write_bytes(b'\xef\xbb\xbf{"tracks": [{"prompt": "cave drones"}]}')
        self.assertEqual(load_manifest(path)[0].prompt, "cave drones")


class BatchStateTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_fingerprint_is_stable_and_sensitive(self):
        first = (MusicRequest("cave", theme="cave level"),)
        second = (MusicRequest("cave", theme="cave level"),)
        third = (MusicRequest("cave", theme="village"),)
        self.assertEqual(manifest_fingerprint(first), manifest_fingerprint(second))
        self.assertNotEqual(manifest_fingerprint(first), manifest_fingerprint(third))

    def test_state_round_trip(self):
        fingerprint = manifest_fingerprint((MusicRequest("cave"),))
        path = state_path(self.root / "out", fingerprint)
        entry = {
            "index": 1,
            "name": "cave",
            "status": "accepted",
            "payload": {"accepted": True, "audio": "out/cave/track.wav"},
            "error": None,
        }
        save_state(path, fingerprint, [entry])
        loaded = load_state(path, fingerprint)
        self.assertEqual(loaded[1]["status"], "accepted")
        self.assertTrue(loaded[1]["payload"]["accepted"])

    def test_missing_or_mismatched_state_is_explained(self):
        fingerprint = manifest_fingerprint((MusicRequest("cave"),))
        path = state_path(self.root / "out", fingerprint)
        with self.assertRaises(ConfigurationError) as caught:
            load_state(path, fingerprint)
        self.assertIn("no batch state", caught.exception.what)

        save_state(path, fingerprint, [])
        with self.assertRaises(ConfigurationError) as caught:
            load_state(path, "other")
        self.assertIn("different manifest", caught.exception.what)

    def test_corrupt_state_is_explained(self):
        fingerprint = manifest_fingerprint((MusicRequest("cave"),))
        path = state_path(self.root / "out", fingerprint)
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ConfigurationError) as caught:
            load_state(path, fingerprint)
        self.assertIn("state", caught.exception.what)
        self.assertIn("Fix", caught.exception.render())

    def test_inconsistent_state_is_explained(self):
        fingerprint = manifest_fingerprint((MusicRequest("cave"),))
        path = state_path(self.root / "out", fingerprint)
        save_state(
            path,
            fingerprint,
            [
                {
                    "index": 1,
                    "name": "cave",
                    "status": "accepted",
                    "payload": {"accepted": False},
                    "error": None,
                }
            ],
        )
        with self.assertRaises(ConfigurationError) as caught:
            load_state(path, fingerprint)
        self.assertIn("inconsistent", caught.exception.what)

    def test_state_size_is_capped(self):
        fingerprint = manifest_fingerprint((MusicRequest("cave"),))
        path = state_path(self.root / "out", fingerprint)
        path.parent.mkdir(parents=True)
        with patch("muse.batch_state.MAX_STATE_BYTES", 20):
            path.write_text("x" * 21, encoding="utf-8")
            with self.assertRaises(ConfigurationError) as caught:
                load_state(path, fingerprint)
        self.assertIn("limit", caught.exception.what)

    def test_boolean_schema_is_rejected(self):
        fingerprint = manifest_fingerprint((MusicRequest("cave"),))
        path = state_path(self.root / "out", fingerprint)
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"schema": True, "manifest": fingerprint, "tracks": []}),
            encoding="utf-8",
        )
        with self.assertRaises(ConfigurationError) as caught:
            load_state(path, fingerprint)
        self.assertIn("schema", caught.exception.what)


class BatchCliTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.output = self.root / "out"
        self.config = MuseConfig(output_dir=self.output, provider="mock", judge="mock", env={})
        self.provider = MockMusicProvider(self.config)
        self.judge = MockJudge(self.config)

    def manifest(self, tracks):
        path = self.root / "tracks.json"
        path.write_text(json.dumps({"tracks": tracks}), encoding="utf-8")
        return path

    def run_cli(self, argv, judge=None, provider=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(
                argv,
                config=self.config,
                provider=provider or self.provider,
                judge=judge or self.judge,
            )
        return code, out.getvalue(), err.getvalue()

    def test_batch_json_renders_every_track(self):
        path = self.manifest(
            [
                {"prompt": "cave drones", "theme": "cave level", "duration": 1, "name": "cave"},
                {"prompt": "village pads", "theme": "village dawn", "duration": 1, "name": "village"},
            ]
        )
        code, out, err = self.run_cli(["batch", str(path), "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["accepted"], 2)
        self.assertEqual([track["name"] for track in payload["tracks"]], ["cave", "village"])
        for track in payload["tracks"]:
            self.assertTrue(track["accepted"])
            self.assertTrue(Path(track["audio"]).is_file())
            self.assertTrue(Path(track["metadata"]).is_file())

    def test_batch_human_output_and_strict_exit(self):
        path = self.manifest(
            [
                {"prompt": "cave drones", "theme": "cave level", "duration": 1},
                {"prompt": "sunny beach", "theme": "cave level", "duration": 1, "name": "rejected"},
            ]
        )
        code, out, err = self.run_cli(["batch", str(path)])
        self.assertEqual(code, 0, err)
        self.assertIn("[1/2]", out)
        self.assertIn("Batch: 1/2 accepted", out)
        self.assertIn("Rejected: rejected", out)

        code, _, _ = self.run_cli(["batch", str(path), "--strict"])
        self.assertEqual(code, 1)

    def test_batch_applies_attempts_per_track(self):
        path = self.manifest([{"prompt": "sunny beach", "theme": "cave level", "duration": 1}])
        code, out, err = self.run_cli(["batch", str(path), "--attempts", "2", "--json"])
        self.assertEqual(code, 0, err)
        track = json.loads(out)["tracks"][0]
        self.assertTrue(track["accepted"])
        self.assertEqual(len(track["attempts"]), 2)

    def test_batch_without_a_judge_is_refused(self):
        path = self.manifest([{"prompt": "x", "theme": "cave", "duration": 1}])
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(
                ["batch", str(path), "--judge", "none"],
                config=self.config,
                provider=self.provider,
            )
        self.assertEqual(code, 1)
        self.assertIn("listening judge", err.getvalue())

    def test_batch_missing_manifest_exits_one(self):
        code, _, err = self.run_cli(["batch", str(self.root / "nope.json")])
        self.assertEqual(code, 1)
        self.assertIn("manifest", err)
        self.assertIn("Fix:", err)

    def test_batch_dry_run_json_makes_no_calls(self):
        provider = CountingProvider(self.provider)
        path = self.manifest(
            [
                {"prompt": "cave drones", "theme": "cave level", "duration": 1, "name": "cave"},
                {"prompt": "village pads", "theme": "village dawn", "duration": 2, "name": "village"},
            ]
        )
        code, out, err = self.run_cli(
            ["batch", str(path), "--dry-run", "--attempts", "3", "--json"],
            provider=provider,
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["attempts"], 3)
        self.assertEqual([track["name"] for track in payload["tracks"]], ["cave", "village"])
        self.assertEqual(provider.calls, [])
        self.assertFalse(self.output.exists())

    def test_batch_dry_run_human_output_without_a_judge(self):
        path = self.manifest([{"prompt": "cave drones", "theme": "cave level", "duration": 1}])
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(
                ["batch", str(path), "--dry-run", "--judge", "none"],
                config=self.config,
                provider=self.provider,
            )
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("Dry run", out.getvalue())
        self.assertIn("No provider or judge was called", out.getvalue())
        self.assertFalse(self.output.exists())

    def state_file(self):
        matches = list(self.output.glob(".muse-batch-*.json"))
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_batch_writes_state_after_each_track(self):
        path = self.manifest(
            [
                {"prompt": "cave drones", "theme": "cave level", "duration": 1, "name": "cave"},
                {"prompt": "village pads", "theme": "village dawn", "duration": 1, "name": "village"},
            ]
        )
        code, _, err = self.run_cli(["batch", str(path)])
        self.assertEqual(code, 0, err)
        state = json.loads(self.state_file().read_text(encoding="utf-8"))
        self.assertEqual(state["schema"], 1)
        self.assertEqual([track["status"] for track in state["tracks"]], ["accepted", "accepted"])
        self.assertTrue(state["tracks"][0]["payload"]["accepted"])

    def test_resume_reuses_accepted_tracks(self):
        provider = CountingProvider(self.provider)
        path = self.manifest(
            [
                {"prompt": "cave drones", "theme": "cave level", "duration": 1, "name": "cave"},
                {"prompt": "village pads", "theme": "village dawn", "duration": 1, "name": "village"},
            ]
        )
        code, _, err = self.run_cli(["batch", str(path)], provider=provider)
        self.assertEqual(code, 0, err)
        self.assertEqual(provider.calls, ["cave drones", "village pads"])

        code, out, err = self.run_cli(["batch", str(path), "--resume"], provider=provider)
        self.assertEqual(code, 0, err)
        self.assertEqual(provider.calls, ["cave drones", "village pads"])
        self.assertIn("reused", out)
        self.assertIn("Batch: 2/2 accepted", out)

    def test_resume_rerenders_rejected_tracks(self):
        provider = CountingProvider(self.provider)
        path = self.manifest(
            [
                {"prompt": "cave drones", "theme": "cave level", "duration": 1, "name": "cave"},
                {"prompt": "sunny beach", "theme": "cave level", "duration": 1, "name": "sunny"},
            ]
        )
        code, _, err = self.run_cli(["batch", str(path)], provider=provider)
        self.assertEqual(code, 0, err)
        self.assertEqual(provider.calls.count("cave drones"), 1)

        code, out, err = self.run_cli(
            ["batch", str(path), "--resume", "--attempts", "2", "--json"],
            provider=provider,
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["accepted"], 2)
        self.assertEqual(provider.calls.count("cave drones"), 1)
        self.assertEqual(payload["reused"], 1)

    def test_resume_without_state_is_refused(self):
        provider = CountingProvider(self.provider)
        path = self.manifest([{"prompt": "cave drones", "theme": "cave level", "duration": 1}])
        code, _, err = self.run_cli(["batch", str(path), "--resume"], provider=provider)
        self.assertEqual(code, 1)
        self.assertIn("no batch state", err)
        self.assertEqual(provider.calls, [])

    def test_keep_going_records_failure_and_resume_finishes(self):
        provider = FlakyProvider(self.provider, fail_prompt="explode cave level")
        path = self.manifest(
            [
                {"prompt": "cave drones", "theme": "cave level", "duration": 1, "name": "ok"},
                {"prompt": "explode cave level", "theme": "cave level", "duration": 1, "name": "flaky"},
                {"prompt": "village pads", "theme": "village dawn", "duration": 1, "name": "after"},
            ]
        )
        code, out, err = self.run_cli(["batch", str(path), "--keep-going", "--json"], provider=provider)
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["accepted"], 2)
        self.assertEqual(payload["failed"], 1)
        self.assertEqual(payload["tracks"][1]["error"], "render failed")
        self.assertIsNone(payload["tracks"][1]["judge_error"])
        state = json.loads(self.state_file().read_text(encoding="utf-8"))
        self.assertEqual(
            [track["status"] for track in state["tracks"]],
            ["accepted", "failed", "accepted"],
        )

        code, out, err = self.run_cli(["batch", str(path), "--resume", "--json"], provider=provider)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["accepted"], 3)
        self.assertEqual(payload["reused"], 2)
        self.assertEqual(provider.calls.count("explode cave level"), 2)

    def test_resume_rerenders_when_evidence_is_missing(self):
        provider = CountingProvider(self.provider)
        path = self.manifest(
            [
                {"prompt": "cave drones", "theme": "cave level", "duration": 1, "name": "cave"},
                {"prompt": "village pads", "theme": "village dawn", "duration": 1, "name": "village"},
            ]
        )
        code, _, err = self.run_cli(["batch", str(path)], provider=provider)
        self.assertEqual(code, 0, err)
        state = json.loads(self.state_file().read_text(encoding="utf-8"))
        Path(state["tracks"][0]["payload"]["audio"]).unlink()

        code, _, err = self.run_cli(["batch", str(path), "--resume"], provider=provider)
        self.assertEqual(code, 0, err)
        self.assertIn("evidence", err)
        self.assertEqual(provider.calls.count("cave drones"), 2)
