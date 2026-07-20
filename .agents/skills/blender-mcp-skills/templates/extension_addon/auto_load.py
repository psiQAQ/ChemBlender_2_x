import bpy
import typing
import inspect
import pkgutil
import importlib
import sys
from pathlib import Path

blender_version = bpy.app.version
modules = []
ordered_classes = []
EXCLUDED_SUBMODULE_DIRS = {"deps", "wheels", "scripts", ".venv", "venv", "__pycache__"}


def clear_submodule_cache(package_name):
    if not package_name:
        return

    prefix = package_name + "."
    for name in list(sys.modules):
        if name == __name__:
            continue
        if name.startswith(prefix):
            del sys.modules[name]


def init():
    global modules
    global ordered_classes

    clear_submodule_cache(__package__)
    modules = get_all_submodules(Path(__file__).parent)
    ordered_classes = get_ordered_classes_to_register(modules)


def register():
    for cls in ordered_classes:
        _safe_register_class(cls)

    for module in modules:
        if module.__name__ == __name__:
            continue
        if hasattr(module, "register"):
            module.register()


def unregister():
    global modules
    global ordered_classes

    if modules is None:
        modules = []
    if ordered_classes is None:
        ordered_classes = []

    for module in reversed(modules):
        if module.__name__ == __name__:
            continue
        if hasattr(module, "unregister"):
            module.unregister()

    for cls in reversed(ordered_classes):
        _safe_unregister_class(cls)

    modules = []
    ordered_classes = []


def _safe_register_class(cls):
    try:
        bpy.utils.register_class(cls)
        return True
    except ValueError:
        return False


def _safe_unregister_class(cls):
    try:
        bpy.utils.unregister_class(cls)
        return True
    except (ValueError, RuntimeError):
        return False


def get_all_submodules(directory):
    return list(iter_submodules(directory, __package__))


def iter_submodules(path, package_name):
    for name in sorted(iter_submodule_names(path)):
        yield importlib.import_module("." + name, package_name)


def iter_submodule_names(path, root=""):
    for _, module_name, is_package in pkgutil.iter_modules([str(path)]):
        if module_name in EXCLUDED_SUBMODULE_DIRS:
            continue
        if is_package:
            sub_path = path / module_name
            sub_root = root + module_name + "."
            yield from iter_submodule_names(sub_path, sub_root)
        else:
            yield root + module_name


def get_ordered_classes_to_register(modules):
    return toposort(get_register_deps_dict(modules))


def get_register_deps_dict(modules):
    my_classes = set(iter_my_classes(modules))
    my_classes_by_idname = {cls.bl_idname: cls for cls in my_classes if hasattr(cls, "bl_idname")}

    deps_dict = {}
    for cls in my_classes:
        deps_dict[cls] = set(iter_my_register_deps(cls, my_classes, my_classes_by_idname))
    return deps_dict


def iter_my_register_deps(cls, my_classes, my_classes_by_idname):
    yield from iter_my_deps_from_annotations(cls, my_classes)
    yield from iter_my_deps_from_parent_id(cls, my_classes_by_idname)


def iter_my_deps_from_annotations(cls, my_classes):
    for value in typing.get_type_hints(cls, {}, {}).values():
        dependency = get_dependency_from_annotation(value)
        if dependency is not None and dependency in my_classes:
            yield dependency


def get_dependency_from_annotation(value):
    if blender_version >= (2, 93):
        if isinstance(value, bpy.props._PropertyDeferred):
            return value.keywords.get("type")
    else:
        if isinstance(value, tuple) and len(value) == 2:
            if value[0] in (bpy.props.PointerProperty, bpy.props.CollectionProperty):
                return value[1]["type"]
    return None


def iter_my_deps_from_parent_id(cls, my_classes_by_idname):
    if issubclass(cls, bpy.types.Panel):
        parent_idname = getattr(cls, "bl_parent_id", None)
        if parent_idname is not None:
            parent_cls = my_classes_by_idname.get(parent_idname)
            if parent_cls is not None:
                yield parent_cls


def iter_my_classes(modules):
    base_types = get_register_base_types()
    for cls in get_classes_in_modules(modules):
        if any(issubclass(cls, base) for base in base_types):
            if not getattr(cls, "is_registered", False):
                yield cls


def get_classes_in_modules(modules):
    classes = set()
    for module in modules:
        for cls in iter_classes_in_module(module):
            classes.add(cls)
    return classes


def iter_classes_in_module(module):
    for value in module.__dict__.values():
        if inspect.isclass(value):
            yield value


def get_register_base_types():
    return {
        getattr(bpy.types, name)
        for name in [
            "Panel",
            "Operator",
            "PropertyGroup",
            "AddonPreferences",
            "Header",
            "Menu",
            "Node",
            "NodeSocket",
            "NodeTree",
            "UIList",
            "RenderEngine",
            "Gizmo",
            "GizmoGroup",
        ]
    }


def toposort(deps_dict):
    sorted_list = []
    sorted_values = set()

    while len(deps_dict) > 0:
        unsorted = []
        sorted_chunk = []

        for value, deps in deps_dict.items():
            if len(deps) == 0:
                sorted_chunk.append(value)
                sorted_values.add(value)
            else:
                unsorted.append(value)

        if not sorted_chunk:
            raise RuntimeError("Cyclic or unresolved registration dependencies detected")

        deps_dict = {value: deps_dict[value] - sorted_values for value in unsorted}
        sorted_chunk.sort(key=lambda cls: getattr(cls, "bl_order", 0))
        sorted_list.extend(sorted_chunk)

    return sorted_list
