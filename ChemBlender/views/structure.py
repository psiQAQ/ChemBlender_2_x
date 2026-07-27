from dataclasses import dataclass
from math import isfinite

from ..Chem_data import ELEMENTS_DEFAULT
from ..core import Structure, TopologyRecord


_ANGSTROM_SCALE = {"angstrom": 1.0, "bohr": 0.529177210903}
_ELEMENT_BY_NUMBER = {
    data[0]: (symbol, data)
    for symbol, data in ELEMENTS_DEFAULT.items()
    if 0 < data[0] <= 118
}
_STRUCTURE_CONTRACT = "structure_view_v1"
_BALL_STICK_CONTRACT = "structure_ball_stick_v1"
_PERIODIC_DISPLAY_CONTRACT = "structure_periodic_display_v1"
_PERIODIC_MODIFIER_NAME = "ChemBlender Periodic Images"


def _coordinate_scale(unit):
    try:
        return _ANGSTROM_SCALE[unit]
    except KeyError as error:
        raise ValueError(f"unsupported coordinate unit: {unit}") from error


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


def _structure_view_data(structure, topology=None, settings=None):
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

    atom_count = len(structure.atomic_numbers)
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
    }
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
    for bond_id, ((left, right), order, is_aromatic, shift) in enumerate(
        zip(indices, orders, aromatic, shifts)
    ):
        shift_tuple = tuple(map(int, shift))
        legacy_order = _legacy_bond_order(float(order), bool(is_aromatic))
        if shift_tuple == (0, 0, 0):
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
                    tuple(map(float, coordinates[left])),
                    tuple(
                        map(
                            float,
                            coordinates[right]
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
    _write_attribute(mesh, "siteid", "INT", "value", (0,) * count)
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
        modifier.node_group = group
        modifier["cbq_contract"] = _PERIODIC_DISPLAY_CONTRACT
        main["cb_periodic_display_object"] = display.name
        main["cb_periodic_display_bond_count"] = len(segments)
        return display
    except Exception:
        if modifier is not None:
            main.modifiers.remove(modifier)
        if group is not None and group.users == 0:
            bpy.data.node_groups.remove(group)
        if display is not None:
            bpy.data.objects.remove(display, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise


def create_structure_view(
    structure,
    topology=None,
    settings=None,
    *,
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
    data = _structure_view_data(structure, topology, settings)
    settings = data["settings"]
    mesh = bpy.data.meshes.new(name)
    obj = None
    try:
        mesh.from_pydata(data["coordinates"], data["primary_edges"], [])
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        _write_point_attributes(mesh, data)
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
        if topology is not None:
            obj["cb_topology_id"] = str(topology.id)
            obj["cb_topology_revision"] = topology.revision
            obj["cbq_topology_source"] = topology.source_kind.value
            obj["cb_topology_quality"] = topology.quality_status.value
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
        if settings.attach_ball_and_stick:
            from .. import node

            node.ensure_structure_ball_stick_modifier(obj)
        mesh.update()
        return obj
    except Exception:
        if obj is not None and obj.name in bpy.data.objects:
            remove_structure_view(obj)
        elif mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise


def remove_structure_view(obj):
    import bpy

    if not isinstance(obj, bpy.types.Object):
        raise TypeError("obj must be a Blender Object")
    display_name = obj.get("cb_periodic_display_object")
    display = (
        bpy.data.objects.get(display_name)
        if isinstance(display_name, str)
        else None
    )
    groups = tuple(
        modifier.node_group
        for modifier in obj.modifiers
        if modifier.node_group is not None
        and modifier.node_group.get("cbq_contract")
        in {_BALL_STICK_CONTRACT, _PERIODIC_DISPLAY_CONTRACT}
    )
    data_blocks = [obj.data]
    if display is not None:
        data_blocks.append(display.data)
        bpy.data.objects.remove(display, do_unlink=True)
    bpy.data.objects.remove(obj, do_unlink=True)
    for data in data_blocks:
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)
    for group in groups:
        if group.users == 0:
            bpy.data.node_groups.remove(group)
