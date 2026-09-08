"""Actual RNA/operator regression; run only with a private project-cache profile."""

import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import bpy
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
assert ROOT / ".agents" / "cache" in private.parents

from ChemBlender.core import ArrayData, ImportBatch, create_session
from ChemBlender.ui import scientific_view as ui, session as session_ui
from ChemBlender.ui import scientific_import, wavefunction_import
from ChemBlender.ui.project_browser import panel
from ChemBlender.ui.view_cache import scene_plan_from_view
from tests.test_scene_preset import grid
from tests.test_vibration_model import structure, mode_set

classes = (
    panel.CHEMBLENDER_PG_project_browser_row,
    panel.CHEMBLENDER_PG_project_browser,
    ui.CHEMBLENDER_PG_scientific_view,
    ui.CHEMBLENDER_OT_scientific_view,
    ui.CHEMBLENDER_OT_derive_scientific_spectrum,
    ui.CHEMBLENDER_OT_derive_density_difference,
    scientific_import.CHEMBLENDER_PG_scientific_import,
    scientific_import.CHEMBLENDER_OT_import_scientific_file,
    scientific_import.CHEMBLENDER_OT_import_fermi,
    wavefunction_import.CHEMBLENDER_OT_import_wavefunction,
)
for cls in classes:
    bpy.utils.register_class(cls)
bpy.types.Scene.chemblender_project_browser = bpy.props.PointerProperty(type=panel.CHEMBLENDER_PG_project_browser)
ui.register()
ui.register()
scientific_import.register()
scientific_import.register()
wavefunction_import.register()
assert bpy.app.handlers.frame_change_post.count(ui._scientific_frame_change) == 1

scene = bpy.context.scene
session = create_session(temp_parent=private.parent)
session_ui._FILE_SESSION = session_ui._SessionEntry(session, "unlinked", "")
reference = structure()
modes = mode_set(reference.id, displacements=ArrayData(
    numpy.array([[[1., 0., 0.], [-1., 0., 0.]], [[0., 1., 0.], [0., -1., 0.]]]),
    ("mode", "atom", "xyz"), "angstrom"))
left = grid(reference.id)
right = replace(left, id=uuid4(), data=ArrayData(
    numpy.ones((3, 3, 3)), ("x", "y", "z"), left.data.unit))
session.project.commit(ImportBatch(structures=(reference,), datasets=(modes, left, right)))
settings = scene.chemblender_scientific_view


def select(entity):
    session.active_entity_id = entity.id
    scene.chemblender_project_browser.active_entity_id = str(entity.id)


