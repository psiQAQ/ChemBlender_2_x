# 0006：Blender 与边车数据职责边界

## Status

Accepted for Phase 0 quantum visualization foundation.

## Context

量子化学项目可能包含长轨迹、轨道系数和大型体数据。把这些权威数组写入 Blender Mesh、custom properties 或隐藏 datablock 会增加文件体积、损害语义，并使普通 Python、worker 和其他工具难以共享数据。

同时，`.blend` 必须能够保存用户的场景、显示设置和数据引用。本决策确定两侧职责及缓存失效条件，不选择具体边车后端。

## Decision

### 权威数据

边车保存项目的权威 normalized data：

- `QCProject` schema version 与 project UUID；
- structures、calculations、datasets 和 provenance registries；
- 大型数组及其 shape/dims/unit metadata；
- source reference、source hash、parser ID/version 和解析选项；
- entity revision 与派生记录。

原始来源文件可以被边车复制或外部引用，但必须记录来源标识和 SHA-256。复制策略和目录布局由后续存储设计决定。

### `.blend` 内容

`.blend` 只保存 Blender 场景及恢复权威数据所需的最小引用：

| 内容 | 用途 |
| --- | --- |
| project UUID | 防止连接到错误边车 |
| sidecar locator | 优先使用相对 `.blend` 的位置 |
| sidecar schema version | 判断当前 runtime 是否可读取 |
| dataset/entity UUID | 将 Object、plot 和选择绑定到语义实体 |
| entity revision | 判断当前 Blender 派生对象是否过期 |
| display settings | isovalue、颜色、可见性、当前帧等用户视图状态 |
| derivation metadata | operation、版本、参数和输入 revision |

Mesh attributes、Volume、Curve、Image 和临时 Mesh 是显示或缓存，不是权威科学数据。只有 Geometry Nodes 实际消费的当前帧或当前视图属性才复制进 Blender datablock。

### 定位与恢复

- sidecar locator 优先保存相对路径；无法相对定位时才保存显式绝对路径。
- 打开 `.blend` 时必须同时校验 project UUID 和 schema version，不能只相信路径。
- 边车缺失、版本不兼容或 UUID 不匹配时，场景保持可打开，但相关对象标记为 disconnected/stale；不得删除对象、覆盖边车或把缓存宣称为最新。
- 重新链接只能选择与记录 project UUID 一致的边车，除非用户明确执行项目迁移。
- 本地恢复不触发网络下载、依赖安装或外部程序执行。

### Revision 与缓存失效

每个权威实体具有不透明 `revision`。实体数值、shape/dims/unit、semantic role 或影响解释的 metadata 改变时，revision 必须改变。revision 的具体生成算法留给存储设计。

派生缓存身份至少包含：

```text
input entity UUIDs + input revisions
+ operation ID/version
+ normalized parameters
+ adapter version
```

以下任一变化都会使相关缓存 stale：

- 输入 entity revision 改变；
- source hash 或 parser version 改变并导致重新归一化；
- 派生 operation、参数或版本改变；
- Blender adapter 版本改变且其输出契约不兼容；
- project UUID 或 dataset UUID 不匹配。

纯显示参数只有在改变派生几何或采样结果时才进入 derivation identity；材质颜色等可直接更新的视图状态不强制重算科学数据。

### 写入边界

Blender adapter 读取 normalized entities 并生成显示对象，不直接修改 parser source。对权威数据的修改必须通过 core/project API 创建新 revision，再通知 Blender adapter 刷新。

worker 与 Blender 不共享可变 Python 对象；未来通过边车文件或本地 IPC 交换 UUID、revision 和任务结果。

## Consequences

- `.blend` 保持为场景与视图文件，不随轨道矩阵或网格无限增长。
- 普通 Python、worker 和 Blender 可以通过 UUID/revision 共享同一项目语义。
- 边车暂时不可用时不会破坏已有场景，但科学数据显示为断开或过期。
- 实现必须维护链接和 stale 状态，不能把 Blender datablock 当作恢复来源。

## Rejected Alternatives

- **全部数据写入 `.blend`**：大型数组、chunking、跨进程共享和语义验证均不合适。
- **Blender datablock 与边车同时作为权威来源**：产生冲突和双向同步问题。
- **只依赖原始输出文件，每次打开重新解析**：parser/version 变化会导致结果漂移，且启动成本不可控。
- **立即要求常驻数据库或服务**：本地文件工作流不需要该复杂度。

## Deferred

- `.cbq` 目录、manifest schema 和 source copy policy。
- Zarr、HDF5、NPZ、OpenVDB 与 chunk/compression 选择。
- revision canonicalization 和 cache 文件命名。
- 本地 IPC、远程 worker、锁和并发写入。
- Save As、项目复制和共享边车的用户界面。

## Verification Contract

后续实现必须证明：

1. `.blend` 侧只需 project/dataset UUID、revision 和 locator 即可恢复引用。
2. project UUID 不匹配、边车缺失和 schema 不兼容会进入 disconnected/stale 状态，不删除场景对象。
3. source、entity revision、operation 参数或 adapter version 改变时旧缓存失效。
4. 材质颜色变化不会无故重建权威 grid 或 surface 数据。
5. core/sidecar 测试不导入 `bpy`，Blender adapter 不把 datablock 当作权威恢复源。
