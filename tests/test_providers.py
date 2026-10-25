import tempfile
import unittest
from pathlib import Path

from muse.audio import write_tone
from muse.config import MuseConfig
from muse.errors import ConfigurationError, GenerationError
from muse.providers.mock import MockMusicProvider
from muse.providers.registry import build_provider
from muse.providers.replicate import ReplicateMusicProvider
from muse.types import MusicRequest


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.downloads = []

    def json(self, method, url, payload=None, headers=None):
        self.calls.append({"method": method, "url": url, "payload": payload, "headers": headers})
        return self.responses.pop(0)

    def download(self, url, destination, headers=None):
        self.downloads.append((url, Path(destination)))
        write_tone(Path(destination), 0.25)


def config(**changes):
    return MuseConfig(env={"REPLICATE_API_TOKEN": "token"}, **changes)


class ReplicateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.destination = Path(self.folder.name)

    def test_official_model_flow(self):
        http = FakeHttp(
            [
                {"status": "starting", "urls": {"get": "https://api.test/p/1"}},
                {"status": "succeeded", "output": "https://delivery.test/track.wav"},
            ]
        )
        provider = ReplicateMusicProvider(config(), http=http, sleep=lambda _: None)
        track = provider.generate(MusicRequest("cave drones", duration=12), self.destination)
        self.assertEqual(track.path.name, "track.wav")
        self.assertTrue(track.path.is_file())
        self.assertAlmostEqual(track.duration_seconds, 0.25, places=2)
        self.assertEqual(track.model, "stability-ai/stable-audio-2.5")
        create = http.calls[0]
        self.assertEqual(create["method"], "POST")
        self.assertIn("/models/stability-ai/stable-audio-2.5/predictions", create["url"])
        self.assertEqual(create["payload"]["input"]["prompt"], "cave drones")
        self.assertEqual(create["payload"]["input"]["duration"], 12.0)
        self.assertEqual(http.calls[1]["method"], "GET")
        self.assertEqual(http.calls[1]["headers"]["Authorization"], "Bearer token")

    def test_pinned_version_uses_predictions_endpoint(self):
        http = FakeHttp(
            [
                {"status": "starting", "urls": {"get": "https://api.test/p/2"}},
                {"status": "succeeded", "output": ["https://delivery.test/track.mp3"]},
            ]
        )
        provider = ReplicateMusicProvider(
            config(replicate_version="abc123"), http=http, sleep=lambda _: None
        )
        track = provider.generate(MusicRequest("menu loop", duration=8), self.destination)
        self.assertEqual(track.path.suffix, ".mp3")
        self.assertEqual(http.calls[0]["url"], "https://api.replicate.com/v1/predictions")
        self.assertEqual(http.calls[0]["payload"]["version"], "abc123")

    def test_failed_prediction_is_reported(self):
        http = FakeHttp(
            [
                {"status": "starting", "urls": {"get": "https://api.test/p/3"}},
                {"status": "failed", "error": "model exploded"},
            ]
        )
        provider = ReplicateMusicProvider(config(), http=http, sleep=lambda _: None)
        with self.assertRaises(GenerationError) as caught:
            provider.generate(MusicRequest("x"), self.destination)
        self.assertIn("model exploded", caught.exception.why)

    def test_timeout_is_reported(self):
        http = FakeHttp(
            [
                {"status": "starting", "urls": {"get": "https://api.test/p/4"}},
                {"status": "processing"},
            ]
        )
        provider = ReplicateMusicProvider(
            config(poll_timeout=0.001), http=http, sleep=lambda _: None
        )
        with self.assertRaises(GenerationError) as caught:
            provider.generate(MusicRequest("x"), self.destination)
        self.assertIn("timed out", caught.exception.what)

    def test_empty_output_is_reported(self):
        http = FakeHttp(
            [
                {"status": "starting", "urls": {"get": "https://api.test/p/5"}},
                {"status": "succeeded", "output": None},
            ]
        )
        provider = ReplicateMusicProvider(config(), http=http, sleep=lambda _: None)
        with self.assertRaises(GenerationError) as caught:
            provider.generate(MusicRequest("x"), self.destination)
        self.assertIn("no audio", caught.exception.what)

    def test_missing_handle_is_reported(self):
        http = FakeHttp([{"status": "starting"}])
        provider = ReplicateMusicProvider(config(), http=http, sleep=lambda _: None)
        with self.assertRaises(GenerationError) as caught:
            provider.generate(MusicRequest("x"), self.destination)
        self.assertIn("prediction handle", caught.exception.what)


class RegistryTests(unittest.TestCase):
    def test_mock_provider_is_pickable(self):
        provider = build_provider("mock", MuseConfig(env={}))
        self.assertEqual(provider.name, "mock")

    def test_unknown_provider_is_explained(self):
        with self.assertRaises(ConfigurationError) as caught:
            build_provider("sunos", MuseConfig(env={}))
        self.assertIn("sunos", caught.exception.what)

    def test_mock_provider_writes_a_file(self):
        with tempfile.TemporaryDirectory() as folder:
            track = MockMusicProvider().generate(MusicRequest("x", duration=5), Path(folder))
            self.assertTrue(track.path.is_file())
            self.assertAlmostEqual(track.duration_seconds, 2.0, places=2)
