from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import (
    AtomFrameProperty,
    CategoricalData,
    CellFrameProperty,
    DatasetStatus,
    FrameProperty,
    FrameSet,
    QCProject,
    builtin_reader_registry,
    close_session,
    create_session,
)
from ChemBlender.core.formats.extxyz import EXTXYZ_READER, parse_extxyz
from ChemBlender.core.formats import extxyz as extxyz_module
from ChemBlender.core.import_pipeline import (
    ImportCommitDecisions,
    ImportCancelled,
    ImportRequest,
    ImportSource,
    StagedImportSession,
    ValidationMode,
    commit_import_preview,
)
from ChemBlender.core.import_pipeline import transaction as transaction_module
from ChemBlender.reader_api.protocol import ParseRequest
from ChemBlender.reader_api.builtin_bridge import internal_batch_from_public
from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry


FIXTURES = Path(__file__).parent / "fixtures"


class ExtXYZReaderSelectionTests(unittest.TestCase):
    def test_catalog_routes_plain_xyz_and_properties_extxyz_without_ambiguity(self):
        registry = builtin_reader_registry()

        self.assertEqual(
            registry.select(FIXTURES / "xyz" / "water.xyz").reader_id,
            "xyz",
        )
        self.assertEqual(
            registry.select(
                FIXTURES / "extxyz" / "properties-mixed.extxyz"
            ).reader_id,
            "extxyz",
        )
        self.assertEqual(EXTXYZ_READER.reader_version, "1")

    def test_large_preflight_defers_full_parse_until_materialization(self):
        source = FIXTURES / "extxyz" / "multiframe-cell.extxyz"
        with TemporaryDirectory() as directory, patch.object(
            extxyz_module,
            "_DEFERRED_PREVIEW_BYTES",
            0,
        ):
            session = StagedImportSession.create(temp_parent=Path(directory))
            try:
                preview = preflight_reader_plugins(
                    ImportRequest(
                        (ImportSource(source),),
                        ValidationMode.BALANCED,
                    ),
                    builtin_reader_plugin_registry(),
                    session,
                )
                batch_id, = preview.staged_batch_ids
                staged = session.result(batch_id)
                frames = next(
                    item
                    for item in staged.datasets
                    if isinstance(item, FrameSet)
                )
                self.assertEqual(frames.data.shape, (2, 1, 3))
                self.assertTrue(session.has_pending_materializer(batch_id))

                materialized = session.materialize_result(batch_id)
                full_frames = next(
                    item
                    for item in materialized.datasets
                    if isinstance(item, FrameSet)
                )
                self.assertIsInstance(full_frames.data.values, numpy.memmap)
                self.assertTrue(
                    numpy.array_equal(
                        numpy.asarray(full_frames.data.values),
                        numpy.asarray(parse_extxyz(source).datasets[0].data.values),
                    )
                )
                self.assertFalse(session.has_pending_materializer(batch_id))
            finally:
                session.discard()

    def test_deferred_commit_cancellation_keeps_preview_and_live_project(self):
        source = FIXTURES / "extxyz" / "multiframe-cell.extxyz"
        with TemporaryDirectory() as directory, patch.object(
            extxyz_module,
            "_DEFERRED_PREVIEW_BYTES",
            0,
        ):
            root = Path(directory)
            staged = StagedImportSession.create(temp_parent=root)
            project_session = create_session(temp_parent=root)
            try:
                preview = preflight_reader_plugins(
                    ImportRequest(
                        (ImportSource(source),),
                        ValidationMode.BALANCED,
                    ),
                    builtin_reader_plugin_registry(),
                    staged,
                )
                batch_id, = preview.staged_batch_ids
                previous = project_session.project

                with self.assertRaises(ImportCancelled):
                    commit_import_preview(
                        project_session,
                        staged,
                        preview,
                        ImportCommitDecisions(),
                        is_cancelled=lambda: True,
                    )

                self.assertIs(project_session.project, previous)
                self.assertTrue(staged.has_pending_materializer(batch_id))
            finally:
                staged.discard()
                close_session(project_session)

    def test_deferred_materialization_preserves_reviewed_diagnostic_ids(self):
        source = FIXTURES / "extxyz" / "properties-mixed.extxyz"
        with TemporaryDirectory() as directory, patch.object(
            extxyz_module,
            "_DEFERRED_PREVIEW_BYTES",
            0,
        ):
            session = StagedImportSession.create(temp_parent=Path(directory))
            try:
                preview = preflight_reader_plugins(
                    ImportRequest((ImportSource(source),)),
                    builtin_reader_plugin_registry(),
                    session,
                )
                batch_id, = preview.staged_batch_ids
                reviewed_ids = session.result(
                    batch_id
                ).source_revisions[0].diagnostic_ids
                self.assertTrue(reviewed_ids)

                materialized = session.materialize_result(batch_id)

                self.assertEqual(
                    materialized.source_revisions[0].diagnostic_ids,
                    reviewed_ids,
                )
                self.assertEqual(
                    tuple(item.id for item in materialized.diagnostics),
                    reviewed_ids,
                )
            finally:
                session.discard()

    def test_changed_materialized_inventory_keeps_retryable_preview_snapshot(self):
        with TemporaryDirectory() as directory, patch.object(
            extxyz_module,
            "_DEFERRED_PREVIEW_BYTES",
            0,
        ):
            root = Path(directory)
            source = root / "identity-change.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3\nC 0 0 0\n"
                "1\nProperties=species:S:1:pos:R:3\nO 0 0 0\n",
                encoding="utf-8",
            )
            session = StagedImportSession.create(temp_parent=root)
            try:
                preview = preflight_reader_plugins(
                    ImportRequest((ImportSource(source),)),
                    builtin_reader_plugin_registry(),
                    session,
                )
                batch_id, = preview.staged_batch_ids

                for _attempt in range(2):
                    with self.assertRaisesRegex(
                        ValueError,
                        "refresh Import Preview",
                    ):
                        session.materialize_result(batch_id)
                    self.assertTrue(
                        session.has_pending_materializer(batch_id)
                    )
                    self.assertEqual(
                        len(
                            tuple(
                                session.artifact_root.rglob(
                                    extxyz_module._PREVIEW_SNAPSHOT_NAME
                                )
                            )
                        ),
                        1,
                    )
                    self.assertEqual(
                        tuple(session.artifact_root.rglob("*.npy")),
                        (),
                    )
            finally:
                session.discard()

    def test_missing_deferred_snapshot_never_commits_preview_placeholders(self):
        source = FIXTURES / "extxyz" / "multiframe-cell.extxyz"
        with TemporaryDirectory() as directory, patch.object(
            extxyz_module,
            "_DEFERRED_PREVIEW_BYTES",
            0,
        ):
            session = StagedImportSession.create(temp_parent=Path(directory))
            try:
                preview = preflight_reader_plugins(
                    ImportRequest((ImportSource(source),)),
                    builtin_reader_plugin_registry(),
                    session,
                )
                batch_id, = preview.staged_batch_ids
                snapshot, = session.artifact_root.rglob(
                    extxyz_module._PREVIEW_SNAPSHOT_NAME
                )
                snapshot.unlink()

                with self.assertRaisesRegex(
                    extxyz_module.ExtXYZSyntaxError,
                    "snapshot is missing",
                ):
                    session.materialize_result(batch_id)

                self.assertTrue(session.has_pending_materializer(batch_id))
            finally:
                session.discard()

    def test_malformed_properties_requires_explicit_override_for_diagnostic(self):
        registry = builtin_reader_registry()
        malformed = FIXTURES / "extxyz" / "invalid-property.extxyz"

        with self.assertRaises(LookupError):
            registry.select(malformed)
        with self.assertRaisesRegex(ValueError, "positive"):
            registry.parse(malformed, reader_id="extxyz")

    def test_sniff_requires_a_structured_complete_properties_schema(self):
        registry = builtin_reader_registry()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prose = root / "prose.xyz"
            prose.write_text(
                "1\nProperties are useful prose\nH 0 0 0\n",
                encoding="utf-8",
            )
            incomplete = root / "incomplete.xyz"
            incomplete.write_text(
                "1\nProperties=foo:R:1\n1\n",
                encoding="utf-8",
            )

            self.assertEqual(registry.select(prose).reader_id, "xyz")
            with self.assertRaises(LookupError):
                registry.select(incomplete)
            with self.assertRaisesRegex(
                ValueError,
                "species:S:1",
            ):
                registry.parse(incomplete, reader_id="extxyz")


