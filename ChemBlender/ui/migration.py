"""Explicit, reversible migration of detected legacy Blender objects."""

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import os

import bpy
from bpy.props import BoolProperty

from ..core.project_service import relink_project_session_for_scenes
from ..core.sidecar import close_project
from ..legacy import (
    commit_legacy_migration,
    detect_legacy_scene,
    extract_legacy_objects,
    plan_legacy_migration,
)
from ..views import (
    PeriodicViewSettings,
    StructureViewSettings,
    create_periodic_structure_view,
    create_structure_view,
    remove_structure_view,
)
from .session import get_scene_session


_BACKUP_COLLECTION = "ChemBlender Legacy Backup"
_BACKUP_CONTRACT = "v1"
_FATAL_EXCEPTIONS = (KeyboardInterrupt, SystemExit, GeneratorExit, MemoryError)
_LINK_KEYS = (
    "cbq_project_id",
    "cbq_project_schema_version",
    "cbq_sidecar_locator",
    "cbq_manifest_sha256",
)
_DETECTIONS = {}


@dataclass(frozen=True, slots=True)
class LegacyMigrationPreview:
    detection: object
    plan: object
    sidecar_path: Path


@dataclass(frozen=True, slots=True)
class LegacyMigrationResult:
    sidecar_path: Path
    view_names: tuple[str, ...]
    backup_collection: str


def _scene_key(scene):
    return scene.as_pointer()


def _legacy_load_post_handler(_dummy):
    """Cache detection only; loading a file must not change its contents."""
    detection = detect_legacy_scene()
    for scene in bpy.data.scenes:
        _DETECTIONS[_scene_key(scene)] = detection


def legacy_migration_detection(scene):
    detection = _DETECTIONS.get(_scene_key(scene))
    return detect_legacy_scene() if detection is None else detection


def _blend_sidecar_path():
    if not bpy.data.filepath:
        raise ValueError("save the Blender file before migration")
    path = Path(bpy.data.filepath).resolve()
    if path.suffix.lower() != ".blend" or not path.is_file():
        raise ValueError("legacy migration requires a saved .blend file")
    return path.with_suffix(".cbq")


def preview_legacy_migration(scene):
    detection = legacy_migration_detection(scene)
    report = extract_legacy_objects(detection)
    plan = plan_legacy_migration(report, get_scene_session(scene).project)
    return LegacyMigrationPreview(detection, plan, _blend_sidecar_path())


def _mean(values):
    return 1.0 if values is None else sum(values) / len(values)


def _new_view(plan, view_plan):
    structure = plan.project.structures[view_plan.structure_id]
    topology = next(
        (item for item in plan.project.topologies.values() if item.structure_id == structure.id),
        None,
    )
    name = f"{view_plan.legacy_object_name} (Migrated)"
    if bpy.data.objects.get(name) is not None:
        raise ValueError(f"migration view name already exists: {name}")
    if view_plan.kind == "crystal":
        view = create_periodic_structure_view(
            structure, topology, PeriodicViewSettings(), name=name,
            collection=bpy.context.scene.collection, attach_ball_and_stick=False,
        )
    else:
        view = create_structure_view(
            structure, topology,
            StructureViewSettings(
                atom_scale=_mean(view_plan.settings.atom_scales),
                bond_scale=_mean(view_plan.settings.bond_scales),
                attach_ball_and_stick=False,
            ),
            name=name, collection=bpy.context.scene.collection,
        )
    if view.get("cb_structure_contract") != "structure_view_v1":
        raise RuntimeError(f"migration view verification failed: {name}")
    return view


def _scene_links_snapshot():
    return tuple(
        (scene, {key: scene[key] if key in scene else None for key in _LINK_KEYS},
         {key: key in scene for key in _LINK_KEYS})
        for scene in bpy.data.scenes
    )


def _restore_scene_links(snapshot):
    for scene, values, present in snapshot:
        for key in _LINK_KEYS:
            if present[key]:
                scene[key] = values[key]
            elif key in scene:
                del scene[key]


def _restore_session(session, snapshot):
    session.project, session.sidecar_path, session.link_status = snapshot[:3]
    session.active_entity_id, session.active_view_object_name = snapshot[3:5]
    session.mark_clean()
    for reason in snapshot[5]:
        session.mark_dirty(reason)


def _sidecar_backup(destination, session):
    if not destination.exists():
        return None
    if session.sidecar_path is None or Path(session.sidecar_path).resolve() != destination:
        raise ValueError("refusing to replace an unrelated existing .cbq sidecar")
    backup = destination.parent / f".{destination.name}.{uuid4()}.migration-backup"
    os.replace(destination, backup)
    return backup


def _restore_legacy(objects, backup, collection_snapshot):
    for obj, collections, hidden in collection_snapshot:
        for collection in tuple(obj.users_collection):
            collection.objects.unlink(obj)
        for collection in collections:
            collection.objects.link(obj)
        obj.hide_set(hidden)
        for key in ("cb_legacy_migration_backup", "cb_legacy_original_collections"):
            if key in obj:
                del obj[key]
    if backup is not None and backup.name in bpy.data.collections:
        for parent in bpy.data.collections:
            if backup.name in parent.children:
                parent.children.unlink(backup)
        if backup.name in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.unlink(backup)
        bpy.data.collections.remove(backup)


