import hashlib
import unittest
from pathlib import Path

import numpy

from ChemBlender.core import (
    AtomicProperty,
    CapabilitySupport,
    CategoricalData,
    DatasetStatus,
    IssueKind,
    QualityStatus,
    TopologySource,
    builtin_reader_descriptors,
    builtin_reader_registry,
)
from ChemBlender.core.formats import mol2


FIXTURES = Path(__file__).parent / "fixtures" / "mol2"


def _datasets(batch):
    return {dataset.semantic_role: dataset for dataset in batch.datasets}


def _annotations(batch):
    return {annotation.key: annotation.value for annotation in batch.annotations}


class Mol2MappingTests(unittest.TestCase):
    def test_reader_parse_entrypoint_exists(self):
        self.assertTrue(callable(getattr(mol2, "parse_mol2", None)))

    def test_small_record_maps_structure_properties_annotations_and_envelope(self):
        source = FIXTURES / "small.mol2"
        raw = source.read_bytes()

        batch = mol2.parse_mol2(source)

        self.assertEqual(len(batch.structures), 1)
        structure = batch.structures[0]
        self.assertEqual(structure.atomic_numbers, (6, 1))
        self.assertEqual(
            numpy.asarray(structure.coordinates.values).tolist(),
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        )
        self.assertEqual(
            numpy.asarray(structure.atomic_identity.atom_names.codes.values).tolist(),
            [0, 1],
        )
        self.assertEqual(
            structure.atomic_identity.atom_names.categories,
            ("C1", "H1"),
        )

        datasets = _datasets(batch)
        self.assertEqual(
            set(datasets),
            {"atom_type", "substructure_id", "substructure_name", "partial_charge"},
        )
        self.assertTrue(all(isinstance(value, AtomicProperty) for value in datasets.values()))
        self.assertIsInstance(datasets["atom_type"].data, CategoricalData)
        self.assertEqual(datasets["atom_type"].data.categories, ("C.3", "H"))
        self.assertEqual(
            numpy.asarray(datasets["atom_type"].data.codes.values).tolist(),
            [0, 1],
        )
        self.assertEqual(
            numpy.asarray(datasets["substructure_id"].data.values).tolist(),
            [101, 101],
        )
        self.assertEqual(
            datasets["substructure_name"].data.categories,
            ("METHANE",),
        )
        self.assertEqual(
            numpy.asarray(datasets["substructure_name"].data.codes.values).tolist(),
            [0, 0],
        )
        self.assertEqual(
            numpy.asarray(datasets["partial_charge"].data.values).tolist(),
            [-0.12, 0.12],
        )
        self.assertTrue(
            all(value.status is DatasetStatus.COMPLETE for value in datasets.values())
        )

        self.assertEqual(
            _annotations(batch),
            {
                "molecule_type": "SMALL",
                "charge_type": "USER_CHARGES",
                "status_bits": "INVALID_CHARGES",
            },
        )
        self.assertEqual(len(batch.molecular_records), 1)
        record = batch.molecular_records[0]
        self.assertEqual(record.raw_block, raw)
        self.assertEqual(record.title, "methane fragment")
        self.assertEqual(record.source_record_index, 0)
        self.assertEqual(record.structure_id, structure.id)

        self.assertEqual(len(batch.topologies), 1)
        topology = batch.topologies[0]
        self.assertEqual(record.topology_id, topology.id)
        self.assertEqual(structure.topology_ids, (topology.id,))
        self.assertIs(topology.source_kind, TopologySource.EXPLICIT_FILE)
        self.assertIs(topology.quality_status, QualityStatus.COMPLETE)
        self.assertEqual(
            numpy.asarray(topology.bond_indices.values).tolist(),
            [[0, 1]],
        )
        self.assertEqual(
            numpy.asarray(topology.bond_orders.values).tolist(),
            [1.0],
        )
        self.assertEqual(
            numpy.asarray(topology.aromatic_flags.values).tolist(),
            [False],
        )
        self.assertEqual(topology.stereo_labels, ("",))

        self.assertEqual(batch.report.reader_id, "mol2")
        self.assertEqual(batch.report.reader_version, "1")
        self.assertIn(
            (IssueKind.UNSUPPORTED, "section.set"),
            tuple((issue.kind, issue.path) for issue in batch.report.issues),
        )
        self.assertIn(
            ("mol2.unsupported", "section.set"),
            tuple(
                (diagnostic.code, diagnostic.field_path)
                for diagnostic in batch.diagnostics
            ),
        )
        self.assertEqual(
            batch.report.created_entity_ids,
            (
                *(value.id for value in batch.structures),
                *(value.id for value in batch.topologies),
                *(value.id for value in batch.molecular_records),
                *(value.id for value in batch.annotations),
                *(value.id for value in batch.datasets),
                *(value.id for value in batch.provenance),
            ),
        )
        self.assertEqual(len(batch.sources), 1)
        self.assertEqual(len(batch.source_revisions), 1)
        revision = batch.source_revisions[0]
        self.assertEqual(record.source_revision_id, revision.id)
        self.assertEqual(revision.source_id, batch.sources[0].id)
        self.assertEqual(revision.content_hash, hashlib.sha256(raw).hexdigest())
        self.assertEqual(revision.created_entity_ids, batch.report.created_entity_ids)
        self.assertEqual(
            revision.diagnostic_ids,
            tuple(diagnostic.id for diagnostic in batch.diagnostics),
        )

    def test_aromatic_and_amide_bonds_keep_distinct_flags(self):
        aromatic_batch = mol2.parse_mol2(FIXTURES / "aromatic.mol2")
        self.assertEqual(len(aromatic_batch.topologies), 1)
        aromatic = aromatic_batch.topologies[0]
        self.assertEqual(
            numpy.asarray(aromatic.aromatic_flags.values).tolist(),
            [True, True, True, True, True, True],
        )
        self.assertEqual(aromatic.stereo_labels, ("", "", "", "", "", ""))

        amide_batch = mol2.parse_mol2(FIXTURES / "substructure.mol2")
        self.assertEqual(len(amide_batch.topologies), 1)
        amide = amide_batch.topologies[0]
        self.assertEqual(
            numpy.asarray(amide.aromatic_flags.values).tolist(),
            [False, False],
        )
        self.assertEqual(amide.stereo_labels, ("amide", ""))

    def test_bondless_record_maps_an_empty_explicit_topology(self):
        try:
            batch = mol2.parse_mol2(FIXTURES / "multi.mol2")
        except ValueError as error:
            self.fail(f"bondless MOL2 topology raised {type(error).__name__}")

        self.assertEqual(len(batch.topologies), 2)
        self.assertEqual(batch.topologies[0].bond_indices.shape, (0, 2))
        self.assertEqual(batch.topologies[0].bond_orders.shape, (0,))


