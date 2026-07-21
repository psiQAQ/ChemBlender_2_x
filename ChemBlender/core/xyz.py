import array
import hashlib
import math
from pathlib import Path
from uuid import uuid4

from ..Chem_data import ELEMENTS_DEFAULT
from .model import (
    ArrayData,
    DatasetStatus,
    FrameSet,
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
_XYZ_SYMBOLS = set(_ATOMIC_NUMBERS) | {"D", "T"}


def _normalize_symbol(symbol):
    symbol = symbol.strip()
    if symbol.upper() in {"D", "T"}:
        return symbol.upper()
    return symbol[:1].upper() + symbol[1:].lower()


def _valid_atom_line(line):
    fields = line.split()
    if len(fields) < 4 or _normalize_symbol(fields[0]) not in _XYZ_SYMBOLS:
        return False
    try:
        coordinates = (float(fields[1]), float(fields[2]), float(fields[3]))
    except ValueError:
        return False
    return all(math.isfinite(value) for value in coordinates)


def sniff_xyz(source: Path, prefix: bytes) -> SniffResult:
    try:
        text = prefix.decode("utf-8-sig")
    except UnicodeDecodeError:
        return SniffResult(SniffMatch.NONE, "content is not UTF-8 XYZ text")

    lines = text.splitlines()
    if not lines:
        return SniffResult(SniffMatch.NONE, "missing atom count")
    try:
        atom_count = int(lines[0].strip())
    except ValueError:
        return SniffResult(SniffMatch.NONE, "atom count is not an integer")
    if atom_count <= 0 or len(lines) < 2:
        return SniffResult(SniffMatch.NONE, "invalid atom count or comment line")

    atom_lines = lines[2 : 2 + atom_count]
    try:
        truncated = source.stat().st_size > len(prefix)
    except OSError:
        truncated = False
    if truncated and atom_lines and not prefix.endswith((b"\n", b"\r")):
        atom_lines = atom_lines[:-1]
    if any(not _valid_atom_line(line) for line in atom_lines):
        return SniffResult(SniffMatch.NONE, "invalid XYZ atom line")
    if len(atom_lines) == atom_count:
        return SniffResult(SniffMatch.EXACT, "complete XYZ frame")
    if truncated and atom_lines:
        return SniffResult(SniffMatch.PROBABLE, "valid XYZ atom prefix")
    if not atom_lines:
        return SniffResult(SniffMatch.POSSIBLE, "XYZ count and comment prefix")
    return SniffResult(SniffMatch.NONE, "incomplete XYZ frame")


def _parse_frame(lines, offset):
    if len(lines) < offset + 2:
        raise ValueError("XYZ frame is missing its atom count or comment")
    try:
        atom_count = int(lines[offset].strip())
    except ValueError as error:
        raise ValueError("XYZ atom count must be an integer") from error
    if atom_count <= 0:
        raise ValueError("XYZ atom count must be positive")
    end = offset + 2 + atom_count
    if len(lines) < end:
        raise ValueError("XYZ source does not contain the declared atom frame")

    atomic_numbers = []
    coordinates = []
    has_extra_columns = False
    isotope_symbols = set()
    for index, line in enumerate(lines[offset + 2 : end], start=1):
        fields = line.split()
        if len(fields) < 4:
            raise ValueError(f"XYZ atom line {index} must contain four fields")
        symbol = _normalize_symbol(fields[0])
        if symbol not in _XYZ_SYMBOLS:
            raise ValueError(f"unknown XYZ element symbol: {fields[0]}")
        if symbol in {"D", "T"}:
            isotope_symbols.add(symbol)
            symbol = "H"
        try:
            xyz = tuple(float(value) for value in fields[1:4])
        except ValueError as error:
            raise ValueError(
                f"XYZ atom line {index} has invalid coordinates"
            ) from error
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError(
                f"XYZ atom line {index} has non-finite coordinates"
            )
        atomic_numbers.append(_ATOMIC_NUMBERS[symbol])
        coordinates.extend(xyz)
        has_extra_columns = has_extra_columns or len(fields) > 4
    return (
        end,
        tuple(atomic_numbers),
        tuple(coordinates),
        lines[offset + 1],
        has_extra_columns,
        isotope_symbols,
    )


def parse_xyz(source: Path) -> ImportBatch:
    source = Path(source)
    content = source.read_bytes()
    source_hash = hashlib.sha256(content).hexdigest()
    try:
        lines = content.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("XYZ source must be UTF-8 text") from error

    while lines and not lines[-1].strip():
        lines.pop()
    frames = []
    offset = 0
    has_extra_columns = False
    isotope_symbols = set()
    while offset < len(lines):
        offset, numbers, coordinates, comment, extra, isotopes = _parse_frame(
            lines, offset
        )
        if frames and numbers != frames[0][0]:
            raise ValueError("XYZ frames must use the same atom order")
        frames.append((numbers, coordinates, comment))
        has_extra_columns = has_extra_columns or extra
        isotope_symbols.update(isotopes)
    if not frames:
        raise ValueError("XYZ source is missing an atom frame")

    issues = []
    if has_extra_columns:
        issues.append(
            ParserIssue(
                IssueKind.UNSUPPORTED,
                "atom_properties",
                "extra XYZ atom columns were not imported",
            )
        )
    if isotope_symbols:
        issues.append(
            ParserIssue(
                IssueKind.WARNING,
                "structure.atomic_numbers",
                f"{', '.join(sorted(isotope_symbols))} mapped to hydrogen",
            )
        )

    atomic_numbers, first_coordinates, first_comment = frames[0]
    coordinates = memoryview(array.array("d", first_coordinates))
    coordinates = coordinates.cast("B").cast(
        "d", shape=(len(atomic_numbers), 3)
    )
    structure_id = uuid4()
    provenance_id = uuid4()
    structure = Structure(
        id=structure_id,
        revision=source_hash,
        atomic_numbers=atomic_numbers,
        coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"),
    )
    datasets = ()
    created_entity_ids = [structure_id]
    parsed_capabilities = ["structure"]
    if len(frames) > 1:
        flat_frame_coordinates = [
            value
            for _, frame_coordinates, _ in frames
            for value in frame_coordinates
        ]
        frame_values = memoryview(
            array.array("d", flat_frame_coordinates)
        )
        frame_values = frame_values.cast("B").cast(
            "d", shape=(len(frames), len(atomic_numbers), 3)
        )
        frame_set = FrameSet(
            id=uuid4(),
            revision=source_hash,
            semantic_role="coordinates",
            domain="frame",
            data=ArrayData(
                frame_values,
                ("frame", "atom", "xyz"),
                "angstrom",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(provenance_id,),
            structure_id=structure_id,
            comments=tuple(frame[2] for frame in frames),
        )
        datasets = (frame_set,)
        created_entity_ids.append(frame_set.id)
        parsed_capabilities.append("trajectory")
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=source_hash,
        producer="ChemBlender XYZ reader",
        producer_version="1",
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=(("format", "xyz"), ("comment", first_comment)),
    )
    created_entity_ids.append(provenance_id)
    report = ParserReport(
        reader_id="xyz",
        reader_version="1",
        created_entity_ids=tuple(created_entity_ids),
        parsed_capabilities=tuple(parsed_capabilities),
        issues=tuple(issues),
    )
    return ImportBatch(
        structures=(structure,),
        datasets=datasets,
        provenance=(provenance,),
        report=report,
    )


XYZ_READER = ReaderDescriptor(
    reader_id="xyz",
    reader_version="1",
    extensions=(".xyz",),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "trajectory": CapabilitySupport.SUPPORTED,
    },
    priority=100,
    sniff=sniff_xyz,
    parse=parse_xyz,
)
