"""Deterministic normalized PQR export from authoritative core entities."""

import math
from dataclasses import replace
from types import SimpleNamespace

import numpy

from ..formats.pdb import _ELEMENT_NUMBERS
from ..formats.pqr import _infer_pqr_element
from ..model import ArrayData, AtomicProperty, DatasetStatus
from .pdb_readiness import (
    PDBPQRExportStatus,
    _categorical_values,
    _entities,
    pqr_export_readiness,
)
from .rdkit_molecular import MolecularExport, _values
from .xyz import (
    ExportCancelled,
    ExportReport,
    ExportReportEntry,
    _cancelled,
    atomic_write_chunks,
)


_LOSS_MESSAGES = {
    "atom_map_numbers_omitted": "atom-map numbers are omitted",
    "atom_serials_renumbered": "source atom serials are normalized to 1..N",
    "atom_stereo_omitted": "atom stereo labels are omitted",
    "cell_omitted": "PQR periodic-cell data is omitted",
    "chain_segment_indices_omitted": "chain segment indices are omitted",
    "formal_charge_omitted": "PQR formal charges are omitted",
    "isotopes_omitted": "isotope labels are omitted",
    "model_number_omitted": "biological model number is omitted",
    "molecular_charge_omitted": "molecular total charge is omitted",
    "molecular_multiplicity_omitted": "molecular spin multiplicity is omitted",
    "topology_omitted": "PQR topology data is omitted",
}


def _snapshot_array(
    data,
    live_arrays,
    *,
    expected_dims=None,
    expected_shape=None,
    invalid_token=None,
):
    live = data.values
    unloaded = getattr(live, "loaded", None) is False
    try:
        values = numpy.array(live, copy=True, order="C", subok=False)
        if invalid_token is not None and (
            data.dims != expected_dims or values.shape != expected_shape
        ):
            raise ValueError(f"PQR export is Invalid: {invalid_token}")
        values.setflags(write=False)
        live_arrays.append((live, values))
        return replace(data, values=values)
    finally:
        if unloaded:
            live.close()


def _snapshot_categorical(data, live_arrays, *, expected_shape, invalid_token):
    return replace(
        data,
        codes=_snapshot_array(
            data.codes,
            live_arrays,
            expected_dims=("atom",),
            expected_shape=expected_shape,
            invalid_token=invalid_token,
        ),
    )


def _snapshot_structure(structure, live_arrays):
    atom_shape = (len(structure.atomic_numbers),)
    identity = structure.atomic_identity
    identity = None if identity is None else replace(
        identity,
        isotopes=_snapshot_array(
            identity.isotopes,
            live_arrays,
            expected_dims=("atom",),
            expected_shape=atom_shape,
            invalid_token="identity.isotopes.invalid",
        ),
        formal_charges=_snapshot_array(
            identity.formal_charges,
            live_arrays,
            expected_dims=("atom",),
            expected_shape=atom_shape,
            invalid_token="identity.formal_charges.invalid",
        ),
        atom_map_numbers=_snapshot_array(
            identity.atom_map_numbers,
            live_arrays,
            expected_dims=("atom",),
            expected_shape=atom_shape,
            invalid_token="identity.atom_map_numbers.invalid",
        ),
        atom_names=_snapshot_categorical(
            identity.atom_names,
            live_arrays,
            expected_shape=atom_shape,
            invalid_token="identity.atom_name.invalid",
        ),
        stereo_labels=_snapshot_categorical(
            identity.stereo_labels,
            live_arrays,
            expected_shape=atom_shape,
            invalid_token="identity.atom_stereo.invalid",
        ),
    )
    return replace(
        structure,
        coordinates=_snapshot_array(
            structure.coordinates,
            live_arrays,
            expected_dims=("atom", "xyz"),
            expected_shape=(len(structure.atomic_numbers), 3),
            invalid_token="coordinates.shape",
        ),
        atomic_identity=identity,
    )


