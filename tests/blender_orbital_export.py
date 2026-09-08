"""Real PNG export and failure/cancellation restoration in disposable Blender."""

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import bpy
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument("--existing-libraries", required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
sys.path.append(args.existing_libraries)

import ChemBlender
from ChemBlender.core import ImportBatch, evaluate_molecular_orbital_grid
from ChemBlender.ui import orbital_export as export
from ChemBlender.ui.session import get_scene_session, close_scene_session
from tests.test_wavefunction_grid import entities


def snapshot(scene, session):
    return {
        "objects": {obj.name: (obj.hide_render, tuple(tuple(row) for row in obj.matrix_world))
                    for obj in scene.objects},
        "selected": tuple(sorted(obj.name for obj in bpy.context.selected_objects)),
        "active": bpy.context.view_layer.objects.active,
        "camera": scene.camera,
        "render": tuple(getattr(scene.render, key) for key in
                        ("filepath", "use_file_extension", "use_compositing", "use_sequencer")),
        "image": tuple(getattr(scene.render.image_settings, key) for key in
                       ("file_format", "color_mode", "color_depth")),
        "entity": session.active_entity_id,
        "browser_entity": scene.chemblender_project_browser.active_entity_id,
        "owned_data": {key: len(getattr(bpy.data, key)) for key in
                       ("objects", "meshes", "volumes", "cameras", "collections")},
    }


ChemBlender.register()
try:
    scene = bpy.context.scene
    session = get_scene_session(scene)
    structure, basis, orbitals = entities()
    session.project.commit(ImportBatch(structures=(structure,), basis_sets=(basis,), orbital_sets=(orbitals,)))
    session.active_entity_id = orbitals.id
    scene.chemblender_project_browser.active_entity_id = str(orbitals.id)
    settings = scene.chemblender_wavefunction
    settings.orbital_source = str(orbitals.id)
    settings.channel = "restricted"
    settings.origin, settings.spacing, settings.shape = (-2., -2., -2.), .25, (17, 17, 17)
    geometry = dict(origin=tuple(settings.origin), shape=tuple(settings.shape),
                    step_vectors=((.25, 0., 0.), (0., .25, 0.), (0., 0., .25)))
    for index in (0, 1):
        with patch("ChemBlender.core.wavefunction_grid._evaluate_channel", side_effect=
            lambda _s, _b, c, points: numpy.asarray([points[:, 0] * numpy.exp(-numpy.sum(points ** 2, axis=1))])):
            session.project.commit(evaluate_molecular_orbital_grid(structure, basis, orbitals,
                channel="restricted", orbital_index=index, **geometry))
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 2
    scene.render.resolution_x = scene.render.resolution_y = 64
    scene.render.resolution_percentage = 100
    scene.render.filepath = "//user-original-output"
    scene.render.use_file_extension = False
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.color_mode = "RGB"
    user = bpy.data.objects.new("Keep hidden user object", None)
    scene.collection.objects.link(user)
    user.hide_render = True
    user.location = (8., 9., 10.)
    bpy.context.view_layer.update()
    original_camera = scene.camera
    expected = snapshot(scene, session)

    with TemporaryDirectory(prefix="cb-orbital-render-") as temporary:
        directory = Path(temporary)

        def iterator(name, **kwargs):
            return export.iter_orbital_images(bpy.context, session, settings,
                orbital_numbers=(1, 2), destination=directory / name, isovalue=.06, **kwargs)

        scene.camera = None
        try:
            iterator("no-camera")
        except ValueError as error:
            assert "camera" in str(error)
        else:
            raise AssertionError("Missing camera passed preflight")
        scene.camera = original_camera
        assert not list(directory.iterdir())

        # Immediately closing a returned generator must release the session lock.
        for _ in range(2):
            iterator("immediate-close").close()
            assert not export._EXPORTS
            assert snapshot(scene, session) == expected

        # Cancel after entering the display scope and before the first render.
        run = iterator("closed")
        assert next(run)["stage"] == "Render MO 1"
        assert scene.camera != original_camera
        for name, (hidden, _matrix) in expected["objects"].items():
            obj = scene.objects[name]
            assert obj.hide_render == (hidden if obj.type in {"CAMERA", "LIGHT"} else True)
        run.close()
        assert snapshot(scene, session) == expected
        assert not list(directory.iterdir())

        # A real PNG is staged before cancellation; no partial package survives.
        cancelled = False
        run = iterator("cancelled", is_cancelled=lambda: cancelled)
        next(run)
        assert next(run)["stage"] == "Rendered MO 1"
        assert len(list(directory.glob(".cb-orbitals-*/images/*.png"))) == 1
        cancelled = True
        try:
            next(run)
        except export.OrbitalExportCancelled:
            pass
        else:
            raise AssertionError("Cancelled render package was published")
        assert snapshot(scene, session) == expected
        assert not list(directory.iterdir())

        # The second-render failure must also discard the first real PNG.
        original_render = export._RenderScope.render
        count = 0

        def fail_second(renderer, plan, destination, cache):
            global count
            count += 1
            if count == 2:
                raise RuntimeError("injected render failure")
            original_render(renderer, plan, destination, cache)

        with patch.object(export._RenderScope, "render", fail_second):
            try:
                list(iterator("failed"))
            except RuntimeError as error:
                assert "injected" in str(error)
            else:
                raise AssertionError("Second-render failure did not fail the package")
        assert count == 2
        assert snapshot(scene, session) == expected
        assert not list(directory.iterdir())

        # All PNGs and report artifacts refer to the same successfully published bundle.
        result = export.export_orbital_images(bpy.context, session, settings,
            orbital_numbers=(1, 2), destination=directory / "complete", isovalue=.06)
        assert result == directory / "complete"
        assert snapshot(scene, session) == expected
        report = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
        display = json.loads((result / "display.json").read_text(encoding="utf-8"))
        assert report["status"] == "complete" and len(display["orbitals"]) == 2
        assert display["blender_version"] == bpy.app.version_string
        for artifact in report["artifacts"]:
            path = result / artifact["path"]
            assert path.is_file() and path.stat().st_size == artifact["size"]
        assert len(list((result / "images").glob("*.png"))) == 2
        assert not list(directory.glob(".cb-orbitals-*"))
        assert not export._EXPORTS
        assert len(session.project.datasets) == 2
    close_scene_session(scene)
    print(json.dumps({"orbital_export_real_png": "passed", "missing_camera": "passed",
        "immediate_close": "passed", "cancel_after_render": "passed", "second_render_failure": "passed",
        "scene_restore": "passed", "atomic_package": "passed"}))
finally:
    ChemBlender.unregister()
