import bpy
import os
import numpy as np
from . import read, mesh, _math
from .Chem_data import ELEMENTS_DEFAULT
from bpy.types import Operator
from bpy.props import IntProperty, FloatProperty, BoolProperty, StringProperty,EnumProperty, FloatVectorProperty
language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0
warning_text = "请选择一个有效的分子骨架！" if language else "Please Select a Effective Mol Scaffold"

def xyz_block(name, atoms):
    lines = []
    lines.append(str(len(atoms)))
    lines.append(name)
    for x, y, z, atomic_num, symbol in atoms:
        lines.append(f"{symbol:<3s}  {x:12.6f}  {y:12.6f}  {z:12.6f}")
    return lines

def mol_block_v2000(name, atoms, bonds):
    lines = []
    lines.append(name)
    lines.append("  ChemBlender")
    lines.append("")
    # Counts line
    na, nb = len(atoms), len(bonds)
    lines.append(f"{na:3d}{nb:3d}  0  0  0  0  0  0  0  0  0 V2000")
    # Atom block
    for x, y, z, atomic_num, symbol in atoms:
        lines.append(f"{x:10.4f}{y:10.4f}{z:10.4f} {symbol:<3s} 0  0  0  0  0  0  0  0  0  0  0  0")
    # Bond block
    for v1, v2, bond_type in bonds:
        lines.append(f"{v1:3d}{v2:3d}{bond_type:3d}  0  0  0  0")
    lines.append("M  END")
    return lines

def mol_block_v3000(name, atoms, bonds):
    lines = []
    # Header block
    lines.append(name)
    lines.append("  ChemBlender")
    lines.append("")
    lines.append("  0  0  0  0  0  0  0  0  0  0  0 V3000")
    lines.append("M  V30 BEGIN CTAB")
    lines.append(f"M  V30 COUNTS {len(atoms)} {len(bonds)} 0 0 0")
    # Atom block
    lines.append("M  V30 BEGIN ATOM")
    for atom_id, (x, y, z, atomic_num, symbol) in enumerate(atoms, start=1):
        lines.append(f"M  V30 {atom_id} {symbol} {x:.4f} {y:.4f} {z:.4f} 0")
    lines.append("M  V30 END ATOM")
    # Bond block
    lines.append("M  V30 BEGIN BOND")
    for bond_id, (v1, v2, bond_type) in enumerate(bonds):
        lines.append(f"M  V30 {bond_id} {bond_type} {v1} {v2}")
    lines.append("M  V30 END BOND")
    lines.append("M  V30 END CTAB")
    lines.append("M  END")
    return lines

def sdf_block(name, atoms, bonds):
    lines = mol_block_v2000(name, atoms, bonds)
    lines.append("$$$$")
    return lines

