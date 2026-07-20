# Dependencies and Release

## Runtime Baseline

| Item | Value |
| --- | --- |
| Blender minimum | 5.1.0 |
| Validated Blender | 5.1.2, Windows x64 |
| Extension ID | `chemblender` |
| Enabled module key | `bl_ext.user_default.chemblender` |
| Extension root | `ChemBlender/` |

Use Blender's bundled NumPy and Requests. Verify their origins from an isolated `BLENDER_USER_RESOURCES` root; do not infer availability from an existing extension `.local` directory. Do not install packages into Blender's global Python environment.

## RDKit Wheel

| Item | Value |
| --- | --- |
| Package version | 2026.3.3 |
| Filename | `rdkit-2026.3.3-cp313-cp313-win_amd64.whl` |
| Target | CPython 3.13, Windows x64 |
| SHA-256 | `f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48` |
| Source | `https://files.pythonhosted.org/packages/68/d0/5de3d0d7e66f0e7e7795ab94a53b826e257176c15c9ee79f15621ac040ed/rdkit-2026.3.3-cp313-cp313-win_amd64.whl` |

The wheel is downloaded to `ChemBlender/wheels/`, verified before build, declared in `blender_manifest.toml`, and ignored by Git. Runtime code only checks/imports RDKit; it never downloads or installs it.

Pillow is not bundled while ChemBlender does not import PIL or call Pillow-dependent RDKit APIs. Adding such behavior requires a new dependency decision, pinned wheel metadata, and a clean CI install check.

## Local Extension Gates

1. Run `blender-mcp --help`.
2. Query Blender version, executable, Python, system, and extension repositories through MCP.
3. Download and verify the RDKit wheel.
4. Run `ChemBlender/scripts/validate_extension.py` with the MCP-discovered Blender executable.
5. Run `ChemBlender/scripts/build_extension.py --python <Blender Python> --blender <Blender executable>`.
6. Install and test once with a temporary `BLENDER_USER_RESOURCES` root.
7. Verify package contents, module key, representative RDKit operations, properties, installed `.blend` assets, and two disable/enable cycles.
8. Reinstall the same ZIP into the real `user_default` repository from a fresh Blender process.

## Release Gates

- Tag version equals manifest version after stripping leading `v`.
- CI downloads Blender and RDKit from pinned official locations and verifies checksums.
- Built ZIP contains the declared wheel; Git contains no `.whl`.
- Built ZIP excludes development scripts, tests, caches, and nested ZIP files.
- Unit, validate, build, isolated install, real install, register, unregister, reload, RDKit operation, and `.blend` checks pass.
- A draft pull request produces a real green GitHub Actions run and an auditable package artifact.
- GitHub-owned actions use reviewed full commit SHA pins.
- Publishing, pushing, PR creation, and release creation require explicit authorization.

On Windows, overwriting an already loaded extension may warn that old wheel DLLs cannot be removed. Use a fresh Blender process for release validation; clean CI runners do not have the previous installation.
