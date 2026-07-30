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
