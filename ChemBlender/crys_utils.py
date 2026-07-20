import bpy, bmesh
import mathutils
from . import read, mesh, node, _math
from bpy.types import Operator
from bpy.props import IntProperty, FloatProperty, BoolProperty, StringProperty, EnumProperty, FloatVectorProperty
from .Chem_data import metals,SPACE_GROUP_DATA,ELEMENTS_DEFAULT,SYMOP_OPERATIONS

language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0
# -------------------------------------------------------------------------------------------
class SupercellButton(Operator):
    """Add supercell from unit scaffold"""
    bl_idname = "chem.supercell"
    bl_label = "生成超胞" if language else "Add Supercell"
    bl_description = "从单元晶胞骨架生成超胞骨架" if language else "Generate supercell scaffold from unit crystal scaffold"
    bl_options = {'REGISTER', 'UNDO'}

    negative_boundaries: FloatVectorProperty(name='', default=(0.0,0.0,0.0))
    positive_boundaries: FloatVectorProperty(name='', default=(1.0,1.0,1.0))
    full_cell_cutoff: BoolProperty(name='', default=False)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        text = "负向边界:" if language else "Negative Boundaries:"
        split = row.split(factor=0.3 if language else 0.5)
        split.label(text=text)
        col = split.column()
        col.prop(self, 'negative_boundaries', index=0)
        col.prop(self, 'negative_boundaries', index=1)
        col.prop(self, 'negative_boundaries', index=2)
        row = layout.row()
        text = "正向边界:" if language else "Positive Boundaries:"
        split = row.split(factor=0.3 if language else 0.5)
        split.label(text=text)
        col = split.column()
        col.prop(self, 'positive_boundaries', index=0)
        col.prop(self, 'positive_boundaries', index=1)
        col.prop(self, 'positive_boundaries', index=2)
        row = layout.row(align=True)
        text = "整胞截断" if language else "Full Cell Cutoff"
        row.label(text=text)
        row.scale_x = 22
        row.prop(self, 'full_cell_cutoff')


    def copy_filter_modifier(self, source_obj, target_obj):
        for mod in source_obj.modifiers:
            if mod.name.startswith("GN_Crys_Filter") and mod.type == 'NODES':
                new_mod = target_obj.modifiers.new(mod.name, 'NODES')
                new_mod.node_group = mod.node_group.copy()

    def execute(self, context):
        ao = context.object
        if not ao.get('cell angles', None) or not 'unit' in ao.name:
            self.report({'WARNING'}, "该功能需作用于单胞骨架！" if language else "This Function Must Act on Unit Cell Scaffold!")
            return {'CANCELLED'}
        
        try:
            molname = ao.name.split('_',1)[-1]
            coll = bpy.data.collections['Scaffold_'+molname]
            crystal_scaffold = mesh.copy_mesh_object(coll, ao.data, 'crystal_'+molname)
            for key in ao.keys():
                if not key.startswith("_") and key not in {'name','data','type'}:
                    crystal_scaffold[key]=ao[key]
            read.copy_cif_data(ao, crystal_scaffold)
            ao.hide_set(True)
            GN_supercell = node.add_geometry_nodetree(crystal_scaffold, "Supercell_"+molname, "Supercell_"+molname)
            node.Supercell(crystal_scaffold, GN_supercell, self.full_cell_cutoff)
            crystal_scaffold.modifiers["Supercell_"+molname]["Socket_2"]=self.negative_boundaries
            crystal_scaffold.modifiers["Supercell_"+molname]["Socket_3"]=self.positive_boundaries

            self.copy_filter_modifier(ao, crystal_scaffold)
            GN_mol = node.add_geometry_nodetree(crystal_scaffold, "GN_"+molname, "NodeTree_"+molname)
            node.Ball_Stick_nodetree(GN_mol)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"发生错误: {str(e)}")
            return {'CANCELLED'}

