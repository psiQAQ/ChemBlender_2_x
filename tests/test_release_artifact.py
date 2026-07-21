import hashlib
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "ChemBlender"
sys.path.insert(0, str(EXTENSION / "scripts"))

from verify_release_artifact import verify_artifact


class ReleaseArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.artifact_dir = Path(self.temp_dir.name)
        self.tag = "v2.2.0"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_artifact(
        self, *extra_entries: str, packaged_manifest: bytes | None = None
    ) -> Path:
        source_manifest = (EXTENSION / "blender_manifest.toml").read_bytes()
        manifest = tomllib.loads(source_manifest.decode("utf-8"))
        package = self.artifact_dir / "chemblender-2.2.0.zip"
        entries = {
            "blender_manifest.toml": packaged_manifest or source_manifest,
            "LICENSE": b"license",
            "Chem_Nodes.blend": b"blend",
            "Chem_Nodes_En.blend": b"blend",
            manifest["wheels"][0].removeprefix("./"): b"wheel",
        }
        entries.update({name: b"extra" for name in extra_entries})
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        (self.artifact_dir / "chemblender-2.2.0.sha256").write_text(
            f"{digest}  {package.name}\n",
            encoding="utf-8",
            newline="\n",
        )
        return package

    def test_valid_artifact_passes(self):
        package = self._write_artifact()

        result = verify_artifact(self.artifact_dir, EXTENSION, self.tag)

        self.assertEqual(result["version"], "2.2.0")
        self.assertEqual(
            result["package_sha256"], hashlib.sha256(package.read_bytes()).hexdigest()
        )

    def test_checksum_mismatch_fails(self):
        package = self._write_artifact()
        package.write_bytes(package.read_bytes() + b"changed")

        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            verify_artifact(self.artifact_dir, EXTENSION, self.tag)

    def test_manifest_line_endings_do_not_change_package_contract(self):
        source_manifest = (EXTENSION / "blender_manifest.toml").read_bytes()
        linux_manifest = source_manifest.replace(b"\r\n", b"\n")
        self._write_artifact(packaged_manifest=linux_manifest)

        result = verify_artifact(self.artifact_dir, EXTENSION, self.tag)

        self.assertEqual(result["version"], "2.2.0")

    def test_extra_wheel_fails_package_contract(self):
        self._write_artifact("wheels/unexpected.whl")

        with self.assertRaisesRegex(ValueError, "wheel entries"):
            verify_artifact(self.artifact_dir, EXTENSION, self.tag)

    def test_nested_artifact_file_fails(self):
        self._write_artifact()
        nested = self.artifact_dir / "unexpected"
        nested.mkdir()
        (nested / "file.txt").write_text("extra", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "artifact files"):
            verify_artifact(self.artifact_dir, EXTENSION, self.tag)


if __name__ == "__main__":
    unittest.main()
