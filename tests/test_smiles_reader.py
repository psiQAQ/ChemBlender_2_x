import hashlib
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from ChemBlender.core import QualityStatus, TopologySource


class SMILESReaderTests(unittest.TestCase):
    def test_direct_text_preserves_exact_utf8_line_and_source_semantics(self):
        from ChemBlender.core.formats.smiles import parse_smiles_text

        text = "[13CH3][C@H](F)Cl chloroalcohol\r\n"
        batch = self._stage_text(text)

        record, = batch.molecular_records
        structure, = batch.structures
        topology, = batch.topologies
        source, = batch.sources
        revision, = batch.source_revisions
        parameters = dict(batch.provenance[0].parameters)
        self.assertEqual(record.raw_block, text.encode("utf-8"))
        self.assertEqual(record.title, "chloroalcohol")
        self.assertEqual(source.source_kind, "text")
        self.assertEqual(revision.locator, "inline:smiles")
        self.assertEqual(revision.locator_kind, "inline_text")
        self.assertEqual(revision.content_hash, hashlib.sha256(text.encode("utf-8")).hexdigest())
        self.assertEqual(parameters["canonical_smiles"], "CC(F)Cl")
        self.assertEqual(parameters["isomeric_smiles"], "[13CH3][C@H](F)Cl")
        self.assertEqual(structure.atomic_identity.isotopes.values.tolist(), [13, 0, 0, 0])
        self.assertEqual(structure.atomic_identity.formal_charges.values.tolist(), [0, 0, 0, 0])
        self.assertEqual(topology.source_kind, TopologySource.EXPLICIT_FILE)
        self.assertEqual(topology.quality_status, QualityStatus.COMPLETE)
        self.assertTrue((structure.coordinates.values[:, 2] == 0.0).all())

    def test_smi_and_smiles_files_are_catalogued_and_keep_exact_bytes(self):
        from ChemBlender.core import builtin_reader_registry
        from ChemBlender.core.formats.smiles import SMILES_READER, parse_smiles
        from ChemBlender.core.readers import SniffMatch

        content = b"C[NH3+] ammonium\n"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for suffix in (".smi", ".smiles"):
                with self.subTest(suffix=suffix):
                    source = root / f"ammonium{suffix}"
                    source.write_bytes(content)
                    self.assertIs(SMILES_READER.sniff(source, content).match, SniffMatch.PROBABLE)
                    self.assertIs(builtin_reader_registry().select(source), SMILES_READER)
                    self.assertEqual(parse_smiles(source).molecular_records[0].raw_block, content)

    def test_sniff_rejects_unrelated_suffixes(self):
        from ChemBlender.core.formats.smiles import SMILES_READER
        from ChemBlender.core.readers import SniffMatch

        self.assertIs(
            SMILES_READER.sniff(Path("molecule.txt"), b"CCO\n").match,
            SniffMatch.NONE,
        )

    def test_exact_raw_smiles_bytes_distinguish_entity_identity(self):
        from ChemBlender.core.formats.smiles import parse_smiles_text

        first = parse_smiles_text("CCO ethanol\n")
        second = parse_smiles_text("CCO ethyl-alcohol\n")
        self.assertEqual(
            dict(first.provenance[0].parameters)["canonical_smiles"],
            dict(second.provenance[0].parameters)["canonical_smiles"],
        )
        self.assertNotEqual(first.molecular_records[0].id, second.molecular_records[0].id)
        self.assertNotEqual(first.provenance[0].id, second.provenance[0].id)

    def test_inline_smiles_stages_semantic_source_identity_without_temp_path(self):
        from ChemBlender.core import builtin_reader_registry
        from ChemBlender.core.import_pipeline.preflight import preflight_import
        from ChemBlender.core.import_pipeline.request import ImportRequest, ImportSource
        from ChemBlender.core.import_pipeline.staging import StagedImportSession

        identities = []
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            for directory in (first, second):
                source = ImportSource.smiles_text("CCO ethanol\n")
                session = StagedImportSession.create(temp_parent=Path(directory))
                try:
                    preview = preflight_import(ImportRequest((source,)), builtin_reader_registry(), session)
                    batch = session.result(preview.staged_batch_ids[0])
                    revision, = batch.source_revisions
                    self.assertEqual(revision.locator, "inline:smiles")
                    self.assertEqual(revision.locator_kind, "inline_text")
                    self.assertNotIn(str(session.artifact_root), revision.locator)
                    self.assertEqual(batch.molecular_records[0].source_revision_id, revision.id)
                    identities.append(revision.parse_identity)
                finally:
                    session.discard()
        self.assertEqual(identities[0], identities[1])

    def test_core_preflight_repeated_smiles_has_authoritative_entity_identity(self):
        from ChemBlender.core import QCProject

        first = self._stage_text("CCO ethanol\n")
        second = self._stage_text("CCO ethanol\n")
        self.assertNotEqual(first.source_revisions[0].id, second.source_revisions[0].id)
        self.assertNotEqual(first.molecular_records[0].id, second.molecular_records[0].id)
        self.assertNotEqual(first.structures[0].id, second.structures[0].id)
        self.assertEqual(first.provenance[0].source_hash, first.source_revisions[0].content_hash)
        self.assertEqual(second.provenance[0].source_hash, second.source_revisions[0].content_hash)
        project = QCProject(id=uuid4(), schema_version="1.0")
        project.commit(first)
        project.commit(second)

    def test_invalid_text_is_blocking_and_creates_no_fake_structure(self):
        from ChemBlender.core.formats.smiles import parse_smiles_text

        batch = parse_smiles_text("not-a-smiles\n")

        self.assertEqual(batch.structures, ())
        self.assertEqual(batch.topologies, ())
        self.assertEqual(batch.molecular_records, ())
        self.assertEqual(batch.diagnostics[0].code, "smiles.invalid")
        self.assertEqual(batch.diagnostics[0].quality_status, QualityStatus.INVALID)

    def test_request_cancellation_reaches_rdkit_without_staging_artifacts(self):
        from ChemBlender.core.formats.rdkit_common import RDKitMoleculeCancelled
        from ChemBlender.core.formats.smiles import parse_smiles_request
        from ChemBlender.reader_api.protocol import ParseRequest

        with TemporaryDirectory() as directory:
            source = Path(directory) / "water.smi"
            source.write_bytes(b"O\n")
            with self.assertRaises(RDKitMoleculeCancelled):
                parse_smiles_request(
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

    def test_source_parse_always_returns_explicit_planar_2d_coordinates(self):
        from ChemBlender.core.formats.smiles import parse_smiles_text

        batch = self._stage_text("CCO")

        self.assertEqual(batch.structures[0].coordinates.unit, "angstrom")
        self.assertTrue((batch.structures[0].coordinates.values[:, 2] == 0.0).all())
        provenance = dict(batch.provenance[0].parameters)
        self.assertEqual(provenance["coordinate_mode"], "generated_planar_2d")
        self.assertEqual(batch.diagnostics[0].code, "smiles.planar_2d_generated")
        self.assertTrue(provenance["rdkit_version"])

    def test_file_snapshot_is_read_once_and_request_hash_must_match(self):
        from unittest.mock import patch

        from ChemBlender.core.formats.smiles import parse_smiles, parse_smiles_request
        from ChemBlender.reader_api.protocol import ParseRequest

        raw = b"CCO ethanol\r\n"
        changed = b"O water\r\n"
        with TemporaryDirectory() as directory:
            source = Path(directory) / "molecule.smi"
            source.write_bytes(raw)
            calls = []

            def read_once(path):
                calls.append(path)
                return raw if len(calls) == 1 else changed

            with patch.object(Path, "read_bytes", read_once):
                batch = parse_smiles(source)
            self.assertEqual(calls, [source])
            self.assertEqual(batch.molecular_records[0].raw_block, raw)
            with self.assertRaisesRegex(ValueError, "hash"):
                parse_smiles_request(
                    ParseRequest(
                        source, hashlib.sha256(changed).hexdigest(), "balanced", {},
                        Path(directory), lambda _event: None, lambda: False, uuid4(),
                    )
                )

    def test_invalid_encoding_and_multiple_nonempty_lines_are_rejected(self):
        from ChemBlender.core.formats.smiles import parse_smiles_text

        with TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.smi"
            source.write_bytes(b"C\xff\n")
            from ChemBlender.core.formats.smiles import parse_smiles

            invalid = parse_smiles(source)
        self.assertEqual(invalid.structures, ())
        self.assertEqual(invalid.diagnostics[0].code, "smiles.invalid")
        for raw in (b"C methane\nO water\n",):
            with self.subTest(raw=raw):
                batch = parse_smiles_text(raw.decode("utf-8"))
                self.assertEqual(batch.structures, ())
                self.assertEqual(batch.diagnostics[0].code, "smiles.invalid")

    def test_reader_preserves_charge_maps_stereo_aromaticity_and_rejects_unsupported_chemistry(self):
        from ChemBlender.core.formats.smiles import parse_smiles_text

        batch = parse_smiles_text("[CH3:7]/[CH:8]=[CH:9]/[13CH2:10][NH3+]")
        structure, = batch.structures
        topology, = batch.topologies
        self.assertEqual(structure.molecular_charge, 1)
        self.assertEqual(structure.atomic_identity.isotopes.values.tolist(), [0, 0, 0, 13, 0])
        self.assertEqual(structure.atomic_identity.atom_map_numbers.values.tolist(), [7, 8, 9, 10, 0])
        self.assertIn("E", topology.stereo_labels)
        aromatic = parse_smiles_text("c1ccccc1")
        self.assertTrue(aromatic.topologies[0].aromatic_flags.values.all())
        for text in ("[CH3]", "*", "C~C"):
            with self.subTest(text=text):
                rejected = parse_smiles_text(text)
                self.assertEqual(rejected.structures, ())
                self.assertEqual(rejected.diagnostics[0].quality_status, QualityStatus.INVALID)

    def test_public_imports_do_not_eagerly_load_rdkit(self):
        command = (
            "import sys; import ChemBlender.core; import ChemBlender.reader_api; "
            "assert not any(name == 'rdkit' or name.startswith('rdkit.') for name in sys.modules)"
        )
        subprocess.run((sys.executable, "-c", command), check=True)

    def test_smiles_sniff_is_lexical_and_does_not_load_rdkit(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "molecule.smi"
            source.write_bytes(b"CCO\n")
            command = (
                "import sys; from pathlib import Path; "
                "from ChemBlender.core.formats.smiles import sniff_smiles; "
                f"sniff_smiles(Path(r'{source}'), b'CCO\\n'); "
                "assert not any(name == 'rdkit' or name.startswith('rdkit.') for name in sys.modules)"
            )
            subprocess.run((sys.executable, "-c", command), check=True)

    def test_conformer_grouping_skips_smiles_records_without_an_explicit_file_block(self):
        from ChemBlender.core.import_pipeline.conformer_grouping import suggest_conformer_groups

        batch = self._stage_text("CCO")
        record = batch.molecular_records[0]
        second = replace(record, id=uuid4(), record_key="1", source_record_index=1)
        self.assertEqual(
            suggest_conformer_groups(replace(batch, molecular_records=(record, second))),
            (),
        )

    def _stage_text(self, text):
        from ChemBlender.core import builtin_reader_registry
        from ChemBlender.core.import_pipeline.preflight import preflight_import
        from ChemBlender.core.import_pipeline.request import ImportRequest, ImportSource
        from ChemBlender.core.import_pipeline.staging import StagedImportSession

        source = ImportSource.smiles_text(text)
        with TemporaryDirectory() as directory:
            session = StagedImportSession.create(temp_parent=Path(directory))
            try:
                preview = preflight_import(
                    ImportRequest((source,)), builtin_reader_registry(), session
                )
                return session.result(preview.staged_batch_ids[0])
            finally:
                session.discard()


if __name__ == "__main__":
    unittest.main()
