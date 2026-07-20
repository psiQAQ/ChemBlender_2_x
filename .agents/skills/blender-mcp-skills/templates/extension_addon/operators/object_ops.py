import bpy

from ..constants import OPERATOR_RUN_ID
from ..utils.common import get_extension_settings


class EXAMPLE_OT_run(bpy.types.Operator):
    bl_idname = OPERATOR_RUN_ID
    bl_label = "Run Example"
    bl_description = "Run a minimal extension operator"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = get_extension_settings(context)
        message = settings.message if settings else "Extension is running"
        self.report({"INFO"}, message)
        return {"FINISHED"}
