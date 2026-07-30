import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import (
    AtomicProperty,
    CapabilitySupport,
    CategoricalData,
    DatasetStatus,
    IssueKind,
    QCProject,
    QualityStatus,
    TopologySource,
    builtin_reader_descriptors,
    builtin_reader_registry,
    close_project,
    open_project,
    save_project,
)
from ChemBlender.core.formats import mol2


FIXTURES = Path(__file__).parent / "fixtures" / "mol2"


def _datasets(batch):
    return {dataset.semantic_role: dataset for dataset in batch.datasets}


def _annotations(batch):
    return {annotation.key: annotation.value for annotation in batch.annotations}


def _bond_record(name, declared_bonds, bond_lines):
    return (
        b"@<TRIPOS>MOLECULE\n"
        + name.encode("ascii")
        + b"\n2 "
        + str(declared_bonds).encode("ascii")
        + b" 0 0 0\nSMALL\nNO_CHARGES\n"
        b"@<TRIPOS>ATOM\n"
        b"10 C1 0 0 0 C.3\n"
        b"42 H1 1 0 0 H\n"
        b"@<TRIPOS>BOND\n"
        + bond_lines
    )


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
    def _parse_between_valid_records(self, invalid_record):
        from tempfile import TemporaryDirectory

        valid = (FIXTURES / "small.mol2").read_bytes()
        with TemporaryDirectory() as directory:
            source = Path(directory) / "bond-recovery.mol2"
            source.write_bytes(valid + invalid_record + valid)
            try:
                return mol2.parse_mol2(source)
            except ValueError as error:
                self.fail(
                    f"Balanced MOL2 bond recovery raised {type(error).__name__}: "
                    f"{error}"
                )

    def _assert_strict_rejects(self, invalid_record):
        from tempfile import TemporaryDirectory

        from ChemBlender.reader_api import ParseRequest

        valid = (FIXTURES / "small.mol2").read_bytes()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "strict-bond-recovery.mol2"
            raw = valid + invalid_record + valid
            source.write_bytes(raw)
            request = ParseRequest(
                source,
                hashlib.sha256(raw).hexdigest(),
                "strict",
                {},
                root,
                lambda _event: None,
                lambda: False,
            )
            with self.assertRaisesRegex(ValueError, "MOL2 record 1 failed"):
                mol2.parse_mol2_request(request)

    def _assert_middle_topology_invalid(
        self, batch, expected_path="topology.bonds"
    ):
        self.assertEqual(len(batch.structures), 3)
        self.assertEqual(len(batch.molecular_records), 3)
        self.assertEqual(len(batch.topologies), 2)
        self.assertEqual(
            tuple(record.source_record_index for record in batch.molecular_records),
            (0, 1, 2),
        )
        self.assertIsNone(batch.molecular_records[1].topology_id)
        invalid = [
            diagnostic
            for diagnostic in batch.diagnostics
            if diagnostic.quality_status is QualityStatus.INVALID
            and "record-000001" in diagnostic.record_key
        ]
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0].field_path, expected_path)

    def test_duplicate_canonical_edge_keeps_atoms_and_neighbor_records(self):
        batch = self._parse_between_valid_records(
            _bond_record(
                "duplicate edge",
                2,
                b"7 10 42 1\n8 42 10 1\n",
            )
        )

        self._assert_middle_topology_invalid(batch)

    def test_self_edge_keeps_atoms_and_neighbor_records(self):
        batch = self._parse_between_valid_records(
            _bond_record("self edge", 1, b"7 10 10 1\n")
        )

        self._assert_middle_topology_invalid(batch)

    def test_malformed_bond_numeric_keeps_atoms_and_neighbor_records(self):
        batch = self._parse_between_valid_records(
            _bond_record("malformed numeric", 1, b"x 10 42 1\n")
        )

        self._assert_middle_topology_invalid(batch, "bond[0].syntax")

    def test_bond_count_mismatch_keeps_atoms_and_neighbor_records(self):
        batch = self._parse_between_valid_records(
            _bond_record("count mismatch", 2, b"7 10 42 1\n")
        )

        self._assert_middle_topology_invalid(batch, "bond.count")

    def test_strict_rejects_duplicate_canonical_edge_record(self):
        self._assert_strict_rejects(
            _bond_record(
                "duplicate edge",
                2,
                b"7 10 42 1\n8 42 10 1\n",
            )
        )

    def test_strict_rejects_self_edge_record(self):
        self._assert_strict_rejects(
            _bond_record("self edge", 1, b"7 10 10 1\n")
        )

    def test_strict_rejects_malformed_bond_numeric_record(self):
        self._assert_strict_rejects(
            _bond_record("malformed numeric", 1, b"x 10 42 1\n")
        )

    def test_strict_rejects_bond_count_mismatch_record(self):
        self._assert_strict_rejects(
            _bond_record("count mismatch", 2, b"7 10 42 1\n")
        )

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
            b"@<TRIPOS>MOLECULE\npartial charges\n2 1 0 0 0\nSMALL\nUSER_CHARGES\n"
            b"@<TRIPOS>ATOM\n"
            b"1 C1 0 0 0 C.3 **** **** -0.2\n"
            b"2 H1 1 0 0 H\n"
            b"@<TRIPOS>BOND\n1 1 2 1\n"
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "partial-charge.mol2"
            source.write_bytes(raw)
            batch = mol2.parse_mol2(source)

            charges = _datasets(batch)["partial_charge"]
            values = numpy.asarray(charges.data.values)
            self.assertEqual(values[0], -0.2)
            self.assertTrue(numpy.isnan(values[1]))
            self.assertEqual(numpy.isfinite(values).tolist(), [True, False])
            self.assertIs(charges.status, DatasetStatus.PARTIAL)

            project = QCProject(uuid4(), "1.0")
            project.commit(batch)
            sidecar = root / "partial-charge.cbq"
            save_project(sidecar, project)
            reopened = open_project(sidecar)
            try:
                restored = next(
                    value
                    for value in reopened.datasets.values()
                    if value.semantic_role == "partial_charge"
                )
                self.assertTrue(numpy.isnan(restored.data.values[1]))
                self.assertIs(restored.status, DatasetStatus.PARTIAL)
            finally:
                close_project(reopened)

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
            (IssueKind.MISSING, "atom[1].name"),
            tuple((issue.kind, issue.path) for issue in batch.report.issues),
        )
        self.assertIn(
            (IssueKind.MISSING, "atom[1].atom_type"),
            tuple((issue.kind, issue.path) for issue in batch.report.issues),
        )

    def test_missing_atom_name_does_not_make_atom_type_partial(self):
        raw = (
            b"@<TRIPOS>MOLECULE\nmissing name\n1 0 0 0 0\nSMALL\n"
            b"NO_CHARGES\n@<TRIPOS>ATOM\n1 * 0 0 0 C.3\n"
        )
        with TemporaryDirectory() as directory:
            source = Path(directory) / "missing-name.mol2"
            source.write_bytes(raw)
            batch = mol2.parse_mol2(source)

        atom_type = _datasets(batch)["atom_type"]
        self.assertIs(atom_type.status, DatasetStatus.COMPLETE)
        self.assertIn(
            (IssueKind.MISSING, "atom[0].name"),
            tuple((issue.kind, issue.path) for issue in batch.report.issues),
        )
        self.assertNotIn(
            (IssueKind.MISSING, "atom[0].atom_type"),
            tuple((issue.kind, issue.path) for issue in batch.report.issues),
        )

    def test_balanced_keeps_topology_and_substructure_labels_are_recovered(self):
        raw = (
            b"@<TRIPOS>MOLECULE\nsubstructure recovery\n3 2 2 0 0\nSMALL\n"
            b"NO_CHARGES\n@<TRIPOS>ATOM\n"
            b"1 C1 0 0 0 C.3 5 ****\n"
            b"2 C2 1 0 0 C.3 5 INLINE\n"
            b"3 H1 2 0 0 H\n"
            b"@<TRIPOS>BOND\n1 1 2 1\n2 2 3 1\n"
            b"@<TRIPOS>SUBSTRUCTURE\n5 TABLE 1 GROUP\nbroken\n"
        )
        with TemporaryDirectory() as directory:
            source = Path(directory) / "substructure-recovery.mol2"
            source.write_bytes(raw)
            batch = mol2.parse_mol2(source)

        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(len(batch.topologies), 1)
        substructure_ids = _datasets(batch)["substructure_id"]
        self.assertEqual(substructure_ids.data.values.tolist(), [5, 5, 0])
        self.assertIs(substructure_ids.status, DatasetStatus.PARTIAL)
        names = _datasets(batch)["substructure_name"]
        self.assertEqual(names.data.categories, ("TABLE", "INLINE"))
        self.assertEqual(names.data.codes.values.tolist(), [0, 1, -1])
        self.assertIs(names.status, DatasetStatus.PARTIAL)
        self.assertIn(
            (IssueKind.AMBIGUOUS, "atom[1].substructure_name"),
            tuple((issue.kind, issue.path) for issue in batch.report.issues),
        )
        self.assertIn(
            (IssueKind.INVALID, "substructure[1].syntax"),
            tuple((issue.kind, issue.path) for issue in batch.report.issues),
        )
        self._assert_strict_rejects(raw)

    def test_each_record_raw_block_is_hashed_once_for_entity_identity(self):
        source = FIXTURES / "small.mol2"
        raw = source.read_bytes()
        real_sha256 = hashlib.sha256

        with patch.object(mol2.hashlib, "sha256", wraps=real_sha256) as sha256:
            mol2.parse_mol2(source)

        self.assertEqual(
            sum(call.args == (raw,) for call in sha256.call_args_list),
            2,
        )

    def test_zero_molecule_records_fail_closed_for_all_reader_routes(self):
        from ChemBlender.reader_api import ParseRequest

        raw = b"ordinary text\n@<TRIPOS>ATOM\n1 C1 0 0 0 C.3\n"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "not-mol2.mol2"
            source.write_bytes(raw)
            calls = (
                ("direct", lambda: mol2.parse_mol2(source)),
                (
                    "explicit-reader",
                    lambda: builtin_reader_registry().parse(
                        source, reader_id="mol2"
                    ),
                ),
                *(
                    (
                        mode,
                        lambda mode=mode: mol2.parse_mol2_request(
                            ParseRequest(
                                source,
                                hashlib.sha256(raw).hexdigest(),
                                mode,
                                {},
                                root,
                                lambda _event: None,
                                lambda: False,
                            )
                        ),
                    )
                    for mode in ("strict", "balanced", "maximum")
                ),
            )
            for route, call in calls:
                with self.subTest(route=route):
                    with self.assertRaisesRegex(
                        ValueError, "contains no MOLECULE records"
                    ):
                        call()


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
    def test_repeated_set_diagnostics_survive_preview_commit_and_sidecar_reopen(self):
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

        raw = (
            (FIXTURES / "small.mol2").read_bytes()
            + b"@<TRIPOS>SET\n"
            b"2 SECOND_SET ATOMS STATIC\n"
            b"1 42\n"
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "small.mol2"
            source_path.write_bytes(raw)
            first_ids = tuple(
                diagnostic.id
                for diagnostic in mol2.parse_mol2(source_path).diagnostics
            )
            second_ids = tuple(
                diagnostic.id
                for diagnostic in mol2.parse_mol2(source_path).diagnostics
            )
            self.assertEqual(first_ids, second_ids)
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
                self.assertEqual(len(staged.diagnostics), 2)
                self.assertEqual(
                    len({diagnostic.id for diagnostic in staged.diagnostics}),
                    2,
                )
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
                self.assertEqual(len(result.project.diagnostics), 2)
                sidecar = root / "mol2.cbq"
                save_project(sidecar, result.project)
                reopened = open_project(sidecar)
                try:
                    record = next(iter(reopened.molecular_records.values()))
                    self.assertEqual(record.raw_block, raw)
                    self.assertEqual(len(reopened.diagnostics), 2)
                    self.assertEqual(
                        len(
                            {
                                diagnostic.id
                                for diagnostic in reopened.diagnostics.values()
                            }
                        ),
                        2,
                    )
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
