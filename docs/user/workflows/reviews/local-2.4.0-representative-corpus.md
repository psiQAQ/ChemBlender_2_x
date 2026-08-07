# ChemBlender 2.4.0 代表样例人工插件使用体验检阅

本记录已填入自动准备与 Blender 5.1 实跑证据，但尚未由人按 UI 和 Agent/MCP 两条路径逐项操作。所有人工结果保持 `Not Run`，所有 required case 保持 `Incomplete`；因此当前明确阻止 tag/Release。

## Environment

- Automated evidence date/time and timezone: 2026-08-08, Asia/Shanghai
- Human reviewer: Not Run
- Windows version: Windows 10 runtime family；人工复核时补充 build
- Blender version: 5.1.2
- Blender executable: `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
- Bundled Python: 3.13.9
- Runtime system: Windows
- Extension repository: `user_default`
- Enabled key: `bl_ext.user_default.chemblender`
- Automated profile: installed `user_default`；五个 bundle 各用新后台进程 cold reopen，最终 `HEAD` 再次冷重开 Grid bundle
- Human test profile / initial dirty state: Not Run
- Display scale, language and viewport size: Not Run

## Source and package

- Version: 2.4.0（不发布新版本）
- Branch: `codex/representative-example-corpus`
- Runtime/output commit: `e9f32ae1f49d736fa63fe2961b5baa974eaebcfb`
- Runner commit: `3279f79a5300547d4b7767bc9d8e270c26195253`
- Final package-budget commit: `255cdce5245ea07aaab8523a7ae891cc99e12837`
- Package filename: `ChemBlender/chemblender-2.4.0.zip`
- Package SHA-256: `5555bbd3ebc6b8cc4066af78d5ffc929a70c72bae76b797a4cffded7a428e321`
- Package inventory: 29,977,165 bytes；189 members；32,066,803 unpacked bytes；CRC、duplicate、safe-path 和 zero-unexplained-growth budget 检查通过
- Manifest version: schema 2
- RDKit: 2026.03.3，Extension 离线 wheel
- Gemmi: 0.7.5，Extension 离线 wheel
- spglib: 可选 worker dependency；未随 Extension 打包
- Sample manifest SHA-256: `7f44322a2ce69bf9d3617ae1bca157318d5d46978faf410b1d794d932b59f78e`
- Runner result: [`local-representative-2.4.0.json`](../../../../examples/user-workflows/results/local-representative-2.4.0.json)，SHA-256 `a52b0ca75260bbc67f2272cdd6c95b4fb2e407fb8092fbffd5c7a294bf3cb696`

## Required case summary

自动 `Passed` 只写在 Evidence/Rerun result。UI 与 Agent/MCP 的 `Not Run` 使 Final case result 保持 `Incomplete`。

| Case | Required | Workflow | UI result | Agent/MCP result | Duration | Evidence | Findings | Fix commit | Rerun result | Final case result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ENV | Yes | Environment / install | Not Run | Not Run |  | package validate/build 与 live runtime 已自动核对 | 人工待检 |  | Automated Passed | Incomplete |
| IMP | Yes | Import / Preview / cancel | Not Run | Not Run |  | 基础报告与代表报告 | 人工待检 |  | Automated Passed | Incomplete |
| DATA | Yes | Process / revision validity | Not Run | Not Run |  | 基础报告与 parser contracts | 人工待检 |  |  | Automated Passed | Incomplete |
| VIEW | Yes | Structure / Grid / playback | Not Run | Not Run |  | 七个 tracked bundles | 人工待检 |  | Automated Passed | Incomplete |
| EXP | Yes | Export / loss / re-import | Not Run | Not Run |  | [`local-2.4.0.json`](../../../../examples/user-workflows/results/local-2.4.0.json) | 人工待检 |  | Automated Passed | Incomplete |
| LIFE | Yes | Save / cold reopen / recovery | Not Run | Not Run |  | 5/5 代表 bundle 自动冷重开 | 人工待检 |  | Automated Passed | Incomplete |
| MIG | Yes | Legacy preview / migration / reopen | Not Run | Not Run |  | 基础迁移报告 | 人工待检 | `4e46d63` | Automated Passed | Incomplete |
| AGENT | Yes | Public Operator / MCP / crash recovery | Not Run | Not Run |  | public Operator runner；Blender MCP live query | 人工待检 |  | Automated Passed | Incomplete |
| OUTSIDE | Yes, scope only | Generic Blender cases stay outside product scope | Not Run | Not Run |  | 基础报告中的 outside-plugin evidence | 人工待检 |  | Automated Passed | Incomplete |
| REP-MOLECULAR | Yes | 8-format molecular/exchange project | Not Run | Not Run |  | 8 imports、10 Structures、12 topologies、8 Views | 人工待检 | `5902c45`, `4f1d793` | Automated Passed | Incomplete |
| REP-TRAJECTORY | Yes | 32-frame extXYZ playback project | Not Run | Not Run |  | 32×21、energy/force、坐标变化 | 人工待检 | `91c25c5` | Automated Passed | Incomplete |
| REP-BIOLOGICAL | Yes | PDB/PQR hierarchy and MODEL project | Not Run | Not Run |  | 10 MODEL、2 hierarchy、117 residue rows | 人工待检 | `5902c45` | Automated Passed | Incomplete |
| REP-CRYSTAL | Yes | CIF/POSCAR periodic project | Not Run | Not Run |  | 3 Structures；spglib disabled reason | 人工待检 | `3279f79` | Automated Passed | Incomplete |
| REP-GRID | Yes | `64³` Grid Volume/Surface project | Not Run | Not Run |  | 1 Volume view、2 surface views、4 sidecar-local VDB | 人工待检 | `3279f79` | Automated Passed | Incomplete |

## Automated preparation evidence

- 15 个 representative 输入与 17 个 contract 输入均有相邻 Markdown、来源/许可证/规范、bytes 和 SHA-256；parser semantic suite 已覆盖全部 15 个 representative 输入。
- Blender bundled Python 全量测试：2,257 tests，26 skipped，0 failed；最终 `HEAD` 的 corpus/workflow 38/38、artifact budget 16/16 另行通过。
- 公共 Operator runner 的 `REP-MOLECULAR`、`REP-TRAJECTORY`、`REP-BIOLOGICAL`、`REP-CRYSTAL`、`REP-GRID` 和 `REP-SAVE-REOPEN-PREP` 均为 `passed`，`deferred=[]`。
- 五个仓库内 `.blend/.cbq` 配对分别由新 Blender 5.1.2 进程打开；sidecar arrays 完整，Grid 的四个 VDB 路径位于配套 sidecar。最终 Grid 重开再次确认 11 个 Project Browser rows、4 个 Volume、8 个 sidecar 文件和 `grid_volume` / `signed_isosurface` View kinds。
- 119 个新输出文件共 9,008,581 bytes；最大单文件 2,097,280 bytes；无文件达到 50 MiB 或超过 100 MiB。
- Blender MCP live query 确认 Blender 5.1.2、bundled Python 3.13.9、`user_default`、启用键、RDKit 2026.03.3、Gemmi 0.7.5、四组 Scene RNA 与所需公开 Operator。
- Extension validate/build 与 ZIP 审计通过，包体和代码解压预算已精确锁定且 unexplained-growth allowance 仍为 0。现有 `mesh.py:513` invalid-escape warning 不影响断言；spglib 缺失按可选依赖边界显示，不视为 base-install 失败。

## Representative case checklist

### REP-MOLECULAR

- Input/source: CJSON、MOL V2000/V3000、MOL2、QCSchema、SDF、SMILES、XYZ 的 8 个 representative 输入；见[导入数据](../01-import.md)。
- UI steps: 逐个 Quick Import，核对 Preview/diagnostics 并确认；在 Project Browser 检查 Structure、TopologyRecord、MolecularRecord、properties 和 View；保存新项目。
- Agent/MCP: 使用各相邻说明中的提示词，先检查 Operator RNA，只调用 `bpy.ops.chemblender.*`，不跳过 confirmation。
- Expected visible state: 10 Structure rows、12 topology rows、7 molecular records、8 Views；MOL2 unsupported sections 和 SMILES 2D 边界可见。
- UI result: Not Run
- Agent/MCP result: Not Run
- Final case result: Incomplete

### REP-TRAJECTORY

- Input/source: [`aspirin-rmd17-32.extxyz`](../../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz)。
- UI steps: 导入后选中 FrameSet 和匹配 Structure View；运行 `Configure Trajectory Playback`，比较 frame 1/32 坐标并检查 energy/force/source_index。
- Expected visible state: 32 frames、21 atoms、frame end 32；播放改变 View 坐标但不新增 source revision。
- UI result: Not Run
- Agent/MCP result: Not Run
- Final case result: Incomplete

### REP-BIOLOGICAL

- Input/source: [`1d3z-ubiquitin-nmr.pdb`](../../../../examples/user-workflows/inputs/pdb/1d3z-ubiquitin-nmr.pdb) 与 [`apbs-protein-rna-nb.pqr`](../../../../examples/user-workflows/inputs/pqr/apbs-protein-rna-nb.pqr)。
- UI steps: 核对 MODEL/hierarchy、chain/residue、charge/radius；创建 biological View，测试 MODEL playback 和选择。
- Expected visible state: frame end 10；PDB 与 PQR 各有 hierarchy；PQR 998 atoms、41 residues、2 inferred segments，22 个零 radius 保持源值。
- UI result: Not Run
- Agent/MCP result: Not Run
- Final case result: Incomplete

### REP-CRYSTAL

- Input/source: COD CIF、8-site diamond POSCAR、64-site CONTCAR；见[处理数据](../02-process.md)。
- UI steps: 核对 CIF occupancy/disorder/declared symmetry 与 POSCAR cell/site/velocity；读取 spglib availability，再决定是否调用 derive。
- Expected visible state: 三个周期 Structure/View；当前包显示 spglib dependency reason，按钮不可用时不得绕过。
- UI result: Not Run
- Agent/MCP result: Not Run
- Final case result: Incomplete

### REP-GRID

- Input/source: [`h2-lcao-1s-density-64.cube`](../../../../examples/user-workflows/inputs/cube/h2-lcao-1s-density-64.cube)。
- UI steps: 核对 `64×64×64`、bohr origin/steps 和教学模型边界；确认 semantic/unit 后创建 Volume 与 Signed Surface；保存并冷重开。
- Expected visible state: 一个 grid volume View、两个 signed isosurface Views、四个 sidecar-local VDB；不把解析 LCAO 写成 HF/DFT。
- UI result: Not Run
- Agent/MCP result: Not Run
- Final case result: Incomplete

## Saved and exported files

`File SHA-256` 首项是 `.blend`，Notes 中是 sidecar `manifest.json` 文件 SHA-256。完整 119-file inventory 见 [`manifest.json`](../../../../examples/user-workflows/manifest.json)。

| Path | Role | File size | File SHA-256 | Reopen state | External references | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `outputs/representative/biological/biological.blend` + `.cbq/` | biological | 162,372 + 574,500 bytes | `2ad663b7ebe1b125cc82f102fe7b73fa5fbc698eb39a717f7377060c5c1388db` | Automated Passed / Human Not Run | source locator hint only | manifest file `ccbddf9be3b1badc5ad740ec2fe614fdccdc40fcb0518d8e7afefeaa8d69c851` |
| `outputs/representative/crystal/crystal.blend` + `.cbq/` | crystal | 172,350 + 65,049 bytes | `40fc914c896e43013b0796093b4ced0a64df74bf825c1d8500de271c6b77c5ea` | Automated Passed / Human Not Run | source locator hint only | manifest file `5deffe29d3bf2fa887af3a691bbbb1e3c02034098dfe9eca2db85a934e102ca6` |
| `outputs/representative/grid/grid.blend` + `.cbq/` | Grid3D | 107,971 + 5,716,301 bytes | `964599b7f9b57b06fad509d37c03153892fe2827efd14137b332c4d167b5758a` | Automated Passed / Human Not Run | four VDB paths sidecar-local | manifest file `c0d50bcc1e29292ccf36d52bd721336b85f0817692907b9780a0e942eb6275e1` |
| `outputs/representative/molecular/molecular.blend` + `.cbq/` | molecular/exchange | 285,732 + 1,709,949 bytes | `4d1325b8a8d59837f9661b8871ecaa5fd7ff349c44384f8f89967616916aeaff` | Automated Passed / Human Not Run | source locator hint only | manifest file `db74de042ae879b0d5161ec0f7573bfcb360318321db991171bc24ba7ae849da` |
| `outputs/representative/trajectory/trajectory.blend` + `.cbq/` | trajectory | 165,756 + 48,601 bytes | `9e0ebe2a7dfd00aeee8d6820c114dbc53c4b15390d985c176b1829d2c0bee618` | Automated Passed / Human Not Run | source locator hint only | manifest file `15e934a68220d809cf3c0d9c5af7f3bfda14ba08b093bcc0779cde2258b692f6` |

Project UUID / internal sidecar manifest hash：

- biological: `0f4e6fbf-7325-4e09-9b6f-5134fc351a54` / `cdd1d91a70a2e80444f7c2e77c16d1f857a1bbd3a263387cba3a7e90c1447d24`
- crystal: `eae7cb57-28de-4d67-b63e-297b6f7db103` / `edebc0f2a9525b0acca396feabca02c7abc69cd2c55d66d93ba2f6de8ac973a6`
- grid: `8eea3e21-8d5e-48ab-876b-13abdd2dfa79` / `47f8f2eed84b1842092ab25781eef5a076148016a6e60fd3330f5bce0207c9f0`
- molecular: `ff16d8e1-f743-4a46-86a0-ff7876a8d800` / `2d515796b62ac750a4acf74abb934dfa329a6bcc99d8b0e86fa150a93389f101`
- trajectory: `d41c4505-f07d-4a6f-91aa-0f9b75ef45d7` / `874b1cd96406dcd007644a96fd389611d672c335ad96f2c1ae146f67cfb06c2b`

## Findings and fixes already exercised by automation

1. PQR 的 998 条 element-inference 记录级问题曾淹没 Preview；`5902c45` 保留底层明细并在 UI 汇总为一条 warning。
2. Open Babel 5SUN MOL2 含 unsupported `un` bond，合法地没有 topology；`4f1d793` 让 Preview 跳过无 topology 的 conformer grouping，而不伪造键。
3. 通用 extXYZ FrameSet 原先没有公开 playback 入口；`91c25c5` 在 Project Browser 提供 `bpy.ops.chemblender.configure_trajectory_playback`。
4. runner 曾把 Gemmi 当成 symmetry derive 后端，并把 signed Surface 错当成 Mesh；`3279f79` 改为可选 spglib 边界和公开 View-kind 合同。
5. 最终 ZIP audit 发现预算仍指向修复前包体；`255cdce` 将 package/member/code 三个基线精确更新到已验证产物，所有 unexplained-growth allowance 保持为 0。

这些修复均有 RED/GREEN 和 Blender runtime 证据，但仍需人在本记录中确认可发现性、文案、视觉结果和操作感受。

## Final review

- Required cases Passed: 0
- Required cases Failed: 0
- Required cases Blocked: 0
- Required cases Incomplete: 14
- Open findings: 人工检查尚未开始；自动化未留下未修复的 base-install defect
- Deferred external cases requiring approval: None；spglib 为已记录的可选边界，不是本轮安装请求
- Final result: Blocked（manual UI 与 Agent/MCP 均 Not Run）
- Reviewer sign-off and time: Not Run

执行时从[工作流中心](../README.md)按导入、处理、展示、导出、保存/恢复、Agent/MCP 和插件外案例顺序完成；任何 finding 都保留原始失败、修复 commit 与重跑结果。自动 runner 全绿不能覆盖人工失败或未执行状态。
