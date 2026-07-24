# ChemBlender 2.3.0 开发入口

2.3.0 将开发重点从“继续增加量子化学契约和可选后端”转为“基础安装即可使用的格式兼容与项目化用户闭环”。所有设计均基于已批准的 `Native Compatibility 70% + Platform Foundation 30%`。

## 阅读顺序

1. `audits/2026-07-23-main-deep-audit.md`
2. `product-definition.md`
3. `architecture/import-project-reader-api-boundary.md`
4. `architecture/quality-topology-edit-boundary.md`
5. [Import diagnostics report v1](specs/import-report-v1.md)
6. `format-maturity-matrix.md`
7. `dependency-tier-matrix.md`
8. `performance-budget.md`
9. `roadmap.md`
10. `docs/superpowers/specs/` 中的 2.3.0 总设计和 Wave 设计
11. `docs/superpowers/plans/` 中的总排序计划和各实施计划

## 核心原则

```text
产品路线按格式和用户任务表达
内部架构按物理语义表达
验收按真实文件端到端表达
科学来源不可变
Blender datablock 只作为视图和缓存
基础格式不得依赖外部 worker
```

## 发布列车

| 版本 | Wave | 主要内容 |
| --- | --- | --- |
| 2.3.0-alpha.1 | Wave 0 | 会话项目、来源身份、导入预览、Reader API 0.x、Quick Import 与 Project Browser 骨架 |
| 2.3.0-alpha.2 | Wave 1 | XYZ/extXYZ、MOL/SDF/SMILES、Cube 与统一结构/拓扑视图 |
| 2.3.0-beta.1 | Wave 2 | Gemmi CIF、原生 POSCAR/CONTCAR、晶体可视化；冻结 sidecar 与 Reader API v1 RC |
| 2.3.0-beta.2 | Wave 3 | MOL2、PDB/PQR、CJSON、示例插件和 conformance kit |
| 2.3.0-rc.1 | Wave 4 | 旧场景迁移、旧 UI 统一、CI、性能、文档与发布收口 |
| 2.3.0 | Final | 全部门禁通过，不增加范围 |

预发布版本字符串必须先通过 Blender 5.1.2 原生 extension validator 的实际探针；若 Blender 不接受 SemVer prerelease，发布工程计划规定在任何 tag 创建前停下并改用经过验证的数字版本映射。
