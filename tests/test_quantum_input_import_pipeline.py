from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ChemBlender.core import close_session, create_session
from ChemBlender.core.import_pipeline import (
    ImportCommitDecisions,
    ImportRequest,
    ImportSource,
    StagedImportSession,
    ValidationMode,
    commit_import_preview,
)
from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry


ROOT = Path(__file__).resolve().parents[1]


class QuantumInputImportPipelineTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
