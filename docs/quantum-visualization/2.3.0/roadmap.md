# ChemBlender 2.3.0 纵向路线图

## 推进规则

- 同一时间只有一个 active Wave。
- 每个 Wave 由设计、若干 implementation plans、真实 fixtures、UI 验收和发布门组成。
- 不允许用新增按钮绕过统一 Import Pipeline。
- 不允许因已有 adapter 而跳过真实依赖、真实文件和用户操作验证。
- 预发布只从 exact-tag CI artifact发布。
- Beta 之后冻结 sidecar schema 和 Reader API v1 的破坏性变化。

## Wave 0：Platform Foundation

**目标版本：2.3.0-alpha.1**

交付：

- core模型内部模块化、兼容门面和显式 sidecar type registry；
- `SourceRecord`、`SourceRevision`、详细诊断、ConformerSet 和 frame-related properties；
- Session Project、dirty state、temporary sidecar、保存/恢复；
- ImportRequest/Preview/Transaction、重复冲突和归组建议；
- Reader API 0.x、canonical document和worker artifact边界；
- 显式 Blender注册；
- N面板 Quick Import、最小 Project Browser、Import Preview；
- 动态 version/artifact基础和 prerelease validator probe。

退出门：使用现有 XYZ/Cube fixture完成 import preview→project→view→save→reopen；无需新增格式即可证明平台链路。

## Wave 1：Molecular and Grid Native Closure

**目标版本：2.3.0-alpha.2**

交付：

- 原生通用 extXYZ；
- RDKit MOL V2000/V3000、SDF、SMILES；
- record-level recovery、SD properties、ConformerSet；
- 带来源和可信度的拓扑；
- 统一 StructureViewBuilder接入现有球棍节点；
- Cube dataset/semantic/unit/surface UI；
- XYZ/extXYZ、MOL/SDF round-trip；
- 真实 fixture和性能基线。

退出门：基础 ZIP 无外部环境完成所有 Wave 1 格式的 Quick Import、Project Browser、默认视图、保存恢复和适用导出。

## Wave 2：Crystal Native Closure

**目标版本：2.3.0-beta.1**

交付：

- Gemmi wheel和CIF基础 reader；
- 原生 POSCAR/CONTCAR；
- occupancy/Uij/Selective Dynamics/periodic topology；
- 文件声明对称性与可选 spglib派生并存；
- 晶胞、超胞、ADP和受控导出；
- sidecar schema冻结；
- Reader API v1 RC。

退出门：没有 spglib和外部 worker也能完成真实 CIF/POSCAR项目闭环；Gemmi lifecycle和包体门通过。

## Wave 3：Exchange, MOL2 and Bio-atom Metadata

**目标版本：2.3.0-beta.2**

交付：

- MOL2完整导入；
- PDB/PQR atom-level完整导入；
- chain/residue/altloc/MODEL/CONECT/CRYST1/charge/radius；
- CJSON轻量交换；
- 独立示例 Extension Reader；
- Reader API v1 conformance kit；
- 只做向后兼容 API补充。

退出门：示例 reader在仓库外安装和失效都不影响本体；已保存 `.cbq` 在插件缺失时可打开。

## Wave 4：Migration and Release Qualification

**目标版本：2.3.0-rc.1 → 2.3.0**

交付：

- 旧 UI全部改接统一 backend；
- Legacy `.blend` 检测与显式迁移向导；
- CI分层、真实 integration、size/license、performance门；
- 文档、capability matrix、用户指南、插件指南；
- changelog、升级和 schema迁移说明；
- RC后只修阻断问题。

退出门：2.2.x升级、旧场景迁移、基础格式、安装生命周期、性能和Release workflow全部验证；正式版不新增范围。
