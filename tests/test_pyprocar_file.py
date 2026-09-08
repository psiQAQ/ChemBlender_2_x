"""Synthetic boundary cases; the opt-in dependency gate uses the real cached VASP run."""

import importlib.util
import itertools
import json
import unittest
from concurrent.futures import CancelledError
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy as np

from ChemBlender.core import QCProject, close_project, open_project, save_project
from ChemBlender.core import pyprocar_file as adapter


TEXTS = {
    "INCAR": "ISPIN = 1\nLNONCOLLINEAR = .FALSE.\n",
    "KPOINTS": "Synthetic mesh\n0\nGamma\n3 3 3\n0 0 0\n",
    "POSCAR": "Synthetic Si\n1.0\n2 0 0\n0 2 0\n0 0 2\nSi\n1\nDirect\n0 0 0\n",
    "OUTCAR": "Synthetic VASP input for mocked parser\nVRHFIN =Si: s2p2\nions per type = 1\nNKPTS = 27 NBANDS= 4\nISPIN = 1\nposition of ions in fractional coordinates (direct lattice)\n0 0 0\n",
    "PROCAR": "Synthetic mock\nmetadata\nbody\n",
}


def write_inputs(directory, texts=None):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    for name, text in (TEXTS if texts is None else texts).items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def synthetic_arrays():
    points = np.asarray(list(itertools.product(range(3), repeat=3)), dtype=float) / 3
    energies = np.zeros((27, 4, 1))
    energies[:, 0, 0], energies[:, 2, 0] = 1., 9.
    energies[:, 1, 0] = 5.75 + np.sin(2 * np.pi * points[:, 0]) - .1
    energies[:, 3, 0] = 5.75 + np.cos(2 * np.pi * points[:, 1])
    return points, energies


class FakeOutcar:
    def __init__(self, path):
        self.reciprocal_lattice = np.eye(3) / 2
        self.efermi, self.version, self.rotations = 5.75, "mock", None


class FakePoscar:
    def __init__(self, path):
        self.lattice, self.coordinates, self.atoms = np.eye(3) * 2, np.zeros((1, 3)), ["Si"]


class FakeProcar:
    def __init__(self, path):
        self.kpoints, self.bands = synthetic_arrays()
        self.ionsCount = 1


class FakeSurface:
    calls = []

    def __init__(self, **kwargs):
        self.calls.append(kwargs)
        self.points = np.array([[.1, .2, .3], [.3, .2, .3], [.2, .4, .3]])
        self.faces = np.array([3, 0, 1, 2])


def mocked_readers():
    return patch.object(adapter, "_readers", return_value=(FakeOutcar, FakePoscar, FakeProcar))


def mocked_surface():
    return patch.object(adapter, "_surface_backend", return_value=(FakeSurface, lambda *args: None))


class PyProcarFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = write_inputs(self.temp.name)
        FakeSurface.calls.clear()

    def test_absolute_energy_2pi_band_identity_and_provenance_roundtrip(self):
        events = []
        with mocked_readers(), mocked_surface():
            batch = adapter.parse_vasp_fermi(self.root, progress=lambda done, total: events.append((done, total)))
        structure = batch.structures[0]
        band, surface = batch.datasets
        np.testing.assert_allclose(band.reciprocal_lattice.values, np.eye(3) * np.pi)
        self.assertEqual(band.fermi_energy, 5.75)
        self.assertEqual(band.energy_reference.value, "absolute")
        self.assertEqual(surface.band_indices.values.tolist(), [1, 3])
        self.assertEqual(surface.properties, ())
        self.assertEqual(events, [(0, 2), (1, 2), (2, 2)])
        for call, index in zip(FakeSurface.calls, [1, 3]):
            self.assertEqual(call["isovalue"], 5.75)
            np.testing.assert_allclose(call["V_matrix"].ravel(), band.data.values[0, :, index])
            np.testing.assert_allclose(call["transform_matrix"], np.eye(3) * np.pi)
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(batch)
        cbq = self.root / "roundtrip.cbq"
        save_project(cbq, project)
        close_project(project)
        reopened = open_project(cbq)
        self.addCleanup(close_project, reopened)
        metadata = dict(reopened.provenance[batch.provenance[0].id].parameters)
        self.assertEqual(metadata["mesh_shape"], [3, 3, 3])
        self.assertFalse(metadata["mesh_path"])
        self.assertEqual(set(metadata["source_files"]), set(TEXTS))
        self.assertEqual(reopened.datasets[surface.id].structure_id, structure.id)
        self.assertEqual(reopened.datasets[surface.id].band_structure_id, band.id)

    def test_rejects_line_path_nonuniform_and_missing_mesh(self):
        with self.assertRaisesRegex(ValueError, "line path"):
            adapter._mesh_spec("path\n20\nLine-mode\nReciprocal\n")
        points, energies = synthetic_arrays()
        for candidate, values, regex in (
            (points[:-1], energies[:-1], "incomplete"),
            (points * .97, energies, "uniform"),
            (np.concatenate((points, points[:1])), np.concatenate((energies, energies[:1])), "duplicate"),
        ):
            with self.subTest(regex=regex), self.assertRaisesRegex(ValueError, regex):
                adapter._full_mesh(candidate, values, (3, 3, 3), np.zeros(3), None, np.eye(3))

    def test_expands_declared_symmetry_and_rejects_inconsistent_energies(self):
        points = np.asarray(list(itertools.product([0., 1 / 3], repeat=3)))
        energies = np.sum(np.cos(2 * np.pi * points), axis=1)[:, None, None]
        rotations = [np.diag(signs) for signs in itertools.product([-1, 1], repeat=3)]
        full, values, used = adapter._full_mesh(points, energies, (3, 3, 3), np.zeros(3), rotations, np.eye(3))
        self.assertEqual(len(full), 27)
        self.assertEqual(used, 8)
        np.testing.assert_allclose(values[:, 0, 0], np.sum(np.cos(2 * np.pi * full), axis=1), atol=1e-13)
        inconsistent_points = np.concatenate((points, [[-1 / 3, 0, 0]]))
        inconsistent_energies = np.concatenate((energies, [[[100.]]]))
        with self.assertRaisesRegex(ValueError, "energies disagree"):
            adapter._full_mesh(inconsistent_points, inconsistent_energies, (3, 3, 3), np.zeros(3), rotations, np.eye(3))

    def test_mesh_does_not_reverse_asymmetric_kpoint_energy_identity(self):
        points, energies = synthetic_arrays()
        full, values, _ = adapter._full_mesh(points, energies, (3, 3, 3), np.zeros(3), None, np.eye(3))
        np.testing.assert_allclose(values[:, 1, 0], 5.75 + np.sin(2 * np.pi * full[:, 0]) - .1)

    def test_marching_coordinates_preserve_offcenter_grid_location(self):
        coordinates = np.array([[3., 2., 1.], [4., 2., 1.], [3., 3., 1.]])
        def marching(matrix, level):
            self.assertEqual(matrix.shape, (7, 9, 11))
            self.assertEqual(level, 5.75)
            return coordinates.copy(), np.array([[0, 1, 2]]), None, None
        vertices, _, _, _ = adapter._marching_coordinates(np.zeros((3, 3, 3)), [.2, -.4, .6], [.1, .2, .3], [2, 3, 4], 5.75, marching)
        np.testing.assert_allclose(vertices, [[.3, -.6, -.3], [.4, -.6, -.3], [.3, -.4, -.3]])
        self.assertFalse(np.allclose(vertices.mean(axis=0), 0))

    def test_preflight_rejects_implicit_potcar_repair_spinor_and_gzip(self):
        for filename, replacement, regex in (
            ("POSCAR", TEXTS["POSCAR"].replace("\nSi\n1\n", "\n1\n"), "element symbols"),
            ("POSCAR", TEXTS["POSCAR"].replace("Direct", "Cartesian"), "Direct"),
            ("INCAR", "LSORBIT=.TRUE.\n", "spinor"),
            ("PROCAR", "stub\nmetadata\nband *** energy ****\n", "repair"),
        ):
            with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, regex):
                adapter._preflight({**TEXTS, filename: replacement})
        (self.root / "PROCAR.gz").write_bytes(b"must never read me")
        with self.assertRaisesRegex(ValueError, "ambiguous"), patch.object(adapter, "_readers") as readers:
            adapter.parse_vasp_fermi(self.root)
        readers.assert_not_called()

    def test_rejects_invalid_options_complex_energies_and_lattice_mismatch(self):
        for params in ({"spin_index": True}, {"interpolation_factor": 2}):
            with self.assertRaises(ValueError):
                adapter.parse_vasp_fermi(self.root, **params)
        with self.assertRaisesRegex(ValueError, "real"):
            adapter._full_mesh(*[np.zeros((27, 3)), np.ones((27, 1, 1), dtype=complex)], (3, 3, 3), np.zeros(3), None, np.eye(3))
        broken = FakeOutcar(None)
        broken.reciprocal_lattice *= 2 * np.pi
        with patch.object(adapter, "_readers", return_value=(lambda path: broken, FakePoscar, FakeProcar)), self.assertRaisesRegex(ValueError, "lattices"):
            adapter.parse_vasp_fermi(self.root)

    def test_rejects_mismatched_species_positions_and_output_dimensions(self):
        for text in (
            TEXTS["OUTCAR"].replace("VRHFIN =Si", "VRHFIN =C"),
            TEXTS["OUTCAR"].replace("\n0 0 0\n", "\n0.1 0 0\n"),
            TEXTS["OUTCAR"].replace("NBANDS= 4", "NBANDS= 9"),
            TEXTS["OUTCAR"].replace("ISPIN = 1", "ISPIN = 2"),
        ):
            with self.assertRaisesRegex(ValueError, "do not match"):
                adapter._validate_run_identity(text, FakePoscar(None), FakeProcar(None))

    def test_cancel_between_bands_and_surface_failure_never_returns_partial(self):
        cancelled = False
        def progress(done, total):
            nonlocal cancelled
            cancelled = done > 0
        with mocked_readers(), mocked_surface(), self.assertRaises(CancelledError):
            adapter.parse_vasp_fermi(self.root, is_cancelled=lambda: cancelled, progress=progress)
        self.assertEqual(len(FakeSurface.calls), 1)
        with mocked_readers(), patch.object(adapter, "_surface_backend", return_value=(lambda **kwargs: (_ for _ in ()).throw(RuntimeError("numeric failure")), lambda *args: None)), self.assertRaisesRegex(RuntimeError, "numeric failure"):
            adapter.parse_vasp_fermi(self.root)

    @unittest.skipUnless(importlib.util.find_spec("pyprocar") is not None, "optional pinned periodic worker dependencies are not installed")
    def test_real_cached_srvo3_vasp_run(self):
        source = Path(__file__).resolve().parents[1] / ".agents/cache/scientific-visualization/fermi"
        if not (source / "PROCAR").is_file():
            self.skipTest("license-restricted VASP text fixture is absent from private project cache")
        batch = adapter.parse_vasp_fermi(source)
        band, surface = batch.datasets
        self.assertEqual(band.data.shape, (1, 21 ** 3, 20))
        self.assertAlmostEqual(band.fermi_energy, 5.6990, places=4)
        self.assertGreater(surface.faces.shape[0], 100)
        self.assertEqual(batch.structures[0].atomic_numbers, (38, 23, 8, 8, 8))
        self.assertTrue(np.all(np.isfinite(surface.data.values)))
        np.testing.assert_allclose(band.reciprocal_lattice.values, np.eye(3) * 2 * np.pi / 3.84652, rtol=1e-6)


if __name__ == "__main__":
    unittest.main()
