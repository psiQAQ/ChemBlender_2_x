"""Explicit synthetic critic2 files test the public import transaction boundary."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import numpy

from cbq_core.model import ArrayData
from cbq_core.model import ImportBatch
from cbq_core.model import Structure
from cbq_core.sidecar import close_project
from cbq_core.session import close_session
from cbq_core.session import create_session
from cbq_core.sidecar import open_project
from cbq_core.sidecar import save_project
from chemblender_prepare.core.import_pipeline import ImportCancelled
from chemblender_prepare import topology_service as importer
from tests.test_critic2_paths import FIXTURE, flux_text, BOHR_TO_ANGSTROM


def topology_files(directory):
    root = Path(directory)
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    centering = numpy.array([.2, -.3, .4])
    coordinates = numpy.array([[0., 0., 0.], [2., 0., 0.]])
    document["units"] = "bohr"
    document["structure"] = {
        "is_molecule": True, "molecule_centering_vector": centering.tolist(),
        "number_of_species": 1, "species": [{"id": 1, "name": "H", "atomic_number": 1}],
        "number_of_cell_atoms": 2, "cell_atoms": [
            {"id": index + 1, "species": 1, "cartesian_coordinates": point.tolist()}
            for index, point in enumerate(coordinates)],
    }
    document["field"] = {"type": "synthetic density", "source": "test-only.wfx"}
    cp = root / "cpreport.json"
    cp.write_text(json.dumps(document), encoding="utf-8")
    points = numpy.array([[1., 0., 0.], [.5, .2, .1], [.01, 0., 0.]]) + centering
    flux = root / "flux.txt"
    flux.write_text(flux_text(points, start=points[0], end=centering, gap=.01), encoding="utf-8")
    structure = Structure(uuid4(), "synthetic-h2", (1, 1), ArrayData(
        (coordinates + centering) * BOHR_TO_ANGSTROM, ("atom", "xyz"), "angstrom"))
    return structure, cp, flux, points * BOHR_TO_ANGSTROM


class TopologyImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.structure, self.cp, self.flux, self.samples = topology_files(self.root)
        self.session = create_session(temp_parent=self.root)
        self.addCleanup(close_session, self.session)
        self.session.project.commit(ImportBatch(structures=(self.structure,)))
        self.session.mark_clean()

    def load(self, **kwargs):
        options = {"structure": self.structure, "field_kind": "ELECTRON_DENSITY_AU",
                   "fluxprint_path": self.flux, "temp_parent": self.session.temporary_root}
        options.update(kwargs)
        return importer.load_topology_batch(self.cp, **options)

    def assert_unpublished(self):
        self.assertEqual(len(self.session.project.datasets), 0)
        self.assertEqual(len(self.session.project.provenance), 0)
        self.assertFalse(self.session.dirty)
        self.assertFalse(list(self.session.temporary_root.glob("topology-*")))

    def test_service_commits_parent_and_ordered_paths_once_and_reopens(self):
        batch = self.load()
        self.assert_unpublished()
        self.assertEqual(len(batch.datasets), 2)
        self.assertEqual(batch.datasets[0].paths, ())
        numpy.testing.assert_allclose(batch.datasets[1].paths[0].samples.values, self.samples)
        original_commit = type(self.session.project).commit
        with patch.object(type(self.session.project), "commit", autospec=True,
                          side_effect=original_commit) as commit:
            importer.commit_topology_batch(self.session.project, batch)
            commit.assert_called_once()
        self.assertEqual(batch.provenance[1].parent_ids, (batch.datasets[0].id,))
        self.assertEqual({record.source for record in batch.provenance}, {str(self.cp), str(self.flux)})
        sidecar = self.root / "topology.cbq"
        save_project(sidecar, self.session.project)
        reopened = open_project(sidecar)
        try:
            derived = reopened.datasets[batch.datasets[1].id]
            numpy.testing.assert_allclose(derived.paths[0].samples.values, self.samples)
            self.assertEqual(derived.structure_id, self.structure.id)
            self.assertEqual(derived.data.unit, "angstrom")
            self.assertEqual(derived.field_values.unit, "inverse_cubic_bohr")
            binding = dict(reopened.provenance[batch.provenance[1].id].parameters)["topology_import_binding"]
            self.assertEqual(binding["structure_revision"], self.structure.revision)
            self.assertEqual(binding["atom_mapping"], [{"cell_atom_id": 1, "structure_atom_index": 0}, {"cell_atom_id": 2, "structure_atom_index": 1}])
        finally:
            close_project(reopened)

    def test_cp_only_can_later_receive_paths_without_replacing_parent(self):
        base = self.load(fluxprint_path=None)
        importer.commit_topology_batch(self.session.project, base)
        stored = self.session.project.datasets[base.datasets[0].id]
        complete = self.load()
        importer.commit_topology_batch(self.session.project, complete)
        self.assertIs(self.session.project.datasets[stored.id], stored)
        self.assertEqual(len(self.session.project.datasets), 2)
        self.assertEqual(len(self.session.project.provenance), 2)
        with self.assertRaisesRegex(ValueError, "already imported"):
            importer.commit_topology_batch(self.session.project, complete)

    def test_unset_field_and_mismatched_structure_are_rejected(self):
        for kwargs in (
            {"field_kind": "UNSET"},
            {"structure": replace(self.structure, atomic_numbers=(6, 6))},
            {"structure": replace(self.structure, coordinates=ArrayData(
                self.structure.coordinates.values + .1, ("atom", "xyz"), "angstrom"))},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.load(**kwargs)
        document = json.loads(self.cp.read_text())
        del document["structure"]
        self.cp.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "complete structure"):
            self.load()
        self.assert_unpublished()

    def test_periodic_skew_cell_binding_retains_ordered_lattice_image(self):
        from tests.test_periodic_electronic_model import periodic_structure

        matrix = numpy.array([[2., .3, .1], [.2, 3., .4], [0., .1, 4.]])
        fractions = numpy.array([[0., 0., 0.], [.8, 0., 0.]])
        cell = matrix.T * BOHR_TO_ANGSTROM
        crystal = periodic_structure()
        crystal = replace(crystal, atomic_numbers=(1, 1),
            coordinates=ArrayData(fractions @ cell, ("atom", "xyz"), "angstrom"),
            cell=ArrayData(cell, ("cell_vector", "xyz"), "angstrom"),
            periodic=replace(crystal.periodic, fractional_coordinates=ArrayData(
                fractions, ("atom", "xyz"), "dimensionless")))
        document = json.loads(self.cp.read_text())
        section = document["structure"]
        section.update(is_molecule=False, crys_to_cart_matrix=matrix.ravel(order="F").tolist())
        for atom, fraction in zip(section["cell_atoms"], fractions):
            atom["fractional_coordinates"] = fraction.tolist()
            atom["cartesian_coordinates"] = (fraction @ matrix.T).tolist()
        for point, fraction in zip(document["critical_points"]["cell_cps"], [*fractions, [.5, 0., 0.]]):
            point["fractional_coordinates"] = list(fraction)
            point["cartesian_coordinates"] = (matrix @ fraction).tolist()
        self.cp.write_text(json.dumps(document), encoding="utf-8")
        samples = numpy.array([[.5, 0., 0.], [.75, .03, 0.], [1., 0., 0.]])
        self.flux.write_text(flux_text(samples, start=samples[0] @ cell, end=numpy.zeros(3),
            unit="ang_", matrix=matrix, start_fractional=samples[0],
            end_fractional=numpy.zeros(3)), encoding="utf-8")
        self.session.project.commit(ImportBatch(structures=(crystal,)))
        batch = self.load(structure=crystal)
        importer.commit_topology_batch(self.session.project, batch)
        path = batch.datasets[-1].paths[0]
        numpy.testing.assert_allclose(path.samples.values, samples @ cell)
        metadata = dict(batch.provenance[-1].parameters)["paths"][0]
        self.assertEqual(metadata["path_id"], str(path.id))
        self.assertEqual(metadata["end_lattice_vector"], (1, 0, 0))
        changed = replace(crystal, cell=ArrayData(cell * 1.01, ("cell_vector", "xyz"), "angstrom"))
        with self.assertRaisesRegex(ValueError, "lattice"):
            self.load(structure=changed)

    def test_atom_permutation_is_explicit_and_nonnumeric_coordinates_rejected(self):
        reordered = replace(self.structure, coordinates=ArrayData(
            self.structure.coordinates.values[::-1], ("atom", "xyz"), "angstrom"))
        batch = self.load(structure=reordered)
        binding = dict(batch.provenance[0].parameters)["topology_import_binding"]
        self.assertEqual([item["structure_atom_index"] for item in binding["atom_mapping"]], [1, 0])
        document = json.loads(self.cp.read_text())
        for invalid in ([True, False, True], ["0", "0", "0"], [0., float("nan"), 0.]):
            document["structure"]["cell_atoms"][0]["cartesian_coordinates"] = invalid
            self.cp.write_text(json.dumps(document), encoding="utf-8")
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.load()
        self.assert_unpublished()

    def test_changed_original_and_frozen_files_fail_before_any_publication(self):
        original = importer.parse_critic2_cpreport
        for frozen in (False, True):
            self.structure, self.cp, self.flux, self.samples = topology_files(self.root)
            def changed(path, **kwargs):
                result = original(path, **kwargs)
                target = path if frozen else self.cp
                target.write_bytes(target.read_bytes() + b" ")
                return result
            with self.subTest(frozen=frozen), patch.object(importer, "parse_critic2_cpreport", side_effect=changed):
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.load(fluxprint_path=None)
            self.assert_unpublished()

    def test_changed_binding_or_source_before_commit_is_rejected(self):
        batch = self.load()
        for field in ("revision", "array", "source"):
            if field == "revision":
                self.session.project.structures[self.structure.id] = replace(self.structure, revision="changed")
            elif field == "array":
                self.session.project.structures[self.structure.id] = replace(self.structure,
                    coordinates=ArrayData(self.structure.coordinates.values + .01, ("atom", "xyz"), "angstrom"))
            else:
                self.session.project.structures[self.structure.id] = self.structure
                self.cp.write_bytes(self.cp.read_bytes() + b" ")
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "changed"):
                importer.commit_topology_batch(self.session.project, batch)
            self.assert_unpublished()

    def test_invalid_paths_or_cancelled_task_discard_both_graphs(self):
        with patch.object(importer, "parse_critic2_paths", side_effect=ValueError("invalid ordered paths")):
            with self.assertRaisesRegex(ValueError, "invalid ordered paths"):
                self.load()
        entered, release = Event(), Event()
        original = importer.parse_critic2_cpreport
        def blocked(*args, **kwargs):
            result = original(*args, **kwargs)
            entered.set()
            release.wait(5)
            return result
        cancelled = Event()
        with patch.object(importer, "parse_critic2_cpreport", side_effect=blocked), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.load, is_cancelled=cancelled.is_set)
            self.assertTrue(entered.wait(5))
            cancelled.set()
            release.set()
            with self.assertRaises(ImportCancelled):
                future.result(timeout=5)
        batch = self.load()
        with self.assertRaises(ImportCancelled):
            importer.commit_topology_batch(self.session.project, batch, is_cancelled=lambda: True)
        self.assert_unpublished()


if __name__ == "__main__":
    unittest.main()