def _snapshot_hierarchy(hierarchy, live_arrays):
    sites = hierarchy.atom_sites
    atom_shape = (sites.atom_count,)
    return replace(
        hierarchy,
        atom_sites=replace(
            sites,
            serial_numbers=_snapshot_array(
                sites.serial_numbers,
                live_arrays,
                expected_dims=("atom",),
                expected_shape=atom_shape,
                invalid_token="hierarchy.shape",
            ),
            residue_indices=_snapshot_array(
                sites.residue_indices,
                live_arrays,
                expected_dims=("atom",),
                expected_shape=atom_shape,
                invalid_token="hierarchy.shape",
            ),
            alternate_locations=_snapshot_categorical(
                sites.alternate_locations,
                live_arrays,
                expected_shape=atom_shape,
                invalid_token="identity.altloc.invalid",
            ),
            record_kinds=_snapshot_categorical(
                sites.record_kinds,
                live_arrays,
                expected_shape=atom_shape,
                invalid_token="identity.record_kind",
            ),
        ),
    )


def _snapshot_dataset(dataset, live_arrays):
    if not isinstance(dataset, AtomicProperty) or dataset.semantic_role not in {
        "partial_charge",
        "radius",
    }:
        return dataset
    return replace(
        dataset,
        data=_snapshot_array(
            dataset.data,
            live_arrays,
            expected_dims=("atom",),
            expected_shape=dataset.data.shape,
            invalid_token=f"dataset.{dataset.semantic_role}.shape",
        ),
    )


def _snapshot(project_entities):
    structures = _entities(project_entities, "structures")
    hierarchies = _entities(project_entities, "biological_hierarchies")
    datasets = _entities(project_entities, "datasets")
    topologies = _entities(project_entities, "topologies")
    live_arrays = []
    return SimpleNamespace(
        structures=tuple(
            _snapshot_structure(value, live_arrays) for value in structures
        ),
        biological_hierarchies=tuple(
            _snapshot_hierarchy(value, live_arrays) for value in hierarchies
        ),
        datasets=tuple(
            _snapshot_dataset(value, live_arrays) for value in datasets
        ),
        topologies=topologies,
        live_arrays=tuple(live_arrays),
    )


def _assert_snapshot_unchanged(snapshot):
    for live, captured in snapshot.live_arrays:
        unloaded = getattr(live, "loaded", None) is False
        try:
            current = numpy.asarray(live)
            equal = (
                numpy.array_equal(current, captured, equal_nan=True)
                if current.dtype.kind in "fc"
                else numpy.array_equal(current, captured)
            )
            unchanged = (
                current.shape == captured.shape
                and current.dtype == captured.dtype
                and equal
            )
        except (TypeError, ValueError):
            unchanged = False
        finally:
            if unloaded:
                live.close()
        if not unchanged:
            raise ValueError("PQR export inputs changed after snapshot")


def _one(values):
    values = tuple(values)
    return values[0] if len(values) == 1 else None


def _ready(project_entities):
    readiness = pqr_export_readiness(project_entities)
    if readiness.status not in {
        PDBPQRExportStatus.READY,
        PDBPQRExportStatus.READY_WITH_RENUMBERING,
    }:
        raise ValueError(
            f"PQR export is {readiness.status.value}: "
            + ", ".join(readiness.tokens)
        )
    return readiness


def _label(value, name, maximum, *, required=True):
    if value in (None, "") and not required:
        return ""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not value.isascii()
        or any(not 33 <= ord(character) <= 126 for character in value)
    ):
        raise ValueError(f"PQR {name} is invalid")
    return value


def _number(value, width, precision, name, *, positive=False):
    number = float(value)
    if not math.isfinite(number) or positive and number <= 0.0:
        raise ValueError(f"PQR {name} is invalid")
    if len(f"{number:{width}.{precision}f}") > width:
        raise ValueError(f"PQR {name} overflows")
    return f"{0.0 if number == 0.0 else number:.{precision}f}"


