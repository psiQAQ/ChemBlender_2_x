"""Install the extension in a private profile and verify processor settings."""

import importlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import time

import bpy


package = Path(sys.argv[sys.argv.index("--") + 1]).resolve(strict=True)
processor_executable = Path(sys.argv[sys.argv.index("--") + 2]).resolve(strict=True)
profile = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve(strict=True)
assert bpy.app.version >= (5, 1, 0)
assert os.environ.get("PYTHONNOUSERSITE") == "1" and not os.environ.get("PYTHONPATH")
assert profile != Path.home()
assert bpy.ops.extensions.package_install_files(
    filepath=str(package), repo="user_default", enable_on_install=True, overwrite=False
) == {"FINISHED"}

key = "bl_ext.user_default.chemblender"
assert key in bpy.context.preferences.addons
processor = importlib.import_module(key + ".ui.processor")
preferences = bpy.context.preferences.addons[key].preferences
preferences.processor_executable = str(processor_executable)
assert Path(preferences.processor_executable).resolve() == processor_executable
assert not any(hasattr(preferences, name) for name in (
    "worker_python", "worker_repository", "fermi_python", "critic2_executable"
))
assert not hasattr(bpy.types.Scene, "processor_executable")
assert hasattr(bpy.ops.chemblender, "mesh_edit")

with TemporaryDirectory(prefix="processor-installed-") as workspace:
    started = time.perf_counter()
    task = processor.start_capability_test(preferences.processor_executable, workspace)
    assert time.perf_counter() - started < .1
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        snapshot = task.poll()
        if snapshot.state is not processor.ProcessorState.RUNNING:
            break
        time.sleep(.02)
    assert snapshot.state is processor.ProcessorState.SUCCEEDED, snapshot

owned = tuple(importlib.import_module(key + ".runtime.registration")._registered_classes)
assert bpy.ops.preferences.addon_disable(module=key) == {"FINISHED"}
assert all(not cls.is_registered for cls in owned)
assert bpy.ops.preferences.addon_enable(module=key) == {"FINISHED"}
assert importlib.import_module(key + ".ui.processor").CHEMBLENDER_OT_test_processor.is_registered
print("PROCESSOR_INSTALLED_PASSED")
