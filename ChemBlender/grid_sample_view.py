"""Native Blender geometry for scientific grid slices, profiles and legends."""

import bpy

from .core import Grid3D, builtin_scene_presets
from .core.grid_cache_service import _ANGSTROM_SCALE
from .core.grid_sampling import line_profile, plane_slice
from .core.scene_preset import _settings
from .spectrum_plot import _poly_spline
from .surface_view import _property_material


_VALUE = "cb_sample_value"
_VALID = "cb_sample_valid"
_OWNED = "cb_grid_sample_owned"


def _remove_owned(objects, data_blocks=(), materials=()):
    objects = set(objects)
    data_blocks = set(data_blocks) | {obj.data for obj in objects if obj.data is not None}
    materials = set(materials) | {
        material for data in data_blocks for material in getattr(data, "materials", ())
        if material is not None
    }
    for obj in objects:
        for child in tuple(obj.children):
            if child not in objects:
                transform = child.matrix_world.copy()
                child.parent = None
                child.matrix_world = transform
    for obj in objects:
        bpy.data.objects.remove(obj, do_unlink=True)
    for data in data_blocks:
        if data.users == 0 and data.get(_OWNED):
            bpy.data.batch_remove(ids=(data,))
    for material in materials:
        if material.users == 0 and material.get(_OWNED):
            bpy.data.materials.remove(material)


def remove_grid_sample_view(root):
    """Remove this view's geometry; preserve user children and shared resources."""
    if not root.get("cb_grid_sample_root"):
        raise ValueError("object is not a grid sample view root")
    objects = [root]
    for obj in objects:
        objects.extend(child for child in obj.children
                       if child.get("cb_grid_sample_component"))
    _remove_owned(objects)


def _attribute(mesh, name, kind, values):
    import numpy

    attribute = mesh.attributes.new(name, kind, "POINT")
    field = "vector" if kind == "FLOAT_VECTOR" else "value"
    attribute.data.foreach_set(field, numpy.asarray(values).ravel())


