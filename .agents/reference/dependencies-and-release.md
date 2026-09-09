# Dependencies and Release

## 当前迁移的依赖门槛

按[决策0044](../decisions/0044-cbq-viewer-local-processor-boundary.md)，L6 外部功能等价、编辑闭环、性能、取消、数据一致性和生命周期门槛已经全部通过。正式 Viewer 从 L7 起不声明、暂存、下载或打包 RDKit、Gemmi 及其他科学 wheel；manifest、空依赖清单、staging、CI 和包审计必须一致。

Blender仅使用自带NumPy及本地显示代码，共享cbq_core按源码hash打包；原始解析和重计算在外部prepare包。Blender只配置全局本地可执行文件，不配置科学环境路径、不执行pip/uv、不修改全局Python。下方旧 wheel 来源及哈希仅保留为历史版本复现依据，不是当前 Viewer 安装输入。

项目根uv init/uv venv及缓存科学/Fermi/critic2环境已获用户批准。版本隔离和兼容锁详见[依赖提案](../../examples/scientific-visualization/dependencies/PROPOSAL.md)。外部包将构建wheel/sdist供后续PyPI发布，本次不发布。

## 2.5 双制品兼容锁

| 表面 | 版本/边界 |
| --- | --- |
| Blender Extension | `ChemBlender 2.5.0`，无科学 wheel |
| Standard processor | `chemblender-prepare 0.1.0`，Python 3.12 `uv tool install --python 3.12 "chemblender-prepare[formats]"` |
| Standard dependencies | NumPy、RDKit、Gemmi，仅存在于 tool 环境 |
| Automation | Worker Protocol `1`，单一 `chemblender-prepare.exe` 绝对路径 |
| Reader extension | `chemblender_prepare.reader_api`，token `1.0-rc1` |
| Python modules | `core.*` 与 GUI helpers 为内部实现，不承诺通用 SDK |

本地发布必须同时生成 Extension ZIP、prepare wheel/sdist、SHA-256、许可/依赖清单、资格报告和中英离线 SOP。PyPI 与本地 wheel 两种安装命令都写入 SOP，但在首次发布前只验收本地 wheel；远端发布仍需用户单独授权。

以下运行基线及依赖段落含旧交付依据；当前迁移验收以active任务和实际运行证据为准。

## Runtime Baseline

| Item | Value |
| --- | --- |
| Blender minimum | 5.1.0 |
| Validated Blender | 5.1.2, Windows x64 |
| Extension ID | `chemblender` |
| Enabled module key | `bl_ext.user_default.chemblender` |
| Extension root | `ChemBlender/` |

Use Blender's bundled NumPy and Requests. Verify their origins from an isolated `BLENDER_USER_RESOURCES` root; do not infer availability from an existing extension `.local` directory. Do not install packages into Blender's global Python environment.

## 历史 RDKit Wheel 来源

| Item | Value |
| --- | --- |
| Package version | 2026.3.3 |
| Filename | `rdkit-2026.3.3-cp313-cp313-win_amd64.whl` |
| Target | CPython 3.13, Windows x64 |
| SHA-256 | `f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48` |
| Source | `https://files.pythonhosted.org/packages/68/d0/5de3d0d7e66f0e7e7795ab94a53b826e257176c15c9ee79f15621ac040ed/rdkit-2026.3.3-cp313-cp313-win_amd64.whl` |
| Compressed / unpacked | 24,618,400 / 57,121,218 bytes |
| License | BSD-3-Clause; wheel path `rdkit-2026.3.3.dist-info/LICENSE.md` |

该 artifact 仅用于 2.2/2.3 及早期 2.4 构建复现。当前 Viewer 的 `blender_manifest.toml` 不声明它，staging、CI 和运行时均不下载、安装或导入 RDKit；相关操作属于外部 `chemblender-prepare` 环境。

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

The read-only `optional-qc-core` workflow keeps these backends outside the
extension package: cclib and IOData run in isolated CPython 3.13 environments,
while GBasis runs in CPython 3.12 with NumPy 1.26.4. Its per-backend exact
runtime locks are `.github/constraints/cclib-py313.txt`,
`.github/constraints/iodata-py313.txt` and
`.github/constraints/gbasis-py312.txt`. Each lock contains the direct package
and every resolved runtime dependency (not installer tooling); it must be
derived from the pinned submodule metadata and a matching `pip --dry-run
--report` resolution before changing the workflow. CI uses the file for both
`pip -c` and runtime `importlib.metadata` verification. Before each explicit
adapter module list runs, CI checks the recorded submodule commit and fixture
SHA-256 values; its stdlib runner rejects every non-ordinary result, including
targeted skips, expected failures, unexpected successes, subtest failure/error,
load errors and zero discovery instead of converting a missing optional backend
into success.

