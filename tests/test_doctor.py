import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from muse.cli import main
from muse.config import MuseConfig
from muse.doctor import run_checks
from muse.errors import ConfigurationError


class DoctorTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.output = self.root / "out"

    def config(self, **changes):
        values = {"output_dir": self.output, "provider": "mock", "judge": "mock", "env": {}}
        values.update(changes)
        return MuseConfig(**values)

    def checks(self, config):
        return {check.name: check for check in run_checks(config)}

    def test_mock_configuration_is_healthy(self):
        checks = self.checks(self.config())
        self.assertTrue(checks["python"].ok)
        self.assertTrue(checks["output"].ok)
        self.assertTrue(checks["provider"].ok)
        self.assertTrue(checks["judge"].ok)
        self.assertNotIn("REPLICATE_API_TOKEN", checks)
        self.assertNotIn("GEMINI_API_KEY", checks)

    def test_required_keys_are_reported(self):
        checks = self.checks(
            self.config(provider="replicate", judge="gemini")
        )
        self.assertFalse(checks["REPLICATE_API_TOKEN"].ok)
        self.assertFalse(checks["GEMINI_API_KEY"].ok)
        self.assertIn("REPLICATE_API_TOKEN", checks["REPLICATE_API_TOKEN"].detail)
        self.assertIn("GEMINI_API_KEY", checks["GEMINI_API_KEY"].detail)
        self.assertTrue(checks["REPLICATE_API_TOKEN"].fix)

    def test_output_file_is_reported(self):
        blocker = self.root / "blocker"
        blocker.write_text("file", encoding="utf-8")
        checks = self.checks(self.config(output_dir=blocker))
        self.assertFalse(checks["output"].ok)
        self.assertIn("blocker", checks["output"].detail)

    def test_unknown_adapter_names_are_reported(self):
        checks = self.checks(self.config(provider="sun", judge="ears"))
        self.assertFalse(checks["provider"].ok)
        self.assertFalse(checks["judge"].ok)
        self.assertIn("sun", checks["provider"].detail)
        self.assertIn("ears", checks["judge"].detail)

    def test_invalid_configuration_is_a_single_finding(self):
        failure = ConfigurationError("bad timeout", "nan", "set a number")
        with patch("muse.doctor.MuseConfig.from_env", side_effect=failure):
            checks = run_checks(None)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].name, "configuration")
        self.assertFalse(checks[0].ok)
        self.assertEqual(checks[0].fix, "set a number")


class DoctorCliTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.output = self.root / "out"

    def run_cli(self, argv, config):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv, config=config)
        return code, out.getvalue(), err.getvalue()

    def test_doctor_json_healthy(self):
        config = MuseConfig(output_dir=self.output, provider="mock", judge="mock", env={})
        code, out, err = self.run_cli(["doctor", "--json"], config)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertIn("checks", payload)
        self.assertTrue(any(check["name"] == "python" for check in payload["checks"]))
        self.assertTrue(all("fix" not in check for check in payload["checks"]))

    def test_doctor_cli_overrides_the_environment(self):
        config = MuseConfig(output_dir=self.output, provider="replicate", judge="gemini", env={})
        code, out, err = self.run_cli(
            ["doctor", "--provider", "mock", "--judge", "mock", "--json"],
            config,
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["ok"])

    def test_doctor_reports_missing_keys(self):
        config = MuseConfig(output_dir=self.output, provider="replicate", judge="gemini", env={})
        code, out, err = self.run_cli(["doctor"], config)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)
        self.assertIn("GEMINI_API_KEY", out)
        self.assertIn("Fix:", out)
        self.assertNotIn("secret", out)

    def test_doctor_reports_output_file(self):
        blocker = self.root / "blocker"
        blocker.write_text("file", encoding="utf-8")
        config = MuseConfig(output_dir=blocker, provider="mock", judge="mock", env={})
        code, out, err = self.run_cli(["doctor", "--json"], config)
        self.assertEqual(code, 1, err)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        output = next(check for check in payload["checks"] if check["name"] == "output")
        self.assertFalse(output["ok"])
