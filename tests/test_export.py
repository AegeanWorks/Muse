"""Export: stream any PCM WAV to the mono 16-bit file an engine loader accepts."""

import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from muse.analysis import analyze_audio, evaluate, requirements_from_mapping
from muse.errors import ConfigurationError, ExportError
from muse.export import MAX_RATE, MIN_RATE, export_wav

ENGINE = {"channels": [1], "sample_width_bits": [16]}


def sine(count, rate, hertz=220.0, amplitude=0.5):
    return [amplitude * math.sin(2 * math.pi * hertz * index / rate) for index in range(count)]


def pack(frames, width):
    """Pack channel-interleaved floats in [-1, 1] as PCM of `width` bytes."""
    if width == 1:
        return bytes(max(0, min(255, round(value * 127) + 128)) for value in frames)
    if width == 2:
        return struct.pack(f"<{len(frames)}h", *(round(value * 32767) for value in frames))
    if width == 3:
        return b"".join(round(value * 8388607).to_bytes(3, "little", signed=True) for value in frames)
    return struct.pack(f"<{len(frames)}i", *(round(value * 2147483647) for value in frames))


class ExportCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def wav(self, name, frames, rate=44100, channels=1, width=2):
        path = self.root / name
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(width)
            handle.setframerate(rate)
            handle.writeframes(pack(frames, width))
        return path

    def samples(self, path):
        with wave.open(str(path), "rb") as handle:
            data = handle.readframes(handle.getnframes())
        return struct.unpack(f"<{len(data) // 2}h", data)


class ExportFormatTests(ExportCase):
    def test_stereo_44k_becomes_mono_16_bit_at_the_chosen_rate(self):
        left = sine(4410, 44100)
        stereo = [value for pair in zip(left, left) for value in pair]
        source = self.wav("in.wav", stereo, channels=2)
        result = export_wav(source, self.root / "out.wav", 22050)
        profile, reason = analyze_audio(result.destination)
        self.assertEqual(reason, "")
        self.assertEqual((profile.channels, profile.sample_width, profile.sample_rate), (1, 2, 22050))
        self.assertAlmostEqual(profile.duration, 0.1, places=2)
        self.assertTrue(evaluate(profile, requirements_from_mapping(ENGINE), None)["ok"])

    def test_every_pcm_width_is_accepted(self):
        for width in (1, 2, 3, 4):
            with self.subTest(width=width):
                source = self.wav(f"w{width}.wav", sine(800, 8000), rate=8000, width=width)
                result = export_wav(source, self.root / f"o{width}.wav", 8000)
                profile, _ = analyze_audio(result.destination)
                self.assertEqual(profile.sample_width, 2)
                self.assertGreater(profile.peak_dbfs, -8.0)
                self.assertLess(profile.peak_dbfs, -5.0)

    def test_the_same_rate_keeps_the_samples(self):
        source = self.wav("in.wav", sine(4000, 22050), rate=22050)
        result = export_wav(source, self.root / "out.wav", 22050)
        before, after = self.samples(source), self.samples(result.destination)
        self.assertEqual(len(before), len(after))
        self.assertLessEqual(max(abs(a - b) for a, b in zip(before, after)), 1)

    def test_resampling_keeps_pitch_and_level(self):
        source = self.wav("in.wav", sine(8000, 32000, 220.0, 0.5), rate=32000)
        out = self.samples(export_wav(source, self.root / "out.wav", 22050).destination)
        self.assertAlmostEqual(max(out) / 32767, 0.5, delta=0.02)
        crossings = sum(1 for a, b in zip(out, out[1:]) if a < 0 <= b)
        self.assertAlmostEqual(crossings, 55, delta=2)

    def test_opposite_channels_cancel_and_one_channel_halves(self):
        wave_values = sine(2000, 8000, 440.0, 0.8)
        opposite = [v for value in wave_values for v in (value, -value)]
        silent = export_wav(self.wav("a.wav", opposite, 8000, 2), self.root / "a-out.wav", 8000)
        self.assertLessEqual(max(abs(v) for v in self.samples(silent.destination)), 1)
        one_sided = [v for value in wave_values for v in (value, 0.0)]
        half = export_wav(self.wav("b.wav", one_sided, 8000, 2), self.root / "b-out.wav", 8000)
        self.assertAlmostEqual(max(self.samples(half.destination)) / 32767, 0.4, delta=0.01)

    def test_the_result_does_not_depend_on_the_chunk_size(self):
        source = self.wav("in.wav", sine(6001, 32000, 330.0), rate=32000)
        whole = export_wav(source, self.root / "whole.wav", 22050)
        pieces = export_wav(source, self.root / "pieces.wav", 22050, chunk_frames=997)
        self.assertEqual(self.samples(whole.destination), self.samples(pieces.destination))
        self.assertEqual(whole.frames, pieces.frames)

    def test_the_result_reports_the_output(self):
        source = self.wav("in.wav", sine(4410, 44100))
        result = export_wav(source, self.root / "out.wav", 22050)
        self.assertEqual(result.source, source)
        self.assertEqual(result.rate, 22050)
        self.assertAlmostEqual(result.duration, 0.1, places=2)
        self.assertEqual(result.frames, len(self.samples(result.destination)))

    def test_loud_input_is_clamped_not_wrapped(self):
        source = self.wav("in.wav", [1.0, -1.0] * 2000, rate=8000)
        out = self.samples(export_wav(source, self.root / "out.wav", 8000).destination)
        self.assertEqual((max(out), min(out)), (32767, -32767))


