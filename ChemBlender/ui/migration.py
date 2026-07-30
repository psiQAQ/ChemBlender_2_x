"""Explicit, reversible migration of detected legacy Blender objects."""

from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import os
import shutil

import bpy
from bpy.props import BoolProperty

from ..core.project_service import relink_project_session_for_scenes
from ..core.sidecar import close_project, open_project
from ..core.storage.atomic_paths import short_sibling_temporary_path
from ..project_link import ProjectLinkStatus, resolve_project_link
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
_BACKUP_CONTRACT = "v2"
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
    cleanup_warnings: tuple[str, ...] = ()


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


def _apply_view_settings(view, settings, owned_materials):
    mesh = view.data
    for name, values, field in (
        ("radius", settings.radii, "value"),
        ("vdw_radius", settings.vdw_radii, "value"),
        ("atom_scale_f", settings.atom_scales, "value"),
        ("bond_scale_f", settings.bond_scales, "value"),
    ):
        if values is not None:
            for item, value in zip(mesh.attributes[name].data, values):
                setattr(item, field, value)
    if settings.dashed is not None:
        dashed = mesh.attributes.get("dashed")
        if dashed is None:
            dashed = mesh.attributes.new("dashed", "BOOLEAN", "EDGE")
        for item, value in zip(dashed.data, settings.dashed):
            item.value = bool(value)
    if settings.colors is not None:
        for item, value in zip(mesh.attributes["colour"].data, settings.colors):
            item.color = value
    for index, snapshot in enumerate(settings.materials):
        material = bpy.data.materials.new(f"{view.name} Legacy Material {index}")
        material.diffuse_color = snapshot.diffuse_color
        material.metallic = snapshot.metallic
        material.roughness = snapshot.roughness
        mesh.materials.append(material)
        owned_materials.append(material)
    view["cb_legacy_node_settings"] = tuple(
        (item.name, item.node_group_name, item.inputs) for item in settings.node_modifiers
    )


def _new_view(plan, view_plan, collection, owned_materials):
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
            collection=collection, attach_ball_and_stick=False,
        )
    else:
        view = create_structure_view(
            structure, topology,
            StructureViewSettings(
                atom_scale=_mean(view_plan.settings.atom_scales),
                bond_scale=_mean(view_plan.settings.bond_scales),
                attach_ball_and_stick=False,
            ),
            name=name, collection=collection,
        )
    if view.get("cb_structure_contract") != "structure_view_v1":
        raise RuntimeError(f"migration view verification failed: {name}")
    _apply_view_settings(view, view_plan.settings, owned_materials)
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


def _verified_existing_sidecar(session, destination, blend_path):
    if not destination.exists():
        return False
    if (
        session.sidecar_path is None
        or Path(session.sidecar_path).resolve() != destination
        or session.link_status != "connected"
    ):
        raise ValueError("refusing to replace an unrelated existing .cbq sidecar")
    for scene in bpy.data.scenes:
        result = resolve_project_link(scene, blend_path=blend_path)
        try:
            if (
                result.status is not ProjectLinkStatus.CONNECTED
                or result.path != destination
                or result.project.id != session.project.id
                or result.project.schema_version != session.project.schema_version
            ):
                raise ValueError("existing .cbq is stale or not linked to this session")
        finally:
            if result.project is not None:
                close_project(result.project)
    return True


def _cleanup(error, label, callback):
    try:
        callback()
    except BaseException as cleanup:
        error.add_note(f"{label}: {cleanup}")


def _restore_legacy(backup, collection_snapshot):
    for obj, collections, hidden, properties in collection_snapshot:
        for collection in tuple(obj.users_collection):
            collection.objects.unlink(obj)
        for collection in collections:
            collection.objects.link(obj)
        obj.hide_set(hidden)
        for key in tuple(obj.keys()):
            if key not in properties:
                del obj[key]
        for key, value in properties.items():
            obj[key] = value
    if backup is not None and backup.name in bpy.data.collections:
        for parent in bpy.data.collections:
            if backup.name in parent.children:
                parent.children.unlink(backup)
        bpy.data.collections.remove(backup)


def _backup_legacy(objects, collection, project_id, transaction_id):
    existing = bpy.data.collections.get(_BACKUP_COLLECTION)
    if existing is not None:
        raise ValueError("ChemBlender Legacy Backup already exists")
    backup = bpy.data.collections.new(_BACKUP_COLLECTION)
    snapshot = tuple(
        (obj, tuple(obj.users_collection), obj.hide_get(),
         {key: deepcopy(obj[key]) for key in obj.keys()})
        for obj in objects
    )
    try:
        collection.children.link(backup)
        backup.hide_viewport = True
        backup.hide_render = True
        backup["cb_legacy_migration_collection"] = _BACKUP_CONTRACT
        backup["cb_legacy_migration_project_id"] = str(project_id)
        backup["cb_legacy_migration_transaction_id"] = str(transaction_id)
        for obj, collections, _hidden, _properties in snapshot:
            for parent in collections:
                parent.objects.unlink(obj)
            backup.objects.link(obj)
            obj["cb_legacy_migration_backup"] = _BACKUP_CONTRACT
            obj["cb_legacy_migration_project_id"] = str(project_id)
            obj["cb_legacy_migration_transaction_id"] = str(transaction_id)
            obj["cb_legacy_original_collections"] = tuple(parent.name for parent in collections)
        return backup, snapshot
    except BaseException as error:
        try:
            _restore_legacy(backup, snapshot)
        except BaseException as cleanup:
            error.add_note(f"legacy backup rollback failed: {cleanup}")
        raise


