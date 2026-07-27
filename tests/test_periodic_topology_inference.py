import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    ImportBatch,
    PeriodicSiteData,
    QCProject,
    QualityStatus,
    Structure,
)
from ChemBlender.core.topology.infer import (
    TopologyInferenceSettings,
    infer_distance_topology,
)
from ChemBlender.core.topology.periodic import infer_periodic_topology


def periodic_structure(
    fractional,
    *,
    atomic_numbers=None,
    cell=None,
    pbc=(True, True, True),
    structure_id=None,
    revision="periodic-r1",
    stored_fractional=None,
):
    fractional = numpy.asarray(fractional, dtype=float)
    atom_count = len(fractional)
    if atomic_numbers is None:
        atomic_numbers = (6,) * atom_count
    if cell is None:
        cell = numpy.diag((10.0, 10.0, 10.0))
    cell = numpy.asarray(cell, dtype=float)
    return Structure(
        id=uuid4() if structure_id is None else structure_id,
        revision=revision,
        atomic_numbers=tuple(atomic_numbers),
        coordinates=ArrayData(
            fractional @ cell,
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=ArrayData(cell, ("cell_vector", "xyz"), "angstrom"),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(
                (
                    fractional
                    if stored_fractional is None
                    else numpy.asarray(stored_fractional, dtype=float)
                ),
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=tuple(f"site-{index}" for index in range(atom_count)),
            occupancies=ArrayData(
                numpy.ones(atom_count),
                ("atom",),
                "dimensionless",
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",) * atom_count,
            disorder_groups=(0,) * atom_count,
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=(),
            cif_envelope_id=None,
            pbc=pbc,
        ),
    )


def topology(structure):
    return infer_periodic_topology(structure).topologies[0]


class PeriodicTopologyInferenceTests(unittest.TestCase):
    def test_opposite_cell_faces_connect_with_lattice_shift(self):
        reference = periodic_structure(((0.95, 0.5, 0.5), (0.05, 0.5, 0.5)))

        result = topology(reference)

        self.assertEqual(result.bond_indices.values.tolist(), [[0, 1]])
        self.assertEqual(result.bond_lattice_shifts.values.tolist(), [[1, 0, 0]])
        self.assertEqual(result.bond_orders.values.tolist(), [0.0])
        self.assertEqual(result.quality_status, QualityStatus.AMBIGUOUS)
        self.assertIn(("periodic", True), result.inference_parameters)
        self.assertIn(("pbc", (True, True, True)), result.inference_parameters)

    def test_nonorthogonal_cell_uses_fractional_minimum_image(self):
        cell = (
            (3.0, 0.0, 0.0),
            (1.5, 2.598076211, 0.0),
            (0.0, 0.0, 10.0),
        )
        reference = periodic_structure(
            ((0.95, 0.95, 0.5), (0.05, 0.05, 0.5)),
            cell=cell,
        )

        result = topology(reference)

        self.assertEqual(result.bond_indices.values.tolist(), [[0, 1]])
        self.assertEqual(result.bond_lattice_shifts.values.tolist(), [[1, 1, 0]])

    def test_partial_pbc_wraps_only_enabled_axes(self):
        wraps_x = periodic_structure(
            ((0.95, 0.5, 0.5), (0.05, 0.5, 0.5)),
            pbc=(True, False, False),
        )
        does_not_wrap_y = periodic_structure(
            ((0.5, 0.95, 0.5), (0.5, 0.05, 0.5)),
            pbc=(True, False, False),
        )

        wrapped = topology(wraps_x)
        unwrapped = topology(does_not_wrap_y)

        self.assertEqual(wrapped.bond_lattice_shifts.values.tolist(), [[1, 0, 0]])
        self.assertEqual(unwrapped.bond_indices.shape, (0, 2))
        self.assertEqual(unwrapped.bond_lattice_shifts.shape, (0, 3))

    def test_integer_lattice_translation_preserves_topology_identity(self):
        structure_id = uuid4()
        reference = periodic_structure(
            ((0.95, 0.95, 0.5), (0.05, 0.05, 0.5)),
            structure_id=structure_id,
        )
        translated = periodic_structure(
            ((3.95, -1.05, 2.5), (3.05, -1.95, 2.5)),
            structure_id=structure_id,
        )

        original = topology(reference)
        shifted = topology(translated)

        self.assertEqual(shifted.id, original.id)
        self.assertEqual(shifted.revision, original.revision)
        self.assertEqual(
            shifted.bond_indices.values.tolist(),
            original.bond_indices.values.tolist(),
        )
        self.assertEqual(
            shifted.bond_lattice_shifts.values.tolist(),
            original.bond_lattice_shifts.values.tolist(),
        )
        self.assertIn(
            (
                "fractional_normalization",
                "cartesian_pbc_modulo_one",
            ),
            shifted.inference_parameters,
        )

    def test_single_atom_unwrapped_by_multiple_cells_preserves_edges(self):
        structure_id = uuid4()
        reference = periodic_structure(
            ((0.95, 0.5, 0.5), (0.05, 0.5, 0.5)),
            structure_id=structure_id,
        )
        unwrapped = periodic_structure(
            ((0.95, 0.5, 0.5), (3.05, 0.5, 0.5)),
            structure_id=structure_id,
        )

        original = topology(reference)
        shifted = topology(unwrapped)

        self.assertEqual(shifted.id, original.id)
        self.assertEqual(
            shifted.bond_lattice_shifts.values.tolist(),
            [[1, 0, 0]],
        )

    def test_skew_cell_unwrapped_coordinates_preserve_identity(self):
        structure_id = uuid4()
        cell = (
            (3.0, 0.0, 0.0),
            (1.5, 2.598076211, 0.0),
            (0.0, 0.0, 10.0),
        )
        reference = periodic_structure(
            ((0.95, 0.95, 0.5), (0.05, 0.05, 0.5)),
            cell=cell,
            structure_id=structure_id,
        )
        unwrapped = periodic_structure(
            ((2.95, -1.05, 0.5), (0.05, 3.05, 0.5)),
            cell=cell,
            structure_id=structure_id,
        )

        self.assertEqual(topology(unwrapped).id, topology(reference).id)

    def test_skew_cell_integer_boundary_roundoff_preserves_identity(self):
        structure_id = uuid4()
        cell = (
            (6.076548178105441, 0.1535747351592509, -0.9982093402937147),
            (-0.02790012271465714, 5.7605579427458675, 0.6779164425174695),
            (-0.34250410044247936, -0.5787801207625116, 4.2062839602396105),
        )
        reference = periodic_structure(
            ((0.0, 0.37, 0.61), (0.1, 0.37, 0.61)),
            cell=cell,
            structure_id=structure_id,
        )
        unwrapped = periodic_structure(
            ((-14.0, 1.37, 3.61), (0.1, 0.37, 0.61)),
            cell=cell,
            structure_id=structure_id,
        )

        original = topology(reference)
        shifted = topology(unwrapped)

        self.assertEqual(
            original.bond_lattice_shifts.values.tolist(),
            [[0, 0, 0]],
        )
        self.assertEqual(shifted.id, original.id)
        self.assertEqual(
            shifted.bond_lattice_shifts.values.tolist(),
            [[0, 0, 0]],
        )

    def test_near_boundary_noninteger_coordinate_is_not_snapped(self):
        cell = (
            (6.076548178105441, 0.1535747351592509, -0.9982093402937147),
            (-0.02790012271465714, 5.7605579427458675, 0.6779164425174695),
            (-0.34250410044247936, -0.5787801207625116, 4.2062839602396105),
        )
        reference = periodic_structure(
            ((-1.0e-10, 0.37, 0.61), (0.1, 0.37, 0.61)),
            cell=cell,
        )

        result = topology(reference)

        self.assertEqual(
            result.bond_lattice_shifts.values.tolist(),
            [[1, 0, 0]],
        )

    def test_nonperiodic_cell_ill_conditioning_does_not_snap_pbc_axis(self):
        reference = periodic_structure(
            ((0.0, 0.0, 1.0e-4), (0.0, 0.0, 0.19715)),
            cell=((10.0, 0.0, 0.0), (10.0, 1.0e-10, 0.0), (0.0, 0.0, 10.0)),
            pbc=(False, False, True),
        )

        result = topology(reference)

        self.assertEqual(result.bond_indices.values.tolist(), [[0, 1]])
        self.assertEqual(
            result.bond_lattice_shifts.values.tolist(),
            [[0, 0, 0]],
        )

    def test_partial_pbc_does_not_wrap_disabled_axis(self):
        structure_id = uuid4()
        reference = periodic_structure(
            ((0.95, 0.0, 0.5), (0.05, 0.0, 0.5)),
            pbc=(True, False, False),
            structure_id=structure_id,
        )
        pbc_unwrapped = periodic_structure(
            ((2.95, 0.0, 0.5), (-1.95, 0.0, 0.5)),
            pbc=(True, False, False),
            structure_id=structure_id,
        )
        nonpbc_unwrapped = periodic_structure(
            ((0.95, 2.0, 0.5), (0.05, 0.0, 0.5)),
            pbc=(True, False, False),
            structure_id=structure_id,
        )

        self.assertEqual(topology(pbc_unwrapped).id, topology(reference).id)
        self.assertNotEqual(topology(nonpbc_unwrapped).id, topology(reference).id)
        self.assertEqual(topology(nonpbc_unwrapped).bond_indices.shape, (0, 2))

    def test_cartesian_coordinates_are_authoritative_for_wrapping(self):
        structure_id = uuid4()
        reference = periodic_structure(
            ((0.95, 0.5, 0.5), (0.05, 0.5, 0.5)),
            structure_id=structure_id,
        )
        inconsistent_stored_fractional = periodic_structure(
            ((2.95, 0.5, 0.5), (-1.95, 0.5, 0.5)),
            stored_fractional=((0.4, 0.4, 0.4), (0.8, 0.8, 0.8)),
            structure_id=structure_id,
        )

        self.assertEqual(
            topology(inconsistent_stored_fractional).id,
            topology(reference).id,
        )

    def test_single_atom_periodic_chain_keeps_one_canonical_self_image(self):
        reference = periodic_structure(
            ((0.0, 0.0, 0.0),),
            atomic_numbers=(1,),
            cell=((0.7, 0.0, 0.0), (0.0, 5.0, 0.0), (0.0, 0.0, 5.0)),
            pbc=(True, False, False),
        )

        result = topology(reference)

        self.assertEqual(result.bond_indices.values.tolist(), [[0, 0]])
        self.assertEqual(result.bond_lattice_shifts.values.tolist(), [[1, 0, 0]])

        unwrapped = periodic_structure(
            ((4.0, 0.0, 0.0),),
            atomic_numbers=(1,),
            cell=((0.7, 0.0, 0.0), (0.0, 5.0, 0.0), (0.0, 0.0, 5.0)),
            pbc=(True, False, False),
            structure_id=reference.id,
        )
        shifted = topology(unwrapped)
        self.assertEqual(shifted.id, result.id)
        self.assertEqual(
            shifted.bond_lattice_shifts.values.tolist(),
            [[1, 0, 0]],
        )

    def test_periodic_result_commits_and_nonperiodic_result_has_no_shifts(self):
        reference = periodic_structure(((0.95, 0.5, 0.5), (0.05, 0.5, 0.5)))
        batch = infer_periodic_topology(reference)
        project = QCProject(id=uuid4(), schema_version="0.2")

        project.commit(ImportBatch(structures=(reference,)))
        project.commit(batch)

        self.assertIn(batch.topologies[0].id, project.topologies)
        nonperiodic = Structure(
            id=uuid4(),
            revision="molecule-r1",
            atomic_numbers=(8, 1),
            coordinates=ArrayData(
                numpy.asarray(((0.0, 0.0, 0.0), (0.96, 0.0, 0.0))),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        self.assertIsNone(
            infer_distance_topology(nonperiodic).topologies[0].bond_lattice_shifts
        )

    def test_requires_periodic_structure_settings_and_nonsingular_cell(self):
        molecule = Structure(
            id=uuid4(),
            revision="molecule-r1",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                numpy.zeros((1, 3)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        with self.assertRaisesRegex(TypeError, "periodic Structure"):
            infer_periodic_topology(molecule)
        with self.assertRaisesRegex(ValueError, "periodic=True"):
            infer_periodic_topology(
                periodic_structure(((0.0, 0.0, 0.0),)),
                TopologyInferenceSettings(periodic=False),
            )
        with self.assertRaisesRegex(ValueError, "non-singular"):
            periodic_structure(
                ((0.0, 0.0, 0.0),),
                cell=numpy.zeros((3, 3)),
            )


if __name__ == "__main__":
    unittest.main()