def cif_block(cif_data, name):
    for prefix in ('unit_', 'crystal_'):
        if name.startswith(prefix):
            name = 'ChemBlender_' + name[len(prefix):]
            break
    else:
        name = 'ChemBlender_' + name

    cif_lines = []
    cif_lines.append("data_" + name)

    if cif_data.chemical_name_common:
        cif_lines.append(f"_chemical_name_common  '{cif_data.chemical_name_common}'")
    if cif_data.chemical_formula_sum:
        cif_lines.append(f"_chemical_formula_sum  '{cif_data.chemical_formula_sum}'")
    if cif_data.chemical_formula_weight > 0:
        cif_lines.append(f"_chemical_formula_weight  {cif_data.chemical_formula_weight:.3f}")

    cif_lines.append(f"_cell_length_a         {cif_data.a:.6f}")
    cif_lines.append(f"_cell_length_b         {cif_data.b:.6f}")
    cif_lines.append(f"_cell_length_c         {cif_data.c:.6f}")
    cif_lines.append(f"_cell_angle_alpha      {cif_data.alpha:.6f}")
    cif_lines.append(f"_cell_angle_beta       {cif_data.beta:.6f}")
    cif_lines.append(f"_cell_angle_gamma      {cif_data.gamma:.6f}")
    if cif_data.cell_volume > 0:
        cif_lines.append(f"_cell_volume           {cif_data.cell_volume:.4f}")
    cif_lines.append(f"_space_group_name_H-M  '{cif_data.sg_name}'")
    cif_lines.append(f"_space_group_IT_number {cif_data.sg_num}")

    cif_lines.append("")
    cif_lines.append("loop_")
    cif_lines.append("_symmetry_equiv_pos_as_xyz")

    sym_ops = cif_data.sym_ops.split(';') if cif_data.sym_ops else ['x,y,z']
    for op in sym_ops:
        cif_lines.append(f"'{op.strip()}'")
    
    cif_lines.append("")
    cif_lines.append("loop_")
    cif_lines.append("_atom_site_label")
    cif_lines.append("_atom_site_type_symbol")
    cif_lines.append("_atom_site_fract_x")
    cif_lines.append("_atom_site_fract_y")
    cif_lines.append("_atom_site_fract_z")
    cif_lines.append("_atom_site_occupancy")
    cif_lines.append("_atom_site_U_iso_or_equiv")
    cif_lines.append("_atom_site_adp_type")
    for atom in cif_data.atoms:
        line = f"{atom.label:6s} {atom.element:2s}  {atom.x:.6f}  {atom.y:.6f}  {atom.z:.6f}  {atom.occupancy:.4f}  {atom.u_iso_equiv:.6f}  {atom.adp_type:.10s}"
        cif_lines.append(line)
    
    has_aniso = False
    for atom in cif_data.atoms:
        if atom.adp_type == 'Uani':
            has_aniso = True
            break
    if has_aniso:
        cif_lines.append("")
        cif_lines.append("loop_")
        cif_lines.append("_atom_site_aniso_label")
        cif_lines.append("_atom_site_aniso_U_11")
        cif_lines.append("_atom_site_aniso_U_22")
        cif_lines.append("_atom_site_aniso_U_33")
        cif_lines.append("_atom_site_aniso_U_12")
        cif_lines.append("_atom_site_aniso_U_13")
        cif_lines.append("_atom_site_aniso_U_23")
        for atom in cif_data.atoms:
            if atom.adp_type == 'Uani':
                line = f"{atom.label:6s}  {atom.u11:.6f}  {atom.u22:.6f}  {atom.u33:.6f}  {atom.u12:.6f}  {atom.u13:.6f}  {atom.u23:.6f}"
                cif_lines.append(line)

    return cif_lines


def expand_cif_atoms(cif_atoms, sym_ops_list, boundary=-1e-4, decimals=4):
    from copy import copy
    full_atoms = []
    for atom in cif_atoms:
        element = atom.element.strip()
        fract = np.array([atom.x, atom.y, atom.z])
        sym_fracts, _ = _math.fract_symop(fract, sym_ops_list)
        sym_fracts = _math.fracts_normalize(sym_fracts, boundary)
        fract_tuples = [tuple(f) for f in sym_fracts]
        unique_fracts = _math.deduplicate_fracts(fract_tuples, decimals)

        for f in unique_fracts:
            full_atoms.append((element, f[0], f[1], f[2]))
    return full_atoms


def vasp_block(cif_data, name, use_cartesian):
    vasp_lines = []
    vasp_lines.append("ChemBlender_"+name)
    scale = 1.0
    vasp_lines.append(f"{scale}")

    cell_lengths = (cif_data.a, cif_data.b, cif_data.c)
    cell_angles  = (cif_data.alpha, cif_data.beta, cif_data.gamma)
    cell_mat, _ = _math.make_cell_matrix(cell_lengths, cell_angles)

    for row in cell_mat.T:
        vasp_lines.append(f"{row[0]:16.8f} {row[1]:16.8f} {row[2]:16.8f}")
    sym_op_list = cif_data.sym_ops.split(';') if cif_data.sym_ops else ['x,y,z']
    full_atoms = expand_cif_atoms(cif_data.atoms, sym_op_list)

    elem_dict = {}
    for element,_,_,_ in full_atoms:
        if element not in elem_dict:
            elem_dict[element] = 0
        elem_dict[element] += 1
    elem_list = list(elem_dict.keys())
    count_list = [str(n) for n in elem_dict.values()]

    vasp_lines.append("   ".join(elem_list))
    vasp_lines.append("   ".join(count_list))

    if use_cartesian:
        vasp_lines.append("Cartesian")
    else:
        vasp_lines.append("Direct")
    
    if use_cartesian:
        for element,x,y,z in full_atoms:
            fracts = np.array([x,y,z])
            carts = fracts @ cell_mat
            line = f"{carts[0]:16.8f} {carts[1]:16.8f} {carts[2]:16.8f}"
            vasp_lines.append(line)
    else:
        for element,x,y,z in full_atoms:
            line = f"{x:16.8f} {y:16.8f} {z:16.8f}"
            vasp_lines.append(line)

    return vasp_lines


