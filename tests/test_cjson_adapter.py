import json
import tempfile
import unittest
from pathlib import Path

import numpy

from ChemBlender.core.cjson_adapter import (
    CJSON_READER,
    CJSONCompatibilityError,
    export_cjson,
    parse_cjson,
)
from ChemBlender.core.model import (
    AtomicProperty,
    DatasetStatus,
    ExcitedStateSet,
    FrameSet,
    QCProject,
    QualityStatus,
    TopologySource,
)
from ChemBlender.core.readers import ReaderRegistry
from ChemBlender.core.sidecar import close_project, open_project, save_project
from ChemBlender.core.import_pipeline.parse import stage_import_batch
from ChemBlender.core.import_pipeline.request import ImportSource, ValidationMode
from ChemBlender.ui.topology import topology_choices
from ChemBlender.views.structure import _structure_view_data


FIXTURE = Path(__file__).parent / "fixtures" / "cjson" / "water-results.cjson"


class CJSONAdapterTests(unittest.TestCase):
    def test_structure_topology_charge_selection_and_trajectory_are_normalized(self):
        batch = parse_cjson(FIXTURE)
        structure = batch.structures[0]
        topology = batch.topologies[0]
        self.assertEqual(structure.atomic_numbers, (8, 1, 1))
        self.assertEqual(structure.coordinates.unit, "angstrom")
        self.assertEqual(structure.molecular_charge, 0)
        self.assertEqual(structure.molecular_multiplicity, 1)
        self.assertIsNone(structure.topology)
        self.assertEqual(structure.topology_ids, (topology.id,))
        self.assertEqual(topology.bond_indices.dims, ("bond", "endpoint"))
        numpy.testing.assert_array_equal(topology.bond_indices.values, [[0, 1], [0, 2]])
        numpy.testing.assert_array_equal(topology.bond_orders.values, [1, 1])
        self.assertEqual(topology.source_kind, TopologySource.EXPLICIT_FILE)
        self.assertEqual(topology.quality_status, QualityStatus.COMPLETE)
        self.assertIsNone(topology.bond_lattice_shifts)
        self.assertIsNone(topology.aromatic_flags)
        self.assertEqual(topology.stereo_labels, ("", ""))
        self.assertEqual(topology.provenance_ids, (batch.provenance[0].id,))

        project = QCProject(id=structure.id, schema_version="0.2")
        project.commit(batch)
        self.assertEqual(
            tuple(choice.topology_id for choice in topology_choices(project, structure.id)),
            (topology.id,),
        )
        self.assertEqual(
            _structure_view_data(structure, topology)["primary_edges"],
            ((0, 1), (0, 2)),
        )
        self.assertEqual(
            batch.report.created_entity_ids,
            (
                structure.id,
                topology.id,
                batch.cjson_envelopes[0].id,
                *(dataset.id for dataset in batch.datasets),
                batch.provenance[0].id,
            ),
        )
        duplicate = parse_cjson(FIXTURE).topologies[0]
        self.assertEqual((topology.id, topology.revision), (duplicate.id, duplicate.revision))

        atom_data = {
            item.semantic_role: item
            for item in batch.datasets
            if isinstance(item, AtomicProperty)
        }
        self.assertEqual(atom_data["formal_charge"].data.unit, "elementary_charge")
        self.assertEqual(atom_data["mulliken_charge"].status, DatasetStatus.COMPLETE)
        self.assertEqual(atom_data["selected"].data.values.tolist(), [True, False, True])
        frames = next(item for item in batch.datasets if isinstance(item, FrameSet))
        self.assertEqual(frames.data.shape, (2, 3, 3))

    def test_explicit_bonds_are_canonicalized_before_topology_identity(self):
        source = json.loads(FIXTURE.read_text(encoding="utf-8"))
        source["bonds"] = {
            "connections": {"index": [2, 0, 1, 0]},
            "order": [2, 1],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canonical.cjson"
            path.write_text(json.dumps(source), encoding="utf-8")
            topology = parse_cjson(path).topologies[0]

        numpy.testing.assert_array_equal(topology.bond_indices.values, [[0, 1], [0, 2]])
        numpy.testing.assert_array_equal(topology.bond_orders.values, [1, 2])

    def test_staging_keeps_explicit_topology_in_source_revision(self):
        batch = parse_cjson(FIXTURE)
        staged = stage_import_batch(
            source=ImportSource(FIXTURE),
            validation_mode=ValidationMode.BALANCED,
            content_hash="a" * 64,
            byte_size=FIXTURE.stat().st_size,
            plugin_id="chemblender.builtin",
            reader_id="cjson",
            reader_version="0.1.0",
            api_version="0.1",
            parsed_batch=batch,
        )

        self.assertEqual(
            staged.source_revisions[0].created_entity_ids,
            (
                batch.structures[0].id,
                batch.topologies[0].id,
                batch.cjson_envelopes[0].id,
                *(dataset.id for dataset in batch.datasets),
                batch.provenance[0].id,
            ),
        )

    def test_electronic_spectrum_maps_to_excited_states_with_explicit_conversion(self):
        batch = parse_cjson(FIXTURE)
        states = next(item for item in batch.datasets if isinstance(item, ExcitedStateSet))
        self.assertEqual(states.data.unit, "inverse_centimeter")
        numpy.testing.assert_allclose(states.data.values, numpy.asarray([4.2, 5.1]) * 8065.544005)
        numpy.testing.assert_allclose(states.oscillator_strengths.values, [0.12, 0.35])
        self.assertEqual(states.status, DatasetStatus.AMBIGUOUS)
        self.assertEqual(states.rotatory_strengths.unit, "unknown")

    def test_raw_envelope_round_trips_unknown_and_deferred_fields(self):
        source = json.loads(FIXTURE.read_text(encoding="utf-8"))
        batch = parse_cjson(FIXTURE)
        self.assertEqual(export_cjson(batch.cjson_envelopes[0]), source)
        issue_paths = {issue.path for issue in batch.report.issues}
        self.assertIn("vibrations.eigenVectors", issue_paths)
        self.assertIn("orbitals", issue_paths)
        self.assertIn("cube", issue_paths)

    def test_envelope_and_topology_round_trip_through_sidecar(self):
        batch = parse_cjson(FIXTURE)
        project = QCProject(id=batch.report.created_entity_ids[0], schema_version="0.1")
        project.commit(batch)
        with tempfile.TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "cjson.cbq", project)
            restored = open_project(root)
            try:
                document = export_cjson(next(iter(restored.cjson_envelopes.values())))
                self.assertTrue(document["customProjectField"]["preserve"])
                structure = next(iter(restored.structures.values()))
                topology = restored.topologies[structure.topology_ids[0]]
                self.assertEqual(topology.bond_orders.shape, (2,))
                self.assertEqual(topology.source_kind, TopologySource.EXPLICIT_FILE)
                self.assertEqual(topology.quality_status, QualityStatus.COMPLETE)
            finally:
                close_project(restored)

    def test_reader_registry_detects_cjson(self):
        self.assertIs(ReaderRegistry((CJSON_READER,)).select(FIXTURE), CJSON_READER)

    def test_unknown_cjson_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "future.cjson"
            path.write_text(json.dumps({"chemicalJson": 2, "atoms": {}}), encoding="utf-8")
            with self.assertRaisesRegex(CJSONCompatibilityError, "version 2"):
                parse_cjson(path)


if __name__ == "__main__":
    unittest.main()