class AddCellButton(Operator):
    """Customized Unit Cell"""
    bl_idname = "chem.add_unit_cell"
    bl_label = "晶胞参数" if language else "Unit Cell Parameters"
    bl_description = "创建自定义晶胞" if language else "Add a customized unit cell"
    bl_options = {'REGISTER', 'UNDO'}
    
    def update_crystal_system(self, context):
        data = SPACE_GROUP_DATA[self.crystal_system]
        locked = data.get("locked")
        angle_locked = data.get("angle_locked")

        # 边长同步
        if locked == "a=b":
            self.b = self.a
        elif locked == "a=b=c":
            self.b = self.a
            self.c = self.a

        # 角度同步
        if angle_locked == "all=90":
            self.alpha = self.beta = self.gamma = 90.0
        elif angle_locked == "alpha=gamma=90":
            self.alpha = 90.0
            self.gamma = 90.0
        elif angle_locked == "alpha=beta=90, gamma=120":
            self.alpha = 90.0
            self.beta = 90.0
            self.gamma = 120.0

    crystal_system: EnumProperty(
        name = '',
        default = 'triclinic',
        items = [('triclinic', '三斜晶系', ''),
                 ('monoclinic', '单斜晶系', ''),
                 ('orthorhombic', '正交晶系', ''),
                 ('tetragonal', '四方晶系', ''),
                 ('trigonal', '三方晶系', ''),
                 ('hexagonal', '六方晶系', ''),
                 ('cubic', '立方晶系', ''),
        ] if language else [
                     ('triclinic', 'Triclinic', ''),
                    ('monoclinic', 'Monoclinic', ''),
                    ('orthorhombic', 'Orthorhombic', ''),
                    ('tetragonal', 'Tetragonal', ''),
                    ('trigonal', 'Trigonal', ''),
                    ('hexagonal', 'Hexagonal', ''),
                    ('cubic', 'Cubic', ''),
                 ],
        update=update_crystal_system
    ) # type: ignore

    def get_bravais_items(self, context):
        data = SPACE_GROUP_DATA[self.crystal_system]
        return [(b, b, "") for b in data["bravais"]]

    def get_space_group_items(self,context):
        data = SPACE_GROUP_DATA[self.crystal_system]
        return data["groups"][self.bravais_lattice]
    
    bravais_lattice: EnumProperty(
        name = '',
        items = get_bravais_items
    ) # type: ignore
    space_group: EnumProperty(
        name = '',
        items = get_space_group_items
    ) # type: ignore

    a: FloatProperty(name="", default=5.0) # type: ignore
    b: FloatProperty(name="", default=5.0) # type: ignore
    c: FloatProperty(name="", default=5.0) # type: ignore

    alpha: FloatProperty(name="", default=90.0) # type: ignore
    beta: FloatProperty(name="", default=90.0) # type: ignore
    gamma: FloatProperty(name="", default=90.0) # type: ignore

    crys_name: StringProperty(name="", default ="") # type: ignore

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.label(text="晶系:" if language else "Crystal System:")
        row.scale_x = 2.2
        row.prop(self, "crystal_system")
        
        row = layout.row()
        row.label(text="布拉维格子:" if language else "Bravais Lattice:")
        row.scale_x = 2.2
        row.prop(self, "bravais_lattice")
        
        row = layout.row()
        row.label(text="空间群:" if language else "Space Group:")
        row.scale_x = 2.2
        row.prop(self, "space_group")

        layout.separator()

        # 边长
        row = layout.row()
        row.label(text="晶胞边长:" if language else "Cell Lengths:")
        row.scale_x = 0.73
        row.prop(self, "a")
        row.prop(self, "b")
        row.prop(self, "c")
        # 角度
        row = layout.row()
        row.label(text="晶胞角度:" if language else "Cell Angles:")
        row.scale_x = 0.73
        row.prop(self, "alpha")
        row.prop(self, "beta")
        row.prop(self, "gamma")
        layout.separator()

        row = layout.row()
        row.label(text = "晶体名称:" if language else "Crystal Name:")
        row.scale_x = 1.8
        row.prop(self, 'crys_name')

    # 弹窗
    # def invoke(self, context, event):
    #    self.update_crystal_system(context)
    #    return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        data = SPACE_GROUP_DATA[self.crystal_system]
        locked = data.get("locked")
        angle_locked = data.get("angle_locked")

        # 最终强制同步（保证生成出来是严格符合晶系）
        if locked == "a=b":
            self.b = self.a
        elif locked == "a=b=c":
            self.b = self.a
            self.c = self.a

        if angle_locked == "all=90":
            self.alpha = self.beta = self.gamma = 90.0
        elif angle_locked == "alpha=gamma=90":
            self.alpha = 90.0
            self.gamma = 90.0
        elif angle_locked == "alpha=beta=90, gamma=120":
            self.alpha = 90.0
            self.beta = 90.0
            self.gamma = 120.0

        coll_mol = bpy.data.collections.new('Scaffold_'+self.crys_name)
        context.scene.collection.children.link(coll_mol)
        space_group_num = SYMOP_OPERATIONS[self.space_group][0]
        symops = SYMOP_OPERATIONS[self.space_group][4]
        mesh.unit_cell_edges(self.crys_name, coll_mol, self.a, self.b, self.c, self.alpha, self.beta, self.gamma, self.space_group, space_group_num, symops)
        return {'FINISHED'}


# 增删原子按钮
class CHEM_OT_AddAtom(Operator):
    bl_idname = "chem.add_atom"
    bl_label = "+"
    def execute(self, context):
        op = context.active_operator
        op.atom_count += 1
        return {'FINISHED'}

class CHEM_OT_RemoveAtom(Operator):
    bl_idname = "chem.remove_atom"
    bl_label = "-"
    def execute(self, context):
        op = context.active_operator
        if op.atom_count > 1:
            op.atom_count -= 1
        return {'FINISHED'}