class SaveMolButton(Operator):
    """Convert scaffold structure to molecular file"""
    bl_idname = "chem.molecule_output"
    bl_label = "保存分子文件" if language else "Export Molecular File"
    bl_description = "从分子骨架生成分子文件" if language else "Generate a molecular file from the selected molecular graph scaffold"
    bl_options = {'REGISTER', 'UNDO'}

    export_format: EnumProperty(
        name="",
        description="Export file format",
        items=[
            ('CIF',"CIF","Crystallographic Information File"),
            ('MOL',"MOL","MDL format"),
            ('SDF',"SDF","Structure data file"),
            ('VASP',"VASP/POSCAR","Crystal file"),
            ('XYZ',"XYZ","XYZ Coordinate file")
        ],
        default='MOL'
    )

    mol_version: EnumProperty(
        name ="",
        default='V2000',
        items=[
            ('V2000', 'V2000', ''),
            ('V3000', 'V3000', '')
        ]
    )

    vasp_coord_mode: EnumProperty(
        name="",
        default = 'DIRECT',
        items=[
            ('DIRECT', 'Fractional coordinates',''),
            ('CARTESIAN', 'Cartesian coordinates', '')
        ]
    )
    filepath: StringProperty(subtype="FILE_PATH")

    def draw(self, context):
        layout = self.layout
        layout.prop(self,"export_format")

        if self.export_format == 'MOL':
            layout.prop(self, "mol_version")

        if self.export_format == 'VASP':
            layout.prop(self, "vasp_coord_mode")

    def execute(self, context):
        ao = context.object
        if not ao or ao.get('Type') != 'scaffold':
            self.report({'WARNING'}, warning_text)
            return {'CANCELLED'}

        atomic_num_to_symbol = {num: sym for sym, (num, *_) in ELEMENTS_DEFAULT.items()}
        bond_type_map = {1: 1, 2: 2, 3: 3, 12: 4}
        Atomic_Nums = mesh.get_attr(ao, 'atomic_num', 'INT', 'VERT')
        Bond_Orders  = mesh.get_attr(ao, 'bond_order',  'INT', 'EDGE')

        atoms = []
        for vert, atomic_num in zip(ao.data.vertices, Atomic_Nums):
            x, y, z = vert.co
            symbol = atomic_num_to_symbol.get(atomic_num, 'C')
            atoms.append( (x, y, z, atomic_num, symbol) )

        vert_to_idx = {v.index: i + 1 for i, v in enumerate(ao.data.vertices)}
        bonds = []
        for e, bond_order in zip(ao.data.edges, Bond_Orders):
            v1 = vert_to_idx[e.vertices[0]]
            v2 = vert_to_idx[e.vertices[1]]
            bond_type = bond_type_map.get(bond_order, 1)
            bonds.append((v1, v2, bond_type))

        if self.export_format == 'MOL':
            if self.mol_version == 'V2000':
                mol_lines = mol_block_v2000(ao.name, atoms, bonds)
            else:
                mol_lines = mol_block_v3000(ao.name, atoms, bonds)

            if not self.filepath.lower().endswith('.mol'):
                self.filepath += '.mol'
                
            with open(self.filepath, "w", encoding='utf-8') as f:
                f.write("\n".join(mol_lines))
            self.report({'INFO'}, f"Molecule Saved As: {self.filepath}")
            return {'FINISHED'}
        
        elif self.export_format == 'SDF':
            sdf_lines = sdf_block(ao.name, atoms, bonds)
            if not self.filepath.lower().endswith('.sdf'):
                self.filepath += '.sdf'
            with open(self.filepath, "w", encoding='utf-8') as f:
                f.write("\n".join(sdf_lines))
            self.report({'INFO'}, f"SDF Saved As: {self.filepath}")
            return {'FINISHED'}

        elif self.export_format == 'XYZ':
            xyz_lines = xyz_block(ao.name, atoms)
            if not self.filepath.lower().endswith('.xyz'):
                self.filepath += '.xyz'
            with open(self.filepath, "w", encoding='utf-8') as f:
                f.write("\n".join(xyz_lines))
            self.report({'INFO'}, f"XYZ Saved As: {self.filepath}")
            return {'FINISHED'}

        elif self.export_format in ('CIF','VASP'):
            if not hasattr(ao, 'cif_original') or ao.cif_original.atom_count == 0:
                self.report({'ERROR'}, "No Crystal CIF data.")
                return {'CANCELLED'}
            
            cif_data = ao.cif_current
            # generate standard cif file
            cif_lines = cif_block(cif_data, ao.name)

            if self.export_format == 'VASP':
                use_cart = (self.vasp_coord_mode == 'CARTESIAN')
                vasp_lines = vasp_block(cif_data, ao.name, use_cartesian=use_cart)

            if self.export_format == 'CIF':
                if not self.filepath.lower().endswith('.cif'):
                    self.filepath += '.cif'
                with open(self.filepath, "w", encoding='utf-8') as f:
                    f.write("\n".join(cif_lines))
                self.report({'INFO'}, f"CIF Saved As: {self.filepath}")

            elif self.export_format == 'VASP':
                if not self.filepath.lower().endswith('.vasp'):
                    self.filepath += '.vasp'
                with open(self.filepath, "w", encoding='utf-8') as f:
                    f.write("\n".join(vasp_lines))
                self.report({'INFO'}, f"VASP File Saved As: {self.filepath}")

            
            return {'FINISHED'}
        
    def invoke(self, context, event):
        # 调用文件选择器对话框
        self.filepath = context.object.name
        context.window_manager.fileselect_add(self)  # 打开文件保存路径设置窗口
        return {'RUNNING_MODAL'}


