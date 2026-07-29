from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from types import MappingProxyType

from ..Chem_data import ELEMENTS_DEFAULT
from ..core import (
    ArrayData,
    AtomicProperty,
    BiologicalHierarchy,
    DatasetStatus,
    Structure,
    TopologyRecord,
)
from ..core.topology.periodic import _pbc_primary_coordinates


_ANGSTROM_SCALE = {"angstrom": 1.0, "bohr": 0.529177210903}
_ELEMENT_BY_NUMBER = {
    data[0]: (symbol, data)
    for symbol, data in ELEMENTS_DEFAULT.items()
    if 0 < data[0] <= 118
}
_STRUCTURE_CONTRACT = "structure_view_v1"
_BALL_STICK_CONTRACT = "structure_ball_stick_v1"
_PERIODIC_DISPLAY_CONTRACT = "structure_periodic_display_v1"
_PERIODIC_SITE_DISPLAY_CONTRACT = "structure_periodic_sites_v1"
_PERIODIC_MODIFIER_NAME = "ChemBlender Periodic Images"
_SELECTIVE_MARKER_CONTRACT = "structure_selective_marker_v1"
_SELECTIVE_MARKER_GROUP = "ChemBlender Selective Constraints"
_VIEW_CONTRACT_VERSION = 1
_FATAL_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    MemoryError,
)
BIOLOGICAL_NUMERIC_ROLE_SPECS = MappingProxyType(
    {
        "occupancy": MappingProxyType(
            {
                "attribute": "cbq_occupancy",
                "unit": "dimensionless",
                "label": "Occupancy",
                "missing_policy": "nan_is_missing",
            }
        ),
        "b_factor": MappingProxyType(
            {
                "attribute": "cbq_b_factor",
                "unit": "angstrom_squared",
                "label": "B-Factor",
                "missing_policy": "nan_is_missing",
            }
        ),
        "partial_charge": MappingProxyType(
            {
                "attribute": "cbq_partial_charge",
                "unit": "elementary_charge",
                "label": "Partial Charge",
                "missing_policy": "nan_is_missing",
            }
        ),
        "radius": MappingProxyType(
            {
                "attribute": "cbq_pqr_radius",
                "unit": "angstrom",
                "label": "PQR Radius",
                "missing_policy": "nan_is_missing",
            }
        ),
    }
)


def _is_view_contract(owner, contract):
    return (
        owner.get("cbq_contract") == contract
        and owner.get("cbq_contract_version") == _VIEW_CONTRACT_VERSION
    )


def _merge_cleanup_failure(failure, error, label):
    if isinstance(error, _FATAL_EXCEPTIONS) and not isinstance(
        failure,
        _FATAL_EXCEPTIONS,
    ):
        error.add_note(f"earlier failure: {failure}")
        return error
    failure.add_note(f"{label}: {error}")
    return failure


def _run_cleanup(failure, label, callback):
    try:
        callback()
    except BaseException as error:
        return _merge_cleanup_failure(failure, error, label)
    return failure


def _coordinate_scale(unit):
    try:
        return _ANGSTROM_SCALE[unit]
    except KeyError as error:
        raise ValueError(f"unsupported coordinate unit: {unit}") from error


def _categorical_values(categorical):
    return tuple(
        None if int(code) == categorical.missing_code
        else categorical.categories[int(code)]
        for code in categorical.codes.values
    )


def _categorical(values):
    categories = tuple(dict.fromkeys(values))
    indices = {value: index for index, value in enumerate(categories)}
    return tuple(indices[value] for value in values), categories


def _unique_labels(values, prefixes):
    counts = {value: values.count(value) for value in set(values)}
    return tuple(
        value if counts[value] == 1 else f"{prefix}:{value}"
        for value, prefix in zip(values, prefixes)
    )


def _matching_atomic_property(datasets, structure_id, role, atom_count):
    import numpy

    matches = tuple(
        value
        for value in datasets
        if (
            isinstance(value, AtomicProperty)
            and value.structure_id == structure_id
            and value.semantic_role == role
        )
    )
    if len(matches) > 1:
        raise ValueError(f"multiple {role} properties match Structure")
    if not matches:
        return None
    dataset = matches[0]
    spec = BIOLOGICAL_NUMERIC_ROLE_SPECS[role]
    if (
        not isinstance(dataset.data, ArrayData)
        or dataset.data.dims != ("atom",)
        or dataset.data.shape != (atom_count,)
    ):
        raise ValueError(f"{role} must be atom-aligned numeric ArrayData")
    if dataset.status not in {DatasetStatus.COMPLETE, DatasetStatus.PARTIAL}:
        raise ValueError(f"{role} status must be complete or partial")
    if dataset.data.unit != spec["unit"]:
        raise ValueError(f"{role} unit must be {spec['unit']}")
    try:
        dtype = numpy.dtype(dataset.data.dtype)
        values = numpy.asarray(dataset.data.values)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{role} must contain real numeric values") from error
    if dtype.kind not in "iuf" or values.dtype.kind not in "iuf":
        raise ValueError(f"{role} must contain real numeric values")
    if values.shape != (atom_count,):
        raise ValueError(f"{role} values do not match declared shape")
    if numpy.any(numpy.isinf(values)):
        raise ValueError(f"{role} must not contain infinite values")
    if (
        numpy.any(numpy.isnan(values))
        and dataset.status is not DatasetStatus.PARTIAL
    ):
        raise ValueError(f"{role} NaN values require partial status")
    return dataset