try:
    select(modes)
    assert bpy.ops.chemblender.scientific_view(action="DEFAULTS") == {"FINISHED"}
    assert bpy.ops.chemblender.scientific_view(action="CREATE") == {"FINISHED"}
    obj = bpy.context.active_object
    identity = obj["cb_view_instance_id"]
    assert obj["cb_view_root"] is True
    obj.location = (4., 5., 6.)
    user = bpy.data.objects.new("User Child", None)
    scene.collection.objects.link(user)
    user.parent = obj
    user.location = (1., 2., 3.)
    bpy.context.view_layer.update()
    pose = user.matrix_world.copy()
    assert bpy.ops.chemblender.scientific_view(action="LOAD") == {"FINISHED"}
    settings.template = "teaching"
    settings.material_opacity = .4
    assert bpy.ops.chemblender.scientific_view(action="UPDATE") == {"FINISHED"}
    obj = bpy.context.active_object
    assert obj["cb_view_instance_id"] == identity
    assert tuple(obj.location) == (4., 5., 6.)
    bpy.context.view_layer.update()
    assert all(abs(user.matrix_world[i][j] - pose[i][j]) < 1.e-6 for i in range(4) for j in range(4))
    assert dict(scene_plan_from_view(obj, session.project).settings)["template"] == "teaching"

    before = obj.as_pointer()
    with patch("ChemBlender.scene_preset_view.apply_scene_preset", side_effect=RuntimeError("injected preparation failure")):
        try:
            bpy.ops.chemblender.scientific_view(action="UPDATE")
        except RuntimeError as error:
            assert "injected preparation failure" in str(error)
        else:
            raise AssertionError("expected reported preparation failure")
    assert bpy.context.active_object.as_pointer() == before
    assert obj.data is not None

    source_before = modes.data.values.tobytes(), modes.displacements.values.tobytes()
    settings.frame_start = 1
    settings.frames_per_cycle = 48
    assert bpy.ops.chemblender.scientific_view(action="PLAY") == {"FINISHED"}
    scene.frame_set(13)
    assert obj["cb_scientific_playback"] is True
    assert max(abs(vertex.co.x) for vertex in obj.data.vertices) > .1
    assert source_before == (modes.data.values.tobytes(), modes.displacements.values.tobytes())
    assert bpy.ops.chemblender.scientific_view(action="PAUSE") == {"FINISHED"}

    select(modes)
    before_datasets = len(session.project.datasets)
    assert bpy.ops.chemblender.derive_scientific_spectrum(kind="ir") == {"FINISHED"}
    spectrum = session.project.datasets[session.active_entity_id]
    assert len(session.project.datasets) == before_datasets + 1
    assert spectrum.source_dataset_id == modes.id
    assert scene.chemblender_project_browser.active_entity_id == str(spectrum.id)
    assert session.dirty

    select(left)
    settings.difference_source = str(right.id)
    assert settings.difference_source_uuid == str(right.id)
    assert bpy.ops.chemblender.derive_density_difference() == {"FINISHED"}
    difference = session.project.datasets[session.active_entity_id]
    assert difference.semantic_role == "difference_density"
    numpy.testing.assert_array_equal(difference.data.values, -numpy.ones((3, 3, 3)))
    assert scene.chemblender_project_browser.active_entity_id == str(difference.id)
    ui.clear_scientific_playback(session)
    assert not obj["cb_scientific_playback"]

    # Actual operators share a task lifecycle; only their external numerical
    # loader is replaced here. Source staging and publication remain real.
    for operator_type in (wavefunction_import.CHEMBLENDER_OT_import_wavefunction,
                          scientific_import.CHEMBLENDER_OT_import_scientific_file,
                          scientific_import.CHEMBLENDER_OT_import_fermi):
        operator = SimpleNamespace()
        operator._finish_modal = lambda: operator_type._finish_modal(operator)
        operator_type.cancel(operator, None)
    from ChemBlender.core.import_pipeline import ImportSource, ValidationMode
    from ChemBlender.core.import_pipeline.parse import stage_import_batch
    import hashlib
    source = private / "synthetic-cclib.out"
    source.write_bytes(b"synthetic UI import fixture")
    source_structure = structure()
    source_modes = mode_set(source_structure.id)
    batch = stage_import_batch(source=ImportSource(source), validation_mode=ValidationMode.BALANCED,
        content_hash=hashlib.sha256(source.read_bytes()).hexdigest(), byte_size=source.stat().st_size,
        plugin_id="chemblender.builtin", reader_id="cclib_output", reader_version="1", api_version="1.0-rc1",
        parsed_batch=ImportBatch(structures=(source_structure,), datasets=(source_modes,)))
    input_settings = scene.chemblender_scientific_import
    input_settings.worker_python = str(Path(bpy.app.binary_path).parent / "5.1/python/bin/python.exe")
    input_settings.worker_repository = str(ROOT)
    with patch.object(wavefunction_import, "load_reader_batch", return_value=batch):
        assert bpy.ops.chemblender.import_scientific_file(filepath=str(source)) == {"FINISHED"}
    assert session.active_entity_id == source_modes.id
    assert scene.chemblender_project_browser.active_entity_id == str(source_modes.id)
    assert settings.preset_id == "AUTO"
    assert not wavefunction_import._ACTIVE_IMPORTS

    from tests.test_periodic_electronic_model import band_structure, periodic_structure
    from tests.test_fermi_surface_model import fermi_surface
    crystal = periodic_structure()
    band = band_structure(crystal.id)
    surface = fermi_surface(crystal.id, band.id)
    fermi_batch = ImportBatch(structures=(crystal,), datasets=(band, surface))
    input_settings.fermi_python = input_settings.worker_python
    input_settings.fermi_directory = str(private)
    with patch.object(scientific_import, "load_fermi_batch", return_value=fermi_batch):
        assert bpy.ops.chemblender.import_fermi() == {"FINISHED"}
    assert session.active_entity_id == surface.id
    assert scene.chemblender_project_browser.active_entity_id == str(surface.id)
    assert not wavefunction_import._ACTIVE_IMPORTS
    print("SCIENTIFIC_VIEW_UI_PASSED: RNA, views, timeline, derivations, file/Fermi import lifecycle")
finally:
    scientific_import.unregister()
    wavefunction_import.unregister()
    ui.unregister()
    assert ui._scientific_frame_change not in bpy.app.handlers.frame_change_post
    session_ui.close_scene_session(scene)
    del bpy.types.Scene.chemblender_project_browser
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
