# ChemBlender 用户流程样例

这里保存与 `docs/user/workflows/` 配套、来源可追溯且可复现的样例。

- `inputs/` 是不可变输入。文档操作不得覆盖这些文件。
- `outputs/` 由 Blender 5.1 实测流程生成；只有通过冷启动重开、hash 和大小检查的代表性结果才会纳入仓库。
- `scripts/` 保存通过 ChemBlender 公开 Operator 复现 UI 流程的脚本。
- `results/` 保存去除本机绝对路径后的实测结果；基础流程见 [`local-2.4.0.json`](results/local-2.4.0.json)，代表样例见 [`local-representative-2.4.0.json`](results/local-representative-2.4.0.json)。
- `manifest.json` 记录每个输入的来源、取得日期、许可证、规范、运行时依赖、预期数据、实测字节数和 SHA-256。

`contract` 文件是快速语法与字段合同；`representative` 文件用于观察实际规模、帧数、层级或网格采样。几百 bytes 的合同文件并非“低分辨率”，只是覆盖范围小。坐标看原子数与单位，轨迹看 frames，晶体看 sites/cell，生物数据看 hierarchy/models，Cube 才按 grid shape/spacing 讨论采样分辨率。

从 `tests/fixtures/` 复制的合同文件是独立快照，不会在运行时引用测试目录。每个数据文件旁都有同名 `.md`，说明字段、来源、许可证、规范和插件边界；总表见[格式样例矩阵](../../docs/user/workflows/formats.md#样例矩阵)。当前全部已提交输入低于 50 MiB；新文件应尽量保持在 50 MiB 以内，任何文件都不得超过 100 MiB。

## 样例选择

| 数据范围 | 快速合同 | 代表样例 | 主要用途 |
| --- | --- | --- | --- |
| 坐标 / trajectory | water XYZ、carbon extXYZ | [TA1 XYZ 说明](inputs/xyz/ta1-paclitaxel-ccd.md)、[rMD17 aspirin 说明](inputs/extxyz/aspirin-rmd17-32.md) | 113 原子单构象、32×21 轨迹与 force/energy |
| 分子 graph / records | water MOL、mixed SDF、ethanol SMILES | [AIN MOL 说明](inputs/mol/ain-aspirin-v2000.md)、[TA1 V3000 说明](inputs/mol/ta1-paclitaxel-v3000.md)、[CCD SDF 说明](inputs/sdf/ccd-3d-showcase.md) | 显式氢、stereo、拓扑与多记录 |
| 晶体 | NaCl、Si、velocity CONTCAR | [COD 共晶说明](inputs/cif/cod-4503272-caffeine-cocrystal.md)、[64-site diamond 说明](inputs/poscar/cod-9012293-diamond-2x2x2.md) | occupancy/disorder、symmetry 与 supercell |
| 生物 / 层级 | MOL2 substructure、PDB model、PQR chain | [5SUN MOL2 说明](inputs/mol2/openbabel-5sun-protein.md)、[1D3Z PDB 说明](inputs/pdb/1d3z-ubiquitin-nmr.md)、[APBS PQR 说明](inputs/pqr/apbs-protein-rna-nb.md) | 6185 原子、10 MODEL、charge/radius 与 segment |
| Grid3D | two-dataset Cube | [64³ H₂ density 说明](inputs/cube/h2-lcao-1s-density-64.md) | 实际 Volume/Surface 采样和语义确认 |
| JSON exchange | water CJSON、v2 AtomicResult | [Avogadro CJSON 说明](inputs/cjson/avogadro-phthalocyanine.md)、[MolSSI QCSchema 说明](inputs/qcschema/molssi-water-gradient-hf.md) | envelope、formal charge、gradient/properties |
| Legacy | ChemBlender 2.1 molecule | — | 显式迁移、诊断与另存 |

## 可直接查看的结果

| 数据组 | `.blend` | `.cbq` manifest | 已保存内容 |
| --- | --- | --- | --- |
| 分子与 exchange | [molecular.blend](outputs/representative/molecular/molecular.blend) | [manifest](outputs/representative/molecular/molecular.cbq/manifest.json) | 8 种输入、Structure、Topology、records、CJSON/QCSchema 与默认 View |
| trajectory | [trajectory.blend](outputs/representative/trajectory/trajectory.blend) | [manifest](outputs/representative/trajectory/trajectory.cbq/manifest.json) | 32×21 rMD17 aspirin、energy/force 与 playback |
| 生物结构 | [biological.blend](outputs/representative/biological/biological.blend) | [manifest](outputs/representative/biological/biological.cbq/manifest.json) | 1D3Z 10 MODEL 与 APBS PQR hierarchy/charge/radius |
| 晶体 | [crystal.blend](outputs/representative/crystal/crystal.blend) | [manifest](outputs/representative/crystal/crystal.cbq/manifest.json) | COD CIF、8-site/64-site diamond 与可选 spglib 边界 |
| Grid3D | [grid.blend](outputs/representative/grid/grid.blend) | [manifest](outputs/representative/grid/grid.cbq/manifest.json) | `64³` H₂ density、Volume、正负 Surface 与 4 个 VDB cache |

- [workflow.blend](outputs/workflow-project/workflow.blend) 配套同目录的 [workflow.cbq manifest](outputs/workflow-project/workflow.cbq/manifest.json)，包含分子、晶体、轨迹、Grid Volume 和 Signed Surface 等代表性 View。
- [migrated.blend](outputs/legacy-migration/migrated.blend) 配套同目录的 [migrated.cbq manifest](outputs/legacy-migration/migrated.cbq/manifest.json)，展示 2.1 对象迁移、显式 topology 与 legacy backup collection。

以上七组文件均由 Blender 5.1.2 冷启动从仓库内当前位置重开通过。下载或复制时要保留 `.blend` 与完整同名 `.cbq/` 目录的相对位置；不要只拿 `.blend`。

操作入口见 [`docs/user/workflows/README.md`](../../docs/user/workflows/README.md)。

## 自动走查

`scripts/run_ui_workflows.py` 只调用已注册的 `bpy.ops.chemblender.*` Operator 和公开 Scene RNA，不能代替 UI 手工验收。它需要一个已安装并启用 ChemBlender 的 Blender 5.1 环境、一个显式指定且初次运行时为空的目录，以及位于该目录第一层的 JSON 报告路径。

下面的 PowerShell 命令也可由 Blender MCP 在确认实时版本、可执行文件和扩展状态后启动。不要把 `--run-dir` 指向 `inputs/` 或已有用户目录。

```powershell
$blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
$examples = (Resolve-Path "examples\user-workflows").Path
$runner = Join-Path $examples "scripts\run_ui_workflows.py"
$run = Join-Path $env:TEMP "chemblender-user-workflows"
New-Item -ItemType Directory -Path $run

& $blender --background --python $runner -- `
  --examples-root $examples `
  --run-dir $run `
  --report (Join-Path $run "report.json")
```

主流程会生成项目和迁移检查点；以下三次冷启动依次续跑，不得省略 `--resume`：

```powershell
& $blender --background (Join-Path $run "outputs\project\workflow.blend") `
  --python $runner -- --examples-root $examples --run-dir $run `
  --report (Join-Path $run "report.json") --resume `
  --checkpoint reopen --cases LIFE-SAVE-REOPEN-PREP

& $blender --background (Join-Path $examples "inputs\legacy\chemblender-2.1-molecule.blend") `
  --python $runner -- --examples-root $examples --run-dir $run `
  --report (Join-Path $run "report.json") --resume `
  --checkpoint migration --cases MIG-PREVIEW-PREP

& $blender --background (Join-Path $run "outputs\legacy\migrated.blend") `
  --python $runner -- --examples-root $examples --run-dir $run `
  --report (Join-Path $run "report.json") --resume `
  --checkpoint migration-reopen --cases MIG-PREVIEW-PREP
```

每个案例的 `operators`、`evidence`、`outputs`、耗时和错误都会原子写入 `report.json`。`prepared` 只表示等待下一次冷启动；最终判定还要填写 [`docs/user/workflows/reviews/template.md`](../../docs/user/workflows/reviews/template.md)，核对 UI 与 Agent/MCP 两条路径。

默认主流程还会生成五个 `outputs/representative/<family>/` 配对。必须分别用新 Blender 进程续跑同一个报告；最后一次才会把 `REP-SAVE-REOPEN-PREP` 从 `prepared` 改为 `passed`：

```powershell
$families = "molecular", "trajectory", "biological", "crystal", "grid"
foreach ($family in $families) {
  & $blender --background (Join-Path $run "outputs\representative\$family\$family.blend") `
    --python $runner -- --examples-root $examples --run-dir $run `
    --report (Join-Path $run "report.json") --resume `
    --checkpoint reopen --cases REP-SAVE-REOPEN-PREP
}
```
