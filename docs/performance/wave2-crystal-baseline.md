# Wave 2 晶体性能基线

## 结论

2026-07-29 在 Blender 5.1.2 的独立后台进程中运行
`ChemBlender/scripts/benchmark_crystal.py`。先记录一次 cold 样本，再记录五次
hot 样本。
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
| samples | 1 cold + 5 hot |
| memory | `tracemalloc` peak；不代表 NumPy/Blender native allocation |

## 结果

| 操作 | 工作量 | cold | hot median | hot p95 | hot peak Python bytes | 预算判断 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| CIF preview | 1000 sites；Reader API preflight + staged `ImportBatch` + CIF summary | 0.169705 s | 0.056856 s | 0.058387 s | 545,885 | Passed：cold/hot ≤ 0.5 s |
| symmetry expansion | quartz；2 source sites；6 declared operations | 0.001840 s | 0.001651 s | 0.001673 s | 12,850 | Baseline |
| supercell | quartz；10×10×10 | 0.426508 s | 0.416724 s | 0.441469 s | 7,931,298 | Baseline |
| POSCAR import | `si.POSCAR`；2 atoms | 0.002016 s | 0.001479 s | 0.001505 s | 9,299 | Baseline |
| crystal view creation | 1000 sites；`source_sites` | 1.029302 s | 0.901669 s | 0.930671 s | 2,129,297 | Passed：cold/hot ≤ 3 s |

`CIF preview` 使用真实 Reader API registry、reader override、staging 与
Blender Import Preview 的 CIF 纯摘要投影，不以单独调用 Gemmi parser 代替
产品 preflight；synthetic CIF 在 cold preview 前未被预先解析。
`crystal view creation` 在 Blender 中调用真实
`create_periodic_structure_view()`，每次样本后删除本轮对象；node contract
在首个 cold 样本后保持 hot 状态。每项先记录一个 cold 样本，再记录五个
hot 样本用于 median/p95。

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
