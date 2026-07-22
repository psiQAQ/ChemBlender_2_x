# `.npy` sidecar benchmark：Windows / Blender Python

## 环境与方法

- 日期：2026-07-22
- OS：Windows 10.0.19045
- Python：Blender bundled CPython 3.13.9
- NumPy：2.3.4
- storage：未压缩 `.npy` + `numpy.load(..., mmap_mode="r")`
- cache state：写入并 fsync 后的 warm OS cache
- 脚本：`ChemBlender/scripts/benchmark_sidecar.py`

命令：

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe' `
  ChemBlender\scripts\benchmark_sidecar.py
```

## 结果

| Case | Shape / dtype | Raw size | File overhead | Write | Full scan | Slice |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| trajectory | `500×2000×3 float32` | 12.00 MB | 0.00107% | 10.22 ms | 4.32 ms | 0.0106 ms |
| Grid3D | `160³ float32` | 16.38 MB | 0.00078% | 19.65 ms | 5.89 ms | 0.0548 ms |
| MO coefficients | `1200×1200 float64` | 11.52 MB | 0.00111% | 10.78 ms | 4.10 ms | 0.0068 ms |
| projections | `2×64×96×16×9 float32` | 7.08 MB | 0.00181% | 8.09 ms | 2.89 ms | 0.0149 ms |

四类 checksum 均正确，并全部通过预先规定的 1% overhead、5 s write、2 s full scan 和
0.1 s slice 门槛。

## 结论

Phase 3 本地单机 v1 保留 `.npy`，不新增 Zarr/HDF5 依赖。该结论只覆盖当前 7–16 MB
代表性 sample 和 warm-cache 交互；它不能证明 cold storage、压缩、网络文件系统或超大
多轴随机访问性能。

在以下任一条件首次出现时，重新运行同一 workload 并对 Zarr/HDF5 二选一：

- 单个真实权威数组超过 512 MiB；
- 必须压缩才能满足项目容量；
- 非连续 slice 成为已测性能瓶颈；
- 多进程并发访问成为正式需求。
