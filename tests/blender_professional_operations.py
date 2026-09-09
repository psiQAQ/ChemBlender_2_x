"""Exercise real QTAIM, NCI, and phonon operations through Blender."""

import importlib
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import numpy


arguments = sys.argv[sys.argv.index("--") + 1:]
root = Path(arguments[0]).resolve(strict=True)
processor_executable = Path(arguments[1]).resolve(strict=True)
qtaim_source = Path(arguments[2]).resolve(strict=True)
wavefunction_source = Path(arguments[3]).resolve(strict=True)
phonopy_yaml_source = Path(arguments[4]).resolve(strict=True)
force_sets_source = Path(arguments[5]).resolve(strict=True)
born_source = Path(arguments[6]).resolve(strict=True)
extension_package = (
    Path(arguments[7]).resolve(strict=True) if len(arguments) == 8 else None
)
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
model = importlib.import_module(core_root + ".model")
registration = importlib.import_module(package_root + ".runtime.registration")
session_ui = importlib.import_module(package_root + ".ui.session")

if extension_package is None:
    registration.register_extension(package_root)

scene = bpy.context.scene
preferences = SimpleNamespace(processor_executable=str(processor_executable))
with TemporaryDirectory(prefix="professional-blender-") as temporary:
    temporary = Path(temporary)
    qtaim_package = temporary / "water.cbq"
    shutil.copytree(qtaim_source, qtaim_package)
    inputs = temporary / "inputs"
    inputs.mkdir()
    wavefunction = inputs / wavefunction_source.name
    phonopy_yaml = inputs / phonopy_yaml_source.name
    force_sets = inputs / force_sets_source.name
    born = inputs / born_source.name
    for source, destination in (
        (wavefunction_source, wavefunction),
        (phonopy_yaml_source, phonopy_yaml),
        (force_sets_source, force_sets),
        (born_source, born),
    ):
        shutil.copyfile(source, destination)

    scene.chemblender_cbq.input_path = str(qtaim_package)
    assert bpy.ops.chemblender.preview_cbq() == {"FINISHED"}
    assert bpy.ops.chemblender.import_cbq() == {"FINISHED"}
    session = session_ui.get_scene_session(scene)
    original_ids = session.project._all_entity_ids()
    structure = next(iter(session.project.structures.values()))
    session.active_entity_id = structure.id
    scene.chemblender_project_browser.active_entity_id = str(structure.id)
    settings = scene.chemblender_processor_operation

    with patch(
        package_root + ".ui.processor.get_processor_preferences",
        return_value=preferences,
    ):
        processor_operations = importlib.import_module(
            package_root + ".ui.processor_operations"
        )
        operator_type = processor_operations.CHEMBLENDER_OT_processor_operation
        timers = set()
        manager = SimpleNamespace(
            event_timer_add=lambda *_args, **_kwargs: timers.add(object()) or next(iter(timers)),
            event_timer_remove=lambda timer: timers.remove(timer),
            modal_handler_add=lambda _operator: None,
        )
        context = SimpleNamespace(scene=scene, window=None, window_manager=manager)
        operator = SimpleNamespace(
            _session=None, _operation=None, _timer=None, _window_manager=None,
            action="PROFESSIONAL", operation_id="grid.nci_fields",
            source_id="", topology_id="", report=lambda *_args: None,
        )
        operator._begin = lambda value: operator_type._begin(operator, value)
        operator._complete = lambda value, snapshot: operator_type._complete(
            operator, value, snapshot
        )
        operator._release = lambda value: operator_type._release(operator, value)
        settings.nci_grid_points = (128, 128, 128)
        settings.source_file = str(wavefunction)
        baseline_ids = session.project._all_entity_ids()
        started = time.perf_counter()
        assert operator_type.invoke(operator, context, None) == {"RUNNING_MODAL"}
        modal_elapsed = time.perf_counter() - started
        assert modal_elapsed < .1
        result = operator_type.modal(operator, context, SimpleNamespace(type="TIMER"))
        running_elapsed = time.perf_counter() - started
        assert result == {"RUNNING_MODAL"}
        assert operator._operation.poll().state.value == "running"
        assert running_elapsed < 1.
        cancelled_at = time.perf_counter()
        assert operator_type.modal(
            operator, context, SimpleNamespace(type="ESC")
        ) == {"RUNNING_MODAL"}
        deadline = time.monotonic() + 2.
        while result == {"RUNNING_MODAL"} and time.monotonic() < deadline:
            time.sleep(.01)
            result = operator_type.modal(
                operator, context, SimpleNamespace(type="TIMER")
            )
        cancel_elapsed = time.perf_counter() - cancelled_at
        assert result == {"CANCELLED"}, result
        assert cancel_elapsed < 2.
        assert session.project._all_entity_ids() == baseline_ids
        assert not timers and session.id not in processor_operations._ACTIVE_OPERATIONS
        print("PROCESSOR_CANCEL_PROBE_JSON=" + json.dumps({
            "modal_seconds": modal_elapsed,
            "running_seconds": running_elapsed,
            "cancel_seconds": cancel_elapsed,
        }, sort_keys=True))

        settings.source_file = str(wavefunction)
        assert bpy.ops.chemblender.processor_operation(
            "EXEC_DEFAULT", action="PROFESSIONAL",
            operation_id="topology.qtaim",
        ) == {"FINISHED"}
        qtaim_id = session.active_entity_id
        qtaim = session.project.datasets[qtaim_id]
        assert isinstance(qtaim, model.TopologyGraph)
        assert len(qtaim.critical_point_ids) == 5 and len(qtaim.paths) == 4

        settings.nci_grid_points = (20, 20, 20)
        settings.source_file = str(wavefunction)
        assert bpy.ops.chemblender.processor_operation(
            "EXEC_DEFAULT", action="PROFESSIONAL",
            operation_id="grid.nci_fields",
        ) == {"FINISHED"}
        nci_id = session.active_entity_id
        nci = session.project.datasets[nci_id]
        assert isinstance(nci, model.Grid3D)
        assert nci.semantic_role == "reduced_density_gradient"
        assert numpy.asarray(nci.data.values).shape == (20, 20, 20)
        signed_id = next(
            identity for identity, value in session.project.datasets.items()
            if isinstance(value, model.Grid3D)
            and value.semantic_role == "sign_lambda2_rho"
        )

        settings.reader_id = "phonopy-file"
        settings.source_file = str(phonopy_yaml)
        settings.force_sets_file = str(force_sets)
        settings.born_file = str(born)
        settings.qpoints = "0.1,0.2,0.3"
        settings.with_group_velocities = True
        settings.use_nac_direction = False
        assert bpy.ops.chemblender.processor_operation(
            "EXEC_DEFAULT", action="PROFESSIONAL",
            operation_id="periodic.phonon",
        ) == {"FINISHED"}
        phonon_id = session.active_entity_id
        phonon = session.project.datasets[phonon_id]
        assert isinstance(phonon, model.PhononModeSet)
        assert numpy.asarray(phonon.eigenvectors.values).shape[:2] == (1, 6)

    print("PROCESSOR_CANCEL_TIMINGS_JSON=" + json.dumps({
        "cancel_seconds": cancel_elapsed,
        "modal_seconds": modal_elapsed,
        "running_seconds": running_elapsed,
    }, sort_keys=True))
    assert original_ids.issubset(session.project._all_entity_ids())
    for identity in (qtaim_id, nci_id, phonon_id):
        assert any(
            str(identity) in obj.get("cb_scene_bindings_json", "")
            for obj in bpy.data.objects
        )

    saved = temporary / "professional-operations.blend"
    assert bpy.ops.wm.save_as_mainfile(filepath=str(saved)) == {"FINISHED"}
    shutil.rmtree(qtaim_package)
    shutil.rmtree(inputs)
    assert bpy.ops.wm.open_mainfile(filepath=str(saved)) == {"FINISHED"}
    reopened = session_ui.get_scene_session(bpy.context.scene)
    assert qtaim_id in reopened.project.datasets
    assert nci_id in reopened.project.datasets
    assert signed_id in reopened.project.datasets
    assert phonon_id in reopened.project.datasets
    assert numpy.asarray(reopened.project.datasets[nci_id].data.values).shape == (20, 20, 20)
    assert numpy.isfinite(
        numpy.asarray(reopened.project.datasets[phonon_id].data.values)
    ).all()
    for identity in (qtaim_id, nci_id, phonon_id):
        assert any(
            str(identity) in obj.get("cb_scene_bindings_json", "")
            for obj in bpy.data.objects
        )
    session_ui.close_scene_session(bpy.context.scene)

if extension_package is None:
    registration.unregister_extension()
else:
    assert bpy.ops.preferences.addon_disable(module=package_root) == {"FINISHED"}

print("BLENDER_PROFESSIONAL_OPERATIONS_PASSED")
