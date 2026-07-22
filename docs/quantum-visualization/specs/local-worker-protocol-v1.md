# 本地 worker 协议 v1

## 目标

让 Blender Extension 将 GBasis、PyProcar 等重计算交给独立 Python 进程，同时保持
`.cbq` 为唯一权威项目边界。协议是本地文件协议，不是远程 RPC。

## Request

request 是严格 JSON object：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `protocol_version` | `"1"` | 精确版本协商 |
| `request_id` | UUID | 一次任务身份 |
| `project_locator` | string | 相对 request 文件或绝对 `.cbq` 路径 |
| `project_id` | UUID | 防止错连项目 |
| `project_schema_version` | string | normalized schema 要求 |
| `operation_id` | lower token | 固定 registry 中的操作 |
| `operation_version` | string | 操作契约版本 |
| `inputs` | entity refs | 输入 UUID 与 revision |
| `parameters` | JSON object | 规范化参数，不含 Python object |

未知字段、NaN/Infinity、重复或无效 input identity、未知 operation 均拒绝。request 不允许
携带 module/class 名称，因此不能触发动态 import。

## Result

result 状态为 `success`、`error` 或 `cancelled`，包含 request ID、worker/protocol version、
输出 entity refs、artifact 相对路径、cache key 或结构化 error。成功发布前必须：

1. operation 正常返回；
2. 取消标记仍未出现；
3. 重开 `.cbq`；
4. 每个声明输出 UUID/revision 都可在 project registries 找到；
5. result 通过临时文件、fsync、`os.replace` 原子发布。

普通 `Exception` 写 `error`；取消写 `cancelled`；`SystemExit`、进程被杀或 interpreter crash
不写结果。因此调用方只把完整且校验通过的 `success` result 当作完成。

## Cancellation

runner 接受独立 cancel marker path。Blender 通过原子创建 marker 请求取消。operation 可通过
context 在 chunk 边界轮询；runner 至少在执行前和成功发布前检查一次。v1 不承诺强制中断
不响应的第三方 native call，调用方可终止 worker 进程，此时没有 success result。

## Operation registry

registry 由 worker 环境显式注册 `(operation_id, operation_version) -> callable`。v1 内置
`project.verify@1` 作为安装和协议探针。GBasis、PyProcar 等 operation 在其可选 worker
extras 中注册，不进入 Blender Extension import 路径。

v1 已注册的 operation：

| Operation | Inputs（顺序） | Parameters | 输出 |
| --- | --- | --- | --- |
| `project.verify@1` | 无 | 无 | project/schema metadata |
| `wavefunction.mo_grid@1` | Structure、BasisSet、OrbitalSet | origin、step_vectors、shape、channel、orbital_index | Grid3D + provenance |
| `wavefunction.electron_density_grid@1` | Structure、BasisSet、OrbitalSet | origin、step_vectors、shape | Grid3D + provenance |

## 安全边界

- 本地恢复不联网、不安装包、不执行 request 提供的代码。
- artifact path 必须相对 `.cbq` 且不得包含 `..`。
- result 不包含 traceback；详细诊断写 worker 自有日志。
- v1 是单 request/single process；守护进程、队列和远程 transport 不在范围内。
