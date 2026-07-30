import bpy
import os, re
from .Chem_data import preset_smiles
from .core.import_pipeline import ValidationMode
from .legacy.reader_bridge import (
    file_import_request,
    smiles_import_request,
    stage_pubchem_import,
)
from .ui.session import get_scene_session
language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0

def is_valid_cid(s: str) -> bool:
    return s.strip().isdigit()

def is_valid_filepath(s: str) -> bool:
    s = s.strip()
    ext = os.path.splitext(s)[1].lower()
    valid_exts = {
        ".cif",
        ".sdf",
        ".mol",
        ".mol2",
        ".xyz",
        ".pdb",
        ".json",
        ".poscar",
        ".contcar",
        ".vasp",
    }
    return (
        ext in valid_exts
        or os.path.basename(s).lower() in {"poscar", "contcar"}
    )

def is_valid_smiles(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if s.isdigit():
        return False
    pattern = r'^[A-Za-z0-9@+\-\[\]\(\)=#%$*&,.\\/ ]+$'
    return re.fullmatch(pattern, s) is not None

# ------------------------------------------------------------------------------------
class ErrorDialogOperator(bpy.types.Operator):
    bl_idname = "wm.error_dialog"
    bl_label = "错误提示"

    message: bpy.props.StringProperty(default="发生了未知错误") # type: ignore

    def execute(self, context):
        self.report({'INFO'}, "关闭错误提示")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.label(text=self.message)

class ERROR_OT_CustomDialog(bpy.types.Operator):
    bl_idname = "error.custom_dialog"
    bl_label = "错误"

    message: bpy.props.StringProperty() # type: ignore

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=450)

    def draw(self, context):
        layout = self.layout
        for line in self.message.split("\n"):  # 让文本支持换行
            layout.label(text=line)

# 使用这个自定义弹窗
def show_error_dialog(message):
    bpy.ops.error.custom_dialog('INVOKE_DEFAULT', message=message)


class MESH_OT_SCAFFOLD_BUILD(bpy.types.Operator):
    bl_idname = "chem.scaffold_build"
    bl_label = "创建骨架" if language else "Build Scaffold"
    bl_description = "生成分子骨架的球棍模型" if language else "Generate ball and stick molecular model."
    bl_options = {'REGISTER','UNDO'}
    
    def text_input(self, mytool):
        if mytool.choose == 'File':
            moltext = mytool.filetext
        elif mytool.choose == 'SMILES':
            moltext = mytool.smilestext
        elif mytool.choose == "PubChem":
            moltext = mytool.pubchemtext
        elif mytool.choose == "Saccharides":
            moltext = preset_smiles[mytool.Saccharides][1]
        elif mytool.choose == "Amino_Acids":
            moltext = preset_smiles[mytool.Amino_Acids][1]
        elif mytool.choose == "Polymer_Units":
            moltext = preset_smiles[mytool.Polymer_Units][1]
        return moltext

    def mode_judge(self, mytool, moltext):
        mode = mytool.choose
        if mode == 'PubChem':
            return True  # 内部统一处理，不再拦截英文
        if mode == 'SMILES':
            if not is_valid_smiles(moltext):
                self.report({'ERROR'}, "Invalid SMILES")
                return False
        if mode == 'File':
            if not is_valid_filepath(moltext):
                self.report({'ERROR'}, "Invalid structure file")
                return False
        return True
    
    def execute(self, context):
        mytool = context.scene.my_tool
        try:
            moltext = self.text_input(mytool)
            
            if not self.mode_judge(mytool, moltext):
                return {'CANCELLED'}
            validation_mode = ValidationMode(getattr(
                getattr(
                    context.scene,
                    "chemblender_quick_import",
                    None,
                ),
                "validation_mode",
                "balanced",
            ))
            if mytool.choose in {
                "SMILES",
                "Saccharides",
                "Amino_Acids",
                "Polymer_Units",
            }:
                request = smiles_import_request(moltext, validation_mode)
                return bpy.ops.chemblender.import_smiles_text(
                    "EXEC_DEFAULT",
                    smiles_text=request.sources[0].text,
                    validation_mode=request.validation_mode.value,
                )
            if mytool.choose == "File":
                request = file_import_request(
                    os.path.abspath(bpy.path.abspath(moltext)),
                    validation_mode,
                )
                source = request.sources[0].path
                return bpy.ops.chemblender.quick_import(
                    "EXEC_DEFAULT",
                    directory=os.path.dirname(source),
                    files=[{"name": os.path.basename(source)}],
                    validation_mode=request.validation_mode.value,
                )
            if mytool.choose == "PubChem":
                stage = stage_pubchem_import(
                    moltext,
                    get_scene_session(context.scene),
                    validation_mode=validation_mode,
                )
                if stage.request is None:
                    show_error_dialog(stage.diagnostics[0].message)
                    return {'CANCELLED'}
                source = stage.request.sources[0].path
                return bpy.ops.chemblender.quick_import(
                    "EXEC_DEFAULT",
                    directory=os.path.dirname(source),
                    files=[{"name": os.path.basename(source)}],
                    validation_mode=stage.request.validation_mode.value,
                )
            return {'CANCELLED'}
        except Exception as e:
            print("导入错误:", e)
            text = f"操作失败: 请检查输入内容。\n错误信息: {e}" if language else f"Operation failed: Please check the input text. \nError: {e}"
            #bpy.ops.wm.error_dialog('INVOKE_DEFAULT', message=text)
            show_error_dialog(text)
            return {'CANCELLED'}

