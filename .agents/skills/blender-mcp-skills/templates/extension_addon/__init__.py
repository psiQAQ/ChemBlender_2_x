from . import auto_load
from .utils import dependency_manager


def register():
    dependency_manager.add_private_deps_path()
    auto_load.init()
    auto_load.register()


def unregister():
    auto_load.unregister()
    dependency_manager.remove_private_deps_path()
