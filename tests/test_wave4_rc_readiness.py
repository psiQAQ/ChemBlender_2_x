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
PERFORMANCE_REPORT = (
    ROOT
    / "docs"
    / "quantum-visualization"
    / "2.3.0"
    / "benchmarks"
    / "2.3.0-rc-reference.json"
)
RC_VERSION = "2.3.0-rc.1"
RC_TAG = f"v{RC_VERSION}"
QUALIFICATION_SOURCE = "c796ee9469b44c418da729c25b114a5b06595d46"
PACKAGE_SHA256 = "fed220ad7d9ababe03e821e630ae5beee1a834245060864a8611c5b74f5cfd64"

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

    def test_product_performance_and_readiness_bind_exact_local_evidence(self):
        report = json.loads(PERFORMANCE_REPORT.read_text(encoding="utf-8"))
        self.assertTrue(report["passed"])
        self.assertFalse(report["source_dirty"])
        self.assertEqual(report["source_commit"], QUALIFICATION_SOURCE)
        self.assertEqual(report["sample_count"], 5)
        self.assertEqual(
            {case["name"] for case in report["cases"]},
            {
                "extension_enable",
                "preflight_feedback",
                "default_view",
                "vdb_cache",
                "trajectory_frame",
                "browser_projection_filter",
            },
        )
        for case in report["cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(case["status"], "Passed")
                self.assertEqual(len(case["sample_seconds"]), 5)

        readiness = READINESS.read_text(encoding="utf-8")
        for text in (
            QUALIFICATION_SOURCE,
            PACKAGE_SHA256,
            "benchmark_230_product.py",
            "--samples 5",
            ".superpowers/sdd/docs-release/task5-final-performance/",
            "D:\\cbe230-final",
        ):
            with self.subTest(text=text):
                self.assertIn(text, readiness)


if __name__ == "__main__":
    unittest.main()
