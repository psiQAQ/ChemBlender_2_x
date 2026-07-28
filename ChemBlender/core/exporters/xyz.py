"""Deterministic XYZ and extXYZ export."""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path

from ...Chem_data import ELEMENTS_DEFAULT
from ..formats.extxyz import (
    _RESERVED_COMMENT_KEYS,
    _token,
    parse_extxyz_comment,
)
from ..model import (
    AtomFrameProperty,
    CategoricalData,
    CellFrameProperty,
    DatasetStatus,
    FrameProperty,
    FrameSet,
    ImportBatch,
    Structure,
)
from ..storage.atomic_paths import short_sibling_temporary_path


_SYMBOLS = {
    data[0]: symbol
    for symbol, data in ELEMENTS_DEFAULT.items()
    if data[0] > 0
}
_ATOM_ROLE_NAMES = {
    "atomic_force": ("force", 0, "electron_volt_per_angstrom"),
    "atomic_velocity": ("vel", 1, "angstrom_per_femtosecond"),
    "atomic_charge": ("charge", 2, "elementary_charge"),
    "atomic_mass": ("mass", 3, "atomic_mass_unit"),
}
_FRAME_ROLE_RANK = {
    "energy": 0,
    "free_energy": 1,
    "step": 2,
    "temperature": 3,
    "time": 4,
}
_FRAME_ROLE_UNITS = {
    "energy": "electron_volt",
    "free_energy": "electron_volt",
    "step": "dimensionless",
    "temperature": "kelvin",
    "time": "femtosecond",
}
_FRAME_SOURCE_KEYS = {
    "stress_voigt": "stress",
    "stress_matrix": "stress",
    "virial_voigt": "virial",
    "virial_matrix": "virial",
}


@dataclass(frozen=True, slots=True)
class ExportReportEntry:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ExportReport:
    format: str
    written: bool
    frame_count: int
    requires_confirmation: bool
    entries: tuple[ExportReportEntry, ...] = ()
    missing_value_token: str | None = None


class ExportCancelled(RuntimeError):
    pass


def _cancelled(is_cancelled):
    if is_cancelled is None:
        return False
    if not callable(is_cancelled):
        raise TypeError("is_cancelled must be callable")
    value = is_cancelled()
    if type(value) is not bool:
        raise TypeError("is_cancelled must return bool")
    return value


def _number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("XYZ numeric values must be finite")
    return format(0.0 if value == 0.0 else value, ".17g")


def _replacement_number(value, missing_value_token):
    try:
        return _number(value)
    except (TypeError, ValueError):
        if missing_value_token is None:
            raise
        return missing_value_token


