import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy

from ChemBlender.core.cjson_adapter import export_cjson, parse_cjson
from ChemBlender.core.import_pipeline.parse import stage_import_batch
from ChemBlender.core.import_pipeline.request import ImportSource, ValidationMode
from ChemBlender.core.model import AtomicProperty, FrameSet, QCProject
from ChemBlender.core.readers import READER_API_VERSION
from ChemBlender.core.sidecar import close_project, open_project, save_project
from ChemBlender.views.structure import _structure_view_data


FIXTURE = Path(__file__).parent / "fixtures" / "cjson" / "water-results.cjson"


class CJSONProductFlowTests(unittest.TestCase):
    def test_import_view_save_reopen_export_and_reparse_preserve_lightweight_semantics(
        self,
    ):
        source_bytes = FIXTURE.read_bytes()
        parsed = parse_cjson(FIXTURE)
        staged = stage_import_batch(
            source=ImportSource(FIXTURE),
            validation_mode=ValidationMode.BALANCED,
            content_hash=hashlib.sha256(source_bytes).hexdigest(),
            byte_size=len(source_bytes),
            plugin_id="chemblender.builtin",
            reader_id="cjson",
            reader_version="0.1.0",
            api_version=READER_API_VERSION,
            parsed_batch=parsed,
        )
        revision = staged.source_revisions[0]
        self.assertEqual(revision.reader_api_version, READER_API_VERSION)
        self.assertIn(staged.structures[0].id, revision.created_entity_ids)
        self.assertIn(staged.annotations[0].id, revision.created_entity_ids)

        project = QCProject(staged.structures[0].id, "1.0")
        project.commit(staged)
        topology = staged.topologies[0]
        self.assertEqual(
            _structure_view_data(staged.structures[0], topology)["primary_edges"],
            ((0, 1), (0, 2)),
        )

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            root = save_project(directory / "water.cbq", project)
            restored = open_project(root)
            try:
                envelope = next(iter(restored.cjson_envelopes.values()))
                destination = directory / "exported.cjson"
                try:
                    report = export_cjson(
                        envelope,
                        destination,
                        max_inline_bytes=1024,
                    )
                except TypeError as error:
                    self.fail(f"CJSON destination export is missing: {error}")
                self.assertTrue(report.written)
                self.assertFalse(report.requires_confirmation)
                exported_document = json.loads(
                    destination.read_text(encoding="utf-8")
                )
            finally:
                close_project(restored)

            exported = parse_cjson(destination)

        left_structure = staged.structures[0]
        right_structure = exported.structures[0]
        self.assertEqual(left_structure.atomic_numbers, right_structure.atomic_numbers)
        numpy.testing.assert_allclose(
            left_structure.coordinates.values,
            right_structure.coordinates.values,
        )
        numpy.testing.assert_array_equal(
            staged.topologies[0].bond_indices.values,
            exported.topologies[0].bond_indices.values,
        )
        numpy.testing.assert_array_equal(
            staged.topologies[0].bond_orders.values,
            exported.topologies[0].bond_orders.values,
        )
        self.assertEqual(
            {
                item.semantic_role
                for item in staged.datasets
                if isinstance(item, AtomicProperty)
            },
            {
                item.semantic_role
                for item in exported.datasets
                if isinstance(item, AtomicProperty)
            },
        )
        left_frames = next(
            item for item in staged.datasets if isinstance(item, FrameSet)
        )
        right_frames = next(
            item for item in exported.datasets if isinstance(item, FrameSet)
        )
        numpy.testing.assert_allclose(left_frames.data.values, right_frames.data.values)
        self.assertEqual(exported_document["chemicalJson"], 1)


if __name__ == "__main__":
    unittest.main()
