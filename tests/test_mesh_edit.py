import unittest

from ChemBlender.ui.mesh_edit import measure_points


class LocalMeshMeasurementTests(unittest.TestCase):
    def test_distance_angle_and_invalid_geometry(self):
        self.assertEqual(measure_points(((0, 0, 0), (3, 4, 0))), (5, 'distance'))
        self.assertEqual(measure_points(((1, 0, 0), (0, 0, 0), (0, 1, 0))), (90, 'angle'))
        for points in (((0, 0, 0),), ((0, 0, 0), (float('nan'), 0, 0)),
                       ((0, 0, 0), (0, 0, 0), (1, 0, 0))):
            with self.subTest(points=points), self.assertRaises(ValueError):
                measure_points(points)


class NativeMeshEditingTests(unittest.TestCase):
    def test_native_selection_atom_bond_edit_and_measurement(self):
        import os
        from pathlib import Path
        import shutil
        import subprocess
        from tempfile import TemporaryDirectory

        root = Path(__file__).resolve().parents[1]
        executable = os.environ.get("BLENDER_EXECUTABLE") or shutil.which("blender")
        if not executable:
            candidate = Path("C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
            executable = str(candidate) if candidate.is_file() else None
        if executable is None:
            self.skipTest("Blender 5.1 executable unavailable")
        with TemporaryDirectory(prefix="cb-mesh-edit-") as profile:
            environment = dict(os.environ, BLENDER_USER_RESOURCES=profile, PYTHONNOUSERSITE="1")
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [executable, "--background", "--factory-startup", "--offline-mode",
                 "--python-exit-code", "1", "--python", str(root / "tests/blender_mesh_edit.py"),
                 "--", str(root)],
                env=environment, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MESH_EDIT_PASSED", result.stdout)
        self.assertIn("MESH_APPLY_PASSED", result.stdout)
