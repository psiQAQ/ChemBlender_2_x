import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "ChemBlender"
SCRIPTS = EXTENSION / "scripts"
FINAL_VERSION = "2.3.0"
FINAL_MANIFEST_SHA256 = (
    "a48c28e6c4e56b2c859dbe7369730d1f9fbb33599e207acc2ed5f4f37473d22e"
)
RC_NOTES_SHA256 = (
    "d19666306b6afe45c33640b8032535c713bdc6d49164f305c5d2ae5cfe4da14b"
)

sys.path.insert(0, str(SCRIPTS))

from extract_release_notes import extract_release_notes
from release_metadata import read_release_metadata


class Wave4FinalReadinessTests(unittest.TestCase):
    def test_final_metadata_and_manifest_are_exact(self):
        metadata = read_release_metadata(EXTENSION)
        self.assertEqual(metadata.version, FINAL_VERSION)
        self.assertEqual(metadata.package_name, "chemblender-2.3.0.zip")
        self.assertEqual(metadata.checksum_name, "chemblender-2.3.0.sha256")
        self.assertEqual(metadata.artifact_name, "chemblender-2.3.0-windows-x64")

        manifest = (EXTENSION / "blender_manifest.toml").read_bytes()
        self.assertEqual(
            hashlib.sha256(manifest.replace(b"\r\n", b"\n")).hexdigest(),
            FINAL_MANIFEST_SHA256,
        )

    def test_final_changelog_preserves_published_rc_and_stable_release_contract(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        final_notes = extract_release_notes(changelog, FINAL_VERSION)
        rc_notes = extract_release_notes(changelog, "2.3.0-rc.1")

        self.assertEqual(hashlib.sha256(rc_notes.encode()).hexdigest(), RC_NOTES_SHA256)
        for heading in (
            "Added",
            "Changed",
            "Fixed",
            "Compatibility",
            "Migration",
            "Known Limitations",
            "Verification",
        ):
            with self.subTest(heading=heading):
                self.assertIn(f"### {heading}", final_notes)
        self.assertIn("exact-tag `extension-package` run `30682833534`", final_notes)
        self.assertIn(
            "The final Release publishes only the successful exact-tag package CI "
            "artifact after independent artifact and Release workflow verification",
            final_notes,
        )
        self.assertNotIn("Remote CI: Not Run", final_notes)
        self.assertNotIn("pending", final_notes.lower())
        self.assertNotIn("authorization", final_notes.lower())
        self.assertIn(
            "[Unreleased]: https://github.com/psiQAQ/ChemBlender_2_x/compare/v2.3.0...HEAD",
            changelog,
        )
        self.assertIn(
            "[2.3.0]: https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.3.0",
            changelog,
        )
        self.assertIn(
            "[2.3.0-rc.1]: https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.3.0-rc.1",
            changelog,
        )

if __name__ == "__main__":
    unittest.main()