class ExportSafetyTests(ExportCase):
    def test_a_replaced_destination_leaves_no_temporary_file(self):
        source = self.wav("in.wav", sine(4000, 8000), rate=8000)
        destination = self.root / "out.wav"
        destination.write_bytes(b"old")
        export_wav(source, destination, 8000)
        self.assertGreater(destination.stat().st_size, 3)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["in.wav", "out.wav"])

    def test_the_source_cannot_be_the_destination(self):
        source = self.wav("in.wav", sine(4000, 8000), rate=8000)
        before = source.read_bytes()
        with self.assertRaises(ExportError):
            export_wav(source, source, 8000)
        self.assertEqual(source.read_bytes(), before)

    def test_a_failed_export_leaves_no_partial_file(self):
        source = self.root / "noise.wav"
        source.write_bytes(b"not audio")
        with self.assertRaises(ExportError):
            export_wav(source, self.root / "out.wav", 22050)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["noise.wav"])

    def test_a_missing_file_is_an_export_error(self):
        with self.assertRaises(ExportError) as caught:
            export_wav(self.root / "missing.wav", self.root / "out.wav", 22050)
        self.assertTrue(caught.exception.fix)

    def test_an_empty_wav_is_an_export_error(self):
        source = self.wav("empty.wav", [], rate=8000)
        with self.assertRaises(ExportError):
            export_wav(source, self.root / "out.wav", 8000)

    def test_a_float_wav_is_an_export_error_naming_the_format(self):
        source = self.root / "float.wav"
        header = (
            b"RIFF" + struct.pack("<I", 44) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 3, 1, 8000, 32000, 4, 32)
            + b"data" + struct.pack("<I", 8) + b"\0" * 8
        )
        source.write_bytes(header)
        with self.assertRaises(ExportError) as caught:
            export_wav(source, self.root / "out.wav", 8000)
        self.assertIn("WAV", caught.exception.what + caught.exception.why)

    def test_the_rate_must_be_in_range(self):
        source = self.wav("in.wav", sine(400, 8000), rate=8000)
        for rate in (MIN_RATE - 1, MAX_RATE + 1, 0, -5, True, 22050.5):
            with self.subTest(rate=rate), self.assertRaises(ConfigurationError):
                export_wav(source, self.root / "out.wav", rate)

    def test_a_truncated_file_exports_the_audio_it_holds(self):
        source = self.wav("in.wav", sine(4000, 8000, 220.0), rate=8000)
        data = source.read_bytes()
        source.write_bytes(data[: 44 + (len(data) - 44) // 2 + 1])
        result = export_wav(source, self.root / "out.wav", 8000)
        self.assertAlmostEqual(result.duration, 0.25, places=2)


if __name__ == "__main__":
    unittest.main()
