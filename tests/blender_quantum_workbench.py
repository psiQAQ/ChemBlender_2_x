"""Run with Blender --background --factory-startup --python-exit-code 1 --python this_file."""

import json
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import bpy
import numpy as np
import openvdb


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbq_core.model import ArrayData
from cbq_core.model import DatasetStatus
from cbq_core.model import Grid3D
from cbq_core.model import ImportBatch
from cbq_core.session import ProjectSession
from cbq_core.model import QCProject
from cbq_core.model import Structure
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import plan_scene_preset
from ChemBlender.surface_view import (
    create_property_surface,
    create_signed_isosurfaces,
    remove_surface_object,
)


BOHR_TO_ANGSTROM = 0.529177210903
ORIGIN = np.array((-3.7, -2.9, -3.3))
STEPS = np.array(((0.5, 0.1, 0.0), (0.1, 0.45, 0.05), (0.0, 0.1, 0.55)))
LINEAR_COEFFICIENTS = np.array((0.7, -0.4, 0.2))
STRUCTURE_ID = uuid4()


def make_grid(values, role, revision):
    return Grid3D(
        id=uuid4(), revision=revision, semantic_role=role, domain="grid",
        data=ArrayData(np.asarray(values, dtype=np.float32), ("x", "y", "z"), "dimensionless"),
        status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        structure_id=STRUCTURE_ID, origin=tuple(ORIGIN),
        step_vectors=tuple(tuple(row) for row in STEPS), coordinate_unit="bohr",
    )


def mesh_snapshot(obj):
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    geometry = evaluated.evaluated_geometry()
    assert geometry.mesh is not None, "surface did not evaluate to a mesh"
    mesh = geometry.mesh
    assert mesh.vertices and mesh.polygons, "surface mesh must be nonempty"
    assert all(polygon.use_smooth for polygon in mesh.polygons)
    vertices = np.asarray([tuple(vertex.co) for vertex in mesh.vertices], dtype=float)
    rounded = [tuple(np.round(vertex, 6)) for vertex in vertices]
    # Canonical coordinates and face membership ignore Blender's element ordering.
    canonical_vertices = tuple(sorted(rounded))
    canonical_faces = tuple(sorted(
        tuple(sorted(rounded[index] for index in polygon.vertices))
        for polygon in mesh.polygons
    ))
    bounds = tuple(np.round(np.concatenate((vertices.min(axis=0), vertices.max(axis=0))), 6))
    attribute = mesh.attributes.get("cbq_surface_property")
    samples = None if attribute is None else np.asarray([entry.value for entry in attribute.data])
    return vertices, samples, (canonical_vertices, canonical_faces, bounds)


def verify_vdb_affine(obj, expected_grids):
    grids, _metadata = openvdb.readAll(obj["cb_cache_path"])
    assert {grid.name for grid in grids} == set(expected_grids)
    for grid in grids:
        for index in ((0, 0, 0), (2, 3, 4), (12, 12, 12)):
            expected = (ORIGIN + np.asarray(index) @ STEPS) * BOHR_TO_ANGSTROM
            np.testing.assert_allclose(grid.transform.indexToWorld(index), expected, atol=1e-12)
    assert obj["cb_structure_id"] == str(STRUCTURE_ID)
    assert obj["cb_source_coordinate_unit"] == "bohr"
    assert obj["cb_display_coordinate_unit"] == "angstrom"


def check_property_geometry(cache_root):
    indices = np.indices((13, 13, 13), dtype=float).transpose(1, 2, 3, 0)
    radius = np.linalg.norm(indices - 6.0, axis=-1)
    density = make_grid(np.maximum(3.5 - radius, 0.0), "electron_density", "density-r1")
    world = (ORIGIN + indices @ STEPS) * BOHR_TO_ANGSTROM
    linear = world @ LINEAR_COEFFICIENTS + 0.15
    properties = (
        ("zero", np.zeros_like(linear), 0.0),
        ("linear", linear, 1.0),
        ("large", 50.0 * linear, 50.0),
    )
    reference = None
    results = {}
    for name, values, multiplier in properties:
        prop = make_grid(values, "electrostatic_potential", f"property-{name}-r1")
        obj = create_property_surface(
            density, prop, cache_root, isovalue=0.5,
            color_min=-20.0, color_max=20.0, colormap="coolwarm",
            surface_dataset_index=0, property_dataset_index=0,
            render_identity=f"regression-property-{name}", collection=bpy.context.scene.collection,
        )
        try:
            verify_vdb_affine(obj, ("density", "property"))
            vertices, sampled, canonical = mesh_snapshot(obj)
            assert sampled is not None and len(sampled) == len(vertices)
            results[name] = {"vertices": len(vertices), "faces": len(canonical[1]), "bbox": canonical[2]}
            print("WORKBENCH_PROPERTY", name, json.dumps(results[name]))
            if reference is None:
                reference = canonical
            else:
                assert canonical == reference, f"property {name} changed density surface geometry: {results}"
            expected = multiplier * (vertices @ LINEAR_COEFFICIENTS + 0.15)
            np.testing.assert_allclose(sampled, expected, rtol=2e-5, atol=2e-5,
                                       err_msg=f"{name} property must interpolate at each world-space vertex")
            results[name]["sample_max_error"] = float(np.max(np.abs(sampled - expected)))
        finally:
            remove_surface_object(obj)
    return results


