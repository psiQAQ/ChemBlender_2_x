import bpy, bmesh
import random
from . import mesh, node, _math
from bpy.types import Operator
from bpy.props import IntProperty, FloatProperty, BoolProperty, StringProperty,EnumProperty, FloatVectorProperty
from .Chem_data import metals,SPACE_GROUP_DATA,ELEMENTS_DEFAULT,SYMOP_OPERATIONS

language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0
warning_text = "请选择一个有效的分子骨架！" if language else "Please Select a Effective Mol Scaffold"

def simplify_text(text):
        for sep in ',;/| ': text = text.replace(sep, ' ')
        elements = text.split()
        elements = [e.capitalize() if e.isalpha() else e for e in elements]
        elements = ['bond' if e == 'Bond' else e for e in elements]
        if 'all' in text.lower() or '*' in text:
            elements += ['atom', 'bond']
        if 'atom' in text.lower() or 'ball' in text.lower():
            elements += ['atom']
        if 'bond' in text.lower() or 'ball' in text.lower():
            elements += ['bond']
        # e.g. ['C','H']
        bond_syms = [[x.split('-')[0].capitalize(),x.split('-')[1].capitalize()] for x in elements if '-' in x]
        return list(set(elements)), bond_syms

class SelectButton(Operator):
    bl_idname = "chem.select"
    bl_label = "选择" if language else "Select"
    bl_description = "根据输入内容选择点或边" if language else "Select vertices and edges based on input text"
    bl_options = {'REGISTER','UNDO'}
    
    def execute(self, context):
        mytool  = context.scene.my_tool
        text = mytool.select_text
        text, bond_syms = simplify_text(text)
        ao = bpy.context.object
        if not ao or ao.get('Type') != 'scaffold':
            self.report({'WARNING'}, warning_text)
            return {'CANCELLED'}
        else:
            mesh.deselect_all(ao)
            mesh.select_verts(ao, text)
            mesh.select_edges(ao, bond_syms)
            mesh.select_bond_orders(ao, text)
            if 'atom' in text: mesh.select_all(ao, 'VERT')
            if 'bond' in text: mesh.select_all(ao, 'EDGE')
            if 'all' in text or '*' in text: mesh.select_all(ao, 'VERT')
            return {'FINISHED'}

