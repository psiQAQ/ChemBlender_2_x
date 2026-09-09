"""Run in a separate Blender process with a private BLENDER_USER_RESOURCES."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import bpy
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ChemBlender import electronic_plot, fermi_surface_view, spectrum_plot, topology_view
from cbq_core.model import ArrayData
from cbq_core.model import BandPathBranch
from cbq_core.model import SpectrumKind
from cbq_core.model import SpectrumProfile
from cbq_core.model import TopologyPath
from chemblender_prepare.core.vibration_spectrum import derive_vibrational_spectrum
from chemblender_prepare.core.critic2_adapter import parse_critic2_cpreport
from tests.test_fermi_surface_model import fermi_surface
from tests.test_periodic_electronic_model import band_structure, density_of_states
from tests.test_vibration_model import mode_set


def inventory():
    return {name: {block.as_pointer() for block in getattr(bpy.data, name)}
            for name in ("objects", "meshes", "curves", "materials", "node_groups")}


def cleanup(root):
    spectrum_plot._remove_objects((root, *root.children))


def rendered_faces(obj):
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return len(mesh.polygons)
    finally:
        evaluated.to_mesh_clear()


def check_plots():
    band = band_structure(uuid4())
    dos = density_of_states(band.structure_id)
    dos = replace(dos, projections=ArrayData(np.arange(60.).reshape(2, 5, 2, 3),
        ("spin", "energy", "atom", "orbital"), dos.data.unit))
    before = inventory()
    arrays_before = dos.projections.values.tobytes()
    obj = electronic_plot.create_dos_plot(dos, atom_indices=(1,), orbital_labels=("pz",), spin_indices=(1,))
    try:
        assert len(obj.data.splines) == 1
        x = obj.data.splines[0].points[0].co.x / obj["cb_plot_width"]
        lower, upper = obj["cb_plot_x_range"]
        assert np.isclose(lower + x * (upper - lower), -dos.projections.values[1, 0, 1, 2])
        assert list(obj["cb_plot_spin_indices"]) == [1]
        assert list(obj["cb_dos_atom_indices"]) == [1]
        assert list(obj["cb_dos_orbital_labels"]) == ["pz"]
        assert rendered_faces(obj) > 0
        labels = [child.data.body for child in obj.children if child.type == "FONT"]
        assert "E - E_F (eV)" in labels and "states / eV" in labels
        assert any("beta mirrored" in label for label in labels)
        assert all(child.get("cb_scientific_component") for child in obj.children)
        obj.location = (9., 7., 3.)
        assert dos.projections.values.tobytes() == arrays_before
    finally:
        cleanup(obj)
    assert inventory() == before

    # A final single-point branch must never create a line across the path break.
    band = replace(band, branches=(BandPathBranch(0, 1, "GAMMA", None), BandPathBranch(2, 2, "X", "X")))
    obj = electronic_plot.create_band_structure_plot(band)
    try:
        assert len(obj.data.splines) == 16
        assert [len(spline.points) for spline in obj.data.splines[:2]] == [2, 1]
        labels = [child.data.body for child in obj.children if child.type == "FONT"]
        assert "GAMMA" in labels and "X" in labels
        assert rendered_faces(obj) > 0
    finally:
        cleanup(obj)
    assert inventory() == before

    spectrum = derive_vibrational_spectrum(mode_set(uuid4()), kind=SpectrumKind.IR,
                                           profile=SpectrumProfile.STICK).datasets[0]
    obj = spectrum_plot.create_spectrum_plot(spectrum)
    try:
        assert len(obj.data.splines) == len(spectrum.axis.values)
        assert rendered_faces(obj) > 0
        assert any(child.type == "FONT" and child.data.body == spectrum.axis.unit for child in obj.children)
    finally:
        cleanup(obj)
    assert inventory() == before


def check_fermi():
    surface = fermi_surface(uuid4(), uuid4())
    before = inventory()
    obj = fermi_surface_view.create_fermi_surface_view(surface)
    try:
        legend = json.loads(obj["cb_band_legend"])
        assert obj["cb_color_mapping"] == "categorical_band_index"
        assert [item["band_index"] for item in legend] == sorted(set(surface.band_indices.values))
        assert all(item["band_number"] == item["band_index"] + 1 for item in legend)
        assert len(obj.data.materials) == len(legend)
        for polygon, band in zip(obj.data.polygons, surface.band_indices.values):
            assert legend[polygon.material_index]["band_index"] == band
    finally:
        cleanup(obj)
    assert inventory() == before
    obj = fermi_surface_view.create_fermi_surface_view(
        surface, color_property="fermi_velocity", vector_component="x",
        color_min=-1., color_max=3., vector_property="fermi_velocity", vector_stride=2, vector_scale=.1)
    try:
        assert obj.data.attributes["cbq_band_index"].data[0].value == 1
        assert obj.data.attributes["cbq_color_value"].domain == "POINT"
        assert obj["cb_color_unit"] == "meter_per_second"
        assert np.allclose([item.value for item in obj.data.attributes["cbq_color_value"].data], 1.)
        child, = obj.children
        assert child["cb_scientific_component"] == "fermi_vectors"
        assert [item.value for item in child.data.attributes["cbq_source_sample_index"].data] == [0, 2]
        assert np.allclose([tuple(item.vector) for item in child.data.attributes["cbq_vector"].data], .1)
        assert rendered_faces(child) > 0
        fermi_surface_view.select_fermi_face(obj, surface, 0)
        assert obj["cb_selected_band"] == 1
        ramp = next(node for node in obj.data.materials[0].node_tree.nodes if node.bl_idname == "ShaderNodeValToRGB")
        assert any(np.isclose(element.position, .25) for element in ramp.color_ramp.elements)
    finally:
        cleanup(obj)
    assert inventory() == before


def check_topology():
    dataset = parse_critic2_cpreport(ROOT / "tests/fixtures/critic2/cpreport-minimal.json", structure_id=uuid4()).datasets[0]
    before = inventory()
    points, paths = topology_view.create_topology_view(dataset)
    try:
        assert paths is None and len(dataset.connections) > 0
        assert len(points.data.vertices) == len(dataset.critical_point_ids)
        assert rendered_faces(points) >= 80 * len(dataset.critical_point_ids)
        bpy.context.view_layer.update()
        evaluated = points.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            assert "cbq_critical_point_index" in mesh.attributes
            assert "cbq_kind_color" in mesh.attributes
            assert set(item.value for item in mesh.attributes["cbq_critical_point_index"].data) == {0, 1, 2}
        finally:
            evaluated.to_mesh_clear()
    finally:
        cleanup(points)
    assert inventory() == before

    samples = np.array(((0., 0., 0.), (.5, .35, .1), (1., 0., 0.)))
    path = TopologyPath(id=uuid4(), start_id=dataset.critical_point_ids[0], end_id=dataset.critical_point_ids[2],
                        samples=ArrayData(samples, ("sample", "xyz"), "bohr"))
    dataset = replace(dataset, paths=(path,))
    points, paths = topology_view.create_topology_view(dataset, color_property="laplacian", color_min=-10., color_max=2.)
    try:
        assert paths.parent == points and len(paths.data.splines) == 1
        assert paths.data.bevel_depth == np.float32(.025)
        np.testing.assert_allclose([tuple(point.co)[:3] for point in paths.data.splines[0].points], samples * .529177210903)
        assert rendered_faces(paths) > 0
        assert points["cb_point_radius"] == .1
    finally:
        cleanup(points)
    assert inventory() == before


def check_rollback():
    before = inventory()
    spectrum = derive_vibrational_spectrum(mode_set(uuid4()), kind=SpectrumKind.IR, profile=SpectrumProfile.STICK).datasets[0]
    with patch.object(spectrum_plot, "_plot_axes", side_effect=RuntimeError("injected axes failure")):
        try:
            spectrum_plot.create_spectrum_plot(spectrum)
        except RuntimeError as error:
            assert str(error) == "injected axes failure"
        else:
            raise AssertionError("expected rollback failure")
    assert inventory() == before
    dataset = parse_critic2_cpreport(ROOT / "tests/fixtures/critic2/cpreport-minimal.json", structure_id=uuid4()).datasets[0]
    with patch.object(topology_view, "_point_glyphs", side_effect=RuntimeError("injected glyph failure")):
        try:
            topology_view.create_topology_view(dataset)
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected glyph rollback failure")
    assert inventory() == before


assert os.environ.get("BLENDER_USER_RESOURCES"), "private Blender resources are required"
print(json.dumps({"version": bpy.app.version_string, "executable": bpy.app.binary_path,
                  "python": sys.executable, "background": bpy.app.background,
                  "resources": os.environ["BLENDER_USER_RESOURCES"],
                  "repositories": [repo.directory for repo in bpy.context.preferences.extensions.repos]}))
assert bpy.app.background and bpy.app.version >= (5, 1, 0)
for check in (check_plots, check_fermi, check_topology, check_rollback):
    check()
    print(check.__name__, "PASSED")
print("SCIENTIFIC_ADAPTERS_PASSED")