class UpdateCIFFromMesh(Operator):
    bl_idname = "chem.update_cif_from_mesh"
    bl_label = "更新CIF数据" if language else "Update CIF from Mesh"
    bl_description = ("从当前骨架重新计算原子坐标、分子式、空间群等信息并更新到cif_original"
                      if language else
                      "Recalculate atom coords, formula and space group from current mesh and update cif_original")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ao = context.object
        if not ao or ao.get('Type') != 'scaffold':
            self.report({'WARNING'}, "请选择分子骨架" if language else "Please select a scaffold object")
            return {'CANCELLED'}
        if not hasattr(ao, 'cif_original') or ao.cif_original.atom_count == 0:
            self.report({'ERROR'}, "No CIF data found.")
            return {'CANCELLED'}

        ok, msg = read.update_cif_from_mesh(ao)
        self.report({'INFO'} if ok else {'ERROR'}, msg)
        return {'FINISHED'} if ok else {'CANCELLED'}


class AddCameraButton(Operator):
    """Add camera from view"""
    bl_idname = "chem.add_camera"
    bl_label = "添加摄像机" if language else "Add Camera"
    bl_description = "为当前视角添加摄像机" if language else "Add a camera to current view."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            # 判断当前视图是否已经是相机视角
            if context.space_data.region_3d.view_perspective == 'CAMERA':
                self.report({'INFO'}, "当前已是摄像机视角，操作已取消")
                return {'CANCELLED'}
            bpy.ops.object.camera_add()
            camera = bpy.context.active_object
            # 设置当前场景的摄像机
            bpy.context.scene.camera = camera
            bpy.ops.view3d.camera_to_view()
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"发生错误: {str(e)}")
            return {'CANCELLED'}

