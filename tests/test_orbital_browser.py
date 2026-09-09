import unittest
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

import numpy

from cbq_core.model import ArrayData
from cbq_core.model import ImportBatch
from cbq_core.model import OrbitalKind
from cbq_core.model import QCProject
from chemblender_prepare.core.orbital_browser import estimate_grid_memory
from cbq_core.orbital_browser import orbital_rows
from chemblender_prepare.core.orbital_browser import suggest_grid
from chemblender_prepare.core.wavefunction_grid import evaluate_molecular_orbital_grid
from tests.test_wavefunction_grid import GRID, entities


def project_with(orbitals=None, kind=OrbitalKind.RESTRICTED):
    structure, basis, default = entities(kind)
    if orbitals is None:
        orbitals = default
    else:
        orbitals = replace(orbitals, structure_id=structure.id, basis_set_id=basis.id)
    project = QCProject(id=uuid4(), schema_version="0.1")
    project.commit(ImportBatch(structures=(structure,), basis_sets=(basis,),
                               orbital_sets=(orbitals,)))
    return project, structure, basis, orbitals


class OrbitalBrowserTests(unittest.TestCase):
    def test_known_frontiers_and_spin_channels(self):
        for kind, channel in ((OrbitalKind.RESTRICTED, "restricted"),
                              (OrbitalKind.UNRESTRICTED, "beta")):
            project, _, _, orbitals = project_with(kind=kind)
            rows = orbital_rows(project, orbitals, channel)
            self.assertEqual(rows[0].labels, ("HOMO",))
            self.assertEqual(rows[1].labels, ("LUMO",))
            self.assertEqual(rows[0].energy, -0.5)
            self.assertEqual(rows[0].spin, channel)
            self.assertFalse(rows[0].evaluation_error)

    def test_missing_fractional_and_unknown_energies_do_not_infer_frontiers(self):
        _, _, original = entities()
        for occupations, energies in ((None, original.channels[0].energies),
                (ArrayData(numpy.array([1.5, .5]), ("orbital",), "dimensionless"),
                 original.channels[0].energies),
                (original.channels[0].occupations, None)):
            orbitals = replace(original, channels=(replace(original.channels[0],
                occupations=occupations, energies=energies),))
            project, _, _, orbitals = project_with(orbitals)
            self.assertTrue(all(not row.labels for row in orbital_rows(
                project, orbitals, "restricted")))

    def test_somo_is_only_for_known_singly_occupied_restricted_orbitals(self):
        _, _, original = entities()
        orbitals = replace(original, channels=(replace(original.channels[0],
            occupations=ArrayData(numpy.array([1., 0.]), ("orbital",), "dimensionless")),))
        project, _, _, orbitals = project_with(orbitals)
        self.assertEqual(orbital_rows(project, orbitals, "restricted")[0].labels,
                         ("HOMO", "SOMO"))

    def test_generalized_and_complex_evaluation_is_disabled(self):
        project, _, _, orbitals = project_with(kind=OrbitalKind.GENERALIZED)
        self.assertIn("spinors", orbital_rows(project, orbitals, "generalized")[0].evaluation_error)
        _, _, original = entities()
        orbitals = replace(original, channels=(replace(original.channels[0],
            coefficients=ArrayData(numpy.array([[1.j], [.5j]]),
                                   ("orbital", "basis_function"), "dimensionless")),))
        project, _, _, orbitals = project_with(orbitals)
        self.assertIn("Complex", orbital_rows(project, orbitals, "restricted")[0].evaluation_error)

    @patch("chemblender_prepare.core.wavefunction_grid._evaluate_channel",
           return_value=numpy.array([[1., 2.]]))
    def test_cache_requires_current_identity_structure_and_requested_grid(self, evaluate):
        project, structure, basis, orbitals = project_with()
        batch = evaluate_molecular_orbital_grid(structure, basis, orbitals,
            channel="restricted", orbital_index=0, **GRID)
        project.commit(batch)
        grid = batch.datasets[0]
        self.assertEqual(orbital_rows(project, orbitals, "restricted",
            grid_parameters=GRID)[0].cached_dataset_ids, (grid.id,))
        self.assertFalse(orbital_rows(project, orbitals, "restricted",
            grid_parameters={**GRID, "origin": (0., 0., 0.)})[0].cached_dataset_ids)
        # Historical derived grids lack structure binding or use the previous identity.
        for old_grid in (replace(grid, structure_id=None), replace(grid, revision="old")):
            project.datasets[grid.id] = old_grid
            self.assertFalse(orbital_rows(project, orbitals, "restricted")[0].cached_dataset_ids)

        project.datasets[grid.id] = grid
        record = batch.provenance[0]
        for key in ("structure_revision", "basis_revision", "orbital_revision"):
            for value in (None, "stale-revision"):
                with self.subTest(key=key, value=value):
                    parameters = dict(record.parameters)
                    if value is None:
                        parameters.pop(key)
                    else:
                        parameters[key] = value
                    project.provenance[record.id] = replace(
                        record, parameters=tuple(parameters.items()))
                    self.assertFalse(orbital_rows(
                        project, orbitals, "restricted")[0].cached_dataset_ids)
        project.provenance[record.id] = record
        self.assertEqual(orbital_rows(project, orbitals, "restricted")[0].cached_dataset_ids,
                         (grid.id,))

    def test_grid_preflight_covers_bounds_and_bounded_working_memory(self):
        _, structure, basis, _ = project_with()
        geometry = suggest_grid(structure, spacing=.5, padding=1.)
        self.assertEqual(geometry["shape"], (5, 5, 5))
        self.assertEqual(geometry["origin"], (-1., -1., -1.))
        small = estimate_grid_memory((10, 10, 10), basis.basis_function_count, block_size=32)
        large = estimate_grid_memory((100, 100, 100), basis.basis_function_count, block_size=32)
        self.assertEqual(small["working_bytes"], large["working_bytes"])
        self.assertEqual(large["output_bytes"], 8_000_000)
        for shape in ((True, 2, 3), (1, 2), (1., 2, 3), (0, 2, 3)):
            with self.assertRaises(ValueError):
                estimate_grid_memory(shape, 1)
        for spacing in (0., float("nan"), True):
            with self.assertRaises(ValueError):
                suggest_grid(structure, spacing=spacing)


if __name__ == "__main__":
    unittest.main()
