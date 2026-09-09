"""CBQ 1.1 preparation, historical integrity and NumPy-only symmetry display."""

from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy as np

from cbq_core.model import ArrayData, PeriodicSiteData, QCProject, Structure
from cbq_core.sidecar import SidecarIntegrityError, close_project, open_project, save_project
from chemblender_prepare.core.package_upgrade import upgrade_project
from tests.test_sidecar_storage import FIXTURES, sample_project, write_manifest

ROOT = Path(__file__).resolve().parents[1]
HAS_GEMMI = importlib.util.find_spec("gemmi") is not None


def crystal():
    beta = np.radians(104.0)
    cell = np.asarray(((4.0, 0, 0), (0, 5.0, 0), (6*np.cos(beta), 0, 6*np.sin(beta))))
    fractional = np.asarray(((0.13, 0.27, 0.39),))
    periodic = PeriodicSiteData(
        fractional_coordinates=ArrayData(fractional, ("atom", "xyz"), "dimensionless"),
        site_labels=("C1",),
        occupancies=ArrayData(np.ones(1), ("atom",), "dimensionless"),
        isotropic_displacements=None,
        anisotropic_displacements=ArrayData(np.asarray(((0.1, 0.2, 0.3, 0.01, 0.02, 0.03),)),
                                           ("atom", "tensor_component"), "angstrom_squared"),
        adp_types=("uani",), disorder_groups=(0,),
        declared_space_group_name=None, declared_space_group_number=None,
        symmetry_operations=("x,y,z", "-x,y+1/2,-z+1/2"), cif_envelope_id=None,
    )
    return Structure(uuid4(), "original-r1", (6,),
                     ArrayData(fractional @ cell, ("atom", "xyz"), "angstrom"),
                     ArrayData(cell, ("cell_vector", "xyz"), "angstrom"), periodic)


def crystal_project():
    structure = crystal()
    return QCProject(uuid4(), "1.0", structures={structure.id: structure})