class AddCrysScaffoldButton(Operator):
    bl_idname = "chem.add_crys_scaffold"
    bl_label = "添加骨架结构" if language else "Add Crystal Scaffold"
    bl_description = "创建自定义晶体骨架" if language else "Add a customized crystal scaffold"
    bl_options = {'REGISTER', 'UNDO'}

    MAX_ATOMS = 100  #自定义添加对称原子个数
    length_factor: FloatProperty(name="键长系数:" if language else "Length Factor:", default=1.0, min=0.0, max=3.0) # type: ignore
    boundary: FloatProperty(name="边界扩展:" if language else "Boundary Expand:", default=0.0, min=0.0, max=1.0) # type: ignore
    grow_iter: IntProperty(name="直接扩展:" if language else "Direct Expand:", default=0, min=0, max=10) # type: ignore
    atom_count: IntProperty(name='', default=4, min=1, max=MAX_ATOMS) # type: ignore

    # ======================================================
    for _i in range(1, MAX_ATOMS+1):
        exec(f'''
elem{_i}: StringProperty(name="", default="C")
x{_i}: FloatProperty(name="", default=0.0, min=0, max=1)
y{_i}: FloatProperty(name="", default=0.0, min=0, max=1)
z{_i}: FloatProperty(name="", default=0.0, min=0, max=1)
''')
    # ======================================================

    def invoke(self, context, event):
        ao = context.object
        if not ao or ao.get("cell angles") is None:
            self.report({'ERROR'}, "请选择一个晶胞！" if language else "Please Select a Unit Cell!")
            return {'CANCELLED'}
        else:
            return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "length_factor")
        layout.prop(self, "boundary")
        layout.prop(self, "grow_iter")
        layout.separator()

        for i in range(self.atom_count):
            row = layout.row(align=True)
            row.label(text=f"原子 {i+1}" if language else f"Atom {i+1}")
            row.prop(self, f"elem{i+1}")
            row.prop(self, f"x{i+1}")
            row.prop(self, f"y{i+1}")
            row.prop(self, f"z{i+1}")
        row = layout.row(align=True)
        row.operator("chem.add_atom", text="添加原子" if language else "Add Atom")
        row.operator("chem.remove_atom", text="删除原子" if language else "Delete Atom")

    def execute(self, context):
        import re
        from rdkit import Chem
        periodic_table = Chem.GetPeriodicTable()
        ao = context.object
        try:
            atoms = []
            for i in range(self.atom_count):
                elem = getattr(self, f"elem{i+1}")
                x = getattr(self, f"x{i+1}")
                y = getattr(self, f"y{i+1}")
                z = getattr(self, f"z{i+1}")
                
                if elem and elem.strip():
                    atoms.append((elem.strip().capitalize(), x, y, z))

            length_a, length_b, length_c, angle_alpha, angle_beta, angle_gamma, space_group, space_group_num, symop_operations = mesh.get_cell_parameters(ao)
            cell_lengths = (length_a, length_b, length_c)
            cell_angles = (angle_alpha, angle_beta, angle_gamma)
            sg_info = (space_group, space_group_num, symop_operations)
            atom_list = []
            for i, (elem, x, y, z) in enumerate(atoms):
                label = f"{elem}{i+1}"  # C1, C2, N1...
                atom_dict = {
                    "label": label,
                    "element": elem,
                    "x": x,
                    "y": y,
                    "z": z,
                    "occupancy": 1.0,
                    "u_iso_equiv": 0.0,
                    "adp_type": 'Uiso',
                    "u11": 0.0,
                    "u22": 0.0,
                    "u33": 0.0,
                    "u12": 0.0,
                    "u13": 0.0,
                    "u23": 0.0,
                }
                atom_list.append(atom_dict)

            
            ATOMS,COORDS,AtomicNum,COLORS = [],[],[],[]
            VDW_R, Radii, RingNum = [],[],[]
            
            for element, fx, fy, fz in atoms:
                sym_fracts = _math.fract_symop_expand((fx, fy, fz), symop_operations, self.boundary)
                atoms = [element]*len(sym_fracts)
                coords = [_math.fract_to_cartn(fract, length_a, length_b, length_c, angle_alpha, angle_beta, angle_gamma) for fract in sym_fracts]
                for atom, coord in zip(atoms,coords):
                    atomic_num = periodic_table.GetAtomicNumber(atom)
                    if atom:
                        ATOMS.append(atom)
                        AtomicNum.append(atomic_num)
                        COORDS.append(coord)
                        VDW_R.append(periodic_table.GetRvdw(atomic_num))
                        Radii.append(periodic_table.GetRcovalent(atomic_num))
                        COLORS.extend(ELEMENTS_DEFAULT[atom][3])
            BONDS, BOND_ORDERS = read.add_BONDS(ATOMS, COORDS, self.length_factor)
            Atom_Scale_f = [1]*len(ATOMS)
            U_Scale = [1.0, 1.0, 1.0]*len(ATOMS)
            U_v1 = [1.0, 0.0, 0.0]*len(ATOMS)
            U_v2 = [0.0, 1.0, 0.0]*len(ATOMS)
            U_v3 = [1.0, 0.0, 1.0]*len(ATOMS)
            SiteID = [0]*len(ATOMS)
            RingNum = [0]*len(BONDS)
            Bond_Scale_f = [1]*len(BONDS)
            
            crys_name = ao.name[11:] if len(ao.name) > 11 else ao.name
            coll_name = 'Scaffold_' + crys_name
            if coll_name in bpy.data.collections:
                coll = bpy.data.collections[coll_name]
            else:
                coll = bpy.data.collections.new(coll_name)
                bpy.context.scene.collection.children.link(coll)

            crys_scaffold = mesh.create_object(coll, "unit_"+crys_name, COORDS, BONDS, [])
            read.init_cif_data(crys_scaffold, cell_lengths, cell_angles, sg_info, atom_list)
            crys_scaffold['Type'] = 'scaffold'
            crys_scaffold['cell lengths'] = f'{length_a},{length_b},{length_c}'
            crys_scaffold['cell angles'] = f'{angle_alpha},{angle_beta},{angle_gamma}'
            crys_scaffold['space group'] = space_group
            crys_scaffold['SG No.'] = space_group_num
            crys_scaffold['Elements'] = str(list(set(ATOMS)))

            mesh.add_scaffold_attr(crys_scaffold, ATOMS, AtomicNum, BOND_ORDERS, VDW_R, Radii, RingNum, SiteID, COLORS, Atom_Scale_f, Bond_Scale_f, U_Scale, U_v1, U_v2, U_v3)
            bpy.context.view_layer.objects.active = crys_scaffold
            mesh.remove_doubles(crys_scaffold)

            node.crys_expand(crys_scaffold, (length_a, length_b, length_c), (angle_alpha, angle_beta, angle_gamma), self.grow_iter)
            GN_mol = node.add_geometry_nodetree(crys_scaffold, "GN_"+crys_name, "NodeTree_"+crys_name)
            node.Ball_Stick_nodetree(GN_mol)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"发生错误: {str(e)}")
            print("完整报错:",e)
            return {'CANCELLED'}
        

