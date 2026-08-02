"""Deterministic native Cube export from authoritative core entities."""

from dataclasses import dataclass, replace
from types import SimpleNamespace

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
    "atomic_identity_omitted": "Cube omits project atomic-identity metadata",
    "cell_periodicity_omitted": "Cube omits Structure cell and periodic metadata",
    "comments_normalized": "Cube source comments are replaced by deterministic comments",
    "dataset_id_normalized": "Cube dataset ID is normalized to selected index plus one",
    "dataset_id_omitted": "Malformed scalar Cube dataset ID is omitted",
    "grid_semantic_role_omitted": "Cube does not preserve the Grid3D semantic role",
    "grid_value_unit_omitted": "Cube does not preserve the Grid3D value unit",
    "molecular_charge_omitted": "Cube omits molecular total charge",
    "molecular_multiplicity_omitted": "Cube omits molecular spin multiplicity",
    "project_identity_omitted": "Cube omits project UUID and revision identity",
    "provenance_omitted": "Cube omits project provenance identity",
    "topology_omitted": "Cube omits molecular topology",
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


def _optional_entities(project_entities, name):
    return _entities(project_entities, name) if hasattr(project_entities, name) else ()


def _close_after_read(live, unloaded, primary):
    if not unloaded:
        return
    try:
        live.close()
    except BaseException as close_error:
        if primary is None:
            raise
        primary.add_note(f"lazy Cube export array close failed: {close_error}")


def _snapshot_array(data, live_arrays, *, selection=None, expected_shape, token):
    live = data.values
    unloaded = getattr(live, "loaded", None) is False
    primary = None
    try:
        source = numpy.asarray(live)
        selected = source if selection is None else source[selection]
        values = numpy.array(selected, copy=True, order="C", subok=False)
        if (
            values.shape != expected_shape
            or values.dtype != numpy.dtype(data.dtype)
        ):
            raise ValueError(f"Cube export is Invalid: {token}")
        values.setflags(write=False)
        live_arrays.append((live, values, selection))
        return values
    except BaseException as error:
        primary = error
        raise
    finally:
        _close_after_read(live, unloaded, primary)


def _snapshot(project_entities, dataset_index):
    structures = _entities(project_entities, "structures")
    datasets = _entities(project_entities, "datasets")
    provenance = _optional_entities(project_entities, "provenance")
    topologies = _optional_entities(project_entities, "topologies")
    raw = SimpleNamespace(
        structures=structures,
        datasets=datasets,
        provenance=provenance,
        topologies=topologies,
    )
    grids = tuple(value for value in datasets if isinstance(value, Grid3D))
    if len(grids) != 1:
        _ready(raw, dataset_index)
    grid = grids[0]
    linked = tuple(value for value in structures if value.id == grid.structure_id)
    charges = tuple(
        value
        for value in datasets
        if isinstance(value, AtomicProperty)
        and value.structure_id == grid.structure_id
        and value.semantic_role == "nuclear_charge"
    )
    if len(linked) != 1 or len(charges) != 1:
        _ready(raw, dataset_index)
    structure = linked[0]
    charge = charges[0]
    scalar = grid.data.dims == ("x", "y", "z")
    multi = grid.data.dims == ("dataset", "x", "y", "z")
    if (
        (scalar and dataset_index is not None)
        or (multi and (
            type(dataset_index) is not int
            or not 0 <= dataset_index < grid.data.shape[0]
        ))
        or not (scalar or multi)
    ):
        _ready(raw, dataset_index)

    live_arrays = []
    coordinates = _snapshot_array(
        structure.coordinates,
        live_arrays,
        expected_shape=(len(structure.atomic_numbers), 3),
        token="structure.coordinates",
    )
    charges_snapshot = _snapshot_array(
        charge.data,
        live_arrays,
        expected_shape=(len(structure.atomic_numbers),),
        token="dataset.nuclear_charge",
    )
    selected = _snapshot_array(
        grid.data,
        live_arrays,
        selection=None if scalar else dataset_index,
        expected_shape=grid.grid_shape,
        token="grid.data",
    )
    structure_snapshot = replace(
        structure,
        coordinates=replace(structure.coordinates, values=coordinates),
    )
    charge_snapshot = replace(
        charge,
        data=replace(charge.data, values=charges_snapshot),
    )
    grid_values = selected if scalar else numpy.broadcast_to(selected, grid.data.shape)
    grid_snapshot = replace(
        grid,
        data=replace(grid.data, values=grid_values),
    )
    projected_datasets = tuple(
        grid_snapshot
        if value is grid
        else charge_snapshot
        if value is charge
        else value
        for value in datasets
    )
    entities = SimpleNamespace(
        structures=tuple(
            structure_snapshot if value is structure else value for value in structures
        ),
        datasets=projected_datasets,
        provenance=provenance,
        topologies=topologies,
    )
    _ready(entities, dataset_index)
    return SimpleNamespace(
        entities=entities,
        structure=structure_snapshot,
        grid=grid_snapshot,
        charge=charge_snapshot,
        selected_values=selected,
        live_arrays=tuple(live_arrays),
    )


def _assert_snapshot_unchanged(snapshot):
    for live, captured, selection in snapshot.live_arrays:
        unloaded = getattr(live, "loaded", None) is False
        primary = None
        try:
            try:
                current = numpy.asarray(live)
                current = current if selection is None else current[selection]
                unchanged = (
                    current.shape == captured.shape
                    and current.dtype == captured.dtype
                    and numpy.array_equal(current, captured, equal_nan=True)
                )
            except (TypeError, ValueError):
                unchanged = False
            if not unchanged:
                raise ValueError("Cube export inputs changed after snapshot")
        except BaseException as error:
            primary = error
            raise
        finally:
            _close_after_read(live, unloaded, primary)


