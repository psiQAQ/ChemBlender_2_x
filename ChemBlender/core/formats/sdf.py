"""Byte-oriented recoverable multi-record SDF reader."""

import hashlib
import json
import math
import re
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ..model import (
    ArrayData,
    CategoricalData,
    DatasetStatus,
    DiagnosticSeverity,
    ImportBatch,
    ImportDiagnostic,
    ParserReport,
    QualityStatus,
    RawRecordProperty,
    RecordPropertyColumn,
)
from ..readers import CapabilitySupport, ReaderDescriptor, SniffMatch, SniffResult
from .mol import _decode_diagnostic, _decode_mol, _mol_version


_CAPABILITIES = {
    "atomic_identity": CapabilitySupport.SUPPORTED,
    "molecular_record": CapabilitySupport.SUPPORTED,
    "record_property": CapabilitySupport.PARTIAL,
    "structure": CapabilitySupport.SUPPORTED,
    "topology": CapabilitySupport.SUPPORTED,
}
_PROPERTY_HEADER = re.compile(br">\s*<([^>]*)>.*")
_INTEGER = re.compile(r"[+-]?\d+\Z", re.ASCII)
_V2000_COUNTS = re.compile(br"\s*\d+\s+\d+.*V2000\Z")
_V2000_ATOM = re.compile(br"\s*[+-]?(?:\d+\.\d*|\.\d+)\s+")
_V3000_COUNTS = re.compile(
    br"M +V30 +COUNTS +\d+ +\d+ +\d+ +\d+ +\d+\Z"
)
_V3000_ATOM = re.compile(br"M  V30 \d+ [A-Z][a-z]?(?:\s|\Z)")


class SDFReaderCancelled(Exception):
    """Signal reader cancellation before an incomplete record is emitted."""


class SDFRecordParseError(ValueError):
    """An expected, record-local SDF data error that balanced mode may retain."""


@dataclass(frozen=True, slots=True)
class SDFRecordBoundary:
    index: int
    start: int
    end: int
    raw_hash: str = ""


def _check_cancel(is_cancelled):
    if is_cancelled is None:
        return
    value = is_cancelled()
    if type(value) is not bool:
        raise TypeError("is_cancelled must return a bool")
    if value:
        raise SDFReaderCancelled()


def iter_sdf_records(raw_source, *, is_cancelled=None):
    """Yield half-open byte ranges split only by standalone SDF delimiters."""
    if type(raw_source) is not bytes:
        raise TypeError("raw_source must be bytes")
    start = 0
    line_start = 0
    index = 0
    size = len(raw_source)
    while line_start < size:
        _check_cancel(is_cancelled)
        line_end = raw_source.find(b"\n", line_start)
        if line_end < 0:
            line_end = size
            next_line = size
        else:
            next_line = line_end + 1
        if raw_source[line_start:line_end].rstrip(b"\r") == b"$$$$":
            raw_record = raw_source[start:line_start]
            yield SDFRecordBoundary(
                index, start, line_start, hashlib.sha256(raw_record).hexdigest()
            )
            index += 1
            start = next_line
        line_start = next_line
    _check_cancel(is_cancelled)
    if raw_source[start:].strip(b" \t\r\n"):
        raw_record = raw_source[start:size]
        yield SDFRecordBoundary(
            index, start, size, hashlib.sha256(raw_record).hexdigest()
        )


def _scan_sdf_stream(stream, *, is_cancelled, chunk_bytes, snapshot=None, digest=None):
    """Scan binary chunks without retaining an unbounded physical line."""
    if isinstance(chunk_bytes, bool) or not isinstance(chunk_bytes, int) or chunk_bytes <= 0:
        raise ValueError("chunk_bytes must be a positive integer")
    record_start = 0
    index = 0
    tail_has_content = False
    boundaries = []
    line_start = 0
    offset = 0
    line_probe = bytearray()
    line_too_long = False
    line_has_content = False

    def finish_line(next_start):
        nonlocal index, line_start, record_start, tail_has_content
        nonlocal line_probe, line_too_long, line_has_content
        if not line_too_long and line_probe.rstrip(b"\r") == b"$$$$":
            boundaries.append(SDFRecordBoundary(index, record_start, line_start))
            index += 1
            record_start = next_start
            tail_has_content = False
        elif line_has_content:
            tail_has_content = True
        line_start = next_start
        line_probe = bytearray()
        line_too_long = False
        line_has_content = False

    def add_line_segment(segment):
        nonlocal line_too_long, line_has_content
        if len(line_probe) < 5:
            remaining = 5 - len(line_probe)
            line_probe.extend(segment[:remaining])
            if len(segment) > remaining:
                line_too_long = True
        elif segment:
            line_too_long = True
        if segment.strip(b" \t\r"):
            line_has_content = True

    while True:
        _check_cancel(is_cancelled)
        chunk = stream.read(chunk_bytes)
        if not chunk:
            break
        if snapshot is not None:
            snapshot.write(chunk)
        if digest is not None:
            digest.update(chunk)
        segment_start = 0
        while True:
            newline = chunk.find(b"\n", segment_start)
            if newline < 0:
                add_line_segment(chunk[segment_start:])
                offset += len(chunk) - segment_start
                break
            add_line_segment(chunk[segment_start:newline])
            offset += newline - segment_start + 1
            finish_line(offset)
            segment_start = newline + 1
    if line_start < offset:
        finish_line(offset)
    if tail_has_content:
        boundaries.append(SDFRecordBoundary(index, record_start, offset))
    _check_cancel(is_cancelled)
    return tuple(boundaries)