class AddCoordPolyhedraButton(Operator):
    bl_idname = "chem.add_coordpolyhedra"
    bl_label = "添加配位多面体" if language else "Add Coordination Polyhedra"
    bl_description = "添加配位多面体" if language else "Add coordination polyhedra"
    bl_options = {'REGISTER', 'UNDO'}

    set_mode: EnumProperty(
        name = 'Type',
        default = '0',
        items = [('0','默认',''),
                 ('1','自定义',''),]
                if language else 
                [('0','Default',''),
                 ('1','Customize',''),]
    )

    centers: StringProperty(name = "",)
    ligands: StringProperty(name = "",)
    RMin: FloatProperty(name="RMin", default=1.0, min=0.0, soft_max=5.0)
    RMax: FloatProperty(name="RMax", default=2.6, min=0.0, soft_max=5.0)
    append_mode: BoolProperty(name="", default=False)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        sub_left = row.row()
        sub_left.ui_units_x = 10
        sub_left.prop(self, 'set_mode', )
        row.separator(factor=2.0)

        sub_right = row.row(align=True)
        sub_right.label(text="逐个添加:" if language else "Add individual:")
        sub_right.prop(self, "append_mode", text="")

        if self.set_mode == '1':
            row = layout.row(align=True)
            col = row.column(align=True)
            text = "中心原子" if language else "Center"
            col.label(text=text)
            col.prop(self, 'centers')
            col = row.column(align=True)
            text = "配位原子" if language else "Ligand"
            col.label(text=text)
            col.prop(self, 'ligands')
            row = layout.row(align=True)
            sub = row.row(align=True)
            sub.prop(self, 'RMin')
            sub.prop(self, 'RMax')

    def execute(self, context):
        from rdkit import Chem
        periodic_table = Chem.GetPeriodicTable()
        ao = context.object
        if not ao:
            self.report({'WARNING'}, "请选择一个晶体骨架！" if language else "Please Select a Crystal Scaffold!")
            return {'CANCELLED'}
        geo_modifiers = [m for m in ao.modifiers if m.type =='NODES']
        try:
            centers = []
            ligands = []
            if self.set_mode == '0':
                all_elems = eval(ao['Elements'])
                centers = [e for e in all_elems if e in metals]
                ligands = [e for e in all_elems if e in ['O', 'N', 'P', 'S', 'F']]
                self.RMin = 1.0
                self.RMax = 2.6
            else:
                if not self.centers.strip() or not self.ligands.strip():
                    return {'CANCELLED'}
                centers = simplify_text(self.centers)[0]
                ligands = simplify_text(self.ligands)[0]
            
            center_nums,ligand_nums = [],[]
            if centers:
                for center in centers:
                    try:
                        center_num = periodic_table.GetAtomicNumber(center)
                    except:
                        center_num = -1
                    if center == 'dummy': center_num = 0
                    center_nums.append(center_num)
            if ligands:
                for ligand in ligands:
                    try:
                        ligand_num = periodic_table.GetAtomicNumber(ligand)
                    except:
                        ligand_num = -1
                    if ligand == 'dummy': ligand_num = 0
                    ligand_nums.append(ligand_num)

            for m in geo_modifiers: m.show_viewport = False
            bpy.ops.object.mode_set(mode='OBJECT')
            if centers:
                mesh.select_verts(ao, centers)
                mesh.set_sel_center_ligand(ao, True, False)
            mesh.deselect_all(ao)
            if ligands:
                mesh.select_verts(ao, ligands)
                mesh.set_sel_center_ligand(ao, False, True)
            for m in geo_modifiers: m.show_viewport = True

            nodetree = ao.modifiers[-1]
            node.CoordPolyhedra(nodetree, self.set_mode, self.append_mode, self.RMin, self.RMax, center_nums, ligand_nums)
            self.report({'INFO'}, "配位多面体添加成功！" if language else "Coordination Polyhedra Added!")
            return {'FINISHED'}
        except Exception as e:
            for m in geo_modifiers: m.show_viewport = True
            self.report({'ERROR'}, f"添加失败：{str(e)}" if language else f"Failed: {str(e)}")
            return {'CANCELLED'}
        

