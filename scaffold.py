import bpy
import os, re
from .read import check_type, read_MOL, read_Cryst, download_sdf_from_pubchem
from .mesh import create_object, add_scaffold_attr, unit_cell_edges, remove_doubles
from .Chem_data import preset_smiles
from . import node
from bpy.props import FloatProperty,StringProperty,IntProperty,EnumProperty,CollectionProperty
language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0

selected_pubchem_cid = None

def is_valid_cid(s: str) -> bool:
    return s.strip().isdigit()

def is_valid_filepath(s: str) -> bool:
    s = s.strip()
    ext = os.path.splitext(s)[1].lower()
    valid_exts = {".cif", ".sdf", ".mol", ".mol2", ".xyz", ".pdb", ".json", ".poscar", ".vasp"}
    return ext in valid_exts

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
    
    length_factor: FloatProperty(name='', default=1.0, min=0.0, max=3.0) # type: ignore
    boundary: FloatProperty(name='', default=0.0, min=0.0, max=1.0) # type: ignore
    grow_iter: IntProperty(name='', default=0, min=0, max=10) # type: ignore
    filter: StringProperty(name='', default='') # type: ignore

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

    def name_input(self, mytool, moltext):
        if os.path.exists(moltext):
            molname = os.path.basename(moltext).split('.')[0]
        elif mytool.choose == "Saccharides":
            molname = preset_smiles[mytool.Saccharides][0]
        elif mytool.choose == "Amino_Acids":
            molname = preset_smiles[mytool.Amino_Acids][0]
        elif mytool.choose == "Polymer_Units":
            molname = preset_smiles[mytool.Polymer_Units][0]
        elif mytool.choose == "PubChem":
            molname = download_sdf_from_pubchem(moltext)[1]
        else:
            molname = moltext
        return molname
    
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
    
    def draw(self, context):
        mytool = context.scene.my_tool
        try:
            moltext = self.text_input(mytool)
            text_type = check_type(moltext)
            if text_type.lower() in ('cif','vasp','poscar'):
                layout = self.layout

                row = layout.row()
                text = "过滤原子：" if language else "Filter Atom:"
                row.label(text=text)
                row.scale_x = 1.8
                row.prop(self, 'filter')

                row = layout.row()
                text = "键长系数:" if language else "Length Factor:"
                row.label(text=text)
                row.scale_x = 1.8
                row.prop(self, 'length_factor')

                row = layout.row()
                text = "边界扩展:" if language else "Boundary Expand:"
                row.label(text=text)
                row.scale_x = 1.8
                row.prop(self, 'boundary')

                row = layout.row()
                text = "直接扩展:" if language else "Direct Expand:"
                row.label(text=text)
                row.scale_x = 1.8
                row.prop(self, 'grow_iter')
        except Exception as e:
            print(e)

    def execute(self, context):
        global selected_pubchem_cid
        mytool = context.scene.my_tool
        wm = context.window_manager
        try:
            moltext = self.text_input(mytool)
            
            if not self.mode_judge(mytool, moltext):
                return {'CANCELLED'}
            if mytool.choose == "PubChem":
                from urllib.parse import quote
                import requests

                # 自动搜索：输入名称 → 拿第一个（最匹配）CID
                if not is_valid_cid(moltext):
                    try:
                        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{quote(moltext)}/cids/JSON"
                        res = requests.get(url, timeout=30)
                        data = res.json()
                        cid = str(data["IdentifierList"]["CID"][0])
                    except:
                        show_error_dialog(f"Cannot find molecule: {moltext}")
                        return {'CANCELLED'}
                else:
                    cid = moltext.strip()

                moltext = cid
            molname = self.name_input(mytool, moltext)
            text_type = check_type(moltext)
            filter_text = self.filter
            for sep in ',;/| ': filter_text = filter_text.replace(sep, ' ')
            filters = filter_text.split()
            filters = [filter.capitalize() for filter in filters]
            
            if text_type.lower() in ('cif','vasp','poscar'):
                data1, data2 = read_Cryst(moltext, text_type, self.length_factor, self.boundary)
                ATOMS, AtomicNum, COORDS, BONDS, BOND_ORDERS, VDW_R, Radii, RingNum = data1
                cell_lengths, cell_angles, space_group, space_group_num, symop_operations = data2
                print(symop_operations)
            else:
                data1 = read_MOL(moltext)[0][0]
                print(data1)
                ATOMS, AtomicNum, COORDS, BONDS, BOND_ORDERS, VDW_R, Radii, RingNum = data1
                cell_lengths = cell_angles = None
                
            coll = bpy.data.collections.new('Scaffold_'+molname)
            bpy.context.scene.collection.children.link(coll)
            mol_scaffold = create_object(coll, molname, COORDS, BONDS, [])
            mol_scaffold['Type'] = 'scaffold'
            mol_scaffold['Elements'] = f'{list(set(ATOMS))}'
            add_scaffold_attr(mol_scaffold, ATOMS, AtomicNum, BOND_ORDERS, VDW_R, Radii, RingNum)
            bpy.context.view_layer.objects.active = mol_scaffold

            if text_type.lower() in ('cif','vasp','poscar') and cell_lengths[0] is not None:
                remove_doubles(mol_scaffold)
                cell_edges = unit_cell_edges(molname, coll, cell_lengths[0], cell_lengths[1], cell_lengths[2],
                                                cell_angles[0], cell_angles[1], cell_angles[2], space_group)
                mol_scaffold.name = 'unit_'+ molname
                mol_scaffold['cell lengths'] = f'{cell_lengths[0]},{cell_lengths[1]},{cell_lengths[2]}'
                mol_scaffold['cell angles'] = f'{cell_angles[0]},{cell_angles[1]},{cell_angles[2]}'
                mol_scaffold['space group'] = space_group
                mol_scaffold['SG No.'] = space_group_num
                node.crys_expand(mol_scaffold, cell_lengths, cell_angles, self.grow_iter)

            # mol_scaffold.select_set(True)
            node.crys_filter(mol_scaffold, molname, filters)
            GN_mol = node.add_geometry_nodetree(mol_scaffold, "GN_"+molname, "NodeTree_"+molname)
            node.Ball_Stick_nodetree(GN_mol)
            return {'FINISHED'}
        except Exception as e:
            print("导入错误:", e)
            text = f"操作失败: 请检查输入内容。\n错误信息: {e}" if language else f"Operation failed: Please check the input text. \nError: {e}"
            #bpy.ops.wm.error_dialog('INVOKE_DEFAULT', message=text)
            show_error_dialog(text)
            return {'CANCELLED'}

