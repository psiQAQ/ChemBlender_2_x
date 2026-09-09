"""Panel-driven Cycles image/sequence exports using the shared render transaction."""

import json
import math
import os
from pathlib import Path
from types import SimpleNamespace

from cbq_core.analysis_report import build_analysis_report
from cbq_core.analysis_report import describe_report_artifact
from cbq_core.analysis_report import write_analysis_report_bundle
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import plan_scene_preset
from cbq_core.scene_preset import scene_plan_document
from ..render_scene import RenderCancelled, RenderScope
from .orbital_export import _EXPORTS, _image_staging, _release_export
from .view_cache import scene_plan_from_view


def selected_view_roots(context):
    roots = []
    selected = tuple(context.selected_objects) or ((context.active_object,) if context.active_object else ())
    for obj in selected:
        while obj.parent is not None and obj.get("cb_view_root") is not True:
            obj = obj.parent
        if obj.get("cb_scene_preset_id") and obj not in roots:
            roots.append(obj)
    if not roots:
        raise ValueError("Select one or more scientific Views")
    return tuple(roots)


def _encode_video(images, destination, width, height, fps):
    """Encode already-rendered PNG frames with Blender's native FFmpeg writer."""
    import bpy

    if not bpy.app.build_options.codec_ffmpeg:
        raise ValueError("This Blender build does not provide FFmpeg")
    scene = bpy.data.scenes.new("Scientific Video Encoding")
    try:
        editor = scene.sequence_editor_create()
        strip = editor.strips.new_image("Scientific PNG Frames", str(images[0]), channel=1, frame_start=1)
        for path in images[1:]:
            strip.elements.append(path.name)
        scene.frame_start, scene.frame_end = 1, len(images)
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x, scene.render.resolution_y = width, height
        scene.render.resolution_percentage = 100
        scene.render.fps = fps
        scene.render.fps_base = 1.
        scene.render.use_sequencer = True
        scene.render.use_compositing = False
        scene.render.image_settings.media_type = "VIDEO"
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "HIGH"
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.render.filepath = str(destination)
        result = bpy.ops.render.render(animation=True, scene=scene.name)
        if "FINISHED" not in result or not destination.is_file():
            raise RenderCancelled("Video encoding failed or was cancelled")
        with destination.open("rb") as stream:
            if stream.read(12)[4:8] != b"ftyp":
                raise ValueError("Blender did not produce an MP4 file")
    finally:
        bpy.data.scenes.remove(scene)