## 历史 Gemmi Wheel 来源

| Item | Value |
| --- | --- |
| Package version | `gemmi==0.7.5` |
| Filename | `gemmi-0.7.5-cp313-cp313-win_amd64.whl` |
| Target | CPython 3.13, Windows x64 |
| SHA-256 | `ad1f72ffa24adbfaf259e11471f6f071a668667f6ca846051f3bfea024fd337d` |
| Source | `https://files.pythonhosted.org/packages/ee/ab/7d7463cda94f8b68b969ea97aaad679655a0e436efd6a643e528a8de114e/gemmi-0.7.5-cp313-cp313-win_amd64.whl` |
| Compressed / unpacked | 2,270,352 / 5,345,458 bytes |
| License | MPL-2.0; wheel path `gemmi-0.7.5.dist-info/licenses/LICENSE.txt` |
| Transitive requirements | None |

该 artifact 仅用于 2.3 及早期 2.4 构建复现。当前 Viewer 不打包或导入 Gemmi；CIF 解析和 raw-envelope 处理属于外部 prepare 环境，Gemmi 对象仍不得进入项目、CBQ canonical document 或 Viewer UI。

## Machine-readable Bundled Inventory

`ChemBlender/dependencies.toml` is the canonical bundled-dependency inventory.
The formal Viewer records `dependency = []`, and `blender_manifest.toml` omits
`wheels`. Any future bundled dependency requires a new decision and must add its
version, filename, platform, ABI, fixed URL, SHA-256, SPDX license, in-wheel
license path and size ceilings together.

Run the deterministic empty-inventory check with Blender Python:

```powershell
& <Blender Python> ChemBlender/scripts/dependency_inventory.py `
  --manifest ChemBlender/blender_manifest.toml `
  --output wheel-inventory.json `
  --license-copy-list wheel-license-copy-list.json
