import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    AtomicProperty,
    DatasetStatus,
    QCProject,
    QualityStatus,
    Structure,
    TopologyRecord,
    TopologySource,
)
from ChemBlender.core.edits.structure import (
    commit_structure_edits,
    preview_structure_edits,
)
from ChemBlender.ui.scientific_edit import preview_structure_object_edits


def array(values, dims, unit, dtype=float):
    return ArrayData(numpy.asarray(values, dtype=dtype), dims, unit)


class _Sequence(list):
    def foreach_get(self, field, target):
        values = []
        for item in self:
            value = getattr(item, field)
            values.extend(value if hasattr(value, "__len__") else (value,))
        target[:] = values


class _AttributeData(list):
    def foreach_get(self, field, target):
        target[:] = [getattr(item, field) for item in self]


class _Object(dict):
    pass


class StructureDerivationTests(unittest.TestCase):
    def setUp(self):
        self.structure_id = uuid4()
        self.topology_id = uuid4()
        self.structure = Structure(
            id=self.structure_id,
            revision="source-r1",
            atomic_numbers=(8, 1),
            coordinates=array(
                ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
                ("atom", "xyz"),
                "angstrom",
            ),
            cell=array(
                ((8.0, 0.0, 0.0), (0.0, 8.0, 0.0), (0.0, 0.0, 8.0)),
                ("cell_vector", "xyz"),
                "angstrom",
            ),
            molecular_charge=0,
            molecular_multiplicity=1,
            topology_ids=(self.topology_id,),
        )
        self.topology = TopologyRecord(
            id=self.topology_id,
            revision="topology-r1",
            structure_id=self.structure_id,
            bond_indices=array(
                ((0, 1),),
                ("bond", "endpoint"),
                "dimensionless",
                int,
            ),
            bond_orders=array(
                (1.0,),
                ("bond",),
                "dimensionless",
            ),
            aromatic_flags=None,
            stereo_labels=("",),
            source_kind=TopologySource.EXPLICIT_FILE,
            quality_status=QualityStatus.COMPLETE,
            inference_parameters=(),
            provenance_ids=(),
        )
        self.dataset = AtomicProperty(
            id=uuid4(),
            revision="charges-r1",
            semantic_role="mulliken_charge",
            domain="atom",
            data=array(
                (-0.2, 0.2),
                ("atom",),
                "elementary_charge",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=self.structure_id,
        )
        self.project = QCProject(
            id=uuid4(),
            schema_version="1.0",
            structures={self.structure.id: self.structure},
            topologies={self.topology.id: self.topology},
            datasets={self.dataset.id: self.dataset},
        )

    def edited(self, **changes):
        values = {
            "atomic_numbers": self.structure.atomic_numbers,
            "coordinates": self.structure.coordinates,
            "bond_indices": self.topology.bond_indices,
            "bond_orders": self.topology.bond_orders,
            "cell": self.structure.cell,
        }
        values.update(changes)
        return values

    def test_preview_reports_scientific_changes_and_linked_results(self):
        preview = preview_structure_edits(
            self.project,
            self.structure,
            self.topology,
            **self.edited(
                atomic_numbers=(7, 1, 6),
                coordinates=array(
                    (
                        (0.0, 0.0, 0.0),
                        (1.5, 0.0, 0.0),
                        (3.0, 0.0, 0.0),
                    ),
                    ("atom", "xyz"),
                    "angstrom",
                ),
                bond_indices=array(
                    ((0, 1), (1, 2)),
                    ("bond", "endpoint"),
                    "dimensionless",
                    int,
                ),
                bond_orders=array(
                    (2.0, 1.0),
                    ("bond",),
                    "dimensionless",
                ),
                cell=array(
                    (
                        (9.0, 0.0, 0.0),
                        (0.0, 8.0, 0.0),
                        (0.0, 0.0, 8.0),
                    ),
                    ("cell_vector", "xyz"),
                    "angstrom",
                ),
            ),
        )

        self.assertTrue(preview.has_changes)
        self.assertEqual((preview.atom_count_before, preview.atom_count_after), (2, 3))
        self.assertEqual(preview.coordinate_change_count, 1)
        self.assertEqual(preview.element_change_count, 1)
        self.assertEqual(preview.bond_added_count, 1)
        self.assertEqual(preview.bond_removed_count, 0)
        self.assertEqual(preview.bond_order_change_count, 1)
        self.assertTrue(preview.cell_changed)
        self.assertAlmostEqual(preview.max_displacement_angstrom, 0.5)
        self.assertEqual(preview.affected_result_ids, (self.dataset.id,))

    def test_equivalent_bohr_view_and_object_transform_are_not_edits(self):
        preview = preview_structure_edits(
            self.project,
            self.structure,
            self.topology,
            **self.edited(
                coordinates=array(
                    (
                        (0.0, 0.0, 0.0),
                        (1.8897261246257702, 0.0, 0.0),
                    ),
                    ("atom", "xyz"),
                    "bohr",
                )
            ),
        )

        self.assertFalse(preview.has_changes)
        self.assertEqual(preview.max_displacement_angstrom, 0.0)

    def test_blender_float32_coordinate_quantization_is_not_an_edit(self):
        source = Structure(
            id=uuid4(),
            revision="float32-source",
            atomic_numbers=(8, 1),
            coordinates=array(
                ((-0.24, 0.93, 0.0), (0.96, 0.0, 0.0)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        project = QCProject(
            id=uuid4(),
            schema_version="1.0",
            structures={source.id: source},
        )

        preview = preview_structure_edits(
            project,
            source,
            atomic_numbers=source.atomic_numbers,
            coordinates=ArrayData(
                numpy.asarray(source.coordinates.values, dtype=numpy.float32),
                ("atom", "xyz"),
                "angstrom",
            ),
            cell=None,
        )

        self.assertFalse(preview.has_changes)

    def test_commit_creates_derived_entities_without_inheriting_results(self):
        original_structure = self.structure
        original_topology = self.topology
        edited = self.edited(
            coordinates=array(
                ((0.0, 0.0, 0.0), (1.25, 0.0, 0.0)),
                ("atom", "xyz"),
                "angstrom",
            ),
            bond_orders=array(
                (2.0,),
                ("bond",),
                "dimensionless",
            ),
        )

        batch = commit_structure_edits(
            self.project,
            self.structure,
            self.topology,
            **edited,
        )
        derived = batch.structures[0]
        derived_topology = batch.topologies[0]

        self.assertNotEqual(derived.id, self.structure.id)
        self.assertEqual(derived.topology_ids, (derived_topology.id,))
        self.assertEqual(derived_topology.structure_id, derived.id)
        self.assertIs(derived_topology.source_kind, TopologySource.USER_EDITED)
        self.assertEqual(
            batch.provenance[0].parent_ids,
            (self.structure.id, self.topology.id),
        )
        self.assertEqual(batch.provenance[0].operation, "scientific_edit")
        self.assertEqual(batch.datasets, ())
        self.assertEqual(len(batch.report.issues), 1)
        self.assertIn("not inherited", batch.report.issues[0].message)

        self.project.commit(batch)
        self.assertIs(self.project.structures[self.structure.id], original_structure)
        self.assertIs(self.project.topologies[self.topology.id], original_topology)
        self.assertIs(self.project.datasets[self.dataset.id], self.dataset)
        self.assertIn(derived.id, self.project.structures)
        self.assertIn(derived_topology.id, self.project.topologies)

    def test_identical_edits_have_deterministic_identity(self):
        edited = self.edited(
            coordinates=array(
                ((0.0, 0.0, 0.0), (1.25, 0.0, 0.0)),
                ("atom", "xyz"),
                "angstrom",
            )
        )

        first = commit_structure_edits(
            self.project,
            self.structure,
            self.topology,
            **edited,
        )
        second = commit_structure_edits(
            self.project,
            self.structure,
            self.topology,
            **edited,
        )

        self.assertEqual(first.structures[0].id, second.structures[0].id)
        self.assertEqual(
            first.structures[0].revision,
            second.structures[0].revision,
        )
        numpy.testing.assert_array_equal(
            first.structures[0].coordinates.values,
            second.structures[0].coordinates.values,
        )
        self.assertEqual(first.topologies[0].id, second.topologies[0].id)
        self.assertEqual(
            first.topologies[0].revision,
            second.topologies[0].revision,
        )
        self.assertEqual(first.provenance[0], second.provenance[0])

    def test_commit_rejects_a_noop(self):
        with self.assertRaisesRegex(ValueError, "no scientific edits"):
            commit_structure_edits(
                self.project,
                self.structure,
                self.topology,
                **self.edited(),
            )

    def test_malformed_edited_bonds_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            preview_structure_edits(
                self.project,
                self.structure,
                self.topology,
                **self.edited(
                    bond_indices=array(
                        ((0, 2),),
                        ("bond", "endpoint"),
                        "dimensionless",
                        int,
                    )
                ),
            )

    def test_stable_atom_ids_distinguish_removal_from_coordinate_edit(self):
        preview = preview_structure_edits(
            self.project,
            self.structure,
            self.topology,
            atomic_numbers=(1,),
            coordinates=array(
                ((1.0, 0.0, 0.0),),
                ("atom", "xyz"),
                "angstrom",
            ),
            source_atom_indices=(1,),
            bond_indices=ArrayData(
                numpy.empty((0, 2), dtype=int),
                ("bond", "endpoint"),
                "dimensionless",
            ),
            bond_orders=array(
                (),
                ("bond",),
                "dimensionless",
            ),
            cell=self.structure.cell,
        )

        self.assertEqual(preview.atom_count_after, 1)
        self.assertEqual(preview.coordinate_change_count, 0)
        self.assertEqual(preview.element_change_count, 0)

    def test_object_preview_uses_local_mesh_data_not_object_transform(self):
        vertices = _Sequence(
            (
                type("Vertex", (), {"co": (0.0, 0.0, 0.0)})(),
                type("Vertex", (), {"co": (1.0, 0.0, 0.0)})(),
            )
        )
        edges = (
            type("Edge", (), {"vertices": (0, 1)})(),
        )
        attributes = {
            "atomic_num": type(
                "Attribute",
                (),
                {
                    "data": _AttributeData(
                        (
                            type("Value", (), {"value": 8})(),
                            type("Value", (), {"value": 1})(),
                        )
                    )
                },
            )(),
            "cbq_atom_id": type(
                "Attribute",
                (),
                {
                    "data": _AttributeData(
                        (
                            type("Value", (), {"value": 0})(),
                            type("Value", (), {"value": 1})(),
                        )
                    )
                },
            )(),
            "cbq_bond_order": type(
                "Attribute",
                (),
                {
                    "data": _AttributeData(
                        (type("Value", (), {"value": 1.0})(),)
                    )
                },
            )(),
        }
        obj = _Object(
            cb_structure_contract="structure_view_v1",
            cb_structure_id=str(self.structure.id),
            cb_structure_revision=self.structure.revision,
            cb_topology_id=str(self.topology.id),
            cb_topology_revision=self.topology.revision,
            cb_periodic_cell=tuple(
                float(value)
                for row in self.structure.cell.values
                for value in row
            ),
        )
        obj.data = type(
            "Mesh",
            (),
            {
                "vertices": vertices,
                "edges": edges,
                "attributes": attributes,
            },
        )()
        obj.matrix_world = (
            (2.0, 0.0, 0.0, 5.0),
            (0.0, 2.0, 0.0, 6.0),
            (0.0, 0.0, 2.0, 7.0),
            (0.0, 0.0, 0.0, 1.0),
        )

        preview = preview_structure_object_edits(self.project, obj)
        self.assertFalse(preview.has_changes)
        vertices[1].co = (1.2, 0.0, 0.0)
        preview = preview_structure_object_edits(self.project, obj)
        self.assertTrue(preview.has_changes)
        self.assertAlmostEqual(preview.max_displacement_angstrom, 0.2)


if __name__ == "__main__":
    unittest.main()
