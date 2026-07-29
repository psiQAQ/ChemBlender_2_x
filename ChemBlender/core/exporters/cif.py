"""Controlled CIF export with source-envelope preservation."""

from dataclasses import dataclass
import math
import re

from ...Chem_data import ELEMENTS_DEFAULT
from ..formats.cif import _gemmi, _parse_block, _read_document
from ..model import ArrayData, CIFEnvelope, Structure, unit_cell_parameters
from .xyz import ExportReport, ExportReportEntry, atomic_write_chunks


_SYMBOLS = {
    data[0]: symbol
    for symbol, data in ELEMENTS_DEFAULT.items()
    if data[0] > 0
}
_ACTIONS = {"preserve", "replace", "add", "omit"}
_BLOCK_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_U_COMPONENTS = ("11", "22", "33", "12", "13", "23")
_SYMMETRY_NAME_TAGS = (
    "_space_group_name_H-M_alt",
    "_symmetry_space_group_name_H-M",
)
_SYMMETRY_NUMBER_TAGS = (
    "_space_group_IT_number",
    "_symmetry_Int_Tables_number",
)
_SYMMETRY_HALL_TAGS = (
    "_space_group_name_Hall",
    "_symmetry_space_group_name_Hall",
)
_SYMMETRY_OPERATION_TAGS = (
    "_space_group_symop_operation_xyz",
    "_symmetry_equiv_pos_as_xyz",
)


@dataclass(frozen=True, slots=True)
class CIFExportField:
    name: str
    action: str
    detail: str

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("CIF export field name must be non-empty")
        if self.action not in _ACTIONS:
            raise ValueError("unsupported CIF export field action")
        if not isinstance(self.detail, str) or not self.detail:
            raise ValueError("CIF export field detail must be non-empty")


@dataclass(frozen=True, slots=True)
class CIFExportPlan:
    mode: str
    block_key: str
    fields: tuple[CIFExportField, ...]

    def __post_init__(self):
        if self.mode not in {"preserve", "normalized"}:
            raise ValueError("CIF export mode must be preserve or normalized")
        if not isinstance(self.block_key, str) or not self.block_key:
            raise ValueError("CIF export block key must be non-empty")
        fields = tuple(self.fields)
        if any(not isinstance(value, CIFExportField) for value in fields):
            raise TypeError("fields must contain CIFExportField values")
        object.__setattr__(self, "fields", fields)


def _number(value):
    value = float(value)
    if math.isnan(value):
        return "?"
    if not math.isfinite(value):
        raise ValueError("CIF numeric values must be finite or missing")
    return format(0.0 if value == 0.0 else value, ".17g")


def _same_array(left, right):
    import numpy

    if left is None or right is None:
        return left is right
    return bool(
        numpy.allclose(
            numpy.asarray(left.values),
            numpy.asarray(right.values),
            rtol=0.0,
            atol=1.0e-12,
            equal_nan=True,
        )
    )


def _action(left, right):
    if left is None and right is None:
        return "omit"
    if left is None:
        return "add"
    return "preserve" if _same_array(left, right) else "replace"


def _sequence_action(original, current, default):
    if original == current:
        return "preserve"
    return "add" if all(value == default for value in original) else "replace"


def _bound_source(structure, envelope):
    if not isinstance(structure, Structure) or structure.periodic is None:
        raise TypeError("structure must be a periodic Structure")
    if (
        not isinstance(envelope, CIFEnvelope)
        or structure.periodic.cif_envelope_id != envelope.id
    ):
        raise ValueError("preserve mode requires the matching CIF envelope")
    index = structure.periodic.cif_block_index
    if (
        index is None
        or index >= len(envelope.block_names)
        or structure.periodic.cif_block_name != envelope.block_names[index]
        or structure.periodic.cif_block_key != envelope.block_keys[index]
    ):
        raise ValueError("structure has an invalid CIF block identity")
    gemmi = _gemmi()
    document = _read_document(gemmi, envelope.source_bytes)
    blocks = tuple(document)
    if (
        index >= len(blocks)
        or blocks[index].name != envelope.block_names[index]
    ):
        raise ValueError("CIF envelope block inventory no longer matches")
    baseline, _issues, _normalizations = _parse_block(
        gemmi,
        blocks[index],
        source_hash=envelope.revision,
        envelope_id=envelope.id,
        block_name=envelope.block_names[index],
        block_key=envelope.block_keys[index],
        block_index=index,
    )
    return gemmi, document, blocks[index], baseline


