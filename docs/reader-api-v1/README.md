# ChemBlender Reader API v1

Reader API 是 Reader Extension 与 ChemBlender 之间的纯 Python 数据边界。
当前冻结 token 为 `1.0-rc1`，兼容范围为 `>=1.0,<2.0`。它不提供
`QCProject`、Blender RNA 或第三方 parser 对象。

## 文档

- [插件 manifest](manifest.md)
- [Python API 与生命周期](python-api.md)
- [Worker API](worker-api.md)
- [诊断与故障隔离](diagnostics.md)
- [Conformance kit](conformance.md)
- [兼容与弃用策略](compatibility.md)

## Installed Extension bootstrap

安装后的模块名由 Blender repository 决定，插件不得猜测宿主模块路径。只有
Extension 的 registration bootstrap 访问 `bpy`；reader 业务模块接收动态解析的
公开 API module。

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
