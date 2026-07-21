import bpy

from .constants import SCENE_SETTINGS_NAME


class EXAMPLE_PG_settings(bpy.types.PropertyGroup):
    message: bpy.props.StringProperty(
        name="Message",
        description="Message shown by the demo operator",
        default="Hello from extension",
    )


def register():
    if not hasattr(bpy.types.Scene, SCENE_SETTINGS_NAME):
        setattr(
            bpy.types.Scene,
            SCENE_SETTINGS_NAME,
            bpy.props.PointerProperty(type=EXAMPLE_PG_settings),
        )


def unregister():
    if hasattr(bpy.types.Scene, SCENE_SETTINGS_NAME):
        delattr(bpy.types.Scene, SCENE_SETTINGS_NAME)
