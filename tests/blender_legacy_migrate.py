import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
sys.path.insert(0, str(ROOT))


def main():
    import ChemBlender

    path = Path(tempfile.mkdtemp()) / Path(bpy.data.filepath).name
    assert bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {"FINISHED"}
    ChemBlender.register()
    from ChemBlender.ui import migration

    scene = bpy.context.scene
    before_objects = tuple(sorted(item.name for item in bpy.data.objects))
    before_keys = tuple(sorted(scene.keys()))
    migration._legacy_load_post_handler(None)
    detection = migration.legacy_migration_detection(scene)
    assert detection.objects
    assert tuple(sorted(item.name for item in bpy.data.objects)) == before_objects
    assert tuple(sorted(scene.keys())) == before_keys

    preview = migration.preview_legacy_migration(scene)
    assert preview.plan.view_plans
    try:
        migration.migrate_legacy_scene(scene, confirmed=False)
    except ValueError as error:
        assert "confirmation" in str(error)
    else:
        raise AssertionError("migration accepted without explicit confirmation")

    dirty_before = bpy.data.is_dirty
    rollback_before = tuple(
        (obj.name, tuple(sorted(group.name for group in obj.users_collection)), obj.hide_get())
        for obj in bpy.data.objects
        if obj.name in preview.plan.report.object_names
    )
    original_backup = migration._backup_legacy
    migration._backup_legacy = lambda _objects: (_ for _ in ()).throw(OSError("injected backup failure"))
    try:
        migration.migrate_legacy_scene(scene, confirmed=True)
    except OSError as error:
        assert "injected backup failure" in str(error)
    else:
        raise AssertionError("injected migration failure did not escape")
    finally:
        migration._backup_legacy = original_backup
    assert not bpy.data.objects.get("unit_partial_uij (Migrated)")
    assert tuple(
        (obj.name, tuple(sorted(group.name for group in obj.users_collection)), obj.hide_get())
        for obj in bpy.data.objects
        if obj.name in preview.plan.report.object_names
    ) == rollback_before
    assert not preview.sidecar_path.exists()
    assert bpy.data.is_dirty == dirty_before

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

    original = tuple(
        (obj.name, tuple(sorted(group.name for group in obj.users_collection)), obj.hide_get())
        for obj in bpy.data.objects
        if obj.name in preview.plan.report.object_names
    )
    result = migration.migrate_legacy_scene(scene, confirmed=True)
    assert result.sidecar_path.is_dir()
    assert {item.name for item in bpy.data.objects if item.name.endswith(" (Migrated)")} == {
        f"{name} (Migrated)" for name in preview.plan.report.object_names if name != "cell_edges_partial_uij"
    }
    backup = bpy.data.collections["ChemBlender Legacy Backup"]
    assert backup.hide_viewport
    for name, collections, hidden in original:
        obj = bpy.data.objects[name]
        assert tuple(sorted(group.name for group in obj.users_collection)) == (backup.name,)
        assert obj.hide_get() == hidden
        assert obj["cb_legacy_migration_backup"] == "v1"
        assert tuple(obj["cb_legacy_original_collections"]) == collections
    assert migration.legacy_migration_detection(scene).objects == ()

    bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
    bpy.ops.wm.open_mainfile(filepath=bpy.data.filepath)
    assert migration.legacy_migration_detection(bpy.context.scene).objects == ()
    print("PASS: legacy migration transaction and reopen")


if __name__ == "__main__":
    main()
