"""Real molecule Save As/move/public rebuild checks on private cache copies only.

Run in Blender 5.1.1 background with private BLENDER_USER_RESOURCES; pass
--existing-libraries for an existing compatible RDKit/Gemmi directory. No install.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

import bpy
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".agents/cache"
FORMAL = ROOT / "examples/scientific-visualization/output/molecular/scenes"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples/scientific-visualization"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_hashes(directory, pattern="*"):
    return {str(path.relative_to(directory)): digest(path)
            for path in directory.rglob(pattern) if path.is_file()}


def private_path(path):
    path = path.resolve()
    if CACHE not in path.parents or path.is_symlink():
        raise ValueError("lifecycle mutations require a local repository cache path")
    return path


def roots():
    return {obj["cb_view_instance_id"]: obj for obj in bpy.context.scene.objects
            if obj.get("cb_view_root") is True}


def view_snapshot(project):
    from cbq_core.scene_preset import scene_plan_document
    from ChemBlender.scene_preset_view import scene_view_objects
    from ChemBlender.ui.view_cache import scene_plan_from_view

    result = {}
    for identity, obj in roots().items():
        plan = scene_plan_from_view(obj, project)
        result[identity] = {"name": obj.name, "plan": scene_plan_document(plan),
                            "matrix": [list(row) for row in obj.matrix_world],
                            "hide_render": obj.hide_render, "hide_viewport": obj.hide_viewport,
                            "components": len(scene_view_objects(obj))}
    assert result and len(result) == len(set(result))
    return result


def assert_views(project, expected):
    current = view_snapshot(project)
    assert current.keys() == expected.keys(), "View instances changed"
    for identity, row in current.items():
        original = expected[identity]
        np.testing.assert_allclose(row["matrix"], original["matrix"], rtol=0, atol=2e-6)
        assert {k: v for k, v in row.items() if k != "matrix"} == {
            k: v for k, v in original.items() if k != "matrix"}, (identity, row, original)


def assert_cache(sidecar):
    paths = set()
    for obj in bpy.context.scene.objects:
        if obj.type == "VOLUME":
            path = Path(bpy.path.abspath(obj.data.filepath)).resolve()
            assert sidecar / "cache/render" in path.parents, path
            assert path.is_file(), path
            paths.add(path)
    assert paths
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--existing-libraries", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    profile = private_path(Path(os.environ["BLENDER_USER_RESOURCES"]))
    assert bpy.app.background and bpy.app.version >= (5, 1, 0)
    profile.mkdir(parents=True, exist_ok=True)
    libraries = args.existing_libraries.resolve(strict=True)
    assert CACHE in libraries.parents, "use previously qualified private dependencies"
    sys.path.append(str(libraries))
    destination = private_path(args.output or CACHE / ("molecular-lifecycle-" + uuid4().hex))
    if destination.exists():
        raise FileExistsError("lifecycle output must be a new directory")
    destination.mkdir(parents=True)
    original_hashes = file_hashes(FORMAL)
    entries = json.loads((FORMAL / "scene-manifest.json").read_text(encoding="utf-8"))["scenes"]
    report = {"status": "running", "blender": bpy.app.version_string,
              "profile": str(profile), "source": str(FORMAL), "scenes": []}
    report_path = destination / "verification.json"

    import ChemBlender
    from cbq_core.sidecar import close_project
    from cbq_core.sidecar import open_project
    from ChemBlender.ui import session as session_ui
    from render_molecular import array_hashes

    assert Path(ChemBlender.__file__).resolve() == ROOT / "ChemBlender/__init__.py"
    bpy.context.preferences.filepaths.save_version = 0
    ChemBlender.register()
    try:
        assert hasattr(bpy.types.Scene, "chemblender_scientific_view")
        for entry in entries:
            molecule = entry["molecule"]
            copied = destination / (molecule + "-copy")
            copied.mkdir()
            blend = copied / entry["blend"]
            sidecar = copied / entry["sidecar"]
            shutil.copyfile(FORMAL / entry["blend"], blend)
            shutil.copytree(FORMAL / entry["sidecar"], sidecar)
            disk_arrays = file_hashes(sidecar, "*.npy")
            assert disk_arrays
            source = open_project(sidecar)
            try:
                scientific = array_hashes(source)
            finally:
                close_project(source)
            bpy.ops.wm.open_mainfile(filepath=str(blend))
            session = session_ui.get_scene_session(bpy.context.scene)
            assert session.sidecar_path.resolve() == sidecar
            assert session.link_status == "connected" and array_hashes(session.project) == scientific
            expected = view_snapshot(session.project)
            quantity_ids = {obj["cb_view_instance_id"] for row in entry["views"]
                            for obj in (bpy.data.objects[row["name"]],)}
            assert len(quantity_ids) == len(entry["views"])
            for row in entry["views"]:
                obj = bpy.data.objects[row["name"]]
                assert obj["cb_view_instance_id"] == row["instance_id"]
                assert obj["cb_scene_render_identity"] == row["render_identity"]
            assert_cache(sidecar)

            saved = copied / "save-as"
            saved.mkdir()
            new_blend = saved / (molecule + "-copy.blend")
            # Exercise Blender's default relative_remap=True across directories.
            assert bpy.ops.wm.save_as_mainfile(filepath=str(new_blend), check_existing=False) == {"FINISHED"}
            new_sidecar = new_blend.with_suffix(".cbq")
            assert session.sidecar_path.resolve() == new_sidecar
            assert array_hashes(session.project) == scientific
            assert file_hashes(new_sidecar, "*.npy") == disk_arrays
            assert_views(session.project, expected)
            assert_cache(new_sidecar)
            print("MOLECULAR_SAVE_AS_PASSED", molecule, len(quantity_ids), flush=True)

            # Close scientific maps and unload VDB handles before moving this
            # explicitly checked cache directory on Windows.
            for obj in bpy.context.scene.objects:
                if obj.type == "VOLUME":
                    obj.data.grids.unload()
            session_ui.close_scene_session(bpy.context.scene)
            moved = private_path(destination / (molecule + "-moved"))
            assert saved.resolve().parent == copied.resolve() and destination in saved.resolve().parents
            os.rename(saved, moved)
            moved_blend = moved / new_blend.name
            moved_sidecar = moved_blend.with_suffix(".cbq")
            bpy.ops.wm.open_mainfile(filepath=str(moved_blend))
            session = session_ui.get_scene_session(bpy.context.scene)
            assert session.link_status == "connected" and session.sidecar_path.resolve() == moved_sidecar
            assert array_hashes(session.project) == scientific
            assert file_hashes(moved_sidecar, "*.npy") == disk_arrays
            assert_views(session.project, expected)
            assert_cache(moved_sidecar)
            print("MOLECULAR_DIRECTORY_MOVE_PASSED", molecule, flush=True)

            for obj in bpy.context.scene.objects:
                if obj.type == "VOLUME":
                    obj.data.grids.unload()
            render_cache = private_path(moved_sidecar / "cache/render")
            deleted = sorted(render_cache.rglob("*.vdb"))
            assert deleted
            for path in deleted:
                assert render_cache in path.resolve().parents and not path.is_symlink()
                path.unlink()
            assert not tuple(render_cache.rglob("*.vdb"))
            assert file_hashes(moved_sidecar, "*.npy") == disk_arrays
            for identity in sorted(quantity_ids):
                obj = roots()[identity]
                for selected in tuple(bpy.context.selected_objects):
                    selected.select_set(False)
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                session.active_view_object_name = obj.name
                assert bpy.ops.chemblender.scientific_view(action="LOAD") == {"FINISHED"}
                settings = bpy.context.scene.chemblender_scientific_view
                saved_settings = dict(expected[identity]["plan"]["settings"])
                assert settings.template == saved_settings["template"]
                assert settings.shaded == saved_settings["shaded"]
                assert bpy.ops.chemblender.scientific_view(action="REBUILD") == {"FINISHED"}
                assert not roots()[identity].get("cb_view_stale", False)
                assert array_hashes(session.project) == scientific
                assert_views(session.project, expected)
            assert_cache(moved_sidecar)
            assert file_hashes(moved_sidecar, "*.npy") == disk_arrays
            assert bpy.ops.wm.save_as_mainfile(filepath=str(moved_blend), check_existing=False) == {"FINISHED"}
            bpy.ops.wm.open_mainfile(filepath=str(moved_blend))
            session = session_ui.get_scene_session(bpy.context.scene)
            assert array_hashes(session.project) == scientific
            assert_views(session.project, expected)
            assert_cache(moved_sidecar)
            assert file_hashes(moved_sidecar, "*.npy") == disk_arrays
            report["scenes"].append({"molecule": molecule, "quantity_views": len(quantity_ids),
                "total_views": len(expected), "removed_vdb_files": len(deleted),
                "array_files": len(disk_arrays), "instance_ids": sorted(quantity_ids),
                "save_as": "Passed", "move": "Passed", "public_rebuild": "Passed",
                "reopen": "Passed", "scientific_arrays": "unchanged"})
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            session_ui.close_scene_session(bpy.context.scene)
            print("MOLECULAR_PUBLIC_REBUILD_PASSED", molecule, len(quantity_ids), flush=True)
        report["status"] = "Passed"
    except BaseException as error:
        report.update(status="Failed", error=repr(error))
        raise
    finally:
        ChemBlender.unregister()
        assert not hasattr(bpy.types.Scene, "chemblender_scientific_view")
        assert file_hashes(FORMAL) == original_hashes, "formal examples changed"
        report["formal_examples_unchanged"] = True
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("MOLECULAR_LIFECYCLE_PASSED", report_path, flush=True)


if __name__ == "__main__":
    main()
