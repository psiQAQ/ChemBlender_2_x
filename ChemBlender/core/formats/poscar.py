"""Dependency-free POSCAR/CONTCAR syntax parsing."""

from dataclasses import dataclass
import math
from pathlib import Path
import re

from ..model import IssueKind, ParserIssue
from ..readers import SNIFF_PREFIX_BYTES, SniffMatch, SniffResult


_INTEGER = re.compile(r"[+-]?[0-9]+\Z")
_POSCAR_SUFFIXES = frozenset((".vasp", ".poscar", ".contcar"))


class PoscarSyntaxError(ValueError):
    """Stable syntax failure for a POSCAR or CONTCAR document."""


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
    marker = lines[start].lstrip()[:1].lower()
    mode = "cartesian" if not marker or marker in {"c", "k"} else "direct"
    rows = lines[start + 1 :]
    if len(rows) != count:
        raise PoscarSyntaxError("POSCAR velocity block must contain one row per atom")
    return mode, tuple(
        _numbers(line, count=3, name="POSCAR velocity rows") for line in rows
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


__all__ = ("PoscarDocument", "PoscarSyntaxError", "parse_poscar_document", "sniff_poscar")
