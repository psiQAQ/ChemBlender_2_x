# Template Guide

## Built-in template

Use this local template:

- `templates/extension_addon/` (`auto_load` topology registration)

Compatibility target:

- Blender **4.2+** (Extension system)

Manifest reference:

- `./manifest-fields.md`

## Mandatory pre-step: system adaptation

Before running Blender commands or editing add-on files, read:

- `./system-adaptation.md`

Always detect both runtime systems first:

1. Agent runtime system
2. Blender runtime system

Then choose the file and path strategy for:

- same-system runtime
- cross-system runtime (including WSL to Windows `/mnt/c/...` mapping when applicable)

## Template structure

```text
extension_addon/
├─ blender_manifest.toml
├─ __init__.py
├─ auto_load.py
├─ constants.py
├─ properties.py
├─ preferences.py
├─ deps/
│  └─ site-packages/      # created by private pip installs; do not ship by default
├─ wheels/                # preferred release-time offline dependencies
├─ operators/
│  ├─ __init__.py
│  └─ object_ops.py
├─ panels/
│  ├─ __init__.py
│  └─ viewport_panel.py
├─ utils/
│  ├─ __init__.py
│  ├─ dependency_manager.py
│  └─ common.py
├─ scripts/
│  ├─ validate_extension.py
│  ├─ build_extension.py
│  └─ sync_and_reload.py
└─ README.md
```

## Why this structure

- `blender_manifest.toml`: extension metadata and compatibility.
- `__init__.py + auto_load.py`: topology-based orchestration for dependency-safe class registration.
- `constants.py`: centralized IDs and naming constants for safer renames.
- `properties.py`: PropertyGroup and scene pointer property side effects.
- `operators/object_ops.py`: executable actions.
- `panels/viewport_panel.py`: UI layout.
- `preferences.py`: add-on settings entry point.
- `utils/dependency_manager.py`: private dependency path, status checks, and user-triggered `pip --target` install helper.
- `utils/common.py`: shared helper functions for reusable logic.
- `deps/site-packages`: development/internal private dependency target; release builds should exclude it by default.
- `wheels`: preferred location for release-time offline dependency wheels listed in `blender_manifest.toml`.
- `scripts/validate_extension.py`: merged validator (local preflight + `blender --command extension validate`).
- `scripts/build_extension.py`: unified Python build entrypoint with system checks and Blender path resolution.
- `scripts/*`: validation, build orchestration, and optional sync helper.

## Recommended usage flow

1. Copy template to target add-on folder.
2. Update manifest fields (`id`, `name`, `maintainer`, `version`).
3. Rename example classes and operator IDs.
4. Reload add-on and verify panel/operator/property behavior.
5. If dependencies are needed, edit `utils/dependency_manager.py` and keep imports delayed until runtime.

## Dependency packaging guidance

- Use `deps/site-packages` only for development or internal private installs with `pip --target`.
- Do not include `deps/site-packages` in release builds by default.
- For published extensions, prefer `wheels = [...]` in `blender_manifest.toml` and store wheel files under `wheels/`.

## Build extension package

Run in the add-on root directory:

```bash
python scripts/build_extension.py
```

Python interpreter priority for scripted checks/build:

1. User-specified extension development Python environment
2. Project virtual environment (`.venv`)
3. Blender bundled Python from MCP (`bpy.app.binary_path_python`)
4. System Python in PATH

## Install package to Extensions repo

After build, install zip to an extension repository (prefer `user_default`) instead of legacy add-on folders.

```python
bpy.ops.extensions.package_install_files(
    filepath=r"C:\\path\\to\\your_extension-1.0.0.zip",
    repo="user_default",
    enable_on_install=True,
    overwrite=True,
)
```

Verification key pattern in preferences map:

- `bl_ext.<repo_module>.<extension_id>`

Detailed install checklist:

- `./extension-install.md`
