"""Build and cold-reopen current tutorial Views from fixed CBQ projects."""

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys

import bpy


ROOT = Path(__file__).resolve().parents[1]
KEY = "bl_ext.user_default.chemblender"
parser = argparse.ArgumentParser()
parser.add_argument("--phase", choices=("build", "cold"), required=True)
parser.add_argument("--spec", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
spec = json.loads(args.spec.resolve(strict=True).read_text(encoding="utf-8"))
output = args.output.resolve(strict=True)
profile = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve(strict=True)
assert output.is_relative_to(ROOT / ".blend-analysis")
assert profile.is_relative_to(ROOT / ".blend-analysis")
assert KEY in bpy.context.preferences.addons

session_ui = importlib.import_module(KEY + ".ui.session")
view_cache = importlib.import_module(KEY + ".ui.view_cache")
scene_view = importlib.import_module(KEY + ".scene_preset_view")
render_scene = importlib.import_module(KEY + ".render_scene")
presets = importlib.import_module(KEY + "._cbq_core.scene_preset")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hashes(path):
    path = Path(path)
    return {item.relative_to(path).as_posix(): digest(item)
            for item in sorted(path.rglob("*")) if item.is_file()}


def entity(project, selector):
    matches = []
    for registry_name in ("structures", "datasets", "topologies"):
        for value in getattr(project, registry_name, {}).values():
            if type(value).__name__ != selector["type"]:
                continue
            role = selector.get("semantic_role")
            if role is None or getattr(value, "semantic_role", None) == role:
                matches.append(value)
    index = selector.get("index", 0)
    assert len(matches) > index, (selector, [type(item).__name__ for item in matches])
    return matches[index]


def plan(project, view):
    definition = presets.builtin_scene_presets()[view["preset"]]
    bindings = {name: entity(project, selector).id
                for name, selector in view["bindings"].items()}
    settings = dict(view.get("settings", {}))
    settings.setdefault("template", "research")
    return presets.plan_scene_preset(definition, project, bindings, settings)


def linked_structure(project, planned):
    for binding in planned.bindings:
        if binding.entity_kind == "structure":
            return project.structures[binding.entity_id]
        value = project.datasets.get(binding.entity_id)
        identity = getattr(value, "structure_id", None)
        if identity in project.structures:
            return project.structures[identity]
    return None


def clear_scene():
    session_ui.close_scene_session(bpy.context.scene)
    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def build_item(item):
    item_dir = output / item["name"]
    item_dir.mkdir()
    source = (ROOT / item["source"]).resolve(strict=True)
    imported = item_dir / "import-source.cbq"
    shutil.copytree(source, imported)
    scene = bpy.context.scene
    scene.chemblender_cbq.input_path = str(imported)
    assert bpy.ops.chemblender.preview_cbq() == {"FINISHED"}
    assert bpy.ops.chemblender.import_cbq() == {"FINISHED"}
    session = session_ui.get_scene_session(scene)
    blend = item_dir / "project.blend"
    assert bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=False) == {"FINISHED"}
    cache = view_cache._durable_cache_root(session.sidecar_path)
    views = []
    for index, definition in enumerate(item["views"]):
        planned = plan(session.project, definition)
        objects = scene_view.apply_scene_preset(
            planned, session.project, collection=scene.collection, cache_root=cache
        )
        root = objects[0]
        root.name = f"{item['name']}-{index + 1:02d}-{planned.view_kind}"
        root.location.x += index * 4.0
        session.mark_dirty("view_cache")
        render = item_dir / f"render-{index + 1:02d}-{planned.view_kind}.png"
        with render_scene.RenderScope(
            bpy.context, session.project, linked_structure(session.project, planned),
            template="research", width=960, height=720, samples=16,
        ) as renderer:
            render_document = renderer.render(
                planned, render, item_dir / "render-cache"
            )
        views.append({
            "root": root.name,
            "view_kind": planned.view_kind,
            "render": render.name,
            "render_sha256": digest(render),
            "bindings": {binding.name: str(binding.entity_id) for binding in planned.bindings},
            "render_document": render_document,
        })
    assert bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=False) == {"FINISHED"}
    unavailable = item_dir / "source-unavailable.cbq"
    shutil.move(str(imported), str(unavailable))
    receipt = {
        "case_id": item["case_id"],
        "item": item["name"],
        "source": item["source"],
        "source_unavailable": unavailable.name,
        "project_id": str(session.project.id),
        "blend_sha256": digest(blend),
        "sidecar_files": tree_hashes(item_dir / "project.cbq"),
        "views": views,
    }
    (item_dir / "build.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    clear_scene()
    return receipt


def cold_item(item):
    item_dir = output / item["name"]
    build = json.loads((item_dir / "build.json").read_text(encoding="utf-8"))
    before = tree_hashes(item_dir / "project.cbq")
    assert not (item_dir / "import-source.cbq").exists()
    assert (item_dir / build["source_unavailable"]).is_dir()
    assert bpy.ops.wm.open_mainfile(filepath=str(item_dir / "project.blend")) == {"FINISHED"}
    session = session_ui.get_scene_session(bpy.context.scene)
    assert str(session.project.id) == build["project_id"]
    assert session_ui.get_scene_session_status(bpy.context.scene)[0] == "connected"
    rebuilt = []
    for view in build["views"]:
        root = bpy.data.objects[view["root"]]
        bpy.ops.object.select_all(action="DESELECT")
        root.select_set(True)
        bpy.context.view_layer.objects.active = root
        assert bpy.ops.chemblender.scientific_view(action="REBUILD") == {"FINISHED"}
        rebuilt.append(view["root"])
    assert bpy.ops.wm.save_as_mainfile(
        filepath=str(item_dir / "cold-project.blend"), check_existing=False
    ) == {"FINISHED"}
    after = tree_hashes(item_dir / "cold-project.cbq")
    assert {name: value for name, value in before.items() if name.startswith("arrays/")} == {
        name: value for name, value in after.items() if name.startswith("arrays/")
    }
    result = {
        "case_id": item["case_id"],
        "item": item["name"],
        "status": "passed",
        "project_id": build["project_id"],
        "source_unavailable": True,
        "processor_required": False,
        "rebuilt_views": rebuilt,
        "scientific_array_hashes_preserved": True,
        "cold_blend_sha256": digest(item_dir / "cold-project.blend"),
    }
    clear_scene()
    return result


results = [build_item(item) if args.phase == "build" else cold_item(item)
           for item in spec["items"]]
(output / f"{args.phase}-summary.json").write_text(
    json.dumps({"status": "passed", "phase": args.phase, "items": results},
               indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print("TUTORIAL_VIEWER_BATCH_PASSED", args.phase, len(results), flush=True)
