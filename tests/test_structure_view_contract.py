from dataclasses import FrozenInstanceError
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    PeriodicSiteData,
    QualityStatus,
    Structure,
    TopologyRecord,
    TopologySource,
)
from ChemBlender.views.structure import (
    StructureViewSettings,
    _structure_view_data,
)


def structure(*, periodic=False):
    values = {
        "id": uuid4(),
        "revision": "structure-r1",
        "atomic_numbers": (8, 1, 1),
        "coordinates": ArrayData(
            numpy.asarray(
                ((0.0, 0.0, 0.0), (0.96, 0.0, 0.0), (-0.24, 0.93, 0.0))
            ),
            ("atom", "xyz"),
            "angstrom",
        ),
    }
    if periodic:
        values["cell"] = ArrayData(
            numpy.diag((10.0, 10.0, 10.0)),
            ("cell_vector", "xyz"),
            "angstrom",
        )
    return Structure(**values)


def topology(reference, *, shifts=None):
    return TopologyRecord(
        id=uuid4(),
        revision="topology-r1",
        structure_id=reference.id,
        bond_indices=ArrayData(
            numpy.asarray(((0, 1), (0, 2))),
            ("bond", "endpoint"),
            "dimensionless",
        ),
        bond_orders=ArrayData(
            numpy.asarray((1.0, 1.5)),
            ("bond",),
            "dimensionless",
        ),
        aromatic_flags=ArrayData(
            numpy.asarray((False, True)),
            ("bond",),
            "dimensionless",
        ),
        stereo_labels=("", ""),
        source_kind=TopologySource.EXPLICIT_FILE,
        quality_status=QualityStatus.COMPLETE,
        inference_parameters=(),
        provenance_ids=(),
        bond_lattice_shifts=(
            None
            if shifts is None
            else ArrayData(
                numpy.asarray(shifts),
                ("bond", "xyz"),
                "dimensionless",
            )
        ),
    )


def periodic_structure(
    coordinates,
    *,
    pbc=(True, False, False),
    structure_id=None,
):
    coordinates = numpy.asarray(coordinates, dtype=float)
    cell = numpy.diag((4.0, 5.0, 6.0))
    return Structure(
        id=uuid4() if structure_id is None else structure_id,
        revision="periodic-r1",
        atomic_numbers=(8, 1, 1),
        coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"),
        cell=ArrayData(cell, ("cell_vector", "xyz"), "angstrom"),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(
                coordinates @ numpy.linalg.inv(cell),
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=("O", "H1", "H2"),
            occupancies=ArrayData(
                numpy.ones(3), ("atom",), "dimensionless"
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",) * 3,
            disorder_groups=(0,) * 3,
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=(),
            cif_envelope_id=None,
            pbc=pbc,
        ),
    )


def periodic_segment_data(second_coordinate):
    wrapped = periodic_structure(
        ((0.1, 1.25, 0.0), (3.8, 2.5, 0.0), (0.2, 0.0, 0.0))
    )
    candidate = periodic_structure(
        ((0.1, 1.25, 0.0), second_coordinate, (0.2, 0.0, 0.0)),
        structure_id=wrapped.id,
    )
    selected = topology(
        wrapped,
        shifts=((-1, 0, 0), (0, 0, 0)),
    )
    return (
        _structure_view_data(wrapped, selected),
        _structure_view_data(candidate, selected),
    )


class StructureViewContractTests(unittest.TestCase):
    def test_settings_are_frozen_and_positive(self):
        settings = StructureViewSettings()
        self.assertEqual(settings.atom_scale, 1.0)
        self.assertEqual(settings.bond_scale, 1.0)
        self.assertTrue(settings.attach_ball_and_stick)
        self.assertTrue(settings.display_periodic_images)
        with self.assertRaises(FrozenInstanceError):
            settings.atom_scale = 2.0
        for changes in (
            {"atom_scale": 0.0},
            {"bond_scale": float("nan")},
            {"attach_ball_and_stick": 1},
            {"display_periodic_images": None},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    StructureViewSettings(**changes)

    def test_explicit_topology_builds_primary_edges_and_legacy_attributes(self):
        reference = structure()

        data = _structure_view_data(reference, topology(reference))

        self.assertEqual(data["primary_edges"], ((0, 1), (0, 2)))
        self.assertEqual(data["primary_bond_ids"], (0, 1))
        self.assertEqual(data["bond_order"], (1, 12))
        self.assertEqual(data["cbq_bond_order"], (1.0, 1.5))
        self.assertEqual(data["is_aromatic"], (False, True))
        self.assertEqual(data["periodic_segments"], ())
        self.assertEqual(data["atomic_num"], (8, 1, 1))
        self.assertEqual(data["cbq_atom_id"], (0, 1, 2))
        self.assertEqual(data["atom_scale_f"], (1.0, 1.0, 1.0))
        self.assertEqual(data["bond_scale_f"], (1.0, 1.0))

    def test_no_topology_is_an_atoms_only_contract(self):
        data = _structure_view_data(structure(), None)

        self.assertEqual(data["primary_edges"], ())
        self.assertEqual(data["periodic_segments"], ())
        self.assertEqual(data["bond_order"], ())

    def test_periodic_shift_becomes_derived_segment_not_primary_edge(self):
        reference = structure(periodic=True)
        selected = topology(reference, shifts=((1, 0, 0), (0, 0, 0)))

        data = _structure_view_data(reference, selected)

        self.assertEqual(data["primary_edges"], ((0, 2),))
        self.assertEqual(data["primary_bond_ids"], (1,))
        self.assertEqual(len(data["periodic_segments"]), 1)
        segment = data["periodic_segments"][0]
        self.assertEqual(segment["bond_id"], 0)
        self.assertEqual(segment["atom_ids"], (0, 1))
        self.assertEqual(segment["lattice_shift"], (1, 0, 0))
        numpy.testing.assert_allclose(
            segment["coordinates"],
            ((0.0, 0.0, 0.0), (10.96, 0.0, 0.0)),
        )

    def test_periodic_segment_geometry_is_invariant_to_pbc_unwrapping(self):
        wrapped_data, unwrapped_data = periodic_segment_data(
            (11.8, 2.5, 0.0)
        )

        self.assertEqual(unwrapped_data["coordinates"][1], (11.8, 2.5, 0.0))
        self.assertEqual(unwrapped_data["primary_edges"], ((0, 2),))
        numpy.testing.assert_allclose(
            unwrapped_data["periodic_segments"][0]["coordinates"],
            wrapped_data["periodic_segments"][0]["coordinates"],
        )

    def test_periodic_segment_does_not_wrap_disabled_axis(self):
        _wrapped_data, unwrapped_data = periodic_segment_data(
            (11.8, 12.5, 0.0)
        )
        segment = unwrapped_data["periodic_segments"][0]

        self.assertEqual(segment["coordinates"][1][1], 12.5)

    def test_topology_must_match_structure_and_periodic_shifts_require_cell(self):
        reference = structure()
        other = structure()
        with self.assertRaisesRegex(ValueError, "does not match"):
            _structure_view_data(reference, topology(other))
        with self.assertRaisesRegex(ValueError, "cell"):
            _structure_view_data(
                reference,
                topology(reference, shifts=((1, 0, 0), (0, 0, 0))),
            )


if __name__ == "__main__":
    unittest.main()
