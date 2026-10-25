import json
import tempfile
import unittest
from pathlib import Path

from muse.artifacts import unique_directory, write_json_atomic
from muse.audio import mime_type, slugify, wav_duration, write_tone


class SlugTests(unittest.TestCase):
    def test_slugifies_prompt(self):
        self.assertEqual(slugify("Dark Ambient: Cave #3!"), "dark-ambient-cave-3")

    def test_falls_back_when_nothing_remains(self):
        self.assertEqual(slugify("***", fallback="theme"), "theme")


class MimeTests(unittest.TestCase):
    def test_known_and_unknown_suffixes(self):
        self.assertEqual(mime_type(Path("a.wav")), "audio/wav")
        self.assertEqual(mime_type(Path("a.MP3")), "audio/mp3")
        self.assertEqual(mime_type(Path("a.bin")), "audio/wav")


class ToneTests(unittest.TestCase):
    def test_writes_a_readable_wav(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tone.wav"
            write_tone(path, 0.25)
            self.assertGreater(path.stat().st_size, 44)
            self.assertAlmostEqual(wav_duration(path), 0.25, places=2)

    def test_duration_of_non_wav_is_none(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "x.wav"
            path.write_bytes(b"not a wav")
            self.assertIsNone(wav_duration(path))


class ArtifactTests(unittest.TestCase):
    def test_unique_directories_get_suffixes(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            first = unique_directory(parent, "Cave Theme")
            second = unique_directory(parent, "Cave Theme")
            self.assertEqual(first.name, "cave-theme")
            self.assertEqual(second.name, "cave-theme-2")
            self.assertTrue(first.is_dir() and second.is_dir())

    def test_json_write_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "meta.json"
            write_json_atomic(path, {"score": 88})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"score": 88})
            self.assertEqual([item.name for item in Path(folder).iterdir()], ["meta.json"])
