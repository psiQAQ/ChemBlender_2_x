"""Render real PQR charges and rMD17 configurations through public scientific exports.

Use a private project-cache BLENDER_USER_RESOURCES. --preview renders small stills;
the default publishes 2400x1800/256-sample stills and 1280x720/64-sample sequences.
Neither mode changes the prepared scientific arrays or invents physical time.
"""

import argparse
import json
import os
from pathlib import Path
import sys

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_molecular import array_hashes, configure_device, digest, image_metrics
from ChemBlender.core import builtin_scene_presets, close_session, create_session, plan_scene_preset
from ChemBlender.core.sidecar import open_project
from ChemBlender.scene_preset_view import apply_scene_preset, _remove_objects
from ChemBlender.ui.scientific_export import iter_scientific_images
from ChemBlender.ui.orbital_export import _image_staging


SOURCE = ROOT / ".agents/cache/scientific-corpus/molecular"


def cases():
    return (
        dict(name="pqr-charge", source="pqr", preset="atomic_scalar", animation=False,
             direction=(.932727, .335011, .133372), framing_margin=1.5,
             settings=dict(color_min=-1.2, color_max=1.2, symmetric=True, colormap="coolwarm")),
        dict(name="aspirin-force", source="rmd17", preset="trajectory_force", animation=False,
             direction=(.376812, .700065, .606566), framing_margin=1.5,
             settings=dict(frame_index=0, vector_scale=.5)),
        dict(name="aspirin-trajectory", source="rmd17", preset="trajectory", animation=False,
             direction=(.376812, .700065, .606566), framing_margin=1.5, settings=dict(frame_index=0)),
        dict(name="aspirin-force-animation", source="rmd17", preset="trajectory_force", animation=True,
             direction=(.376812, .700065, .606566), framing_margin=1.5,
             settings=dict(frame_index=0, vector_scale=.5)),
        dict(name="aspirin-trajectory-animation", source="rmd17", preset="trajectory", animation=True,
             direction=(.376812, .700065, .606566), framing_margin=1.5, settings=dict(frame_index=0)),
    )


def hashes(sidecar):
    return {path.relative_to(sidecar).as_posix(): digest(path)
            for path in sorted(sidecar.rglob("*")) if path.is_file()}


def bindings_for(project, case):
    structure, = project.structures.values()
    result = {"structure": structure.id}
    if case["preset"] == "atomic_scalar":
        prop, = (value for value in project.datasets.values() if value.semantic_role == "partial_charge")
        result["property"] = prop.id
    else:
        frames, = (value for value in project.datasets.values() if type(value).__name__ == "FrameSet")
        result["frames"] = frames.id
        if case["preset"] == "trajectory_force":
            force, = (value for value in project.datasets.values() if value.semantic_role == "atomic_force")
            result["force"] = force.id
    return result


