"""Shared temporary render scope for scientific views and orbital image batches."""

from .core.scene_preset import builtin_scene_presets, plan_scene_preset, scene_plan_document


class RenderCancelled(RuntimeError):
    pass


def _coordinate_metadata(plan, project, objects):
    """Keep display graph coordinates distinct from real/reciprocal space."""
    kind = plan.view_kind
    if kind == "fermi_surface":
        return {"display_coordinate_unit": "inverse_angstrom",
                "display_coordinate_system": "reciprocal_cartesian_2pi"}
    plotted = {"spectrum_plot", "band_structure", "density_of_states", "band_dos_linked",
               "grid_profile", "grid_colorbar", "vibration_spectrum_linked", "electronic_spectrum_linked"}
    if kind not in plotted:
        return {"display_coordinate_unit": "angstrom", "display_coordinate_system": "spatial_cartesian"}
    entities = {binding.name: project.datasets[binding.entity_id] for binding in plan.bindings
                if binding.entity_kind == "dataset"}
    axes = []
    for name, entity in entities.items():
        if name == "spectrum":
            x_unit, y_unit = entity.axis.unit, entity.data.unit
        elif name == "band":
            x_unit, y_unit = entity.distances.unit, entity.data.unit
        elif name == "dos":
            x_unit, y_unit = entity.data.unit, entity.energies.unit
        elif name == "grid" and kind in {"grid_profile", "grid_colorbar"}:
            x_unit = entity.coordinate_unit if kind == "grid_profile" else entity.data.unit
            y_unit = entity.data.unit if kind == "grid_profile" else None
        else:
            continue
        plot = next((obj for obj in objects if obj.get("cb_dataset_id") == str(entity.id)
                     and obj.get("cb_plot_coordinate_system")), None)
        if plot is not None:
            x_unit, y_unit = plot.get("cb_plot_x_unit", x_unit), plot.get("cb_plot_y_unit", y_unit)
        axes.append({"binding": name, "dataset_id": str(entity.id), "x_unit": x_unit, "y_unit": y_unit})
    frames = [{"dataset_id": obj.get("cb_dataset_id"),
               "coordinate_system": obj["cb_plot_coordinate_system"],
               "x_range": list(obj["cb_plot_x_range"]), "y_range": list(obj["cb_plot_y_range"]),
               "width": obj["cb_plot_width"], "height": obj["cb_plot_height"],
               "matrix_world": [list(row) for row in obj.matrix_world]}
              for obj in objects if obj.get("cb_plot_coordinate_system")]
    mixed = kind in {"vibration_spectrum_linked", "electronic_spectrum_linked"}
    return {"display_coordinate_unit": None,
            "display_coordinate_system": "spatial_and_plot" if mixed else "plot",
            "spatial_component_unit": "angstrom" if mixed else None,
            "scientific_axes": axes, "plot_frames": frames}