def iter_sdf_file_records(source, *, is_cancelled=None, chunk_bytes=64 * 1024):
    """Yield SDF byte ranges from fixed-size binary reads."""
    _check_cancel(is_cancelled)
    with Path(source).open("rb") as stream:
        boundaries = _scan_sdf_stream(
            stream, is_cancelled=is_cancelled, chunk_bytes=chunk_bytes
        )
        yield from _hash_stream_boundaries(stream, boundaries, is_cancelled=is_cancelled)


def _hash_stream_boundaries(stream, boundaries, *, is_cancelled):
    hashed = []
    for boundary in boundaries:
        digest = hashlib.sha256()
        remaining = boundary.end - boundary.start
        stream.seek(boundary.start)
        while remaining:
            _check_cancel(is_cancelled)
            chunk = stream.read(min(64 * 1024, remaining))
            if not chunk:
                raise OSError("SDF source changed while hashing a record")
            digest.update(chunk)
            remaining -= len(chunk)
        hashed.append(replace(boundary, raw_hash=digest.hexdigest()))
    _check_cancel(is_cancelled)
    return tuple(hashed)


def _read_snapshot_record(snapshot, boundary, *, is_cancelled):
    remaining = boundary.end - boundary.start
    chunks = []
    snapshot.seek(boundary.start)
    while remaining:
        _check_cancel(is_cancelled)
        chunk = snapshot.read(min(64 * 1024, remaining))
        if not chunk:
            raise OSError("SDF snapshot changed while reading a record")
        chunks.append(chunk)
        remaining -= len(chunk)
    _check_cancel(is_cancelled)
    return b"".join(chunks)


def _snapshot_source(source, *, is_cancelled, temp_dir=None, chunk_bytes=64 * 1024):
    digest = hashlib.sha256()
    snapshot = tempfile.SpooledTemporaryFile(
        max_size=4 * chunk_bytes, mode="w+b", dir=temp_dir
    )
    try:
        with Path(source).open("rb") as stream:
            boundaries = _scan_sdf_stream(
                stream,
                is_cancelled=is_cancelled,
                chunk_bytes=chunk_bytes,
                snapshot=snapshot,
                digest=digest,
            )
        snapshot.seek(0)
        return snapshot, digest.hexdigest(), _hash_stream_boundaries(
            snapshot, boundaries, is_cancelled=is_cancelled
        )
    except BaseException:
        snapshot.close()
        raise


def _split_mol_block(raw_record):
    line_start = 0
    while line_start < len(raw_record):
        line_end = raw_record.find(b"\n", line_start)
        if line_end < 0:
            line_end = len(raw_record)
            next_line = line_end
        else:
            next_line = line_end + 1
        if raw_record[line_start:line_end].rstrip(b"\r") == b"M  END":
            return raw_record[:next_line], raw_record[next_line:]
        line_start = next_line
    raise ValueError("SDF record is missing M  END")


def _properties(raw_properties):
    lines = raw_properties.splitlines()
    result = []
    index = 0
    while index < len(lines):
        match = _PROPERTY_HEADER.fullmatch(lines[index].rstrip(b"\r"))
        if match is None:
            index += 1
            continue
        name = match.group(1).decode("utf-8", errors="replace")
        index += 1
        values = []
        while index < len(lines) and lines[index].strip(b"\r"):
            values.append(lines[index].rstrip(b"\r").decode("utf-8", errors="replace"))
            index += 1
        result.append(RawRecordProperty(name, "\n".join(values)))
        while index < len(lines) and not lines[index].strip(b"\r"):
            index += 1
    return tuple(result)