class EnhancedSelectButton(Operator):
    bl_idname = "chem.enhance_select"
    bl_label = "增强选择" if language else "Enhanced Select"
    bl_description = "编辑模式下的特殊选择方式" if language else "Special Select Methods in Edit Mode"
    bl_options = {'REGISTER','UNDO'}

    select_mode: EnumProperty(
        name = '',
        default = 'Random',
        items = [('Random', '随机选择', ''),
                 #('Mirror', '镜像选择', ''),
                 ('Topology', '拓扑筛选', ''),
                 ] if language else [
                     ('Random', 'Select Random', ''),
                     #('Mirror', 'Select Mirror', ''),
                     ('Topology', 'Topology Select', ''),
                 ]
    )
    rand_ratio: FloatProperty(name='', default=50.0, min=0.0, max=100.0, subtype='PERCENTAGE')
    rand_seed: IntProperty(name='', default=0)
    topo_counts: StringProperty(name='', default='0')
    limit_sel: BoolProperty(name='', default=True)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        text = "选择模式:" if language else "Select Mode:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "select_mode")
        if self.select_mode == 'Random':
            row = layout.row(align=True)
            text = "随机比率:" if language else "Random Ratio:"
            row.label(text=text)
            row.scale_x = 1.8
            row.prop(self, 'rand_ratio')
            row = layout.row(align=True)
            text = "随机种:" if language else "Random Seed:"
            row.label(text=text)
            row.scale_x = 1.8
            row.prop(self, 'rand_seed')
            row = layout.row(align=True)
            text = "限定当前所选范围" if language else "Limit to Current Selection"
            row.label(text=text)
            row.scale_x = 10
            row.prop(self, 'limit_sel')
        elif self.select_mode == 'Topology':
            row = layout.row(align=True)
            text = "拓扑数:" if language else "Topo Counts:"
            row.label(text=text)
            row.scale_x = 1.8
            row.prop(self, 'topo_counts')
            row = layout.row(align=True)
            text = "限定当前所选范围" if language else "Limit to Current Selection"
            row.label(text=text)
            row.scale_x = 10
            row.prop(self, 'limit_sel')

    def execute(self, context):
        ao = context.active_object
        if not ao or ao.type != 'MESH':
            self.report({'WARNING'}, "请选中一个网格物体." if language else "Please Select a Mesh Object.")
            return {'CANCELLED'}
        
        if ao.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        sel_type = context.tool_settings.mesh_select_mode[:]       
        mesh = ao.data
        bm = bmesh.from_edit_mesh(mesh)
        topo_cache = {}

        if sel_type[0]:
            for idx, v in enumerate(bm.verts):
                topo_cache[idx] = len(v.link_edges)
        elif sel_type[1]:
            for idx, e in enumerate(bm.edges):
                topo_cache[idx] = len(e.link_faces)
        else:
            for idx, f in enumerate(bm.faces):
                topo_cache[idx] = len(f.edges)


        bpy.ops.object.mode_set(mode='OBJECT')
        if sel_type[0]:
            elements = mesh.vertices
        elif sel_type[1]:
            elements = mesh.edges
        else:
            elements = mesh.polygons
        
        candidates = [e for e in elements if e.select] if self.limit_sel else list(elements)
        if not candidates:
            self.report({'INFO'}, "无可选元素." if language else "No Available Elements.")
            bpy.ops.object.mode_set(mode='EDIT')
            return {'FINISHED'}

        if self.select_mode == 'Random':
            self._random_select(candidates)
        elif self.select_mode == 'Topology':
            self._topo_select(candidates, topo_cache)

        return {'FINISHED'}

    def _random_select(self, candidates):
        rng = random.Random(self.rand_seed)
        for elem in candidates:
            elem.select = False
        sel_count = 0
        for elem in candidates:
            if rng.random() < self.rand_ratio/100.0:
                elem.select = True
                sel_count += 1
        bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'}, f"已选中 {sel_count} 个元素." if language else f"{sel_count} Elements Selected.")
    
    def _topo_select(self, candidates, topo_cache):
        target_set = set()
        for sep in ',;/| ': text = self.topo_counts.replace(sep, ' ')
        topo_list = text.split(' ')
        for s in topo_list:
            s = s.strip()
            if s.isdigit():
                target_set.add(int(s))

        for elem in candidates:
            elem.select = False
        sel_count = 0
        for elem in candidates:
            if topo_cache.get(elem.index, 0) in target_set:
                elem.select = True
                sel_count += 1
        bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'}, f"已选中 {sel_count} 个元素." if language else f"{sel_count} Elements Selected.")

        
        
class DistanceButton(Operator):
    bl_idname = "chem.button_distance"
    bl_label = "Calc Distnace"
    bl_description = "选择一条边计算长度" if language else "Calculate the length of a selected edge"

    def execute(self, context):
        mytool = context.scene.my_tool
        ao = bpy.context.object   # active object
        if not ao or bpy.context.mode == 'OBJECT':
            return {'CANCELLED'}
        else:
            distance = mesh.calc_length()
            mytool.distance = distance
            return {'FINISHED'}

class AngleButton(Operator):
    bl_idname = "chem.button_angle"
    bl_label = "Calc Angle"
    bl_description = "选择两条边计算夹角" if language else "Calculate the angle between two selected edges"

    def execute(self, context):
        mytool = context.scene.my_tool
        ao = bpy.context.object
        if not ao or bpy.context.mode == 'OBJECT':
            return {'CANCELLED'}
        else:
            angle = mesh.calc_angle()
            mytool.angle = angle
            return {'FINISHED'}
        
class EnergyButton(Operator):
    bl_idname = "chem.button_energy"
    bl_label = "Calc Energy"
    bl_description = "计算相对分子势能" if language else "Calculate the relative molecular potential energy"

    def execute(self, context):
        mytool = context.scene.my_tool
        ao = bpy.context.object
        if not ao or ao.get('Type') != 'scaffold':
            self.report({'WARNING'}, warning_text)
            return {'CANCELLED'}
        else:
            energy = mesh.calc_energy(ao)
            mytool.energy = energy
            return {'FINISHED'}
        
