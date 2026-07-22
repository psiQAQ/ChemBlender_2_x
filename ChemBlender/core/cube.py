import array
import hashlib
import math
from pathlib import Path
from uuid import uuid4

from .model import (
    ArrayData,
    DatasetStatus,
    Grid3D,
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


def _finite_floats(fields, label):
    try:
        values = tuple(float(field) for field in fields)
    except ValueError as error:
        raise ValueError(f"Cube {label} contains an invalid number") from error
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"Cube {label} contains a non-finite number")
    return values


def _header_and_axes(lines):
    if len(lines) < 6:
        raise ValueError("Cube source is missing its header or axes")
    header = lines[2].split()
    if len(header) not in (4, 5):
        raise ValueError("Cube origin line must contain four or five fields")
    try:
        signed_atom_count = int(header[0])
        nval = int(header[4]) if len(header) == 5 else 1
    except ValueError as error:
        raise ValueError("Cube atom count and NVAL must be integers") from error
    if signed_atom_count == 0 or nval <= 0:
        raise ValueError("Cube atom count must be nonzero and NVAL positive")
    if signed_atom_count < 0 and nval != 1:
        raise ValueError("negative Cube NATOMS requires absent or unit NVAL")
    origin = _finite_floats(header[1:4], "origin")

    grid_shape = []
    step_vectors = []
    has_negative_count = False
    for line in lines[3:6]:
        fields = line.split()
        if len(fields) != 4:
            raise ValueError("Cube axis lines must contain four fields")
        try:
            signed_count = int(fields[0])
        except ValueError as error:
            raise ValueError("Cube voxel count must be an integer") from error
        if signed_count == 0:
            raise ValueError("Cube voxel counts must be nonzero")
        grid_shape.append(abs(signed_count))
        step_vectors.append(_finite_floats(fields[1:4], "step vector"))
        has_negative_count = has_negative_count or signed_count < 0
    return (
        signed_atom_count,
        nval,
        origin,
        tuple(grid_shape),
        tuple(step_vectors),
        has_negative_count,
    )


def sniff_cube(source: Path, prefix: bytes) -> SniffResult:
    try:
        lines = prefix.decode("utf-8-sig").splitlines()
        _header_and_axes(lines)
    except (UnicodeDecodeError, ValueError):
        return SniffResult(SniffMatch.NONE, "invalid Cube header or axes")
    try:
        truncated = source.stat().st_size > len(prefix)
    except OSError:
        truncated = False
    if truncated:
        return SniffResult(SniffMatch.PROBABLE, "valid Cube header prefix")
    return SniffResult(SniffMatch.EXACT, "complete Cube text with valid header")


