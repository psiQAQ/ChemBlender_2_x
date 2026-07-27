from dataclasses import FrozenInstanceError, fields
from copy import deepcopy
import json
from pathlib import Path
import unittest
from uuid import uuid4

import ChemBlender.core as core
from ChemBlender.core import model
from ChemBlender.core.import_pipeline.transaction import _merge_batches
from ChemBlender.core.sidecar import SidecarIntegrityError
from ChemBlender.core.sidecar_migrations import migrate_manifest
import ChemBlender.reader_api as reader_api
import numpy
from worker.runner import _batch_references


LEGACY_SIDECAR = (
    Path(__file__).resolve().parent / "fixtures" / "sidecar" / "model-v01"
)


def array(values, dims):
    return core.ArrayData(numpy.asarray(values), dims, "dimensionless")


def topology_record(**changes):
    values = {
        "id": uuid4(),
        "revision": "topology-r1",
        "structure_id": uuid4(),
        "bond_indices": array(((0, 1), (1, 2)), ("bond", "endpoint")),
        "bond_orders": array((1.0, 1.5), ("bond",)),
        "aromatic_flags": array((False, True), ("bond",)),
        "stereo_labels": ("", "E"),
        "source_kind": core.TopologySource.EXPLICIT_FILE,
        "quality_status": core.QualityStatus.COMPLETE,
        "inference_parameters": (),
        "provenance_ids": (),
    }
    values.update(changes)
    return core.TopologyRecord(**values)


def structure(**changes):
    values = {
        "id": uuid4(),
        "revision": "structure-r1",
        "atomic_numbers": (8, 1, 1),
        "coordinates": core.ArrayData(
            numpy.asarray(
                ((0.0, 0.0, 0.0), (0.96, 0.0, 0.0), (-0.24, 0.93, 0.0))
            ),
            ("atom", "xyz"),
            "angstrom",
        ),
    }
    values.update(changes)
    return core.Structure(**values)


