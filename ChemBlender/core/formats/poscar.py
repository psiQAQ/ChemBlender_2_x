"""Dependency-free POSCAR/CONTCAR syntax parsing."""

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
from uuid import NAMESPACE_URL, uuid5

from ...Chem_data import ELEMENTS_DEFAULT
from ..model import (
    ArrayData,
    AtomicProperty,
    DatasetStatus,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    PeriodicSiteData,
    PropertyDataset,
    ProvenanceRecord,
    Structure,
)
from ..readers import (
    SNIFF_PREFIX_BYTES,
    CapabilitySupport,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
)


_INTEGER = re.compile(r"[+-]?[0-9]+\Z")
_POSCAR_SUFFIXES = frozenset((".vasp", ".poscar", ".contcar"))
_ATOMIC_NUMBERS = {
    symbol: data[0]
    for symbol, data in ELEMENTS_DEFAULT.items()
    if 0 < data[0] <= 118
}
_READER_VERSION = "1"


class PoscarSyntaxError(ValueError):
    """Stable syntax failure for a POSCAR or CONTCAR document."""


@dataclass(frozen=True, slots=True)
class PoscarLatticeVelocityBlock:
    initialization_state: float
    velocities: tuple[tuple[float, float, float], ...]
    lattice_vectors: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True, slots=True)
class PoscarDocument:
    comment: str
    scale: float
    scale_factor: float
    lattice: tuple[tuple[float, float, float], ...]
    species: tuple[str, ...] | None
    counts: tuple[int, ...]
    coordinate_mode: str
    coordinates: tuple[tuple[float, float, float], ...]
    selective_dynamics: tuple[tuple[bool, bool, bool], ...] | None
    lattice_velocities: PoscarLatticeVelocityBlock | None
    velocity_mode: str | None
    velocities: tuple[tuple[float, float, float], ...] | None
    diagnostics: tuple[ParserIssue, ...]


def _numbers(line, *, count, name):
    fields = line.split()
    if len(fields) != count:
        raise PoscarSyntaxError(f"{name} must contain {count} numeric fields")
    try:
        values = tuple(float(value) for value in fields)
    except ValueError as error:
        raise PoscarSyntaxError(f"{name} must contain numeric fields") from error
    if not all(math.isfinite(value) for value in values):
        raise PoscarSyntaxError(f"{name} must contain finite numeric fields")
    return values


def _determinant(lattice):
    (a, b, c), (d, e, f), (g, h, i) = lattice
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def _parse_counts(line):
    values = line.split()
    if not values or not all(_INTEGER.fullmatch(value) for value in values):
        raise PoscarSyntaxError("POSCAR counts must be positive integers")
    counts = tuple(int(value) for value in values)
    if any(value <= 0 for value in counts):
        raise PoscarSyntaxError("POSCAR counts must be positive integers")
    return counts


def _mode(line):
    marker = line.lstrip()[:1].lower()
    if marker == "d":
        return "direct"
    if marker in {"c", "k"}:
        return "cartesian"
    raise PoscarSyntaxError("POSCAR coordinate mode must be Direct or Cartesian/K")


def _parse_coordinates(lines, start, count, selective):
    end = start + count
    if len(lines) < end:
        raise PoscarSyntaxError("POSCAR does not contain the declared coordinate rows")
    coordinates = []
    flags = []
    for line in lines[start:end]:
        fields = line.split()
        required = 6 if selective else 3
        if len(fields) != required:
            raise PoscarSyntaxError(
                f"POSCAR coordinate rows must contain {required} fields"
            )
        coordinates.append(_numbers(" ".join(fields[:3]), count=3, name="coordinates"))
        if selective:
            triplet = tuple(value.upper() for value in fields[3:])
            if any(value not in {"T", "F"} for value in triplet):
                raise PoscarSyntaxError("POSCAR selective dynamics requires T/F triplets")
            flags.append(tuple(value == "T" for value in triplet))
    return tuple(coordinates), tuple(flags) if selective else None, end


def _parse_velocities(lines, start, count):
    if start >= len(lines):
        return None, None
    remaining = lines[start:]
    if not any(line.strip() for line in remaining):
        return None, None
    marker = remaining[0].lstrip()[:1].lower()
    mode = "cartesian" if not marker or marker in {"c", "k"} else "direct"
    rows = remaining[1:]
    while rows and not rows[-1].strip():
        rows.pop()
    if len(rows) != count:
        raise PoscarSyntaxError("POSCAR velocity block must contain one row per atom")
    return mode, tuple(
        _numbers(line, count=3, name="POSCAR velocity rows") for line in rows
    )


