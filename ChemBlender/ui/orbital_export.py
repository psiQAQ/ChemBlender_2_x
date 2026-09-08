"""Sequential orbital renders with isolated display state and atomic publication."""

import json
import math
import os
import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from ..core.analysis_report import (
    build_analysis_report, describe_report_artifact, write_analysis_report_bundle,
)
from ..core.orbital_browser import orbital_rows
from ..core.scene_preset import builtin_scene_presets, plan_scene_preset, scene_plan_document
from .wavefunction import (
    WavefunctionJob, _JOBS, _grid_parameters, _selected_orbitals,
    operation_memory, wavefunction_inputs, worker_configuration,
)


_EXPORTS = {}


class OrbitalExportCancelled(RuntimeError):
    pass


def parse_orbital_numbers(value, maximum):
    """Parse explicit 1-based numbers/ranges, retaining order and removing repeats."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter orbital numbers, for example 5,6 or 3-6")
    result = []
    for token in value.split(","):
        match = re.fullmatch(r"\s*([0-9]+)\s*(?:-\s*([0-9]+)\s*)?", token)
        if match is None:
            raise ValueError("Use comma-separated orbital numbers or ascending ranges")
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= maximum:
            raise ValueError(f"Orbital numbers must be within 1..{maximum}")
        result.extend(number for number in range(first, last + 1) if number not in result)
    return tuple(result)


def _display_settings(isovalue, positive_color, negative_color, opacity):
    if not math.isfinite(isovalue) or isovalue <= 0:
        raise ValueError("Isovalue must be positive and finite")
    if not math.isfinite(opacity) or not 0 <= opacity <= 1:
        raise ValueError("Opacity must be between zero and one")
    colors = tuple(tuple(float(value) for value in color)
                   for color in (positive_color, negative_color))
    if any(len(color) != 4 or any(not math.isfinite(value) or not 0 <= value <= 1
                                 for value in color) for color in colors):
        raise ValueError("Phase colors must contain four finite values within 0..1")
    return dict(dataset_index=0, isovalue=float(isovalue), opacity=float(opacity),
                positive_color=colors[0], negative_color=colors[1])


def preflight_orbital_export(context, session, settings, *, orbital_numbers, destination,
                            isovalue=.05, positive_color=(.15, .35, .95, 1.),
                            negative_color=(.95, .20, .15, 1.), opacity=1.):
    """Validate without creating files, objects, or launching a worker."""
    if context.scene.camera is None or context.scene.camera.type != "CAMERA":
        raise ValueError("Set the scene camera before exporting orbital images")
    if session.id in _EXPORTS or session.id in _JOBS:
        raise ValueError("Wait for the current wavefunction or orbital export task")
    project = session.project
    orbitals = _selected_orbitals(session, settings)
    if orbitals is None:
        raise ValueError("Select an orbital set before exporting")
    channel = settings.channel or orbitals.channels[0].label
    parameters = _grid_parameters(settings)
    rows = orbital_rows(project, orbitals, channel, grid_parameters=parameters)
    if isinstance(orbital_numbers, str):
        numbers = parse_orbital_numbers(orbital_numbers, len(rows))
    else:
        numbers = tuple(orbital_numbers)
        if not numbers or any(type(number) is not int or not 1 <= number <= len(rows)
                              for number in numbers):
            raise ValueError("Orbital numbers must be a non-empty 1-based integer sequence")
        numbers = tuple(dict.fromkeys(numbers))
    for number in numbers:
        if rows[number - 1].evaluation_error:
            raise ValueError(rows[number - 1].evaluation_error)
    display = _display_settings(isovalue, positive_color, negative_color, opacity)
    target = Path(destination).expanduser().absolute()
    if os.path.lexists(target):
        raise ValueError("Choose a new output directory; existing directories are never replaced")
    parent = target.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("The output parent must be an existing directory")
    target = parent / target.name
    inputs = wavefunction_inputs(project, "wavefunction.mo_grid", orbitals.id)
    worker = None
    if any(not rows[number - 1].cached_dataset_ids for number in numbers):
        memory = operation_memory(project, orbitals, "wavefunction.mo_grid", parameters)
        if memory["estimated_bytes"] > settings.memory_limit_mb * 1024 ** 2:
            raise ValueError("MO evaluation exceeds the configured memory budget")
        worker = worker_configuration(settings)
    return SimpleNamespace(project=project, orbitals=orbitals, channel=channel,
                           parameters=parameters, numbers=numbers, inputs=inputs,
                           display=display, target=target, worker=worker)


class _RenderScope:
    """Own only temporary publication objects; restore every touched display value."""

    def __init__(self, context, project, structure):
        self.context, self.scene = context, context.scene
        self.project, self.structure = project, structure
        self.objects = ()
        self.collection = None
        self.camera_copy = None

    def __enter__(self):
        import bpy
        from ..scene_preset_view import apply_scene_preset

        scene = self.scene
        self.camera = scene.camera
        self.hidden = [(obj, obj.hide_render) for obj in scene.objects]
        self.selection = tuple(self.context.selected_objects)
        self.active = self.context.view_layer.objects.active
        self.render_state = {key: getattr(scene.render, key) for key in (
            "filepath", "use_file_extension", "use_compositing", "use_sequencer")}
        self.image = {key: getattr(scene.render.image_settings, key) for key in (
            "file_format", "color_mode", "color_depth")}
        self.structure_plan = plan_scene_preset(builtin_scene_presets()["structure_publication"],
                                               self.project, {"structure": self.structure.id}, {})
        try:
            self.collection = bpy.data.collections.new("Orbital Image Export")
            scene.collection.children.link(self.collection)
            # Capture the evaluated camera once, including parent/constraint transforms.
            camera_data = self.camera.data.copy()
            try:
                self.camera_copy = bpy.data.objects.new("Orbital Export Camera", camera_data)
            except BaseException:
                bpy.data.cameras.remove(camera_data)
                raise
            self.collection.objects.link(self.camera_copy)
            self.camera_copy.matrix_world = self.camera.evaluated_get(
                self.context.evaluated_depsgraph_get()).matrix_world.copy()
            scene.camera = self.camera_copy
            for obj, _hidden in self.hidden:
                if obj.type not in {"CAMERA", "LIGHT"}:
                    obj.hide_render = True
            scene.render.use_file_extension = True
            # A scene compositor can write outside the output package via File Output nodes.
            scene.render.use_compositing = False
            scene.render.use_sequencer = False
            scene.render.image_settings.file_format = "PNG"
            scene.render.image_settings.color_mode = "RGBA"
            scene.render.image_settings.color_depth = "8"
            self.objects = apply_scene_preset(self.structure_plan, self.project,
                                              collection=self.collection)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def render(self, plan, destination, cache_root):
        import bpy
        from ..scene_preset_view import apply_scene_preset, _remove_objects

        objects = apply_scene_preset(plan, self.project, collection=self.collection,
                                     cache_root=cache_root)
        try:
            self.scene.render.filepath = str(destination)
            result = bpy.ops.render.render(write_still=True, scene=self.scene.name)
            if "FINISHED" not in result:
                raise OrbitalExportCancelled("Rendering was cancelled")
            with destination.open("rb") as stream:
                if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                    raise ValueError("Blender did not produce a PNG image")
        finally:
            _remove_objects(objects)

    def document(self):
        import bpy
        scene, camera = self.scene, self.camera_copy
        return {
            "blender_version": bpy.app.version_string,
            "structure_view": scene_plan_document(self.structure_plan),
            "camera": {"name": self.camera.name, "matrix_world": [list(row) for row in camera.matrix_world],
                       **{key: getattr(camera.data, key) for key in (
                           "type", "lens", "ortho_scale", "sensor_fit", "sensor_width", "sensor_height",
                           "shift_x", "shift_y", "clip_start", "clip_end")}},
            "lights": [{"name": obj.name, "hide_render": hidden,
                        "matrix_world": [list(row) for row in obj.matrix_world],
                        "type": obj.data.type, "energy": obj.data.energy,
                        "color": list(obj.data.color)}
                       for obj, hidden in self.hidden if obj.type == "LIGHT"],
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
            "display_coordinate_unit": "angstrom",
        }

    def __exit__(self, *_error):
        import bpy
        from ..scene_preset_view import _remove_objects

        try:
            _remove_objects(self.objects)
            self.objects = ()
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


def _release_export(state):
    if _EXPORTS.get(state.session_id) is state:
        _EXPORTS.pop(state.session_id)
    if state.manager is not None:
        try:
            if state.timer is not None:
                state.manager.event_timer_remove(state.timer)
        finally:
            state.timer = None
            state.manager.progress_end()
            state.manager = None


def clear_orbital_exports(session=None):
    for state in tuple(_EXPORTS.values()):
        if session is None or state.session_id == session.id:
            state.cancelled = True
            try:
                state.generator.close()
            finally:
                _release_export(state)


def iter_orbital_images(context, session, settings, *, orbital_numbers, destination,
                       is_cancelled=None, isovalue=.05, positive_color=(.15, .35, .95, 1.),
                       negative_color=(.95, .20, .15, 1.), opacity=1.):
    """Return a main-thread iterator yielding {stage, progress}; close it on abandonment.

    StopIteration.value is the published directory. Computed scientific grids are
    committed individually; no images or report are published until all succeed.
    """
    preflight = preflight_orbital_export(
        context, session, settings, orbital_numbers=orbital_numbers, destination=destination,
        isovalue=isovalue, positive_color=positive_color, negative_color=negative_color, opacity=opacity)
    state = SimpleNamespace(session_id=session.id, cancelled=False, generator=None,
                            manager=None, timer=None)
    consumed_grids = {}

    def check():
        if state.cancelled or (is_cancelled is not None and is_cancelled()):
            raise OrbitalExportCancelled("Orbital image export was cancelled")
        if session.project is not preflight.project:
            raise ValueError("The active project changed during orbital image export")
        for entity in preflight.inputs:
            registry = (session.project.structures if entity is preflight.inputs[0] else
                        session.project.basis_sets if entity is preflight.inputs[1] else
                        session.project.orbital_sets)
            if registry.get(entity.id) is None or registry[entity.id].revision != entity.revision:
                raise ValueError("Wavefunction inputs changed during orbital image export")
        for identity, (grid, revision) in consumed_grids.items():
            current = preflight.project.datasets.get(identity)
            if current is not grid or current.revision != revision:
                raise ValueError("An orbital grid changed during image export")

    def iterate():
        active_entity = session.active_entity_id
        browser = getattr(context.scene, "chemblender_project_browser", None)
        browser_entity = browser.active_entity_id if browser is not None else None
        job = None
        try:
            # Arm finally before returning the public iterator, without creating resources.
            yield {"stage": "Ready", "progress": 0.}
            check()
            with TemporaryDirectory(prefix=".cb-orbitals-", dir=preflight.target.parent) as temporary:
                root = Path(temporary)
                (root / "images").mkdir()
                records, dataset_ids, artifacts = [], [], []
                with _RenderScope(context, preflight.project, preflight.inputs[0]) as renderer:
                    document = renderer.document()
                    for ordinal, number in enumerate(preflight.numbers):
                        check()
                        row = orbital_rows(preflight.project, preflight.orbitals, preflight.channel,
                                           grid_parameters=preflight.parameters)[number - 1]
                        cached = bool(row.cached_dataset_ids)
                        if cached:
                            grid = preflight.project.datasets[row.cached_dataset_ids[0]]
                        else:
                            if preflight.worker is None:
                                raise ValueError("A previously available orbital cache was removed")
                            job = WavefunctionJob(session, "wavefunction.mo_grid", preflight.inputs,
                                {**preflight.parameters, "channel": preflight.channel, "orbital_index": number - 1},
                                python_executable=preflight.worker[0], working_directory=preflight.worker[1])
                            job.start()
                            while not job.worker.done:
                                check()
                                status = job.task.snapshot()
                                yield {"stage": f"MO {number}: {status.stage}",
                                       "progress": (ordinal + .7 * status.progress) / len(preflight.numbers)}
                            check()
                            grid = job.publish(session)
                            job.close()
                            job = None
                        consumed_grids[grid.id] = (grid, grid.revision)
                        check()
                        plan = plan_scene_preset(builtin_scene_presets()["signed_isosurface"],
                                                 preflight.project, {"grid": grid.id}, preflight.display)
                        filename = f"images/{preflight.channel}-mo-{number:04d}.png"
                        yield {"stage": f"Render MO {number}",
                               "progress": (ordinal + .7) / len(preflight.numbers)}
                        check()
                        with TemporaryDirectory(prefix="vdb-", dir=root) as cache:
                            renderer.render(plan, root / filename, Path(cache))
                        check()
                        artifacts.append(describe_report_artifact(root, filename, role="orbital_image", media_type="image/png"))
                        dataset_ids.append(grid.id)
                        records.append(dict(orbital_number=number, spin=preflight.channel,
                            energy_hartree=row.energy, occupation=row.occupation, labels=list(row.labels),
                            grid_id=str(grid.id), grid_revision=grid.revision, reused_scientific_cache=cached,
                            image=filename, view=scene_plan_document(plan)))
                        yield {"stage": f"Rendered MO {number}", "progress": (ordinal + 1) / len(preflight.numbers)}
                    check()
                    document.update(schema_name="chemblender_orbital_images", schema_version=1,
                        project_id=str(preflight.project.id), orbital_set_id=str(preflight.orbitals.id),
                        orbital_set_revision=preflight.orbitals.revision, grid_parameters=preflight.parameters,
                        source=row.source, orbitals=records)
                # Restore Blender before publishing any final image or complete report.
                check()
                with (root / "display.json").open("x", encoding="utf-8", newline="\n") as stream:
                    json.dump(document, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
                    stream.write("\n")
                artifacts.append(describe_report_artifact(root, "display.json", role="display_parameters", media_type="application/json"))
                report = build_analysis_report(preflight.project, title="Orbital image export",
                                               dataset_ids=dataset_ids, artifacts=artifacts)
                if report["status"] != "complete":
                    raise ValueError("Orbital export report contains incomplete scientific data")
                package = root / "package"
                write_analysis_report_bundle(package, report)
                (root / "images").rename(package / "images")
                (root / "display.json").rename(package / "display.json")
                check()
                if os.path.lexists(preflight.target):
                    raise ValueError("The output directory was created by another operation")
                package.rename(preflight.target)
                return preflight.target
        finally:
            try:
                if job is not None:
                    job.close()
            finally:
                session.active_entity_id = active_entity
                if browser is not None:
                    browser.active_entity_id = browser_entity
                _release_export(state)

    state.generator = iterate()
    _EXPORTS[session.id] = state
    next(state.generator)
    return state.generator


def export_orbital_images(context, session, settings, **kwargs):
    """Synchronous background-script entrypoint; all Blender calls stay on the caller."""
    iterator = iter_orbital_images(context, session, settings, **kwargs)
    try:
        while True:
            try:
                next(iterator)
            except StopIteration as completed:
                return completed.value
            time.sleep(.02)
    finally:
        iterator.close()


try:
    import bpy
    from bpy.props import StringProperty
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    class CHEMBLENDER_OT_export_orbitals(bpy.types.Operator):
        bl_idname = "chemblender.export_orbitals"
        bl_label = "Export Orbital Images"
        bl_description = "Render explicit orbitals sequentially with the current camera; Esc cancels between stages"
        action: StringProperty(default="export", options={"HIDDEN", "SKIP_SAVE"})

        def _start(self, context):
            from .session import get_scene_session
            session = get_scene_session(context.scene)
            settings = context.scene.chemblender_wavefunction
            self._session = session
            self._iterator = iter_orbital_images(context, session, settings,
                orbital_numbers=settings.export_orbitals, destination=bpy.path.abspath(settings.export_directory),
                isovalue=settings.export_isovalue, positive_color=settings.export_positive_color,
                negative_color=settings.export_negative_color, opacity=settings.export_opacity)
            self._state = _EXPORTS[session.id]

        def execute(self, context):
            from .session import get_scene_session
            if self.action == "cancel":
                state = _EXPORTS.get(get_scene_session(context.scene).id)
                if state is not None:
                    state.cancelled = True
                return {"FINISHED"}
            try:
                self._start(context)
                while True:
                    try:
                        next(self._iterator)
                    except StopIteration as completed:
                        self.report({"INFO"}, f"Exported orbital images to {completed.value}")
                        return {"FINISHED"}
                    time.sleep(.02)
            except Exception as error:
                self.cancel(context)
                self.report({"WARNING"} if isinstance(error, OrbitalExportCancelled) else {"ERROR"}, str(error))
                return {"CANCELLED"}

        def invoke(self, context, _event):
            if self.action == "cancel" or bpy.app.background:
                return self.execute(context)
            try:
                self._start(context)
                self._state.manager = context.window_manager
                self._state.manager.progress_begin(0, 100)
                self._state.timer = self._state.manager.event_timer_add(.1, window=context.window)
                self._state.manager.modal_handler_add(self)
                return {"RUNNING_MODAL"}
            except Exception as error:
                self.cancel(context)
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}

        def modal(self, context, event):
            if _EXPORTS.get(self._session.id) is not self._state:
                return {"CANCELLED"}
            if event.type == "ESC":
                self._state.cancelled = True
            if event.type != "TIMER":
                return {"RUNNING_MODAL"}
            try:
                status = next(self._iterator)
                context.window_manager.progress_update(int(status["progress"] * 100))
                return {"RUNNING_MODAL"}
            except StopIteration as completed:
                self.report({"INFO"}, f"Exported orbital images to {completed.value}")
                return {"FINISHED"}
            except Exception as error:
                self.cancel(context)
                self.report({"WARNING"} if isinstance(error, OrbitalExportCancelled) else {"ERROR"}, str(error))
                return {"CANCELLED"}

        def cancel(self, _context):
            if hasattr(self, "_iterator"):
                self._iterator.close()
                _release_export(self._state)


def draw_orbital_export(layout, context, session):
    settings = context.scene.chemblender_wavefunction
    box = layout.box()
    box.label(text="Orbital Images · Current Spin and Grid")
    box.label(text="Esc cancels between images; the current render finishes first.")
    state = _EXPORTS.get(session.id)
    if state is not None:
        box.label(text="Sequential export in progress")
        box.operator("chemblender.export_orbitals", text="Cancel Image Export").action = "cancel"
        return
    for name in ("export_orbitals", "export_directory", "export_isovalue",
                 "export_positive_color", "export_negative_color", "export_opacity"):
        box.prop(settings, name)
    if context.scene.camera is None:
        box.label(text="Set the scene camera before exporting", icon="ERROR")
    row = box.row()
    row.enabled = context.scene.camera is not None and session.id not in _JOBS
    row.operator("chemblender.export_orbitals")


def register():
    from .session import register_session_cleanup
    register_session_cleanup(clear_orbital_exports)


def unregister():
    from .session import unregister_session_cleanup
    clear_orbital_exports()
    unregister_session_cleanup(clear_orbital_exports)


__all__ = ("OrbitalExportCancelled", "parse_orbital_numbers", "preflight_orbital_export",
           "iter_orbital_images", "export_orbital_images", "clear_orbital_exports", "draw_orbital_export")
if bpy is not None:
    __all__ += ("CHEMBLENDER_OT_export_orbitals",)
