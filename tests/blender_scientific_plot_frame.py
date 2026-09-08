"""Private Cycles QA: fixed plot frames, real Gaussian transition rows, synthetic boundary cases.

This is display validation; it does not replace the pending cclib reader gate.
"""

import hashlib
import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import bpy
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
assert ROOT / ".agents" / "cache" in private.parents and bpy.app.background
output = private.parent / "plot-frame-qa"
output.mkdir(exist_ok=True)

from ChemBlender.core import ArrayData, SpectrumKind, SpectrumProfile, derive_electronic_spectrum
from ChemBlender.electronic_plot import create_band_structure_plot, create_dos_plot
from ChemBlender.render_scene import RenderScope
from ChemBlender.scientific_materials import flat_material
from ChemBlender.spectrum_plot import create_spectrum_plot, _remove_objects
from tests.test_excited_state_model import state_set
from tests.test_periodic_electronic_model import band_structure, density_of_states


def inventory():
    return {name: {value.as_pointer() for value in getattr(bpy.data, name)} for name in
            ("objects", "meshes", "curves", "materials", "node_groups", "cameras", "lights", "worlds")}


def scientific_point(root, point):
    x_low, x_high = root["cb_plot_x_range"]
    y_low, y_high = root["cb_plot_y_range"]
    return (x_low + point.co.x / root["cb_plot_width"] * (x_high - x_low),
            y_low + point.co.y / root["cb_plot_height"] * (y_high - y_low))


source = ROOT / "examples/scientific-visualization/inputs/cclib/Gaussian/basicGaussian16/dvb_td.out"
raw = source.read_bytes()
rows = re.findall(r"Excited State\s+\d+:.*?([\d.]+) eV\s+[\d.]+ nm\s+f=([\d.]+)", raw.decode("utf8"))
assert len(rows) == 5
# Explicit QA conversion of the printed eV values, separate from any reader adapter.
ev_to_cm = 8065.544005
axis = numpy.asarray([float(row[0]) * ev_to_cm for row in rows])
strength = numpy.asarray([float(row[1]) for row in rows])
template = derive_electronic_spectrum(state_set(uuid4()), kind=SpectrumKind.UV_VIS,
                                      profile=SpectrumProfile.STICK).datasets[0]
uv = replace(template, data=ArrayData(strength, ("sample",), "dimensionless"),
             axis=ArrayData(axis, ("sample",), "inverse_centimeter"))
signed = replace(uv, kind=SpectrumKind.ECD, semantic_role="ecd_spectrum",
                 data=ArrayData(numpy.array([-.02, .08, 0., -.01, .04]), ("sample",),
                                "ten_minus_forty_erg_esu_centimeter_per_gauss"))
band = band_structure(uuid4())
dos = density_of_states(band.structure_id)
baseline = inventory()
records = []
for name, dataset, builder, styles in (
    ("gaussian-transition-rows", uv, create_spectrum_plot, ("research", "teaching")),
    ("signed-display-boundary", signed, create_spectrum_plot, ("research",)),
    ("band-display-boundary", band, create_band_structure_plot, ("research",)),
    ("dos-display-boundary", dos, create_dos_plot, ("research",)),
):
    before = dataset.data.values.tobytes()
    for style in styles:
        with RenderScope(bpy.context, None, template=style, width=1200, height=900, samples=32) as renderer:
            plot = builder(dataset,
                material=flat_material("QA curve", (.08, .45, .85, 1.)),
                axis_material=flat_material("QA axes", (.78, .84, .92, 1.) if style == "teaching" else (.045, .06, .08, 1.)))
            try:
                assert plot["cb_plot_coordinate_system"] == "normalized_axes_v1"
                positions = numpy.array([tuple(point.co)[:2] for spline in plot.data.splines for point in spline.points])
                assert numpy.all(positions >= -1.e-6) and numpy.all(positions <= (8.000001, 5.000001))
                assert numpy.ptp(positions[:, 0]) > 7. and numpy.ptp(positions[:, 1]) > 4.9
                if dataset is uv or dataset is signed:
                    for index, spline in enumerate(plot.data.splines):
                        numpy.testing.assert_allclose(scientific_point(plot, spline.points[-1]),
                            (dataset.axis.values[index], dataset.data.values[index]), rtol=2.e-6, atol=1.e-7)
                        numpy.testing.assert_allclose(scientific_point(plot, spline.points[0])[1], 0., atol=1.e-7)
                    bodies = {child.data.body for child in plot.children if child.type == "FONT"}
                    assert dataset.axis.unit in bodies and dataset.data.unit in bodies
                    assert "0" in bodies
                    assert positions[:, 0].min() > .3, "edge sticks must not hide behind the y axis"
                fonts = [child.data.size for child in plot.children if child.type == "FONT"]
                assert fonts and min(fonts) >= .19
                renderer.frame_objects((plot,), flat=True)
                path = output / f"{name}-{style}.png"
                bpy.context.scene.render.filepath = str(path)
                assert "FINISHED" in bpy.ops.render.render(write_still=True)
                records.append({"path": path.name, "style": style,
                    "x_range": list(plot["cb_plot_x_range"]), "y_range": list(plot["cb_plot_y_range"]),
                    "display_size": [8., 5.], "scientific_array_unchanged": dataset.data.values.tobytes() == before})
            finally:
                _remove_objects((plot, *plot.children))
        assert inventory() == baseline
        assert dataset.data.values.tobytes() == before

(output / "qa.json").write_text(json.dumps({"purpose": "plot display validation, not a cclib reader gate",
    "source": str(source.relative_to(ROOT)), "source_sha256": hashlib.sha256(raw).hexdigest(),
    "printed_rows": rows, "ev_to_inverse_centimeter": ev_to_cm, "renders": records}, indent=2) + "\n", encoding="utf8")
print("SCIENTIFIC_PLOT_FRAME_PASSED: five Cycles images; scientific values, zero, axes and resources preserved")