def render_package(options, staging, private):
    manifest = {"schema_version": 1, "purpose": "parameter_preview" if options.preview else "real_scientific_render",
                "script": str(Path(__file__).resolve()), "script_sha256": digest(Path(__file__).resolve()),
                "device": configure_device(options.optix), "cases": {}, "sources": {},
                "limitations": ["rMD17: 32 source configurations, rows 0..3100 stride 100; no physical time interval declared",
                    "Animation FPS controls playback only; no interpolation or time calibration",
                    "PQR element identities were inferred by the reader from atom/residue names; all 998 atoms are shown",
                    "Force arrows use an explicit display scale; source force values remain in electron_volt_per_angstrom"]}
    selected = [case for case in cases() if (not options.preview or not case["animation"])
                and (not options.only or case["name"] in options.only)]
    if not selected or options.only and set(options.only) - {case["name"] for case in selected}:
        raise ValueError("unknown or unavailable case selection")
    for case in selected:
        sidecar = SOURCE / (case["source"] + ".cbq")
        disk_before = hashes(sidecar)
        project = open_project(sidecar)
        session = create_session(temp_parent=private.parent, project=project)
        objects = ()
        try:
            memory_before = array_hashes(project)
            bound = bindings_for(project, case)
            plan = plan_scene_preset(builtin_scene_presets()[case["preset"]], project, bound, case["settings"])
            objects = apply_scene_preset(plan, project)
            objects[0].name = case["name"]
            assert objects[0].matrix_world == Matrix.Identity(4), "example source View must keep its scientific coordinate frame"
            source_matrix_world = [list(row) for row in objects[0].matrix_world]
            width, height, samples = ((640, 480, 32) if options.preview else
                                      (1280, 720, 64) if case["animation"] else (2400, 1800, 256))
            iterator = iter_scientific_images(bpy.context, session, roots=(objects[0],),
                destination=staging / case["name"], width=width, height=height, samples=samples,
                animation=case["animation"], fps=24, direction=case["direction"],
                framing_margin=case["framing_margin"], volume_focus_threshold=0.)
            try:
                while True:
                    try:
                        progress = next(iterator)
                    except StopIteration as completed:
                        result = completed.value
                        break
                    print(json.dumps(dict(case=case["name"], **progress)), flush=True)
            finally:
                iterator.close()
            display = json.loads((result / "display.json").read_text(encoding="utf-8"))
            for view in display["views"]:
                if case["source"] == "rmd17":
                    assert all("time" not in image["trajectory_frame"] for image in view["images"])
                    assert all(image["phase_radians"] is None for image in view["images"])
                    assert "physical time unavailable" in " ".join(view["display"]["annotations"]["details"])
            structure, = project.structures.values()
            provenance = [dict(id=str(value.id), revision=value.revision, source=value.source,
                source_hash=value.source_hash, producer=value.producer, producer_version=value.producer_version,
                parameters=dict(value.parameters)) for value in project.provenance.values()]
            manifest["sources"][case["source"]] = dict(sidecar=str(sidecar), project_id=str(project.id),
                source_files=disk_before, atom_count=len(structure.atomic_numbers), provenance=provenance)
            images = sorted((result / "images").glob("*.png"))
            metrics = {path.relative_to(staging).as_posix(): image_metrics(path)
                       for path in images if not case["animation"] or path.name.endswith(("0001.png", "0032.png"))}
            manifest["cases"][case["name"]] = dict(case, resolution=[width, height], samples=samples,
                source_matrix_world=source_matrix_world,
                fps=24 if case["animation"] else None, display=(result / "display.json").relative_to(staging).as_posix(),
                report=(result / "manifest.json").relative_to(staging).as_posix(),
                bindings={key: str(value) for key, value in bound.items()}, image_count=len(images), image_metrics=metrics)
            assert array_hashes(project) == memory_before, "scientific array changed in memory"
            assert hashes(sidecar) == disk_before, "source sidecar bytes changed"
            assert (result / "manifest.json").is_file() and (result / "report.md").is_file()
            print("ATOM_TRAJECTORY_CASE_PASSED", case["name"], flush=True)
        finally:
            _remove_objects(objects)
            close_session(session)
    manifest["artifacts"] = [{"path": path.relative_to(staging).as_posix(), "bytes": path.stat().st_size,
                               "sha256": digest(path)} for path in sorted(staging.rglob("*")) if path.is_file()]
    (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, allow_nan=False,
        sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--optix", action="store_true")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
    if ROOT / ".agents/cache" not in private.parents:
        raise RuntimeError("a private project-cache Blender profile is required")
    private.mkdir(parents=True, exist_ok=True)
    destination = (options.output or (SOURCE / "atom-trajectory-preview" if options.preview else
                   ROOT / "examples/scientific-visualization/output/atom-trajectory")).resolve()
    if destination.exists():
        raise FileExistsError("Choose a new output directory; existing results are preserved")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _image_staging(destination) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        render_package(options, staging, private)
        if destination.exists():
            raise FileExistsError("Output directory appeared during rendering")
        staging.rename(destination)
    print("ATOM_TRAJECTORY_PUBLISHED", destination, flush=True)


if __name__ == "__main__":
    main()
