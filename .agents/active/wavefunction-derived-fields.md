# Wavefunction Derived Fields

## Goal

从 ChemBlender `BasisSet`/`OrbitalSet` 计算可验证的分子轨道与电子密度 `Grid3D`，并复用 OpenVDB adapter 进入 Blender。

## Success Criteria

- 对 ORBKIT 与 IOData+GBasis/Grid 做固定版本、许可证、API、Windows/Python 3.13 和数值结果比较，记录主后端决策。
- 至少一个真实 restricted FCHK 的指定 MO 在均匀斜或正交网格上生成 `Grid3D`，保留 orbital/channel、单位、父实体和计算参数。
- 至少一个电子密度 grid 与独立参考或守恒量进行数值核对。
- 正负 MO 相位不合并为依赖法线推断的单一语义；Blender 可从派生 grid 重建 Volume。
- core/compute 测试不依赖 `bpy`，外部数值依赖不打入当前 Blender Extension。

## Constraints

- 先用小型真实 fixture 建立 correctness baseline，再设计自适应网格、GPU 或 worker。
- 不重复解析 FCHK/Molden；求值器只消费 normalized structure/basis/orbital entities。
- basis convention 必须显式传递或转换，不假设 Gaussian/ORCA 默认顺序。
- 每个派生 grid 记录 source entity UUID/revision、backend/version、bounds、spacing、orbital/channel 和 hash。

## Next Action

核对 GBasis/Grid 与 ORBKIT 当前官方 release、依赖和 API；用 `water_sto3g_hf_g03.fchk` 设计最小 AO/MO 求值探针，并确定主后端。

## References

- [持续开发路线图](../../docs/quantum-visualization/roadmap.md)
- [波函数与体网格计划](../../docs/quantum-visualization/plans/wavefunction-and-grids.md)
- [IOData 波函数语义设计](../../docs/superpowers/specs/2026-07-22-iodata-wavefunction-design.md)
- [Grid3D 与单位约定 ADR](../decisions/0004-grid3d-and-units.md)
- [已完成的分子量化读取闭环](../completed/molecular-quantum-chemistry-ingestion.md)
