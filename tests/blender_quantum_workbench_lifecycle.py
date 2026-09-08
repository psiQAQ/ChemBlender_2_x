"""Replay the real water example in separate background Blender processes."""

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import bpy
import numpy as np  # Keep Blender's bundled NumPy before appending existing wheels.
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "quantum-workbench"
SOURCE = ROOT / "submodules" / "iodata" / "iodata" / "test" / "data" / "water_sto3g_hf_g03.fchk"
SOURCE_SHA256 = "aa8dec77849d4f9e1e9dc9357c80f5b4d6ba1efc3bbc17da6c59754bdaed0816"
IODATA_SHA = "adab5813713ba64641565eb2a8c11803a4e9bba6"
GRID = {"origin": (-6.13, -5.87, -6.07), "spacing": .28, "shape": (45, 45, 45)}

arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--phase", choices=("build", "refresh", "reopen", "save-as", "recover", "render", "export"), required=True)
parser.add_argument("--output", type=Path, default=EXAMPLE / "output")
parser.add_argument("--worker-python", type=Path, default=ROOT / ".agents/cache/gbasis-py312/Scripts/python.exe")
parser.add_argument("--existing-libraries", default="C:/Users/ustcw/AppData/Roaming/Blender Foundation/Blender/5.1/extensions/.local/lib/python3.13/site-packages")
args = parser.parse_args(arguments)
assert bpy.app.background, "the example must run in an independent background Blender"
sys.path.insert(0, str(ROOT))
sys.path.append(args.existing_libraries)

import ChemBlender
from ChemBlender.core import builtin_scene_presets, plan_scene_preset
from ChemBlender.core.grid_sampling import export_grid_sample
from ChemBlender.scene_preset_view import _remove_objects, apply_scene_preset
from ChemBlender.ui import session as session_ui
from ChemBlender.ui.view_cache import _durable_cache_root, plan_grid_sample_view


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, document):
    Path(path).write_text(json.dumps(document, ensure_ascii=False, allow_nan=False,
                                    sort_keys=True, indent=2) + "\n", encoding="utf-8")


def array_hashes(sidecar):
    result = {path.name: digest(path) for path in sorted((Path(sidecar) / "arrays").glob("*.npy"))}
    assert result, "scientific arrays are missing"
    return result


def view_metadata():
    keys = ("cb_scene_preset_id", "cb_scene_preset_version", "cb_scene_render_identity",
            "cb_scene_settings_json", "cb_scene_bindings_json")
    return {obj.name: {key: obj[key] for key in keys}
            for obj in bpy.context.scene.objects if obj.get("cb_scene_preset_id")}


def display_metadata():
    scene = bpy.context.scene
    return {
        "coordinate_unit": "angstrom",
        "cameras": {obj.name: {"matrix_world": [list(row) for row in obj.matrix_world],
                                "type": obj.data.type, "ortho_scale": obj.data.ortho_scale}
                    for obj in scene.objects if obj.type == "CAMERA"},
        "view_root_transforms": {obj.name: [list(row) for row in obj.matrix_world]
                                 for obj in scene.objects
                                 if obj.get("cb_scene_preset_id") and obj.parent is None},
    }