class AvgFractButton(Operator):
    bl_idname = "chem.avgfract"
    bl_label = "平均分数坐标" if language else "Average Fract"
    bl_description = "计算选中点的平均分数坐标" if language else "Calculate the average fractional coordinates of selected vertices"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mytool = context.scene.my_tool
        ao = context.active_object

        # 没有选中物体直接退出
        if not ao:
            self.report({'WARNING'}, "未选中物体")
            return {'CANCELLED'}

        # 判断是否为晶体类型
        obj_type = ao.get("Type", None)
        if not ao or ao.get("cell angles") is None:
            self.report({'WARNING'}, "当前物体不是晶体类型")
            return {'CANCELLED'}

        # 从物体名解析晶体名称（例如 Atom_CaF → CaF）
        try:
            underscore_pos = ao.name.find('_')
            if underscore_pos == -1:
                crys_name = ao.name.split('.')[0]
            else:
                crys_name = ao.name[underscore_pos + 1:].split('.')[0]
        except:
            self.report({'ERROR'}, "无法从物体名称识别晶体名")
            return {'CANCELLED'}

        # 获取晶胞对象
        cell_obj_name = f'cell_edges_{crys_name}'
        cell_edges = None
        for obj in bpy.data.objects:
            if obj.name.startswith(cell_obj_name):
                cell_edges = obj
                break
        if not cell_edges:
            self.report({'ERROR'}, f"未找到晶胞对象：{cell_obj_name}")
            return {'CANCELLED'}

        # 安全读取晶胞参数（避免 eval 风险）
        try:
            # 假设格式为 "a,b,c" 和 "alpha,beta,gamma"
            lengths_str = cell_edges.get("cell lengths", "")
            angles_str = cell_edges.get("cell angles", "")

            length_a, length_b, length_c = [float(v.strip()) for v in lengths_str.split(',')]
            angle_alpha, angle_beta, angle_gamma = [float(v.strip()) for v in angles_str.split(',')]
        except Exception as e:
            self.report({'ERROR'}, f"晶胞参数读取失败：{str(e)}")
            return {'CANCELLED'}

        # 必须在编辑模式且选中顶点
        if ao.mode != 'EDIT':
            self.report({'WARNING'}, "请进入编辑模式并选中原子")
            return {'CANCELLED'}

        # 计算选中原子平均坐标
        try:
            avg_xyz = mesh.get_sel_xyz(ao)[0]
        except Exception as e:
            self.report({'ERROR'}, f"计算平均坐标失败：{str(e)}")
            return {'CANCELLED'}

        # 转分数坐标
        try:
            avg_fract = _math.cartn_to_fract(
                avg_xyz,
                length_a, length_b, length_c,
                angle_alpha, angle_beta, angle_gamma
            )
        except Exception as e:
            self.report({'ERROR'}, f"分数坐标转换失败：{str(e)}")
            return {'CANCELLED'}

        # 格式化输出（保留3位小数）
        fract_str = f"{avg_fract[0]:.3f}, {avg_fract[1]:.3f}, {avg_fract[2]:.3f}"
        mytool.avgfract = fract_str

        self.report({'INFO'}, f"平均分数坐标：{fract_str}")
        return {'FINISHED'}


