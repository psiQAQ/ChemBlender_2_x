from dataclasses import dataclass
from math import isfinite, sqrt

from .detection import LegacySceneDetection, detect_legacy_scene


@dataclass(frozen=True, slots=True)
class LegacyDiagnostic:
    code: str
    message: str
    object_name: str | None = None


@dataclass(frozen=True, slots=True)
class LegacyEdgeSnapshot:
    vertices: tuple[int, int]
    order: int | None
    scale: float | None
    dashed: bool | None


@dataclass(frozen=True, slots=True)
class LegacyCIFAtomSnapshot:
    label: str
    element: str
    coordinates: tuple[float, float, float]
    occupancy: float
    u_iso_equiv: float
    adp_type: str
    uij: tuple[float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class LegacyCIFSnapshot:
    cell: tuple[float, float, float, float, float, float]
    space_group: str
    space_group_number: int
    symmetry_operations: tuple[str, ...]
    atoms: tuple[LegacyCIFAtomSnapshot, ...]


@dataclass(frozen=True, slots=True)
class LegacyMaterialSnapshot:
    name: str
    diffuse_color: tuple[float, float, float, float]
    metallic: float
    roughness: float


@dataclass(frozen=True, slots=True)
class LegacyNodeModifierSnapshot:
    name: str
    node_group_name: str | None
    inputs: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class LegacyObjectSnapshot:
    name: str
    kind: str
    collections: tuple[str, ...]
    atomic_numbers: tuple[int, ...]
    coordinates: tuple[tuple[float, float, float], ...]
    edges: tuple[LegacyEdgeSnapshot, ...]
    radii: tuple[float, ...] | None
    vdw_radii: tuple[float, ...] | None
    atom_scales: tuple[float, ...] | None
    colors: tuple[tuple[float, float, float, float], ...] | None
    cell: tuple[float, float, float, float, float, float] | None
    cif_original: LegacyCIFSnapshot | None
    cif_current: LegacyCIFSnapshot | None
    materials: tuple[LegacyMaterialSnapshot, ...] = ()
    node_modifiers: tuple[LegacyNodeModifierSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class LegacyExtractionReport:
    objects: tuple[LegacyObjectSnapshot, ...]
    diagnostics: tuple[LegacyDiagnostic, ...]
    source_path: str | None


_KNOWN_PROPERTIES = frozenset(
    {
        "Type",
        "Elements",
        "cell lengths",
        "cell angles",
        "space group",
        "SG No.",
        "symops",
    }
)


def _attribute_values(mesh, name, field):
    attribute = mesh.attributes.get(name)
    return None if attribute is None else tuple(getattr(value, field) for value in attribute.data)


def _cell(obj):
    if "cell lengths" not in obj or "cell angles" not in obj:
        return None
    lengths = tuple(float(value) for value in str(obj["cell lengths"]).split(","))
    angles = tuple(float(value) for value in str(obj["cell angles"]).split(","))
    return lengths + angles if len(lengths) == len(angles) == 3 else None


def _cif(value):
    if value is None or not getattr(value, "atom_count", 0):
        return None
    return LegacyCIFSnapshot(
        cell=(float(value.a), float(value.b), float(value.c), float(value.alpha), float(value.beta), float(value.gamma)),
        space_group=str(value.sg_name),
        space_group_number=int(value.sg_num),
        symmetry_operations=tuple(item for item in str(value.sym_ops).split(";") if item),
        atoms=tuple(
            LegacyCIFAtomSnapshot(
                label=str(atom.label),
                element=str(atom.element),
                coordinates=(float(atom.x), float(atom.y), float(atom.z)),
                occupancy=float(atom.occupancy),
                u_iso_equiv=float(atom.u_iso_equiv),
                adp_type=str(atom.adp_type),
                uij=(float(atom.u11), float(atom.u22), float(atom.u33), float(atom.u12), float(atom.u13), float(atom.u23)),
            )
            for atom in value.atoms
        ),
    )


def _display_value(value):
    if type(value) in (str, bool, int):
        return value
    if type(value) is float and isfinite(value):
        return value
    try:
        values = tuple(value)
    except TypeError:
        return None
    if (
        2 <= len(values) <= 4
        and all(type(item) in (int, float) and isfinite(item) for item in values)
    ):
        return tuple(float(item) for item in values)
    return None


def _materials(obj, diagnostics):
    materials = []
    for material in obj.data.materials:
        if material is None:
            continue
        color = tuple(float(value) for value in material.diffuse_color)
        metallic = float(material.metallic)
        roughness = float(material.roughness)
        if (
            len(color) != 4
            or not all(isfinite(value) and 0.0 <= value <= 1.0 for value in color)
            or not isfinite(metallic)
            or not isfinite(roughness)
        ):
            diagnostics.append(LegacyDiagnostic("invalid_material_display", material.name, obj.name))
            continue
        materials.append(LegacyMaterialSnapshot(material.name, color, metallic, roughness))
    return tuple(materials)


def _node_modifiers(obj, diagnostics):
    modifiers = []
    for modifier in obj.modifiers:
        if modifier.type != "NODES":
            continue
        inputs = []
        for name in sorted(modifier.keys()):
            value = _display_value(modifier[name])
            if value is None:
                diagnostics.append(LegacyDiagnostic("unsupported_node_input", f"{modifier.name}.{name}", obj.name))
                continue
            inputs.append((name, value))
        modifiers.append(
            LegacyNodeModifierSnapshot(
                modifier.name,
                modifier.node_group.name if modifier.node_group else None,
                tuple(inputs),
            )
        )
    return tuple(modifiers)


def _has_nonuniform_world_transform(matrix):
    axes = tuple(
        tuple(float(matrix[row][column]) for row in range(3))
        for column in range(3)
    )
    lengths = tuple(sqrt(sum(value * value for value in axis)) for axis in axes)
    if min(lengths) <= 1.0e-12:
        return True
    if max(lengths) - min(lengths) > 1.0e-9:
        return True
    return any(
        abs(sum(left[index] * right[index] for index in range(3)) / (left_length * right_length)) > 1.0e-9
        for index, (left, left_length) in enumerate(zip(axes, lengths))
        for right, right_length in zip(axes[index + 1 :], lengths[index + 1 :])
    )


def _snapshot(obj, detection, diagnostics):
    mesh = obj.data
    atomic_numbers = _attribute_values(mesh, "atomic_num", "value") or ()
    coordinates = tuple(
        tuple(float(component) for component in obj.matrix_world @ vertex.co)
        for vertex in mesh.vertices
    )
    orders = _attribute_values(mesh, "bond_order", "value")
    scales = _attribute_values(mesh, "bond_scale_f", "value")
    dashed = _attribute_values(mesh, "dashed", "value")
    if obj.modifiers:
        diagnostics.append(LegacyDiagnostic("evaluated_geometry_ignored", "scientific coordinates use the original base mesh, not modifier output", obj.name))
    if _has_nonuniform_world_transform(obj.matrix_world):
        diagnostics.append(LegacyDiagnostic("nonuniform_transform", "coordinates were transformed through matrix_world", obj.name))
    diagnostics.extend(
        LegacyDiagnostic("unknown_custom_property", name, obj.name)
        for name in sorted(set(obj.keys()) - _KNOWN_PROPERTIES)
    )
    return LegacyObjectSnapshot(
        name=detection.name,
        kind=detection.kind,
        collections=detection.collections,
        atomic_numbers=tuple(int(value) for value in atomic_numbers),
        coordinates=coordinates,
        edges=tuple(
            LegacyEdgeSnapshot(
                tuple(edge.vertices),
                int(orders[index]) if orders is not None else None,
                float(scales[index]) if scales is not None else None,
                bool(dashed[index]) if dashed is not None else None,
            )
            for index, edge in enumerate(mesh.edges)
        ),
        radii=tuple(float(value) for value in (_attribute_values(mesh, "radius", "value") or ())) or None,
        vdw_radii=tuple(float(value) for value in (_attribute_values(mesh, "vdw_radius", "value") or ())) or None,
        atom_scales=tuple(float(value) for value in (_attribute_values(mesh, "atom_scale_f", "value") or ())) or None,
        colors=tuple(tuple(float(component) for component in value.color) for value in (mesh.attributes.get("colour").data if mesh.attributes.get("colour") else ())) or None,
        cell=_cell(obj),
        cif_original=_cif(getattr(obj, "cif_original", None)),
        cif_current=_cif(getattr(obj, "cif_current", None)),
        materials=_materials(obj, diagnostics),
        node_modifiers=_node_modifiers(obj, diagnostics),
    )


def extract_legacy_objects(detection: LegacySceneDetection | None = None) -> LegacyExtractionReport:
    import bpy

    detection = detection or detect_legacy_scene()
    if not detection.objects:
        return LegacyExtractionReport((), (), None)
    diagnostics = []
    source_path = bpy.data.filepath or None
    if source_path is None:
        diagnostics.append(LegacyDiagnostic("missing_blend_source_path", "legacy scene has no saved blend source path"))
    return LegacyExtractionReport(
        tuple(_snapshot(bpy.data.objects[item.name], item, diagnostics) for item in detection.objects),
        tuple(diagnostics),
        source_path,
    )
