import hashlib
import json
import re
import sys
import unittest
from pathlib import Path, PureWindowsPath


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "ChemBlender"
SCRIPTS = EXTENSION / "scripts"
READINESS = ROOT / ".agents" / "completed" / "2.3.0-rc-readiness.md"
ACTIVE_CURSOR = ROOT / ".agents" / "active" / "2.3.0-wave-4-migration-release.md"
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
RC_RELEASE_NOTES_UTF8_SHA256 = (
    "d19666306b6afe45c33640b8032535c713bdc6d49164f305c5d2ae5cfe4da14b"
)
RC_TAG_OBJECT = "e450d0c29ca9244df05debd3022467f153fda8d1"
RC_TAG_COMMIT = "86e4391a73128f0262e0fbf6960443c3be4cb310"
RC_PACKAGE_RUN = "30682833534"
RC_ARTIFACT_ID = "8812929666"
RC_PACKAGE_SHA256_PUBLISHED = (
    "7d45bfe9e208e6d50d2b90e875316092c12e51177f39f8835e8ad71af3d2de17"
)
RC_PUBLISHED_AT = "2026-08-01T04:02:01Z"
RC_FEEDBACK_CHECKED_AT = "2026-08-01T05:25:58Z"
QUALIFICATION_SOURCE = "c796ee9469b44c418da729c25b114a5b06595d46"
PACKAGE_SHA256 = "fed220ad7d9ababe03e821e630ae5beee1a834245060864a8611c5b74f5cfd64"
EXACT_COMMAND_MANIFEST_SHA256 = (
    "fe118ec093fd8e4bec48a15ea9e26eb7b510077d1089afca70e2f189ce92cf5a"
)
EXACT_COMMAND_EVIDENCE = (
    ROOT
    / ".superpowers"
    / "sdd"
    / "docs-release"
    / "task5-final-performance"
    / "exact-command-manifest.json"
)
REQUIRED_GATE_LABELS = {
    "dependency-inventory",
    "optional-dependency-probe",
    "focused",
    "full",
    "compileall",
    "generated-docs",
    "native-validate",
    "artifact-size",
    "package-ci-verifier",
    "release-assets-verifier",
    "diff-check",
    "package-tree-guard",
    "zip-source-byte-inventory",
    "short-product-smoke",
    "default-temp-product-smoke",
    "legacy-1",
    "legacy-2",
    "legacy-3",
}
REQUIRED_GATE_FIELDS = {
    "label",
    "argv",
    "cwd",
    "qualification_source",
    "verification_head",
    "package",
    "package_sha256",
    "environment_overrides",
    "selected_env",
    "started_at_utc",
    "duration_seconds",
    "exit_code",
    "missing_markers",
    "stdout",
    "stdout_bytes",
    "stdout_sha256",
    "stderr",
    "stderr_bytes",
    "stderr_sha256",
}

sys.path.insert(0, str(SCRIPTS))

from extract_release_notes import extract_release_notes