def _preserve_fields(structure, baseline):
    periodic = structure.periodic
    original = baseline.periodic
    atom_same = (
        structure.atomic_numbers == baseline.atomic_numbers
        and periodic.site_labels == original.site_labels
        and _same_array(
            periodic.fractional_coordinates,
            original.fractional_coordinates,
        )
    )
    declared_same = periodic.declared_symmetry == original.declared_symmetry
    return (
        CIFExportField(
            "cell",
            "preserve" if _same_array(structure.cell, baseline.cell) else "replace",
            "unit-cell lengths and angles",
        ),
        CIFExportField(
            "atom_site",
            "preserve" if atom_same else "replace",
            "site labels, elements and coordinates",
        ),
        CIFExportField(
            "occupancy",
            (
                "preserve"
                if _same_array(periodic.occupancies, original.occupancies)
                else "replace"
            ),
            "site occupancy values",
        ),
        CIFExportField(
            "u_iso",
            _action(
                original.isotropic_displacements,
                periodic.isotropic_displacements,
            ),
            "isotropic displacement values",
        ),
        CIFExportField(
            "u_aniso",
            _action(
                original.anisotropic_displacements,
                periodic.anisotropic_displacements,
            ),
            "anisotropic displacement values",
        ),
        CIFExportField(
            "adp_type",
            _sequence_action(original.adp_types, periodic.adp_types, "none"),
            "atom-site displacement types",
        ),
        CIFExportField(
            "disorder_group",
            _sequence_action(
                original.disorder_groups,
                periodic.disorder_groups,
                0,
            ),
            "atom-site disorder groups",
        ),
        CIFExportField(
            "disorder_assembly",
            _sequence_action(
                original.disorder_assemblies,
                periodic.disorder_assemblies,
                "none",
            ),
            "atom-site disorder assemblies",
        ),
        CIFExportField(
            "declared_symmetry",
            "preserve" if declared_same else "replace",
            "source-declared symmetry fields",
        ),
        CIFExportField(
            "unknown_content",
            "preserve",
            "unrecognized source tags and loops",
        ),
    )


def _normalized_fields(structure):
    periodic = structure.periodic
    return (
        CIFExportField("cell", "add", "unit-cell lengths and angles"),
        CIFExportField(
            "atom_site",
            "add",
            "site labels, elements and fractional coordinates",
        ),
        CIFExportField("occupancy", "add", "site occupancy values"),
        CIFExportField(
            "u_iso",
            "add" if periodic.isotropic_displacements is not None else "omit",
            "isotropic displacement values",
        ),
        CIFExportField(
            "u_aniso",
            "add" if periodic.anisotropic_displacements is not None else "omit",
            "anisotropic displacement values",
        ),
        CIFExportField(
            "adp_type",
            (
                "add"
                if any(value != "none" for value in periodic.adp_types)
                else "omit"
            ),
            "atom-site displacement types",
        ),
        CIFExportField(
            "disorder_group",
            "add" if any(periodic.disorder_groups) else "omit",
            "atom-site disorder groups",
        ),
        CIFExportField(
            "disorder_assembly",
            (
                "add"
                if any(
                    value != "none"
                    for value in periodic.disorder_assemblies
                )
                else "omit"
            ),
            "atom-site disorder assemblies",
        ),
        CIFExportField(
            "declared_symmetry",
            (
                "add"
                if any(
                    (
                        periodic.declared_space_group_name,
                        periodic.declared_space_group_number,
                        periodic.declared_hall_symbol,
                        periodic.symmetry_operations,
                    )
                )
                else "omit"
            ),
            "source-declared symmetry fields",
        ),
        CIFExportField(
            "unknown_content",
            "omit",
            "no source envelope is attached",
        ),
    )


