"""Sample-rate conversion: an anti-alias filter when downsampling, exact whatever the chunking."""

import math
import tempfile
import unittest
import wave
from pathlib import Path

from muse.analysis import analyze_audio
from muse.export import export_wav
from muse.resample import (
    CUTOFF,
    _dot_fallback,
    lowpass_kernel,
    resample_chunks,
    tap_count,
)

TARGET = 22050
SOURCES = (32000, 44100, 48000, 96000)


def response_db(kernel, source_rate, hertz, fraction):
    """Gain of one polyphase kernel at `hertz`, for taps placed around `fraction` past a sample."""
    half = len(kernel) // 2
    real = imag = 0.0
    for index, coefficient in enumerate(kernel):
        angle = 2 * math.pi * hertz / source_rate * (index - half + 1 - fraction)
        real += coefficient * math.cos(angle)
        imag += coefficient * math.sin(angle)
    return 20 * math.log10(max(1e-9, math.hypot(real, imag)))


def collect(chunks):
    return [value for block in chunks for value in block]


def split(values, size):
    return [values[start : start + size] for start in range(0, len(values), size)]


def expected_frames(count, source, target):
    """Outputs whose source position leaves at least one later sample, as the exporter promises."""
    return ((count - 1) * target - 1) // source + 1


class KernelTests(unittest.TestCase):
    def test_the_tap_count_grows_with_the_rate_ratio_and_stays_even(self):
        counts = [tap_count(rate, TARGET) for rate in SOURCES]
        self.assertEqual(counts, sorted(counts))
        for count in counts:
            self.assertEqual(count % 2, 0)

    def test_every_kernel_has_unit_gain_at_zero_hertz(self):
        for fraction in (0.0, 0.25, 0.5, 0.99):
            with self.subTest(fraction=fraction):
                kernel = lowpass_kernel(tap_count(44100, TARGET), CUTOFF * TARGET / 44100, fraction)
                self.assertAlmostEqual(sum(kernel), 1.0, places=9)

    def test_the_filter_is_flat_in_the_band_and_rejects_the_alias_band(self):
        for source in SOURCES:
            taps = tap_count(source, TARGET)
            for fraction in (0.0, 0.5):
                kernel = lowpass_kernel(taps, CUTOFF * TARGET / source, fraction)
                with self.subTest(source=source, fraction=fraction):
                    self.assertGreater(response_db(kernel, source, 0.40 * TARGET, fraction), -0.5)
                    self.assertGreater(response_db(kernel, source, 0.05 * TARGET, fraction), -0.5)
                    nyquist = 0.5 * source
                    hertz = 0.5 * TARGET
                    while hertz <= nyquist:
                        self.assertLess(response_db(kernel, source, hertz, fraction), -45.0, hertz)
                        hertz += (nyquist - 0.5 * TARGET) / 12 + 1e-9

    def test_the_fallback_dot_product_matches_the_builtin(self):
        first, second = [0.5, -1.25, 3.0, 0.125], [2.0, 4.0, -0.5, 8.0]
        self.assertAlmostEqual(_dot_fallback(first, second), sum(a * b for a, b in zip(first, second)))


class StreamTests(unittest.TestCase):
    def signal(self, count, source, hertz, amplitude=0.5):
        return [amplitude * math.sin(2 * math.pi * hertz * index / source) for index in range(count)]

    def test_equal_rates_pass_the_chunks_through(self):
        chunks = [[0.1, 0.2], [0.3]]
        self.assertEqual(collect(resample_chunks(iter(chunks), 8000, 8000)), [0.1, 0.2, 0.3])

    def test_the_output_does_not_depend_on_the_chunk_size(self):
        values = self.signal(1200, 32000, 440.0)
        whole = collect(resample_chunks(iter([values]), 32000, TARGET))
        for size in (1, 7, 64, 999):
            with self.subTest(size=size):
                pieces = collect(resample_chunks(iter(split(values, size)), 32000, TARGET))
                self.assertEqual(pieces, whole)

    def test_the_output_length_matches_the_promised_count(self):
        for source, target in ((32000, TARGET), (44100, TARGET), (22050, 44100), (48000, 8000)):
            values = self.signal(2500, source, 300.0)
            with self.subTest(source=source, target=target):
                out = collect(resample_chunks(iter(split(values, 333)), source, target))
                self.assertEqual(len(out), expected_frames(len(values), source, target))

    def test_a_single_sample_produces_nothing(self):
        self.assertEqual(collect(resample_chunks(iter([[0.5]]), 32000, TARGET)), [])

    def test_a_tone_below_the_cutoff_keeps_its_level(self):
        values = self.signal(3200, 32000, 5000.0)
        out = collect(resample_chunks(iter([values]), 32000, TARGET))
        steady = out[100:-100]
        self.assertAlmostEqual(max(abs(v) for v in steady), 0.5, delta=0.01)

    def test_tones_above_the_target_nyquist_are_removed_not_folded(self):
        for source, hertz in ((32000, 12000.0), (32000, 14000.0), (44100, 15000.0), (96000, 30000.0)):
            values = self.signal(2400, source, hertz)
            out = collect(resample_chunks(iter([values]), source, TARGET))
            level = 20 * math.log10(max(abs(v) for v in out[150:-150]) / 0.5)
            with self.subTest(source=source, hertz=hertz):
                self.assertLess(level, -45.0)

    def test_upsampling_still_interpolates_linearly(self):
        values = self.signal(500, 8000, 440.0)
        out = collect(resample_chunks(iter([values]), 8000, TARGET))
        self.assertEqual(len(out), expected_frames(500, 8000, TARGET))
        self.assertAlmostEqual(max(abs(v) for v in out), 0.5, delta=0.01)

    def test_a_target_with_many_phases_uses_a_bounded_table_and_stays_accurate(self):
        values = self.signal(4000, 32000, 1000.0)
        out = collect(resample_chunks(iter([values]), 32000, 22051))
        crossings = sum(1 for a, b in zip(out, out[1:]) if a < 0 <= b)
        self.assertAlmostEqual(crossings, 1000 * len(out) / 22051, delta=1.5)
        self.assertAlmostEqual(max(abs(v) for v in out[100:-100]), 0.5, delta=0.01)


class ExportFilterTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def tone(self, name, rate, hertz, count=6000):
        import struct

        path = self.root / name
        data = struct.pack(
            f"<{count}h",
            *(int(16383 * math.sin(2 * math.pi * hertz * i / rate)) for i in range(count)),
        )
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(data)
        return path

    def steady_peak_dbfs(self, path, edge=300):
        """Peak level of the middle of a file, away from the onset and release of the tone."""
        import struct

        with wave.open(str(path), "rb") as handle:
            data = handle.readframes(handle.getnframes())
        samples = struct.unpack(f"<{len(data) // 2}h", data)[edge:-edge]
        return 20 * math.log10(max(1, max(abs(value) for value in samples)) / 32767)

    def test_an_exported_high_tone_no_longer_aliases(self):
        result = export_wav(self.tone("hi.wav", 44100, 15000.0), self.root / "out.wav", TARGET)
        self.assertLess(self.steady_peak_dbfs(result.destination), -45.0)

    def test_an_exported_low_tone_keeps_its_level(self):
        result = export_wav(self.tone("lo.wav", 44100, 3000.0), self.root / "out.wav", TARGET)
        profile, _ = analyze_audio(result.destination)
        self.assertAlmostEqual(profile.peak_dbfs, -6.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()