def _record_key(source_revision_id, source_hash, boundary):
    identity = uuid5(
        source_revision_id,
        f"sdf:record:{source_hash}:{boundary.index}:{boundary.raw_hash}",
    )
    return f"record-{boundary.index:06d}-{identity}"


def _parse_record(raw_record, boundary, *, source_revision_id, source_hash, validation_mode, is_cancelled):
    try:
        mol_block, raw_properties = _split_mol_block(raw_record)
        text, replaced = _decode_mol(mol_block)
        block_version, lines = _mol_version(text)
    except ValueError as error:
        raise SDFRecordParseError(str(error)) from error
    from .rdkit_common import RDKitMoleculeContext, adapt_rdkit_molecule
    from rdkit import Chem

    key = _record_key(source_revision_id, source_hash, boundary)
    context = RDKitMoleculeContext(
        source_revision_id=source_revision_id,
        source_hash=source_hash,
        record_key=key,
        source_record_index=boundary.index,
        title=lines[0],
        block_version=block_version,
        writer_name=lines[1] or None,
        validation_mode=validation_mode,
    )
    try:
        molecule = Chem.MolFromMolBlock(
            text, sanitize=False, removeHs=False, strictParsing=True
        )
    except ValueError as error:
        raise SDFRecordParseError(str(error)) from error
    if molecule is None:
        raise SDFRecordParseError("RDKit could not parse the SDF MOL block")
    adaptation = adapt_rdkit_molecule(
        molecule, mol_block, context, is_cancelled=is_cancelled
    )
    if adaptation.molecular_record is None:
        raise SDFRecordParseError("SDF record has no usable conformer")
    record = replace(
        adaptation.molecular_record,
        ordered_raw_properties=_properties(raw_properties),
    )
    diagnostics = adaptation.diagnostics + (
        (_decode_diagnostic(context, mol_block),) if replaced else ()
    )
    return adaptation, record, diagnostics


def _failure_diagnostic(source_revision_id, source_hash, boundary, message):
    key = _record_key(source_revision_id, source_hash, boundary)
    return ImportDiagnostic(
        id=uuid5(
            source_revision_id,
            f"sdf:record-parse-failed:{boundary.index}:{boundary.raw_hash}",
        ),
        severity=DiagnosticSeverity.ERROR,
        quality_status=QualityStatus.INVALID,
        source_revision_id=source_revision_id,
        record_key=key,
        entity_id=None,
        field_path=f"record.{boundary.index}",
        code="sdf.record_parse_failed",
        message=message,
        original_value=None,
        normalized_value=None,
        recovery_action="other SDF records were retained",
        scientific_consequence="This record has no imported molecular structure.",
        suggested_action="Correct the record MOL block and import again.",
    )


def _semantic_role(name):
    token = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    return "sdf_property" if not token else f"sdf_{token}"


def _column_value(values):
    present = [value for value in values if value is not None]
    if not present:
        return None
    lowered = [value.lower() for value in present]
    if all(value in {"true", "false"} for value in lowered):
        return bool, [value == "true" for value in lowered]
    if all(_INTEGER.fullmatch(value) for value in present):
        if any(len(value.lstrip("+-")) > 19 for value in present):
            return str, present
        try:
            integers = [int(value) for value in present]
        except ValueError:
            return str, present
        limits = -(2**63), 2**63 - 1
        if all(limits[0] <= value <= limits[1] for value in integers):
            return int, integers
        return str, present
    try:
        converted = [float(value) for value in present]
    except ValueError:
        return str, present
    if not all(math.isfinite(value) for value in converted):
        return str, present
    return float, converted


def _column_revision(name, data, status, validity_mask, record_ids):
    values = data.codes.values if isinstance(data, CategoricalData) else data.values
    payload = {
        "data": values.tolist(),
        "dtype": str(data.dtype),
        "mask": None if validity_mask is None else validity_mask.values.tolist(),
        "name": name,
        "record_ids": [str(item) for item in record_ids],
        "status": status.value,
    }
    if isinstance(data, CategoricalData):
        payload["categories"] = data.categories
        payload["missing_code"] = data.missing_code
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
    ).hexdigest()