class AddDummyButton(Operator):
    bl_idname = "chem.add_dummy"
    bl_label = "添加Dummy原子" if language else "Add Dummy"
    bl_description = "在当前晶胞骨架上添加Dummy原子" if language else "Add dummy to crystal scaffold"
    bl_options = {'REGISTER', 'UNDO'}

    x: FloatProperty(name='', default=0.0, min=0, max=1)
    y: FloatProperty(name='', default=0.0, min=0, max=1)
    z: FloatProperty(name='', default=0.0, min=0, max=1)
    origin_off_x: FloatProperty(name='', default=0.0, soft_min=-1.0, soft_max=1.0)
    origin_off_y: FloatProperty(name='', default=0.0, soft_min=-1.0, soft_max=1.0)
    origin_off_z: FloatProperty(name='', default=0.0, soft_min=-1.0, soft_max=1.0)
    boundary: FloatProperty(name='', default=0.0, min=0.0, max=1.0)
    
    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        text = "位置分数:" if language else "Fraction Coords:"
        split = row.split(factor=0.3 if language else 0.5)
        split.label(text=text)
        col = split.column()
        col.prop(self, 'x', index=0)
        col.prop(self, 'y', index=1)
        col.prop(self, 'z', index=2)

        row = layout.row()
        text = "原点偏移:" if language else "Origin Offset:"
        split = row.split(factor=0.3 if language else 0.5)
        split.label(text=text)
        col = split.column()
        col.prop(self, 'origin_off_x', index=0)
        col.prop(self, 'origin_off_y', index=1)
        col.prop(self, 'origin_off_z', index=2)

        row = layout.row()
        text = "边界扩展:" if language else "Boundary Expand:"
        row.label(text=text)
        row.scale_x = 2.4
        row.prop(self, 'boundary')
        

    def execute(self, context):
        from rdkit import Chem
        pt = Chem.GetPeriodicTable()

        ao = context.object
        if not ao or ao.get("SG No.") is None:
            self.report({'ERROR'}, "请选择一个晶胞骨架！" if language else "Please Select a Crystal Scaffold") 
            return {'CANCELLED'}
        
        try:
            new_coords = get_equiv_cartns(ao, (self.x, self.y, self.z), (self.origin_off_x, self.origin_off_y, self.origin_off_z), self.boundary)

            bpy.ops.object.mode_set(mode='OBJECT')
            new_mesh = bpy.data.meshes.new("tempo")
            tempo = bpy.data.objects.new("tempo", new_mesh)
            bpy.context.collection.objects.link(tempo)
            new_mesh.from_pydata(new_coords, [], [])
            bpy.ops.object.select_all(action='DESELECT')
            ao.select_set(True)
            tempo.select_set(True)
            bpy.ops.object.join()

            ao = bpy.context.object
            bm = bmesh.new()
            bm.from_mesh(ao.data)
            atomic_num_layer = bm.verts.layers.int.get('atomic_num')
            for vert in bm.verts:
                if vert[atomic_num_layer] == 0:
                    vert[atomic_num_layer] = -1
            bm.to_mesh(ao.data)
            bpy.ops.object.mode_set(mode='EDIT')

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"错误：{str(e)}")
            print("AddAtomError:", e)
            return {'CANCELLED'}



def get_equiv_cartns(crys_scaffold, fract, origin_offset, boundary):
    import numpy as np
    length_a, length_b, length_c, angle_alpha, angle_beta, angle_gamma, space_group, space_group_num, symop_operations = mesh.get_cell_parameters(crys_scaffold)
    fract = np.array(fract)+np.array(origin_offset)
    sym_fracts = _math.fract_symop_expand(fract, symop_operations, boundary)
    sym_fracts = np.array(sym_fracts)-np.array(origin_offset)
    sym_fracts = _math.fracts_normalize(sym_fracts, boundary)
    sym_cartns = [
        _math.fract_to_cartn(f, length_a, length_b, length_c,
                            angle_alpha, angle_beta, angle_gamma)
        for f in sym_fracts
    ]
    return sym_cartns


class SymmetrySelect(Operator):
    """Select equivalent atoms in a crystal scaffold based on its symmetry."""
    bl_idname = "chem.sel_symmetry"
    bl_label = "对称选择" if language else "Symmetry Select"
    bl_description = "选择当前所选原子的所有对称等价原子" if language else "Select all symmetrically equivalent atoms in a crystal scaffold for currently selected atoms"
    bl_options = {'REGISTER', 'UNDO'}

    origin_off_x: FloatProperty(name='', default=0.0, soft_min=-1.0, soft_max=1.0)
    origin_off_y: FloatProperty(name='', default=0.0, soft_min=-1.0, soft_max=1.0)
    origin_off_z: FloatProperty(name='', default=0.0, soft_min=-1.0, soft_max=1.0)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        text = "原点偏移:" if language else "Origin Offset:"
        split = row.split(factor=0.3 if language else 0.5)
        split.label(text=text)
        col = split.column()
        col.prop(self, 'origin_off_x', index=0)
        col.prop(self, 'origin_off_y', index=1)
        col.prop(self, 'origin_off_z', index=2)

    def select_equivalent_atoms(self, obj):
        import numpy as np

        if not obj or obj.get("SG No.") is None:
            return

        a, b, c, alpha, beta, gamma, sg, sg_num, sym_op = mesh.get_cell_parameters(obj)
        bpy.ops.object.mode_set(mode='EDIT')

        sel_xyz = mesh.get_sel_xyz(obj)[1]
        if not sel_xyz:
            return

        equiv_fracts = set()
        shift = np.array((self.origin_off_x, self.origin_off_y, self.origin_off_z), dtype=np.float32)

        for xyz in sel_xyz:
            f = _math.cartn_to_fract(xyz, a, b, c, alpha, beta, gamma)
            f = np.array(f) + shift
            f_norm = tuple(x % 1.0 for x in f)
            fs = _math.fract_symop_expand(f_norm, sym_op, boundary=0)
            fs = np.array(fs) - shift

            for ff in fs:
                equiv_fracts.add(tuple(round(v, 4) for v in ff))

        equiv_fracts = np.array(list(equiv_fracts), dtype=np.float32)
        n_equiv = len(equiv_fracts)
        if n_equiv == 0:
            return

        bm = bmesh.from_edit_mesh(obj.data)
        verts = list(bm.verts)
        n_verts = len(verts)
        coords = np.array([v.co for v in verts], dtype=np.float32)

        # 批量转分数坐标
        f_verts = np.array([
            _math.cartn_to_fract(p, a, b, c, alpha, beta, gamma)
            for p in coords
        ], dtype=np.float32)

        epsilon = 1e-3
        eps2 = epsilon * epsilon

        for i, v in enumerate(verts):
            fv = f_verts[i]
            d = equiv_fracts - fv
            d -= np.round(d)
            dist_sq = np.sum(d * d, axis=1)
            v.select = bool(np.any(dist_sq < eps2))

        bmesh.update_edit_mesh(obj.data)

    def execute(self, context):
        self.select_equivalent_atoms(context.object)
        return {'FINISHED'}

