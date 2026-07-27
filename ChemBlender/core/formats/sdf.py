"""Byte-oriented recoverable multi-record SDF reader."""

import hashlib
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ..model import (
    ArrayData,
    DatasetStatus,
    DiagnosticSeverity,
    ImportBatch,
    ImportDiagnostic,
    IssueKind,
    ParserIssue,
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
_PROPERTY_HEADER = re.compile(br">\s*<([^>]*)>")
_INTEGER = re.compile(r"[+-]?\d+\Z", re.ASCII)


class SDFReaderCancelled(Exception):
    """Signal reader cancellation before an incomplete record is emitted."""


@dataclass(frozen=True, slots=True)
class SDFRecordBoundary:
    index: int
    start: int
    end: int


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
            yield SDFRecordBoundary(index, start, line_start)
            index += 1
            start = next_line
        line_start = next_line
    _check_cancel(is_cancelled)
    if raw_source[start:].strip(b"\r\n"):
        yield SDFRecordBoundary(index, start, size)


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


def _record_key(index, raw_record):
    return f"record-{index:06d}-{hashlib.sha256(raw_record).hexdigest()[:16]}"


def _parse_record(raw_record, boundary, *, source_revision_id, source_hash, validation_mode, is_cancelled):
    mol_block, raw_properties = _split_mol_block(raw_record)
    text, replaced = _decode_mol(mol_block)
    block_version, lines = _mol_version(text)
    from .rdkit_common import RDKitMoleculeContext, adapt_rdkit_molecule
    from rdkit import Chem

    key = _record_key(boundary.index, raw_record)
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
    molecule = Chem.MolFromMolBlock(
        text, sanitize=False, removeHs=False, strictParsing=True
    )
    if molecule is None:
        raise ValueError("RDKit could not parse the SDF MOL block")
    adaptation = adapt_rdkit_molecule(
        molecule, mol_block, context, is_cancelled=is_cancelled
    )
    if adaptation.molecular_record is None:
        raise ValueError("SDF record has no usable conformer")
    record = replace(
        adaptation.molecular_record,
        ordered_raw_properties=_properties(raw_properties),
    )
    diagnostics = adaptation.diagnostics + (
        (_decode_diagnostic(context, mol_block),) if replaced else ()
    )
    return adaptation, record, diagnostics


def _failure_diagnostic(source_revision_id, boundary, raw_record, message):
    key = _record_key(boundary.index, raw_record)
    raw_hash = hashlib.sha256(raw_record).hexdigest()
    return ImportDiagnostic(
        id=uuid5(source_revision_id, f"sdf:record-parse-failed:{boundary.index}:{raw_hash}"),
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
        return int, [int(value) for value in present]
    try:
        converted = [float(value) for value in present]
    except ValueError:
        return None
    if not all(math.isfinite(value) for value in converted):
        return None
    return float, converted


def _typed_columns(records, provenance, source_revision_id):
    import numpy

    by_name = {}
    duplicates = set()
    for row, record in enumerate(records):
        per_record = {}
        for item in record.ordered_raw_properties:
            if item.name in per_record:
                duplicates.add(item.name)
            per_record[item.name] = item.value
        for name, value in per_record.items():
            by_name.setdefault(name, [None] * len(records))[row] = value or None
    columns = []
    provenance_ids = tuple(item.id for item in provenance)
    record_ids = tuple(record.id for record in records)
    for name in sorted(set(by_name).difference(duplicates)):
        values = by_name[name]
        converted = _column_value(values)
        if converted is None:
            continue
        value_type, present_values = converted
        iterator = iter(present_values)
        mask_values = [value is not None for value in values]
        materialized = [next(iterator) if present else 0 for present in mask_values]
        status = DatasetStatus.COMPLETE if all(mask_values) else DatasetStatus.PARTIAL
        dtype = {bool: numpy.bool_, int: numpy.int64, float: numpy.float64}[value_type]
        name_hash = hashlib.sha256(name.encode("utf-8")).hexdigest()
        columns.append(
            RecordPropertyColumn(
                id=uuid5(source_revision_id, f"sdf:property:{name_hash}"),
                revision=hashlib.sha256(repr(materialized).encode("utf-8")).hexdigest(),
                semantic_role=_semantic_role(name),
                domain="record",
                data=ArrayData(numpy.asarray(materialized, dtype=dtype), ("record",), "dimensionless"),
                status=status,
                source_calculation=None,
                provenance_ids=provenance_ids,
                record_ids=record_ids,
                validity_mask=(
                    None
                    if status is DatasetStatus.COMPLETE
                    else ArrayData(numpy.asarray(mask_values, dtype=numpy.bool_), ("record",), "dimensionless")
                ),
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
        issues=tuple(
            ParserIssue(IssueKind.INVALID, item.field_path, item.message)
            for item in diagnostics
            if item.code == "sdf.record_parse_failed"
        ),
    )


def _parse_bytes(raw_source, *, source_revision_id, source_hash, validation_mode, is_cancelled):
    from .rdkit_common import RDKitMoleculeCancelled

    structures = []
    topologies = []
    records = []
    provenance = []
    diagnostics = []
    for boundary in iter_sdf_records(raw_source, is_cancelled=is_cancelled):
        raw_record = raw_source[boundary.start:boundary.end]
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
        except Exception as error:
            if validation_mode == "strict":
                raise ValueError(f"SDF record {boundary.index} failed") from error
            diagnostics.append(
                _failure_diagnostic(
                    source_revision_id, boundary, raw_record, type(error).__name__
                )
            )
            continue
        if adaptation.structure is not None:
            structures.append(adaptation.structure)
        topologies.extend(adaptation.topologies)
        records.append(record)
        provenance.append(adaptation.provenance)
        diagnostics.extend(record_diagnostics)
    datasets = _typed_columns(records, provenance, source_revision_id)
    return ImportBatch(
        structures=tuple(structures),
        topologies=tuple(topologies),
        molecular_records=tuple(records),
        datasets=datasets,
        provenance=tuple(provenance),
        diagnostics=tuple(diagnostics),
        report=_report(structures, topologies, records, datasets, provenance, diagnostics),
    )


def sniff_sdf(source, prefix):
    source = Path(source)
    boundaries = tuple(iter_sdf_records(prefix))
    if not boundaries or not any(prefix[item.end:item.end + 5] for item in boundaries[:-1]):
        return SniffResult(SniffMatch.NONE, "missing standalone SDF delimiter")
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
    try:
        complete = source.stat().st_size <= len(prefix)
    except OSError:
        complete = False
    return SniffResult(
        SniffMatch.EXACT if complete else SniffMatch.PROBABLE,
        "complete SDF record stream" if complete else "SDF record stream prefix",
    )


def parse_sdf(source):
    raw_source = Path(source).read_bytes()
    source_hash = hashlib.sha256(raw_source).hexdigest()
    return _parse_bytes(
        raw_source,
        source_revision_id=uuid5(NAMESPACE_URL, f"chemblender:sdf:{source_hash}"),
        source_hash=source_hash,
        validation_mode="balanced",
        is_cancelled=None,
    )


def parse_sdf_request(request):
    return _parse_bytes(
        request.source_path.read_bytes(),
        source_revision_id=request.source_revision_id,
        source_hash=request.source_content_hash,
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
