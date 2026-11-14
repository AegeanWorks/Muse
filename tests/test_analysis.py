"""Requirement analysis: profiles, validated limits and the analyze command."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from muse.analysis import (
    analyze_audio,
    evaluate,
    load_requirements,
    requirement_fit,
    requirements_from_mapping,
)
from muse.audio import write_tone
from muse.cli import main
from muse.config import MuseConfig


def run_cli(arguments):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(arguments)
    return code, out.getvalue(), err.getvalue()


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.settings = MuseConfig(output_dir=self.root)

    def tone(self, name="track.wav", seconds=2.0, rate=8000):
        path = self.root / name
        write_tone(path, seconds, rate)
        return path

    def requirements(self, payload, name="requirements.json"):
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


class ProfileTests(Workspace):
    def test_profile_measures_a_mock_tone(self):
        profile, reason = analyze_audio(self.tone())
        self.assertEqual(reason, "")
        self.assertIsNotNone(profile)
        self.assertAlmostEqual(profile.duration, 2.0, places=2)
        self.assertEqual(profile.sample_rate, 8000)
        self.assertEqual(profile.channels, 1)
        self.assertEqual(profile.sample_width, 2)
        self.assertLess(profile.peak_dbfs, 0)
        self.assertLess(profile.rms_dbfs, profile.peak_dbfs)
        self.assertEqual(profile.clipped_percent, 0.0)
        self.assertGreater(profile.size_bytes, 0)

    def test_a_truncated_file_reports_the_audio_it_holds(self):
        path = self.tone(seconds=10.0)
        data = path.read_bytes()
        path.write_bytes(data[: 44 + (len(data) - 44) // 10])
        profile, reason = analyze_audio(path)
        self.assertEqual(reason, "")
        self.assertAlmostEqual(profile.duration, 1.0, places=1)

    def test_a_file_cut_mid_sample_is_still_profiled(self):
        path = self.tone(seconds=10.0)
        data = path.read_bytes()
        path.write_bytes(data[: 44 + (len(data) - 44) // 10 + 1])
        profile, reason = analyze_audio(path)
        self.assertEqual(reason, "")
        self.assertAlmostEqual(profile.duration, 1.0, places=1)

    def test_a_truncated_file_fails_the_minimum_duration(self):
        path = self.tone(seconds=10.0)
        data = path.read_bytes()
        path.write_bytes(data[: 44 + (len(data) - 44) // 10])
        profile, reason = analyze_audio(path)
        result = evaluate(profile, requirements_from_mapping({"min_duration": 9}), None, reason)
        self.assertFalse(result["ok"])

    def test_a_non_wav_file_is_reported_not_crashed(self):
        path = self.root / "noise.mp3"
        path.write_bytes(b"not audio")
        profile, reason = analyze_audio(path)
        self.assertIsNone(profile)
        self.assertIn("could not be decoded", reason)

    def test_a_missing_file_is_reported(self):
        profile, reason = analyze_audio(self.root / "missing.wav")
        self.assertIsNone(profile)
        self.assertIn("could not be read", reason)


class RequirementParsingTests(Workspace):
    def test_a_full_document_round_trips(self):
        payload = {
            "min_duration": 28,
            "max_duration": 32,
            "min_sample_rate": 22050,
            "channels": [1, 2],
            "sample_width_bits": [16, 24],
            "min_rms_dbfs": -30,
            "max_peak_dbfs": -1,
            "max_size_mb": 25,
            "require_accepted": True,
            "min_score": 60,
        }
        requirements = requirements_from_mapping(payload)
        self.assertEqual(requirements.as_dict()["min_duration"], 28.0)
        self.assertEqual(requirements.channels, (1, 2))
        self.assertEqual(requirements.sample_width_bits, (16, 24))
        self.assertTrue(requirements.require_accepted)

    def test_a_single_channel_count_is_accepted(self):
        self.assertEqual(requirements_from_mapping({"channels": 2}).channels, (2,))

    def test_a_single_bit_depth_is_accepted(self):
        self.assertEqual(
            requirements_from_mapping({"sample_width_bits": 16}).sample_width_bits, (16,)
        )

    def test_an_unsupported_bit_depth_is_rejected(self):
        for payload in ({"sample_width_bits": 12}, {"sample_width_bits": [16, 20]},
                        {"sample_width_bits": []}, {"sample_width_bits": True}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                requirements_from_mapping(payload)

    def test_an_empty_or_unknown_document_is_rejected(self):
        with self.assertRaises(ValueError):
            requirements_from_mapping({})
        with self.assertRaises(ValueError) as caught:
            requirements_from_mapping({"min_duration": 1, "loud": True})
        self.assertIn("unknown requirement", str(caught.exception))

    def test_bad_values_are_rejected(self):
        for payload in (
            {"min_duration": 0},
            {"min_duration": 10, "max_duration": 5},
            {"min_sample_rate": 0},
            {"min_sample_rate": True},
            {"channels": []},
            {"channels": [0]},
            {"min_rms_dbfs": 1},
            {"max_peak_dbfs": "loud"},
            {"max_size_mb": -1},
            {"require_accepted": "yes"},
            {"require_accepted": False},
            {"min_score": 101},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                requirements_from_mapping(payload)

    def test_a_requirements_file_is_read_with_utf8_bom(self):
        path = self.root / "bom.json"
        path.write_bytes("\ufeff{\"min_duration\": 1}".encode("utf-8"))
        self.assertEqual(load_requirements(path).min_duration, 1.0)


class EvaluateTests(Workspace):
    def setUp(self):
        super().setUp()
        self.profile, _ = analyze_audio(self.tone())

    def test_every_limit_passes_on_a_matching_track(self):
        requirements = requirements_from_mapping(
            {
                "min_duration": 1,
                "max_duration": 5,
                "min_sample_rate": 8000,
                "channels": [1, 2],
                "sample_width_bits": [16],
                "min_rms_dbfs": -60,
                "max_peak_dbfs": -0.1,
                "max_size_mb": 1,
            }
        )
        result = evaluate(self.profile, requirements, None)
        self.assertTrue(result["ok"])
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["skipped"], [])

    def test_a_failed_limit_says_which_one(self):
        requirements = requirements_from_mapping({"min_duration": 10})
        result = evaluate(self.profile, requirements, None)
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed"], ["min_duration"])

    def test_a_bit_depth_limit_fails_with_the_measured_width(self):
        requirements = requirements_from_mapping({"sample_width_bits": [8, 24]})
        result = evaluate(self.profile, requirements, None)
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed"], ["sample_width_bits"])
        check = next(item for item in result["checks"] if item["check"] == "sample_width_bits")
        self.assertEqual(check["actual"], 16)

    def test_missing_audio_skips_but_does_not_fail(self):
        requirements = requirements_from_mapping({"min_duration": 1, "max_peak_dbfs": -1})
        result = evaluate(None, requirements, None, "not decodable")
        self.assertTrue(result["ok"])
        self.assertEqual(result["skipped"], ["min_duration", "max_peak_dbfs"])

    def test_judge_limits_use_available_evidence(self):
        requirements = requirements_from_mapping({"require_accepted": True, "min_score": 60})
        accepted = evaluate(self.profile, requirements, {"accepted": True, "score": 88})
        self.assertTrue(accepted["ok"])
        rejected = evaluate(self.profile, requirements, {"accepted": False, "score": 45})
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["failed"], ["require_accepted", "min_score"])

    def test_judge_limits_are_skipped_without_evidence(self):
        requirements = requirements_from_mapping({"require_accepted": True, "min_score": 60})
        result = evaluate(self.profile, requirements, None)
        self.assertTrue(result["ok"])
        self.assertEqual(result["skipped"], ["require_accepted", "min_score"])


class RequirementFitTests(Workspace):
    def setUp(self):
        super().setUp()
        self.profile, _ = analyze_audio(self.tone())

    def fit(self, limits):
        return requirement_fit(evaluate(self.profile, requirements_from_mapping(limits), None))

    def test_a_track_that_meets_every_limit_fits(self):
        result = self.fit({"min_duration": 1, "max_peak_dbfs": -0.1})
        self.assertTrue(result.ok)
        self.assertEqual(result.failed, ())
        self.assertEqual(result.hints, ())

    def test_a_short_track_gets_a_duration_hint(self):
        result = self.fit({"min_duration": 10})
        self.assertFalse(result.ok)
        self.assertEqual(result.failed, ("min_duration",))
        self.assertEqual(len(result.hints), 1)
        self.assertIn("at least 10", result.hints[0])
        self.assertIn("2.0", result.hints[0])

    def test_a_long_track_gets_a_duration_hint(self):
        result = self.fit({"max_duration": 1})
        self.assertEqual(result.failed, ("max_duration",))
        self.assertIn("under 1", result.hints[0])

    def test_loudness_and_format_misses_give_no_hint(self):
        result = self.fit({"min_rms_dbfs": -1, "min_sample_rate": 44100, "channels": [2]})
        self.assertFalse(result.ok)
        self.assertEqual(set(result.failed), {"min_rms_dbfs", "min_sample_rate", "channels"})
        self.assertEqual(result.hints, ())

    def test_skipped_checks_do_not_make_a_track_unfit(self):
        result = requirement_fit(
            evaluate(None, requirements_from_mapping({"min_duration": 10}), None, "not a WAV")
        )
        self.assertTrue(result.ok)

class AnalyzeCommandTests(Workspace):
    def setUp(self):
        super().setUp()
        code, out, err = run_cli(
            [
                "generate", "dark cave drones", "--theme", "cave level", "--duration", "2",
                "--provider", "mock", "--judge", "mock", "--out", str(self.root), "--json",
            ]
        )
        self.assertEqual(code, 0, err)
        self.artifact = json.loads(out)["metadata"]
        self.folder = Path(self.artifact).parent

    def test_matching_requirements_pass_and_exit_zero(self):
        requirements = self.requirements(
            {"min_duration": 1, "max_duration": 5, "min_sample_rate": 8000, "min_score": 60}
        )
        code, out, _ = run_cli(
            [
                "analyze", str(self.folder), "--requirements", str(requirements),
                "--out", str(self.root), "--json",
            ]
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["passed"], 1)
        self.assertTrue(payload["artifacts"][0]["checks"])

    def test_a_failed_limit_exits_one_and_names_it(self):
        requirements = self.requirements({"min_duration": 10})
        code, out, _ = run_cli(
            [
                "analyze", str(self.folder), "--requirements", str(requirements),
                "--out", str(self.root), "--json",
            ]
        )
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["artifacts"][0]["failed"], ["min_duration"])

    def test_a_bare_audio_file_runs_technical_checks_without_evidence(self):
        requirements = self.requirements({"max_peak_dbfs": -0.1})
        loose = self.root / "loose.wav"
        loose.write_bytes((self.folder / "track.wav").read_bytes())
        code, out, _ = run_cli(
            [
                "analyze", str(loose), "--requirements", str(requirements),
                "--out", str(self.root), "--json",
            ]
        )
        self.assertEqual(code, 0)
        artifact = json.loads(out)["artifacts"][0]
        self.assertIsNone(artifact["metadata"])
        self.assertIsNone(artifact["evidence"])

    def test_a_duplicate_argument_is_analyzed_once(self):
        requirements = self.requirements({"min_duration": 1})
        code, out, _ = run_cli(
            [
                "analyze", str(self.folder), str(self.folder), "--requirements", str(requirements),
                "--out", str(self.root), "--json",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["total"], 1)

    def test_a_named_audio_file_beats_foreign_sibling_evidence(self):
        other = self.root / "other-artifact"
        other.mkdir()
        write_tone(other / "theme.wav", 1.0)
        write_tone(other / "track.wav", 5.0)
        payload = {
            "schema": 2,
            "created_at": "2026-01-01T00:00:00+00:00",
            "request": {"prompt": "p", "theme": "t", "duration": 1, "name": "other-artifact"},
            "track": {"file": "theme.wav", "provider": "mock", "model": "m", "duration_seconds": 1},
            "verdict": {"score": 88, "verdict": "fits", "threshold": 60},
            "accepted": True,
        }
        (other / "muse.json").write_text(json.dumps(payload), encoding="utf-8")
        requirements = self.requirements({"max_duration": 2})
        code, out, _ = run_cli(
            [
                "analyze", str(other / "track.wav"), "--requirements", str(requirements),
                "--out", str(self.root), "--json",
            ]
        )
        self.assertEqual(code, 1)
        artifact = json.loads(out)["artifacts"][0]
        self.assertEqual(Path(artifact["audio"]).name, "track.wav")
        self.assertIsNone(artifact["evidence"])
        self.assertEqual(artifact["failed"], ["max_duration"])

    def test_an_audio_file_inside_an_artifact_folder_uses_its_evidence(self):
        requirements = self.requirements({"min_score": 60})
        audio = self.folder / "track.wav"
        code, out, _ = run_cli(
            [
                "analyze", str(audio), "--requirements", str(requirements),
                "--out", str(self.root), "--json",
            ]
        )
        self.assertEqual(code, 0)
        artifact = json.loads(out)["artifacts"][0]
        self.assertIsNotNone(artifact["metadata"])
        self.assertTrue(artifact["evidence"]["accepted"])

    def test_an_invalid_requirements_file_is_usage_misuse(self):
        requirements = self.requirements({"min_duration": 0})
        code, out, err = run_cli(
            ["analyze", str(self.folder), "--requirements", str(requirements), "--json"]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("Why:", err)
        self.assertIn("Fix:", err)

    def test_a_missing_artifact_is_an_operational_error(self):
        requirements = self.requirements({"min_duration": 1})
        code, out, err = run_cli(
            ["analyze", str(self.root / "nope"), "--requirements", str(requirements), "--json"]
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("artifact not found", err)

    def test_human_output_reports_failures(self):
        requirements = self.requirements({"min_duration": 10})
        code, out, _ = run_cli(
            ["analyze", str(self.folder), "--requirements", str(requirements), "--out", str(self.root)]
        )
        self.assertEqual(code, 1)
        self.assertIn("[FAIL]", out)
        self.assertIn("min_duration", out)
        self.assertIn("Summary: 0/1", out)


if __name__ == "__main__":
    unittest.main()