def _projection(project_entities):
    readiness = _ready(project_entities)
    structure = _one(project_entities.structures)
    hierarchy = _one(
        value
        for value in project_entities.biological_hierarchies
        if value.structure_id == structure.id
    )

    def property_value(role):
        return _one(
            value
            for value in project_entities.datasets
            if isinstance(value, AtomicProperty)
            and value.structure_id == structure.id
            and value.semantic_role == role
        )

    charge = property_value("partial_charge")
    radius = property_value("radius")
    atom_count = len(structure.atomic_numbers)
    if (
        hierarchy is None
        or hierarchy.atom_count != atom_count
        or not isinstance(structure.coordinates, ArrayData)
        or structure.coordinates.dims != ("atom", "xyz")
        or structure.coordinates.shape != (atom_count, 3)
        or structure.coordinates.unit != "angstrom"
        or numpy.dtype(structure.coordinates.dtype).kind not in "iuf"
    ):
        raise ValueError("PQR export inputs changed after readiness validation")
    for value, role, unit in (
        (charge, "partial_charge", "elementary_charge"),
        (radius, "radius", "angstrom"),
    ):
        if (
            not isinstance(value, AtomicProperty)
            or value.structure_id != structure.id
            or value.semantic_role != role
            or value.domain != "atom"
            or value.status is not DatasetStatus.COMPLETE
            or not isinstance(value.data, ArrayData)
            or value.data.dims != ("atom",)
            or value.data.shape != (atom_count,)
            or value.data.unit != unit
            or numpy.dtype(value.data.dtype).kind not in "iuf"
        ):
            raise ValueError(f"PQR {role} property is invalid")
    coordinates = _values(structure.coordinates)
    charges = _values(charge.data)
    radii = _values(radius.data)
    serials = _values(hierarchy.atom_sites.serial_numbers)
    residue_indices = _values(hierarchy.atom_sites.residue_indices)
    atom_names = _categorical_values(
        structure.atomic_identity.atom_names,
        atom_count,
        allow_missing=False,
    )
    record_kinds = _categorical_values(
        hierarchy.atom_sites.record_kinds,
        atom_count,
        allow_missing=False,
    )
    if (
        coordinates.shape != (atom_count, 3)
        or charges.shape != (atom_count,)
        or radii.shape != (atom_count,)
        or serials.shape != (atom_count,)
        or residue_indices.shape != (atom_count,)
        or atom_names is None
        or record_kinds is None
    ):
        raise ValueError("PQR export inputs changed after readiness validation")
    if any(array.dtype.kind not in "iuf" for array in (coordinates, charges, radii)):
        raise ValueError("PQR numeric values are invalid")
    if not (
        numpy.all(numpy.isfinite(coordinates))
        and numpy.all(numpy.isfinite(charges))
        and numpy.all(numpy.isfinite(radii))
        and numpy.all(radii > 0.0)
    ):
        raise ValueError("PQR numeric values are invalid")
    preserve_serials = readiness.status is PDBPQRExportStatus.READY
    rows = []
    native_residue_names = {}
    for index in range(atom_count):
        residue_index = int(residue_indices[index])
        if not 0 <= residue_index < len(hierarchy.residues):
            raise ValueError("PQR residue index is invalid")
        residue = hierarchy.residues[residue_index]
        if not 0 <= residue.chain_index < len(hierarchy.chains):
            raise ValueError("PQR residue chain index is invalid")
        chain = hierarchy.chains[residue.chain_index]
        kind = record_kinds[index]
        if kind not in {"atom", "hetatm"}:
            raise ValueError("PQR record kind is invalid")
        if residue.hetero != (kind == "hetatm"):
            raise ValueError("PQR hierarchy.residue_kind.mismatch")
        atom_name = _label(atom_names[index], "atom name", 4)
        residue_name = _label(residue.residue_name, "residue name", 3)
        chain_id = _label(chain.chain_id, "chain ID", 1, required=False)
        insertion_code = _label(
            residue.insertion_code,
            "insertion code",
            1,
            required=False,
        )
        residue_id = f"{residue.sequence_number}{insertion_code}"
        _label(residue_id, "residue number", 5)
        native_residue_key = (
            chain_id,
            residue.sequence_number,
            insertion_code,
            residue.hetero,
        )
        previous_name = native_residue_names.setdefault(
            native_residue_key,
            residue_name,
        )
        if previous_name != residue_name:
            raise ValueError("PQR hierarchy.residue_key.conflict")
        element = _infer_pqr_element(atom_name, kind.upper(), residue_name)
        if _ELEMENT_NUMBERS.get(element) != structure.atomic_numbers[index]:
            raise ValueError("PQR identity.element.mismatch")
        serial = int(serials[index]) if preserve_serials else index + 1
        if not 1 <= serial <= 99999:
            raise ValueError("PQR atom serial is invalid")
        x, y, z = coordinates[index]
        fields = [
            kind.upper(),
            str(serial),
            atom_name,
            residue_name,
        ]
        if chain_id:
            fields.append(chain_id)
        fields.extend(
            (
                residue_id,
                _number(x, 8, 3, "x coordinate"),
                _number(y, 8, 3, "y coordinate"),
                _number(z, 8, 3, "z coordinate"),
                _number(charges[index], 8, 4, "charge"),
                _number(radii[index], 7, 4, "radius", positive=True),
            )
        )
        line = " ".join(fields) + "\n"
        if not line.isascii():
            raise ValueError("PQR output must be ASCII")
        rows.append(line)
    return readiness, structure, hierarchy, tuple(rows)


