from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import hashlib

from ChemBlender.core import (
    builtin_reader_registry,
    close_project,
    close_session,
    create_session,
    open_project,
)
from ChemBlender.core.formats.mol import MOL_READER
from ChemBlender.core.import_pipeline import (
    ImportCommitDecisions,
    ImportRequest,
    ImportSource,
    StagedImportSession,
    ValidationMode,
    commit_import_preview,
)
from ChemBlender.core.mol_v2000 import (
    MOL_V2000_READER,
    MOL_V2000_REPLACEMENT,
    sniff_mol_v2000,
)
from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry
from ChemBlender.ui.default_views import plan_default_view


FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "mol"


class MOLReaderTests(unittest.TestCase):
    def test_native_mol_reader_sniffs_real_v2000_fixture(self) -> None:
        from ChemBlender.core.formats.mol import sniff_mol
        from ChemBlender.core.readers import SniffMatch

        source = FIXTURE_ROOT / "water-v2000.mol"
        result = sniff_mol(source, source.read_bytes())

        self.assertIs(result.match, SniffMatch.EXACT)
        self.assertIn("V2000", result.evidence)

    def test_sniff_rejects_counts_line_without_declared_atom_and_bond_blocks(self) -> None:
        from ChemBlender.core.formats.mol import sniff_mol
        from ChemBlender.core.readers import SniffMatch

        content = b"fake\nwriter\n\n  2  1  0  0  0  0  0  0  0  0  0 V2000\nM  END\n"
        with TemporaryDirectory() as directory:
            source = Path(directory) / "fake.mol"
            source.write_bytes(content)
            result = sniff_mol(source, content)

        self.assertIs(result.match, SniffMatch.NONE)

    def test_report_lists_only_scientific_entities_in_graph_order(self) -> None:
        from ChemBlender.core.formats.mol import parse_mol

        batch = parse_mol(FIXTURE_ROOT / "water-v2000.mol")
        self.assertEqual(
            batch.report.created_entity_ids,
            (
                batch.structures[0].id,
                *(item.id for item in batch.topologies),
                batch.molecular_records[0].id,
                batch.provenance[0].id,
            ),
        )
        self.assertNotIn(batch.diagnostics[0].id if batch.diagnostics else None, batch.report.created_entity_ids)

    def test_parse_request_propagates_cancellation_to_the_host(self) -> None:
        from ChemBlender.core.formats.mol import parse_mol_request
        from ChemBlender.core.formats.rdkit_common import RDKitMoleculeCancelled
        from ChemBlender.reader_api.protocol import ParseRequest

        source = FIXTURE_ROOT / "water-v2000.mol"
        with TemporaryDirectory() as directory:
            with self.assertRaises(RDKitMoleculeCancelled):
                parse_mol_request(
                    ParseRequest(
                        source,
                        hashlib.sha256(source.read_bytes()).hexdigest(),
                        "balanced",
                        {},
                        Path(directory),
                        lambda _event: None,
                        lambda: True,
                        uuid4(),
                    )
                )

    def test_v3000_fixture_is_exact_and_keeps_its_raw_block(self) -> None:
        from ChemBlender.core.formats.mol import parse_mol, sniff_mol
        from ChemBlender.core.readers import SniffMatch

        source = FIXTURE_ROOT / "water-v3000.mol"
        batch = parse_mol(source)

        self.assertIs(sniff_mol(source, source.read_bytes()).match, SniffMatch.EXACT)
        self.assertEqual(batch.molecular_records[0].block_version, "V3000")
        self.assertEqual(batch.molecular_records[0].raw_block, source.read_bytes())
        self.assertEqual(len(batch.topologies[0].bond_orders.values), 2)

    def test_sniff_and_parse_reject_prose_sdf_and_multiple_records(self) -> None:
        from ChemBlender.core.formats.mol import parse_mol, sniff_mol
        from ChemBlender.core.readers import SniffMatch

        valid = (FIXTURE_ROOT / "water-v2000.mol").read_bytes()
        cases = {
            "prose.mol": b"ordinary prose\nwithout a MOL record\n",
            "sdf.mol": valid + b"$$$$\n",
            "multiple.mol": valid + b"second record\n",
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in cases.items():
                with self.subTest(name=name):
                    source = root / name
                    source.write_bytes(content)
                    self.assertIs(sniff_mol(source, content).match, SniffMatch.NONE)
                    with self.assertRaises(ValueError):
                        parse_mol(source)

    def test_raw_bom_crlf_and_non_utf8_bytes_are_preserved_with_diagnostic(self) -> None:
        from ChemBlender.core.formats.mol import parse_mol

        content = (FIXTURE_ROOT / "water-v2000.mol").read_bytes()
        content = b"\xef\xbb\xbfwat\xffr\r\n" + content.split(b"\n", 1)[1].replace(b"\n", b"\r\n")
        with TemporaryDirectory() as directory:
            source = Path(directory) / "encoded.mol"
            source.write_bytes(content)
            batch = parse_mol(source)

        self.assertEqual(batch.molecular_records[0].raw_block, content)
        self.assertEqual(
            tuple(item.code for item in batch.diagnostics),
            ("mol.decode_replacement",),
        )

    def test_catalog_uses_primary_reader_and_explicit_v2000_alias(self) -> None:
        from ChemBlender.core.readers import SniffMatch

        source = FIXTURE_ROOT / "water-v2000.mol"
        self.assertIs(builtin_reader_registry().select(source), MOL_READER)
        self.assertLess(MOL_V2000_READER.priority, MOL_READER.priority)
        self.assertIs(sniff_mol_v2000(source, source.read_bytes()).match, SniffMatch.NONE)
        alias_batch = MOL_V2000_READER.parse(source)
        self.assertEqual(MOL_V2000_REPLACEMENT, "mol")
        self.assertEqual(alias_batch.report.reader_id, "mol-v2000")
        self.assertEqual(alias_batch.report.issues[0].path, "reader.replacement")
        with self.assertRaises(ValueError):
            MOL_V2000_READER.parse(FIXTURE_ROOT / "water-v3000.mol")
        descriptor = next(
            item
            for item in builtin_reader_plugin_registry().descriptors
            if item.reader_id == "mol"
        )
        self.assertTrue(descriptor.availability.available)
        self.assertEqual(
            set(descriptor.capabilities),
            {"structure", "topology", "atomic_identity", "molecular_record"},
        )

    def test_preflight_commit_sidecar_round_trip_keeps_host_revision_and_default_view(self) -> None:
        source = FIXTURE_ROOT / "water-v2000.mol"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            staged = StagedImportSession.create(temp_parent=root)
            session = create_session(temp_parent=root)
            try:
                preview = preflight_reader_plugins(
                    ImportRequest((ImportSource(source),), ValidationMode.BALANCED),
                    builtin_reader_plugin_registry(),
                    staged,
                )
                batch = staged.result(preview.source_previews[0].staged_batch_ids[0])
                revision = batch.source_revisions[0]
                self.assertEqual(
                    batch.molecular_records[0].source_revision_id,
                    revision.id,
                )
                result = commit_import_preview(
                    session,
                    staged,
                    preview,
                    ImportCommitDecisions(),
                )
                reopened = open_project(result.sidecar_path)
                try:
                    restored_revision = reopened.source_revisions[revision.id]
                    record = next(iter(reopened.molecular_records.values()))
                    self.assertEqual(record.source_revision_id, restored_revision.id)
                    plan = plan_default_view(
                        restored_revision, reopened.structures, reopened.datasets
                    )
                    self.assertEqual(plan.display_label, "Structure")
                finally:
                    close_project(reopened)
            finally:
                close_session(session)