def plan_cif_export(
    structure,
    *,
    envelope=None,
    mode="preserve",
    block_name="chemblender",
):
    if not isinstance(structure, Structure) or structure.periodic is None:
        raise TypeError("structure must be a periodic Structure")
    if mode == "preserve":
        _gemmi_value, _document, _block, baseline = _bound_source(
            structure,
            envelope,
        )
        return CIFExportPlan(
            mode,
            structure.periodic.cif_block_key,
            _preserve_fields(structure, baseline),
        )
    if mode != "normalized":
        raise ValueError("mode must be preserve or normalized")
    if not isinstance(block_name, str) or not _BLOCK_NAME.fullmatch(block_name):
        raise ValueError("block_name must be a safe CIF data-block token")
    return CIFExportPlan(mode, block_name, _normalized_fields(structure))


def _cell_parameters(structure):
    import numpy

    scale = {"angstrom": 1.0, "bohr": 0.529177210903}.get(
        structure.cell.unit
    )
    if scale is None:
        raise ValueError("CIF export requires angstrom or bohr cell units")
    cell = ArrayData(
        numpy.asarray(structure.cell.values) * scale,
        ("cell_vector", "xyz"),
        "angstrom",
    )
    return unit_cell_parameters(cell)


def _write_cell(block, structure):
    for tag, value in zip(
        (
            "_cell_length_a",
            "_cell_length_b",
            "_cell_length_c",
            "_cell_angle_alpha",
            "_cell_angle_beta",
            "_cell_angle_gamma",
        ),
        _cell_parameters(structure),
        strict=True,
    ):
        block.set_pair(tag, _number(value))


def _column(block, loop, tag, values):
    column = block.find_loop(tag)
    if not column:
        loop.add_columns((tag,), "?")
        column = block.find_loop(tag)
    if len(column) != len(values):
        raise ValueError(f"CIF {tag} row count does not match Structure")
    for index, value in enumerate(values):
        column[index] = value


def _site_loop(block):
    column = block.find_loop("_atom_site_label")
    if not column:
        raise ValueError("preserve mode requires an atom-site loop")
    return column.get_loop()


def _quoted(gemmi, values):
    return tuple(gemmi.cif.quote(str(value)) for value in values)


def _site_columns(gemmi, structure):
    import numpy

    periodic = structure.periodic
    symbols = []
    for number in structure.atomic_numbers:
        try:
            symbols.append(_SYMBOLS[number])
        except KeyError as error:
            raise ValueError(
                f"CIF export does not support atomic number {number}"
            ) from error
    fractional = numpy.asarray(periodic.fractional_coordinates.values)
    columns = {
        "_atom_site_label": _quoted(gemmi, periodic.site_labels),
        "_atom_site_type_symbol": _quoted(gemmi, symbols),
        "_atom_site_fract_x": tuple(_number(value) for value in fractional[:, 0]),
        "_atom_site_fract_y": tuple(_number(value) for value in fractional[:, 1]),
        "_atom_site_fract_z": tuple(_number(value) for value in fractional[:, 2]),
    }
    if structure.coordinates.unit not in {"angstrom", "bohr"}:
        raise ValueError("CIF export requires angstrom or bohr coordinates")
    scale = 1.0 if structure.coordinates.unit == "angstrom" else 0.529177210903
    cartesian = numpy.asarray(structure.coordinates.values) * scale
    for axis, offset in zip(("x", "y", "z"), range(3), strict=True):
        columns[f"_atom_site_Cartn_{axis}"] = tuple(
            _number(value) for value in cartesian[:, offset]
        )
    return columns


def _write_sites(gemmi, block, structure, *, normalized=False):
    columns = _site_columns(gemmi, structure)
    if normalized:
        tags = (
            "_atom_site_label",
            "_atom_site_type_symbol",
            "_atom_site_fract_x",
            "_atom_site_fract_y",
            "_atom_site_fract_z",
        )
        loop = block.init_loop("", tags)
        for row in zip(*(columns[tag] for tag in tags), strict=True):
            loop.add_row(row)
        return loop
    loop = _site_loop(block)
    for tag, values in columns.items():
        if tag.startswith("_atom_site_Cartn_") and not block.find_loop(tag):
            continue
        _column(block, loop, tag, values)
    return loop


