# Sidecar Benchmark and Local Worker Protocol Plan

## Goal

验证 `.npy` v0.1 是否满足当前本地工作集，并交付可在普通 CPython 独立运行的 worker v1。

## Tasks

1. 为 request/entity ref/result/error 建立严格、versioned JSON model 和 round-trip tests。
2. 建立固定 operation registry、sidecar identity/input/output validation 与 cancellation checks。
3. 以临时文件、fsync、`os.replace` 原子发布 request/result；crash 不留下 success。
4. 增加 `project.verify@1` CLI probe 和 subprocess test，证明 worker 不依赖 Blender。
5. 增加不提交大型数组的 synthetic `.npy` benchmark，覆盖 trajectory、Grid3D、MO coefficient 与 projection。
6. 记录 Windows/Blender Python 实测结果，依据预设门槛决定保留 `.npy` 或进入单一 chunk backend 选型。
7. 运行 core suite、协议 subprocess、native extension validate/build 和隔离 Blender smoke。

## Benchmark gates

在本地 SSD、单进程、未压缩数据下，每个代表性 sample 必须满足：

- `.npy` 文件开销不超过 raw bytes 的 1%；
- 写入不超过 5 s；
- 完整 mmap scan 不超过 2 s；
- 代表性 slice scan 不超过 0.1 s；
- 写后数值 checksum 与预期一致。

门槛用于当前交互/缓存路径，不代表超大远程 dataset 的最终 backend 结论。若全部通过，v1
继续保留 `.npy`；首次出现大于 512 MiB 的真实数组、压缩需求或多轴随机 chunk access
瓶颈时，再用同一 benchmark 对 Zarr 与 HDF5 二选一。

## Verification

- malformed/unknown request 被拒绝。
- success、failure、cancel、output mismatch、BaseException crash 各有测试。
- subprocess 执行 `project.verify@1` 并读取原子 result。
- benchmark JSON 与结论文档可复现，不提交生成的 `.npy`。
