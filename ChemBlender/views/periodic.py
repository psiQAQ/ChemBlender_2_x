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


def _cell_edge_geometry(structure, *, supercell=(1, 1, 1)):
    import numpy

    if not isinstance(structure, Structure) or structure.periodic is None:
        raise ValueError("structure must be a periodic Structure")
    if (
        type(supercell) is not tuple
        or len(supercell) != 3
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for value in supercell
        )
    ):
        raise ValueError("supercell must contain three positive integers")
    vectors = (
        numpy.asarray(structure.cell.values, dtype=float)
        * _coordinate_scale(structure.cell.unit)
        * numpy.asarray(supercell, dtype=float)[:, None]
    )
    vertices = tuple(
        tuple(map(float, x * vectors[0] + y * vectors[1] + z * vectors[2]))
        for x in (0, 1)
        for y in (0, 1)
        for z in (0, 1)
    )
    edges = tuple(
        (left, right)
        for left, right in (
            (0, 1),
            (0, 2),
            (0, 4),
            (1, 3),
            (1, 5),
            (2, 3),
            (2, 6),
            (3, 7),
            (4, 5),
            (4, 6),
            (5, 7),
            (6, 7),
        )
    )
    return vertices, edges


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
        cell = numpy.asarray(structure.cell.values, dtype=float)
        reciprocal_lengths = numpy.linalg.norm(
            numpy.linalg.inv(cell),
            axis=0,
        )
        reciprocal_scale = numpy.diag(reciprocal_lengths)
        inverse_reciprocal_scale = numpy.diag(1.0 / reciprocal_lengths)
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
            raw_transform = (
                inverse_reciprocal_scale
                @ rotation
                @ reciprocal_scale
            )
            result = raw_transform @ tensor @ raw_transform.T
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