def _parse_lattice_velocities(lines, start):
    if start >= len(lines) or lines[start].lstrip()[:1].lower() != "l":
        return None, start
    if len(lines) < start + 8:
        raise PoscarSyntaxError("POSCAR lattice velocity block must contain 8 lines")
    initialization_state, = _numbers(
        lines[start + 1],
        count=1,
        name="POSCAR lattice velocity initialization state",
    )
    velocities = tuple(
        _numbers(line, count=3, name="POSCAR lattice velocity rows")
        for line in lines[start + 2 : start + 5]
    )
    lattice_vectors = tuple(
        _numbers(line, count=3, name="POSCAR lattice velocity vectors")
        for line in lines[start + 5 : start + 8]
    )
    return (
        PoscarLatticeVelocityBlock(
            initialization_state=initialization_state,
            velocities=velocities,
            lattice_vectors=lattice_vectors,
        ),
        start + 8,
    )


def parse_poscar_document(raw):
    if not isinstance(raw, bytes):
        raise TypeError("raw must be bytes")
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as error:
        raise PoscarSyntaxError("POSCAR content must be UTF-8 text") from error
    if len(lines) < 8:
        raise PoscarSyntaxError("POSCAR is missing scale, lattice, or coordinates")

    comment = lines[0]
    scale, = _numbers(lines[1], count=1, name="POSCAR scale")
    lattice = tuple(
        _numbers(line, count=3, name="POSCAR lattice vector")
        for line in lines[2:5]
    )
    labels = lines[5].split()
    if not labels:
        raise PoscarSyntaxError("POSCAR species or counts line is required")
    if all(_INTEGER.fullmatch(label) for label in labels):
        species = None
        counts = _parse_counts(lines[5])
        index = 6
    else:
        species = tuple(labels)
        counts = _parse_counts(lines[6])
        if len(species) != len(counts):
            raise PoscarSyntaxError("POSCAR species and counts must have equal lengths")
        index = 7

    selective = lines[index].lstrip()[:1].lower() == "s"
    if selective:
        index += 1
    if index >= len(lines):
        raise PoscarSyntaxError("POSCAR coordinate mode is required")
    coordinate_mode = _mode(lines[index])
    coordinates, flags, index = _parse_coordinates(
        lines, index + 1, sum(counts), selective
    )
    lattice_velocities, index = _parse_lattice_velocities(lines, index)
    velocity_mode, velocities = _parse_velocities(lines, index, sum(counts))

    diagnostics = []
    determinant = _determinant(lattice)
    if scale > 0:
        scale_factor = scale
    elif scale < 0 and determinant:
        scale_factor = (-scale / abs(determinant)) ** (1 / 3)
    else:
        scale_factor = 1.0
        diagnostics.append(
            ParserIssue(
                IssueKind.INVALID,
                "lattice" if scale < 0 else "scale",
                "POSCAR scale requires a non-zero scale and non-singular lattice",
            )
        )
    scaled_lattice = tuple(
        tuple(value * scale_factor for value in vector) for vector in lattice
    )
    if coordinate_mode == "cartesian":
        coordinates = tuple(
            tuple(value * scale_factor for value in coordinate)
            for coordinate in coordinates
        )
    return PoscarDocument(
        comment=comment,
        scale=scale,
        scale_factor=scale_factor,
        lattice=scaled_lattice,
        species=species,
        counts=counts,
        coordinate_mode=coordinate_mode,
        coordinates=coordinates,
        selective_dynamics=flags,
        lattice_velocities=lattice_velocities,
        velocity_mode=velocity_mode,
        velocities=velocities,
        diagnostics=tuple(diagnostics),
    )


def _sniff_truncated_prefix(prefix):
    try:
        lines = prefix.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as error:
        raise PoscarSyntaxError("POSCAR content must be UTF-8 text") from error
    if prefix[-1:] not in {b"\n", b"\r"}:
        lines = lines[:-1]
    if len(lines) < 9:
        raise PoscarSyntaxError("POSCAR prefix is missing header or coordinates")

    _numbers(lines[1], count=1, name="POSCAR scale")
    for line in lines[2:5]:
        _numbers(line, count=3, name="POSCAR lattice vector")
    labels = lines[5].split()
    if not labels:
        raise PoscarSyntaxError("POSCAR species or counts line is required")
    if all(_INTEGER.fullmatch(label) for label in labels):
        counts = _parse_counts(lines[5])
        index = 6
    else:
        counts = _parse_counts(lines[6])
        if len(labels) != len(counts):
            raise PoscarSyntaxError("POSCAR species and counts must have equal lengths")
        index = 7
    selective = lines[index].lstrip()[:1].lower() == "s"
    if selective:
        index += 1
    _mode(lines[index])
    available = min(sum(counts), len(lines) - index - 1)
    if available < 1:
        raise PoscarSyntaxError("POSCAR prefix has no complete coordinate row")
    _parse_coordinates(lines, index + 1, available, selective)


