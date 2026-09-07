from pathlib import Path
from dataclasses import replace
import importlib
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from ChemBlender.core import close_session, create_session
from ChemBlender.core.import_pipeline import (
    ImportCommitDecisions,
    DuplicateAction,
    ImportRequest,
    ImportSource,
    StagedImportSession,
    ValidationMode,
    commit_import_preview,
    detect_import_conflicts,
)
from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry


ROOT = Path(__file__).resolve().parents[1]


class QuantumInputImportPipelineTests(unittest.TestCase):
    def test_unit_failures_explain_the_required_correction_in_public_preview(self):
        cases = (
            ("unknown.gjf", "# HF Units=Nanometers\n\nH2\n\n0 1\nH 0 0 0\nH 0 0 1\n\n", "unknown Gaussian coordinate unit option: Nanometers"),
            ("conflict.gjf", "# HF Units=Bohr Units=Angstrom\n\nH2\n\n0 1\nH 0 0 0\nH 0 0 1\n\n", "conflicting Gaussian coordinate units"),
            ("unknown.inp", "%coords Units Nanometers end\n* xyz 0 1\nH 0 0 0\nH 0 0 1\n*\n", "unknown ORCA coordinate unit: nanometers"),
            ("conflict.inp", "! Bohrs Angs\n* xyz 0 1\nH 0 0 0\nH 0 0 1\n*\n", "conflicting ORCA coordinate units"),
        )
        for filename, text, expected in cases:
            with self.subTest(filename=filename), TemporaryDirectory() as directory:
                source = Path(directory) / filename
                source.write_text(text, encoding="utf-8")
                staged = StagedImportSession.create(temp_parent=Path(directory))
                try:
                    preview = preflight_reader_plugins(
                        ImportRequest(sources=(ImportSource(source),)),
                        builtin_reader_plugin_registry(), staged,
                    )
                    source_preview, = preview.source_previews
                    batch = staged.result(source_preview.staged_batch_ids[0])
                    diagnostic, = batch.diagnostics
                    self.assertIn(expected, diagnostic.message)
                    self.assertEqual(diagnostic.field_path, "reader.parse")
                    self.assertFalse(batch.structures)
                finally:
                    staged.discard()

    def test_reader_upgrade_creates_a_revision_without_rescaling_saved_data(self):
        for name, suffix, control in (
            ("gaussian", ".gjf", "# HF Units=Bohr\n\nH2\n\n0 1\nH 0 0 0\nH 0 0 1.4\n\n"),
            ("orca", ".inp", "! HF Bohrs\n* xyz 0 1\nH 0 0 0\nH 0 0 1.4\n*\n"),
        ):
            with self.subTest(reader=name), TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / ("hydrogen" + suffix)
                source.write_text(control, encoding="utf-8")
                module = importlib.import_module(f"ChemBlender.core.formats.{name}_input")
                descriptor = getattr(module, f"{name.upper()}_INPUT_READER")
                session = create_session(temp_parent=root)
                stages = []
                try:
                    old_stage = StagedImportSession.create(temp_parent=root)
                    stages.append(old_stage)
                    # Emulate the published v1 interpretation of the same source bytes.
                    with (
                        mock.patch.object(module, "_READER_VERSION", "1"),
                        mock.patch.object(module, "_coordinate_unit", return_value="angstrom"),
                        mock.patch(
                            "ChemBlender.core.reader_catalog.builtin_reader_descriptors",
                            return_value=(replace(descriptor, reader_version="1"),),
                        ),
                    ):
                        preview = preflight_reader_plugins(
                            ImportRequest(sources=(ImportSource(source),)),
                            builtin_reader_plugin_registry(), old_stage,
                        )
                    first = commit_import_preview(session, old_stage, preview, ImportCommitDecisions())
                    old_revision, = first.project.source_revisions.values()
                    old_structure, = first.project.structures.values()
                    self.assertEqual(old_structure.coordinates.values[1, 2], 1.4)

                    new_stage = StagedImportSession.create(temp_parent=root)
                    stages.append(new_stage)
                    preview = preflight_reader_plugins(
                        ImportRequest(sources=(ImportSource(source),)),
                        builtin_reader_plugin_registry(), new_stage,
                    )
                    conflict, = detect_import_conflicts(session.project, preview, new_stage)
                    preview = replace(preview, conflict_ids=(conflict.id,))
                    self.assertIn(DuplicateAction.NEW_REVISION, conflict.allowed_actions)
                    result = commit_import_preview(
                        session, new_stage, preview,
                        ImportCommitDecisions(conflicts=(conflict,), conflict_decisions={
                            conflict.id: DuplicateAction.NEW_REVISION,
                        }),
                    )
                    upgraded, = (
                        item for item in result.project.source_revisions.values()
                        if item.id != old_revision.id
                    )
                    self.assertEqual(upgraded.source_id, old_revision.source_id)
                    self.assertEqual(upgraded.content_hash, old_revision.content_hash)
                    self.assertNotEqual(upgraded.parse_identity, old_revision.parse_identity)
                    self.assertEqual(upgraded.reader_version, "2")
                    corrected = next(result.project.structures[key] for key in upgraded.created_entity_ids if key in result.project.structures)
                    self.assertAlmostEqual(corrected.coordinates.values[1, 2], 1.4 * 0.529177210903)
                    self.assertEqual(result.project.structures[old_structure.id].coordinates.values[1, 2], 1.4)
                finally:
                    close_session(session)
                    for stage in stages:
                        stage.discard()

    def test_preflight_preview_and_commit_preserve_quantum_input_structure(self):
        cases = (
            ("gaussian/water.gjf", "gaussian-input"),
            ("orca/water.inp", "orca-input"),
        )
        for relative, reader_id in cases:
            with self.subTest(reader_id=reader_id), TemporaryDirectory() as directory:
                root = Path(directory)
                source = ROOT / "tests" / "fixtures" / relative
                staged = StagedImportSession.create(temp_parent=root)
                session = create_session(temp_parent=root)
                try:
                    preview = preflight_reader_plugins(
                        ImportRequest(
                            sources=(ImportSource(source),),
                            validation_mode=ValidationMode.BALANCED,
                        ),
                        builtin_reader_plugin_registry(),
                        staged,
                    )
                    source_preview, = preview.source_previews
                    self.assertEqual(source_preview.selected_reader_id, reader_id)
                    batch = staged.result(source_preview.staged_batch_ids[0])
                    revision, = batch.source_revisions
                    structure, = batch.structures
                    self.assertEqual(revision.reader_id, reader_id)
                    self.assertEqual(structure.atomic_numbers, (8, 1, 1))
                    self.assertEqual(structure.molecular_charge, 0)
                    self.assertEqual(structure.molecular_multiplicity, 1)

                    result = commit_import_preview(
                        session,
                        staged,
                        preview,
                        ImportCommitDecisions(),
                    )
                    restored_revision = result.project.source_revisions[revision.id]
                    restored = next(
                        result.project.structures[entity_id]
                        for entity_id in restored_revision.created_entity_ids
                        if entity_id in result.project.structures
                    )
                    self.assertEqual(restored.atomic_numbers, (8, 1, 1))
                    self.assertEqual(restored.coordinates.unit, "angstrom")
                    self.assertEqual(restored.molecular_charge, 0)
                    self.assertEqual(restored.molecular_multiplicity, 1)
                finally:
                    close_session(session)
                    staged.discard()

    def test_truncated_gaussian_input_keeps_reader_specific_diagnostic(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "truncated.gjf"
            source.write_bytes(b"%chk=water.chk\n#p hf/sto-3g\n\nwater\n")
            staged = StagedImportSession.create(temp_parent=root)
            try:
                preview = preflight_reader_plugins(
                    ImportRequest(sources=(ImportSource(source),)),
                    builtin_reader_plugin_registry(),
                    staged,
                )
                source_preview, = preview.source_previews
                self.assertEqual(
                    source_preview.selected_reader_id,
                    "gaussian-input",
                )
                batch = staged.result(source_preview.staged_batch_ids[0])
                diagnostic, = batch.diagnostics
                self.assertEqual(diagnostic.code, "gaussian-input.invalid")
                self.assertEqual(diagnostic.field_path, "reader.parse")
            finally:
                staged.discard()


if __name__ == "__main__":
    unittest.main()
