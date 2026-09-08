"""Publish three replayable molecule workbenches using the normal .blend handlers."""

import argparse
import json
import os
from pathlib import Path
import sys
from uuid import UUID

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_molecular import SOURCE, array_hashes, cases, digest, staging_directory
from ChemBlender.core.scene_preset import builtin_scene_presets, plan_scene_preset
from ChemBlender.core.sidecar import close_project, open_project
from ChemBlender.scene_preset_view import apply_scene_preset
from ChemBlender.scientific_materials import flat_material
from ChemBlender.ui import session as session_ui
from ChemBlender.ui.view_cache import _durable_cache_root, scene_plan_from_view


def clean_scene():
    session_ui.close_scene_session(bpy.context.scene)
    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene = bpy.data.scenes.new("Molecular Workbench")
    bpy.context.window.scene = scene
    for other in tuple(bpy.data.scenes):
        if other != scene:
            bpy.data.scenes.remove(other)
    return scene


def build(molecule, staging, renders):
    scene = clean_scene()
    source = SOURCE / (molecule + ".cbq")
    session = session_ui.get_scene_session(scene)
    previous = session.project
    session.project = open_project(source)
    close_project(previous)
    scientific = array_hashes(session.project)
    session.mark_dirty("example_source")
    blend = staging / (molecule + ".blend")
    # The save handler publishes the original scientific arrays before VDB caches.
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=False)
    assert session.link_status == "connected", session_ui.get_scene_session_status(scene)
    cache = _durable_cache_root(session.sidecar_path)
    selected = [case for case in cases() if case["molecule"] == molecule]
    first_root = None
    rows = []
    label_material = flat_material("Workbench panel title", (.045, .06, .08, 1.))
    for ordinal, case in enumerate(selected):
        for style_index, template in enumerate(("research", "teaching")):
            name = case["name"] + "-" + template
            record = renders["images"][name]
            bindings = {key: UUID(value["id"]) for key, value in record["datasets"].items()}
            preset = builtin_scene_presets()[case["preset"]]
            settings = {key: value for key, value in dict(record["plan"]["settings"]).items()
                        if key in dict(preset.default_settings)}
            plan = plan_scene_preset(builtin_scene_presets()[case["preset"]], session.project, bindings, settings)
            collection = bpy.data.collections.new(name)
            scene.collection.children.link(collection)
            objects = apply_scene_preset(plan, session.project, collection=collection, cache_root=cache)
            root = objects[0]
            root.name = name
            panel_index = ordinal * 2 + style_index
            center = Vector(((panel_index % 3) * 8.5, -(panel_index // 3) * 7., 0.))
            rotation = Matrix(record["display"]["camera"]["matrix_world"]).to_3x3().inverted().to_4x4()
            root.matrix_world = Matrix.Translation(center) @ rotation
            root["cb_example_render_framing_json"] = json.dumps(record["display"]["framing"], sort_keys=True)
            root["cb_example_image"] = "../images/" + record["relative_path"]
            if first_root is None:
                first_root = root
            grid = session.project.datasets[next(iter(bindings.values()))]
            if case["preset"] not in {"grid_slice", "grid_profile"}:
                structure = session.project.structures[grid.structure_id]
                atom_plan = plan_scene_preset(builtin_scene_presets()["structure_publication"], session.project,
                                             {"structure": structure.id}, {"template": template})
                atom = apply_scene_preset(atom_plan, session.project, collection=collection)[0]
                atom.matrix_world = root.matrix_world
                atom.name = name + " atoms"
            label = bpy.data.curves.new(name + " title", "FONT")
            label.body = case["formula"] + "\n" + template.title()
            label.size = .22
            label.align_x = "CENTER"
            label.materials.append(label_material)
            title = bpy.data.objects.new(name + " title", label)
            collection.objects.link(title)
            title.location = center + Vector((0., 2.8, 0.))
            rows.append(dict(name=name, instance_id=root["cb_view_instance_id"],
                             render_identity=plan.render_identity, preset=case["preset"],
                             settings=settings, framing=record["display"]["framing"]))
    height = ((len(rows) - 1) // 3 + 1) * 7.
    camera_data = bpy.data.cameras.new("Workbench Overview")
    camera = bpy.data.objects.new("Workbench Overview", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (8.5, -(height - 7.) / 2., 50.)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(29., height * 4. / 3.)
    scene.camera = camera
    world = bpy.data.worlds.new("Workbench Background")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (.7, .73, .77, 1.)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .7
    scene.world = world
    for offset, power in (((0., 0., 15.), 12000.), ((15., -12., 10.), 6000.)):
        data = bpy.data.lights.new("Workbench Area", "AREA")
        data.energy, data.size = power, 15.
        light = bpy.data.objects.new("Workbench Area", data)
        scene.collection.objects.link(light)
        light.location = offset
    scene.render.engine = "CYCLES"
    scene.render.resolution_x, scene.render.resolution_y = 2400, 1800
    scene.render.resolution_percentage = 100
    scene.cycles.samples, scene.cycles.use_denoising = 256, True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene["cb_example_render_manifest"] = "../images/render-manifest.json"
    for obj in tuple(bpy.context.selected_objects):
        obj.select_set(False)
    first_root.select_set(True)
    bpy.context.view_layer.objects.active = first_root
    session.active_entity_id = UUID(first_root["cb_dataset_id"])
    session.mark_dirty("view_cache")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=False)
    assert array_hashes(session.project) == scientific
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    session = session_ui.get_scene_session(bpy.context.scene)
    assert session.link_status == "connected", session_ui.get_scene_session_status(bpy.context.scene)
    assert array_hashes(session.project) == scientific
    for row in rows:
        obj = bpy.data.objects[row["name"]]
        plan = scene_plan_from_view(obj, session.project)
        assert plan.render_identity == row["render_identity"]
        assert obj["cb_view_instance_id"] == row["instance_id"]
    session.mark_clean()
    session_ui.close_scene_session(bpy.context.scene)
    return dict(molecule=molecule, blend=molecule + ".blend", sidecar=molecule + ".cbq", views=rows,
                scientific_arrays_unchanged=True, saved_reopened=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "examples/scientific-visualization/output/molecular/scenes")
    parser.add_argument("--verify", action="store_true", help="reopen the published workbenches without saving")
    arguments = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
    assert bpy.app.background and ROOT / ".agents/cache" in private.parents
    destination = arguments.output.resolve()
    if arguments.verify:
        verify_published(destination)
        return
    if destination.exists():
        raise FileExistsError("workbench output must be a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    renders = json.loads((destination.parent / "images/render-manifest.json").read_text(encoding="utf-8"))
    bpy.context.preferences.filepaths.save_version = 0
    session_ui.register()
    try:
        with staging_directory(destination.parent, ".molecular-scenes-") as staging:
            entries = [build(molecule, staging, renders) for molecule in ("water", "ch3", "nitrogen")]
            for entry in entries:
                entry["blend_sha256"] = digest(staging / entry["blend"])
            (staging / "scene-manifest.json").write_text(json.dumps({"schema_version": 1, "scenes": entries},
                                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if destination.exists():
                raise FileExistsError("workbench output appeared during preparation")
            os.rename(staging, destination)
        print("MOLECULAR_SCENES_PUBLISHED", destination, flush=True)
    finally:
        session_ui.unregister()


def verify_published(destination):
    entries = json.loads((destination / "scene-manifest.json").read_text(encoding="utf-8"))["scenes"]
    session_ui.register()
    try:
        for entry in entries:
            original = open_project(SOURCE / entry["sidecar"])
            try:
                expected = array_hashes(original)
            finally:
                close_project(original)
            path = destination / entry["blend"]
            assert digest(path) == entry["blend_sha256"]
            bpy.ops.wm.open_mainfile(filepath=str(path))
            session = session_ui.get_scene_session(bpy.context.scene)
            assert session.link_status == "connected", session_ui.get_scene_session_status(bpy.context.scene)
            assert session.sidecar_path.resolve() == (destination / entry["sidecar"]).resolve()
            assert array_hashes(session.project) == expected
            for row in entry["views"]:
                obj = bpy.data.objects[row["name"]]
                assert scene_plan_from_view(obj, session.project).render_identity == row["render_identity"]
                assert obj["cb_view_instance_id"] == row["instance_id"]
            for obj in bpy.data.objects:
                if obj.type == "VOLUME":
                    cache_path = Path(bpy.path.abspath(obj.data.filepath)).resolve()
                    assert cache_path.is_file() and session.sidecar_path.resolve() in cache_path.parents
            print("MOLECULAR_REOPEN_VERIFIED", entry["molecule"], len(entry["views"]), flush=True)
            session_ui.close_scene_session(bpy.context.scene)
    finally:
        session_ui.unregister()


if __name__ == "__main__":
    main()