def _periodic_render_attributes(
    structure,
    settings,
    *,
    source_atom_ids=None,
    rotations=None,
):
    import numpy

    if not isinstance(settings, PeriodicViewSettings):
        raise TypeError("settings must be PeriodicViewSettings")
    attributes, _ = _periodic_site_attributes(
        structure,
        source_atom_ids=source_atom_ids,
        rotations=rotations,
    )
    occupancy = numpy.asarray(attributes["cbq_occupancy"], dtype=float)
    occupancy_valid = numpy.isfinite(occupancy)
    displayed_occupancy = numpy.where(occupancy_valid, occupancy, 1.0)

    from ..Chem_data import PROBABILITY_ELLIPSOID_TABLE

    probability_rows = tuple(sorted(PROBABILITY_ELLIPSOID_TABLE.items()))
    probabilities = numpy.asarray(
        tuple(row[0] for row in probability_rows),
        dtype=float,
    )
    probability_scales = numpy.asarray(
        tuple(row[1] for row in probability_rows),
        dtype=float,
    )
    probability_scale = float(
        numpy.interp(
            settings.adp_probability,
            probabilities,
            probability_scales,
        )
    )
    anisotropic = numpy.column_stack(
        tuple(
            numpy.asarray(attributes[f"cbq_{component}"], dtype=float)
            for component in _U_COMPONENTS
        )
    )
    isotropic = numpy.asarray(attributes["cbq_u_iso"], dtype=float)
    atom_ids = (
        tuple(range(len(structure.atomic_numbers)))
        if source_atom_ids is None
        else tuple(source_atom_ids)
    )
    anisotropic_required = tuple(
        "ani" in structure.periodic.adp_types[atom_id].casefold()
        for atom_id in atom_ids
    )
    cell = numpy.asarray(structure.cell.values, dtype=float)
    reciprocal_lengths = numpy.linalg.norm(
        numpy.linalg.inv(cell),
        axis=0,
    )
    orthogonalization = cell.T @ numpy.diag(reciprocal_lengths)
    adp_valid = []
    adp_scale = []
    adp_axes = []
    for row, isotropic_value, requires_anisotropic in zip(
        anisotropic,
        isotropic,
        anisotropic_required,
    ):
        finite_anisotropic = numpy.isfinite(row)
        partial_anisotropic = bool(
            numpy.any(finite_anisotropic)
            and not numpy.all(finite_anisotropic)
        )
        if numpy.all(numpy.isfinite(row)):
            u11, u22, u33, u12, u13, u23 = row
            raw_tensor = numpy.asarray(
                (
                    (u11, u12, u13),
                    (u12, u22, u23),
                    (u13, u23, u33),
                ),
                dtype=float,
            )
            tensor = (
                orthogonalization
                @ raw_tensor
                @ orthogonalization.T
            )
            eigenvalues, eigenvectors = numpy.linalg.eigh(tensor)
            valid = bool(numpy.all(eigenvalues >= -1.0e-12))
            if valid:
                eigenvalues = numpy.clip(eigenvalues, 0.0, None)
            else:
                eigenvalues = numpy.full(
                    3,
                    (0.2 / probability_scale) ** 2,
                )
                eigenvectors = numpy.eye(3)
        elif isfinite(float(isotropic_value)) and isotropic_value >= 0.0:
            valid = (
                not partial_anisotropic
                and not requires_anisotropic
            )
            eigenvalues = numpy.full(3, float(isotropic_value))
            eigenvectors = numpy.eye(3)
        else:
            valid = False
            eigenvalues = numpy.full(3, (0.2 / probability_scale) ** 2)
            eigenvectors = numpy.eye(3)
        if numpy.linalg.det(eigenvectors) < 0.0:
            eigenvectors[:, 2] *= -1.0
        adp_valid.append(valid)
        adp_scale.append(
            tuple(map(float, probability_scale * numpy.sqrt(eigenvalues)))
        )
        adp_axes.append(
            tuple(
                tuple(map(float, eigenvectors[:, index]))
                for index in range(3)
            )
        )

    return {
        "cbq_occupancy_valid": tuple(map(bool, occupancy_valid)),
        "cbq_occupancy_alpha": tuple(map(float, displayed_occupancy)),
        "cbq_occupancy_radius": tuple(
            map(float, numpy.cbrt(displayed_occupancy))
        ),
        "cbq_adp_valid": tuple(adp_valid),
        "cbq_adp_scale": tuple(adp_scale),
        "cbq_adp_axes": tuple(adp_axes),
        "cbq_quality_badge": tuple(
            (0 if occupancy_is_valid else 1)
            | (0 if displacement_is_valid else 2)
            for occupancy_is_valid, displacement_is_valid in zip(
                occupancy_valid,
                adp_valid,
            )
        ),
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
    render_attributes = _periodic_render_attributes(
        structure,
        settings,
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
    for name in ("cbq_occupancy_valid", "cbq_adp_valid"):
        _write_attribute(
            obj.data,
            name,
            "BOOLEAN",
            "value",
            render_attributes[name],
        )
    for name in ("cbq_occupancy_alpha", "cbq_occupancy_radius"):
        _write_attribute(
            obj.data,
            name,
            "FLOAT",
            "value",
            render_attributes[name],
        )
    _write_attribute(
        obj.data,
        "cbq_quality_badge",
        "INT",
        "value",
        render_attributes["cbq_quality_badge"],
    )
    _write_attribute(
        obj.data,
        "cbq_adp_scale",
        "FLOAT_VECTOR",
        "vector",
        tuple(
            component
            for values in render_attributes["cbq_adp_scale"]
            for component in values
        ),
    )
    for index in range(3):
        _write_attribute(
            obj.data,
            f"cbq_adp_axis_{index + 1}",
            "FLOAT_VECTOR",
            "vector",
            tuple(
                component
                for values in render_attributes["cbq_adp_axes"]
                for component in values[index]
            ),
        )
    if settings.occupancy_mode == "radius":
        current = [0.0] * len(render_attributes["cbq_occupancy_radius"])
        obj.data.attributes["atom_scale_f"].data.foreach_get("value", current)
        _write_attribute(
            obj.data,
            "atom_scale_f",
            "FLOAT",
            "value",
            tuple(
                value * scale
                for value, scale in zip(
                    current,
                    render_attributes["cbq_occupancy_radius"],
                )
            ),
        )
    else:
        _write_attribute(
            obj.data,
            "atom_scale_f",
            "FLOAT",
            "value",
            (0.0,) * len(render_attributes["cbq_occupancy_alpha"]),
        )
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


def _create_periodic_cell_display(main, collection, structure, settings):
    if not settings.show_cell and not settings.show_axes:
        return None
    import bpy

    supercell = (
        settings.supercell
        if settings.representation == "supercell"
        else (1, 1, 1)
    )
    cell_vertices, cell_edges = _cell_edge_geometry(
        structure,
        supercell=supercell,
    )
    vertices = list(cell_vertices) if settings.show_cell else []
    edges = list(cell_edges) if settings.show_cell else []
    if settings.show_axes:
        for endpoint_index in (4, 2, 1):
            endpoint = cell_vertices[endpoint_index]
            start = len(vertices)
            vertices.extend(
                (
                    (0.0, 0.0, 0.0),
                    tuple(1.15 * component for component in endpoint),
                )
            )
            edges.append((start, start + 1))
    vertices = tuple(vertices)
    edges = tuple(edges)
    mesh = bpy.data.meshes.new(f"{main.name} Cell")
    display = None
    try:
        mesh.from_pydata(vertices, edges, ())
        display = bpy.data.objects.new(mesh.name, mesh)
        collection.objects.link(display)
        display.parent = main
        display["cbq_contract"] = "periodic_cell_display_v1"
        display["cbq_contract_version"] = 1
        display["cb_structure_id"] = str(structure.id)
        display["cbq_cell_matrix"] = tuple(
            float(value)
            for row in structure.cell.values
            for value in row
        )
        display["cbq_supercell"] = supercell
        display["cbq_show_axes"] = settings.show_axes
        from .. import node

        node.ensure_periodic_cell_modifier(display)
        main["cbq_periodic_cell_object"] = display.name
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
                "periodic cell display cleanup failed",
                lambda: bpy.data.objects.remove(display, do_unlink=True),
            )
        if mesh.users == 0:
            error = _run_cleanup(
                error,
                "periodic cell mesh cleanup failed",
                lambda: bpy.data.meshes.remove(mesh),
            )
        for group in groups:
            if group.users == 0:
                error = _run_cleanup(
                    error,
                    "periodic cell node-group cleanup failed",
                    lambda group=group: bpy.data.node_groups.remove(group),
                )
        raise error


def _combined_periodic_sites(main, structure, settings, *, derived=None):
    import numpy

    if derived is None:
        derived = _derived_periodic_sites(structure, settings)
    return (
        tuple(tuple(map(float, vertex.co)) for vertex in main.data.vertices)
        + tuple(derived["coordinates"]),
        tuple(range(len(structure.atomic_numbers)))
        + tuple(derived["source_atom_ids"]),
        tuple(
            tuple(map(tuple, numpy.eye(3).tolist()))
            for _ in structure.atomic_numbers
        )
        + tuple(derived.get("rotations", ())),
    )


def _occupancy_material(name):
    import bpy

    material = bpy.data.materials.new(name)
    try:
        material.use_nodes = True
        nodes = material.node_tree.nodes
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        shader = nodes.new("ShaderNodeBsdfPrincipled")
        color = nodes.new("ShaderNodeAttribute")
        color.attribute_name = "cbq_occupancy_color"
        alpha = nodes.new("ShaderNodeAttribute")
        alpha.attribute_name = "cbq_occupancy_alpha"
        material.node_tree.links.new(
            color.outputs["Color"],
            shader.inputs["Base Color"],
        )
        material.node_tree.links.new(
            alpha.outputs["Fac"],
            shader.inputs["Alpha"],
        )
        material.node_tree.links.new(
            shader.outputs["BSDF"],
            output.inputs["Surface"],
        )
        material.diffuse_color = (0.8, 0.35, 0.08, 1.0)
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "DITHERED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "BLEND"
        material["cbq_contract"] = "periodic_occupancy_material_v1"
        material["cbq_contract_version"] = 1
        return material
    except BaseException as error:
        if material.users == 0:
            error = _run_cleanup(
                error,
                "occupancy material initialization cleanup failed",
                lambda: bpy.data.materials.remove(material),
            )
        raise error


def _pie_occupancy_geometry(
    coordinates,
    occupancies,
    valid,
    radii,
    colors,
    quality,
):
    from math import ceil, cos, pi, sin

    vertices = []
    faces = []
    vertex_alpha = []
    vertex_colors = []
    vertex_quality = []

    def add_sector(center, radius, start, fraction, color, badge):
        if fraction <= 0.0:
            return
        segments = max(1, ceil(24 * fraction))
        first = len(vertices)
        vertices.append(tuple(center))
        vertex_alpha.append(1.0)
        vertex_colors.extend(color)
        vertex_quality.append(badge)
        for index in range(segments + 1):
            angle = start + 2.0 * pi * fraction * index / segments
            vertices.append(
                (
                    center[0] + radius * cos(angle),
                    center[1] + radius * sin(angle),
                    center[2],
                )
            )
            vertex_alpha.append(1.0)
            vertex_colors.extend(color)
            vertex_quality.append(badge)
        faces.extend(
            (first, first + index + 1, first + index + 2)
            for index in range(segments)
        )

    for center, occupancy, is_valid, radius, color, badge in zip(
        coordinates,
        occupancies,
        valid,
        radii,
        colors,
        quality,
    ):
        if not is_valid:
            add_sector(
                center,
                radius,
                0.0,
                1.0,
                (0.35, 0.35, 0.35, 1.0),
                badge,
            )
            continue
        occupied = min(1.0, max(0.0, occupancy))
        add_sector(center, radius, 0.0, occupied, color, badge)
        add_sector(
            center,
            radius,
            2.0 * pi * occupied,
            1.0 - occupied,
            (0.35, 0.35, 0.35, 1.0),
            badge,
        )
    return {
        "vertices": tuple(vertices),
        "faces": tuple(faces),
        "alpha": tuple(vertex_alpha),
        "colors": tuple(vertex_colors),
        "quality": tuple(vertex_quality),
    }


def _occupancy_display_geometry(
    main,
    structure,
    settings,
    *,
    derived=None,
):
    import numpy

    coordinates, source_atom_ids, rotations = _combined_periodic_sites(
        main,
        structure,
        settings,
        derived=derived,
    )
    render = _periodic_render_attributes(
        structure,
        settings,
        source_atom_ids=source_atom_ids,
        rotations=rotations,
    )
    site = _periodic_site_attributes(
        structure,
        source_atom_ids=source_atom_ids,
        rotations=rotations,
    )[0]
    point_data = _structure_view_data(structure)
    base_radii = tuple(
        float(point_data["radius"][source_id])
        * float(point_data["atom_scale_f"][source_id])
        for source_id in source_atom_ids
    )
    source_colors = tuple(
        tuple(
            point_data["colour"][source_id * 4 + component]
            for component in range(4)
        )
        for source_id in source_atom_ids
    )
    if settings.occupancy_mode == "pie":
        return _pie_occupancy_geometry(
            coordinates,
            site["cbq_occupancy"],
            render["cbq_occupancy_valid"],
            base_radii,
            source_colors,
            render["cbq_quality_badge"],
        )
    if settings.occupancy_mode == "opacity":
        return {
            "vertices": coordinates,
            "faces": (),
            "scale": tuple((radius,) * 3 for radius in base_radii),
            "alpha": render["cbq_occupancy_alpha"],
            "colors": tuple(
                component for color in source_colors for component in color
            ),
            "quality": render["cbq_quality_badge"],
        }

    vertices = []
    scales = []
    alphas = []
    colors = []
    quality = []
    for center, occupancy, valid, radius, color, badge in zip(
        coordinates,
        site["cbq_occupancy"],
        render["cbq_occupancy_valid"],
        base_radii,
        source_colors,
        render["cbq_quality_badge"],
    ):
        if not valid:
            vertices.append(center)
            scales.append((radius,) * 3)
            alphas.append(1.0)
            colors.extend((0.35, 0.35, 0.35, 1.0))
            quality.append(badge)
            continue
        offset = min(radius * 0.4, 0.2)
        occupied = min(1.0, max(0.0, float(occupancy)))
        for sign, fraction, component_color in (
            (-1.0, occupied, color),
            (1.0, 1.0 - occupied, (0.35, 0.35, 0.35, 1.0)),
        ):
            vertices.append(
                (
                    center[0] + sign * offset,
                    center[1],
                    center[2],
                )
            )
            scale = radius * float(numpy.cbrt(fraction))
            scales.append((scale,) * 3)
            alphas.append(1.0)
            colors.extend(component_color)
            quality.append(badge)
    return {
        "vertices": tuple(vertices),
        "faces": (),
        "scale": tuple(scales),
        "alpha": tuple(alphas),
        "colors": tuple(colors),
        "quality": tuple(quality),
    }


def _create_occupancy_display(
    main,
    collection,
    structure,
    settings,
    *,
    derived=None,
):
    if settings.occupancy_mode == "radius":
        return None
    import bpy

    geometry = _occupancy_display_geometry(
        main,
        structure,
        settings,
        derived=derived,
    )
    mesh = bpy.data.meshes.new(f"{main.name} Site Occupancy")
    display = None
    material = None
    try:
        mesh.from_pydata(
            geometry["vertices"],
            (),
            geometry["faces"],
        )
        display = bpy.data.objects.new(mesh.name, mesh)
        collection.objects.link(display)
        display.parent = main
        material = _occupancy_material(f"{display.name} Material")
        if settings.occupancy_mode == "pie":
            mesh.materials.append(material)
        if "scale" in geometry:
            _write_attribute(
                mesh,
                "cbq_occupancy_scale",
                "FLOAT_VECTOR",
                "vector",
                tuple(
                    component
                    for values in geometry["scale"]
                    for component in values
                ),
            )
        _write_attribute(
            mesh,
            "cbq_occupancy_alpha",
            "FLOAT",
            "value",
            geometry["alpha"],
        )
        _write_attribute(
            mesh,
            "cbq_occupancy_color",
            "FLOAT_COLOR",
            "color",
            geometry["colors"],
        )
        _write_attribute(
            mesh,
            "cbq_quality_badge",
            "INT",
            "value",
            geometry["quality"],
        )
        display["cbq_contract"] = "periodic_occupancy_display_v1"
        display["cbq_contract_version"] = 1
        display["cb_structure_id"] = str(structure.id)
        display["cbq_occupancy_mode"] = settings.occupancy_mode
        from .. import node

        node.ensure_periodic_occupancy_modifier(
            display,
            settings.occupancy_mode,
            material,
        )
        main["cbq_periodic_occupancy_object"] = display.name
        main["cbq_periodic_occupancy_material"] = material.name
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
                "occupancy display cleanup failed",
                lambda: bpy.data.objects.remove(display, do_unlink=True),
            )
        if mesh.users == 0:
            error = _run_cleanup(
                error,
                "occupancy display mesh cleanup failed",
                lambda: bpy.data.meshes.remove(mesh),
            )
        for group in groups:
            if group.users == 0:
                error = _run_cleanup(
                    error,
                    "occupancy node-group cleanup failed",
                    lambda group=group: bpy.data.node_groups.remove(group),
                )
        if material is not None and material.users == 0:
            error = _run_cleanup(
                error,
                "occupancy material cleanup failed",
                lambda: bpy.data.materials.remove(material),
            )
        raise error