def iter_scientific_images(context, session, *, roots, destination,
                          templates=("research", "teaching"), width=2400, height=1800,
                          samples=256, animation=False, fps=24, is_cancelled=None,
                          direction=None, framing_margin=1.40, volume_focus_threshold=0.):
    """Yield progress between stages; publish the package only after complete success."""
    if session.id in _EXPORTS:
        raise ValueError("Wait for the current image export")
    roots = tuple(roots)
    if not roots:
        raise ValueError("Select at least one scientific View")
    if not templates or any(value not in {"research", "teaching"} for value in templates):
        raise ValueError("Select Research and/or Teaching templates")
    if any(type(value) is not int or value < 1 for value in (width, height, samples, fps)):
        raise ValueError("Image dimensions, samples and FPS must be positive integers")
    if animation and (width % 2 or height % 2):
        raise ValueError("H.264 animation requires even image dimensions")
    target = Path(destination).expanduser().absolute()
    if os.path.lexists(target):
        raise ValueError("Choose a new output directory; existing files are never replaced")
    target = target.parent.resolve(strict=True) / target.name
    project = session.project
    inputs = tuple((obj, scene_plan_from_view(obj, project), obj.matrix_world.copy()) for obj in roots)
    frame_ids = {binding.entity_id for _obj, plan, _matrix in inputs
                 for binding in plan.bindings if binding.name == "frames"}

    def time_sources():
        from cbq_core.model import FrameProperty
        return {entity.id: entity.revision for entity in project.datasets.values()
                if isinstance(entity, FrameProperty) and entity.frame_set_id in frame_ids
                and entity.semantic_role == "time"}

    frozen_time_sources = time_sources()
    dataset_ids = tuple(dict.fromkeys(binding.entity_id for _obj, plan, _matrix in inputs
                                     for binding in plan.bindings if binding.entity_kind == "dataset"))
    if not dataset_ids:
        raise ValueError("Select a physical-quantity View for a scientific export report")
    if build_analysis_report(project, title="Scientific visualization export",
                             dataset_ids=dataset_ids)["status"] != "complete":
        raise ValueError("Export requires complete scientific data")
    animated_kinds = {"vibration_mode", "vibration_spectrum_linked", "phonon_mode", "trajectory", "trajectory_force"}
    if animation and any(plan.view_kind not in animated_kinds for _obj, plan, _matrix in inputs):
        raise ValueError("Sequence export requires a vibration, phonon or trajectory View")
    state = SimpleNamespace(session_id=session.id, cancelled=False, generator=None, manager=None, timer=None)

    def check():
        if state.cancelled or is_cancelled is not None and is_cancelled():
            raise RenderCancelled("Scientific image export cancelled")
        if session.project is not project:
            raise ValueError("Project changed during export")
        if time_sources() != frozen_time_sources:
            raise ValueError("Trajectory time sources changed during export")
        for obj, saved, _matrix in inputs:
            if scene_plan_from_view(obj, project) != saved:
                raise ValueError("A selected View changed during export")

    def iterate():
        try:
            yield {"stage": "Ready", "progress": 0.}
            check()
            with _image_staging(target) as staging:
                package = staging / "package"
                package.mkdir()
                (package / "images").mkdir()
                records, artifacts = [], []
                time_dataset_ids = set()
                total = len(inputs) * len(templates)
                for index, (source, saved, matrix) in enumerate(inputs):
                    for ordinal, template in enumerate(templates):
                        check()
                        settings = dict(saved.settings)
                        supplied = {key: settings[key] for key, _default in builtin_scene_presets()[saved.preset_id].default_settings}
                        supplied["template"] = template
                        if template == "research":
                            supplied.update(shaded=saved.view_kind == "signed_isosurface", material_opacity=1.)
                        plan = plan_scene_preset(builtin_scene_presets()[saved.preset_id], project,
                                                {binding.name: binding.entity_id for binding in saved.bindings}, supplied)
                        name = f"{index + 1:03d}-{plan.view_kind}-{template}"
                        record = {"source_view": source.name, "view_instance_id": source.get("cb_view_instance_id"),
                                  "source_matrix_world": [list(row) for row in matrix],
                                  "view": scene_plan_document(plan), "images": []}
                        structure = None
                        if plan.view_kind in {"grid_volume", "signed_isosurface", "property_on_surface", "nci_surface", "topology_graph"}:
                            dataset = project.datasets[plan.bindings[0].entity_id]
                            structure = project.structures.get(getattr(dataset, "structure_id", None))
                        with RenderScope(context, project, structure, template=template,
                                         width=width, height=height, samples=samples,
                                         direction=direction, framing_margin=framing_margin,
                                         volume_focus_threshold=volume_focus_threshold) as renderer:
                            trajectory = plan.view_kind in {"trajectory", "trajectory_force"}
                            frames = (project.datasets[next(binding.entity_id for binding in plan.bindings if binding.name == "frames")]
                                      if trajectory else None)
                            count = (frames.data.shape[0] if trajectory else settings["frames_per_cycle"]) if animation else 1
                            image_paths = []
                            for frame in range(count):
                                check()
                                progress = (index * len(templates) + ordinal + frame / count) / total
                                yield {"stage": f"Cycles {name} · {frame + 1}/{count}", "progress": progress}
                                phase = settings.get("phase", 0.) + math.tau * frame / count if animation and not trajectory else None
                                frame_index = (frame if animation else settings["frame_index"]) if trajectory else None
                                filename = f"images/{name}-{frame + 1:04d}.png"
                                path = package / filename
                                display = renderer.render(plan, path, staging / "cache", matrix_world=matrix,
                                                          phase=phase, frame_index=frame_index,
                                                          is_cancelled=lambda: state.cancelled or is_cancelled is not None and is_cancelled())
                                time_id = display.get("trajectory_frame", {}).get("time_dataset_id")
                                if time_id:
                                    from uuid import UUID
                                    time_dataset_ids.add(UUID(time_id))
                                image_paths.append(path)
                                artifacts.append(describe_report_artifact(package, filename, role="scientific_image", media_type="image/png"))
                                record["images"].append({"path": filename, "phase_radians": phase,
                                                         "trajectory_frame": display.get("trajectory_frame")})
                                record["display"] = display
                            if animation:
                                check()
                                yield {"stage": f"Encode MP4 · {name}", "progress": (index * len(templates) + ordinal + .95) / total}
                                filename = name + ".mp4"
                                _encode_video(image_paths, package / filename, width, height, fps)
                                artifacts.append(describe_report_artifact(package, filename, role="scientific_animation", media_type="video/mp4"))
                                record.update(video=filename, fps=fps)
                        records.append(record)
                check()
                document = {"schema_name": "chemblender_scientific_images", "schema_version": 1,
                            "project_id": str(project.id), "views": records}
                with (package / "display.json").open("x", encoding="utf-8", newline="\n") as stream:
                    json.dump(document, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
                    stream.write("\n")
                artifacts.append(describe_report_artifact(package, "display.json", role="display_parameters", media_type="application/json"))
                report = build_analysis_report(project, title="Scientific visualization export",
                                               dataset_ids=(*dataset_ids, *time_dataset_ids), artifacts=artifacts)
                if report["status"] != "complete":
                    raise ValueError("Export includes incomplete scientific data")
                report_dir = staging / "report"
                write_analysis_report_bundle(report_dir, report)
                for path in report_dir.iterdir():
                    path.rename(package / path.name)
                check()
                if os.path.lexists(target):
                    raise ValueError("Output directory appeared during export")
                package.rename(target)
                return target
        finally:
            _release_export(state)

    state.generator = iterate()
    _EXPORTS[session.id] = state
    next(state.generator)
    return state.generator


def export_scientific_images(context, session, **kwargs):
    iterator = iter_scientific_images(context, session, **kwargs)
    try:
        while True:
            try:
                next(iterator)
            except StopIteration as completed:
                return completed.value
    finally:
        iterator.close()


try:
    import bpy
    from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                           IntProperty, PointerProperty, StringProperty)
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    class CHEMBLENDER_PG_scientific_export(bpy.types.PropertyGroup):
        directory: StringProperty(name="New Output Folder", subtype="DIR_PATH")
        templates: EnumProperty(name="Templates", items=(("both", "Research + Teaching", "Export both styles"),
            ("research", "Research", "Light neutral background"), ("teaching", "Teaching", "Dark neutral background")))
        width: IntProperty(name="Width", default=2400, min=64, max=16384)
        height: IntProperty(name="Height", default=1800, min=64, max=16384)
        samples: IntProperty(name="Cycles Samples", default=256, min=1, max=4096)
        animation: BoolProperty(name="PNG Sequence + MP4", default=False)
        fps: IntProperty(name="FPS", default=24, min=1, max=120)
        custom_direction: BoolProperty(name="Custom Camera Direction", default=False)
        direction: FloatVectorProperty(name="Direction from Center", size=3, default=(1.2, -1.6, 1.1))
        framing_margin: FloatProperty(name="Framing Margin", default=1.40, min=1.01, max=5.)
        volume_focus_threshold: FloatProperty(name="Volume Focus Threshold", default=0., min=0.,
            description="Camera focus uses |field| above this value in the source field unit; 0 frames the full grid. Does not mask volume values")

    from .orbital_export import CHEMBLENDER_OT_export_orbitals

    class CHEMBLENDER_OT_export_scientific(CHEMBLENDER_OT_export_orbitals):
        bl_idname = "chemblender.export_scientific"
        bl_label = "Render Selected Scientific Views"
        bl_description = "Cycles renders and report; Esc cancels between frames, publishing only after complete success"

        def _start(self, context):
            from .session import get_scene_session

            self._session = get_scene_session(context.scene)
            settings = context.scene.chemblender_scientific_export
            templates = ("research", "teaching") if settings.templates == "both" else (settings.templates,)
            self._iterator = iter_scientific_images(context, self._session, roots=selected_view_roots(context),
                destination=bpy.path.abspath(settings.directory), templates=templates, width=settings.width,
                height=settings.height, samples=settings.samples, animation=settings.animation, fps=settings.fps,
                direction=tuple(settings.direction) if settings.custom_direction else None,
                framing_margin=settings.framing_margin, volume_focus_threshold=settings.volume_focus_threshold)
            self._state = _EXPORTS[self._session.id]


def draw_scientific_export(layout, context, session):
    settings = context.scene.chemblender_scientific_export
    box = layout.box()
    box.label(text="Cycles · Scientific Images")
    if session.id in _EXPORTS:
        box.operator("chemblender.export_scientific", text="Cancel Image Export").action = "cancel"
        return
    for key in ("directory", "templates", "width", "height", "samples", "animation"):
        box.prop(settings, key)
    box.prop(settings, "custom_direction")
    if settings.custom_direction:
        box.prop(settings, "direction")
    box.prop(settings, "framing_margin")
    box.prop(settings, "volume_focus_threshold")
    if settings.animation:
        box.prop(settings, "fps")
        box.label(text="Modes: one cycle. Trajectories: all source frames, in order")
    box.label(text="Esc cancels between images; all outputs publish together")
    box.operator("chemblender.export_scientific")


def register():
    bpy.types.Scene.chemblender_scientific_export = PointerProperty(type=CHEMBLENDER_PG_scientific_export)


def unregister():
    if hasattr(bpy.types.Scene, "chemblender_scientific_export"):
        del bpy.types.Scene.chemblender_scientific_export