def _loss_entries(project_entities, readiness, structure, hierarchy):
    codes = set()
    identity = structure.atomic_identity
    if readiness.status is PDBPQRExportStatus.READY_WITH_RENUMBERING:
        codes.add("atom_serials_renumbered")
    for topology_id in structure.topology_ids:
        matches = tuple(
            value
            for value in project_entities.topologies
            if getattr(value, "id", None) == topology_id
        )
        if (
            len(matches) != 1
            or getattr(matches[0], "structure_id", None) != structure.id
        ):
            raise ValueError("PQR topology.reference.invalid")
    if structure.topology is not None or any(
        getattr(value, "structure_id", None) == structure.id
        for value in project_entities.topologies
    ):
        codes.add("topology_omitted")
    if structure.topology_ids:
        codes.add("topology_omitted")
    if hierarchy.model.number is not None:
        codes.add("model_number_omitted")
    if any(chain.segment_index != 0 for chain in hierarchy.chains):
        codes.add("chain_segment_indices_omitted")
    if structure.cell is not None or structure.periodic is not None:
        codes.add("cell_omitted")
    if structure.molecular_charge is not None:
        codes.add("molecular_charge_omitted")
    if structure.molecular_multiplicity is not None:
        codes.add("molecular_multiplicity_omitted")
    if numpy.any(_values(identity.isotopes) != 0):
        codes.add("isotopes_omitted")
    if numpy.any(_values(identity.formal_charges) != 0):
        codes.add("formal_charge_omitted")
    if numpy.any(_values(identity.atom_map_numbers) != 0):
        codes.add("atom_map_numbers_omitted")
    stereo = _categorical_values(
        identity.stereo_labels,
        len(structure.atomic_numbers),
        allow_missing=True,
    )
    if stereo is None:
        raise ValueError("PQR atom stereo labels are invalid")
    if any(value not in (None, "") for value in stereo):
        codes.add("atom_stereo_omitted")
    return tuple(
        ExportReportEntry(code, _LOSS_MESSAGES[code]) for code in sorted(codes)
    )


def preview_pqr_export(project_entities):
    snapshot = _snapshot(project_entities)
    report, _rows = _prepare(snapshot)
    _assert_snapshot_unchanged(snapshot)
    return report


def _prepare(snapshot):
    readiness, structure, hierarchy, rows = _projection(snapshot)
    losses = _loss_entries(snapshot, readiness, structure, hierarchy)
    return ExportReport("pqr", False, 1, bool(losses), losses), rows


def _chunks(rows, is_cancelled):
    chunks = []
    for row in rows:
        if _cancelled(is_cancelled):
            raise ExportCancelled("export cancelled")
        chunks.append(row)
    return tuple(chunks)


def export_pqr(
    project_entities,
    *,
    confirm_loss=False,
    destination=None,
    is_cancelled=None,
):
    if type(confirm_loss) is not bool:
        raise TypeError("confirm_loss must be bool")
    if _cancelled(is_cancelled):
        raise ExportCancelled("export cancelled")
    snapshot = _snapshot(project_entities)
    preview, rows = _prepare(snapshot)
    _assert_snapshot_unchanged(snapshot)
    if preview.requires_confirmation and not confirm_loss:
        return MolecularExport("", preview)
    chunks = _chunks(rows, is_cancelled)
    _assert_snapshot_unchanged(snapshot)
    text = "".join(chunks)
    if destination is not None:
        def guarded_cancelled():
            cancelled = False if is_cancelled is None else is_cancelled()
            _assert_snapshot_unchanged(snapshot)
            return cancelled

        atomic_write_chunks(
            destination,
            chunks,
            is_cancelled=guarded_cancelled,
        )
    return MolecularExport(
        text,
        ExportReport(
            "pqr",
            destination is not None,
            preview.frame_count,
            preview.requires_confirmation,
            preview.entries,
        ),
    )


__all__ = ("export_pqr", "preview_pqr_export")