def atomic_write_chunks(destination, chunks, *, is_cancelled=None):
    """Write UTF-8 chunks atomically with cooperative cancellation."""
    destination = Path(destination)
    if _cancelled(is_cancelled):
        raise ExportCancelled("export cancelled")
    temporary = short_sibling_temporary_path(destination)
    try:
        with temporary.open("xb") as stream:
            for chunk in chunks:
                if _cancelled(is_cancelled):
                    raise ExportCancelled("export cancelled")
                stream.write(chunk.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
            if _cancelled(is_cancelled):
                raise ExportCancelled("export cancelled")
        os.replace(temporary, destination)
    except BaseException as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as cleanup_error:
            error.add_note(f"temporary export cleanup failed: {cleanup_error}")
        raise


def _atomic_write(destination, content):
    atomic_write_chunks(destination, (content,))


# Kept private as a compatibility alias for the existing exporter internals.
_atomic_write_chunks = atomic_write_chunks


def _structure_rows(structure):
    if not isinstance(structure, Structure):
        raise TypeError("structure must be a Structure")
    if structure.coordinates.unit != "angstrom":
        raise ValueError("XYZ export requires angstrom coordinates")
    rows = []
    for atomic_number, coordinates in zip(
        structure.atomic_numbers,
        structure.coordinates.values,
        strict=True,
    ):
        try:
            symbol = _SYMBOLS[atomic_number]
        except KeyError as error:
            raise ValueError(
                f"XYZ export does not support atomic number {atomic_number}"
            ) from error
        rows.append(f"{symbol} {' '.join(_number(value) for value in coordinates)}")
    return rows


def export_xyz(destination, structure, *, title="", is_cancelled=None):
    if not isinstance(title, str):
        raise TypeError("title must be a string")
    if "\n" in title or "\r" in title:
        raise ValueError("title must fit on one line")
    rows = _structure_rows(structure)
    content = "\n".join((str(len(rows)), title, *rows)) + "\n"
    _atomic_write_chunks(
        destination,
        (content,),
        is_cancelled=is_cancelled,
    )
    return ExportReport("xyz", True, 1, False)


def _property_kind(dataset):
    if isinstance(dataset.data, CategoricalData):
        return "S"
    import numpy

    kind = numpy.dtype(dataset.data.dtype).kind
    if kind == "b":
        return "L"
    if kind in "iu":
        return "I"
    if kind in "f":
        return "R"
    raise TypeError(
        f"extXYZ cannot export dtype {dataset.data.dtype!r} "
        f"for {dataset.semantic_role}"
    )


def _property_columns(dataset):
    prefix = 2 if isinstance(dataset, AtomFrameProperty) else 1
    suffix = dataset.data.shape[prefix:]
    if not suffix:
        return 1
    if len(suffix) != 1:
        raise ValueError(
            f"extXYZ atom property {dataset.semantic_role} "
            "must be scalar or one-dimensional"
        )
    return suffix[0]


def _category_value(data, index):
    import numpy

    codes = numpy.asarray(data.codes.values[index])
    if codes.ndim == 0:
        code = int(codes)
        return None if code == data.missing_code else data.categories[code]
    values = numpy.empty(codes.shape, dtype=object)
    for offset in numpy.ndindex(codes.shape):
        code = int(codes[offset])
        values[offset] = (
            None if code == data.missing_code else data.categories[code]
        )
    return values.tolist()


def _quote(value):
    return json.dumps(str(value), ensure_ascii=False, separators=(",", ":"))


def _atom_text(value, kind, missing_value_token):
    if value is None:
        if missing_value_token is None:
            raise ValueError("missing extXYZ atom value requires a token")
        return _quote(missing_value_token) if kind == "S" else missing_value_token
    if kind == "S":
        text = str(value)
        return (
            text
            if text and not any(character.isspace() or character in "\"'\\" for character in text)
            else _quote(text)
        )
    if kind == "L":
        return "T" if bool(value) else "F"
    if kind == "I":
        return str(int(value))
    return _replacement_number(value, missing_value_token)


def _metadata_text(value, missing_value_token):
    import numpy

    value = numpy.asarray(value)
    if value.ndim > 2:
        raise ValueError("extXYZ metadata arrays may have at most two dimensions")
    if value.ndim:
        return _metadata_array(
            value.tolist(),
            missing_value_token,
            force_real=value.dtype.kind == "f",
        )
    scalar = value.item()
    if isinstance(scalar, (bool, numpy.bool_)):
        return "T" if bool(scalar) else "F"
    if isinstance(scalar, (int, numpy.integer)) and not isinstance(scalar, bool):
        return str(int(scalar))
    if isinstance(scalar, (float, numpy.floating)):
        return _real_text(scalar, missing_value_token)
    return _quote(scalar)


def _real_text(value, missing_value_token):
    text = _replacement_number(value, missing_value_token)
    return text if any(character in text for character in ".eE") else text + ".0"


def _metadata_array(value, missing_value_token, *, force_real=False):
    if isinstance(value, list):
        return (
            "["
            + ",".join(
                _metadata_array(
                    item,
                    missing_value_token,
                    force_real=force_real,
                )
                for item in value
            )
            + "]"
        )
    if isinstance(value, bool):
        return "T" if value else "F"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return (
            _real_text(value, missing_value_token)
            if force_real
            else _replacement_number(value, missing_value_token)
        )
    return _quote(value)


def _valid(dataset, frame_index, atom_index=None):
    if isinstance(dataset.data, CategoricalData):
        index = (
            (frame_index, atom_index)
            if atom_index is not None
            else (frame_index,)
        )
        import numpy

        present = (
            numpy.asarray(dataset.data.codes.values[index])
            != dataset.data.missing_code
        )
        return bool(
            numpy.any(present)
            if atom_index is not None
            else numpy.all(present)
        )
    if dataset.validity_mask is None:
        return True
    index = (
        (frame_index, atom_index)
        if atom_index is not None
        else (frame_index,)
    )
    return bool(dataset.validity_mask.values[index])


def _atom_field_name(dataset):
    return _ATOM_ROLE_NAMES.get(
        dataset.semantic_role,
        (dataset.semantic_role, 1000, None),
    )[0]


def _ordered_atom_properties(properties):
    indexed = [
        (index, item)
        for index, item in enumerate(properties)
        if isinstance(item, AtomFrameProperty)
    ]
    return tuple(
        item
        for _index, item in sorted(
            indexed,
            key=lambda pair: (
                _ATOM_ROLE_NAMES.get(
                    pair[1].semantic_role,
                    ("", 1000, None),
                )[1],
                pair[0],
            ),
        )
    )


def _ordered_frame_properties(properties):
    indexed = [
        (index, item)
        for index, item in enumerate(properties)
        if isinstance(item, FrameProperty) and item.semantic_role != "pbc"
    ]
    return tuple(
        item
        for _index, item in sorted(
            indexed,
            key=lambda pair: (
                _FRAME_ROLE_RANK.get(pair[1].semantic_role, 1000),
                pair[0],
            ),
        )
    )


def _emitted_unit_keys(properties):
    keys = set()
    for item in properties:
        if isinstance(item, AtomFrameProperty):
            field_name, _rank, expected = _ATOM_ROLE_NAMES.get(
                item.semantic_role,
                (item.semantic_role, 1000, None),
            )
            if expected is not None and item.data.unit == expected:
                keys.add(f"{field_name}_unit")
        elif isinstance(item, FrameProperty):
            expected = _FRAME_ROLE_UNITS.get(item.semantic_role)
            if expected is not None and item.data.unit == expected:
                keys.add(f"{item.semantic_role}_unit")
    return keys


def _loss_entries(frame_set, properties):
    entries = []
    for item in properties:
        if item.status in {DatasetStatus.PARTIAL, DatasetStatus.AMBIGUOUS}:
            entries.append(
                ExportReportEntry(
                    f"{item.status.value}_property",
                    f"{item.semantic_role} is {item.status.value}",
                )
            )
    modeled = set()
    for item in _ordered_frame_properties(properties):
        modeled.add(item.semantic_role)
        source_key = _FRAME_SOURCE_KEYS.get(item.semantic_role)
        if source_key is not None:
            modeled.add(source_key)
    emitted_units = _emitted_unit_keys(properties)
    raw_keys = set()
    if frame_set is not None:
        for comment_text in frame_set.comments:
            try:
                comment = parse_extxyz_comment(comment_text)
            except ValueError:
                continue
            for entry in comment.entries:
                if (
                    entry.key not in _RESERVED_COMMENT_KEYS
                    and _token(entry.key) not in modeled
                    and entry.key not in emitted_units
                    and entry.key not in raw_keys
                ):
                    raw_keys.add(entry.key)
                    entries.append(
                        ExportReportEntry(
                            "unsafe_metadata_omitted",
                            f"{entry.key} cannot be safely typed and will be omitted",
                        )
                    )
    return entries


def _has_missing_cells(structure, frame_set, properties):
    import numpy

    coordinates = (
        structure.coordinates.values
        if frame_set is None
        else frame_set.data.values
    )
    if not numpy.all(numpy.isfinite(coordinates)):
        return True
    for item in properties:
        if isinstance(item.data, CategoricalData):
            if isinstance(item, AtomFrameProperty):
                codes = numpy.asarray(item.data.codes.values)
                for frame_index in range(frame_set.data.shape[0]):
                    present = (
                        codes[frame_index] != item.data.missing_code
                    )
                    if numpy.any(present) and not numpy.all(present):
                        return True
            continue
        values = numpy.asarray(item.data.values)
        if isinstance(item, AtomFrameProperty):
            for frame_index in range(frame_set.data.shape[0]):
                valid = [
                    _valid(item, frame_index, atom_index)
                    for atom_index in range(frame_set.data.shape[1])
                ]
                if any(valid) and not all(valid):
                    return True
                for atom_index, is_valid in enumerate(valid):
                    if is_valid and not numpy.all(
                        numpy.isfinite(values[frame_index, atom_index])
                    ):
                        return True
        else:
            for frame_index in range(frame_set.data.shape[0]):
                if _valid(item, frame_index) and not numpy.all(
                    numpy.isfinite(values[frame_index])
                ):
                    return True
    return False


def _check_export_inputs(structure, frame_set, properties):
    if not isinstance(structure, Structure):
        raise TypeError("structure must be a Structure")
    if structure.coordinates.unit != "angstrom":
        raise ValueError("extXYZ export requires angstrom coordinates")
    if frame_set is not None:
        if not isinstance(frame_set, FrameSet):
            raise TypeError("frame_set must be a FrameSet or None")
        if frame_set.structure_id != structure.id:
            raise ValueError("frame_set does not belong to structure")
        if frame_set.data.unit != "angstrom":
            raise ValueError("extXYZ export requires angstrom coordinates")
        if frame_set.data.shape[1] != len(structure.atomic_numbers):
            raise ValueError("frame_set atom count does not match structure")
    frame_count = 1 if frame_set is None else frame_set.data.shape[0]
    atom_field_names = {"species", "pos"}
    for item in properties:
        if not isinstance(
            item,
            (AtomFrameProperty, CellFrameProperty, FrameProperty),
        ):
            raise TypeError("properties must contain frame property datasets")
        if frame_set is None or item.frame_set_id != frame_set.id:
            raise ValueError("property does not belong to frame_set")
        if item.data.shape[0] != frame_count:
            raise ValueError("property frame count does not match frame_set")
        if isinstance(item, AtomFrameProperty):
            field_name = _atom_field_name(item)
            if field_name in atom_field_names:
                raise ValueError(
                    f"duplicate extXYZ atom property name: {field_name}"
                )
            atom_field_names.add(field_name)
    comment_keys = set()

    def add_comment_key(key):
        if key in comment_keys:
            raise ValueError(f"duplicate extXYZ comment key: {key}")
        comment_keys.add(key)

    for item in properties:
        if isinstance(item, CellFrameProperty):
            add_comment_key("Lattice")
        elif isinstance(item, FrameProperty) and item.semantic_role == "pbc":
            add_comment_key("pbc")
    unit_keys = _emitted_unit_keys(properties)
    for item in _ordered_frame_properties(properties):
        add_comment_key(item.semantic_role)
    for key in sorted(unit_keys):
        add_comment_key(key)
    return frame_count


def _frame_coordinates(structure, frame_set, frame_index):
    return (
        structure.coordinates.values
        if frame_set is None
        else frame_set.data.values[frame_index]
    )


def _cell_for_frame(structure, properties, frame_index):
    cell_property = next(
        (item for item in properties if isinstance(item, CellFrameProperty)),
        None,
    )
    if cell_property is not None:
        if not _valid(cell_property, frame_index):
            return None
        return cell_property.data.values[frame_index]
    return None if structure.cell is None else structure.cell.values


def _pbc_for_frame(structure, properties, frame_index, cell):
    pbc_property = next(
        (
            item
            for item in properties
            if isinstance(item, FrameProperty) and item.semantic_role == "pbc"
        ),
        None,
    )
    if pbc_property is not None and _valid(pbc_property, frame_index):
        values = pbc_property.data.values[frame_index]
        return tuple(bool(value) for value in values)
    if cell is None or structure.periodic is None:
        return (False, False, False)
    return structure.periodic.pbc


def _metadata_item(dataset, frame_index):
    if not _valid(dataset, frame_index):
        return None
    if isinstance(dataset.data, CategoricalData):
        return _category_value(dataset.data, (frame_index,))
    return dataset.data.values[frame_index]


def _atom_item(dataset, frame_index, atom_index):
    if isinstance(dataset.data, CategoricalData):
        return _category_value(dataset.data, (frame_index, atom_index))
    if not _valid(dataset, frame_index, atom_index):
        return None
    return dataset.data.values[(frame_index, atom_index)]


def _schema_for_frame(atom_properties, frame_index, atom_count):
    fields = [("species", "S", 1, None), ("pos", "R", 3, None)]
    for item in atom_properties:
        validity = [
            _valid(item, frame_index, atom_index)
            for atom_index in range(atom_count)
        ]
        if not any(validity):
            continue
        fields.append(
            (
                _atom_field_name(item),
                _property_kind(item),
                _property_columns(item),
                item,
            )
        )
    names = [field[0] for field in fields]
    if len(names) != len(set(names)):
        raise ValueError("extXYZ property names must be unique")
    return tuple(fields)


def _comment_for_frame(
    structure,
    frame_set,
    properties,
    frame_index,
    fields,
    missing_value_token,
):
    cell = _cell_for_frame(structure, properties, frame_index)
    pbc = _pbc_for_frame(structure, properties, frame_index, cell)
    parts = []
    if cell is not None:
        flat = " ".join(
            _replacement_number(value, missing_value_token)
            for row in cell
            for value in row
        )
        parts.append(f"Lattice={_quote(flat)}")
    descriptor = ":".join(
        f"{name}:{kind}:{columns}"
        for name, kind, columns, _dataset in fields
    )
    parts.append(f"Properties={descriptor}")
    if cell is not None:
        parts.append(
            f'pbc={_quote(" ".join("T" if value else "F" for value in pbc))}'
        )
    for _name, _kind, _columns, dataset in fields:
        if dataset is None:
            continue
        expected = _ATOM_ROLE_NAMES.get(
            dataset.semantic_role,
            ("", 0, None),
        )[2]
        if expected is not None and dataset.data.unit == expected:
            parts.append(f"{_atom_field_name(dataset)}_unit={expected}")
    for dataset in _ordered_frame_properties(properties):
        value = _metadata_item(dataset, frame_index)
        if value is None:
            continue
        parts.append(
            f"{dataset.semantic_role}="
            f"{_metadata_text(value, missing_value_token)}"
        )
        expected = _FRAME_ROLE_UNITS.get(dataset.semantic_role)
        if expected is not None and dataset.data.unit == expected:
            parts.append(f"{dataset.semantic_role}_unit={expected}")
    return " ".join(parts)


def _frame_rows(
    structure,
    frame_set,
    frame_index,
    fields,
    missing_value_token,
):
    coordinates = _frame_coordinates(structure, frame_set, frame_index)
    rows = []
    for atom_index, (atomic_number, position) in enumerate(
        zip(structure.atomic_numbers, coordinates, strict=True)
    ):
        try:
            symbol = _SYMBOLS[atomic_number]
        except KeyError as error:
            raise ValueError(
                f"extXYZ export does not support atomic number {atomic_number}"
            ) from error
        columns = [
            symbol,
            *(
                _replacement_number(value, missing_value_token)
                for value in position
            ),
        ]
        for _name, kind, width, dataset in fields[2:]:
            value = _atom_item(dataset, frame_index, atom_index)
            values = (
                (None,) * width
                if width > 1 and value is None
                else value
                if width > 1
                else (value,)
            )
            if width > 1 and len(values) != width:
                raise ValueError(
                    f"{dataset.semantic_role} has an invalid component count"
                )
            columns.extend(
                _atom_text(item, kind, missing_value_token)
                for item in values
            )
        rows.append(" ".join(columns))
    return rows


def preview_extxyz_export(
    structure,
    *,
    frame_set=None,
    properties=(),
    missing_value_token=None,
):
    properties = tuple(properties)
    frame_count = _check_export_inputs(structure, frame_set, properties)
    if missing_value_token is not None:
        if not isinstance(missing_value_token, str) or not missing_value_token:
            raise ValueError("missing_value_token must be a non-empty string")
        try:
            normalized_token = _number(float(missing_value_token))
        except (TypeError, ValueError) as error:
            raise ValueError(
                "missing_value_token must be a finite real token"
            ) from error
        if normalized_token != missing_value_token:
            raise ValueError(
                "missing_value_token must use canonical numeric formatting"
            )
    entries = _loss_entries(frame_set, properties)
    needs_token = _has_missing_cells(structure, frame_set, properties)
    if needs_token and missing_value_token is None:
        entries.append(
            ExportReportEntry(
                "missing_value_token_required",
                "non-finite or partially missing atom values require "
                "an explicit finite replacement token",
            )
        )
    return ExportReport(
        "extxyz",
        False,
        frame_count,
        bool(entries),
        tuple(entries),
        missing_value_token,
    )


def export_extxyz(
    destination,
    structure,
    *,
    frame_set=None,
    properties=(),
    confirm_loss=False,
    missing_value_token=None,
    is_cancelled=None,
):
    properties = tuple(properties)
    if not isinstance(confirm_loss, bool):
        raise TypeError("confirm_loss must be a bool")
    preview = preview_extxyz_export(
        structure,
        frame_set=frame_set,
        properties=properties,
        missing_value_token=missing_value_token,
    )
    missing_token_required = any(
        entry.code == "missing_value_token_required"
        for entry in preview.entries
    )
    if (
        (preview.requires_confirmation and not confirm_loss)
        or missing_token_required
    ):
        return preview

    atom_properties = _ordered_atom_properties(properties)
    def lines():
        for frame_index in range(preview.frame_count):
            fields = _schema_for_frame(
                atom_properties,
                frame_index,
                len(structure.atomic_numbers),
            )
            comment = _comment_for_frame(
                structure,
                frame_set,
                properties,
                frame_index,
                fields,
                missing_value_token,
            )
            rows = _frame_rows(
                structure,
                frame_set,
                frame_index,
                fields,
                missing_value_token,
            )
            yield f"{len(rows)}\n"
            yield f"{comment}\n"
            for row in rows:
                yield f"{row}\n"

    _atomic_write_chunks(
        destination,
        lines(),
        is_cancelled=is_cancelled,
    )
    return ExportReport(
        "extxyz",
        True,
        preview.frame_count,
        preview.requires_confirmation,
        preview.entries,
        missing_value_token,
    )


def _arrays_equal(left, right, *, rtol, atol):
    import numpy

    left = numpy.asarray(left)
    right = numpy.asarray(right)
    if left.shape != right.shape or left.dtype.kind != right.dtype.kind:
        return False
    if left.dtype.kind in "fc":
        return bool(
            numpy.allclose(
                left,
                right,
                rtol=rtol,
                atol=atol,
                equal_nan=True,
            )
        )
    return bool(numpy.array_equal(left, right))


def _dataset_key(dataset):
    return type(dataset).__name__, dataset.domain, dataset.semantic_role


def _datasets_by_key(datasets):
    grouped = {}
    for dataset in datasets:
        grouped.setdefault(_dataset_key(dataset), []).append(dataset)
    return grouped


def _dataset_differences(left, right, *, name, rtol, atol):
    differences = []
    if left.status is not right.status:
        differences.append(f"{name} status differs")
    if left.data.dims != right.data.dims:
        differences.append(f"{name} dims differ")
        return differences
    if left.data.unit != right.data.unit:
        differences.append(f"{name} unit differs")
    if isinstance(left.data, CategoricalData) != isinstance(
        right.data,
        CategoricalData,
    ):
        differences.append(f"{name} type differs")
        return differences
    if isinstance(left.data, CategoricalData):
        if (
            left.data.categories != right.data.categories
            or left.data.missing_code != right.data.missing_code
            or not _arrays_equal(
                left.data.codes.values,
                right.data.codes.values,
                rtol=rtol,
                atol=atol,
            )
        ):
            differences.append(f"{name} categorical data differs")
    elif not _arrays_equal(
        left.data.values,
        right.data.values,
        rtol=rtol,
        atol=atol,
    ):
        label = "coordinates" if isinstance(left, FrameSet) else name
        differences.append(f"{label} values differ")
    left_mask = getattr(left, "validity_mask", None)
    right_mask = getattr(right, "validity_mask", None)
    if (left_mask is None) != (right_mask is None) or (
        left_mask is not None
        and not _arrays_equal(
            left_mask.values,
            right_mask.values,
            rtol=rtol,
            atol=atol,
        )
    ):
        differences.append(f"{name} validity mask differs")
    return differences


def _dataset_groups_match(left_items, right_items, *, rtol, atol):
    if not left_items:
        return True
    left = left_items[0]
    for index, right in enumerate(right_items):
        if _dataset_differences(
            left,
            right,
            name=left.semantic_role,
            rtol=rtol,
            atol=atol,
        ):
            continue
        remaining = right_items[:index] + right_items[index + 1 :]
        if _dataset_groups_match(
            left_items[1:],
            remaining,
            rtol=rtol,
            atol=atol,
        ):
            return True
    return False


def semantic_extxyz_differences(left, right, *, rtol=1.0e-9, atol=1.0e-12):
    if not isinstance(left, ImportBatch) or not isinstance(right, ImportBatch):
        raise TypeError("semantic comparator requires two ImportBatch values")
    differences = []
    if len(left.structures) != len(right.structures):
        return ("structure count differs",)
    for index, (left_structure, right_structure) in enumerate(
        zip(left.structures, right.structures, strict=True)
    ):
        prefix = "" if index == 0 else f"structure {index} "
        if left_structure.atomic_numbers != right_structure.atomic_numbers:
            differences.append(f"{prefix}atomic numbers differ")
        if not _arrays_equal(
            left_structure.coordinates.values,
            right_structure.coordinates.values,
            rtol=rtol,
            atol=atol,
        ):
            differences.append(f"{prefix}structure coordinates values differ")
        if (left_structure.cell is None) != (right_structure.cell is None):
            differences.append(f"{prefix}cell presence differs")
        elif left_structure.cell is not None and not _arrays_equal(
            left_structure.cell.values,
            right_structure.cell.values,
            rtol=rtol,
            atol=atol,
        ):
            differences.append(f"{prefix}cell values differ")
        left_pbc = (
            (False, False, False)
            if left_structure.periodic is None
            else left_structure.periodic.pbc
        )
        right_pbc = (
            (False, False, False)
            if right_structure.periodic is None
            else right_structure.periodic.pbc
        )
        if left_pbc != right_pbc:
            differences.append(f"{prefix}PBC differs")

    left_datasets = _datasets_by_key(left.datasets)
    right_datasets = _datasets_by_key(right.datasets)
    if left_datasets.keys() != right_datasets.keys():
        differences.append("property inventory differs")
        return tuple(differences)
    for key in sorted(left_datasets):
        left_items = left_datasets[key]
        right_items = right_datasets[key]
        name = key[2]
        if len(left_items) != len(right_items):
            differences.append(
                f"{name} multiplicity differs: "
                f"{len(left_items)} != {len(right_items)}"
            )
            continue
        if sorted(item.status.value for item in left_items) != sorted(
            item.status.value for item in right_items
        ):
            differences.append(f"{name} status differs")
            continue
        if len(left_items) == 1:
            differences.extend(
                _dataset_differences(
                    left_items[0],
                    right_items[0],
                    name=name,
                    rtol=rtol,
                    atol=atol,
                )
            )
        elif not _dataset_groups_match(
            tuple(left_items),
            tuple(right_items),
            rtol=rtol,
            atol=atol,
        ):
            differences.append(
                f"{name} dataset group semantics differ"
            )
    return tuple(differences)


__all__ = (
    "ExportReport",
    "ExportReportEntry",
    "ExportCancelled",
    "atomic_write_chunks",
    "export_extxyz",
    "export_xyz",
    "preview_extxyz_export",
    "semantic_extxyz_differences",
)
