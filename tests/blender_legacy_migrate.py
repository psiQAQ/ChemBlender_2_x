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


def _inventory():
    return (
        tuple(sorted(item.name for item in bpy.data.objects)),
        tuple(sorted(item.name for item in bpy.data.meshes)),
        tuple(sorted(item.name for item in bpy.data.materials)),
    )


def _sibling_inventory(destination):
    return tuple(sorted(
        item.name for item in destination.parent.iterdir()
        if item.name.startswith(".") and item.suffix == ".cbq"
    ))


def _entity_id_sets(project):
    return (
        frozenset(project.structures),
        frozenset(project.topologies),
        frozenset(project.provenance),
    )


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
    from ChemBlender.core import ArrayData, ImportBatch, ProvenanceRecord, Structure
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
    target_scene_name = scene.name
    for collection in active_scene.collection.children:
        scene.collection.children.link(collection)
    assert scene is not bpy.context.scene
    before_objects = tuple(sorted(item.name for item in bpy.data.objects))
    before_keys = tuple(sorted(active_scene.keys()))
    migration._legacy_load_post_handler(None)
    detection = migration.legacy_migration_detection(scene)
    assert detection.objects
    assert tuple(sorted(item.name for item in bpy.data.objects)) == before_objects
    assert tuple(sorted(active_scene.keys())) == before_keys

    forged = bpy.data.objects[detection.objects[0].name]
    foreign_project, foreign_transaction = str(uuid4()), str(uuid4())
    forged["cb_legacy_migration_backup"] = "v2"
    forged["cb_legacy_migration_project_id"] = foreign_project
    forged["cb_legacy_migration_transaction_id"] = foreign_transaction
    migration._legacy_load_post_handler(None)
    assert any(item.name == forged.name for item in migration.legacy_migration_detection(scene).objects), "foreign marker must not suppress detection"
    del forged["cb_legacy_migration_backup"]
    del forged["cb_legacy_migration_project_id"]
    del forged["cb_legacy_migration_transaction_id"]
    foreign_backup = bpy.data.collections.new("ChemBlender Legacy Backup")
    scene.collection.children.link(foreign_backup)
    original_collections = tuple(forged.users_collection)
    for collection in original_collections:
        collection.objects.unlink(forged)
    foreign_backup.objects.link(forged)
    migration._legacy_load_post_handler(None)
    assert any(item.name == forged.name for item in migration.legacy_migration_detection(scene).objects), "foreign backup collection must not suppress detection"
    foreign_backup.objects.unlink(forged)
    for collection in original_collections:
        collection.objects.link(forged)
    scene.collection.children.unlink(foreign_backup)
    bpy.data.collections.remove(foreign_backup)
    migration._legacy_load_post_handler(None)

    session = get_scene_session(scene)
    base_id = uuid4()
    old_provenance_id = uuid4()
    session.project.commit(ImportBatch(structures=(Structure(
        base_id, "base", (1,),
        ArrayData(numpy.asarray(((0.0, 0.0, 0.0),)), ("atom", "xyz"), "angstrom"),
    ),), provenance=(ProvenanceRecord(
        old_provenance_id, "base", "ChemBlender", "2.3.0", "", "", (),
        "legacy_blend_migration", (("legacy_object_name", detection.objects[0].name),),
    ),)))
    bondless_mesh = bpy.data.meshes.new("bondless legacy scaffold")
    bondless_mesh.from_pydata(((0.0, 0.0, 0.0),), (), ())
    atomic_num = bondless_mesh.attributes.new("atomic_num", "INT", "POINT")
    atomic_num.data[0].value = 6
    bondless = bpy.data.objects.new("bondless legacy scaffold", bondless_mesh)
    scene.collection.objects.link(bondless)
    bondless["Type"] = "scaffold"
    migration._legacy_load_post_handler(None)
    preview = migration.preview_legacy_migration(scene)
    assert preview.plan.view_plans
    bondless_plan = next(
        item for item in preview.plan.view_plans
        if item.legacy_object_name == bondless.name
    )
    assert bondless_plan.settings.bond_scales == ()
    assert preview.entity_inventory
    assert tuple(item.legacy_object_name for item in preview.entity_inventory) == preview.plan.report.object_names
    if "cell_edges_partial_uij" in preview.plan.report.object_names:
        backup_only = next(
            item for item in preview.entity_inventory
            if item.legacy_object_name == "cell_edges_partial_uij"
        )
        assert backup_only.backup_only
        assert backup_only.entity_types == ()
        assert backup_only.entity_ids == ()
    assert all(
        "Structure" in item.entity_types and "ProvenanceRecord" in item.entity_types
        for item in preview.entity_inventory if not item.backup_only
    )
    assert all(str(old_provenance_id) not in item.entity_ids for item in preview.entity_inventory)
    crystal_inventory = [
        item for item in preview.entity_inventory
        if item.kind == "crystal" and not item.backup_only
    ]
    assert all("PeriodicSiteData" in item.entity_types for item in crystal_inventory)
    if "cell_edges_partial_uij" in preview.plan.report.object_names:
        assert hasattr(migration, "_object_diagnostic_messages"), (
            "preview popup needs a shared object-diagnostic renderer"
        )
        assert "scientific coordinates use the original base mesh, not modifier output" in (
            migration._object_diagnostic_messages(preview, "cell_edges_partial_uij")
        ), "backup-only object diagnostics must render in the preview popup"
    try:
        migration.migrate_legacy_scene(scene, confirmed=False)
    except ValueError as error:
        assert "confirmation" in str(error)
    else:
        raise AssertionError("migration accepted without explicit confirmation")

    originals = tuple(bpy.data.objects[name] for name in preview.plan.report.object_names)
    collections_before = tuple(sorted(item.name for item in bpy.data.collections))
    inventory_before = _inventory()
    objects_before = _object_snapshot(originals, scene)
    links_before_snapshot = _scene_links_snapshot()
    siblings_before_snapshot = _sibling_inventory(preview.sidecar_path)
    snapshot_failure = RuntimeError("injected snapshot deepcopy failure")
    original_deepcopy = migration.deepcopy

    def fail_snapshot_deepcopy(_value):
        raise snapshot_failure

    migration.deepcopy = fail_snapshot_deepcopy
    try:
        migration._backup_legacy(originals, scene, uuid4(), uuid4())
    except RuntimeError as error:
        assert error is snapshot_failure
    else:
        raise AssertionError("snapshot failure did not escape")
    finally:
        migration.deepcopy = original_deepcopy
    assert tuple(sorted(item.name for item in bpy.data.collections)) == collections_before
    assert _inventory() == inventory_before
    assert _object_snapshot(originals, scene) == objects_before
    assert _scene_links_snapshot() == links_before_snapshot
    assert _sibling_inventory(preview.sidecar_path) == siblings_before_snapshot
    assert "ChemBlender Legacy Backup" not in bpy.data.collections

    alternate_layer = scene.view_layers.new("Migration Target Alternate")
    for obj in (bpy.data.objects[name] for name in preview.plan.report.object_names):
        obj.hide_set(not obj.hide_get(view_layer=scene.view_layers[0]), view_layer=alternate_layer)

    view_inventory = _inventory()
    original_readback = migration._write_display_attribute
    readback_failed = False

    def fail_after_readback(*args):
        nonlocal readback_failed
        original_readback(*args)
        readback_failed = True
        raise RuntimeError("injected readback failure")

    migration._write_display_attribute = fail_after_readback
    try:
        migration._new_view(preview.plan, preview.plan.view_plans[0], scene.collection, [])
    except RuntimeError as error:
        assert str(error) == "injected readback failure"
    else:
        raise AssertionError("readback failure did not escape")
    finally:
        migration._write_display_attribute = original_readback
    assert readback_failed
    assert _inventory() == view_inventory

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
    siblings_before = _sibling_inventory(preview.sidecar_path)
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
    assert _sibling_inventory(preview.sidecar_path) == siblings_before
    assert session.project is not lazy_before
    assert session.project.structures[base_id].coordinates.values[0, 0] == 0.0

    preview = migration.preview_legacy_migration(scene)
    original = _object_snapshot(
        tuple(bpy.data.objects[name] for name in preview.plan.report.object_names), scene,
    )
    expected_entity_ids = None
    expected_view_plans = ()
    original_commit = migration.commit_legacy_migration

    def capture_migration_plan(current_session, plan):
        nonlocal expected_entity_ids, expected_view_plans
        expected_entity_ids = _entity_id_sets(plan.project)
        expected_view_plans = plan.view_plans
        return original_commit(current_session, plan)

    migration.commit_legacy_migration = capture_migration_plan
    try:
        result = migration.migrate_legacy_scene(scene, confirmed=True)
    finally:
        migration.commit_legacy_migration = original_commit
    assert result.sidecar_path.is_dir()
    assert result.cleanup_warnings == ()
    assert _entity_id_sets(session.project) == expected_entity_ids
    assert {item.name for item in bpy.data.objects if item.name.endswith(" (Migrated)")} == {
        f"{item.legacy_object_name} (Migrated)" for item in expected_view_plans
    }
    assert session.link_status == "connected"
    assert base_id in session.project.structures
    backup = bpy.data.collections["ChemBlender Legacy Backup"]
    assert backup.hide_viewport
    assert backup.hide_render
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
    for view_plan in expected_view_plans:
        view = bpy.data.objects[f"{view_plan.legacy_object_name} (Migrated)"]
        assert view.get("cb_structure_contract") == "structure_view_v1"
        assert view["cb_structure_id"] == str(view_plan.structure_id)
        topology = next(
            (item for item in session.project.topologies.values()
             if item.structure_id == view_plan.structure_id),
            None,
        )
        if topology is None:
            assert "cb_topology_id" not in view
            assert view["cb_topology_render_identity"] == "atoms-only"
        else:
            assert view["cb_topology_id"] == str(topology.id)
            assert view["cb_topology_revision"] == topology.revision
        assert view.users_collection[0].name == scene.collection.name
        assert all(child.parent == view and child.get("cbq_contract") for child in view.children)
        _verify_display(view, view_plan.settings)
    assert migration.legacy_migration_detection(scene).objects == ()

    assert bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath) == {"FINISHED"}
    assert bpy.ops.wm.open_mainfile(filepath=bpy.data.filepath) == {"FINISHED"}
    reopened_scene = bpy.data.scenes[target_scene_name]
    assert migration.legacy_migration_detection(reopened_scene).objects == ()
    reopened_link = migration.resolve_project_link(reopened_scene, blend_path=bpy.data.filepath)
    try:
        assert reopened_link.status.value == "connected"
        reopened_project = reopened_link.project
        assert _entity_id_sets(reopened_project) == expected_entity_ids
        base_coordinates = reopened_project.structures[base_id].coordinates.values
        assert isinstance(base_coordinates, LazyNpyArray)
        assert not base_coordinates.loaded
        assert base_coordinates[0, 0] == 0.0
        assert base_coordinates.loaded
        reopened_backup = bpy.data.collections["ChemBlender Legacy Backup"]
        assert reopened_backup.hide_viewport
        assert reopened_backup.hide_render
        assert reopened_backup.name in {item.name for item in reopened_scene.collection.children}
        for view_plan in expected_view_plans:
            reopened_view = bpy.data.objects[f"{view_plan.legacy_object_name} (Migrated)"]
            assert reopened_view.get("cb_structure_contract") == "structure_view_v1"
            assert reopened_view["cb_structure_id"] == str(view_plan.structure_id)
            topology = next(
                (item for item in reopened_project.topologies.values()
                 if item.structure_id == view_plan.structure_id),
                None,
            )
            if topology is None:
                assert "cb_topology_id" not in reopened_view
                assert reopened_view["cb_topology_render_identity"] == "atoms-only"
            else:
                assert reopened_view["cb_topology_id"] == str(topology.id)
                assert reopened_view["cb_topology_revision"] == topology.revision
            assert all(child.parent == reopened_view and child.get("cbq_contract") for child in reopened_view.children)
            _verify_display(reopened_view, view_plan.settings)
        for name, (collections, hidden_viewport, hidden_layers, _properties) in original.items():
            obj = bpy.data.objects[name]
            assert tuple(sorted(group.name for group in obj.users_collection)) == (reopened_backup.name,)
            assert obj.hide_viewport == hidden_viewport
            assert tuple((layer.name, obj.hide_get(view_layer=layer)) for layer in reopened_scene.view_layers) == hidden_layers
            assert obj["cb_legacy_migration_backup"] == "v2"
            assert obj["cb_legacy_migration_project_id"] == reopened_backup["cb_legacy_migration_project_id"]
            assert obj["cb_legacy_migration_transaction_id"] == reopened_backup["cb_legacy_migration_transaction_id"]
    finally:
        if reopened_link.project is not None:
            close_project(reopened_link.project)
    print("PASS: legacy migration transaction and reopen")


if __name__ == "__main__":
    main()