class SetAtomsButton(Operator):
    bl_idname = 'chem.set_atoms'
    bl_label = "设置原子" if language else "Atom Setting"
    bl_description = "设置选中点的原子属性" if language else "Set atom attributes of selected vertices"
    bl_options = {'REGISTER', 'UNDO'}

    atomic_num: IntProperty(name='', default=0, min=0, max=118)
    siteid: IntProperty(name='', default=0)
    scale_f: FloatProperty(name='', default=1.0, min=0.0)
    center: BoolProperty(name='', default=False)
    ligand: BoolProperty(name='', default=False)
    center_set: BoolProperty(name='', default=False)
    radius_type: EnumProperty(
        name = '',
        default = 'C',
        items = [('C', '共价半径', ''),
                 ('I', '离子半径', ''),
                 ('R', '晶体半径', ''),
                 ] if language else [
                     ('C', 'Covalent Radii', ''),
                     ('I', 'Ionic Radii', ''),
                     ('R', 'Crystal Radii', ''),
                 ]
    )
    charge: IntProperty(name='', default=1)
    coord_num: IntProperty(name='', default=4, min=0)
    rotate_angle: FloatProperty(name='', default=0.0, min=-180, max=180)
    n_carbon: IntProperty(name='', default=4, min=2)
    functional_group: EnumProperty(
        name = '',
        default = 'F0',
        items = [('F0', '元素', ''),
                 ('F1', '苯基', ''),
                 ('F2', '羧基', ''),
                 ('F3', '六元环', ''),
                 ('F4', '脂链', ''),
                 ] if language else [
                     ('F0', 'Element', ''),
                     ('F1', 'Benzyl', ''),
                     ('F2', 'Carboxyl', ''),
                     ('F3', 'Hexatomic Ring', ''),
                     ('F4', 'n-Chain', ''),
                 ]
    ) # type: ignore

    use_custom_color: BoolProperty(name="自定义颜色", default=False)
    atom_color: FloatVectorProperty(name="颜色", subtype='COLOR', default=(1,1,1,1), size=4, min=0, max=1) # type: ignore
    
    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        text = "官能团:" if language else "Functional Group:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "functional_group")
        if self.functional_group == 'F0':
            row = layout.row(align=True)
            text = "原子序数:" if language else "Atomic Number:"
            row.label(text=text)
            row.scale_x = 1.8
            row.prop(self, 'atomic_num')
            row = layout.row(align=True)
            row.label(text="SiteID:")
            row.scale_x = 1.8
            row.prop(self, 'siteid')
            row = layout.row(align=True)
            text = "缩放系数:" if language else "Scale Factor:"
            row.label(text=text)
            row.scale_x = 1.8
            row.prop(self, 'scale_f')
            row = layout.row(align=True)
            text = "半径类型:" if language else "Radii Type:"
            row.label(text=text)
            row.scale_x = 1.8
            row.prop(self, 'radius_type')
            
            if self.radius_type == 'I' or self.radius_type == 'R':
                row = layout.row(align=True)
                text = "电荷数:" if language else "Charge Number:"
                row.label(text=text)
                row.scale_x = 1.8
                row.prop(self, 'charge')
                row = layout.row(align=True)
                text = "配位数:" if language else "Coordination Number:"
                row.label(text=text)
                row.scale_x = 1.8
                row.prop(self, 'coord_num')
            
            row = layout.row(align=True)
            row.label(text="自定义颜色:" if language else "Custom Color:")
            row.scale_x = 18
            row.prop(self, "use_custom_color", text="")
            if self.use_custom_color:
                row = layout.row(align=True)
                row.label(text="颜色:" if language else "Color:")
                row.scale_x = 1.8
                row.prop(self, "atom_color", text="")

            row = layout.row(align=True)
            row.label(text="设置中心:" if language else "Center Set:")
            row.scale_x = 18
            row.prop(self, "center_set", text="")

            if self.center_set:
                row = layout.row(align=True)
                sub = row.split(factor=0.6, align=True)
                sub.label(text="设为中心原子" if language else "Set as Center")
                sub.prop(self, 'center', text="")

                # 右边 配位原子
                sub = row.split(factor=0.6, align=True)
                sub.label(text="设为配位原子" if language else "Set as Ligand")
                sub.prop(self, "ligand", text="")
                
        else:
            row = layout.row(align=True)
            text = "旋转角度:" if language else "Rotate Angle:"
            row.label(text=text)
            row.scale_x = 1.8
            row.prop(self, 'rotate_angle')
            if self.functional_group == 'F4':
                row = layout.row(align=True)
                text = "碳原子数:" if language else "Carbon Count:"
                row.label(text=text)
                row.scale_x = 1.8
                row.prop(self, 'n_carbon')

    def draw_new_scaffold(self, scaffold, fg_name):
        mesh.set_sel_atoms_attr(scaffold, atomic_num=6, scale_f=1.0, radius_type='C', charge=0, coord_num=0, center_set=False, 
                center=False, ligand=False, use_custom_color=True, custom_color=(0.12, 0.12, 0.12, 1.0),siteid=0)
        bpy.ops.object.mode_set(mode='OBJECT')
        bm = bmesh.new()
        bm.from_mesh(scaffold.data)
        vert_ids = []
        for vert in bm.verts:
            if vert.select:
                vert_ids.append(vert.index)
                bank, pitch, heading = _math.vert_hpb(vert,0)
                coords = _math.functional_group_coords(vert, bank, pitch, fg_name, self.rotate_angle, self.n_carbon)
                mesh.add_functional_groups(scaffold, coords, fg_name, self.n_carbon)
        bm.free()

    def execute(self, context):
        ao = bpy.context.object
        if not ao or ao.get('Type') != 'scaffold':
            self.report({'WARNING'}, warning_text)
            return {'CANCELLED'}
        if self.functional_group == 'F0':
            try:
                mesh.set_sel_atoms_attr(ao, self.atomic_num, self.scale_f, self.radius_type, self.charge, self.coord_num, self.center_set, 
                self.center, self.ligand, self.use_custom_color, self.atom_color, self.siteid)
            except Exception as e:
                print(e)
        elif self.functional_group == 'F1':
            self.draw_new_scaffold(ao, 'Benzyl')
        elif self.functional_group == 'F2':
                self.draw_new_scaffold(ao, 'Carboxyl')
        elif self.functional_group == 'F3':
            self.draw_new_scaffold(ao, 'Hexatomic Ring')
        elif self.functional_group == 'F4':
            self.draw_new_scaffold(ao, 'n-Chain')
        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}

          
