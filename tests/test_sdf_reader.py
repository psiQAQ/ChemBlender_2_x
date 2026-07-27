from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import statistics
import time
import tracemalloc
import unittest
from uuid import uuid4


FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "sdf"
MOL_BLOCK = (Path(__file__).with_name("fixtures") / "mol" / "water-v2000.mol").read_bytes()


def _record(*properties):
    fields = b"".join(
        b"> <" + name.encode("utf-8") + b">\n" + value + b"\n\n"
        for name, value in properties
    )
    return MOL_BLOCK + fields


def _sdf(*records, final_delimiter=True):
    body = b"$$$$\n".join(records)
    return body + (b"$$$$\n" if final_delimiter else b"")


class SDFReaderTests(unittest.TestCase):
    def test_real_multi_record_fixture_is_selected_and_parsed(self) -> None:
        from ChemBlender.core import builtin_reader_registry
        from ChemBlender.core.formats.sdf import SDF_READER
        from ChemBlender.core.readers import SniffMatch

        source = FIXTURE_ROOT / "records.sdf"
        self.assertIs(SDF_READER.sniff(source, source.read_bytes()).match, SniffMatch.EXACT)
        self.assertIs(builtin_reader_registry().select(source), SDF_READER)
        batch = SDF_READER.parse(source)
        self.assertEqual(tuple(record.source_record_index for record in batch.molecular_records), (0, 1))
        self.assertEqual(len(batch.topologies), 2)

    def test_balanced_recovery_keeps_indices_around_a_malformed_record(self) -> None:
        from ChemBlender.core.formats.sdf import parse_sdf

        content = _sdf(_record(), b"not a MOL record\n", _record())
        with TemporaryDirectory() as directory:
            source = Path(directory) / "broken.sdf"
            source.write_bytes(content)
            batch = parse_sdf(source)

        self.assertEqual(
            tuple(record.source_record_index for record in batch.molecular_records),
            (0, 2),
        )
        self.assertEqual(
            tuple(item.code for item in batch.diagnostics),
            ("sdf.record_parse_failed",),
        )

    def test_raw_properties_preserve_duplicate_empty_and_order(self) -> None:
        from ChemBlender.core.formats.sdf import parse_sdf

        content = _sdf(_record(("Tag", b"one"), ("Tag", b"two"), ("Empty", b"")))
        with TemporaryDirectory() as directory:
            source = Path(directory) / "raw.sdf"
            source.write_bytes(content)
            batch = parse_sdf(source)

        self.assertEqual(
            tuple((item.name, item.value) for item in batch.molecular_records[0].ordered_raw_properties),
            (("Tag", "one"), ("Tag", "two"), ("Empty", "")),
        )
        self.assertEqual(batch.datasets, ())

    def test_unambiguous_typed_columns_keep_missing_values_with_masks(self) -> None:
        from ChemBlender.core import DatasetStatus
        from ChemBlender.core.formats.sdf import parse_sdf

        content = _sdf(
            _record(("Energy", b"-1.25"), ("Flag", b"true")),
            _record(("Flag", b"false")),
        )
        with TemporaryDirectory() as directory:
            source = Path(directory) / "typed.sdf"
            source.write_bytes(content)
            batch = parse_sdf(source)

        columns = {item.semantic_role: item for item in batch.datasets}
        energy = columns["sdf_energy"]
        self.assertIs(energy.status, DatasetStatus.PARTIAL)
        self.assertEqual(energy.data.values.tolist(), [-1.25, 0.0])
        self.assertEqual(energy.validity_mask.values.tolist(), [True, False])
        self.assertEqual(columns["sdf_flag"].data.values.tolist(), [True, False])

    def test_crlf_mol_slice_and_standalone_delimiter_are_exact(self) -> None:
        from ChemBlender.core.formats.sdf import parse_sdf

        mol = MOL_BLOCK.replace(b"\n", b"\r\n")
        content = mol + b"> <Text>\r\n $$$$\r\n\r\n$$$$\r\n"
        with TemporaryDirectory() as directory:
            source = Path(directory) / "crlf.sdf"
            source.write_bytes(content)
            batch = parse_sdf(source)

        record = batch.molecular_records[0]
        self.assertEqual(record.raw_block, mol)
        self.assertEqual(record.ordered_raw_properties[0].value, " $$$$")

    def test_mixed_v2000_and_v3000_records_remain_independent(self) -> None:
        from ChemBlender.core.formats.sdf import parse_sdf

        v3000 = (
            Path(__file__).with_name("fixtures") / "mol" / "water-v3000.mol"
        ).read_bytes()
        content = _sdf(MOL_BLOCK, v3000)
        with TemporaryDirectory() as directory:
            source = Path(directory) / "mixed-version.sdf"
            source.write_bytes(content)
            batch = parse_sdf(source)

        self.assertEqual(
            tuple(record.block_version for record in batch.molecular_records),
            ("V2000", "V3000"),
        )

    def test_missing_final_delimiter_keeps_last_record_and_mol_does_not_select_sdf(self) -> None:
        from ChemBlender.core.formats.sdf import SDF_READER, parse_sdf
        from ChemBlender.core.formats.mol import MOL_READER
        from ChemBlender.core.readers import SniffMatch

        content = _sdf(_record(), _record(), final_delimiter=False)
        with TemporaryDirectory() as directory:
            source = Path(directory) / "unterminated.sdf"
            source.write_bytes(content)
            batch = parse_sdf(source)
            mol_sniff = MOL_READER.sniff(source, content)
            sdf_sniff = SDF_READER.sniff(source, content)

        self.assertEqual(tuple(record.source_record_index for record in batch.molecular_records), (0, 1))
        self.assertIs(mol_sniff.match, SniffMatch.NONE)
        self.assertIs(sdf_sniff.match, SniffMatch.EXACT)

    def test_leading_and_consecutive_delimiters_keep_invalid_record_indices(self) -> None:
        from ChemBlender.core.formats.sdf import SDF_READER, parse_sdf
        from ChemBlender.core.readers import SniffMatch

        content = b"$$$$\n$$$$\n" + _sdf(_record())
        with TemporaryDirectory() as directory:
            source = Path(directory) / "empty-records.sdf"
            source.write_bytes(content)
            batch = parse_sdf(source)
            sniff = SDF_READER.sniff(source, content)

        self.assertIs(sniff.match, SniffMatch.EXACT)
        self.assertEqual(
            tuple(record.source_record_index for record in batch.molecular_records),
            (2,),
        )
        self.assertEqual(
            tuple(tuple(item.record_key.split("-")[:2]) for item in batch.diagnostics),
            (("record", "000000"), ("record", "000001")),
        )
        self.assertEqual(len(batch.diagnostics), 2)

    def test_boundaries_keys_and_host_revision_are_stable(self) -> None:
        from ChemBlender.core.formats.sdf import iter_sdf_records, parse_sdf_request
        from ChemBlender.reader_api.protocol import ParseRequest

        content = _sdf(_record(), _record())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "stable.sdf"
            source.write_bytes(content)
            boundaries = tuple(iter_sdf_records(content))
            source_revision_id = uuid4()
            batch = parse_sdf_request(
                ParseRequest(
                    source,
                    hashlib.sha256(content).hexdigest(),
                    "balanced",
                    {},
                    root,
                    lambda _event: None,
                    lambda: False,
                    source_revision_id,
                )
            )

        self.assertEqual(
            tuple((item.index, item.start, item.end) for item in boundaries),
            ((0, 0, len(_record())), (1, len(_record()) + 5, len(content) - 5)),
        )
        self.assertEqual(
            tuple(record.source_revision_id for record in batch.molecular_records),
            (source_revision_id, source_revision_id),
        )
        self.assertEqual(len(set(record.record_key for record in batch.molecular_records)), 2)

    def test_cancellation_and_10k_byte_indexing_are_bounded(self) -> None:
        from ChemBlender.core.formats.sdf import (
            SDFReaderCancelled,
            iter_sdf_records,
            parse_sdf_request,
        )
        from ChemBlender.reader_api.protocol import ParseRequest

        with self.assertRaises(SDFReaderCancelled):
            tuple(iter_sdf_records(_sdf(_record()), is_cancelled=lambda: True))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "cancel.sdf"
            source.write_bytes(_sdf(_record()))
            with self.assertRaises(SDFReaderCancelled):
                parse_sdf_request(
                    ParseRequest(
                        source,
                        hashlib.sha256(source.read_bytes()).hexdigest(),
                        "balanced",
                        {},
                        root,
                        lambda _event: None,
                        lambda: True,
                    )
                )
        content = _sdf(*(_record() for _ in range(10_000)))
        samples = []
        tracemalloc.start()
        try:
            for _ in range(3):
                started = time.perf_counter()
                boundaries = tuple(iter_sdf_records(content))
                samples.append(time.perf_counter() - started)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        self.assertEqual(len(boundaries), 10_000)
        self.assertLess(statistics.median(samples), 2.0)
        self.assertLess(statistics.quantiles(samples, n=100)[94], 2.0)
        self.assertLess(peak, 128 * 1024 * 1024)

    def test_preflight_sidecar_round_trip_keeps_records_raw_properties_and_masks(self) -> None:
        import numpy

        from ChemBlender.core import close_project, close_session, create_session, open_project
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

        source = FIXTURE_ROOT / "records.sdf"
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
                self.assertEqual(len(batch.molecular_records), 2)
                expected_raw = batch.molecular_records[0].raw_block
                result = commit_import_preview(
                    session, staged, preview, ImportCommitDecisions()
                )
                reopened = open_project(result.sidecar_path)
                try:
                    records = tuple(
                        sorted(
                            reopened.molecular_records.values(),
                            key=lambda item: item.source_record_index,
                        )
                    )
                    self.assertEqual(records[0].raw_block, expected_raw)
                    self.assertEqual(
                        tuple((item.name, item.value) for item in records[0].ordered_raw_properties),
                        (("Energy", "-1.25"), ("Flag", "true")),
                    )
                    energy = next(
                        item
                        for item in reopened.datasets.values()
                        if item.semantic_role == "sdf_energy"
                    )
                    self.assertEqual(numpy.asarray(energy.data.values).tolist(), [-1.25, -2.0])
                    self.assertIsNone(energy.validity_mask)
                finally:
                    close_project(reopened)
            finally:
                close_session(session)
                staged.discard()
                self.assertFalse(staged.root.exists())


if __name__ == "__main__":
    unittest.main()