def _write_occupancy(block, loop, structure):
    _column(
        block,
        loop,
        "_atom_site_occupancy",
        tuple(_number(value) for value in structure.periodic.occupancies.values),
    )


def _write_isotropic(block, loop, structure):
    import numpy

    values = structure.periodic.isotropic_displacements
    u_tag = "_atom_site_U_iso_or_equiv"
    b_tag = "_atom_site_B_iso_or_equiv"
    use_b = bool(block.find_loop(b_tag)) and not bool(block.find_loop(u_tag))
    tag = b_tag if use_b else u_tag
    if values is None:
        rendered = ("?",) * len(structure.atomic_numbers)
    else:
        scale = 8.0 * numpy.pi**2 if use_b else 1.0
        rendered = tuple(_number(value * scale) for value in values.values)
    _column(block, loop, tag, rendered)


def _write_anisotropic(block, structure):
    import numpy

    existing = block.find_loop_item("_atom_site_aniso_label")
    if existing is not None:
        allowed = {
            "_atom_site_aniso_label",
            *(
                f"_atom_site_aniso_{kind}_{component}"
                for kind in ("U", "B")
                for component in _U_COMPONENTS
            ),
        }
        unknown = set(existing.loop.tags) - allowed
        if unknown:
            raise ValueError(
                "cannot replace anisotropic rows with unknown loop columns"
            )
        existing.erase()
    data = structure.periodic.anisotropic_displacements
    if data is None:
        return
    values = numpy.asarray(data.values)
    finite = numpy.all(numpy.isfinite(values), axis=1)
    if not numpy.any(finite):
        return
    tags = (
        "_atom_site_aniso_label",
        *(f"_atom_site_aniso_U_{value}" for value in _U_COMPONENTS),
    )
    loop = block.init_loop("", tags)
    for label, row, keep in zip(
        structure.periodic.site_labels,
        values,
        finite,
        strict=True,
    ):
        if keep:
            loop.add_row((label, *(_number(value) for value in row)))


def _set_optional_pair(gemmi, block, tags, value):
    existing = next((tag for tag in tags if block.find_pair(tag)), tags[0])
    for tag in tags:
        if tag != existing:
            item = block.find_pair_item(tag)
            if item is not None:
                item.erase()
    if value is None:
        item = block.find_pair_item(existing)
        if item is not None:
            item.erase()
    else:
        block.set_pair(existing, gemmi.cif.quote(str(value)))


def _write_declared_symmetry(gemmi, block, structure):
    periodic = structure.periodic
    _set_optional_pair(
        gemmi,
        block,
        _SYMMETRY_NAME_TAGS,
        periodic.declared_space_group_name,
    )
    _set_optional_pair(
        gemmi,
        block,
        _SYMMETRY_NUMBER_TAGS,
        periodic.declared_space_group_number,
    )
    _set_optional_pair(
        gemmi,
        block,
        _SYMMETRY_HALL_TAGS,
        periodic.declared_hall_symbol,
    )
    existing = next(
        (
            block.find_loop_item(tag)
            for tag in _SYMMETRY_OPERATION_TAGS
            if block.find_loop_item(tag) is not None
        ),
        None,
    )
    if existing is not None:
        if set(existing.loop.tags) - set(_SYMMETRY_OPERATION_TAGS):
            raise ValueError(
                "cannot replace symmetry operations with unknown loop columns"
            )
        existing.erase()
    if periodic.symmetry_operations:
        loop = block.init_loop("", (_SYMMETRY_OPERATION_TAGS[0],))
        for operation in periodic.symmetry_operations:
            loop.add_row((gemmi.cif.quote(operation),))