class SetBondsButton(Operator):
    bl_idname = 'chem.set_bonds'
    bl_label = "设置键" if language else "Bond Setting"
    bl_description = "设置选中边的键属性" if language else "Set bond attributes of selected edges"
    bl_options = {'REGISTER', 'UNDO'}

    bond_order: IntProperty(name='', default=0, min=0, soft_max=3)
    bond_scale_f: FloatProperty(name='', default=1.0, min=0.0)
    ring_num: IntProperty(name='', default=0, min=0, soft_max=10)
    dashed_line: BoolProperty(name='', default=False)
    toggle_aromatic: BoolProperty(name='', default=False)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        text = "键级:" if language else "Bond Order:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "bond_order")
        row = layout.row(align=True)
        text = "缩放系数:" if language else "Bond Scale:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "bond_scale_f")
        row = layout.row(align=True)
        text = "环编号:" if language else "Ring Number:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "ring_num")
        row = layout.row(align=True)
        text = "虚线:" if language else "Dashed Line:"
        row.label(text=text)
        row.scale_x = 18
        row.prop(self, "dashed_line")
        row = layout.row(align=True)
        if self.bond_order == 0:
            text = "切换芳香键:" if language else "Toggle Aromatic:"
            row.label(text=text)
            row.scale_x = 18
            row.prop(self, "toggle_aromatic")
            
    def execute(self, context):
        ao = bpy.context.object
        if not ao or ao.get('Type') != 'scaffold':
            self.report({'WARNING'}, warning_text)
            return {'CANCELLED'}
        try:
            mesh.set_sel_bonds_attr(ao, self.bond_order, self.bond_scale_f, self.ring_num, self.dashed_line, self.toggle_aromatic)
            bpy.ops.object.mode_set(mode='EDIT')
            return {'FINISHED'}
        except Exception as e:
            print(e)
            return {'CANCELLED'}

