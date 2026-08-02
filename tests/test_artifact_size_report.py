import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "ChemBlender" / "scripts"
BUDGET = ROOT / ".github" / "artifact-budgets.json"
sys.path.insert(0, str(SCRIPTS))

import artifact_size_report


class ArtifactSizeReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package = self.root / "chemblender.zip"
        self.inventory = self.root / "wheel-inventory.json"
        self.license_list = self.root / "wheel-license-copy-list.json"
        self.budget = self.root / "artifact-budgets.json"
        self.output = self.root / "artifact-size.json"

    def tearDown(self):
        self.temporary.cleanup()

    def _wheel(self, distribution, version, license_source, payload=b"module"):
        filename = f"{distribution}-{version}-py3-none-any.whl"
        path = self.root / filename
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr(f"{distribution}/module.py", payload)
            archive.writestr(license_source, b"license")
        wheel_bytes = path.read_bytes()
        with zipfile.ZipFile(path) as archive:
            unpacked_bytes = sum(info.file_size for info in archive.infolist())
        return {
            "distribution": distribution,
            "version": version,
            "filename": filename,
            "sha256": hashlib.sha256(wheel_bytes).hexdigest(),
            "spdx_license": "MIT",
            "license_source": license_source,
            "compressed_bytes": len(wheel_bytes),
            "unpacked_bytes": unpacked_bytes,
            "wheel_bytes": wheel_bytes,
        }

    def _write_package(self, entries):
        with zipfile.ZipFile(self.package, "w", zipfile.ZIP_STORED) as archive:
            for name, contents in entries:
                archive.writestr(name, contents)

    def _write_inventory(self, wheels):
        inventory = {"wheels": []}
        licenses = {"licenses": []}
        for wheel in sorted(wheels, key=lambda item: item["filename"]):
            inventory["wheels"].append(
                {
                    key: wheel[key]
                    for key in (
                        "compressed_bytes",
                        "distribution",
                        "filename",
                        "license_source",
                        "sha256",
                        "spdx_license",
                        "unpacked_bytes",
                        "version",
                    )
                }
            )
            licenses["licenses"].append(
                {
                    "distribution": wheel["distribution"],
                    "filename": wheel["filename"],
                    "source": wheel["license_source"],
                    "target": (
                        f"licenses/{wheel['distribution']}-{wheel['version']}-"
                        f"{Path(wheel['license_source']).name}"
                    ),
                    "version": wheel["version"],
                }
            )
        self.inventory.write_text(
            json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        self.license_list.write_text(
            json.dumps(licenses, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    def _section_unpacked_baselines(self):
        baselines = {"code": 0, "resources": 0, "wheels": 0, "other": 0}
        with zipfile.ZipFile(self.package) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if info.filename.startswith("wheels/"):
                    section = "wheels"
                elif info.filename == "src/code.py":
                    section = "code"
                elif info.filename in {"LICENSE", "assets/Chem_Nodes.blend"}:
                    section = "resources"
                else:
                    section = "other"
                baselines[section] += info.file_size
        return baselines

    def _write_budget(self, baseline_bytes, **overrides):
        section_baselines = self._section_unpacked_baselines()
        budget = {
            "schema_version": "1",
            "baseline_package_bytes": baseline_bytes,
            "allowed_unexplained_growth_bytes": 0,
            "baseline_member_unpacked_bytes": sum(section_baselines.values()),
            "allowed_unexplained_member_unpacked_growth_bytes": 0,
            "max_member_unpacked_bytes": 30_000_000,
            "section_unpacked_budgets": {
                section: {
                    "baseline_unpacked_bytes": baseline,
                    "allowed_unexplained_growth_bytes": 0,
                }
                for section, baseline in section_baselines.items()
            },
            "existing_wheel_distributions": ["rdkit"],
            "new_wheel_budget": {
                "max_compressed_bytes_per_wheel": 10_000_000,
                "max_unpacked_bytes_per_wheel": 30_000_000,
                "max_compressed_bytes_total": 20_000_000,
                "approved_wheels": [
                    {
                        "distribution": "gemmi",
                        "rationale": "2.3.0 Priority 2 approved compact integration",
                    }
                ],
            },
        }
        budget.update(overrides)
        self.budget.write_text(
            json.dumps(budget, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    def _prepare_valid_package(self):
        rdkit = self._wheel(
            "rdkit", "1.0.0", "rdkit-1.0.0.dist-info/LICENSE.txt", b"rdkit"
        )
        gemmi = self._wheel(
            "gemmi", "1.0.0", "gemmi-1.0.0.dist-info/LICENSE.txt", b"gemmi"
        )
        self._write_package(
            (
                ("src/code.py", b"code"),
                ("assets/Chem_Nodes.blend", b"asset"),
                ("LICENSE", b"license"),
                ("README.txt", b"other"),
                (f"wheels/{rdkit['filename']}", rdkit["wheel_bytes"]),
                (f"wheels/{gemmi['filename']}", gemmi["wheel_bytes"]),
            )
        )
        self._write_inventory([rdkit, gemmi])
        self._write_budget(self.package.stat().st_size)
        return rdkit, gemmi

    def test_report_has_non_overlapping_sections_verified_wheels_and_baseline(self):
        rdkit, gemmi = self._prepare_valid_package()

        report = artifact_size_report.build_report(
            self.package, self.inventory, self.license_list, self.budget
        )

        self.assertEqual(report["package"]["bytes"], self.package.stat().st_size)
        self.assertEqual(
            report["package"]["sha256"],
            hashlib.sha256(self.package.read_bytes()).hexdigest(),
        )
        self.assertEqual(report["baseline"]["actual_growth_bytes"], 0)
        self.assertEqual(
            report["member_unpacked_budget"],
            {
                "actual_growth_bytes": 0,
                "allowed_unexplained_growth_bytes": 0,
                "baseline_unpacked_bytes": sum(
                    value["unpacked_bytes"] for value in report["sections"].values()
                ),
                "max_member_unpacked_bytes": 30_000_000,
            },
        )
        self.assertEqual(
            report["new_wheel_allowance"],
            {
                "approved_distributions": ["gemmi"],
                "compressed_bytes": gemmi["compressed_bytes"],
                "max_compressed_bytes": 20_000_000,
                "unpacked_bytes": gemmi["unpacked_bytes"],
            },
        )
        sections = report["sections"]
        self.assertEqual(
            {section: [member["path"] for member in value["members"]]
             for section, value in sections.items()},
            {
                "code": ["src/code.py"],
                "resources": ["LICENSE", "assets/Chem_Nodes.blend"],
                "wheels": [
                    f"wheels/{gemmi['filename']}",
                    f"wheels/{rdkit['filename']}",
                ],
                "other": ["README.txt"],
            },
        )
        members = [
            member
            for section in sections.values()
            for member in section["members"]
        ]
        self.assertEqual(len(members), 6)
        self.assertEqual(len({member["path"] for member in members}), 6)
        self.assertEqual(
            sum(member["compressed_bytes"] for member in members),
            report["package"]["member_compressed_bytes"],
        )
        self.assertEqual(
            sum(member["unpacked_bytes"] for member in members),
            report["package"]["member_unpacked_bytes"],
        )
        self.assertEqual(
            report["wheels"],
            [
                {
                    "distribution": "gemmi",
                    "filename": gemmi["filename"],
                    "license": {
                        "source": gemmi["license_source"],
                        "spdx_license": "MIT",
                        "target": "licenses/gemmi-1.0.0-LICENSE.txt",
                    },
                    "nested_compressed_bytes": 12,
                    "nested_unpacked_bytes": gemmi["unpacked_bytes"],
                    "outer_compressed_bytes": gemmi["compressed_bytes"],
                    "package_member": f"wheels/{gemmi['filename']}",
                    "sha256": gemmi["sha256"],
                    "wheel_bytes": gemmi["compressed_bytes"],
                },
                {
                    "distribution": "rdkit",
                    "filename": rdkit["filename"],
                    "license": {
                        "source": rdkit["license_source"],
                        "spdx_license": "MIT",
                        "target": "licenses/rdkit-1.0.0-LICENSE.txt",
                    },
                    "nested_compressed_bytes": 12,
                    "nested_unpacked_bytes": rdkit["unpacked_bytes"],
                    "outer_compressed_bytes": rdkit["compressed_bytes"],
                    "package_member": f"wheels/{rdkit['filename']}",
                    "sha256": rdkit["sha256"],
                    "wheel_bytes": rdkit["compressed_bytes"],
                },
            ],
        )

    def test_unsafe_or_duplicate_outer_members_are_rejected(self):
        self._prepare_valid_package()
        with zipfile.ZipFile(self.package, "a", zipfile.ZIP_STORED) as archive:
            archive.writestr("../outside.txt", b"unsafe")

        with self.assertRaisesRegex(ValueError, "unsafe archive member path"):
            artifact_size_report.build_report(
                self.package, self.inventory, self.license_list, self.budget
            )

    def test_uppercase_wheel_member_cannot_bypass_inventory_validation(self):
        self._prepare_valid_package()
        with zipfile.ZipFile(self.package, "a", zipfile.ZIP_STORED) as archive:
            archive.writestr("wheels/rogue.WHL", b"rogue")
        self._write_budget(self.package.stat().st_size)

        with self.assertRaisesRegex(ValueError, "package wheel members"):
            artifact_size_report.build_report(
                self.package, self.inventory, self.license_list, self.budget
            )

    def test_unpacked_bomb_is_rejected_before_zip_content_is_read(self):
        self._prepare_valid_package()
        with zipfile.ZipFile(self.package, "a", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("assets/highly-compressible.json", b"\0" * 64 * 1024 * 1024)

        with (
            mock.patch.object(
                zipfile.ZipFile,
                "testzip",
                side_effect=AssertionError("CRC validation must not run"),
            ),
            mock.patch.object(
                zipfile.ZipFile,
                "read",
                side_effect=AssertionError("member read must not run"),
            ),
            self.assertRaisesRegex(
                ValueError,
                "archive member unpacked size exceeds budget: assets/highly-compressible.json",
            ),
        ):
            artifact_size_report.build_report(
                self.package, self.inventory, self.license_list, self.budget
            )

    def test_duplicate_nested_wheel_members_are_rejected(self):
        rdkit, gemmi = self._prepare_valid_package()
        bad_wheel = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(bad_wheel, "w", zipfile.ZIP_STORED) as archive:
                archive.writestr("gemmi/module.py", b"gemmi")
                archive.writestr("gemmi-1.0.0.dist-info/LICENSE.txt", b"license")
                archive.writestr("gemmi-1.0.0.dist-info/LICENSE.txt", b"duplicate")
        gemmi["wheel_bytes"] = bad_wheel.getvalue()
        gemmi["sha256"] = hashlib.sha256(gemmi["wheel_bytes"]).hexdigest()
        gemmi["compressed_bytes"] = len(gemmi["wheel_bytes"])
        self._write_package(
            (
                (f"wheels/{rdkit['filename']}", rdkit["wheel_bytes"]),
                (f"wheels/{gemmi['filename']}", gemmi["wheel_bytes"]),
            )
        )
        self._write_inventory([rdkit, gemmi])
        self._write_budget(self.package.stat().st_size)

        with self.assertRaisesRegex(ValueError, "duplicate archive member path"):
            artifact_size_report.build_report(
                self.package, self.inventory, self.license_list, self.budget
            )

    def test_missing_or_unexplained_budget_fails_without_partial_output(self):
        self._prepare_valid_package()
        self.output.write_bytes(b"old report")
        budget = json.loads(self.budget.read_text(encoding="utf-8"))
        del budget["baseline_package_bytes"]
        self.budget.write_text(json.dumps(budget), encoding="utf-8")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = artifact_size_report.main(
                [
                    "--package", str(self.package),
                    "--wheel-inventory", str(self.inventory),
                    "--license-copy-list", str(self.license_list),
                    "--budget", str(self.budget),
                    "--output", str(self.output),
                ]
            )

        self.assertEqual(result, 1)
        self.assertIn("budget schema", stdout.getvalue())
        self.assertEqual(self.output.read_bytes(), b"old report")

    def test_package_growth_and_unapproved_wheels_fail_closed(self):
        self._prepare_valid_package()
        self._write_budget(self.package.stat().st_size - 1)
        with self.assertRaisesRegex(ValueError, "package growth exceeds budget"):
            artifact_size_report.build_report(
                self.package, self.inventory, self.license_list, self.budget
            )

        self._write_budget(
            self.package.stat().st_size,
            new_wheel_budget={
                "max_compressed_bytes_per_wheel": 10_000_000,
                "max_unpacked_bytes_per_wheel": 30_000_000,
                "max_compressed_bytes_total": 20_000_000,
                "approved_wheels": [],
            },
        )
        with self.assertRaisesRegex(ValueError, "new wheel is not approved"):
            artifact_size_report.build_report(
                self.package, self.inventory, self.license_list, self.budget
            )

    def test_cli_writes_canonical_report_only_after_all_checks_pass(self):
        self._prepare_valid_package()

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = artifact_size_report.main(
                [
                    "--package", str(self.package),
                    "--wheel-inventory", str(self.inventory),
                    "--license-copy-list", str(self.license_list),
                    "--budget", str(self.budget),
                    "--output", str(self.output),
                ]
            )

        self.assertEqual(result, 0)
        contents = self.output.read_bytes()
        self.assertTrue(contents.endswith(b"\n"))
        self.assertEqual(contents, stdout.getvalue().encode("utf-8"))
        self.assertEqual(
            contents,
            json.dumps(
                json.loads(contents), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            + b"\n",
        )

    def test_repository_budget_is_versioned_and_has_no_unexplained_growth(self):
        budget = artifact_size_report._load_budget(BUDGET)

        self.assertEqual(budget["baseline_package_bytes"], 29_967_890)
        self.assertEqual(budget["allowed_unexplained_growth_bytes"], 0)
        self.assertEqual(budget["baseline_member_unpacked_bytes"], 32_024_217)
        self.assertEqual(
            budget["allowed_unexplained_member_unpacked_growth_bytes"], 0
        )
        self.assertEqual(budget["max_member_unpacked_bytes"], 30_000_000)
        self.assertEqual(
            budget["section_unpacked_budgets"],
            {
                "code": {
                    "baseline_unpacked_bytes": 2_629_461,
                    "allowed_unexplained_growth_bytes": 0,
                },
                "resources": {
                    "baseline_unpacked_bytes": 2_506_004,
                    "allowed_unexplained_growth_bytes": 0,
                },
                "wheels": {
                    "baseline_unpacked_bytes": 26_888_752,
                    "allowed_unexplained_growth_bytes": 0,
                },
                "other": {
                    "baseline_unpacked_bytes": 0,
                    "allowed_unexplained_growth_bytes": 0,
                },
            },
        )
        self.assertEqual(budget["existing_wheel_distributions"], ["rdkit"])
        self.assertEqual(budget["approved_distributions"], ["gemmi"])
        self.assertEqual(budget["max_compressed_bytes_per_wheel"], 10_000_000)
        self.assertEqual(budget["max_unpacked_bytes_per_wheel"], 30_000_000)
        self.assertEqual(budget["max_compressed_bytes_total"], 20_000_000)


if __name__ == "__main__":
    unittest.main()