def _typed_columns(records, provenance, source_revision_id, *, is_cancelled):
    import numpy

    by_name = {}
    duplicates = set()
    for row, record in enumerate(records):
        _check_cancel(is_cancelled)
        per_record = {}
        for item in record.ordered_raw_properties:
            _check_cancel(is_cancelled)
            if item.name in per_record:
                duplicates.add(item.name)
            per_record[item.name] = item.value
        for name, value in per_record.items():
            by_name.setdefault(name, [None] * len(records))[row] = value or None
    columns = []
    provenance_ids = tuple(item.id for item in provenance)
    record_ids = tuple(record.id for record in records)
    for name in sorted(set(by_name).difference(duplicates)):
        _check_cancel(is_cancelled)
        values = by_name[name]
        converted = _column_value(values)
        if converted is None:
            continue
        value_type, present_values = converted
        mask_values = [value is not None for value in values]
        status = DatasetStatus.COMPLETE if all(mask_values) else DatasetStatus.PARTIAL
        if value_type is str:
            categories = []
            category_codes = {}
            codes = []
            iterator = iter(present_values)
            for present in mask_values:
                _check_cancel(is_cancelled)
                if not present:
                    codes.append(-1)
                    continue
                value = next(iterator)
                if value not in category_codes:
                    category_codes[value] = len(categories)
                    categories.append(value)
                codes.append(category_codes[value])
            data = CategoricalData(
                ArrayData(numpy.asarray(codes, dtype=numpy.int64), ("record",), "dimensionless"),
                tuple(categories),
                -1,
            )
            validity_mask = None
        else:
            iterator = iter(present_values)
            materialized = []
            for present in mask_values:
                _check_cancel(is_cancelled)
                materialized.append(next(iterator) if present else 0)
            dtype = {bool: numpy.bool_, int: numpy.int64, float: numpy.float64}[value_type]
            data = ArrayData(numpy.asarray(materialized, dtype=dtype), ("record",), "dimensionless")
            validity_mask = (
                None
                if status is DatasetStatus.COMPLETE
                else ArrayData(numpy.asarray(mask_values, dtype=numpy.bool_), ("record",), "dimensionless")
            )
        name_hash = hashlib.sha256(name.encode("utf-8")).hexdigest()
        columns.append(
            RecordPropertyColumn(
                id=uuid5(source_revision_id, f"sdf:property:{name_hash}"),
                revision=_column_revision(name, data, status, validity_mask, record_ids),
                semantic_role=_semantic_role(name),
                domain="record",
                data=data,
                status=status,
                source_calculation=None,
                provenance_ids=provenance_ids,
                record_ids=record_ids,
                validity_mask=validity_mask,
            )
        )
    return tuple(columns)


def _report(structures, topologies, records, datasets, provenance, diagnostics):
    created = tuple(
        item.id
        for group in (structures, topologies, records, datasets, provenance)
        for item in group
    )
    capabilities = ["structure", "atomic_identity", "topology", "molecular_record"]
    if datasets:
        capabilities.append("record_property")
    return ParserReport(
        reader_id="sdf",
        reader_version="1",
        created_entity_ids=created,
        parsed_capabilities=tuple(capabilities),
        issues=(),
    )


def _parse_records(boundaries, read_record, *, source_revision_id, source_hash, validation_mode, is_cancelled):
    from .rdkit_common import RDKitMoleculeCancelled

    structures = []
    topologies = []
    records = []
    provenance = []
    diagnostics = []
    for boundary in boundaries:
        _check_cancel(is_cancelled)
        raw_record = read_record(boundary)
        if hashlib.sha256(raw_record).hexdigest() != boundary.raw_hash:
            raise OSError("SDF record hash mismatch")
        try:
            adaptation, record, record_diagnostics = _parse_record(
                raw_record,
                boundary,
                source_revision_id=source_revision_id,
                source_hash=source_hash,
                validation_mode=validation_mode,
                is_cancelled=is_cancelled,
            )
        except (SDFReaderCancelled, RDKitMoleculeCancelled):
            raise
        except SDFRecordParseError as error:
            if validation_mode == "strict":
                raise ValueError(f"SDF record {boundary.index} failed") from error
            diagnostics.append(
                _failure_diagnostic(
                    source_revision_id, source_hash, boundary, type(error).__name__
                )
            )
            continue
        if adaptation.structure is not None:
            structures.append(adaptation.structure)
        topologies.extend(adaptation.topologies)
        records.append(record)
        provenance.append(adaptation.provenance)
        diagnostics.extend(record_diagnostics)
    datasets = _typed_columns(
        records, provenance, source_revision_id, is_cancelled=is_cancelled
    )
    return ImportBatch(
        structures=tuple(structures),
        topologies=tuple(topologies),
        molecular_records=tuple(records),
        datasets=datasets,
        provenance=tuple(provenance),
        diagnostics=tuple(diagnostics),
        report=_report(structures, topologies, records, datasets, provenance, diagnostics),
    )


