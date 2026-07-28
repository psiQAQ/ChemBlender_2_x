# Wave 1 extXYZ 产品流性能基线

## 结论

2026-07-28 的 1,000 frames × 1,000 atoms reference workload 中，真实
Reader API preflight、staged batch 与 Preview summary 的首次反馈 median/p95
为 **0.448/0.457 s**，通过 **0.5 s** 门限。完整数值物化为后台可取消长操作，
单次实测 **99.702 s**，不在首次反馈门限内。

## 环境与负载

| 项目 | 数值 |
| --- | --- |
| 设备 | Lenovo 82GR |
| CPU | AMD Ryzen 7 4800H，8 cores / 16 logical processors |
| 系统 | Windows 10.0.19045 x64 |
| Blender Python / NumPy | 3.13.9 / 2.3.4 |
| trajectory | 1,000 frames × 1,000 atoms，6 numeric columns |
| metadata-only | 10,000 frames × 1 atom |
| cache state | 输入生成后 warm OS file cache |
| peak Python allocation | 831,125 bytes |

完整 matrix 使用 3 次重复。最后的 bounded 64 KiB source-read 修复后，另以
5 次真实 preflight 重测首次反馈，样本为 0.448432、0.446794、0.457027、
0.445594、0.449086 s。

## 完整 matrix

| Stage | Median (s) | P95 (s) |
| --- | ---: | ---: |
| first-frame decode | 0.050233 | 0.056432 |
| full parse | 99.932779 | 99.977608 |
| metadata-only parse | 3.517732 | 3.541265 |
| sidecar write | 1.025625 | 1.029081 |
| single-frame access | 0.000012 | 0.000072 |
| export | 22.562982 | 22.713154 |

`preview_ready` 使用最后一次 5-sample 复验值。完整 matrix 同时通过
reference/metadata scale、frame access、bounded memory、cancellation cleanup
和 publication rollback。确认物化的 entity inventory 或语义诊断变化会清理
新 artifacts、保留 snapshot，并要求刷新 Preview。

## 复现

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe" `
  ChemBlender/scripts/benchmark_extxyz.py `
  --frames 1000 --atoms 1000 --metadata-frames 10000 --repeats 3 `
  --output extxyz-flow.json
```

结果为本地验证证据；Remote CI: Not Run。
