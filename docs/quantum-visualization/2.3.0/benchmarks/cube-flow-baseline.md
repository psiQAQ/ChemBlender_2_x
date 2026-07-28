# Wave 1 Cube 128³ 产品流性能基线

## 结论

2026-07-28 在 Blender 5.1.2 的真实 OpenVDB/Volume 路径上，128³ Cube
产品流的各阶段 median 总和为 **1.659 s**，通过 Wave 1 的 **10 s** 门限。

## 环境与负载

| 项目 | 数值 |
| --- | --- |
| 设备 | Lenovo 82GR |
| CPU | AMD Ryzen 7 4800H，8 cores / 16 logical processors |
| 内存 | 17,042,837,504 bytes |
| 系统 | Windows 10.0.19045 x64 |
| Blender | 5.1.2 |
| Python / NumPy | 3.13.9 / 2.3.4 |
| 网格 | 128 × 128 × 128，2,097,152 voxels |
| 生成的 Cube | 32,501,927 bytes |
| 重复次数 | 3 |
| peak Python allocation | 299,352,487 bytes |

输入生成不计入产品流时间。Parse 在刚生成输入后的 warm OS file cache 上测量；
cold VDB 每次先删除 derived cache；hot VDB 验证已有 cache；view stage 使用已有
VDB 并真实创建、删除 Blender Volume datablock。

## 结果

| Stage | Median (s) | P95 (s) |
| --- | ---: | ---: |
| parse | 1.220970 | 1.236715 |
| stage NPY | 0.018436 | 0.060033 |
| sidecar save | 0.352497 | 0.353038 |
| cold VDB cache | 0.056388 | 0.082392 |
| hot VDB cache | 0.010312 | 0.010856 |
| hot Volume view | 0.010994 | 0.011697 |

门限总和使用 `parse + stage NPY + sidecar save + cold VDB cache + hot Volume
view`，结果为 **1.659286 s**。Hot VDB cache 作为独立诊断，不重复计入总和。

## 复现

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background `
  --factory-startup `
  --python-exit-code 1 `
  --python ChemBlender/scripts/benchmark_cube_flow.py `
  -- --size 128 --repeats 3 --output cube-flow.json
```

结果为本地验证证据；Remote CI: Not Run。