def _trusted_dataset_ids(project_entities, grid):
    if len(grid.provenance_ids) != 1:
        return None, bool(grid.provenance_ids)
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


def _source_comments(project_entities, grid):
    direct = tuple(
        value
        for value in _optional_entities(project_entities, "provenance")
        if isinstance(value, ProvenanceRecord) and value.id in grid.provenance_ids
    )
    return any(
        any(key in {"comment_1", "comment_2"} for key, _value in record.parameters)
        for record in direct
    )


def _loss_codes(project_entities, structure, grid, charge):
    codes = {
        "grid_semantic_role_omitted",
        "grid_value_unit_omitted",
        "project_identity_omitted",
    }
    if _source_comments(project_entities, grid):
        codes.add("comments_normalized")
    if (
        grid.provenance_ids
        or charge.provenance_ids
        or grid.source_calculation is not None
        or charge.source_calculation is not None
        or _optional_entities(project_entities, "provenance")
    ):
        codes.add("provenance_omitted")
    if structure.cell is not None or structure.periodic is not None:
        codes.add("cell_periodicity_omitted")
    if structure.molecular_charge is not None:
        codes.add("molecular_charge_omitted")
    if structure.molecular_multiplicity is not None:
        codes.add("molecular_multiplicity_omitted")
    if (
        structure.topology is not None
        or structure.topology_ids
        or any(
            getattr(value, "structure_id", None) == structure.id
            for value in _optional_entities(project_entities, "topologies")
        )
    ):
        codes.add("topology_omitted")
    if structure.atomic_identity is not None:
        codes.add("atomic_identity_omitted")
    return codes


def _prepare(snapshot, dataset_index):
    project_entities = snapshot.entities
    structure = snapshot.structure
    grid = snapshot.grid
    charge = snapshot.charge
    _identifier, codes = _dataset_identifier(
        project_entities,
        grid,
        dataset_index,
    )
    codes = set(codes) | _loss_codes(project_entities, structure, grid, charge)
    entries = tuple(
        ExportReportEntry(code, _LOSS_MESSAGES[code]) for code in sorted(codes)
    )
    return ExportReport("cube", False, 1, bool(entries), entries), _identifier


def preview_cube_export(project_entities, *, dataset_index=None):
    snapshot = _snapshot(project_entities, dataset_index)
    report, _identifier = _prepare(snapshot, dataset_index)
    _assert_snapshot_unchanged(snapshot)
    return report


def _bohr(values, unit):
    values = numpy.asarray(values, dtype=float)
    return values if unit == "bohr" else values / BOHR_TO_ANGSTROM


def _number(value):
    value = float(value)
    return f"{0.0 if value == 0.0 else value:.16E}"


def _line(count, values):
    return f"{count:5d} " + " ".join(_number(value) for value in values) + "\n"


def _text_chunks(snapshot, identifier, *, is_cancelled=None, collected=None):
    structure = snapshot.structure
    grid = snapshot.grid
    charge = snapshot.charge
    signed_atom_count = -len(structure.atomic_numbers) if identifier is not None else len(structure.atomic_numbers)

    def emit(chunk):
        if _cancelled(is_cancelled):
            raise ExportCancelled("export cancelled")
        if collected is not None:
            collected.append(chunk)
        return chunk

    yield emit(f"{_COMMENTS[0]}\n")
    yield emit(f"{_COMMENTS[1]}\n")
    yield emit(_line(signed_atom_count, _bohr(grid.origin, grid.coordinate_unit)))
    for count, vector in zip(grid.grid_shape, grid.step_vectors, strict=True):
        yield emit(_line(count, _bohr(vector, grid.coordinate_unit)))
    coordinates = _bohr(structure.coordinates.values, structure.coordinates.unit)
    charges = numpy.asarray(charge.data.values)
    for atomic_number, nuclear_charge, row in zip(
        structure.atomic_numbers,
        charges,
        coordinates,
        strict=True,
    ):
        yield emit(_line(atomic_number, (nuclear_charge, *row)))
    if identifier is not None:
        yield emit(f"{1:5d} {identifier:5d}\n")
    flat = snapshot.selected_values.ravel(order="C")
    for offset in range(0, len(flat), 6):
        yield emit(" ".join(_number(value) for value in flat[offset : offset + 6]) + "\n")


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
    snapshot = _snapshot(project_entities, dataset_index)
    preview, identifier = _prepare(snapshot, dataset_index)
    if preview.requires_confirmation and not confirm_loss:
        _assert_snapshot_unchanged(snapshot)
        return CubeExport("", preview)
    collected = []
    if destination is not None:
        complete = False

        def chunks():
            nonlocal complete
            yield from _text_chunks(snapshot, identifier, collected=collected)
            complete = True

        def guarded_cancelled():
            cancelled = _cancelled(is_cancelled)
            if complete:
                _assert_snapshot_unchanged(snapshot)
            return cancelled

        atomic_write_chunks(
            destination,
            chunks(),
            is_cancelled=guarded_cancelled,
        )
    else:
        collected.extend(
            _text_chunks(
                snapshot,
                identifier,
                is_cancelled=is_cancelled,
            )
        )
        _assert_snapshot_unchanged(snapshot)
    text = "".join(collected)
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
