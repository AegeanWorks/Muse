import unittest

from muse import MusicRequest
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
