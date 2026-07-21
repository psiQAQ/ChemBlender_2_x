# 存储、缓存与 worker 开发计划

## 范围

为来源文件、大型数组、派生网格、Blender 缓存和独立 worker 建立可恢复的数据生命周期。

## 非目标

- 不把同一权威数组同时写入 Zarr 和 HDF5。
- 不在没有规模基准时引入 worker、数据库或远程服务。
- 不把隐藏 Mesh 顶点当作体数据存储。

## 优先级

| 优先级 | 内容 | 选择门 |
| --- | --- | --- |
| P0 | `.cbq` manifest、source/parser/derivation/render hash、dataset UUID、原子写入和故障恢复 | Phase 0 对象身份与 provenance ADR 通过 |
| P1 | 根据 benchmark 选择 Zarr 或 HDF5；加入 lazy loading、OpenVDB、独立 worker、长轨迹缓存 | Phase 1/2 有代表性数组规模和跨平台测试 |
| P2 | 远程 worker、多计算 ensemble、搜索与项目级 provenance graph | 本地 worker 已稳定且出现真实远程需求 |

## 依赖关系

依赖语义核心、`Grid3D`、Blender/边车 ADR 和 cache identity。worker 依赖稳定的序列化协议，但 Blender Extension 不依赖 worker 才能启用或打开结构场景。

## 交付物

- `.cbq` manifest 最小 schema 与路径规则。
- source、parser、normalized dataset、derivation 和 render cache 的 hash 链。
- 临时写入、校验、原子替换和崩溃恢复规则。
- Zarr/HDF5/OpenVDB/NPZ 的数据规模基准。
- worker 请求、结果、错误、取消与版本协商协议。

## 验收标准

- 源文件或 parser version 改变后相关派生缓存失效。
- 中断写入不会覆盖最后一个有效 manifest。
- `.blend` 重开后通过 project/dataset UUID 恢复引用。
- worker 崩溃不带崩 Blender，也不把部分结果标为成功。
- 选定存储在 Windows、Linux、macOS 的维护成本有证据；未选方案不保留并行实现。

## 参考仓库触发条件

- 轨迹边车、frame manager 和 session 恢复进入实现时审阅 Molecular Nodes。
- 大型数组进入 benchmark 时审阅 Zarr/HDF5 官方实现和目标依赖树。
- 只有 worker 协议落地后才调研 AiiDA、QCArchive、NOMAD 的缓存与不可变记录做法。
