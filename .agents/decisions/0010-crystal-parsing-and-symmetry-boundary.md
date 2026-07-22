# ADR 0010: Crystal Parsing and Symmetry Boundary

## Status

Accepted on 2026-07-22.

## Context

ChemBlender 的旧 CIF/POSCAR 路径同时承担文本解析、空间群猜测和 Blender 数据构建，难以覆盖 quoted values、uncertainty、非标准 tag、setting/origin choice、disorder 与标准化变换。周期结果还需要跨 CIF、POSCAR、ASE 和材料计算格式共享结构 identity。

## Decision

- Gemmi 0.7.5 是新 core CIF reader 的语法与 small-structure 后端；`CIFEnvelope` 保存精确 source bytes、block 和完整 tag 名单。
- `Structure.periodic` 使用 `PeriodicSiteData` 保存 fractional coordinates、occupancy、Uiso/Uij、site label、ADP/disorder 和声明空间群。只有 CIF 来源设置 `cif_envelope_id`；非 CIF 周期结构允许为 `None`。
- spglib 2.7.0 是空间群与标准化后端。`SymmetryResult` 保存 input-basis operations、Hall/IT identity、Wyckoff、等价原子、primitive mappings、transformation matrix、origin shift 与 standard rotation。
- 标准晶胞作为新的 derived `Structure` 注册，不覆盖输入结构。spglib `symprec` 统一为 angstrom，bohr 输入先显式转换。
- 部分占位或 disorder 可由 Gemmi reader 保留，但在 occupancy-aware symmetry 策略完成前拒绝自动 spglib 分析。
- 两个依赖仅在独立 core/worker 环境 late import；不打包进 Blender Extension。

## Consequences

- 未识别 CIF tag 可从 envelope 恢复，normalized 字段与原始来源不再互相替代。
- setting/origin 变换、输入与标准晶胞均可追溯；Blender 可明确选择显示哪一个结构。
- 现有 Blender CIF/POSCAR UI 暂时保留并由 golden smoke 固定，后续迁移可以逐步进行。
- 多 block 选择、磁空间群、modulated CIF 和 occupancy-aware symmetry 仍需后续明确契约。
