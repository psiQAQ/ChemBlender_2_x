"""Render real molecular Cycles previews or an atomic final image package.

Run in background Blender with a private BLENDER_USER_RESOURCES under .agents/cache.
Prepared .cbq arrays stay authoritative and are verified before/after rendering.
"""

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from uuid import UUID, uuid4

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT / ".agents/cache/scientific-corpus/molecular"
OUTPUT = SOURCE / "previews"

from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import plan_scene_preset
from cbq_core.scene_preset import scene_plan_document
from cbq_core.sidecar import close_project
from cbq_core.sidecar import open_project
from ChemBlender.render_scene import RenderScope


POSITIVE = (.035, .30, .82, 1.)
NEGATIVE = (.93, .16, .035, 1.)


@contextmanager
def staging_directory(parent, prefix):
    """Use normal inherited ACLs; Python 3.13's private temp ACL persists on rename."""
    parent = Path(parent).resolve()
    path = parent / (prefix + uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        if path.exists():
            if path.resolve().parent != parent:
                raise RuntimeError("staging cleanup escaped its output parent")
            shutil.rmtree(path)


def cases():
    """Explicit source selection and scientific settings, shared by both templates."""
    def surface(name, molecule, label, level, formula, direction=(1.2, -1.6, 1.1)):
        return dict(name=name, molecule=molecule, labels={"grid": label}, preset="signed_isosurface",
                    settings=dict(isovalue=level, opacity=1., positive_color=POSITIVE,
                                  negative_color=NEGATIVE), formula=formula, direction=direction)

    return (
        surface("water-homo", "water", "mo_restricted_homo", .06, "H2O | RHF/STO-3G | HOMO 5", (1.1, -1.5, .7)),
        surface("water-lumo", "water", "mo_restricted_lumo", .05, "H2O | RHF/STO-3G | LUMO 6", (.7, -1.8, .9)),
        surface("ch3-alpha-homo", "ch3", "mo_alpha_homo", .055, "CH3 radical | alpha HOMO | UHF/STO-3G", (1.4, -1.2, 1.)),
        surface("ch3-beta-homo", "ch3", "mo_beta_homo", .055, "CH3 radical | beta HOMO | UHF/STO-3G", (1.4, -1.2, 1.)),
        surface("water-density-iso", "water", "rho_scf_total", .08, "H2O | rho(r) | RHF/STO-3G"),
        dict(name="water-density-cloud", molecule="water", labels={"grid": "rho_scf_total"},
             preset="grid_volume", settings=dict(density_scale=5., signed=False, positive_color=POSITIVE),
             formula="H2O | rho(r) cloud | optical density_scale=5", direction=(1.2, -1.6, 1.1),
             focus_threshold=.03),
        surface("ch3-spin", "ch3", "rho_scf_spin", .008,
                "CH3 radical | rho_alpha(r) - rho_beta(r)", (1.4, -1.2, 1.)),
        surface("nitrogen-mp2-minus-scf", "nitrogen", "difference_mp2_minus_scf", .0007,
                "N atom | rho_UMP2(r) - rho_UHF(r) | 6-31G", (1.2, -1.6, 1.1)),
        dict(name="water-esp-surface", molecule="water",
             labels={"surface_grid": "rho_scf_total", "property_grid": "esp_scf"},
             preset="property_on_surface", settings=dict(surface_isovalue=.002,
                 color_min=-.06, color_max=.06, symmetric=True, colormap="coolwarm"),
             formula="H2O | V(r) on rho(r)=0.002 e/bohr^3", direction=(.6, -2., .6)),
        dict(name="water-esp-slice", molecule="water", labels={"grid": "esp_scf"},
             preset="grid_slice", settings=dict(origin=(-4., .35, -4.), u_vector=(9., 0., 0.),
                 v_vector=(0., 0., 10.), counts=(129, 129), color_min=-.1, color_max=.1,
                 symmetric=True, colormap="coolwarm"),
             formula="H2O | V(x,y=0.35 bohr,z) | offset plane avoids nuclei", direction=(0., -1., .001),
             framing_margin=1.45),
        dict(name="water-esp-profile", molecule="water", labels={"grid": "esp_scf"},
             preset="grid_profile", settings=dict(start=(-4., .7, .6), end=(5., .7, .6),
                 sample_count=257, radius=.012),
             formula="H2O | V(x,y=0.7,z=0.6 bohr) | distance axis in bohr", direction=(0., 0., 1.)),
    )


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def array_hashes(project):
    from dataclasses import fields, is_dataclass
    from cbq_core.model import ArrayData

    result = {}

    def visit(value, path):
        if isinstance(value, ArrayData):
            array = np.asarray(value.values)
            result[path] = hashlib.sha256(np.ascontiguousarray(array).view(np.uint8)).hexdigest()
        elif is_dataclass(value):
            for field in fields(value):
                visit(getattr(value, field.name), path + "/" + field.name)
        elif isinstance(value, (tuple, list)):
            for index, item in enumerate(value):
                visit(item, path + "/" + str(index))
        elif isinstance(value, dict):
            for name, item in value.items():
                visit(item, path + "/" + str(name))

    for registry in ("structures", "datasets", "basis_sets", "orbital_sets", "density_matrices"):
        visit(getattr(project, registry, {}), registry)
    return result


def configure_device(use_optix):
    if not use_optix:
        return {"device": "CPU"}
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "OPTIX"
    preferences.refresh_devices()
    devices = []
    for device in preferences.devices:
        device.use = device.type == "OPTIX"
        if device.use:
            devices.append(device.name)
    if not devices:
        raise RuntimeError("no OptiX device is available in this private profile")
    bpy.context.scene.cycles.device = "GPU"
    return {"device": "OPTIX", "names": devices, "preferences_saved": False}


def image_metrics(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        width, height = image.size
        pixels = np.asarray(image.pixels[:]).reshape(height, width, 4)[..., :3]
        background = np.median(np.concatenate((pixels[:4, :4].reshape(-1, 3),
                                              pixels[-4:, -4:].reshape(-1, 3))), axis=0)
        foreground = np.max(np.abs(pixels - background), axis=-1) > .06
        return dict(width=width, height=height, foreground_fraction=float(foreground.mean()),
                    border_foreground_fraction=float(np.concatenate((foreground[0], foreground[-1],
                                                       foreground[:, 0], foreground[:, -1])).mean()))
    finally:
        bpy.data.images.remove(image)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--optix", action="store_true")
    parser.add_argument("--final", action="store_true", help="2400 x 1800, 256 samples, new atomic image package")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
    if ROOT / ".agents" / "cache" not in private.parents:
        raise RuntimeError("a private repository cache profile is required")
    destination = (options.output or (ROOT / "examples/scientific-visualization/output/molecular/images"
                                     if options.final else OUTPUT)).resolve()
    if options.final and destination.exists():
        raise FileExistsError("final output must be a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        output = (stack.enter_context(staging_directory(destination.parent, ".molecular-images-"))
                  if options.final else destination)
        render_selected(options, output, destination)
        if options.final:
            if destination.exists():
                raise FileExistsError("final output appeared during rendering")
            os.rename(output, destination)
            print("MOLECULAR_FINAL_PUBLISHED", destination, flush=True)


def render_selected(options, output, destination):
    from cbq_core.analysis_report import build_analysis_report
    from cbq_core.analysis_report import describe_report_artifact
    from cbq_core.analysis_report import write_analysis_report_bundle

    OUTPUT.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / ("render-manifest.json" if options.final else "preview-manifest.json")
    document = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "schema_version": 1, "purpose": "final_scientific_render" if options.final
        else "parameter_tuning_preview_not_formal_final", "images": {}}
    document["device"] = configure_device(options.optix)
    document["script"] = str(Path(__file__).resolve())
    document["script_sha256"] = digest(Path(__file__).resolve())
    sources = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))["cases"]
    selected = [case for case in cases() if options.only is None or case["name"] in options.only]
    if options.only and set(options.only) - {case["name"] for case in selected}:
        raise ValueError("unknown preview case")
    for case_index, case in enumerate(selected):
        source = sources[case["molecule"]]
        sidecar = SOURCE / (case["molecule"] + ".cbq")
        disk_hashes = {str(path.relative_to(sidecar)): digest(path) for path in sidecar.rglob("*.npy")}
        project = open_project(sidecar)
        try:
            before = array_hashes(project)
            rows = {row["label"]: row for row in source["outputs"]}
            bindings = {key: UUID(rows[label]["id"]) for key, label in case["labels"].items()}
            grid = project.datasets[next(iter(bindings.values()))]
            structure = (project.structures[grid.structure_id]
                         if case["preset"] not in {"grid_slice", "grid_profile"} else None)
            for template in ("research", "teaching"):
                name = case["name"] + "-" + template
                settings = {**case["settings"], "template": template,
                            "shaded": template == "teaching" or case["preset"] == "signed_isosurface", "material_opacity": 1.}
                plan = plan_scene_preset(builtin_scene_presets()[case["preset"]], project, bindings, settings)
                path = output / (name + ".png")
                start = time.monotonic()
                print("MOLECULAR_RENDER_START", case_index * 2 + (1 if template == "research" else 2),
                      "/", len(selected) * 2, name, flush=True)
                with RenderScope(bpy.context, project, structure, template=template,
                                  width=2400 if options.final else 320, height=1800 if options.final else 240,
                                  samples=256 if options.final else 32, direction=case["direction"],
                                  framing_margin=case.get("framing_margin", 1.4),
                                  volume_focus_threshold=case.get("focus_threshold", 0.) if case["preset"] == "grid_volume" else 0.) as renderer:
                    display = renderer.render(plan, path, OUTPUT / "render-cache")
                if array_hashes(project) != before:
                    raise AssertionError("render changed authoritative scientific arrays")
                metrics = image_metrics(path)
                if metrics["foreground_fraction"] < .005:
                    raise AssertionError("preview appears blank")
                document["images"][name] = dict(path=str(destination / path.name), relative_path=path.name,
                    sha256=digest(path), status="rendered" if options.final
                    else "preview_rendered_pending_visual_review", molecule=case["molecule"],
                    molecular_formula={"water": "H2O", "ch3": "CH3 radical", "nitrogen": "N"}[case["molecule"]],
                    formula=case["formula"], source_sidecar=str(sidecar), source=source["source"],
                    datasets={key: rows[label] for key, label in case["labels"].items()},
                    plan=scene_plan_document(plan), display=display,
                    camera_tuning=display["framing"],
                    pixel_metrics=metrics,
                    scientific_arrays_unchanged=True, elapsed_seconds=time.monotonic() - start)
                manifest_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print("MOLECULAR_RENDER_COMPLETE", name, round(time.monotonic() - start, 2), flush=True)
            if options.final:
                artifacts = tuple(describe_report_artifact(output, case["name"] + "-" + template + ".png",
                                  role="scientific_image", media_type="image/png")
                                  for template in ("research", "teaching"))
                report = build_analysis_report(project, title=case["formula"],
                                               dataset_ids=tuple(bindings.values()), artifacts=artifacts)
                if report["status"] != "complete":
                    raise ValueError("scientific report is not complete")
                write_analysis_report_bundle(output / "reports" / case["name"], report)
            after = {str(path.relative_to(sidecar)): digest(path) for path in sidecar.rglob("*.npy")}
            if after != disk_hashes:
                raise AssertionError("render changed source sidecar files")
        finally:
            close_project(project)
    print("MOLECULAR_IMAGES_COMPLETE", len(selected) * 2, manifest_path, flush=True)


if __name__ == "__main__":
    main()
