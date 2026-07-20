from ..constants import SCENE_SETTINGS_NAME


def get_extension_settings(context):
    scene = getattr(context, "scene", None)
    return getattr(scene, SCENE_SETTINGS_NAME, None) if scene else None