class Wave4RCReadinessTests(unittest.TestCase):
    def test_rc_changelog_is_complete(self):
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

    def test_readiness_separates_historical_pre_tag_snapshot_from_published_rc(self):
        readiness = READINESS.read_text(encoding="utf-8")
        for text in (
            "Historical pre-tag qualification snapshot",
            RC_TAG_OBJECT,
            RC_TAG_COMMIT,
            RC_PACKAGE_RUN,
            RC_ARTIFACT_ID,
            RC_PACKAGE_SHA256_PUBLISHED,
            "30683074015",
            "30683112170",
            "https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.3.0-rc.1",
            "must not be copied into the final `2.3.0` changelog or readiness record",
            RC_PUBLISHED_AT,
            RC_FEEDBACK_CHECKED_AT,
        ):
            with self.subTest(text=text):
                self.assertIn(text, readiness)

        cursor = ACTIVE_CURSOR.read_text(encoding="utf-8")
        self.assertIn(RC_FEEDBACK_CHECKED_AT, cursor)

    def test_rc_feedback_window_is_nonzero_and_evidence_bounded(self):
        evidence = (
            f"published at `{RC_PUBLISHED_AT}`",
            f"fresh feedback check at `{RC_FEEDBACK_CHECKED_AT}`",
            "`1h23m57s`",
            "Issues disabled",
            "PR #6 `reviews=0`, `review comments=0`, and `issue comments=0`",
            "`gh api --jq length`",
            "`discussion_url=null`",
            "`reactions=null`",
            "no blocker was found",
            "plan defines no minimum feedback-window duration",
            "current user explicitly authorized continuing to final",
            "does not claim that user feedback was received",
        )
        for name, path in (
            ("readiness", READINESS),
            ("active", ACTIVE_CURSOR),
        ):
            document = " ".join(path.read_text(encoding="utf-8").split())
            with self.subTest(document=name):
                for expected in evidence:
                    self.assertIn(expected, document)

    def test_rc_changelog_scopes_pre_tag_remote_ci_snapshot(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        notes = extract_release_notes(changelog, RC_VERSION)
        self.assertEqual(
            hashlib.sha256(notes.encode("utf-8")).hexdigest(),
            RC_RELEASE_NOTES_UTF8_SHA256,
            "RC release notes must match the immutable tagged/public UTF-8 body",
        )

        for text in (
            "Remote CI has not run for this exact RC commit. Local qualification "
            "evidence must not be described as exact-HEAD CI evidence.",
            "`Remote CI: Not Run`. Tagging, package CI and prerelease publication "
            "require separate authorization and exact-tag evidence.",
        ):
            with self.subTest(text=text):
                self.assertIn(text, notes)

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

    def test_exact_command_evidence_contract_is_complete(self):
        readiness = READINESS.read_text(encoding="utf-8")
        match = re.search(
            r"<!-- RC_EXACT_COMMAND_EVIDENCE (\{[^\r\n]+\}) -->",
            readiness,
        )
        self.assertIsNotNone(match, "missing exact command evidence summary")
        summary = json.loads(match.group(1))
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["command_count"], 18)
        self.assertEqual(set(summary["required_labels"]), REQUIRED_GATE_LABELS)
        self.assertEqual(
            set(summary["required_record_fields"]),
            REQUIRED_GATE_FIELDS,
        )
        self.assertEqual(summary["qualification_source"], QUALIFICATION_SOURCE)
        self.assertEqual(summary["package_sha256"], PACKAGE_SHA256)
        self.assertEqual(
            summary["manifest_sha256"],
            EXACT_COMMAND_MANIFEST_SHA256,
        )
        self.assertTrue(PureWindowsPath(summary["cwd"]).is_absolute())

        if not EXACT_COMMAND_EVIDENCE.is_file():
            return
        manifest_bytes = EXACT_COMMAND_EVIDENCE.read_bytes()
        self.assertEqual(
            hashlib.sha256(manifest_bytes).hexdigest(),
            EXACT_COMMAND_MANIFEST_SHA256,
        )
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest["status"], "passed")
        self.assertEqual(manifest["command_count"], 18)
        self.assertFalse(manifest["verification_head_dirty"])
        self.assertEqual(manifest["qualification_source"], QUALIFICATION_SOURCE)
        self.assertEqual(manifest["package_sha256"], PACKAGE_SHA256)
        self.assertEqual(
            {record["label"] for record in manifest["commands"]},
            REQUIRED_GATE_LABELS,
        )
        evidence_root = EXACT_COMMAND_EVIDENCE.parent
        for record in manifest["commands"]:
            with self.subTest(gate=record["label"]):
                self.assertTrue(REQUIRED_GATE_FIELDS <= record.keys())
                self.assertTrue(PureWindowsPath(record["cwd"]).is_absolute())
                self.assertTrue(PureWindowsPath(record["argv"][0]).is_absolute())
                self.assertTrue(PureWindowsPath(record["package"]).is_absolute())
                self.assertEqual(record["qualification_source"], QUALIFICATION_SOURCE)
                self.assertEqual(
                    record["verification_head"], manifest["verification_head"]
                )
                self.assertEqual(record["package_sha256"], PACKAGE_SHA256)
                self.assertEqual(record["exit_code"], 0)
                self.assertEqual(record["missing_markers"], [])
                self.assertEqual(
                    set(record["selected_env"]),
                    {"BLENDER_USER_RESOURCES", "PYTHONPATH", "TEMP", "TMP"},
                )
                for stream in ("stdout", "stderr"):
                    log = evidence_root / record[stream]
                    self.assertTrue(log.is_file(), f"missing {stream}: {log}")
                    self.assertEqual(log.stat().st_size, record[f"{stream}_bytes"])
                    self.assertEqual(
                        hashlib.sha256(log.read_bytes()).hexdigest(),
                        record[f"{stream}_sha256"],
                    )


if __name__ == "__main__":
    unittest.main()
