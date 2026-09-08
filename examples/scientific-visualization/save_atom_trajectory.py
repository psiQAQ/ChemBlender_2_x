"""Save and independently verify real PQR/rMD17 workbenches in a private Blender.

Run once to publish a new scenes directory, then in another background Blender
with --verify. --lifecycle-cache tests Save As and directory moves on copies;
repeat it with --verify in another process to publish the compact evidence.
Existing scientific render packages are never rewritten.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".agents/cache"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_atom_trajectory import SOURCE, bindings_for, cases, hashes
from render_molecular import array_hashes, digest, staging_directory
from save_molecular import clean_scene
from ChemBlender.core import builtin_scene_presets, plan_scene_preset
from ChemBlender.core.sidecar import close_project, open_project
from ChemBlender.dataset_view import _VECTOR_ATTRIBUTE
from ChemBlender.scene_preset_view import apply_scene_preset, scene_view_objects
from ChemBlender.scientific_materials import flat_material
from ChemBlender.ui import session as session_ui
from ChemBlender.ui.view_cache import scene_plan_from_view


def write_json(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").replace("\n", "\r\n").encode("utf-8"))


def select(root, session):
    for obj in tuple(bpy.context.selected_objects):
        obj.select_set(False)
    root.select_set(True)
    bpy.context.view_layer.objects.active = root
    session.active_view_object_name = root.name
    assert bpy.ops.chemblender.scientific_view(action="LOAD") == {"FINISHED"}


def bounds(root):
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    points = [obj.evaluated_get(graph).matrix_world @ Vector(corner)
              for obj in scene_view_objects(root) if obj.type in {"MESH", "CURVE", "FONT"}
              for corner in obj.evaluated_get(graph).bound_box]
    assert points
    return np.asarray(points, dtype=float)


def check_frames(root, session, plan):
    """Check all real coordinates and forces via the public Apply Frame action."""
    if plan.view_kind not in {"trajectory", "trajectory_force"}:
        return bounds(root), 0
    entities = {binding.name: session.project.datasets[binding.entity_id]
                for binding in plan.bindings if binding.entity_kind == "dataset"}
    frames, force = entities["frames"], entities.get("force")
    assert frames.data.shape == (32, 21, 3) and frames.data.unit == "angstrom"
    select(root, session)
    settings = bpy.context.scene.chemblender_scientific_view
    geometry = []
    saved = dict(plan.settings)["frame_index"]
    for index in range(frames.data.shape[0]):
        settings.frame_index = index
        assert bpy.ops.chemblender.scientific_view(action="FRAME") == {"FINISHED"}
        assert root["cb_trajectory_frame_index"] == index
        assert root["cb_trajectory_frame_label"] == frames.comments[index]
        assert "cb_trajectory_time" not in root
        coordinates = np.empty(frames.data.shape[1] * 3)
        root.data.vertices.foreach_get("co", coordinates)
        np.testing.assert_allclose(coordinates.reshape(-1, 3), frames.data.values[index], atol=2e-6, rtol=0)
        if force is not None:
            assert force.data.unit == "electron_volt_per_angstrom"
            values = np.empty(force.data.shape[1] * 3)
            root.data.attributes[_VECTOR_ATTRIBUTE].data.foreach_get("vector", values)
            np.testing.assert_allclose(values.reshape(-1, 3),
                force.data.values[index] * root["cb_vector_display_scale"], atol=2e-6, rtol=0)
            assert root["cb_trajectory_force_status"] == "current frame"
        geometry.append(bounds(root))
    settings.frame_index = saved
    assert bpy.ops.chemblender.scientific_view(action="FRAME") == {"FINISHED"}
    assert root["cb_trajectory_frame_index"] == saved
    assert scene_plan_from_view(root, session.project).render_identity == plan.render_identity
    return np.concatenate(geometry), len(geometry)


def verify_views(session, rows):
    scientific = array_hashes(session.project)
    roots = [obj for obj in bpy.context.scene.objects if obj.get("cb_view_root") is True]
    assert len(roots) == len(rows)
    for row in rows:
        root = bpy.data.objects[row["name"]]
        assert root["cb_view_instance_id"] == row["instance_id"]
        plan = scene_plan_from_view(root, session.project)
        assert plan.render_identity == row["render_identity"]
        assert dict(plan.settings) == row["settings"]
        np.testing.assert_allclose(root.matrix_world, row["matrix_world"], atol=2e-6, rtol=0)
        select(root, session)
        assert bpy.context.scene.chemblender_scientific_view.template == dict(plan.settings)["template"]
        assert bpy.ops.chemblender.scientific_view(action="REBUILD") == {"FINISHED"}
        root = next(obj for obj in bpy.context.scene.objects
                    if obj.get("cb_view_root") is True and obj.get("cb_view_instance_id") == row["instance_id"])
        assert root["cb_view_instance_id"] == row["instance_id"]
        assert scene_plan_from_view(root, session.project).render_identity == row["render_identity"]
        np.testing.assert_allclose(root.matrix_world, row["matrix_world"], atol=2e-6, rtol=0)
        _points, count = check_frames(root, session, plan)
        assert count == row["verified_frame_count"]
        assert array_hashes(session.project) == scientific
    return scientific


def build(source_name, staging):
    scene = clean_scene()
    scene.name = "PQR Workbench" if source_name == "pqr" else "rMD17 Workbench"
    session = session_ui.get_scene_session(scene)
    previous = session.project
    source = SOURCE / (source_name + ".cbq")
    disk_before = hashes(source)
    session.project = open_project(source)
    close_project(previous)
    scientific = array_hashes(session.project)
    session.mark_dirty("example_source")
    blend = staging / (source_name + ".blend")
    assert bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=False) == {"FINISHED"}
    assert session.link_status == "connected", session_ui.get_scene_session_status(scene)
    rows, extents = [], []
    cursor = 0.
    for case in cases():
        if case["source"] != source_name or case["animation"]:
            continue
        for template in ("research", "teaching"):
            settings = dict(case["settings"], template=template, shaded=template == "teaching")
            plan = plan_scene_preset(builtin_scene_presets()[case["preset"]], session.project,
                                     bindings_for(session.project, case), settings)
            objects = apply_scene_preset(plan, session.project)
            root = objects[0]
            root.name = case["name"] + "-" + template
            root.matrix_world = Vector(case["direction"]).to_track_quat("Z", "Y").inverted().to_matrix().to_4x4()
            points, count = check_frames(root, session, plan)
            low, high = points.min(axis=0), points.max(axis=0)
            gap = max(float(high[0] - low[0]) * .18, 2.)
            translation = Vector((cursor - low[0], -(low[1] + high[1]) / 2., 0.))
            root.matrix_world = Matrix.Translation(translation) @ root.matrix_world
            cursor += high[0] - low[0] + gap
            extents.append(points + np.asarray(translation))
            root["cb_example_image"] = "../" + case["name"] + "/images/001-" + case["preset"] + "-" + template + "-0001.png"
            title_data = bpy.data.curves.new(root.name + " title", "FONT")
            title_data.body = case["name"] + " | " + template.title()
            title_data.size = max(float(high[0] - low[0]) * .028, .24)
            title_data.align_x = "CENTER"
            title_data.materials.append(flat_material(root.name + " label", (.045, .06, .08, 1.)))
            title = bpy.data.objects.new(root.name + " title", title_data)
            scene.collection.objects.link(title)
            title.location = (cursor - gap - (high[0] - low[0]) / 2., (high[1] - low[1]) / 2. + gap * .35, 0.)
            rows.append(dict(name=root.name, instance_id=root["cb_view_instance_id"],
                render_identity=plan.render_identity, preset=plan.preset_id, settings=dict(plan.settings),
                matrix_world=[list(row) for row in root.matrix_world], verified_frame_count=count))
    assert len(rows) == (2 if source_name == "pqr" else 4)
    points = np.concatenate(extents)
    low, high = points.min(axis=0), points.max(axis=0)
    center = (low + high) / 2.
    size = max(float(high[0] - low[0]), float(high[1] - low[1]) * 4. / 3.) * 1.2
    camera_data = bpy.data.cameras.new("Workbench Overview")
    camera = bpy.data.objects.new("Workbench Overview", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (center[0], center[1], high[2] + size * 2.)
    camera.data.type, camera.data.ortho_scale = "ORTHO", size
    camera.data.clip_end = size * 5.
    scene.camera = camera
    world = bpy.data.worlds.new("Workbench Background")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (.7, .73, .77, 1.)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .7
    scene.world = world
    for dx, power in ((-.2, 45.), (.3, 20.)):
        light_data = bpy.data.lights.new("Workbench Area", "AREA")
        light_data.energy, light_data.size = size * size * power, size * .6
        light = bpy.data.objects.new("Workbench Area", light_data)
        scene.collection.objects.link(light)
        light.location = (center[0] + size * dx, center[1], high[2] + size)
    scene.render.engine = "CYCLES"
    scene.render.resolution_x, scene.render.resolution_y = 2400, 1800
    scene.render.resolution_percentage = 100
    scene.cycles.samples, scene.cycles.use_denoising = 256, True
    scene.view_settings.view_transform, scene.view_settings.look = "Standard", "None"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_location = center
                area.spaces.active.region_3d.view_distance = size
                area.spaces.active.region_3d.view_rotation = (1., 0., 0., 0.)
                area.spaces.active.region_3d.view_perspective = "ORTHO"
    select(bpy.data.objects[rows[0]["name"]], session)
    session.mark_dirty("view_cache")
    assert bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=False) == {"FINISHED"}
    assert array_hashes(session.project) == scientific
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    session = session_ui.get_scene_session(bpy.context.scene)
    assert session.link_status == "connected"
    assert verify_views(session, rows) == scientific
    assert hashes(source) == disk_before
    arrays = {path.name: digest(path) for path in sorted(blend.with_suffix(".cbq").rglob("*.npy"))}
    assert arrays == {path.name: digest(path) for path in sorted(source.rglob("*.npy"))}
    source_project_id = str(session.project.id)
    session.mark_clean()
    session_ui.close_scene_session(bpy.context.scene)
    print("ATOM_TRAJECTORY_SAVED", source_name, len(rows), flush=True)
    return dict(source=source_name, blend=blend.name, sidecar=source_name + ".cbq", views=rows,
        blend_sha256=digest(blend), scientific_array_files=arrays, source_project_id=source_project_id,
        source_sidecar=source.relative_to(ROOT).as_posix(), saved_reopened=True,
        public_load_rebuild="Passed", scientific_arrays_unchanged=True)


def verify_published(destination):
    path = destination / "scene-manifest.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["created_process_id"] != os.getpid(), "verify in another Blender process"
    for entry in document["scenes"]:
        blend = destination / entry["blend"]
        assert digest(blend) == entry["blend_sha256"]
        expected_project = open_project(SOURCE / entry["sidecar"])
        try:
            expected = array_hashes(expected_project)
        finally:
            close_project(expected_project)
        bpy.ops.wm.open_mainfile(filepath=str(blend))
        session = session_ui.get_scene_session(bpy.context.scene)
        assert session.link_status == "connected"
        assert session.sidecar_path.resolve() == blend.with_suffix(".cbq")
        assert verify_views(session, entry["views"]) == expected
        assert {p.name: digest(p) for p in sorted(session.sidecar_path.rglob("*.npy"))} == entry["scientific_array_files"]
        entry["independent_reopen_public_load_rebuild"] = "Passed"
        session.mark_clean()
        session_ui.close_scene_session(bpy.context.scene)
        assert digest(blend) == entry["blend_sha256"]
        print("ATOM_TRAJECTORY_INDEPENDENT_REOPEN", entry["source"], len(entry["views"]), flush=True)
    document["verification_process_id"] = os.getpid()
    document["verification_script_sha256"] = digest(Path(__file__))
    document["independent_reopen_verified"] = True
    write_json(path, document)


def verify_lifecycle(destination, workspace, *, cold_reopen):
    """Mutate cache copies only, retaining formal files and full View identity."""
    workspace = workspace.resolve()
    assert CACHE.resolve() in workspace.parents and not workspace.is_symlink()
    source_manifest = destination / "scene-manifest.json"
    document = json.loads(source_manifest.read_text(encoding="utf-8"))
    protected = {name: value for name, value in hashes(destination).items()
                 if name != "lifecycle-verification.json"}
    report_path = workspace / "verification.json"
    if cold_reopen:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["status"] == "awaiting_cold_reopen"
        assert report["process_id"] != os.getpid(), "cold reopen requires another Blender process"
        assert report["source_manifest_sha256"] == digest(source_manifest)
    else:
        workspace.mkdir(parents=True, exist_ok=False)
        report = dict(status="running", blender=bpy.app.version_string, process_id=os.getpid(),
            script="examples/scientific-visualization/save_atom_trajectory.py",
            script_sha256=digest(Path(__file__)), source_manifest_sha256=digest(source_manifest),
            cache_evidence=report_path.relative_to(ROOT).as_posix(), scenes=[])

    def open_and_check(blend, entry):
        assert bpy.ops.wm.open_mainfile(filepath=str(blend)) == {"FINISHED"}
        session = session_ui.get_scene_session(bpy.context.scene)
        assert session.link_status == "connected"
        assert session.sidecar_path.resolve() == blend.with_suffix(".cbq")
        assert str(session.project.id) == entry["source_project_id"]
        assert {p.name: digest(p) for p in session.sidecar_path.rglob("*.npy")} == entry["scientific_array_files"]
        values = verify_views(session, entry["views"])
        assert {p.name: digest(p) for p in session.sidecar_path.rglob("*.npy")} == entry["scientific_array_files"]
        return session, values

    try:
        for entry in document["scenes"]:
            name = entry["source"]
            moved = workspace / (name + "-moved")
            moved_blend = moved / (name + "-copy.blend")
            if cold_reopen:
                row = next(row for row in report["scenes"] if row["source"] == name)
                assert digest(moved_blend) == row["moved_blend_sha256"]
                _session, scientific = open_and_check(moved_blend, entry)
                assert scientific == row["scientific_arrays"]
                row["independent_cold_reopen"] = "Passed"
            else:
                copied = workspace / (name + "-copy")
                copied.mkdir()
                original_blend = copied / entry["blend"]
                shutil.copyfile(destination / entry["blend"], original_blend)
                shutil.copytree(destination / entry["sidecar"], original_blend.with_suffix(".cbq"))
                session, scientific = open_and_check(original_blend, entry)
                saved = copied / "save-as"
                saved.mkdir()
                new_blend = saved / moved_blend.name
                # Exercise Blender's default relative_remap=True across directories.
                assert bpy.ops.wm.save_as_mainfile(filepath=str(new_blend), check_existing=False) == {"FINISHED"}
                assert session.sidecar_path.resolve() == new_blend.with_suffix(".cbq")
                session_ui.close_scene_session(bpy.context.scene)
                session, saved_scientific = open_and_check(new_blend, entry)
                assert saved_scientific == scientific
                session_ui.close_scene_session(bpy.context.scene)
                # Both resolved endpoints are confined to this task's cache workspace.
                assert workspace in saved.resolve().parents and workspace in moved.resolve().parents
                assert not saved.is_symlink() and not moved.exists()
                os.rename(saved, moved)
                session, moved_scientific = open_and_check(moved_blend, entry)
                assert moved_scientific == scientific
                session.mark_dirty("view_cache")
                assert bpy.ops.wm.save_as_mainfile(filepath=str(moved_blend), check_existing=False) == {"FINISHED"}
                report["scenes"].append(dict(source=name, project_id=entry["source_project_id"],
                    view_count=len(entry["views"]), instance_ids=[row["instance_id"] for row in entry["views"]],
                    render_identities=[row["render_identity"] for row in entry["views"]],
                    array_file_count=len(entry["scientific_array_files"]), scientific_arrays=scientific,
                    scientific_array_files=entry["scientific_array_files"], save_as="Passed", move="Passed",
                    public_load_rebuild="Passed", matrices_and_settings="unchanged",
                    trajectory_frames=32 if name == "rmd17" else None,
                    moved_blend_sha256=digest(moved_blend)))
            session_ui.close_scene_session(bpy.context.scene)
            print("ATOM_TRAJECTORY_LIFECYCLE", name, "cold reopen" if cold_reopen else "Save As + move", flush=True)
        report["status"] = "Passed" if cold_reopen else "awaiting_cold_reopen"
        if cold_reopen:
            report["cold_reopen_process_id"] = os.getpid()
            report["verification_script_sha256"] = digest(Path(__file__))
    except BaseException as error:
        report.update(status="Failed", error=repr(error))
        raise
    finally:
        session_ui.close_scene_session(bpy.context.scene)
        assert all(digest(destination / name) == value for name, value in protected.items()), "formal scenes changed"
        report["formal_scenes_unchanged"] = True
        write_json(report_path, report)
    if cold_reopen:
        write_json(destination / "lifecycle-verification.json", report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "examples/scientific-visualization/output/atom-trajectory/scenes")
    parser.add_argument("--existing-libraries", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--lifecycle-cache", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
    assert bpy.app.background and CACHE in private.parents
    assert private in Path(bpy.utils.user_resource("CONFIG")).resolve().parents, "private config must exist before Blender starts"
    libraries = args.existing_libraries.resolve(strict=True)
    assert CACHE in libraries.parents, "use previously qualified private wheel libraries"
    sys.path.append(str(libraries))  # NumPy was imported from Blender before adding native wheels.
    destination = args.output.resolve()
    render_manifest = destination.parent / "manifest.json"
    render_document = json.loads(render_manifest.read_text(encoding="utf-8"))
    protected = {destination.parent / row["path"]: row["sha256"] for row in render_document["artifacts"]}
    protected[render_manifest] = digest(render_manifest)
    assert all(digest(path) == value for path, value in protected.items())
    import ChemBlender

    bpy.context.preferences.filepaths.save_version = 0
    ChemBlender.register()
    try:
        if args.lifecycle_cache:
            verify_lifecycle(destination, args.lifecycle_cache, cold_reopen=args.verify)
        elif args.verify:
            verify_published(destination)
        else:
            if destination.exists():
                raise FileExistsError("choose a new scenes output directory")
            # Keep atomic .cbq temporary names below Windows' legacy path limit.
            with staging_directory(CACHE, "atom-scenes-") as staging:
                try:
                    entries = [build(name, staging) for name in ("pqr", "rmd17")]
                finally:
                    # Release memory maps before the staging owner cleans up on failure.
                    session_ui.close_scene_session(bpy.context.scene)
                write_json(staging / "scene-manifest.json", dict(schema_version=1,
                    purpose="Real PQR and rMD17 workbenches; source arrays remain authoritative",
                    blender=bpy.app.version_string, script="examples/scientific-visualization/save_atom_trajectory.py",
                    script_sha256=digest(Path(__file__)), created_process_id=os.getpid(),
                    independent_reopen_verified=False, scenes=entries,
                    render_manifest="../manifest.json", render_manifest_sha256=digest(render_manifest),
                    original_render_artifacts_unchanged=True,
                    limitations=["rMD17 source sequence has no physical time interval; 32 frames are not time-calibrated",
                                 "Panel layout is a View transform and does not modify source coordinates or forces"]))
                if destination.exists():
                    raise FileExistsError("output appeared during preparation")
                os.rename(staging, destination)
    finally:
        session_ui.close_scene_session(bpy.context.scene)
        ChemBlender.unregister()
        assert all(digest(path) == value for path, value in protected.items()), "existing render artifacts changed"
    print("ATOM_TRAJECTORY_WORKBENCH_PASSED", destination, flush=True)


if __name__ == "__main__":
    main()
