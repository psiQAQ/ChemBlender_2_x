import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy

from ChemBlender.core import IssueKind, QCProject, parse_cif
from ChemBlender.core.sidecar import close_project, open_project, save_project
from ChemBlender.reader_api import (
    public_batch_document,
    public_batch_from_document,
    public_batch_from_internal,
)


FIXTURES = Path(__file__).parent / "fixtures" / "cif"
MULTI_BLOCK = FIXTURES / "multi-block.cif"
QUOTED_LOOP = FIXTURES / "quoted-loop.cif"


class CIFBlockTests(unittest.TestCase):
    def test_multiple_valid_blocks_share_one_envelope_and_have_stable_identity(self):
        first = parse_cif(MULTI_BLOCK)
        second = parse_cif(MULTI_BLOCK)

        self.assertEqual(len(first.cif_envelopes), 1)
        self.assertEqual(len(first.structures), 2)
        envelope = first.cif_envelopes[0]
        self.assertEqual(envelope.source_bytes, MULTI_BLOCK.read_bytes())
        self.assertEqual(
            envelope.revision,
            hashlib.sha256(MULTI_BLOCK.read_bytes()).hexdigest(),
        )
        self.assertEqual(envelope.block_names, ("first", "second"))
        self.assertEqual(envelope.block_keys, ("first", "second"))
        self.assertEqual(
            tuple(structure.periodic.cif_block_index for structure in first.structures),
            (0, 1),
        )
        self.assertEqual(
            tuple(structure.periodic.cif_block_key for structure in first.structures),
            envelope.block_keys,
        )
        self.assertEqual(
            tuple(structure.periodic.cif_block_name for structure in first.structures),
            envelope.block_names,
        )
        self.assertEqual(
            tuple(structure.id for structure in first.structures),
            tuple(structure.id for structure in second.structures),
        )
        self.assertEqual(first.cif_envelopes[0].id, second.cif_envelopes[0].id)

    def test_duplicate_block_names_receive_stable_local_keys_and_diagnostic(self):
        content = MULTI_BLOCK.read_text(encoding="utf-8")
        content = content.replace("data_second", "data_first")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "duplicate.cif"
            source.write_text(content, encoding="utf-8")
            batch = parse_cif(source)

        self.assertEqual(batch.cif_envelopes[0].block_names, ("first", "first"))
        self.assertEqual(batch.cif_envelopes[0].block_keys, ("first", "first#2"))
        self.assertEqual(
            tuple(item.periodic.cif_block_key for item in batch.structures),
            ("first", "first#2"),
        )
        self.assertIn(
            ("cif.blocks[1].name", IssueKind.AMBIGUOUS),
            {(issue.path, issue.kind) for issue in batch.report.issues},
        )

    def test_duplicate_block_fallback_does_not_relax_tag_validation(self):
        content = (
            MULTI_BLOCK.read_text(encoding="utf-8")
            .replace("data_second", "data_first")
            .replace("_cell_length_a 4.12", "_cell_length_a 4.12\n_cell_length_a 4.12")
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "duplicate-tag.cif"
            source.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate CIF tag"):
                parse_cif(source)

    def test_invalid_blocks_preserve_source_envelope_and_report_blocking_issue(self):
        content = b"data_metadata\n_audit_creation_method 'fixture'\n"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "metadata.cif"
            source.write_bytes(content)
            batch = parse_cif(source)

        self.assertEqual(batch.structures, ())
        self.assertEqual(len(batch.cif_envelopes), 1)
        self.assertEqual(batch.cif_envelopes[0].source_bytes, content)
        self.assertIn(
            ("cif.blocks", IssueKind.INVALID),
            {(issue.path, issue.kind) for issue in batch.report.issues},
        )

    def test_gemmi_handles_quoted_values_multiline_text_and_uncertainty(self):
        batch = parse_cif(QUOTED_LOOP)
        structure = batch.structures[0]
        self.assertEqual(structure.periodic.site_labels, ("Na site", "Cl site"))
        self.assertTrue(
            numpy.allclose(structure.cell.values, numpy.eye(3) * 5.6402)
        )
        self.assertIn("_publ_section_title", batch.cif_envelopes[0].tag_names)

    def test_block_identity_survives_sidecar_round_trip(self):
        batch = parse_cif(MULTI_BLOCK)
        project = QCProject(id=uuid4(), schema_version="0.2")
        project.commit(batch)
        with tempfile.TemporaryDirectory() as directory:
            path = save_project(Path(directory) / "blocks.cbq", project)
            reopened = open_project(path)
            try:
                envelope = next(iter(reopened.cif_envelopes.values()))
                self.assertEqual(envelope.block_names, ("first", "second"))
                self.assertEqual(envelope.block_keys, ("first", "second"))
                self.assertEqual(
                    {
                        structure.periodic.cif_block_key
                        for structure in reopened.structures.values()
                    },
                    {"first", "second"},
                )
            finally:
                close_project(reopened)

    def test_project_rejects_mismatched_block_identity(self):
        batch = parse_cif(MULTI_BLOCK)
        structure = batch.structures[0]
        forged = replace(
            structure,
            periodic=replace(structure.periodic, cif_block_key="missing"),
        )
        project = QCProject(id=uuid4(), schema_version="0.2")
        with self.assertRaisesRegex(ValueError, "invalid CIF block reference"):
            project.commit(replace(batch, structures=(forged,)))

    def test_canonical_decoder_accepts_pre_block_identity_documents(self):
        batch = public_batch_from_internal(parse_cif(QUOTED_LOOP))
        with tempfile.TemporaryDirectory() as directory:
            raw = public_batch_document(batch, directory)
            document = json.loads(raw)

            def strip_added_fields(value):
                if isinstance(value, dict):
                    if value.get("$type") == "CIFEnvelope":
                        value.pop("block_names")
                        value.pop("block_keys")
                    elif value.get("$type") == "PeriodicSiteData":
                        value.pop("cif_block_name")
                        value.pop("cif_block_key")
                        value.pop("cif_block_index")
                        value.pop("disorder_assemblies")
                        value.pop("declared_hall_symbol")
                    for item in value.values():
                        strip_added_fields(item)
                elif isinstance(value, list):
                    for item in value:
                        strip_added_fields(item)

            strip_added_fields(document)
            restored = public_batch_from_document(
                json.dumps(
                    document,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
                directory,
            )
        self.assertEqual(restored.cif_envelopes[0].block_names, ("quoted",))
        self.assertIsNone(restored.structures[0].periodic.cif_block_key)
        self.assertIsNone(
            restored.structures[0].periodic.declared_hall_symbol
        )
        self.assertEqual(
            restored.structures[0].periodic.disorder_assemblies,
            ("none", "none"),
        )


if __name__ == "__main__":
    unittest.main()
