"""Exercise real scientific operations through Blender's shared operator."""

import os
import importlib
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bpy
import numpy


arguments = sys.argv[sys.argv.index("--") + 1:]
root = Path(arguments[0]).resolve(strict=True)
processor_executable = Path(arguments[1]).resolve(strict=True)
wavefunction_source = Path(arguments[2]).resolve(strict=True)
extension_package = (Path(arguments[3]).resolve(strict=True)
                     if len(arguments) == 4 else None)
profile = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve(strict=True)
assert bpy.app.version >= (5, 1, 0)
assert profile != Path.home() and root not in profile.parents
if extension_package is None:
    sys.path.insert(0, str(root))
    package_root = "ChemBlender"
else:
    assert bpy.ops.extensions.package_install_files(
        filepath=str(extension_package), repo="user_default",
        enable_on_install=True, overwrite=False,
    ) == {"FINISHED"}
    package_root = "bl_ext.user_default.chemblender"

core_root = "cbq_core" if extension_package is None else package_root + "._cbq_core"
Grid3D = importlib.import_module(core_root + ".model").Grid3D
registration = importlib.import_module(package_root + ".runtime.registration")
processor_operations = importlib.import_module(package_root + ".ui.processor_operations")
get_scene_session = importlib.import_module(
    package_root + ".ui.session"
).get_scene_session


if extension_package is None:
    registration.register_extension(package_root)
else:
    assert Path(processor_operations.__file__).resolve().is_relative_to(profile)
scene = bpy.context.scene
session = get_scene_session(scene)
settings = scene.chemblender_processor_operation
wavefunction = scene.chemblender_wavefunction

with TemporaryDirectory(prefix="processor-blender-") as temporary:
    temporary = Path(temporary)
    source_copy = temporary / wavefunction_source.name
    shutil.copyfile(wavefunction_source, source_copy)
    settings.reader_id = "iodata_wavefunction"
    settings.source_file = str(source_copy)
    preferences = SimpleNamespace(processor_executable=str(processor_executable))
    with patch(package_root + ".ui.processor.get_processor_preferences",
               return_value=preferences):
        timers = set()
        manager = SimpleNamespace(
            event_timer_add=lambda *_args, **_kwargs: timers.add(object()) or next(iter(timers)),
            event_timer_remove=lambda timer: timers.remove(timer),
            modal_handler_add=lambda _operator: None,
        )
        operator_type = processor_operations.CHEMBLENDER_OT_processor_operation
        operator = SimpleNamespace(
            _session=None, _operation=None, _timer=None, _window_manager=None,
            action="READER", operation_id="", source_id="", topology_id="",
            report=lambda *_args: None,
        )
        invoke_context = SimpleNamespace(
            scene=scene, window=None, window_manager=manager, area=Mock(),
        )
        started = time.perf_counter()
        operator._begin = lambda context: operator_type._begin(operator, context)
        operator._complete = lambda context, snapshot: operator_type._complete(
            operator, context, snapshot
        )
        operator._release = lambda context: operator_type._release(operator, context)
        result = operator_type.invoke(operator, invoke_context, None)
        modal_elapsed = time.perf_counter() - started
        assert result == {"RUNNING_MODAL"}, result
        assert modal_elapsed < .1
        assert operator._operation is None and timers
        result = operator_type.modal(
            operator, invoke_context, SimpleNamespace(type="TIMER")
        )
        running_elapsed = time.perf_counter() - started
        assert result == {"RUNNING_MODAL"}, result
        assert operator._operation.poll().state.value == "running"
        assert running_elapsed < 1.
        deadline = time.monotonic() + 120.
        while result == {"RUNNING_MODAL"} and time.monotonic() < deadline:
            time.sleep(.02)
            result = operator_type.modal(
                operator, invoke_context, SimpleNamespace(type="TIMER")
            )
        assert result == {"FINISHED"}, result
        assert not timers
        assert session.id not in processor_operations._ACTIVE_OPERATIONS
        invoke_context.area.tag_redraw.assert_called_once_with()
        assert len(session.project.structures) == 1
        assert len(session.project.basis_sets) == 1
        assert len(session.project.orbital_sets) == 1
        assert len(session.project.density_matrices) == 1
        orbitals = next(iter(session.project.orbital_sets.values()))
        revision = next(iter(session.project.source_revisions.values()))
        assert Path(revision.locator) == source_copy.resolve()

        wavefunction.origin = (-1., -1., -1.)
        wavefunction.spacing = .5
        wavefunction.shape = (3, 3, 3)
        wavefunction.orbital_number = 1
        wavefunction.channel = orbitals.channels[0].label
        result = bpy.ops.chemblender.processor_operation(
            "EXEC_DEFAULT", action="WAVEFUNCTION",
            operation_id="wavefunction.mo_grid", source_id=str(orbitals.id),
        )
        assert result == {"FINISHED"}, result
        grid = session.project.datasets[session.active_entity_id]
        assert isinstance(grid, Grid3D)
        assert grid.semantic_role == "molecular_orbital"
        expected = numpy.asarray(grid.data.values).copy()
        assert expected.shape == (3, 3, 3) and numpy.isfinite(expected).all()

    print("PROCESSOR_TIMINGS_JSON=" + json.dumps({
        "modal_seconds": modal_elapsed,
        "running_seconds": running_elapsed,
    }, sort_keys=True))
    blend_path = temporary / "processor-operation.blend"
    assert bpy.ops.wm.save_as_mainfile(filepath=str(blend_path)) == {"FINISHED"}
    source_copy.unlink()
    assert bpy.ops.wm.open_mainfile(filepath=str(blend_path)) == {"FINISHED"}
    reopened = get_scene_session(bpy.context.scene)
    reopened_grid = reopened.project.datasets[grid.id]
    assert numpy.array_equal(numpy.asarray(reopened_grid.data.values), expected)
    assert any(str(grid.id) in obj.get("cb_scene_bindings_json", "")
               and obj.get("cb_view_root") is True for obj in bpy.data.objects)
    if extension_package is None:
        registration.unregister_extension()
    else:
        assert bpy.ops.preferences.addon_disable(module=package_root) == {"FINISHED"}

print("PROCESSOR_OPERATIONS_PASSED")
