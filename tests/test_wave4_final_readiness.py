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

    def test_local_final_qualification_is_recorded_without_claiming_publication(self):
        readiness = (
            ROOT / ".agents/completed/2.3.0-release-readiness.md"
        ).read_text(encoding="utf-8")
        active = (
            ROOT / ".agents/active/2.3.0-wave-4-migration-release.md"
        ).read_text(encoding="utf-8")
        roadmap = (
            ROOT / "docs/quantum-visualization/2.3.0/roadmap.md"
        ).read_text(encoding="utf-8")

        for expected in (
            "Local final qualification: Passed",
            "`chemblender-2.3.0.zip`",
            "`chemblender-2.3.0.sha256`",
            "`chemblender-2.3.0-windows-x64`",
            "`60585ac9fd757b53cf20947dd83c281670d3192784e23ae09537e77d9ff00ba3`",
            "Final exact-tag package CI: Not Run in this local preparation task",
            "Final public Release: Not Run in this local preparation task",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, readiness)

        self.assertIn("- State: `in_progress`.", active)
        self.assertIn("Task 7 local final qualification: Passed", active)
        self.assertIn(
            "final exact-tag CI and final public Release remain Pending",
            active,
        )
        self.assertIn(
            "本地 final qualification：Passed（2026-08-01）",
            roadmap,
        )
        self.assertIn(
            "远端 final exact-tag CI 与最终公开 Release：Pending（本地任务中 Not Run）",
            roadmap,
        )
        self.assertNotIn("2.3.0 Release-qualified", active)
        self.assertNotIn("2.3.0 Release-qualified", roadmap)

    def test_remote_handoff_is_fail_closed_and_ordered_through_main(self):
        documents = {
            "active": (
                ROOT / ".agents/active/2.3.0-wave-4-migration-release.md"
            ).read_text(encoding="utf-8"),
            "readiness": (
                ROOT / ".agents/completed/2.3.0-release-readiness.md"
            ).read_text(encoding="utf-8"),
        }
        ordered_gates = (
            "1. Independent final review: Passed; record reviewed release HEAD as `H`.",
            "2. Ordinary-push `release/2.3.0` to `origin`.",
            "3. Create PR: `release/2.3.0` to `main`.",
            "4. PR exact HEAD `H`: all five required checks Passed:",
            "5. Immediately after PR checks pass, run `git fetch origin --prune`, record `B = origin/main`, and require the remote PR base still equals `B` and has not advanced.",
            "6. Merge to `main` with an ordinary merge commit and record it as `M`; squash/rebase are forbidden.",
            "7. Fetch and require exact merge identities:",
            "8. Main exact merge commit: all five required checks Passed.",
            "9. Create/push annotated `v2.3.0` from the verified `origin/main` merge commit.",
            "10. Exact-tag CI: unique successful `extension-package` run for the tag's exact commit.",
            "11. Artifact verify: unexpired metadata-named five-file artifact, ZIP/checksum digests, inventory, licenses, size, install, and lifecycle evidence.",
            "12. Dry-run: `extension-release.yml` with `publish=false` must pass.",
            "13. Publish: dispatch with `publish=true`, then verify the public final Release, assets, body, digests, and latest status.",
        )
        required_checks = (
            "`extension-package / native-core`",
            "`extension-package / package`",
            "`optional-qc-core / cclib`",
            "`optional-qc-core / iodata`",
            "`optional-qc-core / gbasis`",
        )
        authorization = (
            "The user has explicitly authorized all remaining Git and remote "
            "operations in this execution.",
            "No further confirmation is required for this sequence.",
            "This execution-specific authorization does not change the "
            "repository's general authorization policy.",
        )
        merge_identity_anchors = (
            "`M^1 == B` (first parent equals the recorded pre-merge `origin/main`).",
            "`M^2 == H` (second parent equals the reviewed release HEAD).",
            "`origin/main == M`.",
            "`H` is an ancestor of `M` (additional check; it does not replace either parent equality).",
        )

        for name, document in documents.items():
            with self.subTest(document=name):
                normalized = " ".join(document.split())
                positions = [normalized.index(gate) for gate in ordered_gates]
                self.assertEqual(positions, sorted(positions))
                push_start = positions[1]
                remote_release_equality = normalized.index(
                    "`origin/release/2.3.0 == H`", push_start
                )
                pr_start = positions[2]
                self.assertLess(remote_release_equality, pr_start)
                pr_checks_start = positions[3]
                base_capture_start = positions[4]
                merge_start = positions[5]
                for check in required_checks:
                    check_position = normalized.index(check, pr_checks_start)
                    self.assertLess(check_position, base_capture_start)
                self.assertLess(pr_checks_start, base_capture_start)
                self.assertLess(base_capture_start, merge_start)
                identity_start = positions[6]
                main_checks_start = positions[7]
                identity_positions = [
                    normalized.index(anchor, identity_start)
                    for anchor in merge_identity_anchors
                ]
                self.assertEqual(identity_positions, sorted(identity_positions))
                self.assertTrue(
                    all(position < main_checks_start for position in identity_positions)
                )
                self.assertIn(
                    "If any gate fails, is missing, or is ambiguous, stop before all later steps.",
                    normalized,
                )
                for statement in authorization:
                    self.assertIn(statement, normalized)

if __name__ == "__main__":
    unittest.main()
