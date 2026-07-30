import sys
import tempfile
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import bpy
import numpy


ROOT = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
sys.path.insert(0, str(ROOT))

_LINK_KEYS = (
    "cbq_project_id", "cbq_project_schema_version", "cbq_sidecar_locator",
    "cbq_manifest_sha256",
)


def _property_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return tuple(_property_value(item) for item in value)
    except TypeError:
        return value


def _object_snapshot(objects, scene):
    return {
        obj.name: (
            tuple(sorted(group.name for group in obj.users_collection)),
            obj.hide_viewport,
            tuple((layer.name, obj.hide_get(view_layer=layer)) for layer in scene.view_layers),
            {key: _property_value(obj[key]) for key in sorted(obj.keys())},
        )
        for obj in objects
    }


def _scene_links_snapshot():
    return {
        scene.name: {
            key: (key in scene, scene[key] if key in scene else None)
            for key in _LINK_KEYS
        }
        for scene in bpy.data.scenes
    }


def _tree_hash(path):
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*"), key=lambda item: str(item.relative_to(path))):
        if child.is_file():
            digest.update(str(child.relative_to(path)).replace("\\", "/").encode("utf-8"))
            digest.update(child.read_bytes())
    return digest.hexdigest()


def _attribute_values(view, name, field):
    return tuple(
        tuple(getattr(item, field)) if field == "color" else getattr(item, field)
        for item in view.data.attributes[name].data
    )


def _verify_display(view, settings):
    for name, values, field in (
        ("radius", settings.radii, "value"),
        ("vdw_radius", settings.vdw_radii, "value"),
        ("atom_scale_f", settings.atom_scales, "value"),
        ("bond_scale_f", settings.bond_scales, "value"),
        ("dashed", settings.dashed, "value"),
        ("colour", settings.colors, "color"),
    ):
        if values is not None:
            assert _attribute_values(view, name, field) == tuple(values), name
    materials = tuple(view.data.materials)
    assert len(materials) == len(settings.materials)
    for material, expected in zip(materials, settings.materials):
        assert tuple(material.diffuse_color) == expected.diffuse_color
        assert material.metallic == expected.metallic
        assert material.roughness == expected.roughness
    expected_audit = [
        {"inputs": list(item.inputs), "name": item.name, "node_group_name": item.node_group_name}
        for item in settings.node_modifiers
    ]
    assert json.loads(view["cb_legacy_node_settings"]) == expected_audit


