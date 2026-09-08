"""Run with Blender --background --factory-startup --python-exit-code 1 --python this_file."""

import json
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import bpy
import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ChemBlender.core import ArrayData, DatasetStatus, Grid3D
from ChemBlender.core.grid_sampling import export_grid_sample, line_profile, plane_slice
from ChemBlender.grid_sample_view import create_grid_sample_view, remove_grid_sample_view
from ChemBlender.surface_view import property_color_stops


ORIGIN = np.array((-1., .4, -.5))
STEPS = np.array(((.5, .1, 0), (.15, .6, .05), (0, .1, .4)))
SCALE = .529177210903
COEFFICIENTS = np.array((.7, -.4, .2))


def point(index):
    return ORIGIN + np.asarray(index) @ STEPS


def grid():
    points = ORIGIN + np.indices((5, 5, 5), dtype=float).transpose(1, 2, 3, 0) @ STEPS
    return Grid3D(
        id=uuid4(), revision="analytic-r1", semantic_role="electrostatic_potential",
        domain="grid", data=ArrayData(points @ COEFFICIENTS + .15, ("x", "y", "z"),
                                       "hartree_per_elementary_charge"),
        status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        structure_id=uuid4(), origin=tuple(ORIGIN),
        step_vectors=tuple(tuple(row) for row in STEPS), coordinate_unit="bohr",
    )


def inventory():
    return {name: {data.as_pointer() for data in getattr(bpy.data, name)}
            for name in ("objects", "meshes", "curves", "materials")}


def attributes(mesh, name, vector=False):
    return np.asarray([tuple(item.vector) if vector else item.value
                       for item in mesh.attributes[name].data])


def check_slice_and_csv():
    dataset = grid()
    settings = dict(dataset_index=0, origin=tuple(point((-1, 0, 2))),
                    u_vector=tuple(6 * STEPS[0]), v_vector=tuple(4 * STEPS[1]),
                    counts=(7, 5), color_min=-1., color_max=3.,
                    symmetric=False, colormap="coolwarm")
    samples = plane_slice(dataset, **{name: settings[name] for name in (
        "dataset_index", "origin", "u_vector", "v_vector", "counts")})
    before = inventory()
    objects = create_grid_sample_view(dataset, "grid_slice", settings)
    root = objects[0]
    try:
        assert root.type == "MESH" and root["cb_grid_sample_root"]
        assert root["cb_grid_sample_contract"] == "grid_slice_v1"
        assert root["cb_valid_sample_count"] == 25
        assert len(root.data.polygons) == 16
        actual = attributes(root.data, "cb_sample_value")
        valid = attributes(root.data, "cb_sample_valid").astype(bool)
        np.testing.assert_array_equal(valid, samples.valid_mask.ravel())
        np.testing.assert_allclose(actual[valid], samples.values.ravel()[valid], atol=1e-6)
        assert np.isnan(actual[~valid]).all()
        for face in root.data.polygons:
            assert valid[list(face.vertices)].all()
        np.testing.assert_allclose(attributes(root.data, "cb_sample_coordinate", True),
                                   samples.points.reshape(-1, 3), atol=1e-6)
        np.testing.assert_allclose([tuple(vertex.co) for vertex in root.data.vertices],
                                   samples.points.reshape(-1, 3) * SCALE, atol=1e-6)
        material = root.data.materials[0]
        assert material["cbq_contract"] == "property_colormap_v2"
        assert material["cb_property_attribute"] == "cb_sample_value"
        principal = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        assert principal.inputs["Alpha"].links[0].from_node.attribute_name == "cb_sample_valid"
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "slice.csv"
            export_grid_sample(path, dataset, kind="plane", settings=settings)
            original = path.read_bytes()
            root.location = (8., -3., 2.)
            root.rotation_euler = (.2, .1, .6)
            root.scale = (2., 1., .5)
            bpy.context.view_layer.update()
            export_grid_sample(path, dataset, kind="plane", settings=settings)
            assert path.read_bytes() == original, "scene transforms changed scientific CSV"
        np.testing.assert_allclose(attributes(root.data, "cb_sample_value")[valid], actual[valid])
    finally:
        remove_grid_sample_view(root)
    assert inventory() == before, "slice cleanup leaked datablocks"
    return {"samples": int(valid.size), "valid": int(valid.sum()), "faces": 16}


