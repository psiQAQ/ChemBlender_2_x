# 自动化与 Reader 扩展 API

## Worker Protocol v1

调用 `chemblender-prepare worker request.json result.json [--cancel-file PATH]`。request 包含 CBQ project、project ID/schema/revision、operation ID/version、inputs、parameters 与 artifacts。worker 原子写进度、检查取消，并发布一个 success/cancelled/error result。Blender 会拒绝身份不匹配、过期 revision、无效 hash 和位于任务目录外的输出。

规范字段见 [local-worker-protocol-v1.md](../../quantum-visualization/specs/local-worker-protocol-v1.md)。request/result 均按不可信输入处理，不要修改正在运行的任务文件。

## Reader API 1.0-rc1

Reader 扩展使用 `chemblender_prepare.reader_api`、manifest、确定性 discovery、descriptor 和 worker bridge。从 [Reader API 总览](../../reader-api-v1/README.md)、[manifest](../../reader-api-v1/manifest.md)、[Python API](../../reader-api-v1/python-api.md)、[worker bridge](../../reader-api-v1/worker-api.md)、[conformance](../../reader-api-v1/conformance.md)开始。

兼容 token 固定为 `1.0-rc1`。reader 在声明的环境中运行，不能访问 Blender 内部模块。源码生成的 reader 清单见 [public-surface.json](../public-surface.json)。
