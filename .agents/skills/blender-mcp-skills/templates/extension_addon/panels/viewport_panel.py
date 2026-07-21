import bpy

from ..constants import OPERATOR_RUN_ID, PANEL_CATEGORY, PANEL_ID
from ..utils.common import get_extension_settings


class EXAMPLE_PT_panel(bpy.types.Panel):
    bl_idname = PANEL_ID
    bl_label = "Extension Demo"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY

    def draw(self, context):
        layout = self.layout
        settings = get_extension_settings(context)

        if settings:
            layout.prop(settings, "message")

        layout.operator(OPERATOR_RUN_ID, icon="PLAY")
