# ChemBlender Reader API v1

Reader API 是外部 Reader 与 chemblender-prepare 之间的纯 Python 数据边界。
当前冻结 token 为 `1.0-rc1`，兼容范围为 `>=1.0,<2.0`。它不提供
`QCProject`、Blender RNA 或第三方 parser 对象。

## 文档

- [插件 manifest](manifest.md)
- [Python API 与生命周期](python-api.md)
- [Worker API](worker-api.md)
- [诊断与故障隔离](diagnostics.md)
- [Conformance kit](conformance.md)
- [兼容与弃用策略](compatibility.md)

## 开发入口

- 内置 reader、capability 文档和 UI 接入：
  [Import Pipeline 与 Reader 开发](../development/import-pipeline.md)
- 可独立构建的外部 Extension：
  [SimpleCoords example](../../examples/reader-extension/README.md)

Extension reader 使用 in-process API；worker reader 使用固定 operation 和
canonical bundle。两者都不得扫描任意 `sys.path`、接收 `QCProject`、写 Blender
RNA，或传递 pickle、任意 callable/module/shell command。具体 failure、
cancellation 和兼容规则分别见 [诊断](diagnostics.md)、[Worker API](worker-api.md)
和 [兼容策略](compatibility.md)。

## External Python integration

当前 Reader 在 chemblender-prepare 外部环境运行；Viewer 不发布 Reader handle。
第三方 reader 由调用者显式注册，不扫描任意目录。`your_reader` 是用户已安装并信任的模块。

<!-- external-reader-bootstrap -->
```python
from chemblender_prepare import reader_api
from chemblender_prepare.reader_api.discovery import ReaderPluginDiscovery
from your_reader import create_plugin

registry = reader_api.builtin_reader_plugin_registry()
discovery = ReaderPluginDiscovery(registry)
plugin = create_plugin(reader_api)
state = discovery.register(plugin)
if not state.availability.available:
    raise RuntimeError(state.availability.reason_code)
snapshot = discovery.refresh()
# Use this registry with the external import pipeline before unregistering.
discovery.unregister(plugin.manifest)
```

这是外部 Python 接口；当前 CLI 默认仅注册22个内置 reader，不会自动加载此处的
第三方实例。解析和事务提交继续使用 `preflight_reader_plugins` 与
`commit_import_preview`。`PublicImportBatch` 是中间结果，须校验并保存为 CBQ 后交给 Viewer。

## Installed Extension bootstrap（历史2.3接口）

下列代码仅供旧版本迁移对照，不能用于当前 CBQ Viewer。旧 Reader 的 parser 可复用，
但应改用上面的外部 Python 接口。

<!-- installed-extension-bootstrap -->
```python
import importlib

import bpy

from . import reader


_handle = None
_plugin = None


def register():
    global _handle, _plugin
    if _plugin is not None:
        return
    handle = bpy.app.driver_namespace.get("chemblender.reader_api.v1")
    if handle is None:
        return
    api = importlib.import_module(handle.module_name)
    plugin = reader.create_plugin(api)
    handle.register_callback(plugin)
    _handle, _plugin = handle, plugin


def unregister():
    global _handle, _plugin
    if _handle is not None and _plugin is not None:
        _handle.unregister_callback(_plugin.manifest)
    _handle = _plugin = None
```

缺少宿主 handle 时，插件保持 unavailable，不得让 Blender 启动失败。注册失败应
转为插件自身诊断；不得修改 ChemBlender registry 或项目目录。