def check_signed_branches(cache_root):
    indices = np.indices((13, 13, 13), dtype=float).transpose(1, 2, 3, 0)
    positive = np.maximum(2.3 - np.linalg.norm(indices - (8, 6, 6), axis=-1), 0.0)
    negative = np.maximum(2.3 - np.linalg.norm(indices - (4, 6, 6), axis=-1), 0.0)
    grid = make_grid(positive - negative, "molecular_orbital", "signed-r1")
    objects = create_signed_isosurfaces(
        grid, cache_root, isovalue=0.5,
        positive_color=(0.2, 0.3, 0.8, 1.0), negative_color=(0.8, 0.2, 0.3, 1.0),
        opacity=1.0, dataset_index=0, render_identity="regression-signed",
        collection=bpy.context.scene.collection,
    )
    try:
        assert [obj["cb_surface_phase"] for obj in objects] == ["positive", "negative"]
        assert [obj["cb_surface_isovalue"] for obj in objects] == [0.5, -0.5]
        means = []
        for obj in objects:
            verify_vdb_affine(obj, ("density",))
            vertices, _samples, _canonical = mesh_snapshot(obj)
            local = (vertices / BOHR_TO_ANGSTROM - ORIGIN) @ np.linalg.inv(STEPS)
            means.append(float(local[:, 0].mean()))
        assert means[0] > 7.0 and means[1] < 5.0, means
        return {"positive_index_x_mean": means[0], "negative_index_x_mean": means[1]}
    finally:
        for obj in objects:
            remove_surface_object(obj)


def resource_snapshot(*, names=False):
    return tuple(
        frozenset(value.name if names else value.as_pointer()
                  for value in getattr(bpy.data, name))
        for name in ("objects", "volumes", "node_groups", "materials")
    )


def make_legacy_view(project, density, prop, cache_root, collection):
    from ChemBlender.scene_preset_view import _write_plan_metadata

    old_preset = replace(
        builtin_scene_presets()["property_on_surface"], version="1",
        adapter_contracts=("openvdb_volume_v1", "volume_to_mesh_v1", "surface_property_plan_v1"),
        default_settings=(
            ("surface_dataset_index", 0), ("property_dataset_index", 0),
            ("surface_isovalue", 0.001), ("color_min", -0.1),
            ("color_max", 0.1), ("symmetric", True), ("colormap", "coolwarm"),
        ),
    )
    plan = plan_scene_preset(old_preset, project,
                             {"surface_grid": density.id, "property_grid": prop.id},
                             {"surface_isovalue": 0.5, "color_min": -2.0, "color_max": 2.0})
    obj = create_property_surface(
        density, prop, cache_root, isovalue=0.5, color_min=-2.0, color_max=2.0,
        colormap="coolwarm", surface_dataset_index=0, property_dataset_index=0,
        render_identity=plan.render_identity, collection=collection,
    )
    _write_plan_metadata(obj, plan, {"surface_grid": density, "property_grid": prop})
    group = obj.modifiers[0].node_group
    nodes, links = group.nodes, group.links
    # Reproduce the historical whole-Volume meshing graph, not just a v1 label.
    modern_mesh = next(node for node in nodes if node.bl_idname == "GeometryNodeGridToMesh")
    destination = modern_mesh.outputs["Mesh"].links[0].to_socket
    nodes.remove(modern_mesh)
    density_node = next(node for node in nodes
                        if node.bl_idname == "GeometryNodeGetNamedGrid"
                        and node.inputs["Name"].default_value == "density")
    nodes.remove(density_node)
    old_mesh = nodes.new("GeometryNodeVolumeToMesh")
    old_mesh.inputs["Threshold"].default_value = 0.5
    group_input = next(node for node in nodes if node.bl_idname == "NodeGroupInput")
    links.new(group_input.outputs["Geometry"], old_mesh.inputs["Volume"])
    links.new(old_mesh.outputs["Mesh"], destination)
    obj.modifiers[0]["cbq_contract"] = group["cbq_contract"] = "property_surface_v1"
    return obj


