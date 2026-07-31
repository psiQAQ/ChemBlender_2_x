import json
import re
import sys
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "ChemBlender"
SCRIPTS = EXTENSION / "scripts"
READINESS = ROOT / ".agents" / "completed" / "2.3.0-rc-readiness.md"
RC_VERSION = "2.3.0-rc.1"
RC_TAG = f"v{RC_VERSION}"

sys.path.insert(0, str(SCRIPTS))

from extract_release_notes import extract_release_notes
from release_metadata import read_release_metadata


class Wave4RCReadinessTests(unittest.TestCase):
    def test_rc_metadata_and_changelog_are_exact(self):
        metadata = read_release_metadata(EXTENSION)
        self.assertEqual(metadata.version, RC_VERSION)
        self.assertEqual(metadata.package_name, f"chemblender-{RC_VERSION}.zip")
        self.assertEqual(metadata.checksum_name, f"chemblender-{RC_VERSION}.sha256")
        self.assertEqual(
            metadata.artifact_name,
            f"chemblender-{RC_VERSION}-windows-x64",
        )

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## [{RC_VERSION}] - ", changelog)
        notes = extract_release_notes(changelog, RC_VERSION)
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
                self.assertIn(f"### {heading}", notes)

    def test_readiness_binds_local_rc_evidence_and_zero_growth_budget(self):
        self.assertTrue(READINESS.is_file(), f"missing RC readiness: {READINESS}")
        readiness = READINESS.read_text(encoding="utf-8")
        for text in (
            f"`{RC_VERSION}`",
            f"`{RC_TAG}`",
            "Remote CI",
            "Not Run",
            "Blender 5.1.2",
            "RDKit 2026.03.3",
            "Gemmi 0.7.5",
        ):
            with self.subTest(text=text):
                self.assertIn(text, readiness)

        match = re.search(
            r"<!-- RC_ARTIFACT_BUDGET (\{[^\r\n]+\}) -->",
            readiness,
        )
        self.assertIsNotNone(match, "missing canonical RC artifact-budget evidence")
        evidence = json.loads(match.group(1))
        budget = json.loads(
            (ROOT / ".github" / "artifact-budgets.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["package_bytes"], budget["baseline_package_bytes"])
        self.assertEqual(
            evidence["member_unpacked_bytes"],
            budget["baseline_member_unpacked_bytes"],
        )
        self.assertEqual(
            evidence["section_unpacked_bytes"],
            {
                name: section["baseline_unpacked_bytes"]
                for name, section in budget["section_unpacked_budgets"].items()
            },
        )
        self.assertEqual(budget["allowed_unexplained_growth_bytes"], 0)
        self.assertEqual(
            budget["allowed_unexplained_member_unpacked_growth_bytes"], 0
        )
        self.assertTrue(
            all(
                section["allowed_unexplained_growth_bytes"] == 0
                for section in budget["section_unpacked_budgets"].values()
            )
        )

    def test_manifest_version_is_a_single_root_assignment(self):
        source = (EXTENSION / "blender_manifest.toml").read_bytes()
        self.assertEqual(source.count(f'version = "{RC_VERSION}"'.encode()), 1)
        with (EXTENSION / "blender_manifest.toml").open("rb") as stream:
            self.assertEqual(tomllib.load(stream)["version"], RC_VERSION)


if __name__ == "__main__":
    unittest.main()
