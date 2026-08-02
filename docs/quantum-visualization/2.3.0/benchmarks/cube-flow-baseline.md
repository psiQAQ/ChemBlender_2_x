# Wave 1 Cube 128³ 产品流性能基线

## 结论

2026-08-02 在 Blender 5.1.2 的真实 Cube export、OpenVDB/Volume
路径上，128³ Cube 产品流的各阶段 median 总和为 **4.717 s**，
通过 **10 s** 门限；单独 export p95 为 **3.090 s**，也通过同一门限。

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
| 导出的 Cube | 49,279,468 bytes |
| 重复次数 | 3 |
| parse peak Python allocation | 299,352,852 bytes |
| export peak Python allocation | 132,598,684 bytes |

输入生成不计入产品流时间。Parse 在刚生成输入后的 warm OS file cache 上测量；
cold VDB 每次先删除 derived cache；hot VDB 验证已有 cache；view stage 使用已有
VDB 并真实创建、删除 Blender Volume datablock。

## 结果

| Stage | Median (s) | P95 (s) |
| --- | ---: | ---: |
| parse | 1.205448 | 1.212711 |
| export | 3.072077 | 3.089668 |
| stage NPY | 0.014989 | 0.024769 |
| sidecar save | 0.350846 | 0.362858 |
| cold VDB cache | 0.059734 | 0.079383 |
| hot VDB cache | 0.011182 | 0.011693 |
| hot Volume view | 0.013774 | 0.013905 |

门限总和使用 `parse + export + stage NPY + sidecar save + cold VDB cache
+ hot Volume view`，结果为 **4.716870 s**。Hot VDB cache 作为独立诊断，
不重复计入总和。

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
