import hashlib
import subprocess
import sys
import tomllib
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
RELEASE_HEAD = "bd3e4a730ee687974d46e8c16d87ebe91b1b49ae"
PRE_MERGE_MAIN = "86e4391a73128f0262e0fbf6960443c3be4cb310"
MERGE_COMMIT = "26e4d51b8be6915618d4230006fabad6c2326d0c"
TAG_OBJECT = "01f97d594e9d857980dcd920e2f49df729536c92"
PACKAGE_SHA256 = (
    "5ba1ad9c8f41f413c355343d357dd26bb037128a0f8adfad01ec704f96ba069f"
)
CHECKSUM_SHA256 = (
    "54573f54562dcf765c5bb544d1df1eba74e0e38fe476111307dfb8c9c0fefd95"
)
RELEASE_BODY_SHA256 = (
    "cad6ea6f3761f345fe5330ee62e869bdaed72ef10933ce9ad49542b4ea2490fd"
)
FINAL_CURSOR = ROOT / ".agents/completed/2.3.0-wave-4-migration-release.md"
READINESS = ROOT / ".agents/completed/2.3.0-release-readiness.md"
ROADMAP = ROOT / "docs/quantum-visualization/2.3.0/roadmap.md"

sys.path.insert(0, str(SCRIPTS))

from extract_release_notes import extract_release_notes


class Wave4FinalReadinessTests(unittest.TestCase):
    def test_final_metadata_and_manifest_are_exact(self):
        manifest = subprocess.run(
            [
                "git",
                "show",
                f"{MERGE_COMMIT}:ChemBlender/blender_manifest.toml",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(tomllib.loads(manifest.decode("utf-8"))["version"], FINAL_VERSION)
        self.assertEqual(
            hashlib.sha256(manifest.replace(b"\r\n", b"\n")).hexdigest(),
            FINAL_MANIFEST_SHA256,
        )

    def test_final_changelog_preserves_published_rc_and_stable_release_contract(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        final_notes = extract_release_notes(changelog, FINAL_VERSION)
        rc_notes = extract_release_notes(changelog, "2.3.0-rc.1")

        self.assertEqual(hashlib.sha256(rc_notes.encode()).hexdigest(), RC_NOTES_SHA256)
        self.assertIn(
            "post-RC work remained limited to release-blocking fixes, "
            "qualification, and documentation clarity",
            final_notes,
        )
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
            "[2.3.0]: https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.3.0",
            changelog,
        )
        self.assertIn(
            "[2.3.0-rc.1]: https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.3.0-rc.1",
            changelog,
        )

    def test_final_publication_is_recorded_at_exact_remote_identities(self):
        readiness = READINESS.read_text(encoding="utf-8")
        completed = FINAL_CURSOR.read_text(encoding="utf-8")
        roadmap = ROADMAP.read_text(encoding="utf-8")

        for expected in (
            "Local final qualification: Passed",
            "Final public Release: Passed",
            "`chemblender-2.3.0.zip`",
            "`chemblender-2.3.0.sha256`",
            "`chemblender-2.3.0-windows-x64`",
            "`7eea1c2db9a4bc22a66b99b8ea374a5c04a908f72dc64e6c27ad3dd12e6c0edf`",
            RELEASE_HEAD,
            PRE_MERGE_MAIN,
            MERGE_COMMIT,
            TAG_OBJECT,
            "PR [#7](https://github.com/psiQAQ/ChemBlender_2_x/pull/7)",
            "30688290548",
            "30688290557",
            "30688503614",
            "30688503615",
            "30688727561",
            "8814949707",
            PACKAGE_SHA256,
            CHECKSUM_SHA256,
            "30689352612",
            "30689376447",
            "363458494",
            "https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.3.0",
            RELEASE_BODY_SHA256,
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, readiness)

        self.assertFalse(
            (ROOT / ".agents/active/2.3.0-wave-4-migration-release.md").exists()
        )
        self.assertIn("- State: `completed`.", completed)
        self.assertIn("2.3.0 Release-qualified: Passed", completed)
        self.assertIn(
            ".agents/completed/2.3.0-release-readiness.md",
            completed,
        )
        self.assertIn("2.3.0 Release-qualified：Passed（2026-08-01）", roadmap)
        self.assertIn("Wave 4 已完成", roadmap)

        stale_claims = (
            "Final exact-tag package CI: Not Run in this local preparation task",
            "Final public Release: Not Run in this local preparation task",
            "final exact-tag CI and final public Release remain Pending",
            "远端 final exact-tag CI 与最终公开 Release：Pending",
        )
        for document in (readiness, completed, roadmap):
            for stale in stale_claims:
                with self.subTest(stale=stale):
                    self.assertNotIn(stale, document)

    def test_completed_cursor_has_no_remaining_release_work(self):
        completed = FINAL_CURSOR.read_text(encoding="utf-8")

        for obsolete in (
            "close all Task 5 review findings",
            "Docs Tasks 6–7 require an authorized RC tag/push",
            "Remaining execution order:",
            "complete the independent final review",
            "Final annotated tag `v2.3.0`, exact-tag CI, Release dry-run, and public Release remain `Not Run`.",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, completed)
        for expected in (
            "Final publication evidence:",
            "No remaining Wave 4 task.",
            "Release Groundwork and Waves 0–4 are complete.",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, completed)

    def test_durable_entrypoints_match_the_published_release(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        branch_release = (
            ROOT / "docs/development/branch-and-release.md"
        ).read_text(encoding="utf-8")
        reader_compatibility = (
            ROOT / "docs/reader-api-v1/compatibility.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "Latest release readiness evidence: "
            "`.agents/completed/2.3.0-release-readiness.md`",
            agents,
        )
        self.assertIn("2.3.0: published final extension", branch_release)
        self.assertNotIn("2.3.0-alpha.1: Wave 0", branch_release)
        self.assertIn(
            "2.3.0 正式版\n保留 `1.0-rc1` token",
            reader_compatibility,
        )
        self.assertNotIn("only at the 2.3.0 final release gate", reader_compatibility)

    def test_completed_records_contain_no_live_remote_runbook(self):
        documents = {
            "completed": FINAL_CURSOR.read_text(encoding="utf-8"),
            "readiness": READINESS.read_text(encoding="utf-8"),
        }
        obsolete = (
            "all remaining Git and remote operations",
            "No further confirmation is required",
            "Immediately after PR checks pass",
            "Create/push annotated `v2.3.0`",
            "dispatch with `publish=true`",
            "Before final handoff",
        )

        for name, document in documents.items():
            with self.subTest(document=name):
                for statement in obsolete:
                    self.assertNotIn(statement, document)

if __name__ == "__main__":
    unittest.main()
