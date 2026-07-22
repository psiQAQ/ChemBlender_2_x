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

## Optional Quantum Core

| Item | Value |
| --- | --- |
| Package | `cclib==1.8.1` |
| Runtime boundary | independent CPython core environment |
| Reference source | `submodules/cclib` at `07260dd0394cb1a2381d4d897746d727a12ad6ce` (`v1.8.1`) |
| License | BSD-3-Clause |
| Transitive requirements | NumPy, SciPy, periodictable, packaging |

cclib is an optional parser backend, not a Blender Extension wheel. `ChemBlender.core` and `ChemBlender.core.cclib_adapter` import without loading cclib or its numerical stack; only `parse_cclib_output()` loads the dependency. Developers may install the pinned submodule into an ignored isolated environment for integration tests. Never install it during Blender import, registration, enable, or file parsing fallback.

| Item | Value |
| --- | --- |
| Package | `qc-iodata==1.0.1` |
| Runtime boundary | independent CPython core environment |
| Reference source | `submodules/iodata` at `adab5813713ba64641565eb2a8c11803a4e9bba6` (`v1.0.1`) |
| License | GPL-3.0-or-later |
| Transitive requirements | NumPy, SciPy, attrs |

IOData is the optional FCHK/Molden basis, orbital, AO-basis 1-RDM, and effective nuclear-charge parser. Its adapter preserves atomic units, basis conventions, total/spin matrix roles, and ECP-aware `atcorenums` in ChemBlender-owned entities. Neither IOData nor its submodule is packaged in the Blender Extension; only `parse_iodata_wavefunction()` loads it in an external core environment.

| Item | Value |
| --- | --- |
| Package | `qc-gbasis==0.1.0` (import name `gbasis`) |
| Runtime boundary | independent CPython worker/core environment |
| Reference source | `submodules/gbasis` at `6440c84f3fcf8d42cbd9b5de53ae8d70bed4cd4f` (`v0.1.0`) |
| License | GPL-3.0-or-later |
| Transitive requirements | NumPy, SciPy, SymPy, importlib-resources |
| Recommended worker Python | 3.12 on Windows |

GBasis evaluates normalized Gaussian basis functions, molecular orbitals, total/spin density and electrostatic-potential grids. Install the modern distribution as `qc-gbasis`; do not install the withdrawn legacy `gbasis` distribution. Version 0.1.0 declares `numpy<2` on Windows, so its standard dependency set has no Python 3.13-compatible NumPy wheel. A Python 3.12/NumPy 1.26.4 worker is the supported local baseline. Python 3.13 with forced NumPy 2.5.1 produced matching probe results but is not a supported installation path. GBasis, IOData, SciPy and their submodules remain outside the Blender Extension ZIP.

| Item | Value |
| --- | --- |
| Packages | `gemmi==0.7.5`, `spglib==2.7.0` |
| Runtime boundary | independent CPython worker/core environment |
| Reference sources | `submodules/gemmi` at `5cc1c23c6007e0e6cbd69289c6f7c0bff50e943e`; `submodules/spglib` at `12355c77fb7c505a55f52cae36341d73b781a065` |
| Licenses | Gemmi MPL-2.0; spglib BSD-3-Clause |
| Transitive requirements | spglib requires NumPy; Gemmi wheel has no required Python dependency |

Gemmi owns CIF parsing and raw-envelope access; spglib owns symmetry search and standardization. Both adapters use late imports. They are tested in an ignored Python 3.13 environment and remain outside the Blender Extension ZIP. A future distributed worker must retain the applicable license files and notices.

| Item | Value |
| --- | --- |
| Packages | `ase==3.29.0`, `pymatgen-core==2026.7.16` |
| Runtime boundary | independent CPython worker/core environment |
| Reference sources | `submodules/ase` at `f27c0005ae6a67ea419f996e728668865bfc1f86`; `submodules/pymatgen-core` at `488ad74cc5ecaba5d24c1726e2762fb47f31f5ef` |
| Licenses | ASE LGPL-2.1-or-later; pymatgen-core MIT |
| Scope | POSCAR/CONTCAR/extXYZ, CHGCAR/PARCHG/ELFCAR/LOCPOT and vasprun.xml band/DOS adapters |

The `pymatgen` 2026.5.4 distribution is a metapackage that resolves the actual
implementation separately. ChemBlender pins `pymatgen-core` directly so reviewed
source and tested runtime match. ASE and pymatgen-core are late-imported and remain
outside the Blender Extension ZIP.

| Item | Value |
| --- | --- |
| Package | `phonopy==4.4.0` |
| Runtime boundary | independent CPython worker/core environment |
| Reference source | `submodules/phonopy` at `2df40f4865d477f44d3b5d1ebcafc0b4af878e35` |
| License | BSD-3-Clause |
| Scope | q-point frequencies, complex eigenvectors, group velocities and periodic mode frames |

phonopy and its scientific stack are late-imported and remain outside the Blender
Extension ZIP. The first adapter consumes an in-memory `Phonopy` object after
`run_qpoints(..., with_eigenvectors=True)`; it does not bundle h5py or matplotlib.

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
- `CHANGELOG.md` has exactly one non-empty dated entry for the manifest version; future tags contain that same entry.
- CI downloads Blender and RDKit from pinned official locations and verifies checksums.
- Built ZIP contains the declared wheel; Git contains no `.whl`.
- Built ZIP excludes development scripts, tests, caches, and nested ZIP files.
- Unit, validate, build, isolated install, real install, register, unregister, reload, RDKit operation, and `.blend` checks pass.
- Pull-request and maintained `main` runs are green; the exact annotated tag produces the authoritative package artifact for publication.
- GitHub-owned actions use reviewed full commit SHA pins.
- Run `extension-release` with `publish=false` before the separately authorized `publish=true` dispatch.
- The Release workflow selects the successful exact-SHA tag run, re-verifies its ZIP and checksum, extracts the matching changelog entry as the Release body, creates a draft, compares GitHub asset digests, and only then publishes; it never rebuilds the package.
- Only the conditional publish job has `contents: write`; routine package CI and Release verification remain read-only.
- Publishing, pushing, PR creation, and release creation require explicit authorization.

On Windows, overwriting an already loaded extension may warn that old wheel DLLs cannot be removed. Use a fresh Blender process for release validation; clean CI runners do not have the previous installation.

For a persistent `user_default` reinstall, a fresh process is insufficient when the old
extension is auto-enabled at startup. Disable it and save preferences, exit Blender, install
from a second cold process, then launch a third process to verify the enabled key and real
RDKit import. A same-process smoke result does not prove the shared wheel remains complete
after exit.
