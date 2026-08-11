"""Dependency-free Gaussian Cartesian input reader."""

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


_READER_ID = "gaussian-input"
_READER_VERSION = "1"
_ATOMIC_NUMBERS = {
    symbol: data[0] for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
}
_ELEMENT_SYMBOLS = frozenset((*_ATOMIC_NUMBERS, "D", "T"))


def _normalize_symbol(value):
    value = value.strip()
    if value.upper() in {"D", "T"}:
        return value.upper()
    return value[:1].upper() + value[1:].lower()


def _next_nonempty(lines, index):
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def _parse_text(text):
    lines = text.splitlines()
    if any(line.strip().lower() == "--link1--" for line in lines):
        raise ValueError("Gaussian Link1 inputs are not supported")

    index = _next_nonempty(lines, 0)
    while index < len(lines) and lines[index].lstrip().startswith("%"):
        index += 1
    if index >= len(lines) or not lines[index].lstrip().startswith("#"):
        raise ValueError("Gaussian route section is missing")
    while index < len(lines) and lines[index].strip():
        index += 1
    if index >= len(lines):
        raise ValueError("Gaussian title section is missing")

    index += 1
    title_lines = []
    while index < len(lines) and lines[index].strip():
        title_lines.append(lines[index].strip())
        index += 1
    if not title_lines:
        raise ValueError("Gaussian title section is missing")
    if index >= len(lines):
        raise ValueError("Gaussian charge and multiplicity are missing")

    index += 1
    if index >= len(lines):
        raise ValueError("Gaussian charge and multiplicity are missing")
    charge_fields = lines[index].split()
    if len(charge_fields) != 2:
        raise ValueError("Gaussian charge and multiplicity must contain two integers")
    try:
        charge, multiplicity = (int(value) for value in charge_fields)
    except ValueError as error:
        raise ValueError(
            "Gaussian charge and multiplicity must contain two integers"
        ) from error
    if multiplicity <= 0:
        raise ValueError("Gaussian multiplicity must be positive")

    index += 1
    atomic_numbers = []
    coordinates = []
    isotope_symbols = set()
    while index < len(lines) and lines[index].strip():
        fields = lines[index].split()
        if len(fields) != 4:
            raise ValueError("Gaussian Cartesian atom lines must contain four fields")
        symbol = _normalize_symbol(fields[0])
        if symbol not in _ELEMENT_SYMBOLS:
            raise ValueError(f"unknown Gaussian element symbol: {fields[0]}")
        try:
            xyz = tuple(float(value) for value in fields[1:])
        except ValueError as error:
            raise ValueError("Gaussian Cartesian coordinates must be numeric") from error
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError("Gaussian Cartesian coordinates must be finite")
        if symbol in {"D", "T"}:
            isotope_symbols.add(symbol)
            symbol = "H"
        atomic_numbers.append(_ATOMIC_NUMBERS[symbol])
        coordinates.extend(xyz)
        index += 1
    if not atomic_numbers:
        raise ValueError("Gaussian Cartesian coordinate block is empty")
    return (
        "\n".join(title_lines),
        charge,
        multiplicity,
        tuple(atomic_numbers),
        tuple(coordinates),
        isotope_symbols,
    )


def _looks_like_gaussian(text):
    lines = text.splitlines()
    has_route = any(line.lstrip().startswith("#") for line in lines)
    has_charge = any(
        len(fields := line.split()) == 2
        and all(value.lstrip("+-").isdigit() for value in fields)
        for line in lines
    )
    return has_route and has_charge


def sniff_gaussian_input(source, prefix):
    try:
        text = prefix.decode("utf-8-sig")
    except UnicodeDecodeError:
        return SniffResult(SniffMatch.NONE, "content is not UTF-8 Gaussian text")
    try:
        _parse_text(text)
    except ValueError as error:
        if _looks_like_gaussian(text):
            return SniffResult(SniffMatch.PROBABLE, str(error))
        return SniffResult(SniffMatch.NONE, str(error))
    return SniffResult(SniffMatch.EXACT, "complete Gaussian Cartesian input")


def parse_gaussian_input(source):
    source = Path(source)
    content = source.read_bytes()
    source_hash = hashlib.sha256(content).hexdigest()
    try:
        parsed = _parse_text(content.decode("utf-8-sig"))
    except UnicodeDecodeError as error:
        raise ValueError("Gaussian input must be UTF-8 text") from error
    title, charge, multiplicity, atomic_numbers, values, isotopes = parsed

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
        producer="ChemBlender Gaussian input reader",
        producer_version=_READER_VERSION,
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=(
            ("coordinate_mode", "cartesian"),
            ("format", "gaussian-input"),
            ("title", title),
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


GAUSSIAN_INPUT_READER = ReaderDescriptor(
    reader_id=_READER_ID,
    reader_version=_READER_VERSION,
    extensions=(".gjf", ".com"),
    capabilities={"structure": CapabilitySupport.SUPPORTED},
    priority=100,
    sniff=sniff_gaussian_input,
    parse=parse_gaussian_input,
)
