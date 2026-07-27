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
from ChemBlender.core.import_pipeline import (
    ImportCommitDecisions,
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

    def test_malformed_properties_requires_explicit_override_for_diagnostic(self):
        registry = builtin_reader_registry()
        malformed = FIXTURES / "extxyz" / "invalid-property.extxyz"

        with self.assertRaises(LookupError):
            registry.select(malformed)
        with self.assertRaisesRegex(ValueError, "positive"):
            registry.parse(malformed, reader_id="extxyz")


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


class ExtXYZStagingTests(unittest.TestCase):
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

            self.assertIsInstance(frames.data.values, numpy.memmap)
            self.assertTrue(tuple(session.artifact_root.glob("*.npy")))
            root = session.root
            session.register_result(uuid4(), batch)
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
