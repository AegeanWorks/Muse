import io
import tempfile
import unittest
import urllib.error
from pathlib import Path

from muse.errors import MuseError
from muse.net import HttpClient, HttpResponse


class FlakyClient(HttpClient):
    def __init__(self, responses):
        self.sleeps = []
        super().__init__(timeout=1, retries=2, backoff=1.0, sleep=self.sleeps.append)
        self.responses = list(responses)

    def _once(self, method, url, body, headers):
        return self.responses.pop(0)


class HttpClientTests(unittest.TestCase):
    def test_retries_retryable_status(self):
        client = FlakyClient([HttpResponse(503, {}, b"busy"), HttpResponse(200, {}, b'{"ok": true}')])
        self.assertEqual(client.json("GET", "https://example.test"), {"ok": True})
        self.assertEqual(client.sleeps, [1.0])

    def test_does_not_retry_client_error(self):
        client = FlakyClient([HttpResponse(400, {}, b"bad request")])
        with self.assertRaises(MuseError) as caught:
            client.json("GET", "https://example.test")
        self.assertIn("400", caught.exception.what)
        self.assertEqual(client.sleeps, [])

    def test_retries_are_exhausted(self):
        client = FlakyClient([HttpResponse(500, {}, b"boom"), HttpResponse(500, {}, b"boom"), HttpResponse(500, {}, b"boom")])
        with self.assertRaises(MuseError):
            client.json("GET", "https://example.test")
        self.assertEqual(len(client.sleeps), 2)

    def test_non_json_body_is_explained(self):
        client = FlakyClient([HttpResponse(200, {}, b"<html>")])
        with self.assertRaises(MuseError) as caught:
            client.json("GET", "https://example.test")
        self.assertIn("non-JSON", caught.exception.what)


class FakeResponse:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self, size):
        chunk = self.chunks.pop(0)
        if isinstance(chunk, Exception):
            raise chunk
        return chunk


class ScriptedOpener:
    def __init__(self, actions):
        self.actions = list(actions)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


class DownloadTests(unittest.TestCase):
    def test_failed_download_leaves_no_partial_file(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "track.wav"
            opener = ScriptedOpener([FakeResponse([b"partial", OSError("network down")])])
            client = HttpClient(timeout=1, retries=0, sleep=lambda _: None, opener=opener)
            with self.assertRaises(MuseError):
                client.download("https://example.test/track.wav", destination)
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_download_retries_transport_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "track.wav"
            opener = ScriptedOpener(
                [
                    urllib.error.URLError("temporary"),
                    FakeResponse([b"RIFF", b"data", b""]),
                ]
            )
            sleeps = []
            client = HttpClient(timeout=1, retries=1, sleep=sleeps.append, opener=opener)
            client.download("https://example.test/track.wav", destination)
            self.assertEqual(destination.read_bytes(), b"RIFFdata")
            self.assertEqual(sleeps, [1.5])
            self.assertEqual([path.name for path in Path(folder).iterdir()], ["track.wav"])

    def test_download_does_not_retry_http_404(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "track.wav"
            not_found = urllib.error.HTTPError(
                "https://example.test/track.wav", 404, "missing", {}, io.BytesIO(b"missing")
            )
            opener = ScriptedOpener([not_found])
            client = HttpClient(timeout=1, retries=3, sleep=lambda _: None, opener=opener)
            with self.assertRaises(MuseError) as caught:
                client.download("https://example.test/track.wav", destination)
            self.assertIn("404", caught.exception.why)
            self.assertEqual(len(opener.requests), 1)