def sniff_poscar(source, prefix):
    source = Path(source)
    try:
        if len(prefix) < SNIFF_PREFIX_BYTES:
            parse_poscar_document(prefix)
        else:
            _sniff_truncated_prefix(prefix)
    except (PoscarSyntaxError, TypeError):
        return SniffResult(SniffMatch.NONE, "missing POSCAR lattice, counts, or coordinates")
    if source.name.upper() in {"POSCAR", "CONTCAR"}:
        return SniffResult(SniffMatch.EXACT, "valid canonical POSCAR/CONTCAR content")
    if source.suffix.lower() in _POSCAR_SUFFIXES:
        return SniffResult(SniffMatch.PROBABLE, "valid POSCAR content with VASP suffix")
    return SniffResult(SniffMatch.NONE, "POSCAR filename or VASP suffix is required")


def _species_assignment(document, species):
    if species is None:
        return document.species
    species = tuple(species)
    if document.species is not None:
        raise ValueError("species assignment is only valid for VASP 4 files")
    if len(species) != len(document.counts):
        raise ValueError("species assignment must match the POSCAR count groups")
    if any(type(value) is not str or value not in _ATOMIC_NUMBERS for value in species):
        raise ValueError("species assignment must contain recognized element symbols")
    return species


def _identity(source_hash, species, name):
    assignment = "" if species is None else ",".join(species)
    return uuid5(
        NAMESPACE_URL,
        f"chemblender:poscar:{_READER_VERSION}:{source_hash}:{assignment}:{name}",
    )


def _site_inventory(species, counts):
    atomic_numbers = []
    labels = []
    for symbol, count in zip(species, counts):
        atomic_numbers.extend((_ATOMIC_NUMBERS[symbol],) * count)
        labels.extend(f"{symbol}{index + 1}" for index in range(count))
    return tuple(atomic_numbers), tuple(labels)


def _periodic_site_data(document, labels, fractional):
    import numpy

    atom_count = len(labels)
    return PeriodicSiteData(
        fractional_coordinates=ArrayData(
            fractional,
            ("atom", "xyz"),
            "dimensionless",
        ),
        site_labels=labels,
        occupancies=ArrayData(
            numpy.ones(atom_count, dtype=numpy.float64),
            ("atom",),
            "dimensionless",
        ),
        isotropic_displacements=None,
        anisotropic_displacements=None,
        adp_types=("none",) * atom_count,
        disorder_groups=(0,) * atom_count,
        declared_space_group_name=None,
        declared_space_group_number=None,
        symmetry_operations=(),
        cif_envelope_id=None,
        pbc=(True, True, True),
    )


def _datasets(document, structure_id, provenance_id, source_hash, species):
    import numpy

    values = []
    if document.selective_dynamics is not None:
        values.append(
            AtomicProperty(
                id=_identity(source_hash, species, "selective-dynamics"),
                revision=f"{source_hash}:{','.join(species)}:selective-dynamics",
                semantic_role="selective_dynamics",
                domain="atom",
                data=ArrayData(
                    numpy.asarray(document.selective_dynamics, dtype=numpy.bool_),
                    ("atom", "xyz"),
                    "dimensionless",
                ),
                status=DatasetStatus.COMPLETE,
                source_calculation=None,
                provenance_ids=(provenance_id,),
                structure_id=structure_id,
            )
        )
    if document.velocities is not None:
        values.append(
            AtomicProperty(
                id=_identity(source_hash, species, "atomic-velocity"),
                revision=f"{source_hash}:{','.join(species)}:atomic-velocity",
                semantic_role="atomic_velocity",
                domain="atom",
                data=ArrayData(
                    numpy.asarray(document.velocities, dtype=numpy.float64),
                    ("atom", "xyz"),
                    "unknown",
                ),
                status=DatasetStatus.AMBIGUOUS,
                source_calculation=None,
                provenance_ids=(provenance_id,),
                structure_id=structure_id,
            )
        )
    if document.lattice_velocities is not None:
        values.append(
            PropertyDataset(
                id=_identity(source_hash, species, "lattice-velocity"),
                revision=f"{source_hash}:{','.join(species)}:lattice-velocity",
                semantic_role="lattice_velocity",
                domain="cell",
                data=ArrayData(
                    numpy.asarray(
                        document.lattice_velocities.velocities,
                        dtype=numpy.float64,
                    ),
                    ("cell_vector", "xyz"),
                    "unknown",
                ),
                status=DatasetStatus.AMBIGUOUS,
                source_calculation=None,
                provenance_ids=(provenance_id,),
            )
        )
    return tuple(values)


