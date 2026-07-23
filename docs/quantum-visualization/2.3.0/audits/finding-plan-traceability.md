# 审计发现到执行计划追踪矩阵

| Finding | 证据/影响 | 负责计划 | 退出证据 |
| --- | --- | --- | --- |
| F-001 Phase“完成”与Product UX混淆 | 路线图Phase 0–4全部完成，但UI缺失 | Master sequencing、Wave 4 docs | maturity分级与生成能力文档 |
| F-002 `model.py`单体 | 2500+行、多领域/事务 | Wave 0 core modularization | 模块测试、public façade、sidecar v0.1 reopen |
| F-003 sidecar动态扫描model module | 模块拆分会破坏type registry | Wave 0 core modularization | explicit registry、安全tag测试 |
| F-004 无SourceRecord/revision | 重复/移动/更新无法表达 | Wave 0 source/session | conflict tests、save/reopen |
| F-005 ParserIssue信息不足 | 无科学后果/恢复UX | Wave 0 transaction/diagnostics | ImportDiagnostic JSON/Markdown |
| F-006 session project缺失 | 首次导入到保存之间无正式状态 | Wave 0 source/session | temporary→solidify→reopen |
| F-007 auto_load递归导入core | 启用/隔离/插件风险 | Wave 0 registration/UI | module/lifecycle smoke、enable baseline |
| F-008 无Quick Import/Project Browser | 普通用户无法使用新core | Wave 0 registration/UI | XYZ/Cube UI product flow |
| F-009 Reader API内部化 | 无plugin来源/执行模式/兼容 | Wave 0 reader API、Wave 3 conformance | example extension reader |
| F-010 CI/制品硬编码2.2.0 | 下版构建/发布失配 | Wave 0 release groundwork | metadata helper/workflow tests |
| F-011 prerelease regex不支持 | 发布列车不可执行 | Wave 0 release groundwork | Blender native probe、dry-run |
| F-012 XYZ extra columns丢失 | extXYZ数据损失 | Wave 1 extXYZ | generic Properties round-trip |
| F-013 MOL core丢键 | “支持”误导 | Wave 1 RDKit molecular | explicit topology/charge/stereo tests |
| F-014 SDF只读单record | 静默数据丢失 | Wave 1 RDKit molecular | record recovery/grouping/round-trip |
| F-015 V3000 bond ID从0开始 | 非规范输出 | Wave 1 RDKit molecular | regression test ID=1 |
| F-016 legacy MOL2 unbound `mol` | 运行时崩溃 | Wave 1 bridge、Wave 3 MOL2 | explicit interim error→native reader |
| F-017 point-only structure view | 新旧显示割裂 | Wave 1 topology/view | edges/GN/attributes smoke |
| F-018 推断拓扑无来源 | 科学事实混淆 | Wave 1 topology/view | TopologyRecord provenance/accept/reject |
| F-019 Cube缺dataset/semantic UX | strong parser无法产品化 | Wave 1 Cube UX | multi-dataset resolve/surface/save |
| F-020 Gemmi不在ZIP | CIF基础目标冲突 | Wave 2 Gemmi CIF | wheel/lifecycle/base flow |
| F-021 POSCAR依赖旧/ASE | 基础目标冲突 | Wave 2 POSCAR | native reader/exporter |
| F-022 文件/派生对称性混淆风险 | source vs calculation | Wave 2 crystal/spglib | declared/derived comparison UI |
| F-023 MOL2缺失 | 格式声明不一致 | Wave 3 MOL2 | native record-aware reader |
| F-024 PDB/PQR层级缺失 | 活性位点/charge/radius不可用 | Wave 3 PDB/PQR | chain/residue/altloc/MODEL smoke |
| F-025 Reader生态未证明 | API可能只适合内置代码 | Wave 3 CJSON/plugin | standalone plugin/conformance |
| F-026 optional real tests静默skip | CI绿不证明真实解析 | Wave 4 CI hardening | required runner zero skip |
| F-027 无包体/许可证门 | 新wheel风险 | Wave 4 CI hardening | inventory/size/license artifacts |
| F-028 旧场景升级不明确 | 用户升级阻力/数据风险 | Wave 4 legacy migration | fixed `.blend` fixtures、rollback |
| F-029 性能无SLA | sidecar/UI是否可发布不清 | Wave 4 performance | baseline/budget/trend |
| F-030 文档/manifest/changelog落后 | 用户预期与代码不一致 | Wave 4 docs/release | generated formats、migration、release evidence |
