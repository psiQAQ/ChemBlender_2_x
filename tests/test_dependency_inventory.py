import hashlib
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
import warnings
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ChemBlender" / "scripts" / "dependency_inventory.py"


class DependencyInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.wheels = self.root / "wheels"
        self.wheels.mkdir()
        self.inventory = self.root / "dependencies.toml"
        self.output = self.root / "wheel-inventory.json"
        self.licenses = self.root / "wheel-license-copy-list.json"

    def tearDown(self):
        self.temporary.cleanup()

    def _write_wheel(
        self, entries: dict[str, bytes] | list[tuple[str, bytes]]
    ) -> tuple[str, int, int]:
        filename = "fixture-1.0.0-py3-none-any.whl"
        wheel = self.wheels / filename
        with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as archive:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                for name, data in (
                    entries.items() if isinstance(entries, dict) else entries
                ):
                    archive.writestr(name, data)
        with zipfile.ZipFile(wheel) as archive:
            unpacked_bytes = sum(info.file_size for info in archive.infolist())
        return hashlib.sha256(wheel.read_bytes()).hexdigest(), wheel.stat().st_size, unpacked_bytes

    def _write_inventory(
        self,
        sha256: str,
        compressed: int,
        unpacked: int,
        *,
        include_optional: bool = False,
        max_compressed: int | None = None,
        max_unpacked: int | None = None,
        expected_sha256: str | None = None,
        license_source: str = "fixture-1.0.0.dist-info/LICENSE.txt",
    ) -> None:
        lines = [
            'schema_version = "1"',
            "",
            "[[dependency]]",
            'distribution = "fixture"',
            'version = "1.0.0"',
            'filename = "fixture-1.0.0-py3-none-any.whl"',
            'platform = "any"',
            'python_abi = "py3-none-any"',
            'url = "https://example.invalid/fixture-1.0.0-py3-none-any.whl"',
            f'sha256 = "{expected_sha256 or sha256}"',
            'spdx_license = "MIT"',
            f'license_source = "{license_source}"',
            "required = true",
            f"max_compressed_bytes = {max_compressed if max_compressed is not None else compressed}",
            f"max_unpacked_bytes = {max_unpacked if max_unpacked is not None else unpacked}",
            "",
        ]
        if include_optional:
            lines.extend(
                (
                    "[[dependency]]",
                    'distribution = "external"',
                    'version = "1.0.0"',
                    'filename = "external-1.0.0-py3-none-any.whl"',
                    'platform = "any"',
                    'python_abi = "py3-none-any"',
                    'url = "https://example.invalid/external-1.0.0-py3-none-any.whl"',
                    'sha256 = "0000000000000000000000000000000000000000000000000000000000000000"',
                    'spdx_license = "MIT"',
                    'license_source = "external-1.0.0.dist-info/LICENSE.txt"',
                    "required = false",
                    "max_compressed_bytes = 1",
                    "max_unpacked_bytes = 1",
                    "",
                )
            )
        self.inventory.write_text(
            "\n".join(lines),
            encoding="utf-8",
            newline="\n",
        )

    def _run_cli(self, *extra_args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (
                sys.executable,
                str(SCRIPT),
                "--inventory",
                str(self.inventory),
                "--wheel-dir",
                str(self.wheels),
                "--output",
                str(self.output),
                "--license-copy-list",
                str(self.licenses),
                *extra_args,
            ),
            cwd=ROOT,
            check=False,
            capture_output=True,
            encoding="utf-8",
        )

    def test_cli_writes_hash_verified_canonical_inventory_and_license_copy_list(self):
        sha256, compressed, unpacked = self._write_wheel(
            {
                "fixture/__init__.py": b"value = 1\n",
                "fixture-1.0.0.dist-info/LICENSE.txt": b"fixture license\n",
            }
        )
        self._write_inventory(sha256, compressed, unpacked)

        result = self._run_cli()

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload, json.loads(self.output.read_text(encoding="utf-8")))
        self.assertEqual(
            self.output.read_text(encoding="utf-8"),
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n",
        )
        self.assertEqual(
            json.loads(self.licenses.read_text(encoding="utf-8")),
            {
                "licenses": [
                    {
                        "distribution": "fixture",
                        "filename": "fixture-1.0.0-py3-none-any.whl",
                        "source": "fixture-1.0.0.dist-info/LICENSE.txt",
                        "target": "licenses/fixture-1.0.0-LICENSE.txt",
                        "version": "1.0.0",
                    }
                ]
            },
        )

    def test_cli_rejects_manifest_wheel_not_in_required_inventory(self):
        sha256, compressed, unpacked = self._write_wheel(
            {"fixture-1.0.0.dist-info/LICENSE.txt": b"fixture license\n"}
        )
        self._write_inventory(sha256, compressed, unpacked, include_optional=True)
        manifest = self.root / "blender_manifest.toml"
        manifest.write_text(
            "wheels = [\n"
            '  "./wheels/fixture-1.0.0-py3-none-any.whl",\n'
            '  "./wheels/external-1.0.0-py3-none-any.whl",\n'
            "]\n",
            encoding="utf-8",
            newline="\n",
        )

        result = self._run_cli("--manifest", str(manifest))

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("manifest wheel paths must equal required inventory", result.stdout)

    def test_cli_rejects_hash_mismatch_or_missing_license_source(self):
        cases = (
            ("hash", {"expected_sha256": "0" * 64}, "wheel hash mismatch"),
            (
                "license",
                {"license_source": "fixture-1.0.0.dist-info/MISSING.txt"},
                "license source missing",
            ),
        )
        for name, inventory_args, error in cases:
            with self.subTest(name=name):
                sha256, compressed, unpacked = self._write_wheel(
                    {"fixture-1.0.0.dist-info/LICENSE.txt": b"fixture license\n"}
                )
                self._write_inventory(sha256, compressed, unpacked, **inventory_args)

                result = self._run_cli()

                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(error, result.stdout)

    def test_cli_rejects_unsafe_or_duplicate_wheel_member_paths(self):
        cases = (
            ("traversal", "../escape.txt", "unsafe wheel member path"),
            ("absolute", "/escape.txt", "unsafe wheel member path"),
            ("drive", r"C:\\escape.txt", "unsafe wheel member path"),
            ("duplicate", "fixture/data.txt", "duplicate wheel member path"),
        )
        for name, bad_member, expected_error in cases:
            with self.subTest(name=name):
                entries: list[tuple[str, bytes]] = [
                    ("fixture-1.0.0.dist-info/LICENSE.txt", b"fixture license\n"),
                    (bad_member, b"bad"),
                ]
                if name == "duplicate":
                    entries.append((bad_member, b"duplicate"))
                sha256, compressed, unpacked = self._write_wheel(entries)
                self._write_inventory(sha256, compressed, unpacked)

                result = self._run_cli()

                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(expected_error, result.stdout)

    def test_cli_rejects_wheel_over_approved_size_budget(self):
        for budget, error in (
            ("compressed", "compressed size exceeds budget"),
            ("unpacked", "unpacked size exceeds budget"),
        ):
            with self.subTest(budget=budget):
                sha256, compressed, unpacked = self._write_wheel(
                    {"fixture-1.0.0.dist-info/LICENSE.txt": b"fixture license\n"}
                )
                self._write_inventory(
                    sha256,
                    compressed,
                    unpacked,
                    **{f"max_{budget}": (compressed if budget == "compressed" else unpacked) - 1},
                )

                result = self._run_cli()

                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(error, result.stdout)

    def test_cli_allows_canonical_wheel_directory_entries(self):
        sha256, compressed, unpacked = self._write_wheel(
            [
                ("fixture/", b""),
                ("fixture-1.0.0.dist-info/LICENSE.txt", b"fixture license\n"),
            ]
        )
        self._write_inventory(sha256, compressed, unpacked)

        result = self._run_cli()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_repository_manifest_matches_required_inventory(self):
        with (ROOT / "ChemBlender" / "dependencies.toml").open("rb") as handle:
            dependencies = tomllib.load(handle)["dependency"]
        with (ROOT / "ChemBlender" / "blender_manifest.toml").open("rb") as handle:
            manifest = tomllib.load(handle)

        required = [dependency for dependency in dependencies if dependency["required"]]
        optional = [dependency for dependency in dependencies if not dependency["required"]]
        self.assertTrue({"rdkit", "gemmi"}.issubset({item["distribution"] for item in required}))
        self.assertEqual(
            {f"./wheels/{dependency['filename']}" for dependency in required},
            set(manifest["wheels"]),
        )
        self.assertTrue(required)
        for dependency in required:
            with self.subTest(distribution=dependency["distribution"]):
                for field in (
                    "distribution",
                    "version",
                    "filename",
                    "platform",
                    "python_abi",
                    "url",
                    "sha256",
                    "spdx_license",
                    "license_source",
                    "max_compressed_bytes",
                    "max_unpacked_bytes",
                ):
                    self.assertTrue(dependency[field])
        self.assertTrue(
            {f"./wheels/{dependency['filename']}" for dependency in optional}.isdisjoint(
                manifest["wheels"]
            )
        )


if __name__ == "__main__":
    unittest.main()