def _parse_poscar_bytes(raw, source, species=None):
    import numpy

    source_hash = hashlib.sha256(raw).hexdigest()
    document = parse_poscar_document(raw)
    species = _species_assignment(document, species)
    provenance_id = _identity(source_hash, species, "provenance")
    issues = list(document.diagnostics)
    structures = ()
    datasets = ()
    invalid = any(issue.kind is IssueKind.INVALID for issue in issues)
    if species is None:
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                "poscar.species",
                "VASP 4 count groups require an explicit ordered species assignment",
            )
        )
    elif not invalid:
        if any(symbol not in _ATOMIC_NUMBERS for symbol in species):
            raise ValueError("POSCAR species must contain recognized element symbols")
        atomic_numbers, labels = _site_inventory(species, document.counts)
        cell = numpy.asarray(document.lattice, dtype=numpy.float64)
        if document.coordinate_mode == "direct":
            fractional = numpy.asarray(document.coordinates, dtype=numpy.float64)
            cartesian = fractional @ cell
        else:
            cartesian = numpy.asarray(document.coordinates, dtype=numpy.float64)
            fractional = cartesian @ numpy.linalg.inv(cell)
        structure_id = _identity(source_hash, species, "structure")
        structure = Structure(
            id=structure_id,
            revision=f"{source_hash}:{','.join(species)}",
            atomic_numbers=atomic_numbers,
            coordinates=ArrayData(
                cartesian,
                ("atom", "xyz"),
                "angstrom",
            ),
            cell=ArrayData(
                cell,
                ("cell_vector", "xyz"),
                "angstrom",
            ),
            periodic=_periodic_site_data(document, labels, fractional),
        )
        structures = (structure,)
        datasets = _datasets(
            document,
            structure_id,
            provenance_id,
            source_hash,
            species,
        )

    lattice_velocity = document.lattice_velocities
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=(
            f"{source_hash}:{','.join(species)}"
            if species is not None
            else f"{source_hash}:unassigned"
        ),
        producer="ChemBlender POSCAR adapter",
        producer_version=_READER_VERSION,
        source=str(Path(source).resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=(
            ("format", "poscar"),
            ("comment", document.comment),
            ("scale", document.scale),
            ("scale_factor", document.scale_factor),
            ("coordinate_mode", document.coordinate_mode),
            ("species_order", document.species),
            ("species_assignment", species if document.species is None else None),
            ("counts", document.counts),
            ("selective_dynamics", document.selective_dynamics is not None),
            ("velocity_mode", document.velocity_mode),
            ("lattice_velocity_initialization_state", (
                None if lattice_velocity is None
                else lattice_velocity.initialization_state
            )),
            ("lattice_velocity_vectors", (
                None if lattice_velocity is None
                else lattice_velocity.lattice_vectors
            )),
        ),
    )
    created_ids = tuple(
        [value.id for value in structures]
        + [value.id for value in datasets]
        + [provenance_id]
    )
    report = ParserReport(
        reader_id="poscar",
        reader_version=_READER_VERSION,
        created_entity_ids=created_ids,
        parsed_capabilities=(
            ("structure", "crystal", "atomic_property")
            if structures
            else ("crystal",)
        ),
        issues=tuple(issues),
    )
    return ImportBatch(
        structures=structures,
        datasets=datasets,
        provenance=(provenance,),
        report=report,
    )


def parse_poscar(source, *, species=None):
    source = Path(source)
    return _parse_poscar_bytes(source.read_bytes(), source, species)


def parse_poscar_request(request):
    parameters = dict(request.canonical_parameters)
    if parameters.keys() - {"species"}:
        raise ValueError("unsupported POSCAR parse parameter")
    cancelled = request.is_cancelled()
    if type(cancelled) is not bool:
        raise TypeError("is_cancelled must return bool")
    if cancelled:
        raise RuntimeError("POSCAR parse was cancelled")
    raw = Path(request.source_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != request.source_content_hash:
        raise ValueError("POSCAR source content hash does not match ParseRequest")
    species = parameters.get("species")
    assignment = (
        None
        if species is None
        else tuple(value.strip() for value in species.split(","))
    )
    if assignment is not None and any(not value for value in assignment):
        raise ValueError("species parameter must be comma-separated element symbols")
    return _parse_poscar_bytes(raw, request.source_path, assignment)


POSCAR_READER = ReaderDescriptor(
    reader_id="poscar",
    reader_version=_READER_VERSION,
    extensions=(".vasp", ".poscar", ".contcar"),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "crystal": CapabilitySupport.SUPPORTED,
        "atomic_property": CapabilitySupport.SUPPORTED,
    },
    priority=120,
    sniff=sniff_poscar,
    parse=parse_poscar,
    parse_request=parse_poscar_request,
)


__all__ = (
    "POSCAR_READER",
    "PoscarDocument",
    "PoscarLatticeVelocityBlock",
    "PoscarSyntaxError",
    "parse_poscar",
    "parse_poscar_document",
    "parse_poscar_request",
    "sniff_poscar",
)
