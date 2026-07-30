import hashlib
import io
import json
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "ChemBlender"
sys.path.insert(0, str(EXTENSION / "scripts"))

import verify_release_artifact
import artifact_size_report
from release_metadata import read_release_metadata
from verify_release_artifact import verify_artifact


class ReleaseArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.artifact_dir = Path(self.temp_dir.name)
        self.tag = "v2.3.0-alpha.1"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_artifact(
        self, *extra_entries: str, packaged_manifest: bytes | None = None
    ) -> Path:
        return self._write_artifact_for_extension(
            self.artifact_dir,
            EXTENSION,
            *extra_entries,
            packaged_manifest=packaged_manifest,
        )

    def _write_artifact_for_extension(
        self,
        artifact_dir: Path,
        extension: Path,
        *extra_entries: str,
        packaged_manifest: bytes | None = None,
    ) -> Path:
        source_manifest = (extension / "blender_manifest.toml").read_bytes()
        manifest = tomllib.loads(source_manifest.decode("utf-8"))
        metadata = read_release_metadata(extension)
        package = artifact_dir / metadata.package_name
        entries = {
            "blender_manifest.toml": packaged_manifest or source_manifest,
            "LICENSE": b"license",
            "Chem_Nodes.blend": b"blend",
            "Chem_Nodes_En.blend": b"blend",
            **{
                wheel.removeprefix("./"): b"wheel"
                for wheel in manifest["wheels"]
            },
        }
        entries.update({name: b"extra" for name in extra_entries})
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        (artifact_dir / metadata.checksum_name).write_text(
            f"{digest}  {package.name}\n",
            encoding="utf-8",
            newline="\n",
        )
        return package

    def test_valid_artifact_passes(self):
        package = self._write_artifact()

        result = verify_artifact(
            self.artifact_dir, EXTENSION, self.tag, metadata_mode="release-assets"
        )

        self.assertEqual(result["version"], "2.3.0-alpha.1")
        self.assertEqual(
            result["package_sha256"], hashlib.sha256(package.read_bytes()).hexdigest()
        )

    def test_verifier_reads_release_metadata_once(self):
        self._write_artifact()

        with mock.patch.object(
            verify_release_artifact,
            "read_release_metadata",
            wraps=read_release_metadata,
        ) as read_metadata:
            verify_release_artifact.verify_artifact(
                self.artifact_dir, EXTENSION, self.tag, metadata_mode="release-assets"
            )

        read_metadata.assert_called_once_with(EXTENSION.resolve())

    def test_checksum_mismatch_fails(self):
        package = self._write_artifact()
        package.write_bytes(package.read_bytes() + b"changed")

        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            verify_artifact(
                self.artifact_dir, EXTENSION, self.tag, metadata_mode="release-assets"
            )

    def test_manifest_line_endings_do_not_change_package_contract(self):
        source_manifest = (EXTENSION / "blender_manifest.toml").read_bytes()
        linux_manifest = source_manifest.replace(b"\r\n", b"\n")
        self._write_artifact(packaged_manifest=linux_manifest)

        result = verify_artifact(
            self.artifact_dir, EXTENSION, self.tag, metadata_mode="release-assets"
        )

        self.assertEqual(result["version"], "2.3.0-alpha.1")

    def test_tag_version_must_match_release_metadata(self):
        self._write_artifact()

        with self.assertRaisesRegex(
            ValueError,
            "tag version 2.3.0-beta.1 does not match manifest 2.3.0-alpha.1",
        ):
            verify_artifact(
                self.artifact_dir,
                EXTENSION,
                "v2.3.0-beta.1",
                metadata_mode="release-assets",
            )

    def test_prerelease_tag_matches_prerelease_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            extension = root / "extension"
            artifact = root / "artifact"
            extension.mkdir()
            artifact.mkdir()
            manifest = (EXTENSION / "blender_manifest.toml").read_bytes()
            (extension / "blender_manifest.toml").write_bytes(manifest)
            self._write_artifact_for_extension(artifact, extension)

            result = verify_artifact(
                artifact,
                extension,
                "v2.3.0-alpha.1",
                metadata_mode="release-assets",
            )

        self.assertEqual(result["version"], "2.3.0-alpha.1")
        self.assertEqual(result["package"], "chemblender-2.3.0-alpha.1.zip")

    def test_tag_requires_v_and_shared_release_version_grammar(self):
        self._write_artifact()

        for tag in (
            "2.2.0",
            "vv2.2.0",
            "v2.2.0-alpha",
            "v2.2.0-alpha.0",
            "v2.2.0-preview.1",
            "v02.2.0",
            "v2\u0663.3.0",
            "v2.3.0-alpha.1\u0661",
        ):
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(ValueError, "invalid release tag"):
                    verify_artifact(
                        self.artifact_dir, EXTENSION, tag, metadata_mode="release-assets"
                    )

    def test_extra_wheel_fails_package_contract(self):
        self._write_artifact("wheels/unexpected.whl")

        with self.assertRaisesRegex(ValueError, "wheel entries"):
            verify_artifact(
                self.artifact_dir, EXTENSION, self.tag, metadata_mode="release-assets"
            )

    def test_nested_artifact_file_fails(self):
        self._write_artifact()
        nested = self.artifact_dir / "unexpected"
        nested.mkdir()
        (nested / "file.txt").write_text("extra", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "artifact files"):
            verify_artifact(
                self.artifact_dir, EXTENSION, self.tag, metadata_mode="release-assets"
            )

    def test_package_ci_metadata_is_required_and_bound_to_the_package(self):
        extension = self.artifact_dir / "extension"
        package_dir = self.artifact_dir / "package-ci"
        extension.mkdir()
        package_dir.mkdir()
        wheel_name = "fixture-1.0.0-py3-none-any.whl"
        manifest = (
            'id = "chemblender"\n'
            'version = "2.3.0-alpha.1"\n'
            'platforms = ["windows-x64"]\n'
            f'wheels = ["./wheels/{wheel_name}"]\n'
        ).encode("utf-8")
        (extension / "blender_manifest.toml").write_bytes(manifest)
        wheel_stream = io.BytesIO()
        with zipfile.ZipFile(wheel_stream, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("fixture/module.py", b"fixture")
            archive.writestr("fixture-1.0.0.dist-info/LICENSE.txt", b"license")
        wheel = wheel_stream.getvalue()
        wheel_sha256 = hashlib.sha256(wheel).hexdigest()
        package = package_dir / "chemblender-2.3.0-alpha.1.zip"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("blender_manifest.toml", manifest)
            archive.writestr("LICENSE", b"license")
            archive.writestr("Chem_Nodes.blend", b"blend")
            archive.writestr("Chem_Nodes_En.blend", b"blend")
            archive.writestr(f"wheels/{wheel_name}", wheel)
        checksum = hashlib.sha256(package.read_bytes()).hexdigest()
        (package_dir / "chemblender-2.3.0-alpha.1.sha256").write_text(
            f"{checksum}  {package.name}\n", encoding="utf-8", newline="\n"
        )
        with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
            wheel_unpacked = sum(info.file_size for info in archive.infolist())
        (extension / "dependencies.toml").write_text(
            "\n".join(
                (
                    'schema_version = "1"',
                    "",
                    "[[dependency]]",
                    'distribution = "fixture"',
                    'version = "1.0.0"',
                    f'filename = "{wheel_name}"',
                    'platform = "windows-x64"',
                    'python_abi = "py3-none-any"',
                    'url = "https://example.invalid/fixture.whl"',
                    f'sha256 = "{wheel_sha256}"',
                    'spdx_license = "MIT"',
                    'license_source = "fixture-1.0.0.dist-info/LICENSE.txt"',
                    "required = true",
                    f"max_compressed_bytes = {len(wheel)}",
                    f"max_unpacked_bytes = {wheel_unpacked}",
                    "",
                )
            ),
            encoding="utf-8",
            newline="\n",
        )
        inventory = {
            "wheels": [
                {
                    "compressed_bytes": len(wheel),
                    "distribution": "fixture",
                    "filename": wheel_name,
                    "license_source": "fixture-1.0.0.dist-info/LICENSE.txt",
                    "max_compressed_bytes": len(wheel),
                    "max_unpacked_bytes": wheel_unpacked,
                    "platform": "windows-x64",
                    "python_abi": "py3-none-any",
                    "required": True,
                    "sha256": wheel_sha256,
                    "spdx_license": "MIT",
                    "unpacked_bytes": wheel_unpacked,
                    "url": "https://example.invalid/fixture.whl",
                    "version": "1.0.0",
                }
            ]
        }
        licenses = {
            "licenses": [
                {
                    "distribution": "fixture",
                    "filename": wheel_name,
                    "source": "fixture-1.0.0.dist-info/LICENSE.txt",
                    "target": "licenses/fixture-1.0.0-LICENSE.txt",
                    "version": "1.0.0",
                }
            ]
        }
        inventory_path = package_dir / "wheel-inventory.json"
        license_path = package_dir / "wheel-license-copy-list.json"
        inventory_path.write_bytes(
            (json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        )
        license_path.write_bytes(
            (json.dumps(licenses, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        )
        budget = {
            "schema_version": "1",
            "baseline_package_bytes": package.stat().st_size,
            "allowed_unexplained_growth_bytes": 0,
            "existing_wheel_distributions": ["fixture"],
            "new_wheel_budget": {
                "max_compressed_bytes_per_wheel": 10_000_000,
                "max_unpacked_bytes_per_wheel": 30_000_000,
                "max_compressed_bytes_total": 20_000_000,
                "approved_wheels": [],
            },
        }
        (extension / "artifact-budgets.json").write_text(
            json.dumps(budget, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        report = artifact_size_report.build_report(
            package, inventory_path, license_path, extension / "artifact-budgets.json"
        )
        (package_dir / "artifact-size.json").write_bytes(
            artifact_size_report.canonical_json(report)
        )

        result = verify_artifact(
            package_dir,
            extension,
            self.tag,
            metadata_mode="package-ci",
            budget_path=extension / "artifact-budgets.json",
        )
        self.assertEqual(result["package_sha256"], checksum)

        inventory["wheels"][0]["license_source"] = "fixture/module.py"
        inventory["wheels"][0]["spdx_license"] = "BOGUS-SPDX"
        licenses["licenses"][0]["source"] = "fixture/module.py"
        licenses["licenses"][0]["target"] = "licenses/fixture-1.0.0-module.py"
        inventory_path.write_bytes(
            (json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        )
        license_path.write_bytes(
            (json.dumps(licenses, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        )
        report = artifact_size_report.build_report(
            package, inventory_path, license_path, extension / "artifact-budgets.json"
        )
        (package_dir / "artifact-size.json").write_bytes(
            artifact_size_report.canonical_json(report)
        )
        with self.assertRaisesRegex(ValueError, "wheel inventory does not match tagged dependencies"):
            verify_artifact(
                package_dir,
                extension,
                self.tag,
                metadata_mode="package-ci",
                budget_path=extension / "artifact-budgets.json",
            )

        inventory["wheels"][0]["license_source"] = "fixture-1.0.0.dist-info/LICENSE.txt"
        inventory["wheels"][0]["spdx_license"] = "MIT"
        licenses["licenses"][0]["source"] = "fixture-1.0.0.dist-info/LICENSE.txt"
        licenses["licenses"][0]["target"] = "licenses/fixture-1.0.0-LICENSE.txt"
        inventory_path.write_bytes(
            (json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        )
        license_path.write_bytes(
            (json.dumps(licenses, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        )
        report = artifact_size_report.build_report(
            package, inventory_path, license_path, extension / "artifact-budgets.json"
        )

        report["package"]["bytes"] += 1
        (package_dir / "artifact-size.json").write_bytes(
            artifact_size_report.canonical_json(report)
        )
        with self.assertRaisesRegex(ValueError, "artifact-size metadata"):
            verify_artifact(
                package_dir,
                extension,
                self.tag,
                metadata_mode="package-ci",
                budget_path=extension / "artifact-budgets.json",
            )

        release_assets = self.artifact_dir / "release-assets"
        release_assets.mkdir()
        for name in (package.name, "chemblender-2.3.0-alpha.1.sha256"):
            (release_assets / name).write_bytes((package_dir / name).read_bytes())
        self.assertEqual(
            verify_artifact(
                release_assets, extension, self.tag, metadata_mode="release-assets"
            )["package_sha256"],
            checksum,
        )


if __name__ == "__main__":
    unittest.main()
