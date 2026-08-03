import unittest
from pathlib import Path

from ChemBlender.scripts.extract_release_notes import extract_release_notes
from ChemBlender.scripts.release_metadata import read_release_metadata


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.4.0"
FEEDBACK = ROOT / "docs/quantum-visualization/2.4.0/rc1-feedback-review.md"
READINESS = ROOT / "docs/quantum-visualization/2.4.0/stable-readiness.md"


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

    def test_local_readiness_records_exact_stable_evidence_and_stop_boundary(self):
        self.assertTrue(READINESS.is_file(), READINESS)
        readiness = READINESS.read_text(encoding="utf-8")
        for term in (
            "State: `Passed`",
            "`chemblender-2.4.0.zip`",
            "`chemblender-2.4.0.sha256`",
            "`chemblender-2.4.0-windows-x64`",
            "`a8d99de7246c1d06d3cb84e8b915597a3821ead2451ef0bd6a546a5c94920bcf`",
            "`6a7bb40dbf4b1be1c4572fe5f7d4093809b786ce8569ff682a9a8149e0aed1ff`",
            "29,976,424 bytes",
            "189 members",
            "2,206 passed / 26 skipped / 0 failed",
            "Blender 5.1.2",
            "Stable manifest probe: `Passed`",
            "Package-CI artifact verification: `Passed`",
            "Release-assets verification: `Passed`",
            "Isolated installed-product smoke: `Passed`",
            "Remote CI: `Passed`",
            "Annotated tag: `Passed`",
            "GitHub Release: `Passed`",
        ):
            with self.subTest(term=term):
                self.assertIn(term, readiness)

    def test_public_release_records_exact_remote_and_public_evidence(self):
        self.assertTrue(READINESS.is_file(), READINESS)
        readiness = READINESS.read_text(encoding="utf-8")
        for term in (
            "PR #22",
            "`a39894d38d170b29a218d9b16f38230fb8bc6987`",
            "`30777435670`",
            "`30777435669`",
            "`302b6efec366f1f1657663659b89e8ce526877a5`",
            "`30777713611`",
            "`30777713610`",
            "`65212c7bdee8a3e14ed86b8d7b4e2d8e989bd0cf`",
            "`30777953426`",
            "`30778221407`",
            "`30778260789`",
            "Release ID: `363951894`",
            "`939d00f292ca41748870094c15a24ac6adf95f28eab293d3c55d6315d8244571`",
            "`f50e93ff8a828732a6518faac7789a2ccea00ca50e7aca5283134348228666a7`",
            "Release body match: `Byte-identical`",
            "Remote CI: `Passed`",
            "Annotated tag: `Passed`",
            "GitHub Release: `Passed`",
        ):
            with self.subTest(term=term):
                self.assertIn(term, readiness)


if __name__ == "__main__":
    unittest.main()
