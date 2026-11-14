"""Agent documentation: the contract names every command and stays short."""

import re
import unittest
from pathlib import Path

from muse.analysis import REQUIREMENT_KEYS
from muse.cli import build_parser

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS = REPO_ROOT / "AGENTS.md"
README = REPO_ROOT / "README.md"


def agents_text() -> str:
    return AGENTS.read_text(encoding="utf-8").replace("\r\n", "\n")


def readme_text() -> str:
    return README.read_text(encoding="utf-8").replace("\r\n", "\n")


class AgentContractTests(unittest.TestCase):
    def test_contract_names_every_subcommand(self):
        help_text = build_parser().format_help()
        match = re.search(r"\{([a-z,]+)\}", help_text)
        self.assertIsNotNone(match, "the parser help lists its subcommands")
        commands = match.group(1).split(",")
        text = agents_text()
        for command in commands:
            with self.subTest(command=command):
                self.assertIn(f"`{command}", text)

    def test_contract_states_the_output_and_exit_codes(self):
        text = agents_text()
        self.assertIn("--json", text)
        for code in ("`0`", "`1`", "`2`"):
            self.assertIn(code, text)
        self.assertIn("prints its one JSON object", " ".join(text.split()))

    def test_contract_names_the_offline_adapters_and_keys(self):
        text = agents_text()
        self.assertIn("--provider mock --judge mock", text)
        self.assertIn("REPLICATE_API_TOKEN", text)
        self.assertIn("GEMINI_API_KEY", text)

    def test_readme_links_the_contract(self):
        self.assertIn("[AGENTS.md](AGENTS.md)", readme_text())

    def test_readme_documents_every_requirement_key(self):
        text = readme_text()
        for key in REQUIREMENT_KEYS:
            with self.subTest(key=key):
                self.assertIn(f"`{key}`", text.replace('"' + key + '"', f"`{key}`"))

    def test_readme_export_example_analyzes_the_exported_file(self):
        section = readme_text().split("### Exporting for an engine", 1)[1].split("\n## ", 1)[0]
        commands = [line for line in section.splitlines() if line.startswith("python -m muse analyze")]
        self.assertTrue(commands, "the export section shows how to check the exported file")
        for command in commands:
            self.assertIn("-22050hz.wav", command, "analyze the exported file, not the artifact folder")

    def test_contract_stays_a_single_screen(self):
        lines = agents_text().splitlines()
        self.assertLessEqual(len(lines), 120, "the agent contract must stay short enough to load whole")


if __name__ == "__main__":
    unittest.main()
