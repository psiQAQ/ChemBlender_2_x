from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import numpy

import ChemBlender.core as core
from ChemBlender.reader_api import (
    internal_batch_from_public,
    public_batch_document,
    public_batch_from_document,
    public_batch_from_internal,
)


def array(values, dims, unit):
    return core.ArrayData(numpy.asarray(values), dims, unit)


def periodic_structure(
    *,
    cell=None,
    fractional=None,
    coordinates=None,
    coordinate_unit="angstrom",
    structure_id=None,
    topology_ids=(),
):
    if cell is None:
        cell = numpy.asarray(
            (
                (3.0, 0.0, 0.0),
                (1.0, 4.0, 0.0),
                (0.5, 0.75, 5.0),
            ),
            dtype=float,
        )
    else:
        cell = numpy.asarray(cell, dtype=float)
    if fractional is None:
        fractional = numpy.asarray(((0.25, 0.5, 0.75),), dtype=float)
    else:
        fractional = numpy.asarray(fractional, dtype=float)
    if coordinates is None:
        coordinates = fractional @ cell
    return core.Structure(
        id=uuid4() if structure_id is None else structure_id,
        revision="crystal-r1",
        atomic_numbers=(14,) * len(fractional),
        coordinates=array(coordinates, ("atom", "xyz"), coordinate_unit),
        cell=array(cell, ("cell_vector", "xyz"), coordinate_unit),
        periodic=core.PeriodicSiteData(
            fractional_coordinates=array(
                fractional,
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=tuple(f"Si{index + 1}" for index in range(len(fractional))),
            occupancies=array(
                numpy.ones(len(fractional)),
                ("atom",),
                "dimensionless",
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",) * len(fractional),
            disorder_groups=(0,) * len(fractional),
            declared_space_group_name="P 1",
            declared_space_group_number=1,
            symmetry_operations=("x,y,z",),
            cif_envelope_id=None,
        ),
        topology_ids=topology_ids,
    )


def symmetry_result(rotations):
    rotations = numpy.asarray(rotations)
    operation_count = rotations.shape[0]
    return core.SymmetryResult(
        id=uuid4(),
        revision="symmetry-r1",
        structure_id=uuid4(),
        standardized_structure_id=uuid4(),
        hall_number=1,
        international_number=1,
        international_symbol="P1",
        hall_symbol="P 1",
        choice="",
        pointgroup="1",
        rotations=array(
            rotations,
            ("operation", "output_axis", "input_axis"),
            "dimensionless",
        ),
        translations=array(
            numpy.zeros((operation_count, 3)),
            ("operation", "axis"),
            "dimensionless",
        ),
        wyckoffs=("a",),
        site_symmetry_symbols=("1",),
        equivalent_atoms=array((0,), ("atom",), "dimensionless"),
        crystallographic_orbits=array((0,), ("atom",), "dimensionless"),
        transformation_matrix=array(
            numpy.eye(3),
            ("standard_axis", "input_axis"),
            "dimensionless",
        ),
        origin_shift=array(numpy.zeros(3), ("axis",), "dimensionless"),
        mapping_to_primitive=array((0,), ("atom",), "dimensionless"),
        std_mapping_to_primitive=array(
            (0,),
            ("standard_atom",),
            "dimensionless",
        ),
        std_rotation_matrix=array(
            numpy.eye(3),
            ("cartesian_output_axis", "cartesian_input_axis"),
            "dimensionless",
        ),
        symprec=1.0e-5,
        angle_tolerance=-1.0,
        provenance_ids=(),
    )


def periodic_topology(structure_id, topology_id=None):
    return core.TopologyRecord(
        id=uuid4() if topology_id is None else topology_id,
        revision="topology-r1",
        structure_id=structure_id,
        bond_indices=array(((0, 0),), ("bond", "endpoint"), "dimensionless"),
        bond_orders=array((0.0,), ("bond",), "dimensionless"),
        aromatic_flags=None,
        stereo_labels=("",),
        source_kind=core.TopologySource.EXPLICIT_FILE,
        quality_status=core.QualityStatus.COMPLETE,
        inference_parameters=(),
        provenance_ids=(),
        bond_lattice_shifts=array(
            ((1, 0, 0),),
            ("bond", "xyz"),
            "dimensionless",
        ),
    )


class CrystalCellContractTests(unittest.TestCase):
    def test_unit_cell_parameters_derive_lengths_and_angles_from_rows(self):
        cell = array(
            (
                (3.0, 0.0, 0.0),
                (1.0, 4.0, 0.0),
                (0.5, 0.75, 5.0),
            ),
            ("cell_vector", "xyz"),
            "angstrom",
        )

        actual = core.unit_cell_parameters(cell)

        expected_lengths = tuple(numpy.linalg.norm(row) for row in cell.values)
        expected_angles = (
            80.38182145677305,
            84.35217611782296,
            75.96375653207352,
        )
        numpy.testing.assert_allclose(actual[:3], expected_lengths, atol=1.0e-12)
        numpy.testing.assert_allclose(actual[3:], expected_angles, atol=1.0e-12)

    def test_fractional_cartesian_roundtrip_preserves_shape_and_units(self):
        structure = periodic_structure()

        cartesian = core.fractional_to_cartesian(
            structure.periodic.fractional_coordinates,
            structure.cell,
        )
        restored = core.cartesian_to_fractional(cartesian, structure.cell)

        self.assertEqual(cartesian.dims, ("atom", "xyz"))
        self.assertEqual(cartesian.unit, "angstrom")
        self.assertEqual(restored.unit, "dimensionless")
        numpy.testing.assert_allclose(
            cartesian.values,
            structure.coordinates.values,
            atol=1.0e-12,
        )
        numpy.testing.assert_allclose(
            restored.values,
            structure.periodic.fractional_coordinates.values,
            atol=1.0e-12,
        )

    def test_bohr_roundtrip_retains_native_length_unit(self):
        structure = periodic_structure(
            cell=numpy.diag((2.0, 3.0, 4.0)),
            fractional=((0.5, 0.25, 0.125),),
            coordinate_unit="bohr",
        )

        cartesian = core.fractional_to_cartesian(
            structure.periodic.fractional_coordinates,
            structure.cell,
        )

        self.assertEqual(cartesian.unit, "bohr")
        numpy.testing.assert_allclose(
            cartesian.values,
            ((1.0, 0.75, 0.5),),
            atol=1.0e-12,
        )

    def test_structure_rejects_non_length_and_nonfinite_coordinates(self):
        for unit in ("unknown", "dimensionless", "electron_volt"):
            with self.subTest(unit=unit):
                with self.assertRaisesRegex(ValueError, "known length unit"):
                    periodic_structure(coordinate_unit=unit)
        with self.assertRaisesRegex(ValueError, "finite"):
            periodic_structure(coordinates=((numpy.nan, 0.0, 0.0),))

    def test_coordinate_consistency_is_an_explicit_adapter_boundary(self):
        structure = periodic_structure()
        core.validate_periodic_coordinate_consistency(structure)

        inconsistent = replace(
            structure,
            coordinates=array(
                ((99.0, 0.0, 0.0),),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        with self.assertRaisesRegex(ValueError, "fractional.*Cartesian"):
            core.validate_periodic_coordinate_consistency(inconsistent)

    def test_coordinate_helpers_reject_bad_shape_unit_and_tolerance(self):
        cell = array(numpy.eye(3), ("cell_vector", "xyz"), "angstrom")
        with self.assertRaisesRegex(ValueError, "known length unit"):
            core.unit_cell_parameters(
                array(numpy.eye(3), ("cell_vector", "xyz"), "electron_volt")
            )
        with self.assertRaisesRegex(ValueError, "non-singular"):
            core.unit_cell_parameters(
                array(numpy.zeros((3, 3)), ("cell_vector", "xyz"), "angstrom")
            )
        bad_fractional = array(
            numpy.zeros((1, 2)),
            ("atom", "xyz"),
            "dimensionless",
        )
        with self.assertRaisesRegex(ValueError, "fractional"):
            core.fractional_to_cartesian(bad_fractional, cell)

        cartesian = array(
            numpy.zeros((1, 3)),
            ("atom", "xyz"),
            "bohr",
        )
        with self.assertRaisesRegex(ValueError, "same unit"):
            core.cartesian_to_fractional(cartesian, cell)

        with self.assertRaisesRegex(ValueError, "absolute_tolerance"):
            core.validate_periodic_coordinate_consistency(
                periodic_structure(),
                absolute_tolerance=-1.0,
            )


class CrystalSymmetryContractTests(unittest.TestCase):
    def test_integer_unimodular_rotations_are_accepted(self):
        result = symmetry_result(
            (
                numpy.eye(3, dtype=numpy.int64),
                -numpy.eye(3, dtype=numpy.int64),
            )
        )

        self.assertEqual(result.rotations.shape, (2, 3, 3))

    def test_float_rotation_dtype_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "rotation.*integer"):
            symmetry_result((numpy.eye(3, dtype=float),))

    def test_non_unimodular_rotation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unimodular"):
            symmetry_result(
                (
                    numpy.asarray(
                        (
                            (2, 0, 0),
                            (0, 1, 0),
                            (0, 0, 1),
                        ),
                        dtype=numpy.int64,
                    ),
                )
            )

    def test_translation_shape_and_finiteness_remain_fail_closed(self):
        valid = symmetry_result((numpy.eye(3, dtype=numpy.int64),))
        with self.assertRaisesRegex(ValueError, "rotations and translations"):
            replace(
                valid,
                translations=array(
                    numpy.zeros((1, 2)),
                    ("operation", "axis"),
                    "dimensionless",
                ),
            )
        with self.assertRaisesRegex(ValueError, "finite and dimensionless"):
            replace(
                valid,
                translations=array(
                    ((numpy.inf, 0.0, 0.0),),
                    ("operation", "axis"),
                    "dimensionless",
                ),
            )


class CrystalPersistenceContractTests(unittest.TestCase):
    def test_project_commit_rollback_preserves_existing_periodic_graph(self):
        structure = periodic_structure()
        project = core.QCProject(id=uuid4(), schema_version="0.2")
        project.commit(core.ImportBatch(structures=(structure,)))
        before = dict(project.structures), dict(project.topologies)
        dangling = periodic_topology(uuid4())

        with self.assertRaisesRegex(ValueError, "dangling structure"):
            project.commit(core.ImportBatch(topologies=(dangling,)))

        self.assertEqual(project.structures, before[0])
        self.assertEqual(project.topologies, before[1])

    def test_periodic_structure_and_topology_round_trip_through_sidecar(self):
        structure_id = uuid4()
        topology_id = uuid4()
        structure = periodic_structure(
            structure_id=structure_id,
            topology_ids=(topology_id,),
        )
        topology = periodic_topology(structure_id, topology_id)
        project = core.QCProject(id=uuid4(), schema_version="0.2")
        project.commit(
            core.ImportBatch(
                structures=(structure,),
                topologies=(topology,),
            )
        )

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "crystal.cbq"
            core.save_project(destination, project)
            restored = core.open_project(destination)
            try:
                loaded_structure = restored.structures[structure_id]
                loaded_topology = restored.topologies[topology_id]
                self.assertFalse(loaded_structure.coordinates.values.loaded)
                self.assertFalse(loaded_structure.cell.values.loaded)
                numpy.testing.assert_allclose(
                    loaded_structure.cell.values,
                    structure.cell.values,
                )
                numpy.testing.assert_allclose(
                    loaded_structure.periodic.fractional_coordinates.values,
                    structure.periodic.fractional_coordinates.values,
                )
                self.assertEqual(loaded_structure.periodic.pbc, (True, True, True))
                self.assertEqual(
                    numpy.asarray(
                        loaded_topology.bond_lattice_shifts.values
                    ).tolist(),
                    [[1, 0, 0]],
                )
            finally:
                core.close_project(restored)

    def test_periodic_batch_round_trips_through_canonical_document(self):
        structure_id = uuid4()
        topology_id = uuid4()
        structure = periodic_structure(
            structure_id=structure_id,
            topology_ids=(topology_id,),
        )
        topology = periodic_topology(structure_id, topology_id)
        batch = core.ImportBatch(
            structures=(structure,),
            topologies=(topology,),
        )

        with TemporaryDirectory() as directory:
            bundle = Path(directory)
            document = public_batch_document(
                public_batch_from_internal(batch),
                bundle,
            )
            restored = internal_batch_from_public(
                public_batch_from_document(document, bundle)
            )

        self.assertEqual(restored.structures[0].id, structure_id)
        self.assertEqual(
            restored.topologies[0].bond_lattice_shifts.values.tolist(),
            [[1, 0, 0]],
        )


if __name__ == "__main__":
    unittest.main()
