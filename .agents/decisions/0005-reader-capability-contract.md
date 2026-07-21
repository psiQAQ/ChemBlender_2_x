# 0005：Reader Capability Contract

## Status

Accepted for Phase 0 quantum visualization foundation.

## Context

ChemBlender 当前通过扩展名白名单和分支代码选择 reader，已出现 `.mol2` 被声明允许但没有对应读取分支的问题。`.log`、`.out` 和无扩展名文件也不能仅凭后缀可靠区分来源程序。

本决策定义 reader 的注册、探测、能力和解析结果契约，不批准 cclib、IOData、ASE 等依赖，也不决定第三方插件发现机制。

## Decision

### 显式 Registry

P0 使用显式、进程内 reader registry。每个 reader 注册一个 descriptor：

| 字段 | 含义 |
| --- | --- |
| `reader_id` | 稳定、唯一的 ASCII 标识 |
| `reader_version` | reader 实现版本 |
| `extensions` | 小写后缀提示，可为空 |
| `capabilities` | reader 声明可能产生的语义能力及支持等级 |
| `priority` | 仅在匹配等级不同时辅助排序 |
| `sniff` | 对 bounded source prefix 的无副作用内容探测 |
| `parse` | 生成待校验 import batch，不直接修改项目 |

P0 不扫描模块、不读取 Python entry points，也不在运行时安装 reader。registry 中重复 `reader_id` 是启动时错误。

### Reader 选择

选择顺序如下：

1. 调用方提供 `reader_id` 时，只验证该 reader 存在并直接使用。
2. 否则扩展名用于形成候选集，但不能单独证明格式。
3. 候选 reader 对有限长度的文件前缀执行 `sniff`；需要 fallback 时允许其他通用 reader 参与。
4. `sniff` 返回 `exact`、`probable`、`possible` 或 `none`，并附带简短 evidence。
5. 选择唯一最高匹配等级；同等级多个候选无法由已声明 priority 明确区分时返回 ambiguous，不静默猜测。

`sniff` 不执行完整解析、不修改文件、不启动外部程序，也不导入 Blender。具体 prefix 字节上限在实现计划中确定并作为测试常量。

### Capability

capability 使用稳定的非空 token，例如 `structure`、`trajectory`、`energy`、`atomic_property`、`vibration`、`excited_state`、`orbital` 和 `grid`。P0 不建立覆盖全部量子化学程序的封闭枚举。

Descriptor 的声明等级至少区分：

| 等级 | 含义 |
| --- | --- |
| `supported` | reader 设计并测试了该能力 |
| `partial` | 仅覆盖该能力的部分字段或来源变体 |
| `unsupported` | 已知不能提供 |

静态 capability 说明 reader 的实现范围；单次解析结果仍由 `ParserReport` 记录实际 parsed、missing、unsupported、ambiguous 和 invalid 项。静态 `supported` 不保证每个来源文件都包含该物理量。

### Parse 输出与事务

reader 的 parse 阶段返回待提交 import batch，其中只包含 ADR 0003/0004 定义的 normalized entities、provenance 和 `ParserReport`。第三方容器如 `ccData`、ASE `Atoms` 或 IOData 对象不能越过 reader adapter 成为项目权威数据。

流程固定为：

```text
source → select reader → parse import batch → validate → atomic QCProject commit
```

reader 不直接修改 `QCProject`，验证失败时整个 batch 不提交。成功报告至少记录：

- reader ID 与版本；
- source 标识与 hash；
- sniff evidence；
- 创建的 entity UUID；
- parsed capability；
- missing、unsupported、ambiguous、invalid 和 warning issues；
- 计算正常结束、失败或不完整状态（来源可判断时）。

issue 必须指向 capability 或字段路径，并提供可展示的信息。未取得的数据不创建空 `PropertyDataset`。

### 能力矩阵

用户文档和 UI 展示的格式能力矩阵必须从已注册 descriptor 与通过的 fixtures 生成或校验，不能维护另一份仅靠手工更新的后缀白名单。

`.mol2` 必须成为回归契约：只有 registry 中存在可选中且通过 fixture 的 reader 时，才允许对外声明读取支持。

## Consequences

- 专用 reader、通用量化输出 reader 和 fallback 可以确定性组合。
- `.log/.out` 等模糊后缀不会直接路由到错误 parser。
- parser 单元测试可以在普通 CPython 中运行，且失败不会污染项目状态。
- 新格式必须同时提供 descriptor、能力声明和最小 fixture，不能只增加扩展名。

## Rejected Alternatives

- **继续扩展后缀分支**：声明与实现容易再次漂移，也不能处理通用后缀。
- **仅使用内容 sniffing**：忽略明确扩展名会增加无谓探测和误匹配。
- **立即采用动态插件发现**：目前没有独立第三方 reader，增加加载与版本边界而无实际收益。
- **直接向 Blender 返回第三方对象**：解析层与运行时重新耦合，难以测试和复用。

## Deferred

- cclib、IOData、ASE、Gemmi、pymatgen 等具体 adapter。
- Python entry points、外部 reader 插件和 worker 发现。
- sniff prefix 的最终大小与流式 source API。
- 完整 capability token 目录和 UI 布局。

## Verification Contract

后续最小实现必须证明：

1. registry 拒绝重复 reader ID。
2. 明确 `reader_id`、扩展名候选和 content sniff 按规定顺序工作。
3. 同等级冲突返回 ambiguous，不依赖注册顺序。
4. reader 返回的 batch 只有验证通过后才提交。
5. `.mol2` 支持声明必须有真实 reader 与 fixture，不能只在后缀列表中出现。
6. core reader contract 测试不导入 `bpy`。
