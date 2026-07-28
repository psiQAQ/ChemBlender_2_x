from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import platform
import statistics
import sys
import time
import tracemalloc
import unittest
from unittest.mock import patch
from uuid import uuid4


FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "sdf"
MOL_BLOCK = (
    Path(__file__).with_name("fixtures") / "mol" / "water-v2000.mol"
).read_bytes().replace(b"\r\n", b"\n")


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

        batch = parse_sdf(FIXTURE_ROOT / "malformed-middle.sdf")

        self.assertEqual(
            tuple(record.source_record_index for record in batch.molecular_records),
            (0, 2),
        )
        self.assertEqual(
            tuple(item.code for item in batch.diagnostics),
            ("sdf.record_parse_failed",),
        )
        self.assertEqual(batch.report.issues, ())

    def test_raw_properties_preserve_duplicate_empty_and_order(self) -> None:
        from ChemBlender.core.formats.sdf import parse_sdf

        batch = parse_sdf(FIXTURE_ROOT / "duplicate-empty.sdf")

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
            _record(),
        )
        with TemporaryDirectory() as directory:
            source = Path(directory) / "typed.sdf"
            source.write_bytes(content)
            batch = parse_sdf(source)

        columns = {item.semantic_role: item for item in batch.datasets}
        energy = columns["sdf_energy"]
        self.assertIs(energy.status, DatasetStatus.PARTIAL)
        self.assertEqual(energy.data.values.tolist(), [-1.25, 0.0, 0.0])
        self.assertEqual(energy.validity_mask.values.tolist(), [True, False, False])
        flag = columns["sdf_flag"]
        self.assertIs(flag.status, DatasetStatus.PARTIAL)
        self.assertEqual(flag.data.values.tolist(), [True, False, False])
        self.assertEqual(flag.validity_mask.values.tolist(), [True, True, False])

    def test_normal_int64_property_remains_a_numeric_column(self) -> None:
        import numpy

        from ChemBlender.core.formats.sdf import parse_sdf

        with TemporaryDirectory() as directory:
            source = Path(directory) / "integer.sdf"
            source.write_bytes(_sdf(_record(("Identifier", b"9223372036854775807"))))
            batch = parse_sdf(source)

        identifier = next(
            item for item in batch.datasets if item.semantic_role == "sdf_identifier"
        )
        self.assertEqual(identifier.data.dtype, numpy.dtype(numpy.int64))
        self.assertEqual(identifier.data.values.tolist(), [9223372036854775807])

    def test_sdwriter_headers_and_non_numeric_properties_build_categorical_columns(self) -> None:
        from ChemBlender.core import CategoricalData, DatasetStatus
        from ChemBlender.core.formats.sdf import parse_sdf

        content = _sdf(
            MOL_BLOCK + b">  <State>  (1)\nsolid\n\n>  <Count>  (1)\n9223372036854775808\n\n",
            MOL_BLOCK + b">  <State>  (2)\nliquid\n\n>  <Count>  (2)\n2\n\n",
            MOL_BLOCK,
        )
        with TemporaryDirectory() as directory:
            source = Path(directory) / "writer.sdf"
            source.write_bytes(content)
            batch = parse_sdf(source)

        self.assertEqual(
            tuple((item.name, item.value) for item in batch.molecular_records[0].ordered_raw_properties),
            (("State", "solid"), ("Count", "9223372036854775808")),
        )
        columns = {item.semantic_role: item for item in batch.datasets}
        state = columns["sdf_state"]
        self.assertIs(state.status, DatasetStatus.PARTIAL)
        self.assertIsInstance(state.data, CategoricalData)
        self.assertEqual(state.data.categories, ("solid", "liquid"))
        self.assertEqual(state.data.codes.values.tolist(), [0, 1, -1])
        self.assertIsNone(state.validity_mask)
        self.assertIsInstance(columns["sdf_count"].data, CategoricalData)

    def test_very_large_integer_property_becomes_categorical_without_int_conversion(self) -> None:
        from ChemBlender.core import CategoricalData
        from ChemBlender.core.formats.sdf import parse_sdf

        value = b"9" * 5_000
        with TemporaryDirectory() as directory:
            source = Path(directory) / "large-integer.sdf"
            source.write_bytes(_sdf(_record(("Identifier", value))))
            batch = parse_sdf(source)

        identifier = next(
            item for item in batch.datasets if item.semantic_role == "sdf_identifier"
        )
        self.assertIsInstance(identifier.data, CategoricalData)
        self.assertEqual(identifier.data.categories, (value.decode("ascii"),))

    def test_crlf_mol_slice_and_standalone_delimiter_are_exact(self) -> None:
        from ChemBlender.core.formats.sdf import parse_sdf

        source = FIXTURE_ROOT / "crlf.sdf"
        content = source.read_bytes()
        self.assertIn(b"\r\n", content)
        batch = parse_sdf(source)

        record = batch.molecular_records[0]
        self.assertEqual(record.raw_block, content.split(b">", 1)[0])
        self.assertEqual(record.ordered_raw_properties[0].value, " $$$$")

    def test_mixed_v2000_and_v3000_records_remain_independent(self) -> None:
        from ChemBlender.core.formats.sdf import parse_sdf

        batch = parse_sdf(FIXTURE_ROOT / "mixed-version.sdf")

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
        from ChemBlender.core.formats.sdf import (
            iter_sdf_file_records,
            iter_sdf_records,
            parse_sdf_request,
        )
        from ChemBlender.reader_api.protocol import ParseRequest

        content = _sdf(_record(), _record())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "stable.sdf"
            source.write_bytes(content)
            boundaries = tuple(iter_sdf_records(content))
            file_boundaries = tuple(iter_sdf_file_records(source, chunk_bytes=17))
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
        self.assertEqual(file_boundaries, boundaries)
        self.assertEqual(
            tuple(record.source_revision_id for record in batch.molecular_records),
            (source_revision_id, source_revision_id),
        )
        self.assertEqual(len(set(record.record_key for record in batch.molecular_records)), 2)

    def test_final_delimiter_without_newline_has_matching_bytes_and_file_boundaries(self) -> None:
        from ChemBlender.core.formats.sdf import iter_sdf_file_records, iter_sdf_records

        record = _record()
        content = record + b"$$$$"
        expected_hash = hashlib.sha256(record).hexdigest()
        with TemporaryDirectory() as directory:
            source = Path(directory) / "final-delimiter.sdf"
            source.write_bytes(content)
            file_boundaries = tuple(iter_sdf_file_records(source, chunk_bytes=7))
        bytes_boundaries = tuple(iter_sdf_records(content))

        self.assertEqual(bytes_boundaries, file_boundaries)
        self.assertEqual(
            tuple((item.index, item.start, item.end, item.raw_hash) for item in bytes_boundaries),
            ((0, 0, len(record), expected_hash),),
        )

    def test_file_cancellation_and_10k_indexing_are_bounded(self) -> None:
        from ChemBlender.core.formats.sdf import (
            SDFReaderCancelled,
            iter_sdf_file_records,
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
                tuple(iter_sdf_file_records(source, is_cancelled=lambda: True))
            calls = 0

            def cancel_mid_read():
                nonlocal calls
                calls += 1
                return calls > 2

            with self.assertRaises(SDFReaderCancelled):
                tuple(iter_sdf_file_records(source, is_cancelled=cancel_mid_read))
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
            benchmark = root / "10k.sdf"
            benchmark.write_bytes(content)
            samples = []
            tracemalloc.start()
            try:
                for _ in range(3):
                    started = time.perf_counter()
                    boundaries = tuple(iter_sdf_file_records(benchmark, chunk_bytes=4096))
                    samples.append(time.perf_counter() - started)
                _current, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()

        source_hash = hashlib.sha256(content).hexdigest()
        median = statistics.median(samples)
        p95 = statistics.quantiles(samples, n=100)[94]
        from rdkit import rdBase

        print(json.dumps({
            "benchmark": "sdf_10k_file_index",
            "cache_state": {"first_run": "cold_after_write", "later_runs": "warm_os_file_cache"},
            "environment": {
                "blender": Path(sys.executable).parents[2].name,
                "blender_python": sys.executable,
                "platform": platform.platform(),
                "python": platform.python_version(),
                "rdkit": rdBase.rdkitVersion,
            },
            "input": {"record_count": 10_000, "sha256": source_hash, "size_bytes": len(content)},
            "memory": {"peak_bytes": peak},
            "timing_seconds": {"cold": samples[0], "median": median, "p95": p95, "warm": samples[1:]},
        }, sort_keys=True))
        self.assertEqual(source_hash, "bec92cea8a452b1c2a0ad076b346de0f91a97ba94c7d1815b79c90fdd1b10279")
        self.assertEqual(len(boundaries), 10_000)
        self.assertLess(median, 2.0)
        self.assertLess(p95, 2.0)
        self.assertLess(peak, 128 * 1024 * 1024)

    def test_file_scanner_does_not_buffer_an_unterminated_megabyte_line(self) -> None:
        from ChemBlender.core.formats.sdf import iter_sdf_file_records

        with TemporaryDirectory() as directory:
            source = Path(directory) / "long-line.sdf"
            source.write_bytes(b"x" * (1024 * 1024))
            tracemalloc.start()
            try:
                boundaries = tuple(iter_sdf_file_records(source, chunk_bytes=4096))
                _current, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()

        self.assertEqual(len(boundaries), 1)
        self.assertLess(peak, 256 * 1024)

    def test_memory_error_and_host_failures_do_not_become_recovery_diagnostics(self) -> None:
        from ChemBlender.core.formats import sdf

        raw = _sdf(_record())
        with patch.object(sdf, "_parse_record", side_effect=MemoryError("full")):
            with self.assertRaisesRegex(MemoryError, "full"):
                sdf._parse_bytes(
                    raw,
                    source_revision_id=uuid4(),
                    source_hash=hashlib.sha256(raw).hexdigest(),
                    validation_mode="balanced",
                    is_cancelled=None,
                )
        with patch.object(sdf, "_parse_record", side_effect=RuntimeError("host")):
            with self.assertRaisesRegex(RuntimeError, "host"):
                sdf._parse_bytes(
                    raw,
                    source_revision_id=uuid4(),
                    source_hash=hashlib.sha256(raw).hexdigest(),
                    validation_mode="balanced",
                    is_cancelled=None,
                )

    def test_single_missing_final_and_delimiter_beyond_prefix_select_sdf(self) -> None:
        from ChemBlender.core.formats.sdf import SDF_READER
        from ChemBlender.core.readers import SniffMatch

        with TemporaryDirectory() as directory:
            root = Path(directory)
            missing_final = FIXTURE_ROOT / "missing-final.sdf"
            beyond_prefix = root / "long.sdf"
            beyond_prefix.write_bytes(_record(("Long", b"x" * 70_000)))
            self.assertIs(
                SDF_READER.sniff(missing_final, missing_final.read_bytes()).match,
                SniffMatch.EXACT,
            )
            self.assertIs(
                SDF_READER.sniff(beyond_prefix, beyond_prefix.read_bytes()[:65536]).match,
                SniffMatch.PROBABLE,
            )

    def test_truncated_sdf_suffix_prose_without_a_complete_mol_block_is_not_selected(self) -> None:
        from ChemBlender.core.formats.sdf import SDF_READER
        from ChemBlender.core.readers import SniffMatch

        with TemporaryDirectory() as directory:
            source = Path(directory) / "prose.sdf"
            source.write_bytes(b"ordinary prose\n" * 10_000)
            result = SDF_READER.sniff(source, source.read_bytes()[:64 * 1024])

        self.assertIs(result.match, SniffMatch.NONE)

    def test_large_incomplete_v3000_mol_prefix_is_probable_sdf(self) -> None:
        from ChemBlender.core.formats.sdf import SDF_READER
        from ChemBlender.core.readers import SniffMatch

        atoms = b"".join(
            f"M  V30 {index} C 1234567890.1234567890 0.0000000000 0.0000000000 0\n".encode("ascii")
            for index in range(1, 1201)
        )
        content = (
            b"large V3000\nChemBlender\n\n"
            b"  0  0  0     0  0            999 V3000\n"
            b"M  V30 BEGIN CTAB\nM  V30 COUNTS   1200  0   0 0  0\nM  V30 BEGIN ATOM\n"
            + atoms
            + b"M  V30 END ATOM\nM  V30 END CTAB\nM  END\n$$$$\n"
        )
        self.assertGreater(len(content), 64 * 1024)
        with TemporaryDirectory() as directory:
            source = Path(directory) / "large-v3000.sdf"
            source.write_bytes(content)
            result = SDF_READER.sniff(source, content[:64 * 1024])

        self.assertIs(result.match, SniffMatch.PROBABLE)

    def test_v3000_counts_extra_spaces_parse_with_rdkit(self) -> None:
        from ChemBlender.core.formats.sdf import parse_sdf

        mol = (Path(__file__).with_name("fixtures") / "mol" / "water-v3000.mol").read_bytes()
        content = mol.replace(
            b"M  V30 COUNTS 3 2 0 0 0",
            b"M  V30 COUNTS   3  2   0 0  0",
        ) + b"$$$$\n"
        with TemporaryDirectory() as directory:
            source = Path(directory) / "spaces-v3000.sdf"
            source.write_bytes(content)
            batch = parse_sdf(source)

        self.assertEqual(len(batch.molecular_records), 1)

    def test_tabbed_v3000_counts_prefix_is_not_probable(self) -> None:
        from ChemBlender.core.formats.sdf import SDF_READER
        from ChemBlender.core.readers import SniffMatch

        content = (
            b"tabbed V3000\nChemBlender\n\n"
            b"  0  0  0     0  0            999 V3000\n"
            b"M  V30 BEGIN CTAB\nM  V30 COUNTS\t3 2 0 0 0\n"
            b"M  V30 BEGIN ATOM\nM  V30 1 C 0.0 0.0 0.0 0\n"
            + b"x" * (64 * 1024)
        )
        with TemporaryDirectory() as directory:
            source = Path(directory) / "tabbed-v3000.sdf"
            source.write_bytes(content)
            result = SDF_READER.sniff(source, content[:64 * 1024])

        self.assertIs(result.match, SniffMatch.NONE)

    def test_record_keys_depend_on_source_identity_and_full_record_hash(self) -> None:
        from ChemBlender.core.formats.sdf import parse_sdf

        first = _record(("Label", b"same"))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_one = root / "one.sdf"
            source_two = root / "two.sdf"
            source_one.write_bytes(_sdf(first, _record(("Tail", b"one"))))
            source_two.write_bytes(_sdf(first, _record(("Tail", b"two"))))
            first_batch = parse_sdf(source_one)
            second_batch = parse_sdf(source_two)

        self.assertNotEqual(
            first_batch.molecular_records[0].record_key,
            second_batch.molecular_records[0].record_key,
        )

    def test_direct_parse_uses_a_single_atomic_snapshot_when_source_is_replaced(self) -> None:
        from ChemBlender.core.formats import sdf

        original = _sdf(
            _record(("Source", b"original-one")),
            _record(("Source", b"original-two")),
        )
        replacement = _sdf(_record(("Source", b"replacement")))
        with TemporaryDirectory() as directory:
            source = Path(directory) / "swap.sdf"
            source.write_bytes(original)
            create_snapshot = sdf._snapshot_source

            def replace_after_snapshot(path, **kwargs):
                snapshot = create_snapshot(path, **kwargs)
                source.write_bytes(replacement)
                return snapshot

            with patch.object(sdf, "_snapshot_source", replace_after_snapshot):
                batch = sdf.parse_sdf(source)

        self.assertEqual(
            tuple(item.ordered_raw_properties[0].value for item in batch.molecular_records),
            ("original-one", "original-two"),
        )
        self.assertEqual(
            batch.provenance[0].source_hash, hashlib.sha256(original).hexdigest()
        )

    def test_direct_parse_opens_the_product_source_once(self) -> None:
        from ChemBlender.core.formats import sdf

        content = _sdf(_record(), _record())
        with TemporaryDirectory() as directory:
            source = Path(directory) / "single-open.sdf"
            source.write_bytes(content)
            original_open = Path.open
            source_opens = 0

            def count_source_open(path, *args, **kwargs):
                nonlocal source_opens
                if path == source:
                    source_opens += 1
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", count_source_open):
                batch = sdf.parse_sdf(source)

        self.assertEqual(len(batch.molecular_records), 2)
        self.assertEqual(source_opens, 1)

    def test_host_request_rejects_a_snapshot_hash_mismatch(self) -> None:
        from ChemBlender.core.formats.sdf import parse_sdf_request
        from ChemBlender.reader_api.protocol import ParseRequest

        content = _sdf(_record())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "hash.sdf"
            source.write_bytes(content)
            request = ParseRequest(
                source, "0" * 64, "balanced", {}, root, lambda _event: None, lambda: False
            )
            with self.assertRaisesRegex(ValueError, "source content hash mismatch"):
                parse_sdf_request(request)

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

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "partial.sdf"
            content = _sdf(
                _record(("Energy", b"-1.25"), ("Flag", b"true")),
                _record(("Flag", b"false")),
            )
            source.write_bytes(content)
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
                    self.assertEqual(numpy.asarray(energy.data.values).tolist(), [-1.25, 0.0])
                    self.assertEqual(
                        numpy.asarray(energy.validity_mask.values).tolist(), [True, False]
                    )
                    self.assertEqual(energy.record_ids, tuple(item.id for item in records))
                    self.assertEqual(
                        reopened.provenance[records[0].provenance_ids[0]].source_hash,
                        hashlib.sha256(content).hexdigest(),
                    )
                finally:
                    close_project(reopened)
            finally:
                close_session(session)
                staged.discard()
                self.assertFalse(staged.root.exists())


if __name__ == "__main__":
    unittest.main()
