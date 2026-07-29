import hashlib
import importlib
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from ChemBlender import core
from ChemBlender.core.import_pipeline import (
    ImportRequest,
    ImportSource,
    StagedImportSession,
    preflight_import,
)
from ChemBlender.core.readers import ReaderRegistry
from ChemBlender.reader_api import ParseRequest, PublicImportBatch
from ChemBlender.reader_api.registry import (
    builtin_reader_plugin_registry,
    builtin_reader_plugins,
)


ROOT = Path(__file__).resolve().parents[1]
CSCL = ROOT / "tests" / "fixtures" / "cif" / "cscl.cif"


class CIFReaderTests(unittest.TestCase):
    def test_catalog_exposes_cif_without_eager_gemmi_import(self):
        code = """
import sys
from ChemBlender.reader_api.registry import builtin_reader_plugins
plugin = next(
    item for item in builtin_reader_plugins()
    if item.descriptor.reader_id == "cif"
)
assert plugin.descriptor.execution_mode.value == "built_in"
assert "gemmi" not in sys.modules
"""
        completed = subprocess.run([sys.executable, "-c", code], cwd=ROOT)

        self.assertEqual(completed.returncode, 0)

    def test_missing_gemmi_marks_only_cif_unavailable(self):
        import ChemBlender.reader_api.descriptors as descriptors

        find_spec = descriptors.importlib.util.find_spec

        def without_gemmi(module_name):
            return None if module_name == "gemmi" else find_spec(module_name)

        with patch.object(
            descriptors.importlib.util,
            "find_spec",
            side_effect=without_gemmi,
        ):
            plugins = builtin_reader_plugins()

        by_id = {item.descriptor.reader_id: item for item in plugins}
        self.assertIn("cif", by_id)
        cif = by_id["cif"]
        self.assertFalse(cif.descriptor.availability.available)
        self.assertEqual(
            cif.descriptor.availability.reason_code,
            "dependency_missing",
        )
        self.assertEqual(cif.descriptor.availability.detail, "gemmi")
        self.assertTrue(
            next(
                item
                for item in plugins
                if item.descriptor.reader_id == "xyz"
            ).descriptor.availability.available
        )

    def test_builtin_registry_parse_returns_public_batch(self):
        with TemporaryDirectory() as directory:
            registry = builtin_reader_plugin_registry()
            self.assertIn(
                "cif",
                {item.reader_id for item in registry.descriptors},
            )
            request = ParseRequest(
                source_path=CSCL,
                source_content_hash=hashlib.sha256(
                    CSCL.read_bytes()
                ).hexdigest(),
                validation_mode="balanced",
                canonical_parameters={},
                staging_root=Path(directory),
                progress=lambda _event: None,
                is_cancelled=lambda: False,
                source_revision_id=uuid4(),
            )
            result = registry.parse("cif", request)

        self.assertIs(type(result), PublicImportBatch)
        self.assertEqual(result.report.reader_id, "cif")
        self.assertEqual(len(result.structures), 1)
        self.assertEqual(len(result.cif_envelopes), 1)

    def test_import_pipeline_stages_cif_source_revision(self):
        with TemporaryDirectory() as directory:
            session = StagedImportSession.create(temp_parent=Path(directory))
            try:
                preview = preflight_import(
                    ImportRequest(sources=(ImportSource(CSCL),)),
                    ReaderRegistry((core.CIF_READER,)),
                    session,
                )
                batch = session.result(preview.staged_batch_ids[0])
            finally:
                session.discard()

        revision, = batch.source_revisions
        self.assertEqual(revision.reader_id, "cif")
        self.assertEqual(
            revision.created_entity_ids,
            batch.report.created_entity_ids,
        )
        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(len(batch.cif_envelopes), 1)

    def test_legacy_core_exports_delegate_to_formats_module(self):
        self.assertIsNotNone(
            importlib.util.find_spec("ChemBlender.core.formats.cif")
        )
        module = importlib.import_module("ChemBlender.core.formats.cif")

        self.assertIs(core.parse_cif, module.parse_cif)
        self.assertIs(core.sniff_cif, module.sniff_cif)
        self.assertIs(core.CIF_READER, module.CIF_READER)


if __name__ == "__main__":
    unittest.main()
