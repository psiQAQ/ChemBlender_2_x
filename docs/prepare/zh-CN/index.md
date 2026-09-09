# chemblender-prepare 0.1.0

[English](../en/index.md)

外部工具负责原始文件解析、科学派生、导出和诊断。Blender 通过 Worker Protocol v1 调用同一个 executable，不运行 `pip` 或 `uv`。

- [CLI 与 GUI](cli-and-gui.md)
- [Worker Protocol 与 Reader API](protocol-and-reader-api.md)
- [可选 route 配置](advanced-routes.md)
- [源码生成的公开能力清单](../public-surface.json)

公开兼容承诺只有 CLI、Worker Protocol v1、Reader API `1.0-rc1`。直接导入 `core.*`、GUI helper 或 worker 实现模块不受支持。