def _category_hash(categories):
    payload = json.dumps(
        categories,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return sha256(payload).hexdigest()


def biological_point_data(structure, hierarchy, datasets=()):
    """Project typed biological data to atom-aligned view attributes."""
    if not isinstance(structure, Structure):
        raise TypeError("structure must be a Structure")
    if not isinstance(hierarchy, BiologicalHierarchy):
        raise TypeError("hierarchy must be a BiologicalHierarchy")
    if (
        hierarchy.structure_id != structure.id
        or hierarchy.atom_count != len(structure.atomic_numbers)
    ):
        raise ValueError("hierarchy does not match Structure")
    if structure.atomic_identity is None:
        raise ValueError("biological Structure requires atomic identity")
    atom_count = hierarchy.atom_count
    residue_indices = tuple(
        int(value) for value in hierarchy.atom_sites.residue_indices.values
    )
    chain_indices = tuple(
        hierarchy.residues[index].chain_index for index in residue_indices
    )
    raw_chain_labels = tuple(
        chain.chain_id if chain.chain_id else f"[blank {chain.segment_index}]"
        for chain in hierarchy.chains
    )
    chain_labels = _unique_labels(
        raw_chain_labels,
        tuple(
            f"segment {chain.segment_index}" for chain in hierarchy.chains
        ),
    )
    raw_residue_labels = tuple(
        (
            f"{residue.residue_name} {residue.sequence_number}"
            f"{residue.insertion_code}"
        )
        for residue in hierarchy.residues
    )
    residue_labels = _unique_labels(
        raw_residue_labels,
        tuple(chain_labels[value.chain_index] for value in hierarchy.residues),
    )
    residue_names, residue_name_categories = _categorical(
        tuple(
            hierarchy.residues[index].residue_name
            for index in residue_indices
        )
    )
    categorical = {
        "cbq_chain_code": (chain_indices, chain_labels, -1),
        "cbq_residue_code": (residue_indices, residue_labels, -1),
        "cbq_residue_name_code": (
            residue_names,
            residue_name_categories,
            -1,
        ),
        "cbq_altloc_code": (
            tuple(
                int(value)
                for value in hierarchy.atom_sites.alternate_locations.codes.values
            ),
            hierarchy.atom_sites.alternate_locations.categories,
            hierarchy.atom_sites.alternate_locations.missing_code,
        ),
        "cbq_record_kind_code": (
            tuple(
                int(value)
                for value in hierarchy.atom_sites.record_kinds.codes.values
            ),
            hierarchy.atom_sites.record_kinds.categories,
            hierarchy.atom_sites.record_kinds.missing_code,
        ),
        "cbq_atom_name_code": (
            tuple(
                int(value)
                for value in structure.atomic_identity.atom_names.codes.values
            ),
            structure.atomic_identity.atom_names.categories,
            structure.atomic_identity.atom_names.missing_code,
        ),
    }
    result = {
        name: tuple(values)
        for name, (values, _categories, _missing_code) in categorical.items()
    }
    result["cbq_residue_number"] = tuple(
        hierarchy.residues[index].sequence_number
        for index in residue_indices
    )
    matched = {}
    for role, spec in BIOLOGICAL_NUMERIC_ROLE_SPECS.items():
        dataset = _matching_atomic_property(
            datasets,
            structure.id,
            role,
            atom_count,
        )
        matched[role] = dataset
        source_values = (
            (float("nan"),) * atom_count
            if dataset is None
            else tuple(float(value) for value in dataset.data.values)
        )
        valid = tuple(isfinite(value) for value in source_values)
        values = tuple(
            value if value_valid else 0.0
            for value, value_valid in zip(source_values, valid, strict=True)
        )
        name = spec["attribute"]
        result[name] = values
        result[f"{name}_valid"] = valid
    for name, (values, _categories, missing_code) in categorical.items():
        result[f"{name}_valid"] = tuple(
            value != missing_code for value in values
        )
    result["categories"] = {
        name: tuple(categories)
        for name, (_values, categories, _missing_code) in sorted(
            categorical.items()
        )
    }
    result["category_hashes"] = {
        name: _category_hash(categories)
        for name, categories in result["categories"].items()
    }
    bindings = {}
    for role, spec in BIOLOGICAL_NUMERIC_ROLE_SPECS.items():
        dataset = matched[role]
        bindings[role] = {
            "role": role,
            "id": None if dataset is None else str(dataset.id),
            "revision": None if dataset is None else dataset.revision,
            "unit": spec["unit"],
            "missing_policy": spec["missing_policy"],
        }
    result["dataset_bindings"] = bindings
    return result


def default_altloc_mask(structure, hierarchy, datasets=()):
    """Choose blank altloc, else highest finite occupancy, per atom site."""
    projection = biological_point_data(structure, hierarchy, datasets)
    alternate_locations = _categorical_values(
        hierarchy.atom_sites.alternate_locations
    )
    atom_names = _categorical_values(structure.atomic_identity.atom_names)
    record_kinds = _categorical_values(hierarchy.atom_sites.record_kinds)
    residue_indices = tuple(
        int(value) for value in hierarchy.atom_sites.residue_indices.values
    )
    occupancy = projection["cbq_occupancy"]
    occupancy_valid = projection["cbq_occupancy_valid"]
    groups = {}
    for index, identity in enumerate(
        zip(residue_indices, atom_names, record_kinds)
    ):
        groups.setdefault(identity, []).append(index)
    selected = [False] * hierarchy.atom_count
    for indices in groups.values():
        blank = next(
            (
                index
                for index in indices
                if alternate_locations[index] is None
            ),
            None,
        )
        chosen = (
            blank
            if blank is not None
            else max(
                indices,
                key=lambda index: (
                    occupancy[index]
                    if occupancy_valid[index]
                    else float("-inf")
                ),
            )
        )
        selected[chosen] = True
    return tuple(selected)


@dataclass(frozen=True, slots=True)
class StructureViewSettings:
    atom_scale: float = 1.0
    bond_scale: float = 1.0
    attach_ball_and_stick: bool = True
    display_periodic_images: bool = True

    def __post_init__(self):
        for name in ("atom_scale", "bond_scale"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0.0
            ):
                raise ValueError(f"{name} must be a finite positive number")
        for name in ("attach_ball_and_stick", "display_periodic_images"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a bool")


def _legacy_bond_order(order, aromatic):
    if aromatic or abs(order - 1.5) <= 1.0e-8:
        return 12
    if order <= 0.0:
        return 0
    return max(1, min(3, int(round(order))))


def _structure_view_data(
    structure,
    topology=None,
    settings=None,
    *,
    selective_dynamics=None,
    periodic_boundary_tolerance=None,
    biological_hierarchy=None,
    atomic_properties=(),
):
    import numpy

    if not isinstance(structure, Structure):
        raise TypeError("structure must be a Structure")
    if topology is not None and not isinstance(topology, TopologyRecord):
        raise TypeError("topology must be a TopologyRecord or None")
    if topology is not None and topology.structure_id != structure.id:
        raise ValueError("topology does not match structure")
    if settings is None:
        settings = StructureViewSettings()
    if not isinstance(settings, StructureViewSettings):
        raise TypeError("settings must be StructureViewSettings")
    scale = _coordinate_scale(structure.coordinates.unit)
    coordinates = numpy.asarray(structure.coordinates.values, dtype=float) * scale
    if numpy.iscomplexobj(coordinates) or not numpy.all(numpy.isfinite(coordinates)):
        raise ValueError("structure coordinates must be finite and real")
    if periodic_boundary_tolerance is not None:
        if (
            structure.periodic is None
            or isinstance(periodic_boundary_tolerance, bool)
            or not isinstance(periodic_boundary_tolerance, (int, float))
            or not isfinite(periodic_boundary_tolerance)
            or periodic_boundary_tolerance < 0.0
        ):
            raise ValueError(
                "periodic_boundary_tolerance requires a periodic Structure "
                "and a finite non-negative value"
            )
        fractional = numpy.asarray(
            structure.periodic.fractional_coordinates.values,
            dtype=float,
        ).copy()
        for axis, enabled in enumerate(structure.periodic.pbc):
            if enabled:
                fractional[:, axis] %= 1.0
                values = fractional[:, axis]
                values[
                    (numpy.abs(values) <= periodic_boundary_tolerance)
                    | (
                        numpy.abs(values - 1.0)
                        <= periodic_boundary_tolerance
                    )
                ] = 0.0
        coordinates = (
            fractional
            @ numpy.asarray(structure.cell.values, dtype=float)
            * scale
        )

    atom_count = len(structure.atomic_numbers)
    selective = None
    if selective_dynamics is not None:
        if (
            not isinstance(selective_dynamics, AtomicProperty)
            or selective_dynamics.structure_id != structure.id
            or selective_dynamics.semantic_role != "selective_dynamics"
            or selective_dynamics.data.dims != ("atom", "xyz")
            or selective_dynamics.data.shape != (atom_count, 3)
        ):
            raise ValueError(
                "selective_dynamics must match the Structure atom axes"
            )
        selective = numpy.asarray(
            selective_dynamics.data.values,
            dtype=numpy.bool_,
        )
    elements = tuple(
        _ELEMENT_BY_NUMBER.get(number, ("Dummy", ELEMENTS_DEFAULT["Dummy"]))
        for number in structure.atomic_numbers
    )
    point_data = {
        "atomic_num": tuple(structure.atomic_numbers),
        "cbq_atom_id": tuple(range(atom_count)),
        "vdw_radius": tuple(float(data[7]) for _symbol, data in elements),
        "radius": tuple(float(data[5]) for _symbol, data in elements),
        "atom_scale_f": (float(settings.atom_scale),) * atom_count,
        "colour": tuple(
            component
            for _symbol, data in elements
            for component in data[3]
        ),
        "siteid": (0,) * atom_count,
        "u_scale": (1.0, 1.0, 1.0) * atom_count,
        "u_v1": (1.0, 0.0, 0.0) * atom_count,
        "u_v2": (0.0, 1.0, 0.0) * atom_count,
        "u_v3": (0.0, 0.0, 1.0) * atom_count,
        "element_symbols": tuple(symbol for symbol, _data in elements),
        "cbq_selective_x": (
            () if selective is None else tuple(map(bool, selective[:, 0]))
        ),
        "cbq_selective_y": (
            () if selective is None else tuple(map(bool, selective[:, 1]))
        ),
        "cbq_selective_z": (
            () if selective is None else tuple(map(bool, selective[:, 2]))
        ),
        "selective_atom_ids": (
            ()
            if selective is None
            else tuple(
                index
                for index, flags in enumerate(selective)
                if not bool(numpy.all(flags))
            )
        ),
    }
    if biological_hierarchy is not None:
        biological = biological_point_data(
            structure,
            biological_hierarchy,
            atomic_properties,
        )
        point_data.update(
            {
                name: values
                for name, values in biological.items()
                if name not in {"categories", "category_hashes"}
            }
        )
        active = default_altloc_mask(
            structure,
            biological_hierarchy,
            atomic_properties,
        )
        point_data["cbq_selected"] = active
        point_data["cbq_visible"] = active
        point_data["biological_categories"] = biological["categories"]
        point_data["biological_category_hashes"] = biological[
            "category_hashes"
        ]
        point_data["biological_dataset_bindings"] = biological[
            "dataset_bindings"
        ]
        point_data["biological_hierarchy_id"] = biological_hierarchy.id
        point_data["biological_hierarchy_revision"] = (
            biological_hierarchy.revision
        )
    if topology is None:
        return {
            **point_data,
            "coordinates": tuple(map(tuple, coordinates.tolist())),
            "primary_edges": (),
            "primary_bond_ids": (),
            "bond_order": (),
            "cbq_bond_order": (),
            "bond_scale_f": (),
            "ring_num": (),
            "is_aromatic": (),
            "periodic_segments": (),
            "settings": settings,
        }

    indices = numpy.asarray(topology.bond_indices.values, dtype=int)
    orders = numpy.asarray(topology.bond_orders.values, dtype=float)
    aromatic = (
        numpy.zeros(len(indices), dtype=bool)
        if topology.aromatic_flags is None
        else numpy.asarray(topology.aromatic_flags.values, dtype=bool)
    )
    shifts = (
        numpy.zeros((len(indices), 3), dtype=int)
        if topology.bond_lattice_shifts is None
        else numpy.asarray(topology.bond_lattice_shifts.values, dtype=int)
    )
    primary = []
    periodic_segments = []
    cell = (
        None
        if structure.cell is None
        else numpy.asarray(structure.cell.values, dtype=float) * scale
    )
    periodic_coordinates = coordinates
    winding = numpy.zeros_like(coordinates)
    if structure.periodic is not None and len(indices):
        periodic_coordinates, _inverse_cell, winding = _pbc_primary_coordinates(
            coordinates,
            cell,
            structure.periodic.pbc,
        )
    for bond_id, ((left, right), order, is_aromatic, shift) in enumerate(
        zip(indices, orders, aromatic, shifts)
    ):
        shift_tuple = tuple(map(int, shift))
        legacy_order = _legacy_bond_order(float(order), bool(is_aromatic))
        if shift_tuple == (0, 0, 0) and numpy.array_equal(
            winding[left],
            winding[right],
        ):
            if left == right:
                raise ValueError("zero-shift topology edge cannot connect an atom to itself")
            primary.append(
                (
                    bond_id,
                    int(left),
                    int(right),
                    legacy_order,
                    float(order),
                    bool(is_aromatic),
                )
            )
            continue
        if cell is None:
            raise ValueError("periodic topology shifts require a structure cell")
        periodic_segments.append(
            {
                "bond_id": bond_id,
                "atom_ids": (int(left), int(right)),
                "lattice_shift": shift_tuple,
                "coordinates": (
                    tuple(map(float, periodic_coordinates[left])),
                    tuple(
                        map(
                            float,
                            periodic_coordinates[right]
                            + numpy.asarray(shift_tuple, dtype=float) @ cell,
                        )
                    ),
                ),
                "bond_order": legacy_order,
                "cbq_bond_order": float(order),
                "is_aromatic": bool(is_aromatic),
            }
        )
    return {
        **point_data,
        "coordinates": tuple(map(tuple, coordinates.tolist())),
        "primary_edges": tuple((item[1], item[2]) for item in primary),
        "primary_bond_ids": tuple(item[0] for item in primary),
        "bond_order": tuple(item[3] for item in primary),
        "cbq_bond_order": tuple(item[4] for item in primary),
        "bond_scale_f": (float(settings.bond_scale),) * len(primary),
        "ring_num": (0,) * len(primary),
        "is_aromatic": tuple(item[5] for item in primary),
        "periodic_segments": tuple(periodic_segments),
        "settings": settings,
    }


def _attribute(mesh, name, data_type, domain):
    attribute = mesh.attributes.get(name)
    if attribute is not None and (
        attribute.data_type != data_type or attribute.domain != domain
    ):
        mesh.attributes.remove(attribute)
        attribute = None
    if attribute is None:
        attribute = mesh.attributes.new(name, data_type, domain)
    return attribute


def _write_attribute(mesh, name, data_type, field, values, domain="POINT"):
    attribute = _attribute(mesh, name, data_type, domain)
    attribute.data.foreach_set(field, values)
    return attribute


def _write_point_attributes(mesh, data, *, atom_ids=None):
    if atom_ids is None:
        atom_ids = data["cbq_atom_id"]
        atomic_numbers = data["atomic_num"]
    else:
        atomic_numbers = tuple(data["atomic_num"][index] for index in atom_ids)
    count = len(atom_ids)
    _write_attribute(mesh, "atomic_num", "INT", "value", atomic_numbers)
    _write_attribute(mesh, "cbq_atom_id", "INT", "value", atom_ids)
    for name in ("vdw_radius", "radius", "atom_scale_f"):
        values = (
            data[name]
            if atom_ids == data["cbq_atom_id"]
            else tuple(data[name][index] for index in atom_ids)
        )
        _write_attribute(mesh, name, "FLOAT", "value", values)
    colors = tuple(
        data["colour"][index * 4 + component]
        for index in atom_ids
        for component in range(4)
    )
    _write_attribute(mesh, "colour", "FLOAT_COLOR", "color", colors)
    site_ids = (
        data["siteid"]
        if atom_ids == data["cbq_atom_id"]
        else tuple(data["siteid"][index] for index in atom_ids)
    )
    _write_attribute(mesh, "siteid", "INT", "value", site_ids)
    for name, vector in (
        ("u_scale", (1.0, 1.0, 1.0)),
        ("u_v1", (1.0, 0.0, 0.0)),
        ("u_v2", (0.0, 1.0, 0.0)),
        ("u_v3", (0.0, 0.0, 1.0)),
    ):
        _write_attribute(
            mesh,
            name,
            "FLOAT_VECTOR",
            "vector",
            vector * count,
        )
    if data["cbq_selective_x"]:
        for name in (
            "cbq_selective_x",
            "cbq_selective_y",
            "cbq_selective_z",
        ):
            values = (
                data[name]
                if atom_ids == data["cbq_atom_id"]
                else tuple(data[name][index] for index in atom_ids)
            )
            _write_attribute(mesh, name, "BOOLEAN", "value", values)


def _write_biological_attributes(obj, data):
    categories = data.get("biological_categories")
    if categories is None:
        return
    for name in categories:
        _write_attribute(obj.data, name, "INT", "value", data[name])
        _write_attribute(
            obj.data,
            f"{name}_valid",
            "BOOLEAN",
            "value",
            data[f"{name}_valid"],
        )
    _write_attribute(
        obj.data,
        "cbq_residue_number",
        "INT",
        "value",
        data["cbq_residue_number"],
    )
    for spec in BIOLOGICAL_NUMERIC_ROLE_SPECS.values():
        name = spec["attribute"]
        _write_attribute(obj.data, name, "FLOAT", "value", data[name])
        _write_attribute(
            obj.data,
            f"{name}_valid",
            "BOOLEAN",
            "value",
            data[f"{name}_valid"],
        )
    for name in ("cbq_selected", "cbq_visible"):
        _write_attribute(obj.data, name, "BOOLEAN", "value", data[name])
    obj["cb_biological_hierarchy_id"] = str(
        data["biological_hierarchy_id"]
    )
    obj["cb_biological_hierarchy_revision"] = data[
        "biological_hierarchy_revision"
    ]
    obj["cb_biological_categories"] = json.dumps(
        categories,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    obj["cb_biological_category_hashes"] = json.dumps(
        data["biological_category_hashes"],
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    obj["cb_biological_dataset_bindings"] = json.dumps(
        data["biological_dataset_bindings"],
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _write_edge_attributes(
    mesh,
    *,
    bond_ids,
    bond_orders,
    exact_orders,
    aromatic,
    bond_scale,
):
    _write_attribute(
        mesh, "cbq_bond_id", "INT", "value", bond_ids, domain="EDGE"
    )
    _write_attribute(
        mesh, "bond_order", "INT", "value", bond_orders, domain="EDGE"
    )
    _write_attribute(
        mesh,
        "cbq_bond_order",
        "FLOAT",
        "value",
        exact_orders,
        domain="EDGE",
    )
    _write_attribute(
        mesh,
        "bond_scale_f",
        "FLOAT",
        "value",
        bond_scale,
        domain="EDGE",
    )
    _write_attribute(
        mesh,
        "ring_num",
        "INT",
        "value",
        (0,) * len(bond_ids),
        domain="EDGE",
    )
    _write_attribute(
        mesh,
        "is_aromatic",
        "BOOLEAN",
        "value",
        aromatic,
        domain="EDGE",
    )


def _periodic_display_object(main, collection, data):
    import bpy

    segments = data["periodic_segments"]
    mesh = bpy.data.meshes.new(f"{main.name} Periodic Display")
    display = None
    modifier = None
    group = None
    try:
        vertices = tuple(
            coordinate
            for segment in segments
            for coordinate in segment["coordinates"]
        )
        edges = tuple((index * 2, index * 2 + 1) for index in range(len(segments)))
        mesh.from_pydata(vertices, edges, [])
        display = bpy.data.objects.new(mesh.name, mesh)
        collection.objects.link(display)
        atom_ids = tuple(
            atom_id for segment in segments for atom_id in segment["atom_ids"]
        )
        _write_point_attributes(mesh, data, atom_ids=atom_ids)
        _write_attribute(
            mesh,
            "cbq_display_only",
            "BOOLEAN",
            "value",
            (True,) * len(vertices),
        )
        _write_edge_attributes(
            mesh,
            bond_ids=tuple(segment["bond_id"] for segment in segments),
            bond_orders=tuple(segment["bond_order"] for segment in segments),
            exact_orders=tuple(
                segment["cbq_bond_order"] for segment in segments
            ),
            aromatic=tuple(segment["is_aromatic"] for segment in segments),
            bond_scale=(float(data["settings"].bond_scale),) * len(segments),
        )
        display["cb_structure_contract"] = _PERIODIC_DISPLAY_CONTRACT
        display["cbq_contract"] = _PERIODIC_DISPLAY_CONTRACT
        display["cbq_contract_version"] = _VIEW_CONTRACT_VERSION
        display["cb_structure_id"] = main["cb_structure_id"]
        display.hide_render = True
        display.hide_set(True)
        display.parent = main

        modifier = main.modifiers.new(_PERIODIC_MODIFIER_NAME, "NODES")
        group = bpy.data.node_groups.new(
            f"{main.name} Periodic Display Nodes",
            "GeometryNodeTree",
        )
        group.is_modifier = True
        group.interface.new_socket(
            name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
        )
        group.interface.new_socket(
            name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        group_input = group.nodes.new("NodeGroupInput")
        group_output = group.nodes.new("NodeGroupOutput")
        object_info = group.nodes.new("GeometryNodeObjectInfo")
        object_info.transform_space = "RELATIVE"
        object_info.inputs["Object"].default_value = display
        object_info.inputs["As Instance"].default_value = False
        join = group.nodes.new("GeometryNodeJoinGeometry")
        group.links.new(group_input.outputs["Geometry"], join.inputs["Geometry"])
        group.links.new(object_info.outputs["Geometry"], join.inputs["Geometry"])
        group.links.new(join.outputs["Geometry"], group_output.inputs["Geometry"])
        group["cbq_contract"] = _PERIODIC_DISPLAY_CONTRACT
        group["cbq_contract_version"] = _VIEW_CONTRACT_VERSION
        modifier.node_group = group
        modifier["cbq_contract"] = _PERIODIC_DISPLAY_CONTRACT
        modifier["cbq_contract_version"] = _VIEW_CONTRACT_VERSION
        ball_stick = next(
            (
                item
                for item in main.modifiers
                if item.node_group is not None
                and _is_view_contract(
                    item.node_group,
                    _BALL_STICK_CONTRACT,
                )
                and _is_view_contract(item, _BALL_STICK_CONTRACT)
            ),
            None,
        )
        if ball_stick is not None:
            main.modifiers.move(
                tuple(main.modifiers).index(modifier),
                tuple(main.modifiers).index(ball_stick),
            )
        main["cb_periodic_display_object"] = display.name
        main["cb_periodic_display_bond_count"] = len(segments)
        return display
    except BaseException as error:
        if modifier is not None:
            error = _run_cleanup(
                error,
                "periodic display modifier cleanup failed",
                lambda: main.modifiers.remove(modifier),
            )
        if display is not None:
            error = _run_cleanup(
                error,
                "periodic display object cleanup failed",
                lambda: bpy.data.objects.remove(display, do_unlink=True),
            )
        if mesh.users == 0:
            error = _run_cleanup(
                error,
                "periodic display mesh cleanup failed",
                lambda: bpy.data.meshes.remove(mesh),
            )
        if group is not None and group.users == 0:
            error = _run_cleanup(
                error,
                "periodic display node-group cleanup failed",
                lambda: bpy.data.node_groups.remove(group),
            )
        raise error


def _ensure_selective_marker_group():
    import bpy

    group = bpy.data.node_groups.get(_SELECTIVE_MARKER_GROUP)
    if group is not None:
        if (
            group.bl_idname != "GeometryNodeTree"
            or not _is_view_contract(group, _SELECTIVE_MARKER_CONTRACT)
        ):
            raise RuntimeError(
                f"incompatible node group already uses {_SELECTIVE_MARKER_GROUP}"
            )
        return group
    group = bpy.data.node_groups.new(
        _SELECTIVE_MARKER_GROUP,
        "GeometryNodeTree",
    )
    try:
        group.is_modifier = True
        group.interface.new_socket(
            name="Geometry",
            in_out="INPUT",
            socket_type="NodeSocketGeometry",
        )
        group.interface.new_socket(
            name="Geometry",
            in_out="OUTPUT",
            socket_type="NodeSocketGeometry",
        )
        group_input = group.nodes.new("NodeGroupInput")
        group_output = group.nodes.new("NodeGroupOutput")
        points = group.nodes.new("GeometryNodeMeshToPoints")
        points.mode = "VERTICES"
        points.inputs["Radius"].default_value = 0.14
        sphere = group.nodes.new("GeometryNodeMeshIcoSphere")
        sphere.inputs["Radius"].default_value = 0.14
        sphere.inputs["Subdivisions"].default_value = 1
        instance = group.nodes.new("GeometryNodeInstanceOnPoints")
        group.links.new(group_input.outputs["Geometry"], points.inputs["Mesh"])
        group.links.new(points.outputs["Points"], instance.inputs["Points"])
        group.links.new(sphere.outputs["Mesh"], instance.inputs["Instance"])
        group.links.new(
            instance.outputs["Instances"],
            group_output.inputs["Geometry"],
        )
        group["cbq_contract"] = _SELECTIVE_MARKER_CONTRACT
        group["cbq_contract_version"] = _VIEW_CONTRACT_VERSION
        return group
    except BaseException as error:
        if group.users == 0:
            error = _run_cleanup(
                error,
                "selective marker node-group cleanup failed",
                lambda: bpy.data.node_groups.remove(group),
            )
        raise error


def _selective_marker_object(main, collection, data):
    import bpy

    atom_ids = data["selective_atom_ids"]
    if not atom_ids:
        return None
    mesh = bpy.data.meshes.new(f"{main.name} Selective Constraints")
    marker = None
    group = None
    group_created = bpy.data.node_groups.get(_SELECTIVE_MARKER_GROUP) is None
    try:
        mesh.from_pydata(
            tuple(data["coordinates"][index] for index in atom_ids),
            (),
            (),
        )
        marker = bpy.data.objects.new(mesh.name, mesh)
        collection.objects.link(marker)
        _write_point_attributes(mesh, data, atom_ids=atom_ids)
        modifier = marker.modifiers.new(
            _SELECTIVE_MARKER_GROUP,
            "NODES",
        )
        group = _ensure_selective_marker_group()
        modifier.node_group = group
        modifier["cbq_contract"] = _SELECTIVE_MARKER_CONTRACT
        modifier["cbq_contract_version"] = _VIEW_CONTRACT_VERSION
        marker.parent = main
        marker.show_in_front = True
        marker.hide_render = True
        marker["cbq_contract"] = _SELECTIVE_MARKER_CONTRACT
        marker["cbq_contract_version"] = _VIEW_CONTRACT_VERSION
        marker["cb_structure_id"] = main["cb_structure_id"]
        main["cb_selective_marker_object"] = marker.name
        main["cb_selective_constraint_count"] = len(atom_ids)
        main["cb_selective_constraints_visible"] = True
        mesh.update()
        return marker
    except BaseException as error:
        if marker is not None:
            error = _run_cleanup(
                error,
                "selective marker object cleanup failed",
                lambda: bpy.data.objects.remove(marker, do_unlink=True),
            )
        if mesh.users == 0:
            error = _run_cleanup(
                error,
                "selective marker mesh cleanup failed",
                lambda: bpy.data.meshes.remove(mesh),
            )
        if group_created and group is not None and group.users == 0:
            error = _run_cleanup(
                error,
                "selective marker node-group cleanup failed",
                lambda: bpy.data.node_groups.remove(group),
            )
        raise error


def _set_topology_metadata(obj, topology):
    names = (
        "cb_topology_id",
        "cb_topology_revision",
        "cbq_topology_source",
        "cb_topology_quality",
    )
    if topology is None:
        for name in names:
            if name in obj:
                del obj[name]
        obj["cb_topology_render_identity"] = "atoms-only"
        return
    obj["cb_topology_id"] = str(topology.id)
    obj["cb_topology_revision"] = topology.revision
    obj["cbq_topology_source"] = topology.source_kind.value
    obj["cb_topology_quality"] = topology.quality_status.value
    obj["cb_topology_render_identity"] = f"{topology.id}:{topology.revision}"


def _remove_periodic_display(obj):
    import bpy

    groups = []
    for modifier in tuple(obj.modifiers):
        if (
            modifier.node_group is not None
            and _is_view_contract(
                modifier.node_group,
                _PERIODIC_DISPLAY_CONTRACT,
            )
            and _is_view_contract(
                modifier,
                _PERIODIC_DISPLAY_CONTRACT,
            )
        ):
            groups.append(modifier.node_group)
            obj.modifiers.remove(modifier)
    display_name = obj.get("cb_periodic_display_object")
    display = (
        bpy.data.objects.get(display_name)
        if isinstance(display_name, str)
        else None
    )
    if (
        display is not None
        and (
            display.parent != obj
            or not _is_view_contract(
                display,
                _PERIODIC_DISPLAY_CONTRACT,
            )
        )
    ):
        display = None
    if display is not None:
        mesh = display.data
        bpy.data.objects.remove(display, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for group in groups:
        if group.users == 0:
            bpy.data.node_groups.remove(group)
    for name in (
        "cb_periodic_display_object",
        "cb_periodic_display_bond_count",
    ):
        if name in obj:
            del obj[name]


def update_structure_view_topology(
    obj,
    structure,
    topology=None,
    settings=None,
):
    import bmesh
    import bpy

    if not isinstance(obj, bpy.types.Object) or obj.type != "MESH":
        raise TypeError("obj must be a Blender Mesh object")
    if obj.get("cb_structure_contract") != _STRUCTURE_CONTRACT:
        raise ValueError("obj is not a ChemBlender Structure view")
    if obj.get("cb_structure_id") != str(structure.id):
        raise ValueError("Structure does not match the Blender object")
    tolerance = (
        obj.get("cbq_periodic_boundary_tolerance")
        if obj.get("cbq_periodic_representation") != "source_sites"
        else None
    )
    data = _structure_view_data(
        structure,
        topology,
        settings,
        periodic_boundary_tolerance=tolerance,
    )
    if len(obj.data.vertices) != len(data["coordinates"]):
        raise ValueError("Structure atom count does not match the Blender object")

    mesh = obj.data
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        for edge in tuple(bm.edges):
            bm.edges.remove(edge)
        bm.verts.ensure_lookup_table()
        for left, right in data["primary_edges"]:
            bm.edges.new((bm.verts[left], bm.verts[right]))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    _write_edge_attributes(
        mesh,
        bond_ids=data["primary_bond_ids"],
        bond_orders=data["bond_order"],
        exact_orders=data["cbq_bond_order"],
        aromatic=data["is_aromatic"],
        bond_scale=data["bond_scale_f"],
    )
    _remove_periodic_display(obj)
    if data["periodic_segments"] and data["settings"].display_periodic_images:
        collection = (
            obj.users_collection[0]
            if obj.users_collection
            else bpy.context.collection
        )
        _periodic_display_object(obj, collection, data)
    _set_topology_metadata(obj, topology)
    mesh.update()
    return obj


def create_structure_view(
    structure,
    topology=None,
    settings=None,
    *,
    selective_dynamics=None,
    periodic_boundary_tolerance=None,
    biological_hierarchy=None,
    atomic_properties=(),
    name="ChemBlender Structure",
    collection=None,
):
    import bpy

    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")
    if collection is None:
        collection = bpy.context.collection
    if collection is None:
        raise ValueError("a Blender collection is required")
    data = _structure_view_data(
        structure,
        topology,
        settings,
        selective_dynamics=selective_dynamics,
        periodic_boundary_tolerance=periodic_boundary_tolerance,
        biological_hierarchy=biological_hierarchy,
        atomic_properties=atomic_properties,
    )
    settings = data["settings"]
    mesh = bpy.data.meshes.new(name)
    obj = None
    try:
        mesh.from_pydata(data["coordinates"], data["primary_edges"], [])
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        _write_point_attributes(mesh, data)
        _write_biological_attributes(obj, data)
        _write_edge_attributes(
            mesh,
            bond_ids=data["primary_bond_ids"],
            bond_orders=data["bond_order"],
            exact_orders=data["cbq_bond_order"],
            aromatic=data["is_aromatic"],
            bond_scale=data["bond_scale_f"],
        )
        obj["Type"] = "scaffold"
        obj["Elements"] = str(sorted(set(data["element_symbols"])))
        obj["cb_structure_id"] = str(structure.id)
        obj["cb_structure_revision"] = structure.revision
        obj["cb_structure_contract"] = _STRUCTURE_CONTRACT
        obj["cb_source_coordinate_unit"] = structure.coordinates.unit
        obj["cb_display_coordinate_unit"] = "angstrom"
        obj["cb_coordinate_scale"] = _coordinate_scale(
            structure.coordinates.unit
        )
        _set_topology_metadata(obj, topology)
        if structure.periodic is not None:
            scale = _coordinate_scale(structure.coordinates.unit)
            obj["cb_periodic"] = True
            obj["cb_periodic_cell"] = tuple(
                float(value) * scale
                for row in structure.cell.values
                for value in row
            )
            obj["cb_pbc"] = structure.periodic.pbc
        if data["periodic_segments"] and settings.display_periodic_images:
            _periodic_display_object(obj, collection, data)
        _selective_marker_object(obj, collection, data)
        if settings.attach_ball_and_stick:
            from .. import node

            node.ensure_structure_ball_stick_modifier(obj)
        mesh.update()
        return obj
    except BaseException as error:
        if obj is not None and obj.name in bpy.data.objects:
            error = _run_cleanup(
                error,
                "Structure view cleanup failed",
                lambda: remove_structure_view(obj),
            )
        elif mesh.users == 0:
            error = _run_cleanup(
                error,
                "Structure mesh cleanup failed",
                lambda: bpy.data.meshes.remove(mesh),
            )
        raise error


def remove_structure_view(obj):
    import bpy

    if not isinstance(obj, bpy.types.Object):
        raise TypeError("obj must be a Blender Object")
    def owned_child(property_name, contract):
        name = obj.get(property_name)
        child = (
            bpy.data.objects.get(name) if isinstance(name, str) else None
        )
        return (
            child
            if child is not None
            and getattr(child, "parent", None) == obj
            and _is_view_contract(child, contract)
            else None
        )

    display = owned_child(
        "cb_periodic_display_object",
        _PERIODIC_DISPLAY_CONTRACT,
    )
    marker = owned_child(
        "cb_selective_marker_object",
        _SELECTIVE_MARKER_CONTRACT,
    )
    site_display = owned_child(
        "cbq_periodic_site_display_object",
        _PERIODIC_SITE_DISPLAY_CONTRACT,
    )
    cell_display = owned_child(
        "cbq_periodic_cell_object",
        "periodic_cell_display_v1",
    )
    adp_display = owned_child(
        "cbq_periodic_adp_object",
        "periodic_adp_display_v1",
    )
    occupancy_display = owned_child(
        "cbq_periodic_occupancy_object",
        "periodic_occupancy_display_v1",
    )
    occupancy_material_name = obj.get("cbq_periodic_occupancy_material")
    occupancy_material = (
        bpy.data.materials.get(occupancy_material_name)
        if isinstance(occupancy_material_name, str)
        else None
    )
    if (
        occupancy_material is not None
        and not _is_view_contract(
            occupancy_material,
            "periodic_occupancy_material_v1",
        )
    ):
        occupancy_material = None
    groups = tuple(
        modifier.node_group
        for modifier in obj.modifiers
        if modifier.node_group is not None
        and any(
            _is_view_contract(modifier.node_group, contract)
            and _is_view_contract(modifier, contract)
            for contract in (
                _BALL_STICK_CONTRACT,
                _PERIODIC_DISPLAY_CONTRACT,
            )
        )
    )
    data_blocks = [obj.data]
    if display is not None:
        data_blocks.append(display.data)
        bpy.data.objects.remove(display, do_unlink=True)
    if marker is not None:
        data_blocks.append(marker.data)
        groups += tuple(
            modifier.node_group
            for modifier in marker.modifiers
            if modifier.node_group is not None
            and _is_view_contract(
                modifier.node_group,
                _SELECTIVE_MARKER_CONTRACT,
            )
            and _is_view_contract(modifier, _SELECTIVE_MARKER_CONTRACT)
        )
        bpy.data.objects.remove(marker, do_unlink=True)
    if site_display is not None:
        data_blocks.append(site_display.data)
        groups += tuple(
            modifier.node_group
            for modifier in site_display.modifiers
            if modifier.node_group is not None
            and any(
                _is_view_contract(modifier.node_group, contract)
                and _is_view_contract(modifier, contract)
                for contract in (
                    _BALL_STICK_CONTRACT,
                    _PERIODIC_SITE_DISPLAY_CONTRACT,
                )
            )
        )
        bpy.data.objects.remove(site_display, do_unlink=True)
    for child, contract in (
        (cell_display, "periodic_cell_edges_v1"),
        (adp_display, "periodic_thermal_ellipsoid_v1"),
        (occupancy_display, "periodic_site_occupancy_v1"),
    ):
        if child is None:
            continue
        data_blocks.append(child.data)
        groups += tuple(
            modifier.node_group
            for modifier in child.modifiers
            if modifier.node_group is not None
            and _is_view_contract(modifier.node_group, contract)
            and _is_view_contract(modifier, contract)
        )
        bpy.data.objects.remove(child, do_unlink=True)
    bpy.data.objects.remove(obj, do_unlink=True)
    for data in data_blocks:
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)
    unique_groups = []
    for group in groups:
        if group not in unique_groups:
            unique_groups.append(group)
    for group in unique_groups:
        if group.users == 0:
            bpy.data.node_groups.remove(group)
    if occupancy_material is not None and occupancy_material.users == 0:
        bpy.data.materials.remove(occupancy_material)
