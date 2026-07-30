import contextlib
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ChemBlender" / "scripts" / "dependency_inventory.py"
sys.path.insert(0, str(SCRIPT.parent))

import dependency_inventory


class DependencyInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.wheels = self.root / "wheels"
        self.wheels.mkdir()
        self.inventory = self.root / "dependencies.toml"
        self.output = self.root / "wheel-inventory.json"
        self.licenses = self.root / "wheel-license-copy-list.json"
        self.wheel = self.wheels / "fixture-1.0.0-py3-none-any.whl"

    def tearDown(self):
        self.temporary.cleanup()

    def _write_wheel(
        self, entries: dict[str, bytes] | list[tuple[str, bytes]]
    ) -> tuple[str, int, int]:
        filename = "fixture-1.0.0-py3-none-any.whl"
        with zipfile.ZipFile(self.wheel, "w", zipfile.ZIP_DEFLATED) as archive:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                for name, data in (
                    entries.items() if isinstance(entries, dict) else entries
                ):
                    archive.writestr(name, data)
        with zipfile.ZipFile(self.wheel) as archive:
            unpacked_bytes = sum(info.file_size for info in archive.infolist())
        return (
            hashlib.sha256(self.wheel.read_bytes()).hexdigest(),
            self.wheel.stat().st_size,
            unpacked_bytes,
        )

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

    def _run_main(
        self,
        *,
        output: Path | None = None,
        licenses: Path | None = None,
    ) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = dependency_inventory.main(
                [
                    "--inventory",
                    str(self.inventory),
                    "--wheel-dir",
                    str(self.wheels),
                    "--output",
                    str(output or self.output),
                    "--license-copy-list",
                    str(licenses or self.licenses),
                ]
            )
        return result, stdout.getvalue()

    def _prepare_valid_inventory(self) -> None:
        sha256, compressed, unpacked = self._write_wheel(
            {"fixture-1.0.0.dist-info/LICENSE.txt": b"fixture license\n"}
        )
        self._write_inventory(sha256, compressed, unpacked)

    def _assert_outputs_unchanged(self) -> None:
        self.assertEqual(self.output.read_bytes(), b"old inventory")
        self.assertEqual(self.licenses.read_bytes(), b"old licenses")
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

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

    def test_cli_rejects_exact_schema_violations_before_outputs(self):
        self._prepare_valid_inventory()
        valid = self.inventory.read_text(encoding="utf-8")
        duplicate = valid + valid[valid.index("[[dependency]]") :]
        cases = (
            ("unknown root", 'unknown = "x"\n' + valid),
            ("wrong root table", 'schema_version = "1"\ndependency = {}\n'),
            ("wrong schema version", valid.replace('schema_version = "1"', "schema_version = 1")),
            ("extra field", valid + 'extra = "x"\n'),
            ("missing field", valid.replace('spdx_license = "MIT"\n', "")),
            ("wrong bool type", valid.replace("required = true", "required = 1")),
            ("unsafe text", valid.replace('distribution = "fixture"', 'distribution = "f\u2603"')),
            ("empty text", valid.replace('version = "1.0.0"', 'version = ""')),
            ("zero budget", valid.replace("max_compressed_bytes = ", "max_compressed_bytes = 0 # ")),
            ("duplicate record", duplicate),
            ("path-like filename", valid.replace('filename = "fixture-1.0.0-py3-none-any.whl"', 'filename = "dir/fixture.whl"')),
        )
        for name, text in cases:
            with self.subTest(name=name):
                self.output.write_bytes(b"old inventory")
                self.licenses.write_bytes(b"old licenses")
                self.inventory.write_text(text, encoding="utf-8", newline="\n")

                result = self._run_cli()

                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("invalid dependency inventory schema", result.stdout)
                self._assert_outputs_unchanged()

    def test_cli_rejects_nul_special_or_nonregular_license_members(self):
        cases = (
            ("nul", None, "unsafe wheel member path"),
            ("symlink", stat.S_IFLNK | 0o777, "unsafe wheel member type"),
            ("fifo", stat.S_IFIFO | 0o644, "unsafe wheel member type"),
            ("license directory", stat.S_IFDIR | 0o755, "license source must be a regular wheel member"),
        )
        for name, mode, error in cases:
            with self.subTest(name=name):
                if name == "license directory":
                    license = zipfile.ZipInfo("fixture-1.0.0.dist-info/LICENSE.txt")
                    license.create_system = 3
                    license.external_attr = mode << 16
                    entries = [(license, b"fixture license\n")]
                else:
                    entries = [("fixture-1.0.0.dist-info/LICENSE.txt", b"fixture license\n")]
                    if mode is not None:
                        special = zipfile.ZipInfo("special")
                        special.create_system = 3
                        special.external_attr = mode << 16
                        entries.append((special, b"target"))
                    else:
                        entries.append(("nulXmember", b"bad"))
                _, compressed, unpacked = self._write_wheel(entries)
                if name == "nul":
                    data = self.wheel.read_bytes().replace(b"nulXmember", b"nul\x00member")
                    self.wheel.write_bytes(data)
                sha256 = hashlib.sha256(self.wheel.read_bytes()).hexdigest()
                self._write_inventory(sha256, compressed, unpacked)

                result = self._run_cli()

                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(error, result.stdout)

    def test_cli_missing_output_parent_preserves_existing_outputs(self):
        self._prepare_valid_inventory()
        self.output.write_bytes(b"old inventory")
        self.licenses.write_bytes(b"old licenses")

        result, stdout = self._run_main(licenses=self.root / "missing" / "licenses.json")

        self.assertEqual(result, 1)
        self.assertIn("output parent does not exist", stdout)
        self._assert_outputs_unchanged()

    def test_cli_rejects_nonregular_wheel_path(self):
        self._prepare_valid_inventory()
        self.wheel.unlink()
        self.wheel.mkdir()

        result = self._run_cli()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("wheel path must be an ordinary file within wheel directory", result.stdout)

    def test_cli_second_output_write_failure_restores_existing_outputs(self):
        self._prepare_valid_inventory()
        self.output.write_bytes(b"old inventory")
        self.licenses.write_bytes(b"old licenses")
        original = dependency_inventory._write_json
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected write failure")
            return original(*args, **kwargs)

        with mock.patch.object(dependency_inventory, "_write_json", side_effect=fail_second):
            result, stdout = self._run_main()

        self.assertEqual(result, 1)
        self.assertIn("output write failed", stdout)
        self._assert_outputs_unchanged()

    def test_cli_second_replace_failure_restores_existing_outputs(self):
        self._prepare_valid_inventory()
        self.output.write_bytes(b"old inventory")
        self.licenses.write_bytes(b"old licenses")
        real_replace = os.replace
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected replace failure")
            return real_replace(source, destination)

        with mock.patch.object(dependency_inventory, "os", os, create=True), mock.patch.object(
            os, "replace", side_effect=fail_second
        ):
            result, stdout = self._run_main()

        self.assertEqual(result, 1)
        self.assertIn("output replace failed", stdout)
        self._assert_outputs_unchanged()

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