class RenderScope:
    """Own only temporary publication objects; restore every touched display value."""

    def __init__(self, context, project, structure=None, *, template=None,
                 width=2400, height=1800, samples=256, direction=None,
                 framing_margin=1.40, volume_focus_threshold=0.):
        import math

        if template not in {None, "research", "teaching"}:
            raise ValueError("unknown render template")
        if any(type(value) is not int or value < 1 for value in (width, height, samples)):
            raise ValueError("resolution and samples must be positive integers")
        if direction is not None:
            direction = tuple(direction)
            if (len(direction) != 3 or not all(math.isfinite(value) for value in direction)
                    or sum(value * value for value in direction) == 0):
                raise ValueError("camera direction must be finite and nonzero")
        if not math.isfinite(framing_margin) or not 1. < framing_margin <= 5.:
            raise ValueError("framing margin must be greater than 1 and at most 5")
        if not math.isfinite(volume_focus_threshold) or volume_focus_threshold < 0:
            raise ValueError("volume focus threshold must be finite and nonnegative")
        self.direction = direction
        self.framing_margin = framing_margin
        self.volume_focus_threshold = volume_focus_threshold
        self.context, self.scene = context, context.scene
        self.project, self.structure = project, structure
        self.objects = ()
        self.collection = None
        self.camera_copy = None
        self.template, self.width, self.height, self.samples = template, width, height, samples
        self.lights = []
        self.world_copy = None
        self.animation_framed = False
        self.annotation_document = None

    def __enter__(self):
        import bpy
        from .scene_preset_view import apply_scene_preset

        scene = self.scene
        self.camera = scene.camera
        self.hidden = [(obj, obj.hide_render) for obj in scene.objects]
        self.selection = tuple(self.context.selected_objects)
        self.active = self.context.view_layer.objects.active
        self.render_state = {key: getattr(scene.render, key) for key in (
            "filepath", "use_file_extension", "use_compositing", "use_sequencer",
            "engine", "resolution_x", "resolution_y", "resolution_percentage", "film_transparent",
            "pixel_aspect_x", "pixel_aspect_y", "use_border", "use_crop_to_border")}
        self.image = {key: getattr(scene.render.image_settings, key) for key in (
            "media_type", "file_format", "color_mode", "color_depth", "color_management")}
        self.view_state = {key: getattr(scene.view_settings, key) for key in (
            "view_transform", "look", "exposure", "gamma", "use_curve_mapping")}
        self.cycles_state = {key: getattr(scene.cycles, key) for key in (
            "samples", "use_adaptive_sampling", "adaptive_threshold", "use_denoising", "seed")}
        self.world = scene.world
        self.structure_plan = (plan_scene_preset(builtin_scene_presets()["structure_publication"],
                                  self.project, {"structure": self.structure.id},
                                  {"template": self.template or "research"})
                               if self.structure is not None else None)
        try:
            self.collection = bpy.data.collections.new("Scientific Image Export")
            scene.collection.children.link(self.collection)
            # Capture the evaluated camera once, including parent/constraint transforms.
            camera_data = self.camera.data.copy() if self.camera else bpy.data.cameras.new("Scientific Camera")
            try:
                self.camera_copy = bpy.data.objects.new("Orbital Export Camera", camera_data)
            except BaseException:
                bpy.data.cameras.remove(camera_data)
                raise
            self.collection.objects.link(self.camera_copy)
            if self.camera:
                self.camera_copy.matrix_world = self.camera.evaluated_get(
                    self.context.evaluated_depsgraph_get()).matrix_world.copy()
            scene.camera = self.camera_copy
            for obj, _hidden in self.hidden:
                if self.template or obj.type not in {"CAMERA", "LIGHT"}:
                    obj.hide_render = True
            scene.render.use_file_extension = True
            # A scene compositor can write outside the output package via File Output nodes.
            scene.render.use_compositing = False
            scene.render.use_sequencer = False
            scene.render.image_settings.media_type = "IMAGE"
            scene.render.image_settings.file_format = "PNG"
            scene.render.image_settings.color_mode = "RGBA"
            scene.render.image_settings.color_depth = "8"
            scene.render.image_settings.color_management = "FOLLOW_SCENE"
            if self.structure_plan is not None:
                self.objects = apply_scene_preset(self.structure_plan, self.project, collection=self.collection)
            if self.template:
                self._configure_template()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _configure_template(self):
        import bpy

        scene = self.scene
        scene.render.engine = "CYCLES"
        scene.render.resolution_x, scene.render.resolution_y = self.width, self.height
        scene.render.resolution_percentage = 100
        scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1.
        scene.render.use_border = scene.render.use_crop_to_border = False
        scene.render.film_transparent = False
        scene.cycles.samples = self.samples
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = .01
        scene.cycles.use_denoising = True
        scene.cycles.seed = 0
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.
        scene.view_settings.gamma = 1.
        scene.view_settings.use_curve_mapping = False
        self.world_copy = bpy.data.worlds.new("Scientific Background")
        self.world_copy.use_nodes = True
        background = self.world_copy.node_tree.nodes.get("Background")
        background.inputs["Color"].default_value = ((.82, .84, .87, 1.) if self.template == "research"
                                                    else (.012, .019, .032, 1.))
        background.inputs["Strength"].default_value = .8 if self.template == "research" else .5
        scene.world = self.world_copy
        self.camera_copy.data.type = "ORTHO" if self.template == "research" else "PERSP"
        self.camera_copy.data.lens = 50.
        self.camera_copy.data.sensor_fit = "HORIZONTAL"
        self.camera_copy.data.shift_x = self.camera_copy.data.shift_y = 0.
        self.camera_copy.data.dof.use_dof = False
        for name in ("Key", "Fill", "Rim"):
            data = bpy.data.lights.new("Scientific " + name, "AREA")
            obj = bpy.data.objects.new("Scientific " + name, data)
            self.collection.objects.link(obj)
            self.lights.append(obj)

    def _bounds(self, objects):
        from mathutils import Vector
        from .scene_preset_view import _owned_components

        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        corners = []
        for obj in _owned_components(objects):
            if obj.hide_render or obj.type not in {"MESH", "CURVE", "FONT", "VOLUME"}:
                continue
            evaluated = obj.evaluated_get(depsgraph)
            if obj.type == "VOLUME" and "cb_surface_isovalue" in obj:
                # A Volume's bound_box can still describe its input VDB after
                # Geometry Nodes outputs a Mesh. Frame the actual isosurface.
                geometry = evaluated.evaluated_geometry()
                mesh = geometry.mesh
                if mesh is not None and mesh.vertices:
                    minimum = tuple(min(v.co[i] for v in mesh.vertices) for i in range(3))
                    maximum = tuple(max(v.co[i] for v in mesh.vertices) for i in range(3))
                    corners.extend(evaluated.matrix_world @ Vector((x, y, z))
                                   for x in (minimum[0], maximum[0])
                                   for y in (minimum[1], maximum[1])
                                   for z in (minimum[2], maximum[2]))
                    continue
            corners.extend(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
        return corners

    def frame_objects(self, objects, *, flat=False, extra_corners=()):
        """Fit evaluated geometry, including labels, without modifying any source View."""
        import math
        from mathutils import Vector

        corners = self._bounds(objects) + list(extra_corners)
        if not corners:
            raise ValueError("View has no renderable geometry")
        minimum = Vector(tuple(min(point[axis] for point in corners) for axis in range(3)))
        maximum = Vector(tuple(max(point[axis] for point in corners) for axis in range(3)))
        center = (minimum + maximum) * .5
        direction = Vector(self.direction or ((0., 0., 1.) if flat else (1.2, -1.6, 1.1))).normalized()
        camera = self.camera_copy
        # Looking straight down -Z has an ambiguous up-vector for to_track_quat.
        camera.rotation_euler = ((0., 0., 0.) if abs(direction.z - 1.) < 1.e-12
                                 else (-direction).to_track_quat("-Z", "Y").to_euler())
        rotation = camera.rotation_euler.to_matrix()
        view_points = [rotation.transposed() @ (point - center) for point in corners]
        width = max(p.x for p in view_points) - min(p.x for p in view_points)
        height = max(p.y for p in view_points) - min(p.y for p in view_points)
        span = max(width, height * self.width / self.height, .5) * self.framing_margin
        camera.data.ortho_scale = span
        tan_x = math.tan(camera.data.angle_x * .5)
        tan_y = tan_x * self.height / self.width
        distance = max(point.z + max(abs(point.x) / tan_x, abs(point.y) / tan_y) * self.framing_margin
                       for point in view_points) + .1
        distance = max(distance, 2.)
        camera.location = center + direction * distance
        camera.data.clip_start = .01
        camera.data.clip_end = max(100., distance * 5.)
        light_scale = max((maximum - minimum).length, 1.)
        for obj, offset, energy in zip(self.lights, ((-1.5, -1.3, 2.), (1.8, -.5, .7), (.3, 1.8, 1.2)),
                                       (120., 45., 80.), strict=True):
            obj.location = center + Vector(offset) * light_scale
            obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
            obj.data.energy = energy * light_scale ** 2
            obj.data.size = light_scale * 1.4

    def render(self, plan, destination, cache_root, *, matrix_world=None, phase=None,
               frame_index=None, is_cancelled=None):
        import bpy
        from pathlib import Path
        from .scene_preset_view import apply_scene_preset, _remove_objects

        # Grid Volume accepts an existing directory or an explicit .vdb file.
        # This API receives a cache root, including on the first exported frame.
        Path(cache_root).mkdir(parents=True, exist_ok=True)
        objects = apply_scene_preset(plan, self.project, collection=self.collection,
                                     cache_root=cache_root)
        annotations = ()
        try:
            if phase is not None and frame_index is not None:
                raise ValueError("Choose a trajectory frame or an animation phase")
            if self.template and plan.view_kind == "grid_profile":
                # The source path remains in the interactive View. A standalone
                # plot render frames only the graph and its scientific axes.
                objects[0].hide_render = True
            if matrix_world is not None:
                objects[0].matrix_world = matrix_world
                if self.objects:
                    self.objects[0].matrix_world = matrix_world
            envelope = []
            frame_metadata = None
            if frame_index is not None:
                from .scene_preset_view import apply_scientific_frame

                if self.template and not self.animation_framed:
                    frames = self.project.datasets[next(binding.entity_id for binding in plan.bindings if binding.name == "frames")]
                    for index in range(frames.data.shape[0]):
                        if is_cancelled is not None and is_cancelled():
                            raise RenderCancelled("Trajectory framing cancelled")
                        apply_scientific_frame(objects[0], self.project, index)
                        # Keep just running extrema, independent of sequence length.
                        corners = self._bounds(objects) + envelope
                        from mathutils import Vector
                        minimum = tuple(min(point[axis] for point in corners) for axis in range(3))
                        maximum = tuple(max(point[axis] for point in corners) for axis in range(3))
                        envelope = [Vector((x, y, z)) for x in (minimum[0], maximum[0])
                                    for y in (minimum[1], maximum[1]) for z in (minimum[2], maximum[2])]
                frame_metadata = apply_scientific_frame(objects[0], self.project, frame_index)
            if phase is not None:
                import math
                from .scene_preset_view import apply_scientific_phase

                if self.template and not self.animation_framed:
                    for step in range(16):
                        apply_scientific_phase(objects[0], self.project, math.tau * step / 16)
                        envelope.extend(self._bounds(objects))
                apply_scientific_phase(objects[0], self.project, phase)
            animated = phase is not None or frame_index is not None
            if self.template and (not animated or not self.animation_framed):
                framing_objects = (*self.objects, *objects)
                if plan.view_kind == "grid_volume" and self.volume_focus_threshold > 0:
                    import numpy
                    from mathutils import Vector
                    from .core.grid_semantics import _selected_values
                    from .core.grid_cache_service import _ANGSTROM_SCALE

                    grid = self.project.datasets[plan.bindings[0].entity_id]
                    values, _index = _selected_values(grid, dict(plan.settings)["dataset_index"])
                    values = numpy.asarray(values)  # Lazy .npy arrays expose a read-only mmap view.
                    lower, upper = numpy.full(3, numpy.inf), numpy.full(3, -numpy.inf)
                    for start in range(0, values.size, 65536):
                        if is_cancelled is not None and is_cancelled():
                            raise RenderCancelled("Volume camera framing cancelled")
                        selected = numpy.flatnonzero(numpy.abs(values.flat[start:start + 65536]) >= self.volume_focus_threshold)
                        if selected.size:
                            coordinates = numpy.asarray(numpy.unravel_index(selected + start, values.shape)).T
                            lower = numpy.minimum(lower, coordinates.min(axis=0))
                            upper = numpy.maximum(upper, coordinates.max(axis=0))
                    if not numpy.isfinite(lower).all():
                        raise ValueError("No volume samples reach the camera focus threshold")
                    lower, upper = lower - 1, upper + 1
                    for x in (lower[0], upper[0]):
                        for y in (lower[1], upper[1]):
                            for z in (lower[2], upper[2]):
                                point = (numpy.asarray(grid.origin) + numpy.asarray((x, y, z)) @ grid.step_vectors) * _ANGSTROM_SCALE[grid.coordinate_unit]
                                envelope.append(objects[0].matrix_world @ Vector(point))
                    framing_objects = self.objects
                self.frame_objects(framing_objects, flat=plan.view_kind in {
                    "spectrum_plot", "band_structure", "density_of_states", "band_dos_linked", "grid_colorbar"},
                    extra_corners=envelope)
                self.animation_framed = animated
            if self.template:
                from .render_annotations import create_render_annotations

                annotations, self.annotation_document = create_render_annotations(
                    plan, self.project, objects[0], self.camera_copy, template=self.template,
                    aspect=self.width / self.height, collection=self.collection)
            self.scene.render.filepath = str(destination)
            result = bpy.ops.render.render(write_still=True, scene=self.scene.name)
            if "FINISHED" not in result:
                raise RenderCancelled("Rendering was cancelled")
            with destination.open("rb") as stream:
                if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                    raise ValueError("Blender did not produce a PNG image")
            document = self.document()
            document.update(_coordinate_metadata(plan, self.project, objects))
            if frame_metadata is not None:
                document["trajectory_frame"] = frame_metadata
            return document
        finally:
            _remove_objects(annotations)
            _remove_objects(objects)

    def document(self):
        import bpy
        scene, camera = self.scene, self.camera_copy
        return {
            "blender_version": bpy.app.version_string,
            "template": self.template,
            "annotations": self.annotation_document,
            "framing": {"direction": self.direction, "margin": self.framing_margin,
                        "volume_focus_threshold": self.volume_focus_threshold,
                        "focus_affects": "camera only; all volume values remain rendered"},
            "structure_view": scene_plan_document(self.structure_plan) if self.structure_plan else None,
            "camera": {"name": camera.name, "matrix_world": [list(row) for row in camera.matrix_world],
                       **{key: getattr(camera.data, key) for key in (
                           "type", "lens", "ortho_scale", "sensor_fit", "sensor_width", "sensor_height",
                           "shift_x", "shift_y", "clip_start", "clip_end")}},
            "lights": [{"name": obj.name, "hide_render": hidden,
                        "matrix_world": [list(row) for row in obj.matrix_world],
                        "type": obj.data.type, "energy": obj.data.energy,
                        "color": list(obj.data.color)}
                       for obj, hidden in ([(light, False) for light in self.lights] if self.template else self.hidden)
                       if obj.type == "LIGHT"],
            "world": None if scene.world is None else {
                "name": scene.world.name, "color": list(scene.world.color),
                "use_nodes": scene.world.use_nodes,
                "backgrounds": [{"color": list(node.inputs["Color"].default_value),
                                 "strength": node.inputs["Strength"].default_value,
                                 "color_linked": node.inputs["Color"].is_linked,
                                 "strength_linked": node.inputs["Strength"].is_linked}
                                for node in scene.world.node_tree.nodes if node.type == "BACKGROUND"]
                               if scene.world.node_tree else []},
            "render": {key: getattr(scene.render, key) for key in (
                "engine", "resolution_x", "resolution_y", "resolution_percentage",
                "pixel_aspect_x", "pixel_aspect_y", "film_transparent", "use_border",
                "use_crop_to_border", "border_min_x", "border_max_x", "border_min_y", "border_max_y")},
            "color_management": {key: getattr(scene.view_settings, key) for key in (
                "view_transform", "look", "exposure", "gamma")},
            "image_format": dict(file_format="PNG", color_mode="RGBA", color_depth="8"),
            "compositor_enabled": False,
            "cycles": {key: getattr(scene.cycles, key) for key in self.cycles_state},
            "display_coordinate_unit": "angstrom",
        }

    def __exit__(self, *_error):
        import bpy
        from .scene_preset_view import _remove_objects

        try:
            _remove_objects(self.objects)
            self.objects = ()
            for light in self.lights:
                data = light.data
                bpy.data.objects.remove(light, do_unlink=True)
                if data.users == 0:
                    bpy.data.lights.remove(data)
            self.lights.clear()
            if self.camera_copy is not None:
                data = self.camera_copy.data
                bpy.data.objects.remove(self.camera_copy, do_unlink=True)
                self.camera_copy = None
                if data.users == 0:
                    bpy.data.cameras.remove(data)
            if self.collection is not None:
                bpy.data.collections.remove(self.collection)
                self.collection = None
        finally:
            self.scene.camera = self.camera
            self.scene.world = self.world
            if self.world_copy is not None and self.world_copy.users == 0:
                bpy.data.worlds.remove(self.world_copy)
                self.world_copy = None
            for key, value in self.view_state.items():
                setattr(self.scene.view_settings, key, value)
            for key, value in self.cycles_state.items():
                setattr(self.scene.cycles, key, value)
            for key, value in self.render_state.items():
                setattr(self.scene.render, key, value)
            for key, value in self.image.items():
                setattr(self.scene.render.image_settings, key, value)
            for obj, hidden in self.hidden:
                try:
                    obj.hide_render = hidden
                except ReferenceError:
                    continue
            for obj in tuple(self.context.selected_objects):
                obj.select_set(False)
            for obj in self.selection:
                try:
                    obj.select_set(True)
                except ReferenceError:
                    continue
            try:
                self.context.view_layer.objects.active = self.active
            except ReferenceError:
                pass
