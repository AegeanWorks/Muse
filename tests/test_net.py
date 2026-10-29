import http.client
import io
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from muse.errors import MuseError
from muse.net import HttpClient, HttpResponse


class FlakyClient(HttpClient):
    def __init__(self, responses):
        self.sleeps = []
        super().__init__(timeout=1, retries=2, backoff=1.0, sleep=self.sleeps.append)
        self.responses = list(responses)

    def _once(self, method, url, body, headers):
        return self.responses.pop(0)


class BrokenClient(HttpClient):
    def __init__(self):
        super().__init__(timeout=1, retries=1, backoff=1.0, sleep=lambda _: None)
        self.calls = 0

    def _once(self, method, url, body, headers):
        self.calls += 1
        raise http.client.IncompleteRead(b"partial")


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

    def test_truncated_json_response_is_retried(self):
        client = BrokenClient()
        with self.assertRaises(MuseError) as caught:
            client.json("GET", "https://example.test")
        self.assertIn("could not be reached", caught.exception.what)
        self.assertEqual(client.calls, 2)

    def test_unserializable_payload_is_explained(self):
        client = FlakyClient([])
        with self.assertRaises(MuseError) as caught:
            client.json("POST", "https://example.test", {"bad": object()})
        self.assertIn("encoded", caught.exception.what)
        self.assertEqual(client.responses, [])


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
            self.addCleanup(not_found.close)
            opener = ScriptedOpener([not_found])
            client = HttpClient(timeout=1, retries=3, sleep=lambda _: None, opener=opener)
            with self.assertRaises(MuseError) as caught:
                client.download("https://example.test/track.wav", destination)
            self.assertIn("404", caught.exception.why)
            self.assertEqual(len(opener.requests), 1)

    def test_download_rejects_non_http_urls(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "track.wav"
            opener = ScriptedOpener([])
            client = HttpClient(timeout=1, retries=0, sleep=lambda _: None, opener=opener)
            with self.assertRaises(MuseError) as caught:
                client.download("file:///etc/passwd", destination)
            self.assertIn("http", caught.exception.what.lower())
            self.assertEqual(opener.requests, [])
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_download_rejects_an_empty_file(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "track.wav"
            opener = ScriptedOpener([FakeResponse([b""])])
            client = HttpClient(timeout=1, retries=0, sleep=lambda _: None, opener=opener)
            with self.assertRaises(MuseError) as caught:
                client.download("https://example.test/track.wav", destination)
            self.assertIn("empty", caught.exception.why)
            self.assertFalse(destination.exists())

    def test_truncated_download_is_retried_and_cleaned(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "track.wav"
            opener = ScriptedOpener(
                [
                    FakeResponse([b"RIFF", http.client.IncompleteRead(b"partial")]),
                    FakeResponse([b"RIFFdata", b""]),
                ]
            )
            sleeps = []
            client = HttpClient(timeout=1, retries=1, sleep=sleeps.append, opener=opener)
            client.download("https://example.test/track.wav", destination)
            self.assertEqual(destination.read_bytes(), b"RIFFdata")
            self.assertEqual(sleeps, [1.5])
            self.assertEqual([path.name for path in Path(folder).iterdir()], ["track.wav"])

    def test_download_size_is_capped(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "track.wav"
            opener = ScriptedOpener([FakeResponse([b"123456789"])])
            client = HttpClient(timeout=1, retries=0, sleep=lambda _: None, opener=opener)
            with patch("muse.net.MAX_DOWNLOAD_BYTES", 5):
                with self.assertRaises(MuseError) as caught:
                    client.download("https://example.test/track.wav", destination)
            self.assertIn("too large", caught.exception.what)
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_download_folder_failure_is_explained(self):
        with tempfile.TemporaryDirectory() as folder:
            blocker = Path(folder) / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            destination = blocker / "track.wav"
            client = HttpClient(timeout=1, retries=0, sleep=lambda _: None, opener=ScriptedOpener([]))
            with self.assertRaises(MuseError) as caught:
                client.download("https://example.test/track.wav", destination)
            self.assertIn("folder", caught.exception.what.lower())