def legacy_package(root, project, version="1.0"):
    save_project(root, project)
    path = root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["manifest_version"] = version
    manifest["project_schema_version"] = version
    manifest["project"]["schema_version"] = version
    for _key, structure in manifest["project"]["structures"]["$dict"]:
        periodic = structure["periodic"]
        if periodic is not None:
            periodic.pop("symmetry_rotations", None)
            periodic.pop("symmetry_translations", None)
    write_manifest(path, manifest)
    return root


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class NumericSymmetryTests(unittest.TestCase):
    def numeric(self, rotations=None, translations=None):
        r = np.asarray((np.eye(3, dtype=int), np.diag((-1, 1, -1)))) if rotations is None else rotations
        t = np.asarray(((0, 0, 0), (0, 0.5, 0.5))) if translations is None else translations
        return replace(crystal().periodic,
            symmetry_rotations=ArrayData(r, ("symmetry_operation", "row", "column"), "dimensionless"),
            symmetry_translations=ArrayData(t, ("symmetry_operation", "xyz"), "dimensionless"))

    def test_pair_count_dtype_finiteness_determinant_and_finite_order(self):
        periodic = self.numeric()
        with self.assertRaisesRegex(ValueError, "paired"):
            replace(periodic, symmetry_translations=None)
        invalid_rotations = (
            np.ones((1, 3, 3), dtype=int),
            np.broadcast_to(np.eye(3), (2, 3, 3)).copy(),
            np.asarray((np.eye(3, dtype=int), np.diag((2, 1, 1)))),
            np.asarray((np.eye(3, dtype=int), ((1, 1, 0), (0, 1, 0), (0, 0, 1)))),
        )
        for value in invalid_rotations:
            with self.subTest(rotation=value), self.assertRaises(ValueError):
                self.numeric(rotations=value)
        for value in (np.zeros((1, 3)), np.full((2, 3), np.nan), np.full((2, 3), np.inf)):
            with self.subTest(translation=value), self.assertRaises(ValueError):
                self.numeric(translations=value)

    def test_crystallographic_order_three_in_skew_basis_is_accepted(self):
        r = np.asarray((np.eye(3, dtype=int), ((0, -1, 0), (1, -1, 0), (0, 0, 1))))
        self.numeric(rotations=r)

    @unittest.skipUnless(HAS_GEMMI, "External Gemmi unavailable")
    def test_gemmi_preserves_order_and_unwrapped_translation(self):
        import gemmi
        from chemblender_prepare.core.gemmi_adapter import numeric_symmetry_operations
        operations = ("-x,y+3/2,-z+1/2", "x,y,z", "-y,x-y,z+1/3")
        r, t = numeric_symmetry_operations(operations)
        point = np.asarray((0.13, 0.27, 0.39))
        for i, operation in enumerate(operations):
            np.testing.assert_allclose(r.values[i] @ point + t.values[i], gemmi.Op(operation).apply_to_xyz(point))
        self.assertEqual(t.values[0, 1], 1.5)

    @unittest.skipUnless(HAS_GEMMI, "External Gemmi unavailable")
    def test_invalid_triplet_fails_before_mutating_project(self):
        project = crystal_project()
        old = next(iter(project.structures.values()))
        project.structures[old.id] = replace(old, periodic=replace(old.periodic, symmetry_operations=("not-an-operation",)))
        with self.assertRaisesRegex(ValueError, "invalid symmetry operation"):
            upgrade_project(project)
        self.assertEqual(project.structures[old.id].revision, "original-r1")
        self.assertEqual(project.provenance, {})

    def test_empty_operations_do_not_infer_identity_or_load_gemmi(self):
        project = crystal_project()
        old = next(iter(project.structures.values()))
        project.structures[old.id] = replace(old, periodic=replace(old.periodic, symmetry_operations=()))
        with patch.dict(sys.modules, {"gemmi": None}):
            upgraded = upgrade_project(project)
        result = upgraded.structures[old.id]
        self.assertIsNone(result.periodic.symmetry_rotations)
        self.assertEqual(result.revision, old.revision)
        self.assertEqual(upgraded.provenance, {})

    @unittest.skipUnless(HAS_GEMMI, "External Gemmi unavailable")
    def test_nonorthogonal_expansion_and_adp_use_numeric_data_without_gemmi(self):
        from ChemBlender.views.periodic import PeriodicViewSettings, _derived_periodic_sites, _periodic_site_attributes
        project = crystal_project()
        upgraded = upgrade_project(project)
        structure = next(iter(upgraded.structures.values()))
        with patch.dict(sys.modules, {"gemmi": None}):
            derived = _derived_periodic_sites(structure, PeriodicViewSettings(representation="expanded_cell"))
            values, _ = _periodic_site_attributes(structure, source_atom_ids=derived["source_atom_ids"], rotations=derived["rotations"])
        self.assertEqual(derived["source_atom_ids"], (0,))
        np.testing.assert_allclose(derived["coordinates"], np.asarray(((0.87, 0.77, 0.11),)) @ structure.cell.values, atol=1e-12)
        np.testing.assert_allclose([values["cbq_"+name][0] for name in ("u11", "u22", "u33", "u12", "u13", "u23")],
                                   (0.1, 0.2, 0.3, -0.01, 0.02, -0.03), atol=1e-12)

    @unittest.skipUnless(HAS_GEMMI, "External Gemmi unavailable")
    def test_real_quartz_cif_operations_match_gemmi(self):
        import gemmi
        from chemblender_prepare.core.formats.cif import parse_cif
        batch = parse_cif(FIXTURES / "cif" / "quartz.cif")
        p = batch.structures[0].periodic
        self.assertGreater(len(p.symmetry_operations), 1)
        for index, operation in enumerate(p.symmetry_operations):
            np.testing.assert_allclose(np.asarray(p.fractional_coordinates.values) @ p.symmetry_rotations.values[index].T + p.symmetry_translations.values[index],
                                       [gemmi.Op(operation).apply_to_xyz(x) for x in p.fractional_coordinates.values])


