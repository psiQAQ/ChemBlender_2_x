# Crystal Foundation: Gemmi and spglib

## Goal

建立不依赖 `bpy` 的 CIF envelope 与晶体对称性边界，用 Gemmi 负责 CIF 语法、spglib 负责空间群与标准化，并保留原始晶胞到标准晶胞的可追溯变换。

## Success Criteria

- normalized periodic structure 明确表达 lattice、fractional coordinates、occupancy、Uij、site label 和原始 CIF envelope。
- Gemmi adapter 覆盖带不确定度数值、loop、未知 tag、部分占位和非标准 tag，不通过手写分词器猜测。
- spglib adapter 返回 Hall/IT number、operations、Wyckoff、equivalent atoms、transformation matrix、origin shift 和标准化结构。
- 现有 CIF/POSCAR 行为以 golden fixtures 固定；parser 可在普通 CPython 测试且 Extension 不打包 Gemmi/spglib。
- 依赖版本、许可证、submodule 固定 commit 与 worker/core 边界有正式决策记录。

## Constraints

- 先新增纯 core adapters，不直接删除现有 Blender CIF UI 和导出路径。
- 未识别 CIF 内容必须保存在 raw envelope 或明确报告，不能静默丢弃。
- 标准化结构是派生结果，不覆盖原始 CIF 结构或 identity。

## Next Action

审阅现有 `read_cif`、POSCAR 与空间群测试，核对 Gemmi/spglib 当前官方 API、版本与许可证；以测试先定义 periodic/CIF envelope 和 symmetry result 最小语义，再按需固定两个参考 submodule。

## References

- [持续开发路线图](../../docs/quantum-visualization/roadmap.md)
- [周期电子结构计划](../../docs/quantum-visualization/plans/periodic-electronic-structure.md)
- [Reader 与格式能力计划](../../docs/quantum-visualization/plans/readers-and-formats.md)