def check_profile_gaps():
    dataset = grid()
    values = np.asarray(dataset.data.values).copy()
    values[2, :, :] = np.nan
    dataset = replace(dataset, data=ArrayData(values, dataset.data.dims, dataset.data.unit))
    settings = dict(dataset_index=0, start=tuple(point((-.5, 2, 2))),
                    end=tuple(point((4.5, 2, 2))), sample_count=11, radius=.01)
    samples = line_profile(dataset, **{key: value for key, value in settings.items() if key != "radius"})
    before = inventory()
    objects = create_grid_sample_view(dataset, "grid_profile", settings)
    root = objects[0]
    try:
        assert root.type == "CURVE" and len(root.data.splines) == 2
        assert [len(spline.points) for spline in root.data.splines] == [2, 2]
        np.testing.assert_allclose(root.data.bevel_depth, settings["radius"], atol=1e-9)
        graph = next(obj for obj in objects if obj["cb_grid_sample_component"] == "profile_graph")
        assert len(graph.data.splines) == 2
        assert [len(spline.points) for spline in graph.data.splines] == [3, 3]
        assert all(np.isfinite(tuple(p.co)).all() for s in graph.data.splines for p in s.points)
        plotted = np.asarray([tuple(p.co)[:3] for spline in graph.data.splines for p in spline.points])
        axes = next(obj for obj in objects if obj["cb_grid_sample_component"] == "profile_axes")
        height = axes.data.splines[0].points[0].co.y
        minimum, maximum = graph["cb_graph_value_min"], graph["cb_graph_value_max"]
        np.testing.assert_allclose(plotted[:, 0] / SCALE, samples.distance[samples.valid_mask], atol=1e-6)
        np.testing.assert_allclose(plotted[:, 1] / height * (maximum - minimum) + minimum,
                                   samples.values[samples.valid_mask], atol=1e-6)
        np.testing.assert_allclose([tuple(p.co)[:3] for spline in root.data.splines for p in spline.points],
                                   samples.points[[1, 3, 7, 9]] * SCALE, atol=1e-6)
        assert all(obj.parent == root and not obj.get("cb_grid_sample_root") for obj in objects[1:])
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.csv"
            export_grid_sample(path, dataset, kind="profile", settings=settings)
            original = path.read_bytes()
            root.location = (4., 2., -1.)
            root.rotation_euler = (.2, 0, .3)
            bpy.context.view_layer.update()
            export_grid_sample(path, dataset, kind="profile", settings=settings)
            assert path.read_bytes() == original, "scene transforms changed profile CSV"
    finally:
        remove_grid_sample_view(root)
    assert inventory() == before, "profile cleanup leaked datablocks"
    return {"path_segments": 2, "points_per_path_segment": 2, "graph_segments": 2, "valid_samples": 6}


def check_colorbar_and_user_children():
    dataset = grid()
    before = inventory()
    objects = create_grid_sample_view(dataset, "grid_colorbar", dict(
        dataset_index=0, color_min=-1., color_max=3., symmetric=False,
        colormap="coolwarm", width=4., height=.4))
    root = objects[0]
    user = bpy.data.objects.new("User child preserved", None)
    bpy.context.scene.collection.objects.link(user)
    zero_label = next(obj for obj in objects if obj["cb_grid_sample_component"] == "zero_label")
    user.parent = zero_label
    user.location = (.3, .2, .1)
    root.location = (4., -2., 1.)
    bpy.context.view_layer.update()
    transform = user.matrix_world.copy()
    try:
        assert root["cb_color_zero_fraction"] == .25
        np.testing.assert_allclose(zero_label.location.x, 1., atol=1e-7)
        np.testing.assert_allclose(tuple(root.data.vertices[2].co), (4., .4, 0), atol=1e-7)
        material = root.data.materials[0]
        ramp = next(node for node in material.node_tree.nodes if node.type == "VALTORGB")
        stops = property_color_stops(-1., 3.)
        for actual, expected in zip(ramp.color_ramp.elements, stops):
            np.testing.assert_allclose(actual.position, expected[0], atol=1e-7)
            np.testing.assert_allclose(tuple(actual.color), expected[1], atol=1e-7)
        assert next(obj for obj in objects if obj["cb_grid_sample_component"] == "unit_label").data.body == dataset.data.unit
    finally:
        remove_grid_sample_view(root)
    assert user.parent is None
    np.testing.assert_allclose(np.asarray(user.matrix_world), np.asarray(transform), atol=1e-6)
    bpy.data.objects.remove(user, do_unlink=True)
    assert inventory() == before, "legend cleanup leaked datablocks"
    return {"zero_fraction": .25, "neutral_color": list(stops[1][1])}


def check_failed_creation_and_shared_data():
    dataset = grid()
    settings = dict(color_min=-1., color_max=3., symmetric=False, width=4., height=.4)
    before = inventory()
    with patch("ChemBlender.grid_sample_view._poly_spline", side_effect=RuntimeError("injected tick failure")):
        try:
            create_grid_sample_view(dataset, "grid_colorbar", settings)
        except RuntimeError as error:
            assert "injected tick" in str(error)
        else:
            raise AssertionError("injected creation failure did not occur")
    assert inventory() == before, "failed creation leaked datablocks"
    root = create_grid_sample_view(dataset, "grid_colorbar", settings)[0]
    shared_data, material = root.data, root.data.materials[0]
    user = bpy.data.objects.new("User linked geometry", shared_data)
    bpy.context.scene.collection.objects.link(user)
    remove_grid_sample_view(root)
    assert user.data == shared_data and material.users > 0
    bpy.data.objects.remove(user, do_unlink=True)
    bpy.data.meshes.remove(shared_data)
    bpy.data.materials.remove(material)
    assert inventory() == before, "shared-data test cleanup leaked datablocks"


result = {"slice": check_slice_and_csv(), "profile": check_profile_gaps(),
          "colorbar": check_colorbar_and_user_children()}
check_failed_creation_and_shared_data()
print("GRID_SAMPLING_PASSED", json.dumps(result, sort_keys=True))
