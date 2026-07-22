# Quantum Visualization Roadmap Completion Audit

## Result

Phase 0–4 的基础路线图已闭环。审计补齐统一 builtin reader registry 与由测试逐字段校验的 capability matrix，并同步纠正主题计划中已完成但仍写作“继续”的状态。

## Evidence Matrix

| Phase | 已交付边界 | 主要证据 |
| --- | --- | --- |
| 0 | semantic model、units/Grid3D、reader/capability、sidecar boundary | ADR 0003–0006；`test_quantum_core`、`test_reader_catalog` |
| 1 | cclib、IOData、Cube、GBasis fields、vibration/excited-state、Blender dataset adapters | completed 记录 6 项；parser/numerical/Blender smoke |
| 2 | Gemmi/spglib、ASE/pymatgen、band/DOS、phonopy、Fermi surface | ADR 0010–0014；周期 fixtures 与 Blender smoke |
| 3 | `.cbq`、`.npy` benchmark、worker、lazy trajectory、LOD/OpenVDB cache | ADR 0015–0018；sidecar/worker/cache tests |
| 4 | recipe、external process、topology、QCSchema/CJSON、compute worker、report、scene/surface presets、external record connectors | ADR 0019–0028；worker/core/Blender smoke |

## Repository Consistency

- 11 个 built-in file readers 由 `builtin_reader_registry()` 汇总；`reader-capability-matrix.json` 与代码 descriptor 一致。
- 14 个已使用参考项目以 gitlink 固定 commit；未触发候选保持未拉取，不创建伪 submodule。
- Extension manifest 仍只有 Windows x64 RDKit wheel；optional quantum stack、worker、submodules、tests 与 caches 不进入 ZIP。
- `.agents/active/` 和 `.agents/queued/` 均无遗留任务；28 个 ADR 只追加不重写。

## Conditional Future Work

以下项目有明确触发门，不属于当前已承诺的基础路线图：

- Grid 导数、自适应采样、mesh fallback：出现 OpenVDB 缺失平台或真实性能/分析需求后启动。
- CuGBasis/GPU、MDAnalysis/MDTraj：目标 GPU/轨迹格式和规模明确后启动。
- linked brushing、跨计算比较、远程 worker/provenance federation：先确定 UI 与部署需求。
- 在线 QCArchive/AiiDA/NOMAD：需用户选择服务、账号、认证和 SDK；当前仅提供无网络的稳定 contract。
- Multiwfn/critic2 真二进制 integration：需本机可执行文件和可公开的稳定输出 fixture。

## Verification

最终 gate 记录在本提交验证结果中：全量 CPython tests、extension validate/build、ZIP audit、Blender 5.1 isolated lifecycle smoke 与 `git diff --check`。
