import unittest
from pathlib import Path

from ChemBlender.scripts.extract_release_notes import extract_release_notes
from ChemBlender.scripts.release_metadata import read_release_metadata


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.4.0"
FEEDBACK = ROOT / "docs/quantum-visualization/2.4.0/rc1-feedback-review.md"


class StableReleaseReadinessTests(unittest.TestCase):
    def test_production_metadata_and_notes_describe_the_exact_stable_release(self):
        metadata = read_release_metadata(ROOT / "ChemBlender")
        self.assertEqual(VERSION, metadata.version)
        self.assertEqual("chemblender-2.4.0.zip", metadata.package_name)
        self.assertEqual("chemblender-2.4.0.sha256", metadata.checksum_name)
        self.assertEqual(
            "chemblender-2.4.0-windows-x64",
            metadata.artifact_name,
        )

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        notes = extract_release_notes(changelog, VERSION)
        for term in (
            "### Changed",
            "2.4.0-rc.1",
            "Reader API `1.0-rc1`",
            "### Compatibility",
            "Blender 5.1.2",
            "### Known Limitations",
            "### Verification",
        ):
            with self.subTest(term=term):
                self.assertIn(term, notes)
        self.assertIn("## [2.4.0-rc.1] - 2026-08-03", changelog)
        self.assertIn(
            "[Unreleased]: https://github.com/psiQAQ/ChemBlender_2_x/compare/"
            "v2.4.0...HEAD",
            changelog,
        )
        self.assertIn(
            "[2.4.0]: https://github.com/psiQAQ/ChemBlender_2_x/"
            "releases/tag/v2.4.0",
            changelog,
        )
        self.assertIn(
            "[2.4.0-rc.1]: https://github.com/psiQAQ/ChemBlender_2_x/"
            "releases/tag/v2.4.0-rc.1",
            changelog,
        )

    def test_feedback_review_records_exact_published_rc_evidence(self):
        self.assertTrue(FEEDBACK.is_file(), FEEDBACK)
        feedback = FEEDBACK.read_text(encoding="utf-8")
        for term in (
            "State: `Passed`",
            "`v2.4.0-rc.1`",
            "`472775cd4e0652ee5c0c6e9507aee8a29230acba`",
            "`30770885098`",
            "`30771253311`",
            "`30772029322`",
            "`cae3b9d6bc8928c866cfec079ff1b4dab816d3e4803275f679706141c92e08f4`",
            "`99edee2c2f34049e9b36735056b1a4a1fb56673a1152789bf6d1360bf5f65192`",
            "Issues: `Disabled`",
            "Discussions: `Disabled`",
            "Open pull requests: `0`",
            "Release blockers: `None reported`",
        ):
            with self.subTest(term=term):
                self.assertIn(term, feedback)


if __name__ == "__main__":
    unittest.main()