class TopologyRecordTests(unittest.TestCase):
    def test_public_contract_has_exact_source_values_and_fields(self):
        source_type = getattr(model, "TopologySource", None)
        record_type = getattr(model, "TopologyRecord", None)

        self.assertIsNotNone(source_type)
        self.assertIsNotNone(record_type)
        self.assertIs(core.TopologySource, source_type)
        self.assertIs(core.TopologyRecord, record_type)
        self.assertEqual(
            tuple(item.value for item in source_type),
            (
                "explicit_file",
                "rdkit_sanitized",
                "distance_inferred",
                "user_edited",
            ),
        )
        self.assertEqual(
            tuple(field.name for field in fields(record_type)),
            (
                "id",
                "revision",
                "structure_id",
                "bond_indices",
                "bond_orders",
                "aromatic_flags",
                "stereo_labels",
                "source_kind",
                "quality_status",
                "inference_parameters",
                "provenance_ids",
                "bond_lattice_shifts",
            ),
        )

    def test_valid_record_is_frozen_slotted_and_canonicalizes_parameters(self):
        record = topology_record(
            source_kind=core.TopologySource.DISTANCE_INFERRED,
            inference_parameters=(
                ("tolerance_angstrom", 0.2),
                ("covalent_scale", 1.15),
            ),
            provenance_ids=(uuid4(),),
        )

        self.assertEqual(
            record.inference_parameters,
            (("covalent_scale", 1.15), ("tolerance_angstrom", 0.2)),
        )
        self.assertFalse(hasattr(record, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            record.revision = "changed"

    def test_bond_arrays_aromatic_flags_and_stereo_labels_are_validated(self):
        invalid_values = (
            (
                "bond_indices",
                array(1, ()),
                "bond_indices",
            ),
            (
                "bond_indices",
                array(((0, 1, 2),), ("bond", "endpoint")),
                "bond_indices",
            ),
            (
                "bond_indices",
                array(((0.0, 1.0),), ("bond", "endpoint")),
                "bond_indices",
            ),
            (
                "bond_orders",
                object(),
                "bond_orders",
            ),
            (
                "bond_orders",
                array((1.0,), ("edge",)),
                "bond_orders",
            ),
            (
                "bond_orders",
                array((1.0, -1.0), ("bond",)),
                "bond_orders",
            ),
            (
                "aromatic_flags",
                array((0, 1), ("bond",)),
                "aromatic_flags",
            ),
            (
                "aromatic_flags",
                array((True,), ("bond",)),
                "aromatic_flags",
            ),
            ("stereo_labels", ("",), "stereo_labels"),
            ("stereo_labels", ("", 1), "stereo_labels"),
        )
        for name, value, message in invalid_values:
            with self.subTest(name=name, value=value):
                with self.assertRaisesRegex((TypeError, ValueError), message):
                    topology_record(**{name: value})

    def test_identity_source_quality_and_provenance_are_validated(self):
        invalid_values = (
            ("id", "not-a-uuid", "id"),
            ("revision", "", "revision"),
            ("structure_id", "not-a-uuid", "structure_id"),
            ("source_kind", "explicit_file", "source_kind"),
            ("quality_status", "complete", "quality_status"),
            ("provenance_ids", ("not-a-uuid",), "provenance_ids"),
        )
        for name, value, message in invalid_values:
            with self.subTest(name=name):
                with self.assertRaisesRegex((TypeError, ValueError), message):
                    topology_record(**{name: value})

    def test_distance_inference_requires_unique_canonical_parameters(self):
        with self.assertRaisesRegex(ValueError, "inference_parameters"):
            topology_record(
                source_kind=core.TopologySource.DISTANCE_INFERRED,
                inference_parameters=(),
            )
        invalid_parameters = (
            (("scale", 1.0), ("scale", 1.1)),
            (("Bad Key", 1),),
            (("scale", float("nan")),),
            (("settings", {"scale": 1.0}),),
        )
        for parameters in invalid_parameters:
            with self.subTest(parameters=parameters):
                with self.assertRaisesRegex(
                    (TypeError, ValueError), "inference_parameters"
                ):
                    topology_record(inference_parameters=parameters)

    def test_explicit_topology_permits_no_inference_parameters(self):
        record = topology_record()
        self.assertEqual(record.source_kind, core.TopologySource.EXPLICIT_FILE)
        self.assertEqual(record.inference_parameters, ())
        self.assertIsNone(record.bond_lattice_shifts)

    def test_optional_bond_lattice_shifts_are_integer_bond_xyz_values(self):
        valid = topology_record(
            bond_lattice_shifts=array(
                ((0, 0, 0), (1, -1, 0)),
                ("bond", "xyz"),
            )
        )
        self.assertEqual(valid.bond_lattice_shifts.shape, (2, 3))
        invalid = (
            array(((0, 0), (1, 0)), ("bond", "xyz")),
            array(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)), ("bond", "xyz")),
            array(((0, 0, 0),), ("bond", "xyz")),
            array(((0, 0, 0), (1, 0, 0)), ("bond", "axis")),
        )
        for shifts in invalid:
            with self.subTest(shifts=shifts):
                with self.assertRaisesRegex(ValueError, "bond_lattice_shifts"):
                    topology_record(bond_lattice_shifts=shifts)

    def test_structure_has_zero_or_more_topology_references(self):
        reference = structure()
        self.assertIn("topology_ids", tuple(field.name for field in fields(reference)))
        self.assertEqual(reference.topology_ids, ())

    def test_import_batch_and_project_have_topology_registries(self):
        self.assertIn(
            "topologies",
            tuple(field.name for field in fields(core.ImportBatch)),
        )
        self.assertIn(
            "topologies",
            tuple(field.name for field in fields(core.QCProject)),
        )

    def test_project_commits_topology_and_structure_references_atomically(self):
        structure_id = uuid4()
        topology_id = uuid4()
        reference = structure(id=structure_id, topology_ids=(topology_id,))
        topology = topology_record(id=topology_id, structure_id=structure_id)
        project = core.QCProject(id=uuid4(), schema_version="0.2")

        project.commit(
            core.ImportBatch(structures=(reference,), topologies=(topology,))
        )

        self.assertIs(project.structures[structure_id], reference)
        self.assertIs(project.topologies[topology_id], topology)

    def test_project_rejects_dangling_mismatched_and_out_of_range_topology(self):
        structure_id = uuid4()
        topology_id = uuid4()
        cases = (
            (
                core.ImportBatch(
                    topologies=(
                        topology_record(
                            id=topology_id,
                            structure_id=structure_id,
                        ),
                    )
                ),
                "dangling structure",
            ),
            (
                core.ImportBatch(
                    structures=(
                        structure(
                            id=structure_id,
                            topology_ids=(topology_id,),
                        ),
                    )
                ),
                "dangling topology",
            ),
            (
                core.ImportBatch(
                    structures=(
                        structure(
                            id=structure_id,
                            topology_ids=(topology_id,),
                        ),
                        structure(id=uuid4()),
                    ),
                    topologies=(
                        topology_record(
                            id=topology_id,
                            structure_id=uuid4(),
                        ),
                    ),
                ),
                "another structure",
            ),
            (
                core.ImportBatch(
                    structures=(structure(id=structure_id),),
                    topologies=(
                        topology_record(
                            id=topology_id,
                            structure_id=structure_id,
                            bond_indices=array(
                                ((0, 3),),
                                ("bond", "endpoint"),
                            ),
                            bond_orders=array((1.0,), ("bond",)),
                            aromatic_flags=array((False,), ("bond",)),
                            stereo_labels=("",),
                        ),
                    ),
                ),
                "outside",
            ),
            (
                core.ImportBatch(
                    structures=(structure(id=structure_id),),
                    topologies=(
                        topology_record(
                            id=topology_id,
                            structure_id=structure_id,
                            provenance_ids=(uuid4(),),
                        ),
                    ),
                ),
                "provenance",
            ),
        )
        for batch, message in cases:
            with self.subTest(message=message):
                project = core.QCProject(id=uuid4(), schema_version="0.2")
                with self.assertRaisesRegex(ValueError, message):
                    project.commit(batch)
                self.assertEqual(project.structures, {})
                self.assertEqual(project.topologies, {})

    def test_v01_and_v02_embedded_topology_migrate_without_mutating_manifest(self):
        source = json.loads(
            (LEGACY_SIDECAR / "manifest.json").read_text(encoding="utf-8")
        )
        v02 = deepcopy(source)
        v02["manifest_version"] = "0.2"
        v02["project_schema_version"] = "0.2"
        v02["project"]["schema_version"] = "0.2"
        for name in ("sources", "source_revisions", "diagnostics", "calculation_groups", "topologies"):
            v02["project"][name] = {"$dict": []}

        for document in (source, v02):
            with self.subTest(manifest_version=document["manifest_version"]):
                original = deepcopy(document)
                migrated = migrate_manifest(document)

                self.assertEqual(document, original)
                project = migrated["project"]
                structure_value = project["structures"]["$dict"][0][1]
                topology_entries = project["topologies"]["$dict"]
                self.assertIsNone(structure_value["topology"])
                self.assertEqual(len(structure_value["topology_ids"]["$tuple"]), 1)
                self.assertEqual(len(topology_entries), 1)
                topology_id, topology_value = topology_entries[0]
                self.assertEqual(
                    structure_value["topology_ids"]["$tuple"][0],
                    topology_id,
                )
                self.assertEqual(topology_value["$type"], "TopologyRecord")
                self.assertEqual(
                    topology_value["source_kind"],
                    {"$enum": "TopologySource", "value": "distance_inferred"},
                )
                self.assertEqual(
                    topology_value["quality_status"],
                    {"$enum": "QualityStatus", "value": "ambiguous"},
                )
                self.assertEqual(
                    topology_value["inference_parameters"],
                    {
                        "$tuple": [
                            {
                                "$tuple": [
                                    "legacy_origin",
                                    "unverified",
                                ]
                            }
                        ]
                    },
                )
                self.assertIsNone(topology_value["bond_lattice_shifts"])

    def test_batch_bridges_merges_and_worker_references_preserve_topologies(self):
        structure_id = uuid4()
        topology_id = uuid4()
        reference = structure(id=structure_id, topology_ids=(topology_id,))
        topology = topology_record(id=topology_id, structure_id=structure_id)
        batch = core.ImportBatch(
            structures=(reference,),
            topologies=(topology,),
        )

        public = reader_api.public_batch_from_internal(batch)
        restored = reader_api.internal_batch_from_public(public)
        merged = _merge_batches((batch,))
        references = _batch_references(batch)

        self.assertEqual(public.topologies, (topology,))
        self.assertEqual(restored.topologies, (topology,))
        self.assertEqual(merged.topologies, (topology,))
        self.assertIn(topology_id, {item.entity_id for item in references})

    def test_malformed_legacy_topology_migration_is_an_integrity_error(self):
        source = json.loads(
            (LEGACY_SIDECAR / "manifest.json").read_text(encoding="utf-8")
        )
        source["manifest_version"] = "0.2"
        structure_value = source["project"]["structures"]["$dict"][0][1]
        structure_value["id"] = {"$uuid": "not-a-uuid"}

        with self.assertRaisesRegex(
            SidecarIntegrityError,
            "legacy topology",
        ):
            migrate_manifest(source)


if __name__ == "__main__":
    unittest.main()