def create_grid_sample_view(grid, kind, settings, *, collection=None):
    """Create a complete view tuple; scientific coordinates never use object transforms."""
    import numpy

    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    if kind not in {"grid_slice", "grid_profile", "grid_colorbar"}:
        raise ValueError("unsupported grid sample view kind")
    preset = builtin_scene_presets()[kind]
    settings = dict(_settings(preset, dict(settings), {"grid": grid}))
    target = collection if collection is not None else bpy.context.collection
    if target is None:
        raise ValueError("a Blender collection is required")
    scale = _ANGSTROM_SCALE[grid.coordinate_unit]
    objects, data_blocks, materials = [], [], []

    def object_with_data(name, component, data):
        data[_OWNED] = True
        data_blocks.append(data)
        obj = bpy.data.objects.new(name, data)
        objects.append(obj)
        target.objects.link(obj)
        obj["cb_grid_sample_component"] = component
        if len(objects) == 1:
            obj["cb_grid_sample_root"] = True
        else:
            obj.parent = objects[0]
        obj["cb_grid_sample_contract"] = f"{kind}_v1"
        obj["cb_dataset_id"] = str(grid.id)
        obj["cb_dataset_revision"] = grid.revision
        obj["cb_dataset_index"] = settings["dataset_index"]
        obj["cb_semantic_role"] = grid.semantic_role
        obj["cb_source_coordinate_unit"] = grid.coordinate_unit
        obj["cb_display_coordinate_unit"] = "angstrom"
        obj["cb_value_unit"] = grid.data.unit
        if grid.structure_id is not None:
            obj["cb_structure_id"] = str(grid.structure_id)
        return obj

    def mesh(name, component, points, faces):
        obj = object_with_data(name, component, bpy.data.meshes.new(name))
        obj.data.from_pydata(numpy.asarray(points).tolist(), [], faces)
        obj.data.update()
        return obj

    def curve(name, component, segments, radius):
        obj = object_with_data(name, component, bpy.data.curves.new(name, "CURVE"))
        obj.data.dimensions = "3D"
        obj.data.bevel_depth = radius
        obj.data.bevel_resolution = 2
        for coordinates in segments:
            if len(coordinates) >= 2:
                _poly_spline(obj.data, coordinates)
        return obj

    def label(body, component, location, size, align="LEFT"):
        obj = object_with_data("ChemBlender " + component, component,
                               bpy.data.curves.new("ChemBlender " + component, "FONT"))
        obj.data.body = body
        obj.data.size = size
        obj.data.align_x = align
        obj.location = location
        return obj

    def colors(obj, values, valid=None):
        _attribute(obj.data, _VALUE, "FLOAT", values)
        material = _property_material("ChemBlender Grid Colors", settings["color_min"],
                                      settings["color_max"], attribute_name=_VALUE)
        materials.append(material)
        material[_OWNED] = True
        obj.data.materials.append(material)
        principled = next(node for node in material.node_tree.nodes
                          if node.type == "BSDF_PRINCIPLED")
        color_link = principled.inputs["Base Color"].links[0]
        material.node_tree.links.new(color_link.from_socket, principled.inputs["Emission Color"])
        material.node_tree.links.remove(color_link)
        # Scientific colors must stay readable under arbitrary scene lighting.
        principled.inputs["Base Color"].default_value = (0., 0., 0., 1.)
        principled.inputs["Specular IOR Level"].default_value = 0.
        principled.inputs["Emission Strength"].default_value = 1.
        if valid is not None:
            _attribute(obj.data, _VALID, "BOOLEAN", valid)
            attribute = material.node_tree.nodes.new("ShaderNodeAttribute")
            attribute.attribute_name = _VALID
            material.node_tree.links.new(attribute.outputs["Fac"], principled.inputs["Alpha"])
            material.surface_render_method = "DITHERED"

    try:
        if kind == "grid_slice":
            samples = plane_slice(grid, **{name: settings[name] for name in (
                "origin", "u_vector", "v_vector", "counts", "dataset_index")})
            count_u, count_v = samples.values.shape
            valid = samples.valid_mask.ravel()
            faces = []
            for u in range(count_u - 1):
                for v in range(count_v - 1):
                    first = u * count_v + v
                    face = (first, first + count_v, first + count_v + 1, first + 1)
                    # Omit unknown quads entirely so NaN values cannot tint a valid face.
                    if valid[list(face)].all():
                        faces.append(face)
            root = mesh("ChemBlender Grid Slice", "slice",
                        samples.points.reshape(-1, 3) * scale, faces)
            colors(root, samples.values, samples.valid_mask)
            _attribute(root.data, "cb_sample_coordinate", "FLOAT_VECTOR", samples.points)
            root["cb_sample_count"] = int(valid.size)
            root["cb_valid_sample_count"] = int(valid.sum())
        elif kind == "grid_profile":
            samples = line_profile(grid, **{name: settings[name] for name in (
                "start", "end", "sample_count", "dataset_index")})
            radius = settings["radius"]
            transitions = numpy.flatnonzero(numpy.diff(
                numpy.r_[False, samples.valid_mask, False].astype(int))).reshape(-1, 2)
            root = curve("ChemBlender Profile Path", "profile_path",
                         tuple(samples.points[[start, end - 1]] * scale
                               for start, end in transitions if end - start >= 2), radius)
            root["cb_sample_count"] = int(samples.values.size)
            root["cb_valid_sample_count"] = int(samples.valid_mask.sum())
            valid_values = samples.values[samples.valid_mask]
            minimum = float(valid_values.min()) if valid_values.size else 0.0
            maximum = float(valid_values.max()) if valid_values.size else 1.0
            if minimum == maximum:
                margin = max(abs(minimum) * 0.1, 0.5)
                minimum, maximum = minimum - margin, maximum + margin
            width = float(samples.distance[-1]) * scale
            height = max(width * 0.4, radius * 10)
            graph_points = numpy.column_stack((samples.distance * scale,
                (samples.values - minimum) / (maximum - minimum) * height,
                numpy.zeros(samples.values.size)))
            graph = curve("ChemBlender Profile Graph", "profile_graph",
                          tuple(graph_points[start:end] for start, end in transitions), radius)
            offset = numpy.asarray(samples.points[0]) * scale + (0, -height * 1.7, 0)
            graph.location = offset
            graph["cb_graph_value_min"] = minimum
            graph["cb_graph_value_max"] = maximum
            axes = curve("ChemBlender Profile Axes", "profile_axes",
                         (((0, height, 0), (0, 0, 0), (width, 0, 0)),), radius * 0.5)
            axes.location = offset
            font_size = max(height * 0.08, radius * 2)
            label(f"{minimum:.5g}", "value_min_label", offset + (-font_size, 0, 0),
                  font_size, "RIGHT")
            label(f"{maximum:.5g} [{grid.data.unit}]", "value_max_label",
                  offset + (0, height + font_size, 0), font_size)
            label(f"0 - {float(samples.distance[-1]):.5g} [{grid.coordinate_unit}]",
                  "distance_label", offset + (width * 0.5, -font_size * 2, 0),
                  font_size, "CENTER")
            if not valid_values.size:
                label("No valid samples", "missing_label", offset + (0, height * 0.5, 0), font_size)
        else:
            width, height = settings["width"], settings["height"]
            minimum, maximum = settings["color_min"], settings["color_max"]
            root = mesh("ChemBlender Grid Colorbar", "colorbar",
                        ((0, 0, 0), (width, 0, 0), (width, height, 0), (0, height, 0)),
                        ((0, 1, 2, 3),))
            colors(root, (minimum, maximum, maximum, minimum))
            root["cb_color_min"], root["cb_color_max"] = minimum, maximum
            font_size = height * 0.45
            label(f"{minimum:.5g}", "min_label", (0, -font_size * 1.4, 0), font_size)
            label(f"{maximum:.5g}", "max_label", (width, -font_size * 1.4, 0),
                  font_size, "RIGHT")
            label(grid.data.unit, "unit_label", (width * 0.5, height + font_size * 0.5, 0),
                  font_size, "CENTER")
            if minimum <= 0 <= maximum:
                fraction = -minimum / (maximum - minimum)
                root["cb_color_zero_fraction"] = fraction
                x = width * fraction
                curve("ChemBlender Color Zero Tick", "zero_tick",
                      (((x, 0, 0.001), (x, height, 0.001)),), height * 0.012)
                if minimum < 0 < maximum:
                    label("0", "zero_label", (x, -font_size * 1.4, 0), font_size, "CENTER")
        return tuple(objects)
    except BaseException:
        _remove_owned(objects, data_blocks, materials)
        raise
