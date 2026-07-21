# Extension Install (Extension-Native)

Use this document for package install and delivery validation.

## Rule

- Extension-only projects must be installed through Blender Extensions repositories.
- Do not deploy extension source to legacy add-on directories.

## Standard flow

1. Ensure extension root contains `blender_manifest.toml`.
2. Build package from extension root:

```bash
python scripts/build_extension.py
```

Build output guidance:

- Default: place zip in the parent directory of the extension source folder.
- If needed, use another dedicated build directory outside the extension source directory.
- The final zip path must be readable by Blender host system.

3. Install generated zip into a repo (prefer `user_default`):

```python
bpy.ops.extensions.package_install_files(
    filepath=r"C:\\path\\to\\your_extension-1.0.0.zip",
    repo="user_default",
    enable_on_install=True,
    overwrite=True,
)
```

4. Verify enable state key pattern in preferences add-on map:

- `bl_ext.<repo_module>.<extension_id>`

## Cross-system path reminder

When agent runtime and Blender runtime are on different systems:

- Do not pass agent-only local paths to `filepath`.
- Use a path format that Blender host can resolve (for example Windows path or host-accessible UNC path).
- If needed, stage/copy zip into a host-local temp/build directory before install.

Minimal path conversion example (WSL -> Blender-readable on Windows):

```text
WSL path: /home/<user>/project/my_ext-1.0.0.zip
Blender filepath: \\wsl.localhost\<distro>\home\<user>\project\my_ext-1.0.0.zip
Use this filepath in bpy.ops.extensions.package_install_files(filepath=...)
```

## Quick checks

- Install operator returns `{'FINISHED'}`.
- Target repo directory contains `<extension_id>/`.
- Preferences add-ons contain expected extension key.