def main():
    import ChemBlender
    from ChemBlender.core import ArrayData, ImportBatch, Structure
    from ChemBlender.core.project_service import relink_project_session_for_scenes
    from ChemBlender.core.sidecar import LazyNpyArray, close_project
    from ChemBlender.core.storage.publication import solidify_session
    from ChemBlender.ui.session import get_scene_session

    path = Path(tempfile.mkdtemp()) / Path(bpy.data.filepath).name
    assert bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {"FINISHED"}
    ChemBlender.register()
    from ChemBlender.ui import migration

    active_scene = bpy.context.scene
    scene = bpy.data.scenes.new("Migration Target")
    scene.collection.children.link(active_scene.collection.children[0])
    assert scene is not bpy.context.scene
    before_objects = tuple(sorted(item.name for item in bpy.data.objects))
    before_keys = tuple(sorted(active_scene.keys()))
    migration._legacy_load_post_handler(None)
    detection = migration.legacy_migration_detection(scene)
    assert detection.objects
    assert tuple(sorted(item.name for item in bpy.data.objects)) == before_objects
    assert tuple(sorted(active_scene.keys())) == before_keys

    forged = bpy.data.objects[detection.objects[0].name]
    forged["cb_legacy_migration_backup"] = "v1"
    migration._legacy_load_post_handler(None)
    assert any(item.name == forged.name for item in migration.legacy_migration_detection(scene).objects), "foreign marker must not suppress detection"
    del forged["cb_legacy_migration_backup"]
    migration._legacy_load_post_handler(None)

    session = get_scene_session(scene)
    base_id = uuid4()
    session.project.commit(ImportBatch(structures=(Structure(
        base_id, "base", (1,),
        ArrayData(numpy.asarray(((0.0, 0.0, 0.0),)), ("atom", "xyz"), "angstrom"),
    ),)))
    preview = migration.preview_legacy_migration(scene)
    assert preview.plan.view_plans
    assert preview.entity_inventory
    assert all("Structure" in item.entity_types and "ProvenanceRecord" in item.entity_types for item in preview.entity_inventory)
    crystal_inventory = [item for item in preview.entity_inventory if item.kind == "crystal"]
    assert all("PeriodicSiteData" in item.entity_types for item in crystal_inventory)
    try:
        migration.migrate_legacy_scene(scene, confirmed=False)
    except ValueError as error:
        assert "confirmation" in str(error)
    else:
        raise AssertionError("migration accepted without explicit confirmation")

    preview.sidecar_path.mkdir()
    (preview.sidecar_path / "unrelated").write_text("do not replace", encoding="utf-8")
    try:
        migration.migrate_legacy_scene(scene, confirmed=True)
    except ValueError as error:
        assert "unrelated" in str(error)
    else:
        raise AssertionError("unrelated sidecar was accepted")
    assert (preview.sidecar_path / "unrelated").read_text(encoding="utf-8") == "do not replace"
    (preview.sidecar_path / "unrelated").unlink()
    preview.sidecar_path.rmdir()

    solidify_session(session, preview.sidecar_path)
    linked = relink_project_session_for_scenes(
        session=session, scenes=tuple(bpy.data.scenes),
        sidecar_path=preview.sidecar_path, blend_path=bpy.data.filepath,
    )
    assert linked.status.value == "connected"
    lazy_before = session.project
    assert isinstance(lazy_before.structures[base_id].coordinates.values, LazyNpyArray)
    assert not lazy_before.structures[base_id].coordinates.values.loaded
    sidecar_before = _tree_hash(preview.sidecar_path)
    links_before = _scene_links_snapshot()
    originals = tuple(bpy.data.objects[name] for name in preview.plan.report.object_names)
    rollback_before = _object_snapshot(originals, scene)
    original_move = migration._move_backup_object
    moved = False

    def fail_after_first_move(*args):
        nonlocal moved
        original_move(*args)
        if not moved:
            moved = True
            raise OSError("injected post-mutation backup failure")

    migration._move_backup_object = fail_after_first_move
    try:
        migration.migrate_legacy_scene(scene, confirmed=True)
    except OSError as error:
        assert "injected post-mutation backup failure" in str(error)
    else:
        raise AssertionError("injected migration failure did not escape")
    finally:
        migration._move_backup_object = original_move
    assert moved
    assert not any(item.name.endswith(" (Migrated)") for item in bpy.data.objects)
    assert _object_snapshot(originals, scene) == rollback_before
    assert _scene_links_snapshot() == links_before
    assert _tree_hash(preview.sidecar_path) == sidecar_before
    assert session.project is not lazy_before
    assert session.project.structures[base_id].coordinates.values[0, 0] == 0.0

    preview = migration.preview_legacy_migration(scene)
    original = _object_snapshot(
        tuple(bpy.data.objects[name] for name in preview.plan.report.object_names), scene,
    )
    result = migration.migrate_legacy_scene(scene, confirmed=True)
    assert result.sidecar_path.is_dir()
    assert result.cleanup_warnings == ()
    assert {item.name for item in bpy.data.objects if item.name.endswith(" (Migrated)")} == {
        f"{name} (Migrated)" for name in preview.plan.report.object_names if name != "cell_edges_partial_uij"
    }
    assert session.link_status == "connected"
    assert base_id in session.project.structures
    assert len(session.project.structures) == len(preview.plan.project.structures)
    assert len(session.project.topologies) == len(preview.plan.project.topologies)
    assert len(session.project.provenance) == len(preview.plan.project.provenance)
    backup = bpy.data.collections["ChemBlender Legacy Backup"]
    assert backup.hide_viewport
    assert backup.name in {item.name for item in scene.collection.children}
    assert backup.name not in {item.name for item in active_scene.collection.children}
    for name, (collections, hidden_viewport, hidden_layers, properties) in original.items():
        obj = bpy.data.objects[name]
        assert tuple(sorted(group.name for group in obj.users_collection)) == (backup.name,)
        assert obj.hide_viewport == hidden_viewport
        assert tuple((layer.name, obj.hide_get(view_layer=layer)) for layer in scene.view_layers) == hidden_layers
        assert obj["cb_legacy_migration_backup"] == "v2"
        assert tuple(obj["cb_legacy_original_collections"]) == collections
        assert obj["cb_legacy_migration_project_id"] == backup["cb_legacy_migration_project_id"]
        assert obj["cb_legacy_migration_transaction_id"] == backup["cb_legacy_migration_transaction_id"]
    for view_plan in preview.plan.view_plans:
        view = bpy.data.objects[f"{view_plan.legacy_object_name} (Migrated)"]
        assert view.get("cb_structure_contract") == "structure_view_v1"
        assert view.users_collection[0].name == scene.collection.name
        _verify_display(view, view_plan.settings)
    assert migration.legacy_migration_detection(scene).objects == ()

    assert bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath) == {"FINISHED"}
    assert bpy.ops.wm.open_mainfile(filepath=bpy.data.filepath) == {"FINISHED"}
    assert migration.legacy_migration_detection(bpy.context.scene).objects == ()
    reopened_link = migration.resolve_project_link(bpy.context.scene, blend_path=bpy.data.filepath)
    try:
        assert reopened_link.status.value == "connected"
    finally:
        if reopened_link.project is not None:
            close_project(reopened_link.project)
    print("PASS: legacy migration transaction and reopen")


if __name__ == "__main__":
    main()
