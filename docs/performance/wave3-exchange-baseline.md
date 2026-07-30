# Wave 3 Exchange 性能基线

## 结论

2026-07-30 使用 Blender 5.1.2 bundled Python 运行
`ChemBlender/scripts/benchmark_exchange.py`。MOL2、PDB、PQR 与 CJSON 各
生成并解析 50,000 atoms；每项记录一次 cold、一次不计入统计的 warmup、
五次 hot 样本和一次独立 `tracemalloc` peak。小型 MOL2 产品 preview 的
Reader API preflight + staged summary median 为 0.020904 s，满足 0.5 s
快速反馈预算。

PDB 与 PQR 的 50,000-atom median 超过 1 s，但均为 import/background
parse path，不在 Blender draw path。Blender RNA projection 本 benchmark
明确为 `Not Run`，由 Wave 3 product gate 验证。

## 环境

| 项目 | 值 |
| --- | --- |
| OS | Windows 10.0.19045 |
| CPU | AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD；16 logical CPUs |
| RAM | 17,042,837,504 bytes |
| Blender | 5.1.2 |
| Python | 3.13.9；Blender bundled Python |
| NumPy | 2.3.4 |
| samples | 1 cold + 1 warmup + 5 hot；另测 1 次 peak |
| memory | `tracemalloc` peak；不代表 NumPy/native allocation |

## 结果

| 操作 | 工作量 | source bytes | cold | hot median | hot p95 | peak Python bytes | peak/source |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MOL2 parse | 50,000 atoms | 1,877,861 | 0.594753 s | 0.589858 s | 0.607840 s | 38,505,729 | 20.505 |
| PDB parse | 50,000 atoms | 4,050,000 | 1.016801 s | 1.031125 s | 1.074475 s | 55,297,493 | 13.654 |
| PQR parse | 50,000 atoms | 2,933,344 | 1.620293 s | 1.684856 s | 1.710843 s | 71,678,002 | 24.436 |
| CJSON parse | 50,000 atoms | 850,071 | 0.151053 s | 0.138247 s | 0.146241 s | 18,872,730 | 22.201 |
| preview projection | 20 MOL2 atoms | 692 | 0.030715 s | 0.020904 s | 0.022020 s | 133,424 | 192.809 |

内存判断使用 `peak <= max(64 MiB, source_bytes × 32)`；小型 preview
因 source 很小而使用绝对预算。所有 50,000-atom source 均逐行生成，没有
先构造大型 nested tuple。benchmark temporary directory 在运行后清理。

## 复现

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe" `
  "ChemBlender/scripts/benchmark_exchange.py" `
  --atoms 50000 `
  --preview-atoms 20 `
  --samples 5 `
  --output "$env:TEMP\chemblender-wave3-exchange.json"
```

输出为 sorted、compact UTF-8 JSON，并以一个 LF 结尾。桌面测得的绝对时间
只作为后续 Wave 比较基线，不作为 cloud CI 的硬阈值。
