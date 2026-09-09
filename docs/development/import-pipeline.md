# Import Pipeline 与 Reader 开发

原始文件解析、Reader API、科学派生和原始格式导出属于外部
`chemblender_prepare`；共享实体、单位和 CBQ 读写属于 `cbq_core`。
Blender 只导入已准备的 CBQ。科学 parser 不创建 `bpy` 对象，也不直接发布文件。
使用入口见 [Prepare](../prepare/README.md)，完整目标见
[本地处理模块方案](../quantum-visualization/architecture/local-processor.md)。

## 当前 CLI 转换流程

[`cli.py`](../../chemblender_prepare/cli.py) 的 `convert` 执行：

```text
原始文件 + 显式 reader 参数 + companion 文件
  -> bounded sniff + ReaderPluginRegistry availability
  -> 私有任务目录复制输入，复验 SHA-256
  -> reader.parse@0.1 -> PublicImportBatch 与 NPY 中间文件
  -> parse_with_worker() 校验结果 -> QCProject.commit()
  -> 规范化 CBQ 1.1 -> 私有目录保存 -> 重开并校验数组
  -> 取消检查 -> 原子发布到新的输出目录
  -> Blender CBQ 事务导入 -> 独立创建 View
```

输入、配套文件和 worker 输出都须复验。`--project` 读取现有 CBQ 作为准备基础，
输出必须使用不同的新目录；失败不覆盖原包。`critic2` 使用专用适配入口，要求
已有 Structure 绑定。`inspect` 只返回报告，不发布 CBQ。Tk GUI 通过子进程调用
同一 CLI；不是另一套 parser。当前 CLI 默认仅注册22个内置 reader，不自动加载
第三方 Python 插件，也不等同于尚待接通的 Blender 统一异步控制器。

## 外部 Python 的预览与确认事务

需要自定义 reader 或逐来源确认的 Python 调用者可使用
[`preflight_reader_plugins()`](../../chemblender_prepare/reader_api/import_pipeline_bridge.py)：

```text
ImportRequest -> SniffRequest -> ParseRequest -> PublicImportBatch
  -> owned StagedImportSession -> ImportPreview + ImportDiagnostic
  -> explicit ImportCommitDecisions -> commit_import_preview()
  -> verified CBQ publication
```

[`commit_import_preview()`](../../chemblender_prepare/core/import_pipeline/transaction.py)
在 disposable project candidate 中提交，再发布并重开验证。此 API 与 CLI 的直接
worker 转换是不同调用入口，共享科学模型和校验约束。不要把 CLI 描述成调用旧
Blender Import Preview 弹窗。科学提交与 View 创建是两个边界，后者失败不能声称
前者已回滚。

## 添加内置 reader

1. 在 `chemblender_prepare/core/` 或 `chemblender_prepare/core/formats/` 实现
   parser、bounded `sniff` 和 `ReaderDescriptor`。parser 返回内部 `ImportBatch`；
   built-in wrapper 将它投影为 `PublicImportBatch`。
2. `ReaderDescriptor` 声明稳定 `reader_id`/version、扩展名、三态 capability、
   priority、sniff 和 parse。request-aware reader 使用 `parse_request` 或成对的
   `preview_request` / `materialize_request`；`ReaderRuntimeDescriptor` 声明
   execution mode 和 availability。不要创建第二套项目模型。
3. 返回科学实体、`ParserReport`、`ParserIssue` 和必要的 `ImportDiagnostic`。
   `stage_import_batch()` 负责 SourceRecord、SourceRevision、canonical parameters
   和诊断绑定；parser 不自行处理项目冲突。
4. 更新 [`builtin_reader_descriptors()`](../../chemblender_prepare/core/reader_catalog.py)。
   registry 为内置 reader 合成 `ReaderPluginManifest`。同步 optional dependency、
   extensionless basename、export maturity/loss policy 和 fixture family。
5. 按 [测试 fixture](testing-fixtures.md) 添加可审计输入及 provenance，覆盖
   exact、partial/ambiguous、invalid、取消和来源变化。
6. 导出复用 `chemblender_prepare/core/exporters/` 和
   [`export_service.py`](../../chemblender_prepare/export_service.py)，先给出 loss preview，
   需要确认时由 CLI `--confirm-loss` 或 GUI 显式同意；不支持导出保持 `F0`。
7. 用户交互连接外部 [`gui.py`](../../chemblender_prepare/gui.py) 的 CLI 参数；
   Blender 使用 [`cbq_import.py`](../../ChemBlender/ui/cbq_import.py) 与 Project Browser。
   新 Blender module 必须成为显式 registration root，科学数组不得进入 RNA。

在项目已批准的外部环境中运行（不向 Blender 安装依赖）：

```powershell
uv run --frozen python -m unittest `
  tests.test_reader_conformance_v1 `
  tests.test_reader_api_import_bridge `
  tests.test_prepare_cli `
  tests.test_generated_docs_fresh -v
uv run --frozen python ChemBlender/scripts/generate_format_docs.py --check
```

`tests.test_reader_conformance_v1` 检查 descriptor、来源、引用、单位、质量、
canonical round-trip、progress、cancellation 和异常隔离。
`generate_format_docs.py --check` 检查 catalog 与能力文档一致。

## 第三方 reader 与 Worker

第三方 reader 在外部 Python 中使用 [Reader API v1](../reader-api-v1/README.md#external-python-integration)。
[`examples/reader-extension/`](../../examples/reader-extension/README.md) 的 `reader.py`
可复用；其中 Blender 安装 bootstrap 仅为历史2.3示例。当前 Viewer 不提供
`bpy.app.driver_namespace["chemblender.reader_api.v1"]` 注册入口。
`ReaderPluginDiscovery` 只接受显式注册，不扫描任意 `sys.path`；registry 拒绝
重复或 reserved ID 及 manifest/descriptor 冲突。提交的 CBQ 不依赖 reader 留在机器上。

Worker 使用固定 `reader.parse@0.1` operation。调用者提供任务目录内 source
artifact、SHA-256、validation mode 和 canonical parameters。
[`parse_with_worker()`](../../chemblender_prepare/reader_api/worker_bridge.py) 核对
request/result UUID、source/bundle hash、operation/schema、inventory、dtype/shape
和 batch 图。reader/plugin/version/`parse_identity` 由固定 worker 构造，host
当前不独立重算；精确信任边界见 [Worker API](../reader-api-v1/worker-api.md)。
中间 canonical document 与 NPY 不是可交付的 CBQ。

## 安全与依赖方向

- `cbq_core` 使用标准库和 NumPy；外部 parser/Reader API 不依赖 `bpy`。
- reader 不获得 Scene、registry owner、凭据或任意项目目录写权限。
- source 在 parse 前后复验；canonical parameters 只能是稳定 string mapping。
- worker request 不接受任意 module、callable、argv、shell 或 pickle。
- 普通 reader `Exception` 被隔离；`MemoryError`、`KeyboardInterrupt` 和
  `SystemExit` 原样传播。
- staging 只清理自身拥有的目录；失败或取消不发布半成品。发布前检查取消不能
  替代各重计算循环的协作取消与响应时间验收。

公共符号和兼容规则见 [Python API](../reader-api-v1/python-api.md)及
[compatibility policy](../reader-api-v1/compatibility.md)。
