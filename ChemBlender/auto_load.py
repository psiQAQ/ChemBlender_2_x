import bpy
import typing
import inspect

blender_version = bpy.app.version


def _safe_register_class(cls):
    if cls.is_registered:
        return False
    bpy.utils.register_class(cls)
    return True


def _safe_unregister_class(cls):
    if not cls.is_registered:
        return False
    bpy.utils.unregister_class(cls)
    return True


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
        sorted_chunk.sort(
            key=lambda cls: (
                getattr(cls, "bl_order", 0),
                cls.__module__,
                cls.__qualname__,
            )
        )
        sorted_list.extend(sorted_chunk)

    return sorted_list
