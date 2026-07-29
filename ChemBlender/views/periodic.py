from dataclasses import dataclass
import json
from math import isfinite

from ..core import Structure
from .structure import (
    _PERIODIC_SITE_DISPLAY_CONTRACT,
    _coordinate_scale,
    _run_cleanup,
    _structure_view_data,
    _write_attribute,
    _write_point_attributes,
    create_structure_view,
    remove_structure_view,
)


_REPRESENTATIONS = {"source_sites", "expanded_cell", "supercell"}
_OCCUPANCY_MODES = {"opacity", "radius", "pie", "split_site"}
_U_COMPONENTS = ("u11", "u22", "u33", "u12", "u13", "u23")


@dataclass(frozen=True, slots=True)
class PeriodicViewSettings:
    representation: str = "source_sites"
    supercell: tuple[int, int, int] = (1, 1, 1)
    boundary_tolerance: float = 1.0e-5
    show_cell: bool = True
    show_axes: bool = False
    occupancy_mode: str = "opacity"
    adp_probability: float = 0.50
    show_constraints: bool = True

    def __post_init__(self):
        if self.representation not in _REPRESENTATIONS:
            raise ValueError("representation is not supported")
        if (
            type(self.supercell) is not tuple
            or len(self.supercell) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
                for value in self.supercell
            )
        ):
            raise ValueError("supercell must contain three positive integers")
        if (
            isinstance(self.boundary_tolerance, bool)
            or not isinstance(self.boundary_tolerance, (int, float))
            or not isfinite(self.boundary_tolerance)
            or self.boundary_tolerance < 0.0
        ):
            raise ValueError(
                "boundary_tolerance must be finite and non-negative"
            )
        if self.occupancy_mode not in _OCCUPANCY_MODES:
            raise ValueError("occupancy_mode is not supported")
        if (
            isinstance(self.adp_probability, bool)
            or not isinstance(self.adp_probability, (int, float))
            or not isfinite(self.adp_probability)
            or not 0.0 < self.adp_probability < 1.0
        ):
            raise ValueError("adp_probability must be between zero and one")
        for name in ("show_cell", "show_axes", "show_constraints"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a bool")


def _categorical(values):
    categories = tuple(dict.fromkeys(values))
    codes = {value: index for index, value in enumerate(categories)}
    return tuple(codes[value] for value in values), categories


def _normalize_fractional(values, pbc, tolerance):
    import numpy

    result = numpy.asarray(values, dtype=float).copy()
    for axis, enabled in enumerate(pbc):
        if enabled:
            result[..., axis] %= 1.0
            axis_values = result[..., axis]
            axis_values[
                (numpy.abs(axis_values) <= tolerance)
                | (numpy.abs(axis_values - 1.0) <= tolerance)
            ] = 0.0
    return result


def _canonical_source_coordinates(structure, settings):
    import numpy

    fractional = _normalize_fractional(
        structure.periodic.fractional_coordinates.values,
        structure.periodic.pbc,
        settings.boundary_tolerance,
    )
    return (
        fractional
        @ numpy.asarray(structure.cell.values, dtype=float)
        * _coordinate_scale(structure.cell.unit)
    )


def _periodic_site_attributes(
    structure,
    *,
    source_atom_ids=None,
    rotations=None,
):
    import numpy

    if not isinstance(structure, Structure) or structure.periodic is None:
        raise ValueError("structure must be a periodic Structure")
    periodic = structure.periodic
    atom_count = len(structure.atomic_numbers)
    labels, label_categories = _categorical(periodic.site_labels)
    assemblies, assembly_categories = _categorical(
        periodic.disorder_assemblies
    )
    adp_types, adp_categories = _categorical(periodic.adp_types)
    attributes = {
        "siteid": tuple(range(atom_count)),
        "cbq_site_label": labels,
        "cbq_occupancy": tuple(
            map(float, numpy.asarray(periodic.occupancies.values))
        ),
        "cbq_disorder_group": periodic.disorder_groups,
        "cbq_disorder_assembly": assemblies,
        "cbq_adp_type": adp_types,
    }
    isotropic = periodic.isotropic_displacements
    attributes["cbq_u_iso"] = (
        (float("nan"),) * atom_count
        if isotropic is None
        else tuple(map(float, numpy.asarray(isotropic.values)))
    )
    anisotropic = periodic.anisotropic_displacements
    values = (
        numpy.full((atom_count, 6), numpy.nan)
        if anisotropic is None
        else numpy.asarray(anisotropic.values, dtype=float)
    )
    for index, name in enumerate(_U_COMPONENTS):
        attributes[f"cbq_{name}"] = tuple(map(float, values[:, index]))
    if source_atom_ids is not None:
        attributes = {
            name: tuple(values[index] for index in source_atom_ids)
            for name, values in attributes.items()
        }
    if rotations is not None and periodic.anisotropic_displacements is not None:
        if source_atom_ids is None or len(rotations) != len(source_atom_ids):
            raise ValueError("rotations must match derived source atom IDs")
        source_values = numpy.asarray(
            periodic.anisotropic_displacements.values,
            dtype=float,
        )
        transformed = []
        for source_atom_id, rotation in zip(source_atom_ids, rotations):
            row = source_values[source_atom_id]
            if numpy.all(numpy.isnan(row)):
                transformed.append(row)
                continue
            u11, u22, u33, u12, u13, u23 = row
            tensor = numpy.asarray(
                (
                    (u11, u12, u13),
                    (u12, u22, u23),
                    (u13, u23, u33),
                )
            )
            rotation = numpy.asarray(rotation, dtype=float)
            result = rotation @ tensor @ rotation.T
            transformed.append(
                (
                    result[0, 0],
                    result[1, 1],
                    result[2, 2],
                    result[0, 1],
                    result[0, 2],
                    result[1, 2],
                )
            )
        for index, name in enumerate(_U_COMPONENTS):
            attributes[f"cbq_{name}"] = tuple(
                float(values[index]) for values in transformed
            )
    return attributes, {
        "cbq_site_label": label_categories,
        "cbq_disorder_assembly": assembly_categories,
        "cbq_adp_type": adp_categories,
    }


def _write_periodic_attributes(
    obj,
    structure,
    settings,
    *,
    source_atom_ids=None,
    rotations=None,
):
    attributes, categories = _periodic_site_attributes(
        structure,
        source_atom_ids=source_atom_ids,
        rotations=rotations,
    )
    for name in (
        "siteid",
        "cbq_site_label",
        "cbq_disorder_group",
        "cbq_disorder_assembly",
        "cbq_adp_type",
    ):
        _write_attribute(obj.data, name, "INT", "value", attributes[name])
    for name in ("cbq_occupancy", "cbq_u_iso", *(
        f"cbq_{component}" for component in _U_COMPONENTS
    )):
        _write_attribute(obj.data, name, "FLOAT", "value", attributes[name])
    for name, values in categories.items():
        obj[f"{name}_categories"] = json.dumps(
            values,
            ensure_ascii=True,
            separators=(",", ":"),
        )
    obj["cbq_periodic_representation"] = settings.representation
    obj["cbq_periodic_supercell"] = settings.supercell
    obj["cbq_periodic_boundary_tolerance"] = settings.boundary_tolerance
    obj["cbq_periodic_show_cell"] = settings.show_cell
    obj["cbq_periodic_show_axes"] = settings.show_axes
    obj["cbq_periodic_occupancy_mode"] = settings.occupancy_mode
    obj["cbq_periodic_adp_probability"] = settings.adp_probability
    obj["cbq_periodic_show_constraints"] = settings.show_constraints
    obj["cbq_periodic_source_atom_count"] = len(structure.atomic_numbers)


def _derived_periodic_sites(structure, settings):
    import numpy

    if not isinstance(structure, Structure) or structure.periodic is None:
        raise ValueError("structure must be a periodic Structure")
    if not isinstance(settings, PeriodicViewSettings):
        raise TypeError("settings must be PeriodicViewSettings")
    if settings.representation == "source_sites":
        return {"coordinates": (), "source_atom_ids": ()}

    periodic = structure.periodic
    fractional = numpy.asarray(
        periodic.fractional_coordinates.values,
        dtype=float,
    )
    pbc = periodic.pbc
    tolerance = settings.boundary_tolerance

    original = tuple(_normalize_fractional(fractional, pbc, tolerance))
    identity = numpy.eye(3)
    expanded = [
        (index, values, identity, True)
        for index, values in enumerate(original)
    ]
    quantum = tolerance if tolerance > 0.0 else None

    def key(values):
        if quantum is None:
            return tuple(map(float, values))
        return tuple(int(round(float(value) / quantum)) for value in values)

    seen = [{key(values)} for values in original]
    operations = periodic.symmetry_operations or ("x,y,z",)
    if operations != ("x,y,z",):
        import gemmi

        for operation in operations:
            transform = gemmi.Op(operation)
            rotation = (
                numpy.asarray(transform.rot, dtype=float) / transform.DEN
            )
            translation = (
                numpy.asarray(transform.tran, dtype=float) / transform.DEN
            )
            candidates = _normalize_fractional(
                fractional @ rotation.T + translation,
                pbc,
                tolerance,
            )
            for source_atom_id, candidate in enumerate(candidates):
                candidate_key = key(candidate)
                if candidate_key in seen[source_atom_id]:
                    continue
                seen[source_atom_id].add(candidate_key)
                expanded.append(
                    (source_atom_id, candidate, rotation, False)
                )

    translations = (
        ((0, 0, 0),)
        if settings.representation == "expanded_cell"
        else tuple(
            (x, y, z)
            for x in range(settings.supercell[0])
            for y in range(settings.supercell[1])
            for z in range(settings.supercell[2])
        )
    )
    cell = numpy.asarray(structure.cell.values, dtype=float)
    scale = _coordinate_scale(structure.cell.unit)
    expanded_ids = numpy.asarray(
        tuple(value[0] for value in expanded),
        dtype=int,
    )
    expanded_fractional = numpy.asarray(
        tuple(value[1] for value in expanded),
        dtype=float,
    )
    expanded_rotations = numpy.asarray(
        tuple(value[2] for value in expanded),
        dtype=float,
    )
    expanded_original = numpy.asarray(
        tuple(value[3] for value in expanded),
        dtype=bool,
    )
    coordinate_parts = []
    source_id_parts = []
    rotation_parts = []
    for translation in translations:
        coordinates = (
            expanded_fractional
            + numpy.asarray(translation, dtype=float)
        ) @ cell * scale
        keep = (
            ~expanded_original
            if translation == (0, 0, 0)
            else numpy.ones(len(expanded), dtype=bool)
        )
        coordinate_parts.append(coordinates[keep])
        source_id_parts.append(expanded_ids[keep])
        rotation_parts.append(expanded_rotations[keep])
    coordinates = numpy.concatenate(coordinate_parts, axis=0)
    source_atom_ids = numpy.concatenate(source_id_parts, axis=0)
    rotations = numpy.concatenate(rotation_parts, axis=0)
    return {
        "coordinates": tuple(map(tuple, coordinates.tolist())),
        "source_atom_ids": tuple(map(int, source_atom_ids)),
        "rotations": tuple(
            tuple(map(tuple, values.tolist()))
            for values in rotations
        ),
    }


def _create_periodic_site_display(
    main,
    collection,
    structure,
    settings,
    selective_dynamics=None,
):
    import bpy

    derived = _derived_periodic_sites(structure, settings)
    if not derived["coordinates"]:
        return None
    mesh = bpy.data.meshes.new(f"{main.name} Derived Sites")
    display = None
    try:
        mesh.from_pydata(derived["coordinates"], (), ())
        display = bpy.data.objects.new(mesh.name, mesh)
        collection.objects.link(display)
        data = _structure_view_data(
            structure,
            selective_dynamics=selective_dynamics,
        )
        _write_point_attributes(
            mesh,
            data,
            atom_ids=derived["source_atom_ids"],
        )
        _write_periodic_attributes(
            display,
            structure,
            settings,
            source_atom_ids=derived["source_atom_ids"],
            rotations=derived["rotations"],
        )
        _write_attribute(
            mesh,
            "cbq_display_only",
            "BOOLEAN",
            "value",
            (True,) * len(derived["coordinates"]),
        )
        display["cbq_contract"] = _PERIODIC_SITE_DISPLAY_CONTRACT
        display["cb_structure_id"] = str(structure.id)
        display.parent = main
        from .. import node

        node.ensure_structure_ball_stick_modifier(display)
        main["cbq_periodic_site_display_object"] = display.name
        main["cbq_periodic_derived_site_count"] = len(
            derived["coordinates"]
        )
        mesh.update()
        return display
    except BaseException as error:
        groups = (
            ()
            if display is None
            else tuple(
                modifier.node_group
                for modifier in display.modifiers
                if modifier.node_group is not None
            )
        )
        if display is not None:
            error = _run_cleanup(
                error,
                "periodic site display cleanup failed",
                lambda: bpy.data.objects.remove(display, do_unlink=True),
            )
        if mesh.users == 0:
            error = _run_cleanup(
                error,
                "periodic site display mesh cleanup failed",
                lambda: bpy.data.meshes.remove(mesh),
            )
        for group in groups:
            if group.users == 0:
                error = _run_cleanup(
                    error,
                    "periodic site node-group cleanup failed",
                    lambda group=group: bpy.data.node_groups.remove(group),
                )
        raise error


def create_periodic_structure_view(
    structure,
    topology=None,
    settings=None,
    *,
    selective_dynamics=None,
    name="ChemBlender Periodic Structure",
    collection=None,
):
    if not isinstance(structure, Structure) or structure.periodic is None:
        raise ValueError("structure must be a periodic Structure")
    if settings is None:
        settings = PeriodicViewSettings()
    if not isinstance(settings, PeriodicViewSettings):
        raise TypeError("settings must be PeriodicViewSettings")
    obj = None
    try:
        obj = create_structure_view(
            structure,
            topology,
            selective_dynamics=selective_dynamics,
            periodic_boundary_tolerance=(
                None
                if settings.representation == "source_sites"
                else settings.boundary_tolerance
            ),
            name=name,
            collection=collection,
        )
        marker = None
        marker_name = obj.get("cb_selective_marker_object")
        if isinstance(marker_name, str):
            import bpy

            marker = bpy.data.objects.get(marker_name)
        if settings.representation != "source_sites":
            obj["cbq_periodic_coordinates_canonicalized"] = True
        if not settings.show_constraints and marker is not None:
            marker.hide_set(True)
            obj["cb_selective_constraints_visible"] = False
        _write_periodic_attributes(obj, structure, settings)
        _create_periodic_site_display(
            obj,
            obj.users_collection[0] if obj.users_collection else collection,
            structure,
            settings,
            selective_dynamics,
        )
        obj.data.update()
        return obj
    except BaseException as error:
        if obj is not None:
            error = _run_cleanup(
                error,
                "periodic Structure view cleanup failed",
                lambda: remove_structure_view(obj),
            )
        raise error
