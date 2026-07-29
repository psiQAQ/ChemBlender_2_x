from dataclasses import FrozenInstanceError
from math import cos, pi, sin
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    ImportBatch,
    IssueKind,
    QCProject,
    QualityStatus,
    Structure,
    TopologySource,
)
from ChemBlender.core.topology.infer import (
    TopologyInferenceSettings,
    infer_distance_topology,
)


def structure(atomic_numbers, coordinates, *, unit="angstrom", **changes):
    values = {
        "id": uuid4(),
        "revision": "structure-r1",
        "atomic_numbers": tuple(atomic_numbers),
        "coordinates": ArrayData(
            numpy.asarray(coordinates, dtype=float),
            ("atom", "xyz"),
            unit,
        ),
    }
    values.update(changes)
    return Structure(**values)


def edges(batch):
    return tuple(map(tuple, batch.topologies[0].bond_indices.values.tolist()))


class TopologyInferenceTests(unittest.TestCase):
    def test_settings_are_frozen_and_validate_supported_values(self):
        settings = TopologyInferenceSettings()

        self.assertEqual(settings.covalent_scale, 1.15)
        self.assertEqual(settings.tolerance_angstrom, 0.20)
        self.assertEqual(settings.minimum_distance_angstrom, 0.25)
        self.assertEqual(settings.max_coordination_default, 8)
        self.assertEqual(settings.metal_mode, "coordination")
        self.assertFalse(settings.periodic)
        with self.assertRaises(FrozenInstanceError):
            settings.periodic = True

        invalid = (
            {"covalent_scale": 0.0},
            {"covalent_scale": float("nan")},
            {"tolerance_angstrom": -0.1},
            {"minimum_distance_angstrom": float("inf")},
            {"max_coordination_default": 0},
            {"max_coordination_default": True},
            {"metal_mode": "guess"},
            {"periodic": 1},
        )
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    TopologyInferenceSettings(**changes)

    def test_water_and_bohr_coordinates_produce_deterministic_bonds(self):
        water = structure(
            (8, 1, 1),
            ((0.0, 0.0, 0.0), (0.96, 0.0, 0.0), (-0.24, 0.93, 0.0)),
        )
        bohr_water = structure(
            (8, 1, 1),
            numpy.asarray(water.coordinates.values) / 0.529177210903,
            unit="bohr",
        )

        first = infer_distance_topology(water)
        second = infer_distance_topology(water)
        converted = infer_distance_topology(bohr_water)

        self.assertEqual(edges(first), ((0, 1), (0, 2)))
        self.assertEqual(edges(first), edges(converted))
        self.assertEqual(first.topologies[0].id, second.topologies[0].id)
        self.assertEqual(first.topologies[0].revision, second.topologies[0].revision)
        topology = first.topologies[0]
        self.assertEqual(topology.source_kind, TopologySource.DISTANCE_INFERRED)
        self.assertEqual(topology.quality_status, QualityStatus.COMPLETE)
        self.assertEqual(topology.provenance_ids, (first.provenance[0].id,))
        self.assertIn(
            ("structure_revision", water.revision),
            topology.inference_parameters,
        )
        self.assertEqual(
            first.report.created_entity_ids,
            (topology.id, first.provenance[0].id),
        )
        project = QCProject(id=uuid4(), schema_version="0.2")
        project.commit(ImportBatch(structures=(water,)))
        project.commit(first)
        self.assertIs(project.topologies[topology.id], topology)

    def test_benzene_disconnected_fragments_and_edge_order_are_stable(self):
        ring = tuple(
            (1.4 * cos(index * pi / 3), 1.4 * sin(index * pi / 3), 0.0)
            for index in range(6)
        )
        benzene = infer_distance_topology(structure((6,) * 6, ring))
        self.assertEqual(
            edges(benzene),
            ((0, 1), (0, 5), (1, 2), (2, 3), (3, 4), (4, 5)),
        )

        two_fragments = structure(
            (8, 1, 1, 8, 1, 1),
            (
                (0.0, 0.0, 0.0),
                (0.96, 0.0, 0.0),
                (-0.24, 0.93, 0.0),
                (10.0, 0.0, 0.0),
                (10.96, 0.0, 0.0),
                (9.76, 0.93, 0.0),
            ),
        )
        self.assertEqual(
            edges(infer_distance_topology(two_fragments)),
            ((0, 1), (0, 2), (3, 4), (3, 5)),
        )

    def test_close_duplicate_atoms_return_invalid_report_without_topology(self):
        duplicate = structure(
            (6, 6, 1),
            ((0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (1.1, 0.0, 0.0)),
        )

        batch = infer_distance_topology(duplicate)

        self.assertEqual(batch.topologies, ())
        self.assertEqual(batch.provenance, ())
        self.assertEqual(len(batch.report.issues), 1)
        self.assertEqual(batch.report.issues[0].kind, IssueKind.INVALID)
        self.assertIn("minimum_distance_angstrom", batch.report.issues[0].message)

    def test_metal_connections_are_coordination_and_ambiguous(self):
        complex_structure = structure(
            (26, 8, 8, 8, 8),
            (
                (0.0, 0.0, 0.0),
                (2.0, 0.0, 0.0),
                (-2.0, 0.0, 0.0),
                (0.0, 2.0, 0.0),
                (0.0, -2.0, 0.0),
            ),
        )

        topology = infer_distance_topology(complex_structure).topologies[0]

        self.assertEqual(edges(infer_distance_topology(complex_structure)), (
            (0, 1),
            (0, 2),
            (0, 3),
            (0, 4),
        ))
        self.assertTrue(numpy.all(topology.bond_orders.values == 0.0))
        self.assertEqual(topology.quality_status, QualityStatus.AMBIGUOUS)

    def test_coordination_limit_removes_longer_candidates_deterministically(self):
        crowded = structure(
            (6, 1, 1, 1),
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.05, 0.0), (0.0, 0.0, 1.1)),
        )
        settings = TopologyInferenceSettings(max_coordination_default=2)

        self.assertEqual(
            edges(infer_distance_topology(crowded, settings)),
            ((0, 1), (0, 2)),
        )

    def test_unsupported_units_and_periodic_requests_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            structure((1,), ((float("nan"), 0.0, 0.0),))
        with self.assertRaisesRegex(ValueError, "known length unit"):
            structure((1,), ((0.0, 0.0, 0.0),), unit="nanometer")
        with self.assertRaisesRegex(ValueError, "nonperiodic"):
            infer_distance_topology(
                structure((1,), ((0.0, 0.0, 0.0),)),
                TopologyInferenceSettings(periodic=True),
            )

    def test_fifty_thousand_sparse_atoms_complete_without_quadratic_scan(self):
        count = 50_000
        indices = numpy.arange(count)
        coordinates = numpy.column_stack(
            (
                indices % 100,
                (indices // 100) % 100,
                indices // 10_000,
            )
        ).astype(float)
        coordinates *= 4.0

        batch = infer_distance_topology(structure((6,) * count, coordinates))

        self.assertEqual(batch.topologies[0].bond_indices.shape, (0, 2))


if __name__ == "__main__":
    unittest.main()
