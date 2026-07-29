# Wave 2 晶体性能基线

## 结论

2026-07-29 在 Blender 5.1.2 的独立后台进程中运行
`ChemBlender/scripts/benchmark_crystal.py`。五次计时样本前执行一次 warmup。
CIF 1000-site Reader API preview 和 1000-site 默认晶体视图均满足 2.3.0
预算；对称展开、10×10×10 supercell 与 POSCAR import 记录为后续 Wave 的
比较基线。

## 环境

| 项目 | 值 |
| --- | --- |
| OS | Windows 10.0.19045 |
| CPU | AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD；16 logical CPUs |
| RAM | 17,042,837,504 bytes |
| Blender | 5.1.2 |
| Python | 3.13.9 |
| NumPy | 2.3.4 |
| Gemmi | 0.7.5 |
| samples | 5（每项先 warmup 1 次） |
| memory | `tracemalloc` peak；不代表 NumPy/Blender native allocation |

## 结果

| 操作 | 工作量 | median | p95 | peak Python bytes | 预算判断 |
| --- | --- | ---: | ---: | ---: | --- |
| CIF preview | 1000 sites；Reader API preflight + staged `ImportBatch` | 0.055481 s | 0.056431 s | 541,641 | Passed：≤ 0.5 s |
| symmetry expansion | quartz；2 source sites；6 declared operations | 0.001744 s | 0.001774 s | 14,712 | Baseline |
| supercell | quartz；10×10×10 | 0.521372 s | 0.537380 s | 10,448,848 | Baseline |
| POSCAR import | `si.POSCAR`；2 atoms | 0.001520 s | 0.001675 s | 9,299 | Baseline |
| crystal view creation | 1000 sites；`source_sites`；hot after warmup | 0.905908 s | 0.942479 s | 2,127,577 | Passed：≤ 3 s |

`CIF preview` 使用真实 Reader API registry、reader override、staging 与
`ImportPreview` 生成路径，不以单独调用 Gemmi parser 代替产品 preflight。
`crystal view creation` 在 Blender 中调用真实
`create_periodic_structure_view()`，每次样本后删除本轮对象；node contract
在 warmup 后保持 hot 状态。

## 复现

```powershell
$env:PYTHONPATH = (Resolve-Path ".agents/cache/qualification-site").Path

& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background `
  --factory-startup `
  --python "ChemBlender/scripts/benchmark_crystal.py" `
  -- `
  --samples 5 `
  --cif-atom-count 1000 `
  --supercell 10 `
  --include-blender-view `
  --output ".agents/cache/wave2-crystal-blender.json"
```

`qualification-site` 只包含 manifest 已锁定的本地
`gemmi-0.7.5-cp313-cp313-win_amd64.whl` 与
`rdkit-2026.3.3-cp313-cp313-win_amd64.whl` 解包内容；没有修改 Blender
global `site-packages`。
