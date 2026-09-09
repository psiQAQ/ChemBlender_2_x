"""CBQ package review, transactional import, and independent package export."""

from dataclasses import asdict, fields, replace
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from cbq_core.model import QCProject
from cbq_core.package_import import import_package, preview_package
from cbq_core.project_service import (
    ProjectServiceResult, ProjectServiceStatus, sync_project_session_links_for_scenes,
)
from cbq_core.sidecar import close_project, open_project, save_project


_SCENE_PROPERTY_NAME = "chemblender_cbq"
_OWNED_SCENE_PROPERTY = None


def package_path(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Choose a .cbq package directory")
    path = Path(value).expanduser().resolve(strict=True)
    if path.name == "manifest.json":
        path = path.parent
    if path.suffix.lower() != ".cbq" or not path.is_dir():
        raise ValueError("Choose a .cbq directory or its manifest.json")
    return path


def export_package(session, destination):
    """Publish a verified independent package, preserving the active sidecar."""
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("Choose a new .cbq output directory")
    target = Path(destination).expanduser().absolute()
    if target.suffix.lower() != ".cbq":
        raise ValueError("Output directory must end in .cbq")
    target = target.parent.resolve(strict=True) / target.name
    if os.path.lexists(target):
        raise ValueError("Choose a new output directory; existing packages are never replaced")
    if session.sidecar_path is not None and target.is_relative_to(session.sidecar_path.resolve()):
        raise ValueError("Export outside the active CBQ package")
    with TemporaryDirectory(prefix="cbq-export-", dir=target.parent) as temporary:
        staged = Path(temporary) / "project.cbq"
        save_project(staged, session.project)
        verified = open_project(staged, verify_arrays=True)
        close_project(verified)
        if os.path.lexists(target):
            raise ValueError("The output directory was created by another operation")
        staged.rename(target)
    return target


def _entity_ids(project):
    return {identity for item in fields(QCProject)
            if isinstance(registry := getattr(project, item.name), dict)
            for identity in registry}


def import_reviewed_package(session, document, *, allow_duplicate_sources=False,
                            scenes=(), blend_path=""):
    """Advance only validated scene links after the new generation is published."""
    previous_hash = None
    if blend_path and session.sidecar_path is not None:
        previous = sync_project_session_links_for_scenes(
            session=session, scenes=scenes, blend_path=blend_path)
        if previous.status is not ProjectServiceStatus.CONNECTED:
            raise ValueError(previous.message or "Repair the current CBQ project link before importing")
        previous_hash = previous.manifest_sha256
    result = import_package(session, document["path"],
        allow_duplicate_sources=allow_duplicate_sources,
        expected_manifest_sha256=document["manifest_sha256"])
    link = None
    if blend_path:
        # Data is committed at this point. A scene-link failure is recoverable and
        # must not be reported as an uncommitted/cancelled scientific import.
        try:
            link = sync_project_session_links_for_scenes(
                session=session, scenes=scenes, blend_path=blend_path,
                previous_manifest_sha256=previous_hash)
        except Exception as error:
            session.link_status = "invalid"
            session.mark_dirty("project_link")
            link = ProjectServiceResult(ProjectServiceStatus.INVALID, str(error))
        if link.status is not ProjectServiceStatus.CONNECTED:
            result = replace(result, cleanup_warnings=(*result.cleanup_warnings,
                "CBQ imported, but its scene link needs repair: " + link.message))
    return result, link


def _preview_document(settings):
    try:
        result = json.loads(settings.preview_json)
        if not isinstance(result, dict) or result.get("path") != str(package_path(settings.input_path)):
            return None
        digest = result.get("manifest_sha256")
        counts = result.get("counts")
        if (not isinstance(digest, str) or len(digest) != 64
                or any(value not in "0123456789abcdef" for value in digest)
                or not isinstance(counts, dict) or not {"new", "reused"} <= counts.keys()
                or any(type(value) is not int or value < 0 for value in counts.values())):
            return None
        for name in ("conflicts", "source_duplicates", "readiness"):
            values = result.get(name)
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                return None
        return result
    except (OSError, TypeError, ValueError):
        pass
    return None


try:
    import bpy
    from bpy.props import BoolProperty, PointerProperty, StringProperty
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    def _absolute(value):
        return bpy.path.abspath(value) if value else value

    def _review(context, filepath=""):
        from .session import get_scene_session
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        path = package_path(_absolute(filepath or settings.input_path))
        settings.input_path = str(path)
        settings.preview_json = ""
        settings.allow_duplicate_sources = False
        result = preview_package(get_scene_session(context.scene), path)
        settings.preview_json = json.dumps({"path": str(path), **asdict(result)}, ensure_ascii=False)
        return result

    def _draw_review(layout, settings):
        document = _preview_document(settings)
        if document is None:
            layout.label(text="Preview the selected CBQ before importing", icon="INFO")
            return
        counts = document["counts"]
        layout.label(text=f"New entities: {counts['new']} · Reused: {counts['reused']}")
        for name, value in counts.items():
            if value and name not in {"new", "reused"}:
                layout.label(text=f"{name.replace('_', ' ').title()}: {value}")
        for field, icon in (("conflicts", "ERROR"), ("source_duplicates", "ERROR"), ("readiness", "INFO")):
            values = document[field]
            for value in values[:12]:
                layout.label(text=value, icon=icon)
            if len(values) > 12:
                layout.label(text=f"{len(values) - 12} more {field.replace('_', ' ')}; full details in Preview JSON")
        if document["source_duplicates"]:
            layout.prop(settings, "allow_duplicate_sources")
        layout.operator("chemblender.copy_cbq_preview", text="Copy Full Preview Report", icon="COPYDOWN")

    class CHEMBLENDER_PG_cbq(bpy.types.PropertyGroup):
        input_path: StringProperty(name="CBQ Package", subtype="DIR_PATH")
        output_path: StringProperty(name="New CBQ Directory", subtype="DIR_PATH")
        legacy_report_path: StringProperty(name="Legacy Migration Report", subtype="FILE_PATH")
        preview_json: StringProperty(name="Preview JSON", options={"HIDDEN", "SKIP_SAVE"})
        allow_duplicate_sources: BoolProperty(name="Import Sources with Duplicate Content", default=False,
            description="Explicitly retain sources with matching bytes but different identities")
        last_result: StringProperty(name="Last Operation", options={"SKIP_SAVE"})

    class CHEMBLENDER_OT_preview_cbq(bpy.types.Operator):
        bl_idname = "chemblender.preview_cbq"
        bl_label = "Preview CBQ"

        def execute(self, context):
            try:
                _review(context)
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            return {"FINISHED"}

    class CHEMBLENDER_OT_copy_cbq_preview(bpy.types.Operator):
        bl_idname = "chemblender.copy_cbq_preview"
        bl_label = "Copy CBQ Preview"

        def execute(self, context):
            settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
            if _preview_document(settings) is None:
                self.report({"ERROR"}, "Preview the selected CBQ first")
                return {"CANCELLED"}
            context.window_manager.clipboard = settings.preview_json
            return {"FINISHED"}

    class CHEMBLENDER_OT_import_cbq(bpy.types.Operator):
        bl_idname = "chemblender.import_cbq"
        bl_label = "Import CBQ"
        bl_description = "Add a verified CBQ package to the current project"
        filepath: StringProperty(subtype="FILE_PATH", options={"HIDDEN", "SKIP_SAVE"})

        def invoke(self, context, _event):
            try:
                _review(context, self.filepath)
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            return context.window_manager.invoke_props_dialog(self, width=620)

        def draw(self, context):
            _draw_review(self.layout, getattr(context.scene, _SCENE_PROPERTY_NAME))

        def execute(self, context):
            from .session import get_scene_session, _notify_session_mutation, _record_result
            from .orbital_export import _EXPORTS
            from .grid import _ACTIVE_VOLUME_OPERATORS
            settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
            session = get_scene_session(context.scene)
            committed = False
            try:
                if session.id in _EXPORTS or _ACTIVE_VOLUME_OPERATORS:
                    raise ValueError("Finish or cancel the current display export/cache task before importing")
                document = _preview_document(settings)
                if document is None:
                    raise ValueError("Preview the selected CBQ before importing")
                if self.filepath and package_path(_absolute(self.filepath)) != package_path(settings.input_path):
                    raise ValueError("Import path differs from the reviewed CBQ")
                old_ids = _entity_ids(session.project)
                result, link = import_reviewed_package(session, document,
                    allow_duplicate_sources=settings.allow_duplicate_sources,
                    scenes=tuple(bpy.data.scenes), blend_path=bpy.data.filepath)
                committed = True
                # Invalidate the consumed review before any fallible UI refresh.
                settings.preview_json = ""
                settings.allow_duplicate_sources = False
                if link is not None:
                    _record_result(link)
                primary = next((identity for name in ("structures", "datasets", "orbital_sets")
                    for identity in getattr(session.project, name) if identity not in old_ids), None)
                if primary is not None:
                    session.active_entity_id = primary
                    context.scene.chemblender_project_browser.active_entity_id = str(primary)
                settings.last_result = f"Imported {result.counts['new']} entities; reused {result.counts['reused']}"
                _notify_session_mutation(session)
                for warning in result.cleanup_warnings:
                    self.report({"WARNING"}, warning)
                self.report({"INFO"}, settings.last_result)
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                if committed:
                    self.report({"WARNING"}, "CBQ imported, but its interface needs refresh: " + str(error))
                    return {"FINISHED"}
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            return {"FINISHED"}

    class CHEMBLENDER_OT_export_cbq(bpy.types.Operator):
        bl_idname = "chemblender.export_cbq"
        bl_label = "Export CBQ"
        bl_description = "Export the entire scientific project to a new independent CBQ directory"

        def execute(self, context):
            from .session import get_scene_session
            settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
            try:
                result = export_package(get_scene_session(context.scene), _absolute(settings.output_path))
                settings.last_result = f"Exported {result}"
                self.report({"INFO"}, settings.last_result)
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            return {"FINISHED"}

    class CHEMBLENDER_OT_restore_legacy_views(bpy.types.Operator):
        bl_idname = "chemblender.restore_legacy_views"
        bl_label = "Restore Legacy Views"
        bl_description = "Rebuild Views from a verified external legacy migration report"

        def execute(self, context):
            from ..legacy_restore import restore_legacy_views
            from .session import get_scene_session, _notify_session_mutation
            settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
            committed = False
            try:
                session = get_scene_session(context.scene)
                views = restore_legacy_views(session, _absolute(settings.legacy_report_path),
                                             context.collection)
                committed = True
                for obj in context.selected_objects:
                    obj.select_set(False)
                views[-1].select_set(True)
                context.view_layer.objects.active = views[-1]
                context.scene.chemblender_project_browser.active_entity_id = str(session.active_entity_id)
                _notify_session_mutation(session)
                settings.last_result = f"Restored {len(views)} legacy View(s)"
                self.report({"INFO"}, settings.last_result)
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                if committed:
                    self.report({"WARNING"}, "Legacy Views restored, but selection needs refresh: " + str(error))
                    return {"FINISHED"}
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            return {"FINISHED"}

    def draw_cbq_import(layout, context):
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        box = layout.box()
        box.label(text="CBQ Scientific Project", icon="PACKAGE")
        box.label(text="Raw calculation files → Prepare → CBQ → Viewer")
        box.prop(settings, "input_path")
        row = box.row(align=True)
        row.operator(CHEMBLENDER_OT_preview_cbq.bl_idname, icon="VIEWZOOM")
        row.operator_context = "INVOKE_DEFAULT"
        row.operator(CHEMBLENDER_OT_import_cbq.bl_idname, icon="IMPORT")
        _draw_review(box, settings)
        box.prop(settings, "output_path")
        box.operator(CHEMBLENDER_OT_export_cbq.bl_idname, icon="EXPORT")
        box.prop(settings, "legacy_report_path")
        box.operator(CHEMBLENDER_OT_restore_legacy_views.bl_idname, icon="FILE_REFRESH")
        if settings.last_result:
            box.label(text=settings.last_result)

    def register():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        current = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if _OWNED_SCENE_PROPERTY is not None:
            if not _same_scene_property(current, _OWNED_SCENE_PROPERTY):
                raise RuntimeError("CBQ Scene property is no longer owned")
        elif current is not None:
            raise RuntimeError("CBQ Scene property is already owned")
        else:
            setattr(bpy.types.Scene, _SCENE_PROPERTY_NAME, PointerProperty(type=CHEMBLENDER_PG_cbq))
            try:
                identity = _scene_property_identity(_SCENE_PROPERTY_NAME)
                if identity is None:
                    raise RuntimeError("CBQ Scene property registration failed")
            except BaseException as failure:
                # This synchronous registration created the previously absent property.
                try:
                    delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
                except BaseException as cleanup_error:
                    failure.add_note(f"CBQ property rollback failed: {cleanup_error}")
                raise
            _OWNED_SCENE_PROPERTY = identity

    def unregister():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        if _OWNED_SCENE_PROPERTY is not None and _same_scene_property(
            _scene_property_identity(_SCENE_PROPERTY_NAME), _OWNED_SCENE_PROPERTY
        ):
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
        _OWNED_SCENE_PROPERTY = None