def _write_adp_types(gemmi, block, loop, structure, *, include_default=False):
    values = structure.periodic.adp_types
    if include_default or any(value != "none" for value in values):
        _column(
            block,
            loop,
            "_atom_site_adp_type",
            tuple(
                "." if value == "none" else gemmi.cif.quote(value)
                for value in values
            ),
        )


def _write_disorder_groups(block, loop, structure, *, include_default=False):
    periodic = structure.periodic
    if include_default or any(periodic.disorder_groups):
        _column(
            block,
            loop,
            "_atom_site_disorder_group",
            tuple(
                str(value) if value else "."
                for value in periodic.disorder_groups
            ),
        )


def _write_disorder_assemblies(
    gemmi,
    block,
    loop,
    structure,
    *,
    include_default=False,
):
    values = structure.periodic.disorder_assemblies
    if include_default or any(value != "none" for value in values):
        _column(
            block,
            loop,
            "_atom_site_disorder_assembly",
            tuple(
                "." if value == "none" else gemmi.cif.quote(value)
                for value in values
            ),
        )


def _patch_preserved(gemmi, block, structure, plan):
    actions = {field.name: field.action for field in plan.fields}
    if actions["cell"] == "replace":
        _write_cell(block, structure)
    loop = _site_loop(block)
    if actions["atom_site"] == "replace":
        loop = _write_sites(gemmi, block, structure)
    if actions["occupancy"] == "replace":
        _write_occupancy(block, loop, structure)
    if actions["u_iso"] in {"add", "replace"}:
        _write_isotropic(block, loop, structure)
    if actions["u_aniso"] in {"add", "replace"}:
        _write_anisotropic(block, structure)
    if actions["adp_type"] in {"add", "replace"}:
        _write_adp_types(
            gemmi,
            block,
            loop,
            structure,
            include_default=True,
        )
    if actions["disorder_group"] in {"add", "replace"}:
        _write_disorder_groups(
            block,
            loop,
            structure,
            include_default=True,
        )
    if actions["disorder_assembly"] in {"add", "replace"}:
        _write_disorder_assemblies(
            gemmi,
            block,
            loop,
            structure,
            include_default=True,
        )
    if actions["declared_symmetry"] == "replace":
        _write_declared_symmetry(gemmi, block, structure)


def _normalized_document(gemmi, structure, block_name):
    document = gemmi.cif.Document()
    block = document.add_new_block(block_name)
    _write_cell(block, structure)
    loop = _write_sites(gemmi, block, structure, normalized=True)
    _write_occupancy(block, loop, structure)
    if structure.periodic.isotropic_displacements is not None:
        _write_isotropic(block, loop, structure)
    if structure.periodic.anisotropic_displacements is not None:
        _write_anisotropic(block, structure)
    _write_adp_types(gemmi, block, loop, structure)
    _write_disorder_groups(block, loop, structure)
    _write_disorder_assemblies(gemmi, block, loop, structure)
    _write_declared_symmetry(gemmi, block, structure)
    return document


def _report(plan, *, written):
    return ExportReport(
        "cif",
        written,
        1,
        False,
        tuple(
            ExportReportEntry(
                f"{field.action}:{field.name}",
                field.detail,
            )
            for field in plan.fields
        ),
    )


def export_cif(
    destination,
    structure,
    *,
    envelope=None,
    mode="preserve",
    block_name="chemblender",
    is_cancelled=None,
):
    if mode == "preserve":
        gemmi, document, block, baseline = _bound_source(
            structure,
            envelope,
        )
        plan = CIFExportPlan(
            mode,
            structure.periodic.cif_block_key,
            _preserve_fields(structure, baseline),
        )
        _patch_preserved(gemmi, block, structure, plan)
    else:
        plan = plan_cif_export(
            structure,
            envelope=envelope,
            mode=mode,
            block_name=block_name,
        )
        gemmi = _gemmi()
        document = _normalized_document(gemmi, structure, block_name)
    atomic_write_chunks(
        destination,
        (document.as_string(),),
        is_cancelled=is_cancelled,
    )
    return _report(plan, written=True)


__all__ = (
    "CIFExportField",
    "CIFExportPlan",
    "export_cif",
    "plan_cif_export",
)
