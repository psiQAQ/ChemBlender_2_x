"""Dependency-free ORCA Cartesian input reader."""

import array
import hashlib
import math
from pathlib import Path
from uuid import uuid4

from ...Chem_data import ELEMENTS_DEFAULT
from ..model import (
    ArrayData,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    ProvenanceRecord,
    Structure,
)
from ..readers import CapabilitySupport, ReaderDescriptor, SniffMatch, SniffResult


_READER_ID = "orca-input"
_READER_VERSION = "1"
_ATOMIC_NUMBERS = {
    symbol: data[0]
    for symbol, data in ELEMENTS_DEFAULT.items()
    if 1 <= data[0] <= 118
}
_ELEMENT_SYMBOLS = frozenset((*_ATOMIC_NUMBERS, "D", "T"))


def _normalize_symbol(value):
    value = value.strip()
    if value.upper() in {"D", "T"}:
        return value.upper()
    return value[:1].upper() + value[1:].lower()


def _coordinate_headers(lines):
    headers = []
    xyzfiles = []
    internal = []
    for index, line in enumerate(lines):
        fields = line.split()
        if len(fields) < 2 or fields[0] != "*":
            continue
        kind = fields[1].lower()
        if kind == "xyz":
            headers.append((index, fields))
        elif kind == "xyzfile":
            xyzfiles.append((index, fields))
        elif kind in {"int", "internal"}:
            internal.append((index, fields))
    return headers, xyzfiles, internal


def _parse_text(text):
    lines = text.splitlines()
    headers, xyzfiles, internal = _coordinate_headers(lines)
    if xyzfiles:
        raise ValueError("ORCA xyzfile references are not supported")
    if internal:
        raise ValueError("ORCA internal coordinates are not supported")
    if not headers:
        raise ValueError("ORCA inline xyz coordinate block is missing")
    if len(headers) != 1:
        raise ValueError("multiple ORCA coordinate blocks are not supported")

    header_index, fields = headers[0]
    if len(fields) != 4:
        raise ValueError("ORCA xyz header must contain charge and multiplicity")
    try:
        charge, multiplicity = (int(value) for value in fields[2:])
    except ValueError as error:
        raise ValueError("ORCA charge and multiplicity must contain two integers") from error
    if multiplicity <= 0:
        raise ValueError("ORCA multiplicity must be positive")

    atomic_numbers = []
    coordinates = []
    isotope_symbols = set()
    index = header_index + 1
    while index < len(lines) and lines[index].strip() != "*":
        fields = lines[index].split()
        if len(fields) != 4:
            raise ValueError("ORCA Cartesian atom lines must contain four fields")
        symbol = _normalize_symbol(fields[0])
        if symbol not in _ELEMENT_SYMBOLS:
            raise ValueError(f"unknown ORCA element symbol: {fields[0]}")
        try:
            xyz = tuple(float(value) for value in fields[1:])
        except ValueError as error:
            raise ValueError("ORCA Cartesian coordinates must be numeric") from error
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError("ORCA Cartesian coordinates must be finite")
        if symbol in {"D", "T"}:
            isotope_symbols.add(symbol)
            symbol = "H"
        atomic_numbers.append(_ATOMIC_NUMBERS[symbol])
        coordinates.extend(xyz)
        index += 1
    if index >= len(lines):
        raise ValueError("ORCA xyz coordinate block must be terminated by *")
    if not atomic_numbers:
        raise ValueError("ORCA Cartesian coordinate block is empty")
    return (
        charge,
        multiplicity,
        tuple(atomic_numbers),
        tuple(coordinates),
        isotope_symbols,
    )


def sniff_orca_input(source, prefix):
    try:
        text = prefix.decode("utf-8-sig")
    except UnicodeDecodeError:
        return SniffResult(SniffMatch.NONE, "content is not UTF-8 ORCA text")
    headers, xyzfiles, internal = _coordinate_headers(text.splitlines())
    if xyzfiles:
        return SniffResult(
            SniffMatch.PROBABLE,
            "ORCA xyzfile input requires an unsupported external reference",
        )
    if internal:
        return SniffResult(
            SniffMatch.PROBABLE,
            "ORCA internal coordinates are not supported",
        )
    if not headers:
        return SniffResult(SniffMatch.NONE, "ORCA xyz coordinate marker is missing")
    try:
        _parse_text(text)
    except ValueError as error:
        return SniffResult(SniffMatch.PROBABLE, str(error))
    return SniffResult(SniffMatch.EXACT, "complete ORCA Cartesian input")


def parse_orca_input(source):
    source = Path(source)
    content = source.read_bytes()
    source_hash = hashlib.sha256(content).hexdigest()
    try:
        parsed = _parse_text(content.decode("utf-8-sig"))
    except UnicodeDecodeError as error:
        raise ValueError("ORCA input must be UTF-8 text") from error
    charge, multiplicity, atomic_numbers, values, isotopes = parsed

    coordinates = memoryview(array.array("d", values)).cast("B").cast(
        "d", shape=(len(atomic_numbers), 3)
    )
    structure_id = uuid4()
    provenance_id = uuid4()
    structure = Structure(
        id=structure_id,
        revision=source_hash,
        atomic_numbers=atomic_numbers,
        coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"),
        molecular_charge=charge,
        molecular_multiplicity=multiplicity,
    )
    issues = ()
    if isotopes:
        issues = (
            ParserIssue(
                IssueKind.WARNING,
                "structure.atomic_numbers",
                f"{', '.join(sorted(isotopes))} mapped to hydrogen",
            ),
        )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=source_hash,
        producer="ChemBlender ORCA input reader",
        producer_version=_READER_VERSION,
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=(
            ("coordinate_mode", "cartesian"),
            ("format", "orca-input"),
        ),
    )
    report = ParserReport(
        reader_id=_READER_ID,
        reader_version=_READER_VERSION,
        created_entity_ids=(structure_id, provenance_id),
        parsed_capabilities=("structure",),
        issues=issues,
    )
    return ImportBatch(
        structures=(structure,),
        provenance=(provenance,),
        report=report,
    )


ORCA_INPUT_READER = ReaderDescriptor(
    reader_id=_READER_ID,
    reader_version=_READER_VERSION,
    extensions=(".inp",),
    capabilities={"structure": CapabilitySupport.SUPPORTED},
    priority=100,
    sniff=sniff_orca_input,
    parse=parse_orca_input,
)
