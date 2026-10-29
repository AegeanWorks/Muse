import math
import unittest
from pathlib import Path

from muse import MusicRequest, __version__
from muse.config import ConfigurationError, MuseConfig
from muse.types import MAX_DURATION, VERDICT_FITS, Verdict


class MusicRequestTests(unittest.TestCase):
    def test_theme_defaults_to_prompt_intent(self):
        request = MusicRequest("  dark cave  ")
        self.assertEqual(request.prompt, "dark cave")
        self.assertEqual(request.intent, "dark cave")

    def test_theme_wins_as_intent(self):
        request = MusicRequest("synths", theme="  boss fight  ")
        self.assertEqual(request.intent, "boss fight")

    def test_empty_prompt_is_rejected(self):
        with self.assertRaises(ValueError):
            MusicRequest("   ")

    def test_duration_bounds(self):
        for duration in (0, -1, MAX_DURATION + 1):
            with self.assertRaises(ValueError):
                MusicRequest("x", duration=duration)

    def test_text_fields_must_be_strings(self):
        for field in ("prompt", "theme", "name"):
            values = {"prompt": "x", field: 123}
            with self.assertRaises(ValueError) as caught:
                MusicRequest(**values)
            self.assertIn(field, str(caught.exception))
        with self.assertRaises(ValueError):
            MusicRequest("x", theme=None)
        with self.assertRaises(ValueError):
            MusicRequest("x", extra=[])

    def test_duration_must_be_a_finite_number(self):
        for duration in (True, False, "30", None, math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                MusicRequest("x", duration=duration)

    def test_duration_is_stored_as_float(self):
        request = MusicRequest("x", duration=1)
        self.assertIsInstance(request.duration, float)
        self.assertEqual(request.duration, 1.0)

    def test_label_prefers_name_then_theme(self):
        self.assertEqual(MusicRequest("x", name="Intro", theme="menu").label, "Intro")
        self.assertEqual(MusicRequest("x", theme="menu").label, "menu")


class VerdictTests(unittest.TestCase):
    def test_accepts_at_threshold(self):
        verdict = Verdict(60, VERDICT_FITS, "ok", (), (), (), "mock", "m", 60)
        self.assertTrue(verdict.accepted)

    def test_rejects_below_threshold(self):
        verdict = Verdict(59, VERDICT_FITS, "ok", (), (), (), "mock", "m", 60)
        self.assertFalse(verdict.accepted)

    def test_invalid_values_are_rejected(self):
        for score in (-1, 101, True, 84.0):
            with self.assertRaises(ValueError):
                Verdict(score, VERDICT_FITS, "ok", (), (), (), "mock", "m", 60)
        with self.assertRaises(ValueError):
            Verdict(84, "great", "ok", (), (), (), "mock", "m", 60)
        with self.assertRaises(ValueError):
            Verdict(84, VERDICT_FITS, "ok", (), (), (), "mock", "m", 101)
        with self.assertRaises(ValueError):
            Verdict(84, VERDICT_FITS, None, (), (), (), "mock", "m", 60)

    def test_sequences_are_normalized_and_validated(self):
        verdict = Verdict(
            84,
            VERDICT_FITS,
            "ok",
            ["low register"],
            ("slow pulse",),
            ["add strings"],
            "mock",
            "m",
            60,
        )
        self.assertEqual(verdict.strengths, ("low register",))
        self.assertEqual(verdict.issues, ("slow pulse",))
        self.assertEqual(verdict.suggestions, ("add strings",))
        for bad in ("abc", [1], None):
            with self.assertRaises(ValueError):
                Verdict(84, VERDICT_FITS, "ok", bad, (), (), "mock", "m", 60)
        with self.assertRaises(ValueError):
            Verdict(84, VERDICT_FITS, "ok", (), (), (), 1, "m", 60)
        with self.assertRaises(ValueError):
            Verdict(84, VERDICT_FITS, "ok", (), (), (), "mock", None, 60)


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        config = MuseConfig.from_env({})
        self.assertEqual(config.provider, "replicate")
        self.assertEqual(config.judge, "gemini")
        self.assertEqual(config.min_score, 60)
        self.assertEqual(config.output_dir.name, "output")

    def test_environment_overrides(self):
        config = MuseConfig.from_env(
            {
                "MUSE_OUTPUT_DIR": "art",
                "MUSE_PROVIDER": "mock",
                "MUSE_JUDGE": "none",
                "MUSE_MIN_SCORE": "75",
                "MUSE_HTTP_TIMEOUT": "9.5",
            }
        )
        self.assertEqual(config.output_dir.name, "art")
        self.assertEqual(config.provider, "mock")
        self.assertEqual(config.judge, "none")
        self.assertEqual(config.min_score, 75)
        self.assertEqual(config.http_timeout, 9.5)

    def test_empty_environment_values_fall_back_to_defaults(self):
        config = MuseConfig.from_env(
            {
                "MUSE_OUTPUT_DIR": "",
                "MUSE_PROVIDER": "",
                "MUSE_JUDGE": "",
                "MUSE_MUSIC_MODEL": "",
                "MUSE_JUDGE_MODEL": "",
            }
        )
        self.assertEqual(config.output_dir, Path("output"))
        self.assertEqual(config.provider, "replicate")
        self.assertEqual(config.judge, "gemini")
        self.assertEqual(config.music_model, "stability-ai/stable-audio-2.5")
        self.assertEqual(config.judge_model, "gemini-2.5-flash")

    def test_environment_text_is_trimmed_and_expanded(self):
        config = MuseConfig.from_env(
            {
                "MUSE_OUTPUT_DIR": " ~/muse-art ",
                "MUSE_PROVIDER": " mock ",
                "MUSE_JUDGE": " mock ",
                "MUSE_MUSIC_MODEL": " meta/musicgen ",
                "MUSE_JUDGE_MODEL": " gemini-2.5-pro ",
                "MUSE_REPLICATE_VERSION": "  ",
            }
        )
        self.assertEqual(config.output_dir, Path("~/muse-art").expanduser())
        self.assertEqual(config.provider, "mock")
        self.assertEqual(config.judge, "mock")
        self.assertEqual(config.music_model, "meta/musicgen")
        self.assertEqual(config.judge_model, "gemini-2.5-pro")
        self.assertIsNone(config.replicate_version)

    def test_invalid_number_is_a_configuration_error(self):
        with self.assertRaises(ConfigurationError):
            MuseConfig.from_env({"MUSE_MIN_SCORE": "high"})

    def test_threshold_outside_percent_is_rejected(self):
        for score in (-1, 101):
            with self.assertRaises(ConfigurationError):
                MuseConfig(min_score=score)

    def test_non_positive_timeouts_are_rejected(self):
        with self.assertRaises(ConfigurationError):
            MuseConfig(http_timeout=0)
        with self.assertRaises(ConfigurationError):
            MuseConfig(poll_timeout=0)

    def test_non_finite_or_wrongly_typed_values_are_rejected(self):
        for value in (True, "60", 60.5):
            with self.assertRaises(ConfigurationError):
                MuseConfig(min_score=value)
        for value in (math.nan, math.inf, "120", True):
            with self.assertRaises(ConfigurationError):
                MuseConfig(http_timeout=value)
            with self.assertRaises(ConfigurationError):
                MuseConfig(poll_timeout=value)

    def test_output_dir_accepts_a_string(self):
        config = MuseConfig(output_dir="art")
        self.assertIsInstance(config.output_dir, Path)
        self.assertEqual(config.output_dir.name, "art")

    def test_missing_tokens_are_explained(self):
        config = MuseConfig.from_env({})
        with self.assertRaises(ConfigurationError) as replicate:
            config.replicate_token()
        self.assertIn("REPLICATE_API_TOKEN", replicate.exception.what)
        with self.assertRaises(ConfigurationError) as gemini:
            config.gemini_key()
        self.assertIn("GEMINI_API_KEY", gemini.exception.what)

    def test_tokens_are_not_in_repr(self):
        config = MuseConfig.from_env({"REPLICATE_API_TOKEN": "super-secret"})
        self.assertNotIn("super-secret", repr(config))
        self.assertEqual(config.replicate_token(), "super-secret")


class PackagingTests(unittest.TestCase):
    def test_pyproject_version_matches_the_module(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{__version__}"', text)
