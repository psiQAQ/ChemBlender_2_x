# 2.3.0 统一性能基准

`ChemBlender/scripts/benchmark_230.py` 为 2.3.0 release qualification 提供
统一的结果封装；它复用现有 Reader、sidecar、lazy NPY 和 Project Browser
实现，不替换各领域的详细 benchmark。

## 固定规模

| Scale | Structure | Trajectory | Grid | SDF index |
| --- | ---: | ---: | ---: | ---: |
| `interactive` | 50,000 atoms | 1,000 frames | 128³ | 10,000 records |
| `lazy` | 250,000 atoms | 100,000 frames | 256³ | 100,000 records |

`ChemBlender.benchmarks.datasets` 使用固定 seed `230`。结构和 SDF 逐行写入；
trajectory/grid 使用 NPY memmap 按 frame/slab 写入。每次生成都会返回 fixture
的 SHA-256，测试只能使用小规模 override，不能把完整规模 materialize 成 tuple
或大量小文件。

## 运行边界

| Case | 当前执行位置与证据类型 |
| --- | --- |
| `preflight_feedback`、`parse`、`project_commit`、`sidecar_save_open`、`trajectory_frame`、`browser_projection_filter` | 现有 pure-Python API，可由 harness 运行，但当前均为 `diagnostic`，不能作为产品 SLA 证据。 |
| `extension_enable`、`vdb_cache`、`default_view` | 当前没有对应 runner；JSON 明确写入 `Not Run` 和边界原因。 |
| `cancel_cleanup` | 等待 Wave 4 cancellable task state machine；不会伪造取消证据。 |

`--case` 可重复选择单个 case，`--case all` 只用于汇总边界状态。完整
qualification 要求 clean Git source、已验证 Blender/RDKit/Gemmi runtime、所有
所选 case 为 `Passed`，并且每个 budget case 的 measurement 与其 `cold_p95` 或
`hot_p95` 声明一致；`diagnostic` 结果必定被拒绝。

harness 先在计时外准备一次选中 scale 的 fixture；`cold_seconds` 是同一
fixture 的首次访问，随后执行 warmup，再记录至少两个 hot samples。`--samples`
必须不小于 `2`，避免生成没有可比 `hot_seconds` 的报告。
因此单个 `cold_seconds` 不是 cold p95，当前 pure-Python runner 的 p95 也不能
替代产品 cold gate。

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe' `
  ChemBlender\scripts\benchmark_230.py --case parse --scale interactive `
  --warmups 1 --samples 5 --output .agents\cache\benchmark-parse.json
```

不要把 cloud CI 的耗时当作桌面 SLA；绝对门限仍由
[`performance-budget.md`](../performance-budget.md) 的 reference hardware
流程判定。Task 1 只定义 harness 和 deterministic fixtures，不在日常测试中
运行完整 50k/250k/100k workload。

## JSON 契约

输出是 sorted-key、compact、UTF-8/LF 的 JSON，并以同目录 temporary file +
`os.replace()` 原子发布。每份 report 必含 Git `source_commit`/`source_dirty`、
经 background Blender probe 验证的 Blender/RDKit/Gemmi 版本、warmup/sample
count、per-case measurement/cold/hot、median/p95/min/max、samples 和 failure
count。非有限数值、缺字段、dirty source、runtime 不匹配、`diagnostic`、失败或
`Not Run` case 都不能通过 qualification。
