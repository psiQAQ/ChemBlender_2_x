# Dependency Policy

Use this policy when a Blender extension needs optional third-party Python packages.

## Core rules

- Do not install packages into Blender bundled Python global `site-packages`.
- Development or internal extensions may use `deps/site-packages` with `pip install --target`.
- Add `deps/site-packages` to `sys.path` when the add-on is enabled.
- Remove `deps/site-packages` from `sys.path` when the add-on is disabled.
- Do not silently install dependencies in `register()`, module import, or add-on enable flow.
- Install only after the user explicitly clicks an install button in `AddonPreferences`.
- Do not import optional third-party packages at module top level.
- Delay optional imports until an operator `execute()` method or a concrete business function needs them.

## Template defaults

- Keep dependency declarations in `utils/dependency_manager.py`.
- Use `sys.executable -m pip install --target deps/site-packages` for private installs.
- Default to the Tsinghua PyPI mirror, but expose a setting so users can disable it.
- Support `--no-cache-dir` as a user-facing option.
- Show dependency status, import origin, and private path status in `AddonPreferences`.

## Release guidance

- Do not ship a release build with `deps/site-packages` copied into the source tree by default.
- Prefer `wheels = [...]` in `blender_manifest.toml` for published extensions.
- Declare `network` permission if the add-on can install from PyPI or a mirror.
- For `torch`, `opencv-python`, `scipy`, `open3d`, CUDA packages, and other heavy binary dependencies, prefer an external Python service or environment.
- Communicate with heavy external environments through `subprocess`, sockets, HTTP, or MCP instead of forcing them into Blender Python.
