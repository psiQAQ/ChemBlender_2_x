"""Sequential orbital renders with isolated display state and atomic publication."""

import json
import math
import os
import re
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from cbq_core.analysis_report import build_analysis_report
from cbq_core.analysis_report import describe_report_artifact
from cbq_core.analysis_report import write_analysis_report_bundle
from cbq_core.orbital_browser import orbital_rows
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import plan_scene_preset
from cbq_core.scene_preset import scene_plan_document
from cbq_core.storage.atomic_paths import short_sibling_temporary_path
from .wavefunction import _selected_orbitals


_EXPORTS = {}


from ..render_scene import RenderScope as _RenderScope, RenderCancelled as OrbitalExportCancelled


@contextmanager
def _image_staging(destination):
    # TemporaryDirectory uses mode 0700; on Windows 3.13 its ACL survives publication.
    # Ordinary mkdir inherits the user's chosen output folder permissions.
    path = short_sibling_temporary_path(destination, suffix=".images")
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


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
    if session.id in _EXPORTS:
        raise ValueError("Wait for the current orbital export task")
    project = session.project
    orbitals = _selected_orbitals(session, settings)
    if orbitals is None:
        raise ValueError("Select an orbital set before exporting")
    channel = settings.channel or orbitals.channels[0].label
    rows = orbital_rows(project, orbitals, channel)
    if isinstance(orbital_numbers, str):
        numbers = parse_orbital_numbers(orbital_numbers, len(rows))
    else:
        numbers = tuple(orbital_numbers)
        if not numbers or any(type(number) is not int or not 1 <= number <= len(rows)
                              for number in numbers):
            raise ValueError("Orbital numbers must be a non-empty 1-based integer sequence")
        numbers = tuple(dict.fromkeys(numbers))
    for number in numbers:
        if not rows[number - 1].cached_dataset_ids:
            raise ValueError(f"Orbital {number} has no prepared grid in CBQ; prepare it externally before exporting")
    display = _display_settings(isovalue, positive_color, negative_color, opacity)
    target = Path(destination).expanduser().absolute()
    if os.path.lexists(target):
        raise ValueError("Choose a new output directory; existing directories are never replaced")
    parent = target.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("The output parent must be an existing directory")
    target = parent / target.name
    inputs = (project.structures[orbitals.structure_id],
              project.basis_sets[orbitals.basis_set_id], orbitals)
    return SimpleNamespace(project=project, orbitals=orbitals, channel=channel,
                           numbers=numbers, inputs=inputs, display=display, target=target)


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

    StopIteration.value is the published directory. Prepared scientific grids are
    reused; no images or report are published until all succeed.
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
        try:
            # Arm finally before returning the public iterator, without creating resources.
            yield {"stage": "Ready", "progress": 0.}
            check()
            with _image_staging(preflight.target) as root:
                (root / "images").mkdir()
                records, dataset_ids, artifacts = [], [], []
                with _RenderScope(context, preflight.project, preflight.inputs[0]) as renderer:
                    document = renderer.document()
                    for ordinal, number in enumerate(preflight.numbers):
                        check()
                        row = orbital_rows(preflight.project, preflight.orbitals, preflight.channel)[number - 1]
                        if not row.cached_dataset_ids:
                            raise ValueError("A prepared orbital grid was removed during export")
                        grid = preflight.project.datasets[row.cached_dataset_ids[0]]
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
                            grid_id=str(grid.id), grid_revision=grid.revision, reused_scientific_cache=True,
                            grid_origin=grid.origin, grid_step_vectors=grid.step_vectors,
                            grid_shape=grid.grid_shape, grid_coordinate_unit=grid.coordinate_unit,
                            image=filename, view=scene_plan_document(plan)))
                        yield {"stage": f"Rendered MO {number}", "progress": (ordinal + 1) / len(preflight.numbers)}
                    check()
                    document.update(schema_name="chemblender_orbital_images", schema_version=1,
                        project_id=str(preflight.project.id), orbital_set_id=str(preflight.orbitals.id),
                        orbital_set_revision=preflight.orbitals.revision,
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
                        self.report({"INFO"}, f"Exported images to {completed.value}")
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
                self.report({"INFO"}, f"Exported images to {completed.value}")
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
    box.label(text="Orbital Images · Prepared MO Grids")
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
    row.enabled = context.scene.camera is not None
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