class Mol2RecoveryTests(unittest.TestCase):
    def test_balanced_mode_keeps_records_around_a_malformed_record(self):
        first, second = (FIXTURES / "multi.mol2").read_bytes().split(
            b"@<TRIPOS>MOLECULE\nsecond",
            1,
        )
        malformed = (
            b"@<TRIPOS>MOLECULE\nbroken\n1 0 0 0 0\nSMALL\nNO_CHARGES\n"
            b"@<TRIPOS>ATOM\n9 X 0 not-a-number 0 C.3\n"
        )
        raw = (
            first
            + malformed
            + b"@<TRIPOS>MOLECULE\nsecond"
            + second
        )
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            source = Path(directory) / "partial.mol2"
            source.write_bytes(raw)
            try:
                batch = mol2.parse_mol2(source)
            except ValueError as error:
                self.fail(f"Balanced MOL2 recovery raised {type(error).__name__}")

        self.assertEqual(
            tuple(record.source_record_index for record in batch.molecular_records),
            (0, 2),
        )
        self.assertEqual(len(batch.structures), 2)
        failures = [
            diagnostic
            for diagnostic in batch.diagnostics
            if diagnostic.code == "mol2.record_parse_failed"
        ]
        self.assertEqual(len(failures), 1)
        self.assertIs(failures[0].quality_status, QualityStatus.INVALID)
        self.assertIn("record-000001", failures[0].record_key)

    def test_invalid_bonds_keep_structure_without_topology(self):
        batch = mol2.parse_mol2(FIXTURES / "malformed.mol2")

        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(batch.topologies, ())
        self.assertEqual(batch.structures[0].topology_ids, ())
        self.assertIsNone(batch.molecular_records[0].topology_id)
        invalid = [
            diagnostic
            for diagnostic in batch.diagnostics
            if diagnostic.field_path == "bond[0].atom_references"
        ]
        self.assertEqual(len(invalid), 1)
        self.assertIs(invalid[0].quality_status, QualityStatus.INVALID)
        self.assertEqual(
            invalid[0].recovery_action,
            "the Structure was retained without an explicit topology",
        )

    def test_missing_charge_values_make_a_partial_property(self):
        raw = (
            b"@<TRIPOS>MOLECULE\npartial charges\n2 0 0 0 0\nSMALL\nUSER_CHARGES\n"
            b"@<TRIPOS>ATOM\n"
            b"1 C1 0 0 0 C.3 **** **** -0.2\n"
            b"2 H1 1 0 0 H\n"
        )
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            source = Path(directory) / "partial-charge.mol2"
            source.write_bytes(raw)
            batch = mol2.parse_mol2(source)

        charges = _datasets(batch)["partial_charge"]
        self.assertEqual(
            numpy.asarray(charges.data.values).tolist(),
            [-0.2, 0.0],
        )
        self.assertIs(charges.status, DatasetStatus.PARTIAL)

    def test_recovery_sentinels_become_missing_categories(self):
        raw = (
            b"@<TRIPOS>MOLECULE\nmissing category\n2 0 0 0 0\nSMALL\nNO_CHARGES\n"
            b"@<TRIPOS>ATOM\n"
            b"1 C1 0 0 0 C.3\n"
            b"2 * 1 0 0 *\n"
        )
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            source = Path(directory) / "missing-category.mol2"
            source.write_bytes(raw)
            batch = mol2.parse_mol2(source)

        structure = batch.structures[0]
        atom_types = _datasets(batch)["atom_type"]
        self.assertEqual(
            numpy.asarray(structure.atomic_identity.atom_names.codes.values).tolist(),
            [0, -1],
        )
        self.assertEqual(structure.atomic_identity.atom_names.categories, ("C1",))
        self.assertEqual(
            numpy.asarray(atom_types.data.codes.values).tolist(),
            [0, -1],
        )
        self.assertEqual(atom_types.data.categories, ("C.3",))
        self.assertIs(atom_types.status, DatasetStatus.PARTIAL)
        self.assertIn(
            (IssueKind.MISSING, "atom[1].name_and_type"),
            tuple((issue.kind, issue.path) for issue in batch.report.issues),
        )


