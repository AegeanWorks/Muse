import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from muse.batch import MAX_BATCH_TRACKS, MAX_MANIFEST_BYTES, load_manifest
from muse.cli import main
from muse.config import MuseConfig
from muse.errors import ConfigurationError, MuseError
from muse.judges.mock import MockJudge
from muse.providers.mock import MockMusicProvider


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

    def run_cli(self, argv, judge=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv, config=self.config, provider=self.provider, judge=judge or self.judge)
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
