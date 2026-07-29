from dataclasses import dataclass

from ..reader_api.discovery import ReaderPluginDiscovery
from ..reader_api.registry import (
    ReaderPluginRegistry,
    builtin_reader_plugin_registry,
)
from ..reader_api.version import READER_API_VERSION


READER_API_HANDLE_KEY = "chemblender.reader_api.v1"


class ReaderAPIRegistrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReaderAPIHandle:
    api_version: str
    module_name: str
    owner_token: object
    register_callback: object
    unregister_callback: object


_OWNER_TOKEN = object()
_REGISTRY = builtin_reader_plugin_registry()
_DISCOVERY = ReaderPluginDiscovery(_REGISTRY)
_published_handle = None


def get_reader_plugin_registry() -> ReaderPluginRegistry:
    return _REGISTRY


def refresh_reader_plugin_discovery():
    return _DISCOVERY.refresh()


def _register_plugin(plugin):
    return _DISCOVERY.register(plugin)


def _unregister_plugin(manifest):
    return _DISCOVERY.unregister(manifest)


def _driver_namespace():
    import bpy

    return bpy.app.driver_namespace


def register_reader_api_handle(package_root, *, namespace=None):
    global _published_handle

    if type(package_root) is not str or not package_root:
        raise TypeError("package_root must be a non-empty string")
    namespace = _driver_namespace() if namespace is None else namespace
    module_name = f"{package_root}.reader_api"
    if (
        _published_handle is not None
        and _published_handle.module_name != module_name
    ):
        raise ReaderAPIRegistrationError(
            "reader API handle is already published for another package"
        )
    existing = namespace.get(READER_API_HANDLE_KEY)
    if existing is not None:
        if existing is _published_handle:
            return existing
        raise ReaderAPIRegistrationError(
            "reader API handle key is owned by another publisher"
        )
    if _published_handle is None:
        _published_handle = ReaderAPIHandle(
            READER_API_VERSION,
            module_name,
            _OWNER_TOKEN,
            _register_plugin,
            _unregister_plugin,
        )
    namespace[READER_API_HANDLE_KEY] = _published_handle
    return _published_handle


def remove_reader_api_handle(handle, *, namespace=None):
    global _published_handle

    if type(handle) is not ReaderAPIHandle:
        return False
    namespace = _driver_namespace() if namespace is None else namespace
    if (
        handle is not _published_handle
        or handle.owner_token is not _OWNER_TOKEN
        or namespace.get(READER_API_HANDLE_KEY) is not handle
    ):
        return False
    del namespace[READER_API_HANDLE_KEY]
    _published_handle = None
    return True
