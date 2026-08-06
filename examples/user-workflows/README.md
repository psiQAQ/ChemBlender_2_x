# ChemBlender 用户流程样例

这里保存与 `docs/user/workflows/` 配套的小型、可复现样例。

- `inputs/` 是不可变输入。文档操作不得覆盖这些文件。
- `outputs/` 由 Blender 5.1 实测流程生成；只有通过冷启动重开、hash 和大小检查的代表性结果才会纳入仓库。
- `scripts/` 保存通过 ChemBlender 公开 Operator 复现 UI 流程的脚本。
- `results/` 保存去除本机绝对路径后的实测结果；当前记录见 [`local-2.4.0.json`](results/local-2.4.0.json)。
- `manifest.json` 记录每个输入的来源、运行时依赖、预期数据、实测字节数和 SHA-256。

从 `tests/fixtures/` 复制的文件是独立快照，不会在运行时引用测试目录。`ethanol.smi` 是本地生成的最小 SMILES。当前全部输入远小于 50 MiB；新文件应尽量保持在 50 MiB 以内，任何文件都不得超过 100 MiB。

## 样例选择

| 格式族 | 样例 | 主要用途 |
| --- | --- | --- |
| XYZ / extXYZ | `water.xyz`、`carbon-trajectory.extxyz` | 单结构、多帧、cell/PBC |
| MOL / SDF / SMILES | 两版 water MOL、混合属性 SDF、ethanol SMILES | RDKit 分子记录、属性与 3D 派生 |
| CIF / POSCAR | NaCl、Si、含速度 CONTCAR | 晶体、周期边界与导出损失检查 |
| MOL2 / PDB / PQR | substructure、multi-model、with-chain | 拓扑、层级、charge/radius |
| Cube | two-datasets | Structure、Grid3D 与多 dataset 选择 |
| CJSON / QCSchema | water results、AtomicResult | 计算结果 envelope 与可支持属性 |
| Legacy | ChemBlender 2.1 molecule | 显式迁移、诊断与另存 |

## 可直接查看的结果

- [workflow.blend](outputs/workflow-project/workflow.blend) 配套同目录的 [workflow.cbq manifest](outputs/workflow-project/workflow.cbq/manifest.json)，包含分子、晶体、轨迹、Grid Volume 和 Signed Surface 等代表性 View。
- [migrated.blend](outputs/legacy-migration/migrated.blend) 配套同目录的 [migrated.cbq manifest](outputs/legacy-migration/migrated.cbq/manifest.json)，展示 2.1 对象迁移、显式 topology 与 legacy backup collection。

两组文件均由 Blender 5.1.2 冷启动从仓库内当前位置重开通过。下载或复制时要保留 `.blend` 与完整同名 `.cbq/` 目录的相对位置；不要只拿 `.blend`。

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