def _parse_bytes(raw_source, *, source_revision_id, source_hash, validation_mode, is_cancelled):
    return _parse_records(
        iter_sdf_records(raw_source, is_cancelled=is_cancelled),
        lambda boundary: raw_source[boundary.start:boundary.end],
        source_revision_id=source_revision_id,
        source_hash=source_hash,
        validation_mode=validation_mode,
        is_cancelled=is_cancelled,
    )


def _parse_snapshot(snapshot, boundaries, *, source_revision_id, source_hash, validation_mode, is_cancelled):
    return _parse_records(
        boundaries,
        lambda boundary: _read_snapshot_record(
            snapshot, boundary, is_cancelled=is_cancelled
        ),
        source_revision_id=source_revision_id,
        source_hash=source_hash,
        validation_mode=validation_mode,
        is_cancelled=is_cancelled,
    )


def _is_incomplete_mol_prefix(prefix):
    lines = tuple(line.rstrip(b"\r") for line in prefix.splitlines())
    if len(lines) < 5:
        return False
    counts = lines[3]
    if counts.endswith(b"V2000"):
        return bool(
            _V2000_COUNTS.fullmatch(counts)
            and _V2000_ATOM.match(lines[4])
        )
    if not counts.endswith(b"V3000") or len(lines) < 8:
        return False
    return bool(
        lines[4] == b"M  V30 BEGIN CTAB"
        and _V3000_COUNTS.fullmatch(lines[5])
        and lines[6] == b"M  V30 BEGIN ATOM"
        and _V3000_ATOM.match(lines[7])
    )


def sniff_sdf(source, prefix):
    source = Path(source)
    boundaries = tuple(iter_sdf_records(prefix))
    has_delimiter = any(
        line.rstrip(b"\r") == b"$$$$" for line in prefix.splitlines()
    )
    complete = False
    try:
        complete = source.stat().st_size <= len(prefix)
    except OSError:
        pass
    if not has_delimiter:
        if source.suffix.lower() != ".sdf":
            return SniffResult(SniffMatch.NONE, "missing standalone SDF delimiter")
        try:
            mol_block, _properties_bytes = _split_mol_block(prefix)
            _mol_version(_decode_mol(mol_block)[0])
        except ValueError as error:
            if not complete and _is_incomplete_mol_prefix(prefix):
                return SniffResult(
                    SniffMatch.PROBABLE,
                    "incomplete but structurally valid SDF MOL prefix",
                )
            return SniffResult(
                SniffMatch.NONE,
                str(error),
            )
        return SniffResult(
            SniffMatch.EXACT if complete else SniffMatch.PROBABLE,
            "single SDF record without final delimiter" if complete else "SDF delimiter is beyond bounded prefix",
        )
    for boundary in boundaries:
        try:
            mol_block, _properties_bytes = _split_mol_block(
                prefix[boundary.start:boundary.end]
            )
            _mol_version(_decode_mol(mol_block)[0])
            break
        except ValueError as error:
            last_error = error
    else:
        return SniffResult(SniffMatch.NONE, str(last_error))
    return SniffResult(
        SniffMatch.EXACT if complete else SniffMatch.PROBABLE,
        "complete SDF record stream" if complete else "SDF record stream prefix",
    )


def parse_sdf(source):
    snapshot, source_hash, boundaries = _snapshot_source(
        source, is_cancelled=None
    )
    with snapshot:
        return _parse_snapshot(
            snapshot,
            boundaries,
            source_revision_id=uuid5(NAMESPACE_URL, f"chemblender:sdf:{source_hash}"),
            source_hash=source_hash,
            validation_mode="balanced",
            is_cancelled=None,
        )


def parse_sdf_request(request):
    snapshot, source_hash, boundaries = _snapshot_source(
        request.source_path,
        is_cancelled=request.is_cancelled,
        temp_dir=request.staging_root,
    )
    with snapshot:
        if source_hash != request.source_content_hash:
            raise ValueError("source content hash mismatch")
        return _parse_snapshot(
            snapshot,
            boundaries,
            source_revision_id=request.source_revision_id,
            source_hash=source_hash,
            validation_mode=request.validation_mode,
            is_cancelled=request.is_cancelled,
        )


SDF_READER = ReaderDescriptor(
    reader_id="sdf",
    reader_version="1",
    extensions=(".sdf",),
    capabilities=_CAPABILITIES,
    priority=110,
    sniff=sniff_sdf,
    parse=parse_sdf,
    parse_request=parse_sdf_request,
)
