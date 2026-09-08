"""Temporary camera-facing scientific titles and legends for native renders."""

import json
import math

import bpy

from .core.color_mapping import color_stops
from .core.scene_preset import builtin_scene_presets, validate_scene_plan
from .scientific_materials import _remove_unused, flat_material, scalar_material


_UNITS = {
    "dimensionless": "1", "angstrom": "Angstrom", "bohr": "bohr",
    "inverse_angstrom": "1/Angstrom", "inverse_centimeter": "cm^-1",
    "terahertz": "THz", "electron_volt": "eV", "hartree": "Eh",
    "elementary_charge": "e", "electron_per_cubic_bohr": "e/bohr^3",
    "electron_per_cubic_angstrom": "e/Angstrom^3",
    "inverse_bohr_to_three_halves": "bohr^(-3/2)",
    "hartree_per_elementary_charge": "Eh/e", "hartree_per_bohr": "Eh/bohr",
    "electron_volt_per_angstrom": "eV/Angstrom", "meter_per_second": "m/s",
    "electron_per_bohr_to_fifth": "e/bohr^5", "electron_per_angstrom_to_fifth": "e/Angstrom^5",
    "kilometer_per_mole": "km/mol", "angstrom_four_per_dalton": "Angstrom^4/Da",
}


def _number(value):
    return format(float(value), ".5g")


def _unit(value):
    return _UNITS.get(value, value)


def _camera_plane(camera, aspect):
    if (not isinstance(camera, bpy.types.Object) or camera.type != "CAMERA"
            or camera.data.type not in {"ORTHO", "PERSP"}):
        raise ValueError("annotations require an orthographic or perspective camera")
    if isinstance(aspect, bool) or not math.isfinite(aspect) or aspect <= 0:
        raise ValueError("render aspect must be positive and finite")
    if not camera.data.clip_start < 1 < camera.data.clip_end:
        raise ValueError("annotation plane requires camera clipping to include distance 1 (near clip 0.01)")
    vertical = camera.data.sensor_fit == "VERTICAL" or camera.data.sensor_fit == "AUTO" and aspect < 1
    # AUTO fits the longer image dimension, but its lens still uses sensor_width
    # in Blender. The native angle property also handles explicit VERTICAL fit.
    span = camera.data.ortho_scale if camera.data.type == "ORTHO" else 2 * math.tan(camera.data.angle / 2)
    width, height = (span * aspect, span) if vertical else (span, span / aspect)
    return width, height, camera.data.shift_x * span, camera.data.shift_y * span


