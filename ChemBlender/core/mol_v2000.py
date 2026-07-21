import array
import hashlib
import math
from pathlib import Path
from uuid import uuid4

from ..Chem_data import ELEMENTS_DEFAULT
from .model import (
    ArrayData,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    ProvenanceRecord,
    Structure,
)
from .readers import (
    CapabilitySupport,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
)


_ATOMIC_NUMBERS = {
    symbol: data[0] for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
}


def _counts(line):
    if "V2000" not in line[6:]:
        raise ValueError("MOL record must use V2000")
    try:
        atom_count = int(line[0:3])
        bond_count = int(line[3:6])
    except ValueError as error:
        raise ValueError("MOL counts line is invalid") from error
    if atom_count <= 0 or bond_count < 0:
        raise ValueError("MOL atom count must be positive and bond count non-negative")
    return atom_count, bond_count


def _atom(line, index):
    try:
        coordinates = tuple(float(line[start : start + 10]) for start in (0, 10, 20))
    except ValueError as error:
        raise ValueError(f"MOL atom line {index} has invalid coordinates") from error
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError(f"MOL atom line {index} has non-finite coordinates")
    symbol = line[31:34].strip()
    symbol = symbol[:1].upper() + symbol[1:].lower()
    try:
        atomic_number = _ATOMIC_NUMBERS[symbol]
    except KeyError as error:
        raise ValueError(f"unknown MOL element symbol: {symbol}") from error
    return atomic_number, coordinates


def sniff_mol_v2000(source: Path, prefix: bytes) -> SniffResult:
    try:
        lines = prefix.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        return SniffResult(SniffMatch.NONE, "content is not UTF-8 MOL text")
    if len(lines) < 4:
        return SniffResult(SniffMatch.NONE, "missing MOL counts line")
    try:
        atom_count, _ = _counts(lines[3])
    except ValueError:
        return SniffResult(SniffMatch.NONE, "invalid or non-V2000 counts line")
    atom_lines = lines[4 : 4 + atom_count]
    try:
        for index, line in enumerate(atom_lines, start=1):
            _atom(line, index)
    except ValueError:
        return SniffResult(SniffMatch.NONE, "invalid MOL atom line")
    if len(atom_lines) == atom_count and any(
        line.strip() == "M  END" for line in lines[4 + atom_count :]
    ):
        return SniffResult(SniffMatch.EXACT, "complete MOL V2000 record")
    try:
        truncated = source.stat().st_size > len(prefix)
    except OSError:
        truncated = False
    if truncated and atom_lines:
        return SniffResult(SniffMatch.PROBABLE, "valid MOL V2000 prefix")
    return SniffResult(SniffMatch.NONE, "incomplete MOL V2000 record")


def parse_mol_v2000(source: Path) -> ImportBatch:
    source = Path(source)
    content = source.read_bytes()
    source_hash = hashlib.sha256(content).hexdigest()
    try:
        lines = content.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("MOL source must be UTF-8 text") from error
    if len(lines) < 4:
        raise ValueError("MOL source is missing its counts line")
    if any(line.strip() == "$$$$" for line in lines):
        raise ValueError("SDF records are not supported by the MOL V2000 reader")

    atom_count, bond_count = _counts(lines[3])
    atom_end = 4 + atom_count
    bond_end = atom_end + bond_count
    if len(lines) < bond_end:
        raise ValueError("MOL source does not contain its declared atom and bond blocks")

    atomic_numbers = []
    flat_coordinates = []
    for index, line in enumerate(lines[4:atom_end], start=1):
        atomic_number, coordinates = _atom(line, index)
        atomic_numbers.append(atomic_number)
        flat_coordinates.extend(coordinates)

    try:
        end = next(
            index
            for index in range(bond_end, len(lines))
            if lines[index].strip() == "M  END"
        )
    except StopIteration as error:
        raise ValueError("MOL source is missing M  END") from error
    if any(line.strip() for line in lines[end + 1 :]):
        raise ValueError("MOL source contains content after M  END")

    issues = []
    if bond_count:
        issues.append(
            ParserIssue(
                IssueKind.UNSUPPORTED,
                "topology",
                "MOL bonds were not imported",
            )
        )
    if any(line.strip() for line in lines[bond_end:end]):
        issues.append(
            ParserIssue(
                IssueKind.UNSUPPORTED,
                "atom_properties",
                "MOL property records were not imported",
            )
        )

    values = memoryview(array.array("d", flat_coordinates))
    values = values.cast("B").cast("d", shape=(atom_count, 3))
    structure_id = uuid4()
    provenance_id = uuid4()
    structure = Structure(
        id=structure_id,
        revision=source_hash,
        atomic_numbers=tuple(atomic_numbers),
        coordinates=ArrayData(values, ("atom", "xyz"), "angstrom"),
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=source_hash,
        producer="ChemBlender MOL V2000 reader",
        producer_version="1",
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=(("format", "mol_v2000"), ("title", lines[0])),
    )
    report = ParserReport(
        reader_id="mol-v2000",
        reader_version="1",
        created_entity_ids=(structure_id, provenance_id),
        parsed_capabilities=("structure",),
        issues=tuple(issues),
    )
    return ImportBatch(
        structures=(structure,),
        provenance=(provenance,),
        report=report,
    )


MOL_V2000_READER = ReaderDescriptor(
    reader_id="mol-v2000",
    reader_version="1",
    extensions=(".mol",),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "topology": CapabilitySupport.UNSUPPORTED,
    },
    priority=100,
    sniff=sniff_mol_v2000,
    parse=parse_mol_v2000,
)