def _create_adp_display(
    main,
    collection,
    structure,
    settings,
    *,
    derived=None,
):
    import bpy
    from mathutils import Matrix

    coordinates, source_atom_ids, rotations = _combined_periodic_sites(
        main,
        structure,
        settings,
        derived=derived,
    )
    attributes = _periodic_render_attributes(
        structure,
        settings,
        source_atom_ids=source_atom_ids,
        rotations=rotations,
    )
    mesh = bpy.data.meshes.new(f"{main.name} Thermal Ellipsoids")
    display = None
    try:
        mesh.from_pydata(coordinates, (), ())
        display = bpy.data.objects.new(mesh.name, mesh)
        collection.objects.link(display)
        display.parent = main
        _write_attribute(
            mesh,
            "cbq_adp_scale",
            "FLOAT_VECTOR",
            "vector",
            tuple(
                component
                for values in attributes["cbq_adp_scale"]
                for component in values
            ),
        )
        eulers = tuple(
            tuple(
                Matrix(axes).transposed().to_euler("XYZ")
            )
            for axes in attributes["cbq_adp_axes"]
        )
        _write_attribute(
            mesh,
            "cbq_adp_rotation",
            "FLOAT_VECTOR",
            "vector",
            tuple(component for values in eulers for component in values),
        )
        for name in ("cbq_adp_valid",):
            _write_attribute(
                mesh,
                name,
                "BOOLEAN",
                "value",
                attributes[name],
            )
        _write_attribute(
            mesh,
            "cbq_quality_badge",
            "INT",
            "value",
            attributes["cbq_quality_badge"],
        )
        display["cbq_contract"] = "periodic_adp_display_v1"
        display["cbq_contract_version"] = 1
        display["cb_structure_id"] = str(structure.id)
        display["cbq_adp_probability"] = settings.adp_probability
        from .. import node

        node.ensure_periodic_adp_modifier(display)
        main["cbq_periodic_adp_object"] = display.name
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
                "thermal ellipsoid display cleanup failed",
                lambda: bpy.data.objects.remove(display, do_unlink=True),
            )
        if mesh.users == 0:
            error = _run_cleanup(
                error,
                "thermal ellipsoid mesh cleanup failed",
                lambda: bpy.data.meshes.remove(mesh),
            )
        for group in groups:
            if group.users == 0:
                error = _run_cleanup(
                    error,
                    "thermal ellipsoid node-group cleanup failed",
                    lambda group=group: bpy.data.node_groups.remove(group),
                )
        raise error


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
    *,
    derived=None,
):
    import bpy

    if derived is None:
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
        display["cbq_contract_version"] = 1
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
        derived = _derived_periodic_sites(structure, settings)
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
            derived=derived,
        )
        child_collection = (
            obj.users_collection[0] if obj.users_collection else collection
        )
        _create_periodic_cell_display(
            obj,
            child_collection,
            structure,
            settings,
        )
        _create_occupancy_display(
            obj,
            child_collection,
            structure,
            settings,
            derived=derived,
        )
        _create_adp_display(
            obj,
            child_collection,
            structure,
            settings,
            derived=derived,
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