def _description(plan, project, root):
    from .scene_preset_view import _entities

    entities, settings = _entities(plan, project), dict(plan.settings)
    kind = plan.view_kind
    title = builtin_scene_presets()[plan.preset_id].title
    details, legend, scalar = [], [], None
    data = next((entity for name, entity in entities.items() if name != "structure"), None)
    unit = data.data.unit if data is not None and hasattr(data, "data") else ""

    def scalar_legend(label, value_unit, minimum=None, maximum=None, colormap=None):
        return {"label": label, "unit": value_unit,
                "color_min": float(settings["color_min"] if minimum is None else minimum),
                "color_max": float(settings["color_max"] if maximum is None else maximum),
                "colormap": colormap or settings["colormap"]}

    if kind in {"grid_volume", "signed_isosurface", "grid_slice", "grid_profile", "grid_colorbar"}:
        grid = entities["grid"]
        title = grid.semantic_role.replace("_", " ").capitalize()
        details.append(f"Dataset {settings['dataset_index']} | {_unit(grid.data.unit)}")
        if grid.semantic_role == "molecular_orbital":
            for identity in grid.provenance_ids:
                parameters = dict(project.provenance[identity].parameters)
                if "orbital_index" in parameters:
                    details.append(f"MO {int(parameters['orbital_index']) + 1} ({parameters.get('channel', 'unspecified spin')})")
                    break
        if kind == "signed_isosurface":
            title += " isosurface"
            threshold = _number(settings["isovalue"])
            legend = [{"label": f"+{threshold}", "color": settings["positive_color"]},
                      {"label": f"-{threshold}", "color": settings["negative_color"]}]
            from .core.grid_semantics import _selected_values
            import numpy

            values, _index = _selected_values(grid, settings["dataset_index"])
            values = numpy.asarray(values)
            exists = [False, False]
            for start in range(0, values.size, 65536):
                chunk = values.flat[start:start + 65536]
                exists[0] |= bool(numpy.any(chunk >= settings["isovalue"]))
                exists[1] |= bool(numpy.any(chunk <= -settings["isovalue"]))
            legend = [entry for entry, present in zip(legend, exists) if present]
            details.append("Signed values; colors indicate phase" if grid.semantic_role == "molecular_orbital" else "Signed scalar levels")
            if exists == [True, False] and grid.semantic_role != "molecular_orbital":
                details[-1] = "Positive scalar level"
            elif not any(exists):
                details[-1] = "No samples reach the selected isovalue"
        elif kind == "grid_volume":
            title += " volume"
            details.append(f"Optical density scale {_number(settings['density_scale'])} (display transfer)")
            legend = [{"label": "Positive values", "color": settings["positive_color"]}]
            if settings["signed"]:
                legend.append({"label": "Negative values", "color": settings["negative_color"]})
        elif kind == "grid_slice":
            title += " slice"
            scalar = scalar_legend(grid.semantic_role.replace("_", " "), unit)
        elif kind == "grid_profile":
            title += " profile"
    elif kind in {"property_on_surface", "nci_surface"}:
        surface, prop = entities["surface_grid"], entities["property_grid"]
        title = prop.semantic_role.replace("_", " ").capitalize() + " on " + surface.semantic_role.replace("_", " ")
        details.append(f"Surface = {_number(settings['surface_isovalue'])} {_unit(surface.data.unit)}")
        details.append(f"Surface dataset {settings['surface_dataset_index']} | Property dataset {settings['property_dataset_index']}")
        scalar = scalar_legend(prop.semantic_role.replace("_", " "), prop.data.unit)
    elif kind == "atomic_scalar":
        prop = entities["property"]
        title = prop.semantic_role.replace("_", " ").capitalize()
        scalar = scalar_legend(title, prop.data.unit,
            root.get("cb_scalar_display_min"), root.get("cb_scalar_display_max"), root.get("cb_scalar_colormap"))
    elif kind == "atomic_vector":
        prop = entities["property"]
        title = prop.semantic_role.replace("_", " ").capitalize() + " vectors"
        details.append(f"{_unit(prop.data.unit)} | Display scale {_number(settings['vector_scale'])}")
        if settings["as_force"]:
            details.append("Force = -gradient")
    elif kind in {"trajectory", "trajectory_force"}:
        frames = entities["frames"]
        index = int(root.get("cb_trajectory_frame_index", settings["frame_index"]))
        title = f"Trajectory | Frame {index + 1}/{frames.data.shape[0]}"
        if "cb_trajectory_time" in root:
            details.append(f"Source time {_number(root['cb_trajectory_time'])} {_unit(root['cb_trajectory_time_unit'])}")
        else:
            details.append("Source sequence; physical time unavailable")
        if kind == "trajectory_force":
            details.append(f"Force [{_unit(entities['force'].data.unit)}] | Display scale {_number(settings['vector_scale'])}")
            if root.get("cb_trajectory_force_status") != "current frame":
                details.append("Missing force values: arrows hidden")
    elif kind in {"vibration_mode", "phonon_mode", "vibration_spectrum_linked"}:
        modes, index = entities["modes"], settings["selection_index"]
        frequency = modes.data.values[index] if kind != "phonon_mode" else modes.data.values[settings["qpoint_index"], index]
        title = f"{'Phonon' if kind == 'phonon_mode' else 'Vibrational'} mode {index + 1}: {_number(frequency)} {_unit(modes.data.unit)}"
        if frequency < 0:
            title += " (imaginary)"
        phase_key = "cb_phonon_phase" if kind == "phonon_mode" else "cb_vibration_phase"
        details.append(f"Phase {_number(root.get(phase_key, settings['phase']))} rad | Animation phase, not physical time")
        if kind == "phonon_mode":
            qpoint = modes.qpoints.values[settings["qpoint_index"]]
            details.append("q = (" + ", ".join(_number(value) for value in qpoint) + ") fractional")
    elif kind == "fermi_surface":
        surface = entities["surface"]
        title = "Fermi surface"
        details.append(f"E_F = {_number(surface.fermi_energy)} eV | Spin index {surface.spin_index} | 2*pi reciprocal coordinates")
        if settings["color_property"]:
            label = root.get("cb_color_property", settings["color_property"])
            scalar = scalar_legend(label.replace("_", " "), root["cb_color_unit"], root["cb_color_min"], root["cb_color_max"])
        else:
            legend = [{"label": f"Band {entry['band_number']}", "color": entry["color"]}
                      for entry in json.loads(root["cb_band_legend"])]
    elif kind == "topology_graph":
        graph = entities["graph"]
        title = "QTAIM critical points and sampled paths"
        details.append(f"{len(graph.critical_point_ids)} critical points | {len(graph.paths)} sampled paths")
        if settings["color_property"] == "kind":
            from .topology_view import _KIND_CODE, _KIND_COLORS
            declared = {value.split("=", 1)[1] for value in root["cb_kind_legend"]}
            legend = [{"label": value.value.capitalize(), "color": _KIND_COLORS[_KIND_CODE[value]]}
                      for value in sorted(set(graph.kinds), key=lambda item: _KIND_CODE[item]) if value.value in declared]
        else:
            value = graph.field_values if settings["color_property"] == "field_value" else graph.laplacians
            scalar = scalar_legend(settings["color_property"].replace("_", " "), value.unit,
                                   root["cb_color_min"], root["cb_color_max"])
    elif kind in {"spectrum_plot", "electronic_spectrum_linked"}:
        spectrum = entities["spectrum"]
        title = spectrum.kind.value.upper() + " spectrum"
    elif kind in {"band_structure", "density_of_states", "band_dos_linked"}:
        details.append("Energy reference: " + settings["energy_reference"].replace("_", " "))
        if kind == "density_of_states" and (settings["atom_indices"] is not None or settings["orbital_labels"] is not None):
            title = "Projected density of states"
            details.append(f"Atoms (0-based): {settings['atom_indices']} | Orbitals: {settings['orbital_labels']}")
    # Sampling plots and quantitative atom colors stay emission-only even when
    # their shared template settings request shading for other representations.
    if (scalar is not None and settings["shaded"]
            and kind in {"property_on_surface", "nci_surface", "fermi_surface", "topology_graph"}):
        details.append("Morphology shading; Research preserves quantitative colors")
    return {"title": title, "details": details, "scalar": scalar, "categories": legend,
            "value_unit": scalar["unit"] if scalar else unit, "render_identity": plan.render_identity,
            "bindings": {name: {"id": str(entity.id), "revision": entity.revision} for name, entity in entities.items()}}


