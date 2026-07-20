# Dependencies and Release

## Runtime Baseline

| Item | Value |
| --- | --- |
| Blender minimum | 5.1.0 |
| Validated Blender | 5.1.2, Windows x64 |
| Extension ID | `chemblender` |
| Enabled module key | `bl_ext.user_default.chemblender` |
| Extension root | `ChemBlender/` |

Use Blender's bundled NumPy. Do not install packages into Blender's global Python environment.

## RDKit Wheel

| Item | Value |
| --- | --- |
| Package version | 2026.3.3 |
| Filename | `rdkit-2026.3.3-cp313-cp313-win_amd64.whl` |
| Target | CPython 3.13, Windows x64 |
| SHA-256 | `f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48` |
| Source | `https://files.pythonhosted.org/packages/68/d0/5de3d0d7e66f0e7e7795ab94a53b826e257176c15c9ee79f15621ac040ed/rdkit-2026.3.3-cp313-cp313-win_amd64.whl` |

The wheel is downloaded to `ChemBlender/wheels/`, verified before build, declared in `blender_manifest.toml`, and ignored by Git. Runtime code only checks/imports RDKit; it never downloads or installs it.

## Local Extension Gates

1. Run `blender-mcp --help`.
2. Query Blender version, executable, Python, system, and extension repositories through MCP.
3. Download and verify the RDKit wheel.
4. Run `ChemBlender/scripts/validate_extension.py` with the MCP-discovered Blender executable.
5. Run `ChemBlender/scripts/build_extension.py`.
6. Install the ZIP into `user_default` through `bpy.ops.extensions.package_install_files`.
7. Verify module key, RDKit import, properties, `.blend` assets, and two disable/enable cycles.

## Release Gates

- Tag version equals manifest version after stripping leading `v`.
- CI downloads Blender and RDKit from pinned official locations and verifies checksums.
- Built ZIP contains the declared wheel; Git contains no `.whl`.
- Unit, validate, build, install, register, unregister, and reload checks pass.
- Publishing, pushing, PR creation, and release creation require explicit authorization.
