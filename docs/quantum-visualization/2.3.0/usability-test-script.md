# ChemBlender 2.3.0 RC 可用性验收脚本

本脚本验证真实 Blender Extension 用户路径。每次执行都使用全新的
`BLENDER_USER_RESOURCES`、`TEMP` 和 `TMP`，通过 Blender Extensions 安装 ZIP；
不得把源码复制到 legacy add-on 目录。

## 环境与输入

- Windows x64，Blender 5.1.2 或更高的 5.1 版本。
- 当前 checkout 构建出的 `ChemBlender/chemblender-2.3.0-alpha.1.zip`。
- 固定输入：
  `tests/fixtures/xyz/water.xyz`、
  `tests/fixtures/sdf/records.sdf`、
  `tests/fixtures/cube/sheared.cube`、
  `tests/fixtures/cif/partial-disorder.cif` 和
  `tests/fixtures/pdb/altloc.pdb`。
- legacy 场景：
  `chemblender-2.1-molecule.blend`
  (`36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4`)、
  `chemblender-2.2-crystal.blend`
  (`f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a`) 和
  `chemblender-2.2-edited-scaffold.blend`
  (`a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740`)。

开始前记录 Blender/Python 版本、CPU、内存、checkout SHA、ZIP SHA-256 和 wall
clock。每项任务从触发操作开始计时，到下表验收条件全部成立时停止。

## 记录字段

每项都必须记录：

- `Completion`：Passed、Failed 或 Not Run。
- `Elapsed time`：wall-clock 秒数；共享自动化场景须明确标记。
- `Errors`：错误文本或 `None`；warning 与 error 分开记录。
- `Help required`：None、内置提示、文档或人工协助。
- `Scientific misunderstanding`：误解的物理/化学语义及纠正方式，或 `None`。

## 用户任务

| ID | 操作 | 验收条件 |
| --- | --- | --- |
| U01 | 从 ZIP 安装并启用 Extension | `bl_ext.user_default.chemblender` 启用；RDKit 与 Gemmi 可导入；没有 legacy add-on copy |
| U02 | Quick Import 导入 XYZ | 预览显示 Structure；确认后创建绑定正确 revision 的 Structure View |
| U03 | 导入 SDF 并确认 conformers 分组 | review 后生成 `ConformerSet`；Project Browser 可见；SDF export 可重新解析为两条记录 |
| U04 | 导入 Cube、查看 diagnostics 并 resolve Cube semantic | 原 Grid 保持 Ambiguous；派生 Grid 为 Complete `scalar_field`；signed surface 绑定派生 revision |
| U05 | 导入 CIF | fractional/cell/occupancy/ADP 保持；Structure View 可保存、reopen 和 CIF export |
| U06 | 导入 PDB | hierarchy、altloc、occupancy 与默认可见性保持；保存、reopen 后仍一致 |
| U07 | 浏览并导出 diagnostics | 可分页查看；UI preview 有界；JSON/Markdown canonical export 完整 |
| U08 | save/reopen 项目 | `.blend` 与 `.cbq` 建立一致 link；clean save 不改 manifest；reopen 恢复实体和 View bindings |
| U09 | 处理 revision 提示 | Keep Current、Update Selected Views 和 Comparison View 只作用于目标 logical View |
| U10 | 执行 scientific edit | 原 Structure 不变；生成带 `USER_EDITED` topology/provenance 的派生 Structure |
| U11 | export 并语义重导入 | XYZ/extXYZ/SDF/CIF 目标可重读；需确认的 loss preview 不被绕过 |
| U12 | migrate hash-locked legacy scene | 显式 preview/confirm；原对象进入 backup；新 Project/View 保存并 reopen；三份 fixture 均通过 |

## 自动化复验

下面的既有 smoke 是上述用户任务的可重复 operator-level oracle；它调用真实
`bpy.ops`、安装 ZIP，并检查科学 identity、单位、revision、save/reopen 和 export。

```powershell
$blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
$pythonBin = "C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe"
$profile = "D:\cb-usability-fresh"
$env:BLENDER_USER_RESOURCES = "$profile\user"
$env:TEMP = "$profile\tmp"
$env:TMP = "$profile\tmp"

& $blender --command extension validate ChemBlender
& $blender --command extension build --source-dir ChemBlender --output-dir ChemBlender
& $blender --background --factory-startup --python-exit-code 1 `
  --python tests/blender_smoke.py -- `
  ChemBlender/chemblender-2.3.0-alpha.1.zip

$env:BLENDER_EXECUTABLE = $blender
& $pythonBin -m unittest tests.test_legacy_migration_blender -v
```

通过条件是进程 exit `0`、显式 `PASS` marker 存在且所有任务验收条件成立；仅有 ZIP
或 manifest 可解析不算通过。

## 问题分级

- `Blocker`：数据丢失/损坏、错误科学映射、无法恢复或保存、崩溃，或核心任务失败。
- `Major`：主路径仍可完成，但需要未说明的人工绕行，或产生会误导决策的 UI/诊断。
- `Minor`：不改变科学结果、持久化和核心任务完成度的可发现性、文案或非阻断 warning。

RC scope freeze 后只修 `Blocker`。每个修复必须先有复现测试，再有 focused commit；
`Major`/`Minor` 记录到结果和后续计划，不在本任务扩展产品范围。
