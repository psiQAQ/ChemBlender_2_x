# Common Pitfalls and Fixes

## 1) Submodule cache keeps old code

**Symptom:** update does not take effect after disable/enable.

**Fix:** clear `sys.modules["<package>.<submodule>"]` before re-importing submodules.

## 2) `hasattr` is unreliable for registration state

**Symptom:** `hasattr(bpy.types, "MyPropertyGroup")` returns `False` even after registration.

**Fix:**
- use `try/except ValueError` for class registration
- validate PropertyGroup through attached scene property

## 3) Wrong module key for self-disable

**Symptom:** add-on cannot disable itself with display name.

**Fix:** use module name from `self.__class__.__module__.split(".")[0]`.

## 4) `global` declaration order error

**Symptom:** `SyntaxError: name used prior to global declaration`.

**Fix:** put `global` statement before any variable usage in function scope.

## 5) Path errors in shell commands

**Symptom:** quoted path missing causes file-not-found for folders with spaces.

**Fix:** always quote full path variables in shell commands.

## 6) Unregister verification via `bpy.ops`

**Symptom:** operator-like checks look stale due proxy behavior.

**Fix:** verify removal via `bpy.types` and preferences add-ons map.

## 7) Broken or duplicate links in development path

**Symptom:** add-on changes do not apply or wrong directory is loaded.

**Fix:**
- remove broken symlink/junction entries
- remove duplicate links pointing to the same source
- keep only one active link target per module name

## 8) Handler duplication after repeated reload cycles

**Symptom:** handler executes multiple times after disable/enable loops.

**Fix:**
- unregister old handlers before register
- deduplicate handlers by function identity/name before append

## 9) Private path removal does not unload modules

**Symptom:** disabling the add-on removes `deps/site-packages` from `sys.path`, but previously imported packages still appear usable.

**Fix:** remember that removing a path does not remove already loaded entries from `sys.modules`; restart Blender or unload specific modules only when you fully understand the side effects.

## 10) Top-level optional imports break the install button

**Symptom:** a missing package causes add-on enable to fail, so users cannot open Preferences to install it.

**Fix:** do not import optional third-party packages at module top level; import them inside `execute()` or the function that needs them.

## 11) `auto_load.py` scans dependency directories

**Symptom:** reload imports packages from `deps/site-packages` as if they were add-on modules.

**Fix:** exclude `deps`, `wheels`, `.venv`, `venv`, `scripts`, and `__pycache__` from recursive module discovery.

## 12) Network install happens during register

**Symptom:** enabling the add-on unexpectedly downloads packages.

**Fix:** never install in `register()` or import-time code; only install after an explicit user action in Preferences.

## 13) Binary packages fail inside Blender Python

**Symptom:** packages such as `numpy`, `opencv-python`, `scipy`, or `torch` fail with ABI, DLL, or Python version errors.

**Fix:** verify Blender Python compatibility first and prefer wheels or an external Python environment for heavy binary dependencies.

## 14) Heavy dependencies are forced into Blender

**Symptom:** add-on startup becomes fragile or slow because it embeds large ML/CV/CUDA stacks.

**Fix:** run heavy dependencies in an external Python service and communicate through `subprocess`, sockets, HTTP, or MCP.