class ConnectByDistance(bpy.types.Operator):
    bl_idname = "chem.connect_by_dist"
    bl_label = "按距离连接选中点" if language else "Connect by Distance"
    bl_description = "按距离连接选中点" if language else "Connect selected vertices by distance"
    bl_options = {'REGISTER', 'UNDO'}

    min_distance: FloatProperty(name='', default=0.0, min=0.0)
    max_distance: FloatProperty(name='', default=1.0, soft_max=5.0)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        text = "最小距离:" if language else "Min Distance:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "min_distance")
        row = layout.row(align=True)
        text = "最大距离:" if language else "Max Distance:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "max_distance")

    def execute(self, context):
        ao = context.active_object
        if not ao or ao.type != 'MESH':
            self.report({'WARNING'}, "请选中一个网格物体" if language else "Please Select a Mesh Object")
            return {'CANCELLED'}
        success, msg = mesh.connect_by_distance(ao, self.min_distance, self.max_distance)
        self.report({'INFO'} if success else {'WARNING'}, msg)
        return {'FINISHED'}

class AddHydrogens(Operator):
    bl_idname = 'chem.add_hydrogens'
    bl_label = "添加氢原子" if language else "Add Hydrogens"
    bl_description = "根据饱和度和空间构型补齐氢原子" if language else "Fill in hydrogen atoms based on saturation and spatial configuration"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 获取当前选中的物体
        ao = context.object
        
        # 检查是否选中了有效的物体
        if not ao or ao.get('Type') != 'scaffold':
            self.report({'WARNING'}, warning_text)
            return {'CANCELLED'}
        try:
            # 调用添加氢原子的函数
            mesh.add_hydrogens(ao)
            return {'FINISHED'}
        except Exception as e:
            # 打印异常信息，便于调试
            self.report({'ERROR'}, f"发生错误: {str(e)}")
            return {'CANCELLED'}

class AddBranches(Operator):
    bl_idname = 'chem.add_branches'
    bl_label = "设置分支参数" if language else "Set Branches Parameters"
    bl_description = "给选中的原子添加新的分支" if language else "Add new branches to selected atoms"
    bl_options = {'REGISTER', 'UNDO'}

    text = "计算饱和度" if language else "Calc. Saturation"
    calc_SA: BoolProperty(name=text, default=True) # type: ignore
    text = "默认角度" if language else "Default Angle"
    default_angle: BoolProperty(name=text, default=True) # type: ignore
    atomic_num: IntProperty(name='', default=1, min=1, max=118) # type: ignore
    bond_order: IntProperty(name='', default=1, min=1, soft_max=3) # type: ignore
    rotate_angle: FloatProperty(name='', default=0.0, min=-180, max=180) # type: ignore
    deflection_angle: FloatProperty(name='', default=0.0, min=-180, max=180) # type: ignore
    branches: IntProperty(name='', default=1, min=1, max=5) # type: ignore

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        text = "原子序数:" if language else "Atomic Number:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, 'atomic_num')
        row = layout.row()
        text = "键级:" if language else "Bond Order:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, 'bond_order')

        row = layout.row()
        text = "分支数:" if language else "Branches:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, 'branches')
        row = layout.row()
        row.prop(self, 'calc_SA')
        row.scale_x = 1.8
        row.prop(self, 'default_angle')

        if not self.default_angle:
            row = layout.row()
            text = "旋转角度:" if language else "Rotate Angle:"
            row.label(text=text)
            row.scale_x = 1.8
            row.prop(self, 'rotate_angle')
            row = layout.row()
            text = "偏转角度:" if language else "Deflection Angle:"
            row.label(text=text)
            row.scale_x = 1.8
            row.prop(self, 'deflection_angle')

    def execute(self, context):
        ao = context.object
        if not ao or ao.get('Type') != 'scaffold':
            self.report({'WARNING'}, warning_text)
            return {'CANCELLED'}
        
        try:
            new_verts = mesh.para_branches(ao, self.atomic_num, self.branches, self.calc_SA, self.default_angle, self.rotate_angle, self.deflection_angle)
            old_vert_count, old_edge_count = mesh.add_new_scaffold(ao, new_verts)
            mesh.set_new_scaffold_attr(ao, old_vert_count, old_edge_count, self.atomic_num, self.bond_order)
            bpy.ops.object.mode_set(mode='EDIT')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"发生错误: {str(e)}")
            return {'CANCELLED'}
        
        