def create_render_annotations(plan, project, root, camera, *, template="research", aspect=4/3, collection=None):
    """Create owned text/mesh objects in camera space; return objects and metadata."""
    from .scene_preset_view import _remove_objects

    plan = validate_scene_plan(plan, project)
    if root.get("cb_scene_render_identity") != plan.render_identity:
        raise ValueError("annotation root does not match the current scientific View")
    if template not in {"research", "teaching"}:
        raise ValueError("unknown annotation template")
    width, height, center_x, center_y = _camera_plane(camera, aspect)
    metadata = _description(plan, project, root)
    metadata.update(template=template, plane_distance=1., aspect=aspect,
                    reserved_margins={"top": .10, "bottom": .13 if metadata["scalar"] or metadata["categories"] else .04})
    target = collection or bpy.context.collection
    objects, resources = [], []

    def material(name, color):
        value = flat_material(name, color)
        resources.append(value)
        return value

    def object_for(data, name, x, y):
        resources.append(data)
        data["cb_scientific_owned"] = True
        obj = bpy.data.objects.new(name, data)
        objects.append(obj)
        target.objects.link(obj)
        obj.parent = camera
        obj.location = (center_x + x, center_y + y, -1.)
        obj["cb_scientific_owned"] = True
        obj["cb_render_annotation"] = True
        for attribute in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
            setattr(obj, attribute, False)
        return obj

    def text(body, x, y, size=.026, max_width=.90):
        curve = bpy.data.curves.new("Scientific Annotation", "FONT")
        obj = object_for(curve, "Scientific " + body[:40], x * width, y * height)
        curve.body, curve.align_x, curve.align_y = body, "CENTER", "CENTER"
        curve.size = height * size
        curve.materials.append(text_material)
        bpy.context.view_layer.update()
        if obj.dimensions.x > max_width * width:
            curve.size *= max_width * width / obj.dimensions.x
        return obj

    def rectangle(name, x, y, w, h, shader):
        mesh = bpy.data.meshes.new(name)
        obj = object_for(mesh, name, x * width, y * height)
        mesh.from_pydata([(-w*width/2, -h*height/2, 0), (w*width/2, -h*height/2, 0),
                          (w*width/2, h*height/2, 0), (-w*width/2, h*height/2, 0)], [], [(0, 1, 2, 3)])
        mesh.materials.append(shader)
        mesh.update()
        return obj

    try:
        text_material = material("Scientific Annotation Ink", (.035, .045, .06, 1.) if template == "research" else (.94, .96, 1., 1.))
        text(metadata["title"], 0, .455, .031)
        if metadata["details"]:
            text(" | ".join(metadata["details"]), 0, .409, .023)
        scalar = metadata["scalar"]
        if scalar:
            minimum, maximum = scalar["color_min"], scalar["color_max"]
            stops = color_stops(minimum, maximum, scalar["colormap"])
            scalar["stops"] = [[position, list(color)] for position, color in stops]
            scalar["zero_position"] = -minimum / (maximum - minimum) if minimum <= 0 <= maximum else None
            shader = scalar_material("Scientific Render Legend", minimum, maximum,
                attribute_name="cb_render_legend_value", colormap=scalar["colormap"], shaded=False)
            resources.append(shader)
            bar = rectangle("Scientific Colorbar", 0, -.438, .64, .018, shader)
            attribute = bar.data.attributes.new("cb_render_legend_value", "FLOAT", "POINT")
            attribute.data.foreach_set("value", (minimum, maximum, maximum, minimum))
            bar["cb_legend_min"], bar["cb_legend_max"] = minimum, maximum
            text(f"{scalar['label']} [{_unit(scalar['unit'])}]", 0, -.396, .022)
            ticks = [(0., minimum), (1., maximum)]
            if minimum < 0 < maximum:
                ticks.append((scalar["zero_position"], 0.))
            for position, value in ticks:
                x = -.32 + .64 * position
                rectangle("Scientific Tick", x, -.454, .0012, .011, text_material)
                # Put a near-endpoint zero label on the upper side to keep both exact numbers legible.
                near_end = value == 0 and min(position, 1-position) < .12
                text(_number(value), x, -.417 if near_end else -.478, .020, max_width=.15)
        elif metadata["categories"]:
            entries = metadata["categories"]
            columns = min(5, len(entries))
            rows = math.ceil(len(entries) / columns)
            row_height = min(.029, .084 / rows)
            for index, entry in enumerate(entries):
                x = -.40 + (index % columns + .5) * .8 / columns
                y = -.403 - (index // columns) * row_height
                rectangle("Scientific Category", x - .035, y, .016, .016,
                          material("Scientific Category Color", entry["color"]))
                text(entry["label"], x + .025, y, min(.022, .85 * row_height), max_width=.8 / columns - .025)
        return tuple(objects), metadata
    except BaseException:
        _remove_objects(objects)
        _remove_unused(resources)
        raise