class SymmetryDuplicate(Operator):
    """根据晶体对称性，在所有等价位置复制选中的原子"""
    bl_idname = "chem.duplicate_symmetry"
    bl_label = "对称复制" if language else "Symmetry Duplicate"
    bl_description = "将选中的原子按对称性复制到所有等价位置" if language else "Duplicate selected atoms to all symmetrically equivalent positions in a crystal scaffold"
    bl_options = {'REGISTER', 'UNDO'}

    boundary: FloatProperty(name='', default=0.0, min=0.0, max=1.0)
    bond_formation: BoolProperty(name='', default=False)
    length_factor: FloatProperty(name='', default=1.0, min=0.0)
    origin_off_x: FloatProperty(name='', default=0.0, soft_min=-1.0, soft_max=1.0)
    origin_off_y: FloatProperty(name='', default=0.0, soft_min=-1.0, soft_max=1.0)
    origin_off_z: FloatProperty(name='', default=0.0, soft_min=-1.0, soft_max=1.0)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        text = "是否成键:" if language else "Bond Formation:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, 'bond_formation')
        if self.bond_formation:
            row = layout.row()
            text = "键长系数:" if language else "Length Factor:"
            row.label(text=text)
            row.scale_x = 1.8
            row.prop(self, 'length_factor')

        row = layout.row()
        text = "原点偏移:" if language else "Origin Offset:"
        split = row.split(factor=0.3 if language else 0.5)
        split.label(text=text)
        col = split.column()
        col.prop(self, 'origin_off_x', index=0)
        col.prop(self, 'origin_off_y', index=1)
        col.prop(self, 'origin_off_z', index=2)

        row = layout.row()
        text = "边界扩展:" if language else "Boundary Expand:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, 'boundary')

    def execute(self, context):
        from rdkit import Chem
        from rdkit.Chem import PeriodicTable
        pt = Chem.GetPeriodicTable()
        import numpy as np

        obj = context.active_object
        if not obj or obj.get("SG No.") is None:
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        selected_verts = [v for v in bm.verts if v.select]
        
        if not selected_verts:
            self.report({'ERROR'}, "未选中任何原子")
            return {'CANCELLED'}

        a, b, c, alpha, beta, gamma, sg, sg_num, sym_op = mesh.get_cell_parameters(obj)
        origin_offset = (self.origin_off_x, self.origin_off_y, self.origin_off_z)
        atom_data_list = []
        for v in selected_verts:
            idx = v.index
            co = v.co
            atomic_num   = mesh.get_attr(obj, "atomic_num",    "INT",         "VERT")[idx]
            radius       = mesh.get_attr(obj, "radius",        "FLOAT",       "VERT")[idx]
            vdw_radius   = mesh.get_attr(obj, "vdw_radius",    "FLOAT",       "VERT")[idx]
            atom_scale_f = mesh.get_attr(obj, "atom_scale_f",  "FLOAT",       "VERT")[idx]
            colour       = mesh.get_attr(obj, "colour",        "FLOAT_COLOR", "VERT")[idx*4 : idx*4+4]
            f_xyz = _math.cartn_to_fract(co, a, b, c, alpha, beta, gamma)
            f_xyz = np.array(f_xyz)+np.array(origin_offset)
            sym_fracts = _math.fract_symop_expand(f_xyz, sym_op, self.boundary)
            sym_fracts = np.array(sym_fracts)-np.array(origin_offset)
            sym_cartns = [
                _math.fract_to_cartn(sf, a, b, c, alpha, beta, gamma)
                for sf in sym_fracts
            ]

            atom_data_list.append({
                "index": idx,
                "co": co,
                "atomic_num": atomic_num,
                "radius": radius,
                "vdw_radius": vdw_radius,
                "atom_scale_f": atom_scale_f,
                "colour": colour,
                "sym_positions": sym_cartns
            })
        
        original_vert_count = len(obj.data.vertices)

        new_mesh = bpy.data.meshes.new("SymmetricAtoms")
        new_obj = bpy.data.objects.new("SymmetricAtoms", new_mesh)
        context.collection.objects.link(new_obj)

        attrs_def = [
            ("atomic_num",    "INT"),
            ("radius",        "FLOAT"),
            ("vdw_radius",    "FLOAT"),
            ("atom_scale_f",  "FLOAT"),
            ("colour",        "FLOAT_COLOR"),
        ]
        for name, typ in attrs_def:
            if name not in new_mesh.attributes:
                new_mesh.attributes.new(name=name, type=typ, domain='POINT')

        COORDS, AtomicNum, Radii, VDW_R, Atom_Scale_f, atom_colors = [],[],[],[],[],[]

        for data in atom_data_list:
            for pos in data["sym_positions"]:
                COORDS.append(pos)
                AtomicNum.append(data["atomic_num"])
                Radii.append(data["radius"])
                VDW_R.append(data["vdw_radius"])
                Atom_Scale_f.append(data["atom_scale_f"])
                atom_colors.extend(data["colour"])

        ATOMS = [pt.GetElementSymbol(i) for i in AtomicNum]
        if self.bond_formation:
            BONDS, BOND_ORDERS = read.add_BONDS(ATOMS, COORDS, self.length_factor)
        else:
            BONDS = []

        # 写入属性
        new_mesh.from_pydata(COORDS, BONDS, [])
        new_mesh.attributes["atomic_num"].data.foreach_set("value", AtomicNum)
        new_mesh.attributes["radius"].data.foreach_set("value", Radii)
        new_mesh.attributes["vdw_radius"].data.foreach_set("value", VDW_R)
        new_mesh.attributes["atom_scale_f"].data.foreach_set("value", Atom_Scale_f)
        new_mesh.attributes["colour"].data.foreach_set("color", atom_colors)

        new_obj.select_set(True)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.join()

        mesh.remove_doubles(obj)
        for i, v in enumerate(obj.data.vertices):
            v.select = i >= original_vert_count-1  # 只选新点

        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}