class Mol2RegistrationTests(unittest.TestCase):
    def test_builtin_descriptor_is_registered_with_exact_capabilities(self):
        descriptor = getattr(mol2, "MOL2_READER", None)
        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.reader_id, "mol2")
        self.assertEqual(descriptor.reader_version, "1")
        self.assertEqual(descriptor.extensions, (".mol2",))
        self.assertEqual(
            dict(descriptor.capabilities),
            {
                "structure": CapabilitySupport.SUPPORTED,
                "topology": CapabilitySupport.SUPPORTED,
                "atomic_property": CapabilitySupport.SUPPORTED,
                "substructure": CapabilitySupport.SUPPORTED,
                "multi_record": CapabilitySupport.SUPPORTED,
            },
        )
        self.assertIn(descriptor, builtin_reader_descriptors())
        self.assertIs(
            builtin_reader_registry().select("unused", reader_id="mol2"),
            descriptor,
        )

        from ChemBlender.reader_api import ExecutionMode
        from ChemBlender.reader_api.registry import builtin_reader_plugin_registry

        public = next(
            value
            for value in builtin_reader_plugin_registry().descriptors
            if value.reader_id == "mol2"
        )
        self.assertIs(public.execution_mode, ExecutionMode.BUILT_IN)

    def test_content_markers_select_mol2_without_extension_ambiguity(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            source = Path(directory) / "wrong.mol"
            source.write_bytes((FIXTURES / "small.mol2").read_bytes())
            selected = builtin_reader_registry().select(source)

        self.assertEqual(selected.reader_id, "mol2")

    def test_reader_api_v1_conformance_passes(self):
        from ChemBlender.reader_api import ReaderConformanceCase, run_reader_conformance
        from ChemBlender.reader_api.registry import builtin_reader_plugin_registry

        result = run_reader_conformance(
            ReaderConformanceCase(
                name="mol2-small",
                registry=builtin_reader_plugin_registry(),
                reader_id="mol2",
                source_path=FIXTURES / "small.mol2",
                expected_capabilities=(
                    "atomic_property",
                    "multi_record",
                    "structure",
                    "substructure",
                    "topology",
                ),
            )
        )

        self.assertTrue(result.passed, result.as_dict())


class Mol2PersistenceTests(unittest.TestCase):
    def test_preview_commit_and_sidecar_reopen_preserve_record_mapping(self):
        from tempfile import TemporaryDirectory

        from ChemBlender.core import (
            close_project,
            close_session,
            create_session,
            open_project,
            save_project,
        )
        from ChemBlender.core.import_pipeline import (
            ImportCommitDecisions,
            ImportRequest,
            ImportSource,
            ReaderOverride,
            StagedImportSession,
            ValidationMode,
            commit_import_preview,
        )
        from ChemBlender.reader_api.import_pipeline_bridge import (
            preflight_reader_plugins,
        )
        from ChemBlender.reader_api.registry import builtin_reader_plugin_registry

        raw = (FIXTURES / "small.mol2").read_bytes()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "small.mol2"
            source_path.write_bytes(raw)
            source = ImportSource(source_path)
            request = ImportRequest(
                (source,),
                ValidationMode.BALANCED,
                (ReaderOverride(source.id, "mol2"),),
            )
            staged_session = StagedImportSession.create(temp_parent=root)
            project_session = create_session(temp_parent=root)
            try:
                preview = preflight_reader_plugins(
                    request,
                    builtin_reader_plugin_registry(),
                    staged_session,
                )
                self.assertEqual(len(preview.source_previews), 1)
                self.assertEqual(len(preview.staged_batch_ids), 1)
                staged = staged_session.result(preview.staged_batch_ids[0])
                self.assertEqual(len(staged.molecular_records), 1)
                self.assertEqual(
                    staged.molecular_records[0].source_revision_id,
                    staged.source_revisions[0].id,
                )
                self.assertEqual(staged.molecular_records[0].raw_block, raw)

                result = commit_import_preview(
                    project_session,
                    staged_session,
                    preview,
                    ImportCommitDecisions(),
                )
                sidecar = root / "mol2.cbq"
                save_project(sidecar, result.project)
                reopened = open_project(sidecar)
                try:
                    record = next(iter(reopened.molecular_records.values()))
                    self.assertEqual(record.raw_block, raw)
                    self.assertEqual(
                        {value.semantic_role for value in reopened.datasets.values()},
                        {
                            "atom_type",
                            "substructure_id",
                            "substructure_name",
                            "partial_charge",
                        },
                    )
                    self.assertEqual(
                        {
                            value.key: value.value
                            for value in reopened.annotations.values()
                        },
                        {
                            "molecule_type": "SMALL",
                            "charge_type": "USER_CHARGES",
                            "status_bits": "INVALID_CHARGES",
                        },
                    )
                finally:
                    close_project(reopened)
            finally:
                close_session(project_session)
                staged_session.discard()


if __name__ == "__main__":
    unittest.main()
