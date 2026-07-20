# Blender Extension Add-on Template (4.2+) — autoload-only variant

This template is a modular starter for Blender Extension Add-ons.

It uses `auto_load.py` to discover submodules and register classes in topological order.

Class registration is handled by `auto_load.py`. Module-level `register()`/`unregister()` should be used only for non-class side effects (for example Scene property attach/detach).

## Folder layout

```text
extension_addon/
├─ blender_manifest.toml
├─ __init__.py
├─ auto_load.py
├─ constants.py
├─ properties.py
├─ preferences.py
├─ operators/
│  ├─ __init__.py
│  └─ object_ops.py
├─ panels/
│  ├─ __init__.py
│  └─ viewport_panel.py
├─ utils/
│  ├─ __init__.py
│  └─ common.py
├─ scripts/
│  ├─ validate_extension.py
│  ├─ build_extension.py
│  └─ sync_and_reload.py
└─ README.md
```

## When to use this template

Use this template for Blender 4.2+ extension development.

## Quick start

1. Copy this folder and rename it to your extension module name.
2. Update `blender_manifest.toml`:
   - `id`
   - `name`
   - `maintainer`
   - `version`
3. Update `constants.py` and then replace demo class names where needed.
4. Disable/enable in Blender and verify registration behavior.

## Build

Run in the extension root directory (where `blender_manifest.toml` is located):

```bash
python scripts/build_extension.py
```

## Scripted validation and build

Run from the extension root (the folder containing `blender_manifest.toml`).

```bash
# Optional: gather Blender runtime info from MCP and save to JSON
# (binary_path / binary_path_python / blender_system / extension_root)

# Validate (local preflight + blender --command extension validate)
python scripts/validate_extension.py

# Validate with explicit Blender executable
python scripts/validate_extension.py \
  --blender "/path/to/blender"

# Unified build entrypoint (runs validate_extension.py first)
python scripts/build_extension.py \
  --mcp-info-json /path/to/blender_mcp_info.json

# Cross-system mode example (WSL -> Windows Blender)
python scripts/build_extension.py \
  --mcp-info-json /path/to/blender_mcp_info.json \
  --allow-cross-system
```

## Standard local verification commands

Run from the extension root to perform a minimal local verification pass:

```bash
# Python syntax check
python -m py_compile \
  __init__.py \
  auto_load.py \
  constants.py \
  preferences.py \
  properties.py \
  operators/object_ops.py \
  panels/viewport_panel.py \
  utils/common.py \
  scripts/build_extension.py \
  scripts/sync_and_reload.py \
  scripts/validate_extension.py

# Local preflight only (no Blender invocation)
python scripts/validate_extension.py --skip-blender-validate

# Full validate when Blender is available
python scripts/validate_extension.py --blender "/path/to/blender"

# Build extension zip
python scripts/build_extension.py --blender "/path/to/blender"
```

Python interpreter selection priority used by script orchestration:

1. User-specified interpreter (`--python` or `EXTENSION_DEV_PYTHON`)
2. Project virtual environment (`.venv`)
3. Blender bundled Python (`binary_path_python` from MCP info JSON or `BLENDER_PYTHON`)
4. System Python from PATH (`python3` / `python`)

## sync_and_reload helper (optional)

```bash
python scripts/sync_and_reload.py \
  --source /path/to/source/addon \
  --target "/path/to/blender/extensions/user_default/my_example_extension" \
  --module my_addon \
  --delete-stale \
  --dry-run
```

Legacy `scripts/addons` targets are blocked by default in extension-only workflow.
Use `--allow-legacy-target` only when intentionally developing a legacy add-on.

## Development notes

- For WSL + Windows Blender, target installed extension repo paths, and ensure paths are Blender-host resolvable.
- Keep module side effects in module `register()`/`unregister()` and let `auto_load.py` handle class registration order.