def migrate_legacy_scene(scene, *, confirmed):
    if confirmed is not True:
        raise ValueError("explicit migration confirmation is required")
    preview = preview_legacy_migration(scene)
    if not preview.plan.view_plans:
        raise ValueError("no legacy structure is available for migration")
    session = get_scene_session(scene)
    destination = preview.sidecar_path
    has_existing_sidecar = _verified_existing_sidecar(session, destination, bpy.data.filepath)
    session_snapshot = (
        session.project, session.sidecar_path, session.link_status,
        session.active_entity_id, session.active_view_object_name,
        session.dirty_reasons,
    )
    links_snapshot = _scene_links_snapshot()
    views, materials, backup, legacy_snapshot = [], [], None, ()
    staging = short_sibling_temporary_path(destination, suffix=".cbq")
    previous_sidecar = None
    swapped = False
    committed = False
    transaction_id = uuid4()
    try:
        for view_plan in preview.plan.view_plans:
            views.append(_new_view(preview.plan, view_plan, scene.collection, materials))
        session.sidecar_path = staging
        committed_result = commit_legacy_migration(session, preview.plan)
        committed = True
        # The verified candidate owns lazy sidecar arrays.  Windows cannot
        # rename its directory while those mappings remain open.
        close_project(session.project)
        if has_existing_sidecar:
            previous_sidecar = short_sibling_temporary_path(destination, suffix=".cbq")
            os.replace(destination, previous_sidecar)
        os.replace(committed_result.sidecar_path, destination)
        swapped = True
        linked = relink_project_session_for_scenes(
            session=session, scenes=tuple(bpy.data.scenes),
            sidecar_path=destination, blend_path=bpy.data.filepath,
        )
        if linked.status.value != "connected":
            raise RuntimeError(linked.message)
        backup, legacy_snapshot = _backup_legacy(
            tuple(bpy.data.objects[name] for name in preview.plan.report.object_names),
            scene.collection, session.project.id, transaction_id,
        )
        session.mark_dirty("legacy_migration")
        _legacy_load_post_handler(None)
        warnings = list(committed_result.cleanup_warnings)
        if previous_sidecar is not None and previous_sidecar.exists():
            try:
                shutil.rmtree(previous_sidecar)
            except OSError as cleanup:
                warnings.append(f"previous sidecar cleanup failed: {cleanup}")
        return LegacyMigrationResult(
            destination, tuple(view.name for view in views), backup.name,
            tuple(warnings),
        )
    except BaseException as error:
        if backup is not None:
            _cleanup(error, "legacy backup rollback failed", lambda: _restore_legacy(backup, legacy_snapshot))
        for view in reversed(views):
            if view.name in bpy.data.objects:
                _cleanup(error, "migration view rollback failed", lambda view=view: remove_structure_view(view))
        for material in materials:
            if material.name in bpy.data.materials and material.users == 0:
                _cleanup(error, "migration material rollback failed", lambda material=material: bpy.data.materials.remove(material))
        _cleanup(error, "scene-link rollback failed", lambda: _restore_scene_links(links_snapshot))
        if committed and session.project is not session_snapshot[0]:
            _cleanup(error, "candidate project cleanup failed", lambda: close_project(session.project))
        if swapped and destination.exists():
            _cleanup(error, "candidate sidecar rollback failed", lambda: os.replace(destination, staging))
        if previous_sidecar is not None and previous_sidecar.exists():
            _cleanup(error, "previous sidecar restore failed", lambda: os.replace(previous_sidecar, destination))
        if has_existing_sidecar:
            restored = open_project(destination, expected_project_id=session_snapshot[0].id,
                                    expected_schema_version=session_snapshot[0].schema_version)
            session_snapshot = (restored, destination, "connected", *session_snapshot[3:])
        _restore_session(session, session_snapshot)
        _cleanup(error, "legacy detection refresh failed", lambda: _legacy_load_post_handler(None))
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
        layout.label(text=f"Destination: {preview.sidecar_path}")
        layout.label(text=f"Legacy entities: {len(preview.plan.report.object_names)}")
        for view_plan in preview.plan.view_plans:
            settings = view_plan.settings
            layout.label(text=f"{view_plan.legacy_object_name} -> {view_plan.legacy_object_name} (Migrated)")
            recovered = [
                name for name, value in (
                    ("radii", settings.radii), ("vdw", settings.vdw_radii),
                    ("atom scale", settings.atom_scales), ("colour", settings.colors),
                    ("bond scale", settings.bond_scales), ("dashed", settings.dashed),
                    ("materials", settings.materials), ("node settings", settings.node_modifiers),
                ) if value
            ]
            layout.label(text=f"  recovered: {', '.join(recovered) or 'structure only'}")
            unsupported = [
                item.message for item in preview.plan.report.diagnostics
                if item.object_name == view_plan.legacy_object_name
            ]
            if unsupported:
                layout.label(text=f"  unsupported: {'; '.join(unsupported)}", icon="ERROR")
        for item in preview.plan.report.diagnostics:
            if item.object_name is None:
                layout.label(text=f"scene unsupported: {item.message}", icon="ERROR")

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
