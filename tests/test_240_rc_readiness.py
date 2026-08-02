import unittest
from pathlib import Path

from ChemBlender.scripts.extract_release_notes import extract_release_notes
from ChemBlender.scripts.release_metadata import read_release_metadata


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.4.0-rc.1"


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


if __name__ == "__main__":
    unittest.main()
