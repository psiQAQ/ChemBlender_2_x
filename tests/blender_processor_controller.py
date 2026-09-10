"""Native Blender regression for the local processor and preview lifecycle."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bpy


root = Path(sys.argv[sys.argv.index("--") + 1]).resolve(strict=True)
processor_executable = Path(sys.argv[sys.argv.index("--") + 2]).resolve(strict=True)
profile = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve(strict=True)
assert bpy.app.version >= (5, 1, 0)
assert os.environ.get("PYTHONNOUSERSITE") == "1" and not os.environ.get("PYTHONPATH")
assert profile != Path.home() and root not in profile.parents
sys.path.insert(0, str(root))

from ChemBlender.runtime import registration
from ChemBlender.ui import processor, scientific_view


registration.register_extension("ChemBlender")
owned = tuple(registration._registered_classes)
assert processor.CHEMBLENDER_Preferences.is_registered
assert processor.CHEMBLENDER_OT_test_processor.is_registered
assert processor.CHEMBLENDER_Preferences.bl_idname == "ChemBlender"
assert "processor_executable" in processor.CHEMBLENDER_Preferences.__annotations__
assert not hasattr(bpy.types.Scene, "processor_executable")
assert hasattr(bpy.ops.chemblender, "mesh_edit")

scene = bpy.context.scene
root_object = bpy.data.objects.new("processor-preview-root", None)
scene.collection.objects.link(root_object)
settings = scene.chemblender_scientific_view
settings.loaded_view_name = root_object.name
project = object()
with patch("ChemBlender.ui.session.get_scene_session",
           return_value=SimpleNamespace(project=project)), \
     patch("ChemBlender.scene_preset_view.apply_scientific_phase") as apply_phase:
    settings.phase = .1
    settings.phase = .2
    settings.phase = .3
    assert bpy.app.timers.is_registered(scientific_view._flush_local_previews)
    bpy.app.timers.unregister(scientific_view._flush_local_previews)
    scientific_view._flush_local_previews()
    apply_phase.assert_called_once()
    assert apply_phase.call_args.args[:2] == (root_object, project)
    assert abs(apply_phase.call_args.args[2] - .3) < 1.e-6

with patch("ChemBlender.ui.session.get_scene_session",
           return_value=SimpleNamespace(project=project)), \
     patch("ChemBlender.scene_preset_view.apply_scientific_frame") as apply_frame:
    settings.frame_index = 1
    settings.frame_index = 2
    bpy.app.timers.unregister(scientific_view._flush_local_previews)
    scientific_view._flush_local_previews()
    apply_frame.assert_called_once_with(root_object, project, 2)
    assert root_object["cb_scientific_playback"] is False

with TemporaryDirectory(prefix="processor-native-") as workspace:
    started = time.perf_counter()
    task = processor.start_capability_test(processor_executable, workspace)
    assert time.perf_counter() - started < .1
    assert task.snapshot().state is processor.ProcessorState.RUNNING
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        snapshot = task.poll()
        if snapshot.state is not processor.ProcessorState.RUNNING:
            break
        time.sleep(.02)
    assert snapshot.state is processor.ProcessorState.SUCCEEDED, snapshot
    assert snapshot.result["worker_protocol_version"] == "1"

# A completed capability task must redraw Preferences without a second UI action.
context = SimpleNamespace(area=Mock())
operator = SimpleNamespace(_task=Mock(), _cleanup=Mock(), report=Mock())
for terminal in (processor.ProcessorState.SUCCEEDED,
                 processor.ProcessorState.FAILED,
                 processor.ProcessorState.CANCELLED):
    context.area.reset_mock()
    operator._task.poll.return_value = SimpleNamespace(
        state=terminal, result=snapshot.result, error=None)
    result = processor.CHEMBLENDER_OT_test_processor.modal(
        operator, context, SimpleNamespace(type="TIMER"))
    assert result == ({"FINISHED"} if terminal is processor.ProcessorState.SUCCEEDED
                      else {"CANCELLED"})
    context.area.tag_redraw.assert_called_once_with()
context.area.reset_mock()
processor.CHEMBLENDER_OT_test_processor.modal(
    operator, context, SimpleNamespace(type="ESC"))
context.area.tag_redraw.assert_called_once_with()

registration.unregister_extension()
assert all(not cls.is_registered for cls in owned)
assert not hasattr(bpy.types.Scene, "chemblender_scientific_view")
registration.register_extension("ChemBlender")
assert processor.CHEMBLENDER_OT_test_processor.is_registered
registration.unregister_extension()
print("PROCESSOR_CONTROLLER_PASSED")
