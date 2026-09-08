"""Private native Save As checks for current and unrelated scientific Views."""

import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
assert private.is_relative_to(ROOT / ".agents/cache")
output = private / ("ownership-" + uuid4().hex)
output.mkdir(parents=True)

import ChemBlender
from ChemBlender.core import builtin_scene_presets, plan_scene_preset
from ChemBlender.core.formats.mol2 import parse_mol2
from ChemBlender.core.formats.pdb import parse_pdb
from ChemBlender.scene_preset_view import apply_scene_preset, scene_view_objects
from ChemBlender.ui import session as session_ui


def array_hashes(sidecar):
    return {str(path.relative_to(sidecar)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sidecar.rglob("*.npy")}


def find_root(identity):
    return next(obj for obj in bpy.context.scene.objects
                if obj.get("cb_view_root") is True and obj.get("cb_view_instance_id") == identity)


def create(batch):
    session = session_ui.new_scene_session(bpy.context.scene)
    session.project.commit(batch)
    session.mark_dirty("import")
    plan = plan_scene_preset(builtin_scene_presets()["structure_publication"],
        session.project, {"structure": batch.structures[0].id}, {})
    root = apply_scene_preset(plan, session.project)[0]
    assert all(obj["cb_scene_project_id"] == str(session.project.id)
               for obj in scene_view_objects(root))
    return session, root


ChemBlender.register()
try:
    first, old = create(parse_pdb(ROOT / "tests/fixtures/pdb/altloc.pdb"))
    old_identity = old["cb_view_instance_id"]
    old_project = str(first.project.id)
    # Legacy .blend Views acquire ownership only after successful validation.
    del old["cb_scene_project_id"]
    first_file = output / "first.blend"
    assert bpy.ops.wm.save_as_mainfile(filepath=str(first_file), check_existing=False) == {"FINISHED"}
    assert not first.dirty and old["cb_scene_project_id"] == old_project
    first_hashes = array_hashes(first_file.with_suffix(".cbq"))
    assert first_hashes
    assert bpy.ops.wm.open_mainfile(filepath=str(first_file)) == {"FINISHED"}

    current, view = create(parse_mol2(ROOT / "tests/fixtures/mol2/substructure.mol2"))
    current_identity = view["cb_view_instance_id"]
    current_project = str(current.project.id)
    second_file = output / "second.blend"
    assert bpy.ops.wm.save_as_mainfile(filepath=str(second_file), check_existing=False) == {"FINISHED"}
    assert not current.dirty
    old = find_root(old_identity)
    assert old["cb_view_stale"] and not old["cb_report_eligible"]
    assert "source project" in old["cb_view_diagnostic"]
    assert old["cb_scene_project_id"] == old_project
    assert view["cb_scene_project_id"] == current_project
    assert array_hashes(first_file.with_suffix(".cbq")) == first_hashes
    current_hashes = array_hashes(second_file.with_suffix(".cbq"))
    assert bpy.ops.wm.open_mainfile(filepath=str(second_file)) == {"FINISHED"}
    current = session_ui.get_scene_session(bpy.context.scene)
    assert not current.dirty
    assert find_root(old_identity)["cb_view_stale"]
    view = find_root(current_identity)

    # A damaged binding in the current project remains a strict retry error.
    saved_bindings = view["cb_scene_bindings_json"]
    changed = json.loads(saved_bindings)
    changed["structure"]["revision"] = "damaged-current-binding"
    view["cb_scene_bindings_json"] = json.dumps(changed)
    assert bpy.ops.wm.save_mainfile() == {"FINISHED"}
    assert current.dirty_reasons == frozenset({"view_cache"})
    assert view["cb_view_stale"]
    assert array_hashes(second_file.with_suffix(".cbq")) == current_hashes
    view["cb_scene_bindings_json"] = saved_bindings
    bpy.ops.object.select_all(action="DESELECT")
    view.select_set(True)
    bpy.context.view_layer.objects.active = view
    assert bpy.ops.chemblender.scientific_view(action="REBUILD") == {"FINISHED"}
    assert find_root(current_identity)["cb_scene_project_id"] == current_project
    assert bpy.ops.wm.save_mainfile() == {"FINISHED"}
    assert not current.dirty
    assert array_hashes(second_file.with_suffix(".cbq")) == current_hashes
    print("VIEW_PROJECT_OWNERSHIP_PASSED: legacy validation, foreign diagnostics, Save As/reopen, current failure, public rebuild, unchanged arrays")
finally:
    ChemBlender.unregister()