def _backup_legacy(objects):
    existing = bpy.data.collections.get(_BACKUP_COLLECTION)
    if existing is not None:
        raise ValueError("ChemBlender Legacy Backup already exists")
    backup = bpy.data.collections.new(_BACKUP_COLLECTION)
    bpy.context.scene.collection.children.link(backup)
    backup.hide_viewport = True
    backup.hide_render = True
    snapshot = []
    for obj in objects:
        collections = tuple(obj.users_collection)
        hidden = obj.hide_get()
        snapshot.append((obj, collections, hidden))
        for collection in collections:
            collection.objects.unlink(obj)
        backup.objects.link(obj)
        obj["cb_legacy_migration_backup"] = _BACKUP_CONTRACT
        obj["cb_legacy_original_collections"] = tuple(collection.name for collection in collections)
    return backup, tuple(snapshot)


def migrate_legacy_scene(scene, *, confirmed):
    if confirmed is not True:
        raise ValueError("explicit migration confirmation is required")
    preview = preview_legacy_migration(scene)
    if not preview.plan.view_plans:
        raise ValueError("no legacy structure is available for migration")
    session = get_scene_session(scene)
    destination = preview.sidecar_path
    session_snapshot = (
        session.project, session.sidecar_path, session.link_status,
        session.active_entity_id, session.active_view_object_name,
        session.dirty_reasons,
    )
    links_snapshot = _scene_links_snapshot()
    views, backup, legacy_snapshot, sidecar_backup, committed = [], None, (), None, False
    try:
        for view_plan in preview.plan.view_plans:
            views.append(_new_view(preview.plan, view_plan))
        sidecar_backup = _sidecar_backup(destination, session)
        session.sidecar_path = destination
        committed_result = commit_legacy_migration(session, preview.plan)
        committed = True
        linked = relink_project_session_for_scenes(
            session=session, scenes=tuple(bpy.data.scenes),
            sidecar_path=committed_result.sidecar_path, blend_path=bpy.data.filepath,
        )
        if linked.status.value != "connected":
            raise RuntimeError(linked.message)
        backup, legacy_snapshot = _backup_legacy(
            tuple(bpy.data.objects[name] for name in preview.plan.report.object_names),
        )
        session.mark_dirty("legacy_migration")
        _legacy_load_post_handler(None)
        if sidecar_backup is not None and sidecar_backup.exists():
            import shutil
            shutil.rmtree(sidecar_backup)
        return LegacyMigrationResult(
            committed_result.sidecar_path, tuple(view.name for view in views), backup.name,
        )
    except BaseException as error:
        if backup is not None:
            _restore_legacy((), backup, legacy_snapshot)
        for view in reversed(views):
            if view.name in bpy.data.objects:
                remove_structure_view(view)
        _restore_scene_links(links_snapshot)
        if committed and session.project is not session_snapshot[0]:
            close_project(session.project)
        if committed and destination.exists():
            import shutil
            shutil.rmtree(destination)
        if sidecar_backup is not None and sidecar_backup.exists():
            os.replace(sidecar_backup, destination)
        _restore_session(session, session_snapshot)
        _legacy_load_post_handler(None)
        if isinstance(error, _FATAL_EXCEPTIONS):
            raise
        raise


class CHEMBLENDER_OT_preview_legacy_migration(bpy.types.Operator):
    bl_idname = "chemblender.preview_legacy_migration"
    bl_label = "Preview Legacy Migration"

    _preview = None

    def invoke(self, context, _event):
        try:
            self._preview = preview_legacy_migration(context.scene)
        except _FATAL_EXCEPTIONS:
            raise
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return context.window_manager.invoke_popup(self, width=520)

    def draw(self, _context):
        preview = self._preview
        layout = self.layout
        layout.label(text=f"Sidecar: {preview.sidecar_path}")
        for view_plan in preview.plan.view_plans:
            settings = view_plan.settings
            layout.label(text=f"{view_plan.legacy_object_name} -> {view_plan.legacy_object_name} (Migrated)")
            layout.label(text=f"  recovered: radii={settings.radii is not None}, display={settings.atom_scales is not None}")
        for item in preview.plan.report.diagnostics:
            layout.label(text=f"{item.object_name or 'scene'}: {item.message}", icon="ERROR")

    def execute(self, context):
        try:
            self._preview = preview_legacy_migration(context.scene)
        except _FATAL_EXCEPTIONS:
            raise
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class CHEMBLENDER_OT_migrate_legacy_scene(bpy.types.Operator):
    bl_idname = "chemblender.migrate_legacy_scene"
    bl_label = "Migrate to Project"
    confirmed: BoolProperty(name="I understand the legacy objects move to backup", default=False)

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            migrate_legacy_scene(context.scene, confirmed=self.confirmed)
        except _FATAL_EXCEPTIONS:
            raise
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class CHEMBLENDER_PT_legacy_migration(bpy.types.Panel):
    bl_idname = "CHEMBLENDER_PT_LEGACY_MIGRATION"
    bl_label = "Legacy Migration"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ChemBlender"

    def draw(self, context):
        layout = self.layout
        detection = legacy_migration_detection(context.scene)
        layout.label(text=f"{len(detection.objects)} legacy object(s)")
        layout.operator("chemblender.preview_legacy_migration")
        layout.operator("chemblender.migrate_legacy_scene")


def register():
    bpy.app.handlers.persistent(_legacy_load_post_handler)
    while _legacy_load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_legacy_load_post_handler)
    bpy.app.handlers.load_post.append(_legacy_load_post_handler)


def unregister():
    while _legacy_load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_legacy_load_post_handler)
    _DETECTIONS.clear()