```

The standard-library-only CLI currently emits `{"wheels":[]}` and an empty
license copy list. Its generic non-empty path remains fail-closed on manifest
paths, SHA-256, archive member paths, license sources and size ceilings. It does
not download, install, extract or delete data. External prepare packages remain
outside the Blender manifest.

## Artifact Size Budget

`.github/artifact-budgets.json` remains the versioned package-budget authority;
`allowed_unexplained_growth_bytes` stays zero. Its exact wheel-free package and
resource baseline is updated only from the final L8 artifact, not estimated from
an intermediate build. A smaller ZIP does not by itself authorize a baseline or
dependency change.

| Item | Value |
| --- | --- |
| Package | `spglib==2.7.0` |
| Runtime boundary | independent CPython worker/core environment |
| Reference source | `submodules/spglib` at `12355c77fb7c505a55f52cae36341d73b781a065` |
| License | BSD-3-Clause |
| Transitive requirements | NumPy |

spglib owns optional symmetry search and standardization. It remains outside
the Blender Extension ZIP and cannot be a CIF import requirement.

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

| Item | Value |
| --- | --- |
| Package | optional `PyProcar==6.5.0` worker extra |
| Runtime boundary | isolated worker environment; separate from NumPy 2.x qc-core |
| Reference source | `submodules/pyprocar` at `4a2ec9049af78fdd35b6214eef68fe40e5f356ed` |
| License | GPL-3.0 |
| Scope | Fermi-surface mesh, band identity, projection, spin texture and velocity |

PyProcar requires `numpy<2.0` plus PyVista/VTK, scikit-image, matplotlib and other
plotting dependencies. ChemBlender accepts its PyVista-compatible output through a
neutral adapter; none of this stack enters the Blender Extension or base qc-core.

## Optional Workflow and Exchange

| Component | Pinned reference | Runtime boundary | Current scope |
| --- | --- | --- | --- |
| QCElemental | `v0.50.4` / `46034a0` | external core/worker | QCSchema v1/v2 fixtures and schema review; no runtime lock-in |
| QCEngine | `v0.50.0` / `d1842c4` | external worker | optional `qcschema.compute@1`; delayed import |
| Avogadro libs | `1.103.0` / `5d5d11f` | reference only | CJSON field/convention review |
| critic2 | `4b5dec9` | external executable | descriptor, safe process boundary and JSON topology adapter |
| Multiwfn | not pinned | external executable | descriptor only; no interactive menu automation |
| QCArchive/AiiDA/NOMAD | SDK not pinned | optional external worker | versioned read-only connector request and offline replay only |

These components, `worker/`, all submodules, fixtures and tests are excluded from the
Extension ZIP. Enabling an online connector or executable requires a separate dependency,
license, authentication and deployment decision; credential values never enter `.cbq`.

## Local Extension Gates

1. Run `blender-mcp --help`.
2. Query Blender version, executable, Python, system, and extension repositories through MCP.
3. Generate the empty dependency inventory and license-copy list.
4. Run `ChemBlender/scripts/validate_extension.py` with the MCP-discovered Blender executable.
5. Run `ChemBlender/scripts/build_extension.py --python <Blender Python> --blender <Blender executable>`.
6. Install and test once with a temporary `BLENDER_USER_RESOURCES` root.
7. Verify zero `.whl`, `find_spec("rdkit") is None`, `find_spec("gemmi") is None`, the module key, CBQ display/edit/reopen, installed `.blend` assets, and two disable/enable cycles.
8. Reinstall the same ZIP into the real `user_default` repository from a fresh Blender process when release validation is authorized.

## 人工插件使用体验检阅

After the local installed-product gates pass, copy the tracked
[review template](../../docs/user/workflows/reviews/template.md) to
`reviews/<version>.md` and run the version-neutral
[UX-GATE](../../docs/user/workflows/reviews/README.md) against the same package.
Record the manual UI result and Agent/MCP result for every required case, including
real save/cold-reopen and format-specific output evidence. The automated public-
Operator runner accompanies this record but never replaces manual evidence.

Any required case with status `Incomplete`, `Failed`, or `Blocked` blocks the
tag/Release. `OUTSIDE` is required only to prove that generic Blender scene,
material and render work remains clearly outside ChemBlender product scope; it
does not judge scientific correctness. Commit the completed review before tag or
Release authorization. Do not infer that a version passed because the template or
an older review exists.

## Release Gates

- Tag version equals manifest version after stripping leading `v`.
- `CHANGELOG.md` has exactly one non-empty dated entry for the manifest version; future tags contain that same entry.
- CI downloads Blender from its pinned official location and verifies its checksum; it does not download scientific wheels.
- CI emits the deterministic empty `wheel-inventory.json` and license-copy list from `dependencies.toml` before package artifact upload.
- Package CI also emits `artifact-size.json` and verifies the ZIP/package digest in explicit `package-ci` mode before its only upload.
- Built ZIP contains no `.whl`; Git contains no `.whl`.
- Built ZIP excludes development scripts, tests, caches, and nested ZIP files.
- Unit, validate, build, isolated install, real install, register, unregister, reload, CBQ display/edit/reopen, dependency-absence and `.blend` checks pass.
- Pull-request and maintained `main` runs are green; the exact annotated tag produces the authoritative package artifact for publication.
- GitHub-owned actions use reviewed full commit SHA pins.
- Run `extension-release` with `publish=false` before the separately authorized `publish=true` dispatch.
- The Release workflow selects the successful exact-SHA tag run, re-verifies its ZIP and checksum, extracts the matching changelog entry as the Release body, creates a draft, compares GitHub asset digests, and only then publishes; it never rebuilds the package.
- Only the conditional publish job has `contents: write`; routine package CI and Release verification remain read-only.
- Publishing, pushing, PR creation, and release creation require explicit authorization.

On Windows, upgrading from an historical wheel-bearing package may warn that its already loaded DLLs cannot be removed. Exit that old Blender process before installing the wheel-free Viewer; clean profiles and CI runners do not have this legacy lock.

For a persistent `user_default` reinstall, disable an auto-enabled old extension and save
preferences, exit Blender, install from a second cold process, then launch a third process
to verify the enabled key, zero packaged wheels and CBQ Viewer lifecycle. A same-process
smoke result does not prove cold-start behavior.
