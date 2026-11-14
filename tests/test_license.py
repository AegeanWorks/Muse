"""License documents: resolvable pointers, current operative text and mirror identity."""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LICENSE = REPO_ROOT / "LICENSE"
MIRROR = REPO_ROOT / "LICENSES" / "LicenseRef-AL-1.1.txt"
CLA_URL = ("https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/"
           "CONTRIBUTING_CLA.md")
ACL_URL = ("https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/"
           "ACL-1.0.md")
RELATIVE_SIBLING = re.compile(r"`licenses/")


def document_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


class LicenseDocumentTests(unittest.TestCase):
    def test_sibling_documents_are_referenced_by_url(self):
        text = document_text(LICENSE)
        self.assertIn(CLA_URL, text)
        self.assertIn(ACL_URL, text)
        self.assertIsNone(RELATIVE_SIBLING.search(text))

    def test_mirror_matches_the_license(self):
        self.assertEqual(document_text(LICENSE), document_text(MIRROR))

    def test_operative_text_carries_the_current_compatibility_wording(self):
        self.assertIn("not compatible with copyleft licenses that would",
                      document_text(LICENSE))

    def test_reuse_and_package_metadata_agree_on_the_license(self):
        self.assertIn('SPDX-License-Identifier = "LicenseRef-AL-1.1"',
                      (REPO_ROOT / "REUSE.toml").read_text(encoding="utf-8"))
        self.assertIn('license = "LicenseRef-AL-1.1"',
                      (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
