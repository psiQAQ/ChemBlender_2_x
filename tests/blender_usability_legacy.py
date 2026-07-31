"""Exercise legacy migration through the installed Blender Extension operators."""

import hashlib
import importlib
import sys
import tempfile
from pathlib import Path

import bpy


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    assert len(arguments) == 3, (
        "expected ZIP path, package SHA-256, and fixture SHA-256"
    )
    package = Path(arguments[0]).resolve()
    expected_package_hash, expected_fixture_hash = arguments[1:]
    source = Path(bpy.data.filepath).resolve()
    assert package.is_file(), package
    assert source.is_file(), source
    assert _sha256(package) == expected_package_hash
    assert _sha256(source) == expected_fixture_hash

    destination = Path(tempfile.mkdtemp(prefix="cb-packaged-legacy-")) / source.name
    assert bpy.ops.wm.save_as_mainfile(filepath=str(destination)) == {"FINISHED"}

    result = bpy.ops.extensions.package_install_files(
        filepath=str(package),
        repo="user_default",
        enable_on_install=True,
        overwrite=True,
    )
    assert result == {"FINISHED"}, result
    module_keys = sorted(
        addon.module
        for addon in bpy.context.preferences.addons
        if addon.module.rsplit(".", 1)[-1] == "chemblender"
    )
    assert module_keys == ["bl_ext.user_default.chemblender"], module_keys
    module_key = module_keys[0]
    migration = importlib.import_module(f"{module_key}.ui.migration")

    scene = bpy.context.scene
    scene_name = scene.name
    detection = migration.legacy_migration_detection(scene)
    assert detection.objects, source.name
    legacy_names = tuple(item.name for item in detection.objects)

    assert bpy.ops.chemblender.preview_legacy_migration("EXEC_DEFAULT") == {"FINISHED"}
    assert tuple(
        item.name for item in migration.legacy_migration_detection(scene).objects
    ) == legacy_names
    assert bpy.ops.chemblender.migrate_legacy_scene(confirmed=True) == {"FINISHED"}
    assert migration.legacy_migration_detection(scene).objects == ()
    backup = bpy.data.collections["ChemBlender Legacy Backup"]
    assert backup.hide_viewport and backup.hide_render
    assert any(
        obj.get("cb_structure_contract") == "structure_view_v1"
        for obj in bpy.data.objects
    )

    assert bpy.ops.wm.save_mainfile() == {"FINISHED"}
    assert bpy.ops.wm.open_mainfile(filepath=str(destination)) == {"FINISHED"}
    reopened_scene = bpy.data.scenes[scene_name]
    assert migration.legacy_migration_detection(reopened_scene).objects == ()
    reopened_backup = bpy.data.collections["ChemBlender Legacy Backup"]
    assert reopened_backup.hide_viewport and reopened_backup.hide_render
    assert any(
        obj.get("cb_structure_contract") == "structure_view_v1"
        for obj in bpy.data.objects
    )
    link = migration.resolve_project_link(
        reopened_scene,
        blend_path=bpy.data.filepath,
    )
    try:
        assert link.status.value == "connected", link.message
        assert link.project is not None
    finally:
        if link.project is not None:
            core = importlib.import_module(f"{module_key}.core")
            core.close_project(link.project)

    print(
        "PASS: packaged legacy migration and reopen "
        f"fixture={source.name} fixture_sha256={expected_fixture_hash} "
        f"package_sha256={expected_package_hash}"
    )


if __name__ == "__main__":
    main()
