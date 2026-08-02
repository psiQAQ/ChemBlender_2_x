"""Deterministic native Cube export from authoritative core entities."""

from dataclasses import dataclass

import numpy

from ..model import AtomicProperty, Grid3D, ProvenanceRecord
from .cube_readiness import CubeExportStatus, _entities, cube_export_readiness
from .xyz import (
    ExportCancelled,
    ExportReport,
    ExportReportEntry,
    _cancelled,
    atomic_write_chunks,
)


BOHR_TO_ANGSTROM = 0.529177210903
_COMMENTS = (
    "ChemBlender deterministic Cube export",
    "selected scalar dataset",
)
_LOSS_MESSAGES = {
    "dataset_id_normalized": "Cube dataset ID is normalized to selected index plus one",
    "dataset_id_omitted": "Malformed scalar Cube dataset ID is omitted",
}


@dataclass(frozen=True, slots=True)
class CubeExport:
    text: str
    report: ExportReport


def _ready(project_entities, dataset_index):
    readiness = cube_export_readiness(
        project_entities,
        dataset_index=dataset_index,
    )
    if readiness.status is not CubeExportStatus.READY:
        raise ValueError(
            f"Cube export is {readiness.status.value}: "
            + ", ".join(readiness.tokens)
        )


def _projection(project_entities):
    datasets = _entities(project_entities, "datasets")
    grid = next(value for value in datasets if isinstance(value, Grid3D))
    structure = next(
        value
        for value in _entities(project_entities, "structures")
        if value.id == grid.structure_id
    )
    charge = next(
        value
        for value in datasets
        if isinstance(value, AtomicProperty)
        and value.structure_id == structure.id
        and value.semantic_role == "nuclear_charge"
    )
    return structure, grid, charge


def _trusted_dataset_ids(project_entities, grid):
    provenance = _entities(project_entities, "provenance")
    direct = tuple(
        value
        for value in provenance
        if isinstance(value, ProvenanceRecord) and value.id in grid.provenance_ids
    )
    if len(direct) != 1:
        return None, bool(grid.provenance_ids)
    record = direct[0]
    if record.operation != "parse":
        return None, False
    pairs = tuple(record.parameters)
    if len({key for key, _value in pairs}) != len(pairs):
        return None, True
    parameters = dict(pairs)
    if parameters.get("format") != "cube":
        return None, False
    expected_count = 1 if grid.data.dims == ("x", "y", "z") else grid.data.shape[0]
    dataset_count = parameters.get("dataset_count")
    if type(dataset_count) is not int or dataset_count != expected_count:
        return None, True
    if "dataset_ids" not in parameters:
        return None, False
    identifiers = parameters["dataset_ids"]
    if (
        not isinstance(identifiers, tuple)
        or len(identifiers) != expected_count
        or any(type(value) is not int or value < 0 for value in identifiers)
    ):
        return None, True
    return identifiers, False


def _dataset_identifier(project_entities, grid, dataset_index):
    identifiers, malformed = _trusted_dataset_ids(project_entities, grid)
    scalar = grid.data.dims == ("x", "y", "z")
    if identifiers is not None:
        return identifiers[0 if scalar else dataset_index], ()
    if scalar:
        codes = ("dataset_id_omitted",) if malformed else ()
        return None, codes
    return dataset_index + 1, ("dataset_id_normalized",)


def _preview(project_entities, dataset_index):
    _ready(project_entities, dataset_index)
    _structure, grid, _charge = _projection(project_entities)
    _identifier, codes = _dataset_identifier(
        project_entities,
        grid,
        dataset_index,
    )
    entries = tuple(
        ExportReportEntry(code, _LOSS_MESSAGES[code]) for code in sorted(codes)
    )
    return ExportReport("cube", False, 1, bool(entries), entries)


def preview_cube_export(project_entities, *, dataset_index=None):
    return _preview(project_entities, dataset_index)


def _bohr(values, unit):
    values = numpy.asarray(values, dtype=float)
    return values if unit == "bohr" else values / BOHR_TO_ANGSTROM


def _number(value):
    value = float(value)
    return f"{0.0 if value == 0.0 else value:.12E}"


def _line(count, values):
    return f"{count:5d} " + " ".join(_number(value) for value in values) + "\n"


def _text_chunks(project_entities, dataset_index):
    structure, grid, charge = _projection(project_entities)
    identifier, _codes = _dataset_identifier(project_entities, grid, dataset_index)
    signed_atom_count = -len(structure.atomic_numbers) if identifier is not None else len(structure.atomic_numbers)
    chunks = [f"{_COMMENTS[0]}\n", f"{_COMMENTS[1]}\n"]
    chunks.append(_line(signed_atom_count, _bohr(grid.origin, grid.coordinate_unit)))
    for count, vector in zip(grid.grid_shape, grid.step_vectors, strict=True):
        chunks.append(_line(count, _bohr(vector, grid.coordinate_unit)))
    coordinates = _bohr(structure.coordinates.values, structure.coordinates.unit)
    charges = numpy.asarray(charge.data.values)
    for atomic_number, nuclear_charge, row in zip(
        structure.atomic_numbers,
        charges,
        coordinates,
        strict=True,
    ):
        chunks.append(_line(atomic_number, (nuclear_charge, *row)))
    if identifier is not None:
        chunks.append(f"{1:5d} {identifier:5d}\n")
    values = numpy.asarray(grid.data.values)
    selected = values if dataset_index is None else values[dataset_index]
    flat = selected.ravel(order="C")
    for offset in range(0, len(flat), 6):
        chunks.append(" ".join(_number(value) for value in flat[offset : offset + 6]) + "\n")
    return tuple(chunks)


def export_cube(
    project_entities,
    *,
    dataset_index=None,
    confirm_loss=False,
    destination=None,
    is_cancelled=None,
):
    if type(confirm_loss) is not bool:
        raise TypeError("confirm_loss must be bool")
    if _cancelled(is_cancelled):
        raise ExportCancelled("export cancelled")
    preview = _preview(project_entities, dataset_index)
    if preview.requires_confirmation and not confirm_loss:
        return CubeExport("", preview)
    chunks = _text_chunks(project_entities, dataset_index)
    text = "".join(chunks)
    if destination is not None:
        atomic_write_chunks(destination, chunks, is_cancelled=is_cancelled)
    return CubeExport(
        text,
        ExportReport(
            "cube",
            destination is not None,
            1,
            preview.requires_confirmation,
            preview.entries,
        ),
    )


__all__ = (
    "CubeExport",
    "export_cube",
    "preview_cube_export",
)
