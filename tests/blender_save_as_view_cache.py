"""Native Save As remapping and relocated-pair recovery with a private profile."""

import argparse
import hashlib
import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import bpy
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument("--existing-libraries", required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
assert bpy.app.background and os.environ.get("BLENDER_USER_RESOURCES"), "use a private background profile"
sys.path.append(args.existing_libraries)

import ChemBlender
from cbq_core.model import ArrayData
from cbq_core.model import ImportBatch
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import plan_scene_preset
from ChemBlender.scene_preset_view import apply_scene_preset
from ChemBlender.ui.session import get_scene_session, get_scene_session_status, close_scene_session
from tests.test_view_cache_persistence import grid


def arrays(sidecar):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (sidecar / "arrays").glob("*.npy")}


def check_paths(blend_path, *, relative):
    session = get_scene_session(bpy.context.scene)
    assert get_scene_session_status(bpy.context.scene) == ("connected", "")
    assert session.sidecar_path == blend_path.with_suffix(".cbq")
    volumes = [obj for obj in bpy.data.objects if obj.type == "VOLUME" and obj.get("cb_scene_preset_id")]
    assert len(volumes) == 4
    for obj in volumes:
        assert obj.data.filepath.startswith("//") == relative, obj.data.filepath
        path = Path(bpy.path.abspath(obj.data.filepath)).resolve()
        assert path.is_file(), str(path)
        assert path.is_relative_to(session.sidecar_path / "cache" / "render"), str(path)
        assert Path(obj["cb_cache_path"]) == path
        assert not obj.get("cb_view_stale")
    return arrays(session.sidecar_path)


ChemBlender.register()
try:
    with TemporaryDirectory(prefix="cb-save-as-cache-") as temporary:
        root = Path(temporary)
        session = get_scene_session(bpy.context.scene)
        density = grid()
        orbitals = replace(density, id=uuid4(), revision="mo", semantic_role="molecular_orbital",
            data=ArrayData(numpy.asarray(density.data.values) - 13., density.data.dims,
                           "inverse_bohr_to_three_halves"))
        potential = replace(density, id=uuid4(), revision="esp", semantic_role="electrostatic_potential",
            data=ArrayData(numpy.asarray(density.data.values) / 100., density.data.dims,
                           "hartree_per_elementary_charge"))
        session.project.commit(ImportBatch(datasets=(density, orbitals, potential)))
        session.mark_dirty("import")
        cache_root = session.temporary_root / "view-cache"
        cache_root.mkdir()
        for preset_id, bindings, settings in (
            ("grid_volume", {"grid": density.id}, {}),
            ("signed_isosurface", {"grid": orbitals.id}, {"isovalue": .05}),
            ("property_on_surface", {"surface_grid": density.id, "property_grid": potential.id},
             {"surface_isovalue": .05}),
        ):
            plan = plan_scene_preset(builtin_scene_presets()[preset_id], session.project, bindings, settings)
            apply_scene_preset(plan, session.project, cache_root=cache_root)
        original = root / "original.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(original), check_existing=False)
        expected_arrays = check_paths(original, relative=True)
        assert expected_arrays
        for remap in (True, False):
            destination = root / str(remap).lower() / "copy.blend"
            destination.parent.mkdir()
            bpy.ops.wm.save_as_mainfile(filepath=str(destination), check_existing=False, relative_remap=remap)
            assert check_paths(destination, relative=False) == expected_arrays
            # Inspect the serialized RNA in a reopened file, then let load_post
            # resolve caches relative to that file's actual sidecar.
            bpy.ops.wm.open_mainfile(filepath=str(destination))
            assert check_paths(destination, relative=True) == expected_arrays
        relocated = root / "relocated" / "copy.blend"
        relocated.parent.mkdir()
        shutil.copy2(destination, relocated)
        shutil.copytree(destination.with_suffix(".cbq"), relocated.with_suffix(".cbq"))
        bpy.ops.wm.open_mainfile(filepath=str(relocated))
        assert check_paths(relocated, relative=True) == expected_arrays
        # Release our own maps before TemporaryDirectory removes the test pair.
        for obj in bpy.data.objects:
            if obj.type == "VOLUME":
                obj.data.grids.unload()
        close_scene_session(bpy.context.scene)
    print(json.dumps({"save_as_relative_remap_true": "passed", "save_as_relative_remap_false": "passed",
                      "reopen_relative_cache": "passed", "relocated_pair": "passed",
                      "scientific_array_hashes": "unchanged"}))
finally:
    ChemBlender.unregister()
