"""Legacy Blender extraction publishes standalone CBQ and recovery evidence."""

from concurrent.futures import CancelledError
import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy

from cbq_core.sidecar import close_project, open_project
from chemblender_prepare.core.package_upgrade import upgrade_project
from chemblender_prepare.legacy.export import export_legacy_scene
from chemblender_prepare.legacy.extraction import LegacyExtractionReport
from tests.test_legacy_migration_core import molecule_snapshot
from tests.test_legacy_migration_blender import FIXTURE_HASHES, FIXTURES, blender_executable

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "chemblender_prepare/legacy/__main__.py"


class LegacyExportTests(unittest.TestCase):
    def test_cancel_failure_and_source_change_publish_nothing(self):
        source = FIXTURES / "chemblender-2.1-molecule.blend"
        extraction = LegacyExtractionReport((molecule_snapshot(),), (), str(source), True,
                                           hashlib.sha256(source.read_bytes()).hexdigest())
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            cancel = root / "cancel"
            cancel.touch()
            with patch("chemblender_prepare.legacy.export.extract_legacy_objects") as extract:
                with self.assertRaises(CancelledError):
                    export_legacy_scene(root / "cancelled", cancel_file=cancel)
                extract.assert_not_called()
            cancel.unlink()
            with patch("chemblender_prepare.legacy.export.extract_legacy_objects", return_value=extraction):
                with patch("chemblender_prepare.legacy.export.save_project", side_effect=OSError("disk failure")):
                    with self.assertRaisesRegex(OSError, "disk failure"):
                        export_legacy_scene(root / "failed")
                with patch("chemblender_prepare.legacy.export._hash", return_value="0" * 64):
                    with self.assertRaisesRegex(ValueError, "source .blend changed"):
                        export_legacy_scene(root / "changed")
            self.assertEqual(tuple(root.iterdir()), ())

    def test_native_external_export_never_changes_original_scene(self):
        blender = blender_executable()
        if blender is None:
            self.skipTest("Blender 5.1 executable unavailable")
        for name, expected_hash in FIXTURE_HASHES.items():
            with self.subTest(fixture=name), TemporaryDirectory() as temporary:
                fixture = FIXTURES / name
                self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), expected_hash)
                result = subprocess.run([str(blender), "--background", "--factory-startup",
                    "--disable-autoexec", "--python-exit-code", "1", str(fixture),
                    "--python", str(ROOT / "tests/blender_legacy_migrate.py"),
                    "--", str(ROOT), "--external-only"],
                    env=dict(os.environ, BLENDER_USER_RESOURCES=temporary, PYTHONNOUSERSITE="1"),
                    capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("LEGACY_EXTERNAL_SCENE_UNCHANGED", result.stdout)

    def test_real_blends_preview_export_reopen_and_protect_existing_output(self):
        blender = blender_executable()
        if blender is None:
            self.skipTest("Blender 5.1 executable unavailable")
        for name, source_hash in FIXTURE_HASHES.items():
            with self.subTest(fixture=name), TemporaryDirectory(prefix="cb-legacy-export-") as temporary:
                root = Path(temporary)
                output = root / "prepared"
                fixture = FIXTURES / name
                self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), source_hash)
                env = dict(os.environ, BLENDER_USER_RESOURCES=str(root / "profile"))
                command = [str(blender), "--background", "--factory-startup", "--disable-autoexec",
                           "--python-exit-code", "1", str(fixture), "--python", str(SCRIPT),
                           "--", "--output", str(output)]
                preview = subprocess.run([*command, "--preview"], env=env, capture_output=True, text=True)
                self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
                self.assertFalse(output.exists())
                exported = subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
                report = json.loads((output / "migration.json").read_text(encoding="utf-8"))
                manifest = output / "project.cbq/manifest.json"
                self.assertEqual(report["manifest_sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
                self.assertEqual(report["source_sha256"], source_hash)
                self.assertEqual(report["display_restore_status"], "recorded_only")
                project = open_project(output / "project.cbq", verify_arrays=True)
                try:
                    self.assertEqual(project.schema_version, "1.1")
                    provenance = next(iter(project.provenance.values()))
                    self.assertEqual((provenance.producer, provenance.producer_version), ("chemblender_prepare", "0.1.0"))
                    structure = next(iter(project.structures.values()))
                    self.assertEqual(report["views"][0]["structure_id"], str(structure.id))
                    self.assertEqual(structure.coordinates.unit, "angstrom")
                    settings = report["views"][0]["settings"]
                    if "crystal" in name:
                        self.assertEqual(report["requires_numeric_symmetry_upgrade"], [str(structure.id)])
                        self.assertAlmostEqual(float(structure.periodic.occupancies.values[0]), .75)
                        numpy.testing.assert_allclose(structure.periodic.anisotropic_displacements.values[0],
                                                      [.011, .013, .017, .003, .002, .001], atol=1e-8)
                        upgraded = upgrade_project(project)
                        prepared = upgraded.structures[structure.id]
                        self.assertIsNotNone(prepared.periodic.symmetry_rotations)
                        numpy.testing.assert_array_equal(prepared.coordinates.values, structure.coordinates.values)
                    else:
                        self.assertEqual(report["requires_numeric_symmetry_upgrade"], [])
                        topology = next(iter(project.topologies.values()))
                        self.assertEqual(float(topology.bond_orders.values[0]), 2)
                        if "edited" in name:
                            self.assertEqual(structure.atomic_numbers[0], 7)
                            numpy.testing.assert_allclose(structure.coordinates.values[0], [-1, .15, 0], atol=1e-7)
                            self.assertAlmostEqual(settings["atom_scales"][0], 1.4)
                            self.assertTrue(settings["dashed"][0])
                        else:
                            self.assertEqual(structure.atomic_numbers, (6, 8, 1, 1))
                            numpy.testing.assert_allclose(settings["radii"], [.76, .66, .31, .31], atol=1e-7)
                finally:
                    close_project(project)
                before = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
                repeated = subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertNotEqual(repeated.returncode, 0)
                self.assertEqual(before, {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()})
                self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), source_hash)


if __name__ == "__main__":
    unittest.main()