def label(body, location, size=.24, color=(.87, .92, 1., 1.)):
    data = bpy.data.curves.new("Example label", "FONT")
    data.body, data.size = body, size
    obj = bpy.data.objects.new(body, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    material = bpy.data.materials.get("Example label emission")
    if material is None:
        material = bpy.data.materials.new("Example label emission")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Color"].default_value = color
        material.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
    data.materials.append(material)
    return obj


def camera(name, position, target, ortho):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = position
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    data.type, data.ortho_scale, data.lens = "ORTHO", ortho, 50
    return obj


def stage():
    scene = bpy.context.scene
    for obj in tuple(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (.025, .035, .055, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = .7
    for name, position, power, size in (
        ("Example Key", (0, 5, 12), 400, 10),
        ("Example Fill", (-8, -4, 8), 300, 8),
        ("Example Rim", (8, 2, 6), 250, 6),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size = power, "DISK", size
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = position
        obj.rotation_euler = (-obj.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera("Workbench Overview Camera", (0, 0, 28), (0, 0, 0), 19.5)
    camera("Orbital Export Camera", (4, -7, 5), (.3, 0, .2), 7.8)
    scene.render.engine = "CYCLES"
    scene.cycles.device, scene.cycles.samples, scene.cycles.use_denoising = "CPU", 24, True
    scene.render.resolution_x, scene.render.resolution_y = 1800, 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    bpy.context.preferences.filepaths.save_version = 0


def compute(session, operation, source, name, *, orbital_number=None):
    settings = bpy.context.scene.chemblender_wavefunction
    if orbital_number is not None:
        settings.orbital_number = orbital_number
    before = set(session.project.datasets)
    result = bpy.ops.chemblender.wavefunction(action="compute", operation_id=operation, source_id=str(source.id))
    assert result == {"FINISHED"}, (name, result)
    created = set(session.project.datasets) - before
    assert len(created) == 1
    grid = session.project.datasets[created.pop()]
    assert grid.status.value == "complete" and np.isfinite(grid.data.values).all()
    print("EXAMPLE_COMPUTED", name, grid.data.shape, flush=True)
    return grid


def apply(session, preset, bindings, settings, cache, name, transform=None):
    plan = plan_scene_preset(builtin_scene_presets()[preset], session.project, bindings, settings)
    objects = apply_scene_preset(plan, session.project, collection=bpy.context.scene.collection, cache_root=cache)
    for index, obj in enumerate(objects):
        obj.name = f"{name} {index + 1:02d}"
        if transform is not None and obj.parent is None:
            obj.matrix_world = transform
    session.mark_dirty("view_cache")
    return objects


def overview(session, fields):
    stage()
    cache = _durable_cache_root(session.sidecar_path)
    structure = next(iter(session.project.structures.values()))
    rotation = Matrix.Rotation(math.radians(55), 4, "X") @ Matrix.Rotation(math.radians(15), 4, "Y")
    for name, grid_name, center in (("HOMO 5", "homo", (-6, 3, 0)),
                                    ("LUMO 6", "lumo", (0, 3, 0))):
        transform = Matrix.Translation(center) @ rotation
        apply(session, "signed_isosurface", {"grid": fields[grid_name].id},
              {"isovalue": .04}, cache, name, transform)
        apply(session, "structure_publication", {"structure": structure.id}, {}, None, name + " atoms", transform)
        label(name, (center[0] - 2.2, 5.4, 0), .35)
        label("phase: blue (+) / red (-)", (center[0] - 2.2, .8, 0), .19)
    transform = Matrix.Translation((6, 3, 0)) @ rotation
    apply(session, "property_on_surface", {"surface_grid": fields["density"].id, "property_grid": fields["esp"].id},
          {"surface_isovalue": .03, "color_min": -.1, "color_max": .1}, cache, "ESP on density", transform)
    apply(session, "structure_publication", {"structure": structure.id}, {}, None, "ESP atoms", transform)
    label("ESP on electron density", (3.6, 5.4, 0), .30)
    apply(session, "grid_colorbar", {"grid": fields["esp"].id},
          {"color_min": -.1, "color_max": .1, "width": 3.5, "height": .25},
          None, "ESP colorbar", Matrix.Translation((4.25, .9, 0)))
    slice_settings = {"origin": (-4.5, .13, -4.5), "u_vector": (9., 0., 0.),
                      "v_vector": (0., 0., 9.), "counts": (97, 97),
                      "color_min": -.3, "color_max": .3}
    apply(session, "grid_slice", {"grid": fields["esp"].id}, slice_settings, None, "ESP slice",
          Matrix.Translation((-6, -3, 0)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    label("ESP plane at y = 0.13 bohr", (-8.3, -.4, 0), .27)
    profile_settings = {"start": (-4.5, .35, .2), "end": (4.5, .35, .2),
                        "sample_count": 181, "radius": .012}
    apply(session, "grid_profile", {"grid": fields["esp"].id}, profile_settings, None,
          "ESP profile", Matrix.Translation((2.6, -1.8, 0)))
    label("ESP along x", (.2, -.4, 0), .30)
    # Keep native labels and graph lines readable independently of surface lighting.
    text_material = bpy.data.materials["Example label emission"]
    for obj in bpy.context.scene.objects:
        if obj.type in {"FONT", "CURVE"} and not obj.data.materials:
            obj.data.materials.append(text_material)
    label("H2O  |  RHF / STO-3G", (5.35, -4.25, 0), .27)
    label("10 electrons; neutral singlet\nGrid spacing 0.28 bohr\nVisualization grid; no convergence claim",
          (5.35, -5.0, 0), .17)
    label("ChemBlender quantum workbench", (-8.4, 6.05, 0), .27)


def scientific_csv(session, output):
    result = {}
    for root in tuple(bpy.context.scene.objects):
        if root.get("cb_grid_sample_root") and root.get("cb_scene_preset_id") in {"grid_slice", "grid_profile"}:
            plan = plan_grid_sample_view(root, session.project)
            grid = session.project.datasets[plan.bindings[0].entity_id]
            kind = "plane" if plan.view_kind == "grid_slice" else "profile"
            path = output / f"{kind}.csv"
            export_grid_sample(path, grid, kind=kind, settings=dict(plan.settings))
            original = path.read_bytes()
            transform = root.matrix_world.copy()
            root.location += Vector((7., -3., 2.))
            bpy.context.view_layer.update()
            export_grid_sample(path, grid, kind=kind, settings=dict(plan.settings))
            assert path.read_bytes() == original, "display transform changed scientific CSV"
            root.matrix_world = transform
            result[path.name] = digest(path)
    assert set(result) == {"plane.csv", "profile.csv"}
    return result


def save(path):
    assert bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False) == {"FINISHED"}
    status, message = session_ui.get_scene_session_status(bpy.context.scene)
    assert status == "connected", message
    session = session_ui.get_scene_session(bpy.context.scene)
    assert session.sidecar_path.resolve() == path.with_suffix(".cbq").resolve()
    assert not session.dirty, session.dirty_reasons
    return session


def verify(session, manifest, sidecar):
    assert str(session.project.id) == manifest["project_id"]
    assert array_hashes(sidecar) == manifest["scientific_array_sha256"]
    assert view_metadata() == manifest["views"], "persistent View parameters changed"
    for name, field in manifest["fields"].items():
        grid = session.project.datasets[UUID(field["id"])]
        assert grid.revision == field["revision"] and np.isfinite(np.asarray(grid.data.values)).all(), name
    for obj in bpy.context.scene.objects:
        if obj.get("cb_scene_preset_id") == "property_on_surface":
            assert obj["cb_scene_preset_version"] == "2"
            group = next(mod.node_group for mod in obj.modifiers
                         if mod.type == "NODES" and mod.node_group is not None
                         and mod.node_group.get("cbq_contract") == "property_surface_v2")
            mesh = next(node for node in group.nodes if node.bl_idname == "GeometryNodeGridToMesh")
            assert mesh.inputs["Grid"].links[0].from_node.inputs["Name"].default_value == "density"
            assert not any(node.bl_idname == "GeometryNodeVolumeToMesh" for node in group.nodes)
        if obj.get("cb_cache_path"):
            cache = Path(bpy.path.abspath(obj.data.filepath)).resolve()
            assert cache.is_file() and sidecar.resolve() in cache.parents, cache
    assert bpy.context.scene.camera.name == "Workbench Overview Camera"


def render(output):
    bpy.context.scene.camera = bpy.data.objects["Workbench Overview Camera"]
    bpy.context.scene.render.filepath = str(output / "overview.png")
    assert bpy.ops.render.render(write_still=True) == {"FINISHED"}


def refresh(session, manifest, output, blend):
    """Rebuild only this example's presentation from unchanged scientific fields."""
    _remove_objects(tuple(obj for obj in bpy.context.scene.objects if obj.get("cb_scene_preset_id")))
    fields = {name: session.project.datasets[UUID(value["id"])]
              for name, value in manifest["fields"].items()}
    overview(session, fields)
    assert scientific_csv(session, output) == manifest["csv_sha256"]
    session = save(blend)
    manifest["views"] = view_metadata()
    manifest["display"] = display_metadata()
    manifest["render"]["area_light_power_watts"] = [400, 300, 250]
    verify(session, manifest, session.sidecar_path)
    write_json(output / "provenance.json", manifest)
    render(output)
    return session


def build(output, blend):
    if blend.exists():
        raise RuntimeError("example already exists; use reopen/render/export phases to continue it")
    assert digest(SOURCE) == SOURCE_SHA256, "upstream input bytes changed"
    settings = bpy.context.scene.chemblender_wavefunction
    settings.worker_python, settings.worker_repository = str(args.worker_python), str(ROOT)
    assert bpy.ops.chemblender.import_wavefunction(filepath=str(SOURCE)) == {"FINISHED"}
    session = session_ui.get_scene_session(bpy.context.scene)
    orbitals = session.project.orbital_sets[session.active_entity_id]
    settings.orbital_source, settings.channel = str(orbitals.id), "restricted"
    settings.origin, settings.spacing, settings.shape = GRID["origin"], GRID["spacing"], GRID["shape"]
    charges = next(value for value in session.project.datasets.values() if value.semantic_role == "nuclear_charge")
    settings.nuclear_charge = str(charges.id)
    total = next(value for value in session.project.density_matrices.values() if value.spin_role.value == "total")
    fields = {
        "homo": compute(session, "wavefunction.mo_grid", orbitals, "HOMO 5", orbital_number=5),
        "lumo": compute(session, "wavefunction.mo_grid", orbitals, "LUMO 6", orbital_number=6),
        "density": compute(session, "wavefunction.density_matrix_grid", total, "electron density"),
        "esp": compute(session, "wavefunction.esp_grid", total, "ESP"),
    }
    session = save(blend)  # Publish arrays before creating durable render caches.
    overview(session, fields)
    csv_hashes = scientific_csv(session, output)
    session = save(blend)
    orbitals = session.project.orbital_sets[orbitals.id]
    version_code = "import json,importlib.metadata as m; print(json.dumps({n:m.version(n) for n in ('numpy','scipy','qc-iodata','qc-gbasis')}))"
    versions = json.loads(subprocess.check_output([str(args.worker_python), "-B", "-c", version_code], text=True))
    manifest = {
        "example": "water-quantum-workbench", "project_id": str(session.project.id),
        "source": {"path": str(SOURCE.relative_to(ROOT)), "sha256": SOURCE_SHA256,
                   "url": f"https://github.com/theochem/iodata/blob/{IODATA_SHA}/iodata/test/data/{SOURCE.name}",
                   "iodata_git_commit": IODATA_SHA, "upstream_license": "LGPL-3.0-or-later",
                   "license_path": "submodules/iodata/LICENSE.txt",
                   "original_program_version": None,
                   "filename_hint": "g03; the input does not declare an exact program version"},
        "method": {"wavefunction": "RHF", "basis": "STO-3G", "charge": 0, "multiplicity": 1,
                   "electron_count": 10, "density_source": "explicit total SCF AO density matrix",
                   "nuclear_charge_source": "explicit FCHK Nuclear charges record",
                   "orbitals_one_based": {"homo": 5, "lumo": 6},
                   "orbital_energies_hartree": np.asarray(orbitals.channels[0].energies.values).tolist(),
                   "convergence": "visualization grid; integration convergence not tested"},
        "software": {"blender": bpy.app.version_string, "blender_numpy": np.__version__,
                     "worker_python": str(args.worker_python), **versions},
        "grid": GRID, "fields": {name: {"id": str(value.id), "revision": value.revision,
                                          "unit": value.data.unit} for name, value in fields.items()},
        "scientific_array_sha256": array_hashes(session.sidecar_path), "views": view_metadata(),
        "display": display_metadata(),
        "csv_sha256": csv_hashes,
        "render": {"engine": bpy.context.scene.render.engine, "samples": 24,
                   "resolution": [1800, 1200], "view_transform": "Standard",
                   "area_light_power_watts": [400, 300, 250]},
    }
    write_json(output / "provenance.json", manifest)
    verify(session, manifest, session.sidecar_path)
    render(output)


def main():
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    blend = output / "water-workbench.blend"
    copied = output / "save-as" / "water-workbench-copy.blend"
    ChemBlender.register()
    try:
        if args.phase == "build":
            build(output, blend)
        else:
            manifest = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
            target = copied if args.phase == "recover" else blend
            deleted = []
            if args.phase == "recover":
                sidecar = copied.with_suffix(".cbq").resolve(strict=True)
                cache = sidecar / "cache" / "render"
                assert cache.resolve(strict=True) == cache and sidecar in cache.parents
                assert not any(path.is_symlink() or path.is_junction() for path in (sidecar, cache.parent, cache))
                assert array_hashes(sidecar) == manifest["scientific_array_sha256"]
                deleted = [str(path.relative_to(sidecar)) for path in cache.rglob("*") if path.is_file()]
                shutil.rmtree(cache)  # Only verified generated cache/render; never arrays/.
            assert bpy.ops.wm.open_mainfile(filepath=str(target)) == {"FINISHED"}
            session = session_ui.get_scene_session(bpy.context.scene)
            status, message = session_ui.get_scene_session_status(bpy.context.scene)
            assert status == "connected", message
            verify(session, manifest, target.with_suffix(".cbq"))
            assert scientific_csv(session, output) == manifest["csv_sha256"]
            if args.phase == "refresh":
                session = refresh(session, manifest, output, blend)
            elif args.phase == "save-as":
                copied.parent.mkdir(parents=True, exist_ok=True)
                session = save(copied)
                verify(session, manifest, copied.with_suffix(".cbq"))
                assert array_hashes(blend.with_suffix(".cbq")) == manifest["scientific_array_sha256"]
            elif args.phase == "render":
                render(output)
            elif args.phase == "export":
                from ChemBlender.ui.orbital_export import export_orbital_images
                overview_camera = bpy.context.scene.camera
                objects_before = {obj.name: obj.hide_render for obj in bpy.context.scene.objects}
                datasets_before = set(session.project.datasets)
                try:
                    bpy.context.scene.camera = bpy.data.objects["Orbital Export Camera"]
                    package = export_orbital_images(bpy.context, session, bpy.context.scene.chemblender_wavefunction,
                        orbital_numbers=(5, 6), destination=output / "orbitals", isovalue=.04)
                finally:
                    bpy.context.scene.camera = overview_camera
                assert {obj.name: obj.hide_render for obj in bpy.context.scene.objects} == objects_before
                assert set(session.project.datasets) == datasets_before, "existing MO grids were not reused"
                display = json.loads((package / "display.json").read_text(encoding="utf-8"))
                assert [item["orbital_number"] for item in display["orbitals"]] == [5, 6]
                for item in display["orbitals"]:
                    assert item["reused_scientific_cache"]
                    assert (package / item["image"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
                assert json.loads((package / "manifest.json").read_text(encoding="utf-8"))["status"] == "complete"
                verify(session, manifest, blend.with_suffix(".cbq"))
            write_json(output / f"verification-{args.phase}.json", {
                "phase": args.phase, "blender": bpy.app.version_string,
                "opened": str(target), "project_id": str(session.project.id),
                "scientific_arrays_unchanged": True, "view_parameters_unchanged": True,
                "csv_transform_invariant": True, "property_surface_version": 2,
                "removed_render_cache_files": deleted,
            })
        print("QUANTUM_WORKBENCH_LIFECYCLE_PASSED", args.phase, str(output), flush=True)
    finally:
        ChemBlender.unregister()


if __name__ == "__main__":
    main()
