# Reader API 0.x alpha conformance

Reader API `0.x` 在 alpha 期间仍可变更。第三方实验只能使用 Blender 已发布 handle 所解析模块上的公开成员；不得硬编码源码或 extension namespace。

```python
import importlib
import bpy

handle = bpy.app.driver_namespace["chemblender.reader_api.v0"]
reader_api = importlib.import_module(handle.module_name)

case = reader_api.ReaderConformanceCase(...)
result = reader_api.run_reader_conformance(case)
```

可导入的 conformance 公共成员仅为 `ReaderConformanceCase`、`ReaderConformanceCheck`、`ReaderConformanceResult` 与 `run_reader_conformance`。结果的机器可读 schema 版本是 `0.1`；`ReaderConformanceResult.as_dict()` 只返回确定性的 JSON 安全值。

Runner 依次核验 manifest、bounded/deterministic sniff、availability、parse 输出、来源身份、图引用、单位、diagnostics、canonical bundle round-trip、预取消与异常隔离。它是验证工具，不创建或修改项目。

通过 conformance 不授权插件修改 `QCProject`、使用 `bpy`、在 discovery 时导入 optional dependencies，或绕过主进程的来源、canonical bundle 与图验证。alpha 外部插件仍必须只经 handle 的 register/unregister callback 与文档化 Reader API 协作。

当前限制：该 runner 不提供 wall-clock timeout；长任务仍通过既有 progress/cancellation protocol 管理。它验证一个给定文件和 reader case，不替代发行门禁或 Blender runtime smoke test。