class HistoricalIntegrityTests(unittest.TestCase):
    def test_v10_ordinary_fixture_retains_entity_identity_and_numbers(self):
        with patch.dict(sys.modules, {"gemmi": None}):
            project = open_project(FIXTURES / "sidecar" / "model-v10", expected_schema_version="1.0")
            try:
                upgraded = upgrade_project(project)
                self.assertEqual(upgraded.schema_version, "1.1")
                for key, structure in project.structures.items():
                    self.assertIs(upgraded.structures[key], structure)
                np.testing.assert_allclose(next(iter(project.structures.values())).coordinates.values,
                                           ((0, 0, 0), (0, 0, 0.74)))
            finally:
                close_project(project)

    def test_historical_manifest_hash_is_checked_before_migration(self):
        for version in ("0.2", "1.0", "1.1"):
            with self.subTest(version=version), TemporaryDirectory() as temporary:
                root = legacy_package(Path(temporary) / "old.cbq", sample_project(), version)
                manifest_path = root / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["project"]["schema_version"] = "tampered"
                write_manifest(manifest_path, manifest, update_hash=False)
                with self.assertRaisesRegex(SidecarIntegrityError, "manifest hash mismatch"):
                    open_project(root)

    def test_historical_array_hash_is_checked(self):
        for version in ("0.2", "1.0", "1.1"):
            with self.subTest(version=version), TemporaryDirectory() as temporary:
                root = legacy_package(Path(temporary) / "old.cbq", sample_project(), version)
                array = next(iter((root / "arrays").glob("*.npy")))
                value = np.load(array, allow_pickle=False)
                value.flat[0] += 1
                np.save(array, value, allow_pickle=False)
                with self.assertRaises(SidecarIntegrityError):
                    open_project(root)

    @unittest.skipUnless(HAS_GEMMI, "External Gemmi unavailable")
    def test_old_crystal_upgrade_preserves_input_identity_and_is_idempotent(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = legacy_package(directory / "old.cbq", crystal_project())
            before = hashes(root)
            project = open_project(root, expected_schema_version="1.0")
            try:
                old = next(iter(project.structures.values()))
                self.assertIsNone(old.periodic.symmetry_rotations)
                upgraded = upgrade_project(project)
                result = upgraded.structures[old.id]
                self.assertNotEqual(result.revision, old.revision)
                self.assertIs(result.coordinates, old.coordinates)
                self.assertIs(result.periodic.anisotropic_displacements, old.periodic.anisotropic_displacements)
                self.assertEqual(project.provenance, {})
                provenance = next(iter(upgraded.provenance.values()))
                self.assertEqual(dict(provenance.parameters)["source_revision"], old.revision)
                self.assertIn(old.id, provenance.parent_ids)
                repeated = upgrade_project(upgraded)
                self.assertEqual(len(repeated.provenance), 1)
                self.assertIs(repeated.structures[old.id], result)
                output = save_project(directory / "new.cbq", upgraded)
                restored = open_project(output)
                try:
                    self.assertEqual(restored.structures[old.id].revision, result.revision)
                    np.testing.assert_array_equal(restored.structures[old.id].periodic.symmetry_rotations.values, result.periodic.symmetry_rotations.values)
                finally:
                    close_project(restored)
                self.assertEqual(hashes(root), before)
            finally:
                close_project(project)

    @unittest.skipUnless(HAS_GEMMI, "External Gemmi unavailable")
    def test_v10_crystal_cli_publishes_new_directory_and_preserves_source(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original = crystal_project()
            structure = next(iter(original.structures.values()))
            root = legacy_package(directory / "old.cbq", original)
            before = hashes(root)
            result = subprocess.run(
                [sys.executable, "-m", "chemblender_prepare", "upgrade", str(root),
                 "--output", str(directory / "new.cbq"),
                 "--task-directory", str(directory / "task"), "--json"],
                cwd=ROOT, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(hashes(root), before)
            restored = open_project(directory / "new.cbq")
            try:
                upgraded = restored.structures[structure.id]
                self.assertEqual(restored.id, original.id)
                self.assertNotEqual(upgraded.revision, structure.revision)
                self.assertIsNotNone(upgraded.periodic.symmetry_rotations)
                np.testing.assert_array_equal(upgraded.coordinates.values, structure.coordinates.values)
                np.testing.assert_array_equal(upgraded.periodic.anisotropic_displacements.values,
                                              structure.periodic.anisotropic_displacements.values)
            finally:
                close_project(restored)

    def test_corrupt_v10_cli_upgrade_does_not_publish_or_change_source(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = legacy_package(directory / "old.cbq", sample_project())
            path = root / "manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["project"]["schema_version"] = "tampered"
            write_manifest(path, manifest, update_hash=False)
            before = hashes(root)
            result = subprocess.run([sys.executable, "-m", "chemblender_prepare", "upgrade", str(root),
                                     "--output", str(directory / "new.cbq"), "--task-directory", str(directory / "task"), "--json"],
                                    cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("manifest hash mismatch", result.stdout + result.stderr)
            self.assertFalse((directory / "new.cbq").exists())
            self.assertEqual(hashes(root), before)


if __name__ == "__main__":
    unittest.main()
