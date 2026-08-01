"""Exercise legacy migration through the installed Blender Extension operators."""

import hashlib
import importlib
import sys
import tempfile
from pathlib import Path

import bpy


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hash(path):
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*"), key=lambda item: str(item.relative_to(path))):
        if child.is_file():
            digest.update(str(child.relative_to(path)).replace("\\", "/").encode())
            digest.update(child.read_bytes())
    return digest.hexdigest()


def _assert_backup_preservation(backup, legacy_names):
    project_id = backup["cb_legacy_migration_project_id"]
    transaction_id = backup["cb_legacy_migration_transaction_id"]
    for name in legacy_names:
        assert name in bpy.data.objects, name
        obj = bpy.data.objects[name]
        assert tuple(obj.users_collection) == (backup,), (
            name,
            tuple(collection.name for collection in obj.users_collection),
        )
        assert obj.get("cb_legacy_migration_backup") == "v2"
        assert obj.get("cb_legacy_migration_project_id") == project_id
        assert obj.get("cb_legacy_migration_transaction_id") == transaction_id


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
    session_ui = importlib.import_module(f"{module_key}.ui.session")
    publication = importlib.import_module(f"{module_key}.core.storage.publication")

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
    _assert_backup_preservation(backup, legacy_names)
    assert any(
        obj.get("cb_structure_contract") == "structure_view_v1"
        for obj in bpy.data.objects
    )

    session = session_ui.get_scene_session(scene)
    assert session.link_status == "connected"
    assert not session.dirty, session.dirty_reasons
    sidecar = Path(session.sidecar_path)
    manifest_before = (sidecar / "manifest.json").read_bytes()
    tree_before = _tree_hash(sidecar)
    assert not publication.inspect_publication_orphans(sidecar).has_orphans
    assert bpy.ops.wm.save_mainfile() == {"FINISHED"}
    assert session.link_status == "connected"
    assert not session.dirty, session.dirty_reasons
    assert session_ui.get_scene_session_status(scene)[0] == "connected"
    assert (sidecar / "manifest.json").read_bytes() == manifest_before
    assert _tree_hash(sidecar) == tree_before
    assert not publication.inspect_publication_orphans(sidecar).has_orphans
    assert bpy.ops.wm.open_mainfile(filepath=str(destination)) == {"FINISHED"}
    reopened_scene = bpy.data.scenes[scene_name]
    assert session_ui.get_scene_session_status(reopened_scene)[0] == "connected"
    assert migration.legacy_migration_detection(reopened_scene).objects == ()
    reopened_backup = bpy.data.collections["ChemBlender Legacy Backup"]
    assert reopened_backup.hide_viewport and reopened_backup.hide_render
    _assert_backup_preservation(reopened_backup, legacy_names)
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
