import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPGRADE = ROOT / "docs" / "migration" / "2.3.0.md"
LEGACY = ROOT / "docs" / "user" / "legacy-migration.md"
EXTENSION_220 = ROOT / "docs" / "migration" / "2.2.0-extension.md"
INDEX = ROOT / "docs" / "README.md"


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
