"""Blender drag-and-drop entry points for Quick Import."""

import bpy

from ..reader_api.manifest import _extensions


def _builtin_extension_string(descriptors):
    normalized = set()
    for descriptor in descriptors:
        if (
            descriptor.plugin_id != "chemblender.builtin"
            or not descriptor.availability.available
        ):
            continue
        for extension in descriptor.extensions:
            try:
                normalized.add(_extensions((extension,))[0])
            except (TypeError, ValueError):
                continue
    return ";".join(sorted(normalized))


def _poll_region(context, region_type):
    area = getattr(context, "area", None)
    region = getattr(context, "region", None)
    return bool(
        getattr(area, "type", None) == "VIEW_3D"
        and getattr(region, "type", None) == region_type
    )


_FILE_HANDLER_BASE = getattr(bpy.types, "FileHandler", None)
_FILE_EXTENSIONS = ""

if _FILE_HANDLER_BASE is not None:
    from ..runtime.reader_api_bridge import get_reader_plugin_registry

    _FILE_EXTENSIONS = _builtin_extension_string(
        get_reader_plugin_registry().descriptors
    )

    class CHEMBLENDER_FH_view_3d_window(_FILE_HANDLER_BASE):
        bl_idname = "CHEMBLENDER_FH_view_3d_window"
        bl_label = "ChemBlender Quick Import"
        bl_import_operator = "chemblender.quick_import"
        bl_file_extensions = _FILE_EXTENSIONS

        @classmethod
        def poll_drop(cls, context):
            return _poll_region(context, "WINDOW")


    class CHEMBLENDER_FH_project_browser(_FILE_HANDLER_BASE):
        bl_idname = "CHEMBLENDER_FH_project_browser"
        bl_label = "ChemBlender Project Browser Import"
        bl_import_operator = "chemblender.quick_import"
        bl_file_extensions = _FILE_EXTENSIONS

        @classmethod
        def poll_drop(cls, context):
            return _poll_region(context, "UI")


    FILE_HANDLER_CLASSES = (
        CHEMBLENDER_FH_view_3d_window,
        CHEMBLENDER_FH_project_browser,
    )
else:
    FILE_HANDLER_CLASSES = ()


_REGISTERED_CLASSES = ()


def register():
    global _REGISTERED_CLASSES

    if _REGISTERED_CLASSES:
        return
    registered = []
    try:
        for cls in FILE_HANDLER_CLASSES:
            if not cls.is_registered:
                registered.append(cls)
                bpy.utils.register_class(cls)
    except BaseException as failure:
        remaining = []
        for cls in reversed(registered):
            try:
                if cls.is_registered:
                    bpy.utils.unregister_class(cls)
            except BaseException as cleanup_error:
                if cls.is_registered:
                    remaining.append(cls)
                failure.add_note(
                    f"{cls.__name__} rollback failed: "
                    f"{type(cleanup_error).__name__}"
                )
        _REGISTERED_CLASSES = tuple(reversed(remaining))
        raise
    _REGISTERED_CLASSES = tuple(registered)


def unregister():
    global _REGISTERED_CLASSES

    remaining = []
    failure = None
    for cls in reversed(_REGISTERED_CLASSES):
        try:
            if cls.is_registered:
                bpy.utils.unregister_class(cls)
        except BaseException as error:
            if cls.is_registered:
                remaining.append(cls)
            if failure is None:
                failure = error
            else:
                failure.add_note(
                    f"{cls.__name__} unregister failed: "
                    f"{type(error).__name__}"
                )
    _REGISTERED_CLASSES = tuple(reversed(remaining))
    if failure is not None:
        raise failure


__all__ = (
    "CHEMBLENDER_FH_project_browser",
    "CHEMBLENDER_FH_view_3d_window",
    "FILE_HANDLER_CLASSES",
) if FILE_HANDLER_CLASSES else ("FILE_HANDLER_CLASSES",)
