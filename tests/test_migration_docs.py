import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPGRADE = ROOT / "docs" / "migration" / "2.3.0.md"
LEGACY = ROOT / "docs" / "user" / "legacy-migration.md"
EXTENSION_220 = ROOT / "docs" / "migration" / "2.2.0-extension.md"
INDEX = ROOT / "docs" / "README.md"
OFFICIAL_RELEASE_URL = "https://github.com/psiQAQ/ChemBlender_2_x/releases"


def _upgrade_safety_violations(text):
    """Return safety-contract violations in an upgrade-guide copy."""
    source = text.replace("\r\n", "\n")
    compact = " ".join(source.split())
    required = {
        "official release assets": (
            "Download the ZIP and matching `.sha256` file from the "
            f"[official Release page]({OFFICIAL_RELEASE_URL})."
        ),
        "paired user backup": (
            "Make a manual backup of both `project.blend` and the complete "
            "`project.cbq/` directory. Keep the pair together"
        ),
        "internal backup distinction": (
            "That internal publication backup is normally removed after "
            "success and is not a user restore point."
        ),
        "paired restore": (
            "Restore both members of the same pre-upgrade "
            "`.blend`/`.cbq` backup pair."
        ),
        "downgrade prohibition": (
            "ChemBlender cannot downgrade a sidecar saved as v1 for use by 2.2.0."
        ),
        "incompatible sidecar rejection": (
            "An unknown format, unknown/newer schema, invalid manifest hash, "
            "mismatched project UUID or invalid array will fail closed."
        ),
        "checksum filename comparison": (
            "if ($Matches.name -ne $zip.Name) "
            "{ throw 'Checksum names another package' }"
        ),
        "checksum digest comparison": (
            "if ($actual -ne $Matches.digest) "
            "{ throw 'ChemBlender ZIP SHA-256 mismatch' }"
        ),
    }
    violations = [
        name for name, statement in required.items() if statement not in compact
    ]
    backup = source.find("2. Make a manual backup")
    install = source.find("## Install from a cold process on Windows")
    checksum = source.find("$actual = (Get-FileHash")
    if min(backup, install, checksum) < 0 or not backup < checksum < install:
        violations.append("backup before verification and install")
    return tuple(violations)


class MigrationDocumentationTests(unittest.TestCase):
    def read_doc(self, path, *, require_crlf=False):
        raw = path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path)
        if require_crlf:
            self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), path)
        return raw.decode("utf-8")

    def assert_local_links_resolve(self, path, text):
        for destination in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            destination = destination.strip("<>").split("#", 1)[0]
            if not destination or destination.startswith(("http://", "https://")):
                continue
            self.assertTrue(
                (path.parent / destination).resolve().exists(),
                f"{path}: {destination}",
            )

    def test_230_upgrade_guide_is_fail_closed_and_backup_first(self):
        text = self.read_doc(UPGRADE, require_crlf=True)
        compact = " ".join(text.replace("**", "").split())
        for term in (
            "official Release",
            "Get-FileHash",
            "SHA-256",
            "cold Blender process",
            ".blend",
            ".cbq",
            "2.2.0",
            "v0.1",
            "v0.2",
            "in memory",
            "does not modify the old sidecar",
            "Save As",
            'schema version `1.0`',
            "manual backup",
            "internal publication backup",
            "fail closed",
            "cannot downgrade",
        ):
            self.assertIn(term, compact)
        self.assertIn("keep the pair together", compact.lower())
        for term in ("Windows", "DLL", "locked"):
            self.assertIn(term, text)
        self.assertNotIn("automatic overwrite", text.lower())
        self.assertNotIn("lossless migration", text.lower())
        self.assert_local_links_resolve(UPGRADE, text)

    def test_upgrade_safety_contract_rejects_weakened_copies(self):
        text = self.read_doc(UPGRADE).replace("\r\n", "\n")
        backup_start = text.index("2. Make a manual backup")
        backup_end = text.index("3. Download the ZIP", backup_start)
        backup_step = text[backup_start:backup_end]
        without_backup_step = text[:backup_start] + text[backup_end:]
        moved_backup = without_backup_step.replace(
            "## Install from a cold process on Windows\n",
            "## Install from a cold process on Windows\n\n" + backup_step,
            1,
        )
        weakened = {
            "official release assets": text.replace(
                OFFICIAL_RELEASE_URL,
                "https://example.invalid/releases",
                1,
            ),
            "backup before verification and install": moved_backup,
            "internal backup distinction": text.replace(
                "not a user restore point",
                "a user restore point",
                1,
            ),
            "paired restore": text.replace(
                "Restore both members",
                "Restore either member",
                1,
            ),
            "downgrade prohibition": text.replace(
                "cannot downgrade",
                "can downgrade",
                1,
            ),
            "incompatible sidecar rejection": text.replace(
                "will fail closed",
                "may open",
                1,
            ),
            "checksum filename comparison": text.replace(
                "if ($Matches.name -ne $zip.Name) { throw 'Checksum names another package' }\n",
                "",
                1,
            ),
            "checksum digest comparison": text.replace(
                "if ($actual -ne $Matches.digest) { throw 'ChemBlender ZIP SHA-256 mismatch' }\n",
                "",
                1,
            ),
        }
        self.assertFalse(_upgrade_safety_violations(text))
        for expected_violation, mutated in weakened.items():
            with self.subTest(expected_violation):
                self.assertNotEqual(mutated, text)
                self.assertIn(
                    expected_violation,
                    _upgrade_safety_violations(mutated),
                )

    def test_legacy_guide_covers_preview_evidence_and_recovery_limits(self):
        text = self.read_doc(LEGACY, require_crlf=True)
        for term in (
            "Legacy Migration",
            "Preview Legacy Migration",
            "explicit confirmation",
            "ChemBlender Legacy Backup",
            "backup only",
            "legacy_unverified",
            "source path",
            "source hash",
            "diagnostics",
            "hash-locked",
            "chemblender-2.1-molecule.blend",
            "chemblender-2.2-crystal.blend",
            "chemblender-2.2-edited-scaffold.blend",
            "transaction rollback",
            "no supported automatic undo",
        ):
            self.assertIn(term, text)
        self.assertIn("keep the `.blend` and `.cbq` together", text.lower())
        self.assertNotIn("lossless", text.lower())
        self.assert_local_links_resolve(LEGACY, text)

    def test_migration_guides_are_discoverable_from_existing_entrypoints(self):
        index = self.read_doc(INDEX)
        extension = self.read_doc(EXTENSION_220, require_crlf=True)
        for link in (
            "migration/2.3.0.md",
            "user/legacy-migration.md",
        ):
            self.assertIn(link, index)
        self.assertIn("2.3.0.md", extension)
        self.assert_local_links_resolve(INDEX, index)
        self.assert_local_links_resolve(EXTENSION_220, extension)


if __name__ == "__main__":
    unittest.main()