# -------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------

# 记住上一次点的视角
last_axis_type = "X"

class Chem_OT_ViewSet(Operator):
    bl_idname = "chem.view_set"
    bl_label = "设置观察方向" if language else "Set View Direction"
    bl_description = "从轴向、uvw或hkl设置视图观察方向" if language else "Set view direction from axis, uvw or hkl"

    mode: StringProperty(default="X") # type: ignore
    
    def execute(self, context):
        global last_axis_type
        if self.mode != "LAST":
            last_axis_type = self.mode
        else:
            self.mode = last_axis_type

        mytool = context.scene.my_tool
        rv3d = None
        space = None
        for area in context.window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        rv3d = region.data
                        space = area.spaces.active
                        break
                if rv3d:
                    break
        if not rv3d or not space:
            return {'CANCELLED'}

        rv3d.view_perspective = 'ORTHO'
        space.overlay.show_axis_x = True
        space.overlay.show_axis_y = True
        space.overlay.show_axis_z = True

        opposite = mytool.view_axis_opposite
        obj = context.object

        vec = mathutils.Vector((1, 0, 0))
        if self.mode in ('A','B','C','X','Y','Z'):
            A = mathutils.Vector((1, 0, 0))
            B = mathutils.Vector((0, 1, 0))
            C = mathutils.Vector((0, 0, 1))
            try:
                vec_a, vec_b, vec_c = mesh.get_cell_vectors(obj)
                A = mathutils.Vector(vec_a)
                B = mathutils.Vector(vec_b)
                C = mathutils.Vector(vec_c)
            except: pass

            dir_map = {
                    "X": mathutils.Vector((1,0,0)),
                    "Y": mathutils.Vector((0,1,0)),
                    "Z": mathutils.Vector((0,0,1)),
                    "A": A,
                    "B": B,
                    "C": C,
                }
            vec = dir_map[self.mode]

        elif self.mode == "uvw":
            vec = mathutils.Vector(mytool.view_uvw)
            if vec.length < 1e-6:
                self.report({'WARNING'}, "uvw vector too small")
                return {'CANCELLED'}

        elif self.mode == "hkl":
            h, k, l = mytool.view_hkl
            if h == 0 and k == 0 and l == 0:
                self.report({'WARNING'}, "hkl cannot be (0,0,0)")
                return {'CANCELLED'}

            vec_a = (1,0,0)
            vec_b = (0,1,0)
            vec_c = (0,0,1)
            try:
                vec_a, vec_b, vec_c = mesh.get_cell_vectors(obj)
            except: pass

            A = mathutils.Vector(vec_a)
            B = mathutils.Vector(vec_b)
            C = mathutils.Vector(vec_c)
            vec = h * A + k * B + l * C
            if vec.length > 1e-6:
                vec.normalize()

        # 统一反向
        if opposite:
            vec = -vec

        # 设置视角
        quat = vec.to_track_quat('-Z', 'Y')
        rv3d.view_rotation = quat

        # 居中
        if obj:
            center = obj.location + obj.dimensions * 0.5
            rv3d.view_location = center
            rv3d.view_distance = max(obj.dimensions) * 2.0

        return {'FINISHED'}