def parse_cube(source: Path) -> ImportBatch:
    source = Path(source)
    content = source.read_bytes()
    source_hash = hashlib.sha256(content).hexdigest()
    try:
        lines = content.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("Cube source must be UTF-8 text") from error
    (
        signed_atom_count,
        nval,
        origin,
        grid_shape,
        step_vectors,
        has_negative_count,
    ) = _header_and_axes(lines)

    atom_count = abs(signed_atom_count)
    atom_end = 6 + atom_count
    if len(lines) < atom_end:
        raise ValueError("Cube source does not contain its declared atoms")
    atomic_numbers = []
    flat_coordinates = []
    nondefault_nuclear_charge = False
    for index, line in enumerate(lines[6:atom_end], start=1):
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"Cube atom line {index} must contain five fields")
        try:
            atomic_number = int(fields[0])
        except ValueError as error:
            raise ValueError(
                f"Cube atom line {index} has invalid atomic number"
            ) from error
        if not 0 <= atomic_number <= 118:
            raise ValueError("Cube atomic numbers must be from 0 to 118")
        nuclear_charge, *coordinates = _finite_floats(
            fields[1:], f"atom line {index}"
        )
        atomic_numbers.append(atomic_number)
        flat_coordinates.extend(coordinates)
        nondefault_nuclear_charge = (
            nondefault_nuclear_charge or nuclear_charge != atomic_number
        )

    tokens = " ".join(lines[atom_end:]).split()
    dataset_ids = None
    if signed_atom_count < 0:
        if not tokens:
            raise ValueError("Cube source is missing DSET_IDS")
        try:
            dataset_count = int(tokens[0])
        except ValueError as error:
            raise ValueError("Cube dataset count must be an integer") from error
        if dataset_count <= 0 or len(tokens) < dataset_count + 1:
            raise ValueError("Cube DSET_IDS is truncated or empty")
        try:
            dataset_ids = tuple(
                int(token) for token in tokens[1 : dataset_count + 1]
            )
        except ValueError as error:
            raise ValueError("Cube dataset IDs must be integers") from error
        data_tokens = tokens[dataset_count + 1 :]
    else:
        dataset_count = nval
        data_tokens = tokens

    voxel_count = math.prod(grid_shape)
    expected_values = voxel_count * dataset_count
    if len(data_tokens) != expected_values:
        raise ValueError(
            f"Cube data count must be {expected_values}, got {len(data_tokens)}"
        )
    data_values = _finite_floats(data_tokens, "data")
    if dataset_count == 1:
        flat_grid = data_values
        dims = ("x", "y", "z")
        shape = grid_shape
    else:
        flat_grid = tuple(
            data_values[voxel * dataset_count + dataset]
            for dataset in range(dataset_count)
            for voxel in range(voxel_count)
        )
        dims = ("dataset", "x", "y", "z")
        shape = (dataset_count, *grid_shape)

    coordinate_values = memoryview(array.array("d", flat_coordinates))
    coordinate_values = coordinate_values.cast("B").cast(
        "d", shape=(atom_count, 3)
    )
    grid_values = memoryview(array.array("d", flat_grid))
    grid_values = grid_values.cast("B").cast("d", shape=shape)
    structure_id = uuid4()
    grid_id = uuid4()
    provenance_id = uuid4()
    structure = Structure(
        id=structure_id,
        revision=source_hash,
        atomic_numbers=tuple(atomic_numbers),
        coordinates=ArrayData(coordinate_values, ("atom", "xyz"), "bohr"),
    )
    grid = Grid3D(
        id=grid_id,
        revision=source_hash,
        semantic_role="scalar_field",
        domain="grid",
        data=ArrayData(grid_values, dims, "unknown"),
        status=DatasetStatus.AMBIGUOUS,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        origin=origin,
        step_vectors=step_vectors,
        coordinate_unit="bohr",
    )

    issues = [
        ParserIssue(
            IssueKind.AMBIGUOUS,
            "grid.semantic_role",
            "Cube does not reliably identify the scalar-field semantics",
        ),
        ParserIssue(
            IssueKind.AMBIGUOUS,
            "grid.data.unit",
            "Cube does not reliably identify the scalar-field value unit",
        ),
    ]
    if has_negative_count:
        issues.append(
            ParserIssue(
                IssueKind.WARNING,
                "grid.voxel_counts",
                "negative voxel counts were treated as bohr Cube dimensions",
            )
        )
    if nondefault_nuclear_charge:
        issues.append(
            ParserIssue(
                IssueKind.UNSUPPORTED,
                "atom_nuclear_charge",
                "Cube nuclear charges differing from atomic numbers were not imported",
            )
        )

    parameters = [
        ("format", "cube"),
        ("comment_1", lines[0]),
        ("comment_2", lines[1]),
        ("dataset_count", dataset_count),
    ]
    if dataset_ids is not None:
        parameters.append(("dataset_ids", dataset_ids))
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=source_hash,
        producer="ChemBlender Cube reader",
        producer_version="1",
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=tuple(parameters),
    )
    report = ParserReport(
        reader_id="cube",
        reader_version="1",
        created_entity_ids=(structure_id, grid_id, provenance_id),
        parsed_capabilities=("structure", "grid"),
        issues=tuple(issues),
    )
    return ImportBatch(
        structures=(structure,),
        datasets=(grid,),
        provenance=(provenance,),
        report=report,
    )


CUBE_READER = ReaderDescriptor(
    reader_id="cube",
    reader_version="1",
    extensions=(".cube", ".cub"),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "grid": CapabilitySupport.SUPPORTED,
    },
    priority=100,
    sniff=sniff_cube,
    parse=parse_cube,
)
