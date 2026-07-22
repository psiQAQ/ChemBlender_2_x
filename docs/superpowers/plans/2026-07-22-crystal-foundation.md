# Gemmi/spglib 晶体基础设施实现计划

> 依据：[设计文档](../specs/2026-07-22-crystal-foundation-design.md)

## Goal

建立 CIF raw envelope、periodic site 语义、Gemmi reader 与 spglib symmetry/standardization 的纯 core 闭环。

## Plan

1. 固定 Gemmi 0.7.5、spglib 2.7.0 参考 submodule 与独立 Python 3.13 测试环境，记录版本和许可证。
2. 先为 `PeriodicSiteData`、`CIFEnvelope`、`SymmetryResult` 与项目引用写失败测试。
3. 扩展 `Structure`、`ImportBatch`、`QCProject` registry 和事务引用校验。
4. 添加带 uncertainty、unknown tag、occupancy、Uiso/Uij、disorder 的 CIF golden fixtures。
5. 先写 Gemmi sniff/parse 失败测试，再实现 late-import reader、raw envelope 和 normalized periodic structure。
6. 用 CsCl fixture 先断言 spglib #221、operations、Wyckoff、equivalent atoms、变换和标准结构，再实现 derived symmetry batch。
7. 覆盖部分占位拒绝 symmetry、bohr→angstrom、非法 tolerance、缺依赖和多 block 行为。
8. 更新 ADR、reference catalog、capability matrix、路线图与 active/completed 状态。
9. 运行 Blender Python、Gemmi/spglib 环境、compileall、Blender validate/build/lifecycle、ZIP audit 与 `git diff --check`。
10. 创建阶段提交并快进合并本地 `main`，进入 ASE/pymatgen 周期结构与体数据 adapter。

## Success Criteria

- CIF 语法不再由新 core reader 手写分词；未知 tag 可从精确 raw envelope 恢复。
- normalized periodic structure 保留 fractional/cartesian/lattice、occupancy、Uiso/Uij、disorder 与声明空间群。
- spglib 输出与标准结构都保留 input structure identity 和 provenance，不覆盖原始结构。
- core 模块顶层不导入 Gemmi/spglib，Blender Extension 可在没有这两个包时正常 enable。
- Extension ZIP 不包含 Gemmi、spglib、submodule 或测试文件。

## Verify

- Blender Python 中依赖相关测试明确 skip，其余完整 suite 通过。
- 独立 Python 3.13 环境中 Gemmi/spglib integration tests 与完整 suite 通过。
- Blender 5.1.2 隔离安装生命周期通过，ZIP 内容审计通过。