def check_legacy_rebuild(cache_root):
    from ChemBlender.scene_preset_view import apply_scene_preset
    from ChemBlender.ui.grid import rebuild_property_view
    from ChemBlender.ui.view_cache import ViewCacheError, repair_project_view_caches

    indices = np.indices((13, 13, 13), dtype=float).transpose(1, 2, 3, 0)
    density = make_grid(np.maximum(3.5 - np.linalg.norm(indices - 6, axis=-1), 0),
                        "electron_density", "legacy-density-r1")
    linear = ((ORIGIN + indices @ STEPS) * BOHR_TO_ANGSTROM) @ LINEAR_COEFFICIENTS + 0.15
    prop = make_grid(linear, "electrostatic_potential", "legacy-property-r1")
    structure = Structure(STRUCTURE_ID, "structure-r1", (1,),
                          ArrayData(np.zeros((1, 3)), ("atom", "xyz"), "bohr"))
    project = QCProject(uuid4(), "0.2")
    project.commit(ImportBatch(structures=(structure,), datasets=(density, prop)))
    sidecar = Path(cache_root) / "legacy.cbq"
    sidecar.mkdir()
    session = ProjectSession(uuid4(), project, Path(cache_root),
                             sidecar_path=sidecar, link_status="connected")
    collection = bpy.data.collections.new("User surface collection")
    extra_collection = bpy.data.collections.new("Shared user collection")
    bpy.context.scene.collection.children.link(collection)
    bpy.context.scene.collection.children.link(extra_collection)
    legacy = make_legacy_view(project, density, prop, cache_root, collection)
    extra_collection.objects.link(legacy)
    legacy.location = (2.0, -1.0, 0.3)
    legacy.rotation_euler = (0.2, 0.0, -0.1)
    legacy.scale = (1.3, 0.8, 1.1)
    legacy["user_note"] = "Keep this object"
    saved = Path(cache_root) / "legacy-view.blend"
    legacy_name = legacy.name
    collection_name, extra_collection_name = collection.name, extra_collection.name
    bpy.ops.wm.save_as_mainfile(filepath=str(saved), check_existing=False)
    bpy.ops.wm.open_mainfile(filepath=str(saved))
    legacy = bpy.data.objects[legacy_name]
    collection = bpy.data.collections[collection_name]
    extra_collection = bpy.data.collections[extra_collection_name]
    assert legacy.modifiers[0].node_group["cbq_contract"] == "property_surface_v1"
    legacy.modifiers[0].pop("cbq_contract", None)
    user_group = bpy.data.node_groups.new("User passthrough", "GeometryNodeTree")
    user_group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    user_group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    user_group.links.new(user_group.nodes.new("NodeGroupInput").outputs["Geometry"],
                         user_group.nodes.new("NodeGroupOutput").inputs["Geometry"])
    user_modifier = legacy.modifiers.new("User modifier", "NODES")
    user_modifier.node_group = user_group
    current_plan = plan_scene_preset(builtin_scene_presets()["grid_volume"],
                                     project, {"grid": density.id}, {})
    current, = apply_scene_preset(current_plan, project, cache_root=cache_root, collection=collection)
    unrelated = bpy.data.objects.new("Unrelated user object", None)
    collection.objects.link(unrelated)
    unrelated["user_note"] = "untouched"
    try:
        bpy.context.view_layer.update()
        old_mesh = mesh_snapshot(legacy)[2]
        old_identity = legacy["cb_scene_render_identity"]
        original_pointer = legacy.as_pointer()
        transform = legacy.matrix_world.copy()
        collections = tuple(item.as_pointer() for item in legacy.users_collection)
        user_pointer = user_modifier.as_pointer()
        old_data_name, old_group_name = legacy.data.name, legacy.modifiers[0].node_group.name
        old_material_name = next(node.inputs["Material"].default_value.name
                                 for node in legacy.modifiers[0].node_group.nodes
                                 if node.bl_idname == "GeometryNodeSetMaterial")
        old_path = legacy.data.filepath
        current_pointer = current.as_pointer()
        current.data.grids.unload()
        Path(current["cb_cache_path"]).unlink()
        try:
            repair_project_view_caches(session=session, objects=(legacy, current, unrelated),
                                       blend_path=Path(cache_root) / "legacy.blend")
        except ViewCacheError as error:
            assert "stale" in str(error)
        else:
            raise AssertionError("legacy view must require explicit rebuilding")
        assert legacy["cb_view_stale"] and not legacy["cb_report_eligible"]
        assert legacy.data.filepath == old_path and mesh_snapshot(legacy)[2] == old_mesh
        assert current.as_pointer() == current_pointer and Path(current["cb_cache_path"]).is_file()
        assert not current.get("cb_view_stale") and dict(unrelated.items()) == {"user_note": "untouched"}

        before_failure = resource_snapshot()
        old_metadata = legacy.id_properties_ensure().to_dict()
        with patch("ChemBlender.surface_view._surface_group", side_effect=RuntimeError("injected creation failure")):
            try:
                rebuild_property_view(session, legacy, cache_root)
            except RuntimeError as error:
                assert "injected creation failure" in str(error)
            else:
                raise AssertionError("injected creation failure did not propagate")
        assert resource_snapshot() == before_failure, "failed preparation leaked Blender resources"
        assert legacy.id_properties_ensure().to_dict() == old_metadata
        assert legacy.data.name == old_data_name and mesh_snapshot(legacy)[2] == old_mesh

        rebuilt = rebuild_property_view(session, legacy, cache_root)
        assert rebuilt.as_pointer() == original_pointer
        assert rebuilt.matrix_world == transform
        assert tuple(item.as_pointer() for item in rebuilt.users_collection) == collections
        assert rebuilt.modifiers[1].as_pointer() == user_pointer
        assert rebuilt.modifiers[1].node_group == user_group and rebuilt["user_note"] == "Keep this object"
        assert rebuilt["cb_scene_preset_version"] == "2" and not rebuilt["cb_view_stale"]
        assert rebuilt["cb_report_eligible"] and "cb_view_diagnostic" not in rebuilt
        assert rebuilt["cb_scene_render_identity"] != old_identity
        group = rebuilt.modifiers[0].node_group
        assert rebuilt.modifiers[0]["cbq_contract"] == group["cbq_contract"] == "property_surface_v2"
        grid_to_mesh, = [node for node in group.nodes if node.bl_idname == "GeometryNodeGridToMesh"]
        assert grid_to_mesh.inputs["Grid"].links[0].from_node.inputs["Name"].default_value == "density"
        assert not any(node.bl_idname == "GeometryNodeVolumeToMesh" for node in group.nodes)
        assert bpy.data.volumes.get(old_data_name) is None
        assert bpy.data.node_groups.get(old_group_name) is None
        assert bpy.data.materials.get(old_material_name) is None
        assert tuple(map(len, resource_snapshot())) == tuple(map(len, before_failure))
        vertices, samples, new_mesh = mesh_snapshot(rebuilt)
        assert len(new_mesh[0]) == 176 and len(new_mesh[1]) == 174
        np.testing.assert_allclose(samples, vertices @ LINEAR_COEFFICIENTS + 0.15, atol=2e-5)
        assert session.active_view_object_name == rebuilt.name and "view_cache" in session.dirty_reasons
        return {"old_vertices": len(old_mesh[0]), "new_vertices": len(new_mesh[0]),
                "identity_preserved": True, "failure_rollback": True, "old_resources_removed": True}
    finally:
        from ChemBlender.scene_preset_view import _remove_objects
        owned_group = legacy.modifiers[0].node_group.name
        legacy.modifiers[0].pop("cbq_contract", None)
        _remove_objects((legacy,))
        assert bpy.data.node_groups.get(owned_group) is None
        assert bpy.data.node_groups.get(user_group.name) is user_group
        bpy.data.node_groups.remove(user_group)
        current_data = current.data
        bpy.data.objects.remove(current, do_unlink=True)
        bpy.data.volumes.remove(current_data)
        bpy.data.objects.remove(unrelated, do_unlink=True)
        bpy.data.collections.remove(extra_collection)
        bpy.data.collections.remove(collection)


def main():
    assert bpy.app.background, "run this regression in a separate background Blender process"
    # Blender drops unused factory materials (e.g. Dots Stroke) on reload.
    for material in tuple(bpy.data.materials):
        if material.users == 0:
            bpy.data.materials.remove(material)
    baseline_resources = resource_snapshot(names=True)
    with TemporaryDirectory(prefix="cbq-workbench-") as cache_root:
        result = {
            "blender_version": bpy.app.version_string,
            "property_geometry": check_property_geometry(cache_root),
            "signed_branches": check_signed_branches(cache_root),
            "legacy_rebuild": check_legacy_rebuild(cache_root),
        }
    final_resources = resource_snapshot(names=True)
    assert final_resources == baseline_resources, ("regression resource mismatch", baseline_resources, final_resources)
    print("WORKBENCH_PHASE_A_PASSED", json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
