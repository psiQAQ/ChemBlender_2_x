# ChemBlender.core 公共门面

`ChemBlender.core` 可在普通 CPython 中导入，且不依赖 `bpy`。精确的权威名称列表为 `ChemBlender.core.__all__`，由 [tests/test_core_public_api.py](../../../tests/test_core_public_api.py) 强制检查。

## 稳定模型门面

模型类和枚举是稳定门面；其构造器与 `.cbq` sidecar 类型标签保持兼容。请从 [ChemBlender.core](../../../ChemBlender/core/__init__.py) 导入这些语义模型。

## 存储 API

`open_project`、`save_project`、`close_project`、`LazyNpyArray` 及 `Sidecar*Error` 构成 sidecar 存储 API，用于 `.cbq` 项目和数组引用的读取、写入与错误处理。

## Reader 契约

`ReaderDescriptor`、`ReaderRegistry`、`SniffMatch`、`SniffResult` 和 catalog API 是 alpha 0.x Reader 契约，尚非 v1。

## Recipe 契约

`RecipeDefinition`、绑定、参数、计划、校验与文档函数构成 Recipe 契约；其版本化数据定义是该契约的边界。

## 内部 Adapter 兼容面

具体 reader 与 adapter、派生 helper、scene/reporting 和 connector 导出在本任务中保持 import 兼容，但属于内部兼容面，不是冻结的插件 API。