class QuickRenderSetting(Operator):
    bl_idname = "chem.quick_render_set"
    bl_label = "快捷渲染设置" if language else "Quick Render Setting"
    bl_description = "设置渲染参数" if language else "Set rendering parameters."
    bl_options = {'REGISTER', 'UNDO'}

    engine: EnumProperty(
        name='',
        default='CYCLES',
        items=[
            ('CYCLES',"Cycles","Path tracing"),
            ('BLENDER_EEVEE',"Eevee","Real time"),
        ]
    )
    
    view_transform:EnumProperty(
        name='',
        default='AgX',
        items=[
            ('Standard',"Standard",""),
            ('Filmic',"Filmic",""),
            ('AgX',"AgX",""),
            ('False Color',"False Color",""),
            ('Raw',"Raw",""),
        ]
    )

    samples: IntProperty(name='',default=12,min=1,max=4096)
    res_x: IntProperty(name='X',default=1920,min=1)
    res_y: IntProperty(name='Y',default=1080,min=1)
    pixel_density: IntProperty(name='',default=300,min=1,max=1200)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        text = "渲染引擎:" if language else "Render Engine:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "engine")

        row = layout.row()
        text = "最大采样:" if language else "Max Samples:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "samples")

        row = layout.row()
        text = "分辨率:" if language else "Resolution:"
        split = row.split(factor=0.36)
        split.label(text=text)
        col = split.column()
        col.prop(self, 'res_x', index=0)
        col.prop(self, 'res_y', index=1)

        row = layout.row()
        text = "像素密度:" if language else "Pixel Density:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "pixel_density")

        row = layout.row()
        text = "色彩管理:" if language else "Color Management:"
        row.label(text=text)
        row.scale_x = 1.8
        row.prop(self, "view_transform")

    
    def execute(self, context):
        scene = context.scene
        render = scene.render

        render.engine = self.engine
        if self.engine == 'CYCLES':
            scene.cycles.samples = self.samples
        else:
            scene.eevee.taa_render_samples = self.samples
        
        scene.view_settings.view_transform = self.view_transform
        render.resolution_x = self.res_x
        render.resolution_y = self.res_y
        render.ppm_factor = self.pixel_density

        return {'FINISHED'}


class QuickRenderButton(Operator):
    """One click rendering"""
    bl_idname = "chem.quick_render"
    bl_label = "快捷渲染" if language else "Quick Render"
    bl_description = "一键渲染出图" if language else "One click rendering."
    bl_options = {'REGISTER', 'UNDO'}

    def quick_render(self):
        scene = bpy.context.scene
        render = scene.render
        mytool = scene.my_tool
        world = scene.world

        scene.render.film_transparent = True

        tree = world.node_tree
        nodes = tree.nodes
        links = tree.links

        for node in list(nodes):
            if node.type in ["TEX_ENVIRONMENT", "MAPPING", "TEX_COORD"]:
                nodes.remove(node)

        if "Background" not in nodes:
            bg = nodes.new(type='ShaderNodeBackground')
            world_output = nodes.new(type='ShaderNodeOutputWorld')
            links.new(bg.outputs[0], world_output.inputs[0])
        else:
            bg = nodes["Background"]

        # bg.inputs["Strength"].default_value = 1.0

        env_path = mytool.env_texture.strip()
        if env_path in ("选择环境贴图", "Select Environment Texture"):
            env_path = ""

        if env_path != "":
            if not os.path.isfile(env_path):
                raise Exception("文件不存在")
            for node in list(nodes):
                if node.type == "ENVIRONMENT_TEXTURE":
                    nodes.remove(node)

            try:
                env_tex = nodes.new(type='ShaderNodeTexEnvironment')
                env_tex.image = bpy.data.images.load(env_path, check_existing=True)

                tex_coord = nodes.new(type='ShaderNodeTexCoord')
                mapping = nodes.new(type='ShaderNodeMapping')

                links.new(tex_coord.outputs["Generated"], mapping.inputs[0])
                links.new(mapping.outputs[0], env_tex.inputs[0])
                links.new(env_tex.outputs[0], bg.inputs["Color"])

            except:
                raise Exception("环境贴图加载失败")

        else:
            bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)

        bpy.ops.render.render('INVOKE_DEFAULT')


    def show_error_dialog(self, message):
        bpy.ops.error.custom_dialog('INVOKE_DEFAULT', message=message)

    def execute(self, context):
        try:
            self.quick_render()
            return {'FINISHED'}
        except Exception as e:
            text = f"操作失败: 请输入正确的环境贴图。\n错误信息: {e}" if language else f"Operation failed: Please input correct environment texture. \nError: {e}"
            self.show_error_dialog(text)
            return {'CANCELLED'}
