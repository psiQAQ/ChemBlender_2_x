import unittest
from pathlib import Path

from ChemBlender.scripts.extract_release_notes import extract_release_notes
from ChemBlender.scripts.release_metadata import read_release_metadata


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.4.0-rc.1"
READINESS = ROOT / "docs/quantum-visualization/2.4.0/rc1-readiness.md"


class ReleaseCandidateReadinessTests(unittest.TestCase):
    def test_production_metadata_and_notes_describe_the_exact_candidate(self):
        metadata = read_release_metadata(ROOT / "ChemBlender")
        self.assertEqual(VERSION, metadata.version)
        self.assertEqual("chemblender-2.4.0-rc.1.zip", metadata.package_name)
        self.assertEqual(
            "chemblender-2.4.0-rc.1.sha256",
            metadata.checksum_name,
        )
        self.assertEqual(
            "chemblender-2.4.0-rc.1-windows-x64",
            metadata.artifact_name,
        )

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        notes = extract_release_notes(changelog, VERSION)
        for term in (
            "### Added",
            "MOL2",
            "PDB",
            "PQR",
            "Cube",
            "Project Browser",
            "### Changed",
            "Reader API `1.0-rc1`",
            "### Compatibility",
            "Blender 5.1.2",
            "### Known Limitations",
            "### Verification",
            "Remote CI: `Not Run`",
        ):
            self.assertIn(term, notes)
        self.assertNotIn("## [2.4.0]", changelog)
        self.assertIn(
            "[Unreleased]: https://github.com/psiQAQ/ChemBlender_2_x/compare/"
            "v2.4.0-rc.1...HEAD",
            changelog,
        )
        self.assertIn(
            "[2.4.0-rc.1]: https://github.com/psiQAQ/ChemBlender_2_x/"
            "releases/tag/v2.4.0-rc.1",
            changelog,
        )

    def test_local_readiness_records_exact_candidate_evidence_and_stop_boundary(self):
        readiness = READINESS.read_text(encoding="utf-8")
        for term in (
            "State: `Passed`",
            "`chemblender-2.4.0-rc.1.zip`",
            "`chemblender-2.4.0-rc.1.sha256`",
            "`chemblender-2.4.0-rc.1-windows-x64`",
            "`b3df84593f79e14dc594b075c57f09f53fbed0ea75199fa1739ea8c30deb64b7`",
            "29,976,427 bytes",
            "189 members",
            "2,202 passed / 26 skipped / 0 failed",
            "Blender 5.1.2",
            "Prerelease validation probe: `Passed`",
            "Package-CI artifact verification: `Passed`",
            "Release-assets verification: `Passed`",
            "Isolated installed-product smoke: `Passed`",
            "Remote CI: `Not Run`",
            "Annotated tag: `Not Run`",
            "GitHub Release: `Not Run`",
        ):
            with self.subTest(term=term):
                self.assertIn(term, readiness)


if __name__ == "__main__":
    unittest.main()