class GeometryUpdateButton(Operator):
    bl_idname = 'chem.geometry_update'
    bl_label = 'Force Field'
    bl_description = "使用MMFF或UFF力场优化并重新生成分子构象" if language else "Optimize and regenerate molecular conformation using MMFF or UFF"
    bl_options = {'REGISTER', 'UNDO'}

    force_field: EnumProperty(
        name = '',
        default = 'MMFF',
        items = [('MMFF', 'MMFF', ''),
                 ('UFF', 'UFF', ''),
                 ]
    ) # type: ignore

    def execute(self, context):
        ao = context.object
        if not ao or ao.get('Type') != 'scaffold':
            self.report({'WARNING'}, warning_text)
            return {'CANCELLED'}

        try:
            # 调用mol_optimize函数进行构象更新
            mesh.mol_optimize(ao, self.force_field, addHs=True, update=True)
            self.report({'INFO'}, "构象更新成功！" if language else "Congormation Update Successfully!")
            return {'FINISHED'}
        except Exception as e:
            # 打印异常信息，便于调试
            self.report({'ERROR'}, f"发生错误: {str(e)}")
            return {'CANCELLED'}
        
class GeometryOptimizeButton(Operator):
    bl_idname = 'chem.geometry_optimize'
    bl_label = 'Force Field'
    bl_description = "使用MMFF或UFF力场优化分子构象" if language else "Optimizing molecular conformation using MMFF or UFF"
    bl_options = {'REGISTER', 'UNDO'}

    force_field: EnumProperty(
        name = '',
        default = 'MMFF',
        items = [('MMFF', 'MMFF', ''),
                 ('UFF', 'UFF', ''),
                 ]
    ) # type: ignore

    def execute(self, context):
        ao = context.object
        if not ao or ao.get('Type') != 'scaffold':
            self.report({'WARNING'}, warning_text)
            return {'CANCELLED'}

        try:
            mesh.mol_optimize(ao, self.force_field, addHs=True, update=False)
            self.report({'INFO'}, "构象更新成功！")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"发生错误: {str(e)}")
            return {'CANCELLED'}

    

class ScaffoldConvertButton(Operator):
    """Convert mesh to molecular scaffold"""
    bl_idname = "chem.mesh2scaffold"
    bl_label = "网格到分子骨架" if language else "Mesh to Mol Scaffold"
    bl_description = "从网格生成分子骨架" if language else "Generate molecular graph scaffold from mesh object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ao = context.object
        if not ao or ao.type != 'MESH':
            self.report({'WARNING'}, "请选择一个网格物体。" if language else "Please Select a Mesh Object.")
            return {'CANCELLED'}

        obj_type = ao.get('Type', None)  # 避免 KeyError
        if obj_type == 'scaffold':
            self.report({'WARNING'}, "该对象已是分子骨架。" if language else "This is Already a Mol Scaffold.")
            return {'CANCELLED'}
        
        try:
            mesh.mesh_to_mol_scaffold(ao)
            self.report({'INFO'}, "分子骨架生成成功！" if language else "Molecular Scaffold Generated Successfully!")
            GN_mol = node.add_geometry_nodetree(ao, "GN_"+ao.name, "NodeTree_"+ao.name)
            node.Ball_Stick_nodetree(GN_mol)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"发生错误: {str(e)}")
            return {'CANCELLED'}



