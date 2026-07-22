# Sidecar and Cache Foundation

## Result

- `.cbq` v0.1 采用 JSON manifest 与 content-addressed `.npy` array sidecar。
- `QCProject` 的 structure/dataset/provenance identity 可恢复，大型 trajectory array 保持 lazy mmap。
- source/parser/derivation/render cache identity 使用 canonical JSON 和 SHA-256 分层。
- manifest 与数组通过同目录临时文件、fsync 和 `os.replace` 原子发布。
- Blender scene 只保存 project UUID、schema version 和相对 locator，明确报告 missing、mismatch、incompatible 与 invalid。

## Evidence

- core suite：201 tests passed，27 optional-dependency skips。
- Blender 5.1.2 native validate/build passed。
- 隔离 Blender Extension install、sidecar link、两轮 reload、RDKit runtime 与 disable lifecycle passed。
- package smoke 验证 ZIP 只含声明的 RDKit wheel，不含 tests/scripts/cache。

## Decisions

- `.agents/decisions/0015-cbq-npy-sidecar-and-cache-identity.md`
- `docs/quantum-visualization/specs/cbq-sidecar-v0.1.md`

## Known Limitation

`.npy` v0.1 不提供 chunk/compression。是否迁移到 Zarr 或 HDF5 必须先使用真实轨迹、Grid3D、MO coefficient 与 projection shape 做跨平台 benchmark。