class ExtXYZProjectMappingTests(unittest.TestCase):
    def test_known_and_unknown_atom_and_frame_properties_are_typed(self):
        batch = parse_extxyz(
            FIXTURES / "extxyz" / "properties-mixed.extxyz"
        )
        structure, = batch.structures
        frames = next(
            item for item in batch.datasets if isinstance(item, FrameSet)
        )
        properties = {
            item.semantic_role: item
            for item in batch.datasets
            if item is not frames
        }

        self.assertEqual(structure.atomic_numbers, (6, 1))
        self.assertEqual(frames.data.shape, (1, 2, 3))
        self.assertEqual(
            properties["atomic_charge"].data.values.tolist(),
            [[-0.2, 0.2]],
        )
        self.assertEqual(
            properties["atomic_charge"].data.unit,
            "elementary_charge",
        )
        self.assertEqual(
            properties["fixed"].data.values.dtype,
            numpy.dtype(numpy.bool_),
        )
        self.assertEqual(properties["group"].data.values.dtype.kind, "i")
        self.assertEqual(
            properties["energy"].data.values.tolist(),
            [-1.25],
        )
        self.assertTrue(
            any(
                issue.path == "atom_properties.charge"
                for issue in batch.report.issues
            )
        )
        project = QCProject(id=structure.id, schema_version="0.2")
        project.commit(batch)

    def test_lattice_pbc_defaults_and_changing_cell_property(self):
        batch = parse_extxyz(
            FIXTURES / "extxyz" / "multiframe-cell.extxyz"
        )
        structure, = batch.structures
        frames = next(
            item for item in batch.datasets if isinstance(item, FrameSet)
        )
        cells = next(
            item
            for item in batch.datasets
            if isinstance(item, CellFrameProperty)
        )

        self.assertEqual(structure.periodic.pbc, (True, True, True))
        numpy.testing.assert_allclose(structure.cell.values, numpy.eye(3) * 4)
        self.assertEqual(frames.data.shape, (2, 1, 3))
        self.assertEqual(cells.data.shape, (2, 3, 3))
        numpy.testing.assert_allclose(cells.data.values[1], numpy.eye(3) * 5)

        with TemporaryDirectory() as directory:
            plain = Path(directory) / "plain.extxyz"
            plain.write_text(
                "1\nProperties=species:S:1:pos:R:3\nH 0 0 0\n",
                encoding="utf-8",
            )
            plain_structure, = parse_extxyz(plain).structures
            self.assertIsNone(plain_structure.periodic)

            explicit = Path(directory) / "explicit.extxyz"
            explicit.write_text(
                '1\nLattice="2 0 0 0 3 0 0 0 4" pbc="T F T" '
                "Properties=species:S:1:pos:R:3\nH 0 0 0\n",
                encoding="utf-8",
            )
            explicit_structure, = parse_extxyz(explicit).structures
            self.assertEqual(
                explicit_structure.periodic.pbc,
                (True, False, True),
            )
            numpy.testing.assert_allclose(
                explicit_structure.cell.values,
                numpy.diag((2, 3, 4)),
            )

    def test_partial_numeric_logical_and_categorical_properties_keep_missingness(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "partial.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3:q:R:1:flag:L:1:"
                "label:S:1\nC 0 0 0 1.5 T donor\n"
                "1\nProperties=species:S:1:pos:R:3\nC 0.1 0 0\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)

        properties = {
            item.semantic_role: item
            for item in batch.datasets
            if isinstance(item, AtomFrameProperty)
        }
        for name in ("q", "flag"):
            self.assertEqual(properties[name].status, DatasetStatus.AMBIGUOUS)
            self.assertEqual(
                properties[name].validity_mask.values.tolist(),
                [[True], [False]],
            )
        labels = properties["label"]
        self.assertIsInstance(labels.data, CategoricalData)
        self.assertEqual(labels.data.codes.values.tolist(), [[0], [-1]])
        self.assertIsNone(labels.validity_mask)

    def test_incompatible_atom_identity_splits_deterministically(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "split.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3\nH 0 0 0\n"
                "1\nProperties=species:S:1:pos:R:3\nHe 0 0 0\n",
                encoding="utf-8",
            )
            first = parse_extxyz(source)
            second = parse_extxyz(source)

        self.assertEqual(len(first.structures), 2)
        self.assertEqual(
            tuple(item.id for item in first.structures),
            tuple(item.id for item in second.structures),
        )
        self.assertTrue(
            any("atom identity" in issue.message for issue in first.report.issues)
        )
        self.assertEqual(
            set(first.report.created_entity_ids),
            {
                *(item.id for item in first.structures),
                *(item.id for item in first.datasets),
                *(item.id for item in first.provenance),
            },
        )

    def test_explicit_units_are_validated_and_unknown_lexemes_are_preserved(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "units.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3:charge:R:1 "
                "charge_unit=not_a_unit energy=-1 energy_unit=hartree\n"
                "C 0 0 0 -0.2\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)

        properties = {
            item.semantic_role: item
            for item in batch.datasets
            if item.semantic_role != "coordinates"
        }
        self.assertEqual(properties["atomic_charge"].data.unit, "unknown")
        self.assertEqual(
            properties["atomic_charge"].status,
            DatasetStatus.AMBIGUOUS,
        )
        self.assertEqual(properties["energy"].data.unit, "unknown")
        self.assertEqual(properties["energy"].status, DatasetStatus.AMBIGUOUS)
        self.assertIn("charge_unit", properties)
        self.assertIn("energy_unit", properties)
        self.assertFalse(
            any(
                "declared no unit" in issue.message
                for issue in batch.report.issues
            )
        )

    def test_recognized_units_suppress_assumption_diagnostics(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "units.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3:charge:R:1 "
                "charge_unit=elementary_charge energy=-1 "
                "energy_unit=electron_volt\n"
                "C 0 0 0 -0.2\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)

        self.assertFalse(
            any(
                issue.path in {
                    "atom_properties.charge",
                    "frame_properties.energy",
                }
                for issue in batch.report.issues
            )
        )

    def test_stress_and_virial_record_six_and_nine_component_conventions(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "tensor.extxyz"
            source.write_text(
                '1\nProperties=species:S:1:pos:R:3 '
                'stress="1 2 3 4 5 6" '
                'virial="1 0 0 0 1 0 0 0 1"\n'
                "C 0 0 0\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)

        properties = {
            item.semantic_role: item
            for item in batch.datasets
            if isinstance(item, FrameProperty)
        }
        self.assertEqual(properties["stress_voigt"].data.shape, (1, 6))
        self.assertEqual(properties["virial_matrix"].data.shape, (1, 9))
        self.assertEqual(
            properties["stress_voigt"].status,
            DatasetStatus.AMBIGUOUS,
        )

    def test_out_of_range_integer_metadata_is_reported_and_retained_raw(self):
        huge = 2**64
        with TemporaryDirectory() as directory:
            source = Path(directory) / "huge.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3 "
                f"huge_scalar={huge} "
                f"huge_vector=[{huge},{huge + 1}]\n"
                "H 0 0 0\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)

        roles = {
            item.semantic_role
            for item in batch.datasets
            if isinstance(item, FrameProperty)
        }
        self.assertNotIn("huge_scalar", roles)
        self.assertNotIn("huge_vector", roles)
        issues = {
            issue.path: issue.message
            for issue in batch.report.issues
        }
        for name in ("huge_scalar", "huge_vector"):
            self.assertIn(f"metadata.{name}", issues)
            self.assertIn(
                "cannot be represented",
                issues[f"metadata.{name}"],
            )


class ExtXYZStagingTests(unittest.TestCase):
    def test_split_source_uses_exactly_one_plan_and_one_fill_scan(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "split.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3\nH 0 0 0\n"
                "1\nProperties=species:S:1:pos:R:3\nHe 0 0 0\n",
                encoding="utf-8",
            )
            original = extxyz_module.iter_extxyz_frames
            scans = 0

            def counted(path):
                nonlocal scans
                scans += 1
                return original(path)

            with patch.object(
                extxyz_module,
                "iter_extxyz_frames",
                side_effect=counted,
            ):
                parse_extxyz(source)

        self.assertEqual(scans, 2)

    def test_plan_and_fill_use_one_immutable_source_snapshot(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            session = StagedImportSession.create(temp_parent=root)
            source = root / "replace.extxyz"
            original = (
                "1\nProperties=species:S:1:pos:R:3\nH 1 0 0\n"
            )
            source.write_text(original, encoding="utf-8")
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            original_plan = extxyz_module._plan_source

            def plan_then_replace(snapshot, is_cancelled, issues):
                plan = original_plan(snapshot, is_cancelled, issues)
                source.write_text(
                    "1\nProperties=species:S:1:pos:R:3\nHe 9 0 0\n",
                    encoding="utf-8",
                )
                return plan

            with patch.object(
                extxyz_module,
                "_plan_source",
                side_effect=plan_then_replace,
            ):
                batch = parse_extxyz(
                    source,
                    staging_root=session.artifact_root,
                )

            try:
                structure, = batch.structures
                self.assertEqual(structure.atomic_numbers, (1,))
                numpy.testing.assert_array_equal(
                    structure.coordinates.values,
                    [[1.0, 0.0, 0.0]],
                )
                provenance, = batch.provenance
                self.assertEqual(provenance.source, str(source.resolve()))
                self.assertEqual(provenance.source_hash, original_hash)
                self.assertFalse(
                    any(
                        path.suffix in {".extxyz", ".tmp"}
                        for path in session.artifact_root.rglob("*")
                    )
                )
            finally:
                session.register_result(uuid4(), batch)
                session.discard()

    def test_array_owner_cleanup_is_best_effort_and_aggregates_failures(self):
        calls = []

        class Mapping:
            def __init__(self, label, failure=None):
                self.label = label
                self.failure = failure

            def close(self):
                calls.append(f"close:{self.label}")
                if self.failure is not None:
                    raise self.failure

        class Value:
            def __init__(self, mapping):
                self._mmap = mapping

        class File:
            def __init__(self, label, failure=None):
                self.label = label
                self.failure = failure

            def unlink(self):
                calls.append(f"unlink:{self.label}")
                if self.failure is not None:
                    raise self.failure

        class Root:
            def rmdir(self):
                calls.append("rmdir")
                raise OSError("root failed")

        owner = object.__new__(extxyz_module._ArrayOwner)
        owner.root = Root()
        owner.arrays = [
            (Value(Mapping("first")), File("first", OSError("unlink failed"))),
            (Value(Mapping("second", OSError("close failed"))), File("second")),
        ]
        owner._snapshot_path = None
        owner._snapshot_root = None
        owner._snapshot_root_owned = False

        with self.assertRaisesRegex(OSError, "close failed") as caught:
            owner.cleanup()

        self.assertEqual(
            tuple(calls),
            (
                "close:second",
                "unlink:second",
                "close:first",
                "unlink:first",
                "rmdir",
            ),
        )
        self.assertEqual(owner.arrays, [])
        notes = tuple(getattr(caught.exception, "__notes__", ()))
        self.assertTrue(any("unlink failed" in note for note in notes))
        self.assertTrue(any("root failed" in note for note in notes))

    def test_parse_primary_error_survives_owner_cleanup_failure(self):
        primary = KeyboardInterrupt("cancel parse")

        def cancel():
            raise primary

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "cancel.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3\nH 0 0 0\n",
                encoding="utf-8",
            )
            with patch.object(
                extxyz_module._ArrayOwner,
                "cleanup",
                side_effect=OSError("cleanup failed"),
            ):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    parse_extxyz(
                        source,
                        staging_root=root,
                        is_cancelled=cancel,
                    )

        self.assertIs(caught.exception, primary)
        self.assertTrue(
            any(
                "cleanup failed" in note
                for note in getattr(primary, "__notes__", ())
            )
        )

    def test_multiple_sources_get_distinct_staged_backing_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            session = StagedImportSession.create(temp_parent=root)
            first = parse_extxyz(
                FIXTURES / "extxyz" / "multiframe-cell.extxyz",
                staging_root=session.artifact_root,
            )
            first_frames = next(
                item for item in first.datasets if isinstance(item, FrameSet)
            )
            before = numpy.asarray(first_frames.data.values).copy()
            second_source = root / "second.extxyz"
            second_source.write_text(
                "1\nProperties=species:S:1:pos:R:3\nH 9 0 0\n",
                encoding="utf-8",
            )
            second = parse_extxyz(
                second_source,
                staging_root=session.artifact_root,
            )
            second_frames = next(
                item for item in second.datasets if isinstance(item, FrameSet)
            )

            self.assertNotEqual(
                Path(first_frames.data.values.filename).parent,
                Path(second_frames.data.values.filename).parent,
            )
            numpy.testing.assert_array_equal(first_frames.data.values, before)
            session.register_result(uuid4(), first)
            session.register_result(uuid4(), second)
            session.discard()

    def test_staged_values_and_validity_masks_share_the_owner(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            session = StagedImportSession.create(temp_parent=root)
            source = root / "partial.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3:q:R:1\n"
                "C 0 0 0 1\n"
                "1\nProperties=species:S:1:pos:R:3\nC 0 0 0\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(
                source,
                staging_root=session.artifact_root,
            )
            prop = next(
                item
                for item in batch.datasets
                if isinstance(item, AtomFrameProperty)
            )

            self.assertIsInstance(prop.data.values, numpy.memmap)
            self.assertIsInstance(
                prop.validity_mask.values,
                numpy.memmap,
            )
            session.register_result(uuid4(), batch)
            session.discard()

    def test_fill_pass_requires_exact_cancellation_bool(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            calls = 0

            def check():
                nonlocal calls
                calls += 1
                return 1 if calls == 4 else False

            with self.assertRaisesRegex(TypeError, "bool"):
                parse_extxyz(
                    FIXTURES / "extxyz" / "multiframe-cell.extxyz",
                    staging_root=root,
                    is_cancelled=check,
                )
            self.assertEqual(tuple(root.iterdir()), ())

    def test_publication_failure_keeps_live_project_and_staged_owner(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            staged = StagedImportSession.create(temp_parent=root)
            project_session = create_session(temp_parent=root)
            request = ImportRequest(
                (
                    ImportSource(
                        FIXTURES / "extxyz" / "multiframe-cell.extxyz"
                    ),
                ),
                ValidationMode.BALANCED,
            )
            preview = preflight_reader_plugins(
                request,
                builtin_reader_plugin_registry(),
                staged,
            )
            previous = project_session.project

            with patch.object(
                transaction_module,
                "solidify_session",
                side_effect=OSError("publication failed"),
            ):
                with self.assertRaisesRegex(OSError, "publication failed"):
                    commit_import_preview(
                        project_session,
                        staged,
                        preview,
                        ImportCommitDecisions(),
                    )

            self.assertIs(project_session.project, previous)
            self.assertIsNone(project_session.sidecar_path)
            self.assertTrue(staged.root.exists())
            staged.discard()
            close_session(project_session)

    def test_builtin_parse_request_uses_staging_root(self):
        source = FIXTURES / "extxyz" / "multiframe-cell.extxyz"
        with TemporaryDirectory() as directory:
            session = StagedImportSession.create(temp_parent=Path(directory))
            result = builtin_reader_plugin_registry().parse(
                "extxyz",
                ParseRequest(
                    source,
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                    "strict",
                    {},
                    session.artifact_root,
                    lambda _event: None,
                    lambda: False,
                ),
            )
            frames = next(
                item for item in result.datasets if isinstance(item, FrameSet)
            )

            self.assertIsInstance(frames.data.values, numpy.memmap)
            session.register_result(uuid4(), internal_batch_from_public(result))
            session.discard()

    def test_staged_parse_owns_memmaps_and_discard_releases_them(self):
        with TemporaryDirectory() as directory:
            parent = Path(directory)
            session = StagedImportSession.create(temp_parent=parent)
            batch = parse_extxyz(
                FIXTURES / "extxyz" / "multiframe-cell.extxyz",
                staging_root=session.artifact_root,
            )
            frames = next(
                item for item in batch.datasets if isinstance(item, FrameSet)
            )

            root = session.root
            session.register_result(uuid4(), batch)
            try:
                self.assertIsInstance(frames.data.values, numpy.memmap)
                files = tuple(session.artifact_root.rglob("*.npy"))
                self.assertTrue(files)
                self.assertEqual(len({path.parent for path in files}), 1)
            finally:
                session.discard()
            self.assertFalse(root.exists())

    def test_cancellation_removes_incomplete_staged_arrays(self):
        class Cancelled(BaseException):
            pass

        with TemporaryDirectory() as directory:
            root = Path(directory)
            calls = 0

            def check():
                nonlocal calls
                calls += 1
                if calls > 1:
                    raise Cancelled
                return False

            with self.assertRaises(Cancelled):
                parse_extxyz(
                    FIXTURES / "extxyz" / "multiframe-cell.extxyz",
                    staging_root=root,
                    is_cancelled=check,
                )
            self.assertEqual(tuple(root.iterdir()), ())


if __name__ == "__main__":
    unittest.main()
