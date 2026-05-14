import bpy
from bpy.props import StringProperty, EnumProperty, BoolProperty, FloatVectorProperty, IntVectorProperty
language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0

# ------------------------------------------------------------------------------------
# This class lists properties shown in Panel but not in Operator.
class CHEM_texts(bpy.types.PropertyGroup):
    def update_view_opposite(self, context):
        import mathutils

        # 找到 3D 视图
        rv3d = None
        for area in context.window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        rv3d = region.data
                        break
                if rv3d:
                    break
        if not rv3d:
            return

        # 获取当前视线方向（视图看向 -Z）
        view_dir = rv3d.view_rotation @ mathutils.Vector((0,0,-1))
        # 直接反转为 -view_dir
        quat = (-view_dir).to_track_quat('-Z', 'Y')

        rv3d.view_rotation = quat


    filetext: StringProperty(
        name = "Filepath",
        default = "选择分子文件路径" if language else 'Input Molecule Filepath',
        subtype = 'FILE_PATH'
    ) # type: ignore

    smilestext: StringProperty(
        name = "文本输入" if language else "Text Input",
        default = "请输入分子SMILES符号" if language else 'Input SMILES',
        subtype = 'NONE'
    ) # type: ignore

    pubchemtext: StringProperty(
        name = "文本输入" if language else "Text Input",
        default = "请输入CID号或其他PubChem描述" if language else 'Input CID or other PubChem Synonyms',
        subtype = 'NONE'
    ) # type: ignore

    select_text: StringProperty(
        name = '',
        default = "输入文本" if language else "Input Text Here",
        description = "Text of Element Name for Scaling"
    ) # type:ignore

    choose: EnumProperty(
        name = "选项列表" if language else "Option List",
        default = "File",
        items = [("File","从文件创建",""),
                 ("PubChem","从PubChem创建",""),
                 ("SMILES","从SMILES创建",""),
                 ("Saccharides","糖类",""),
                 ("Amino_Acids","氨基酸",""),
                 ("Polymer_Units", "聚合物单元",""),
        ] if language else [
            ("File","From Files",""),
            ("PubChem","From PubChem",""),
            ("SMILES","From SMILES",""),
            ("Saccharides","Saccharides",""),
            ("Amino_Acids","Amino Acids",""),
            ("Polymer_Units", "Polymer Units",""),
        ]
    ) # type: ignore

    Saccharides: EnumProperty(
        name = "糖类" if language else "Saccharides",
        default = "Glc",
        items = [("Glc","葡萄糖",""),
                 ("Fru","果糖",""),
                 ("Gal","半乳糖",""),
                 ("Man","甘露糖",""),
                 ("Xyl","木糖",""),
                 ("Ara","阿拉伯糖",""),
                 ("Rib","核糖",""),
                 ("dRib","脱氧核糖",""),
                 ("Suc","蔗糖",""),
                 ("Lac","乳糖",""),
                 ("Mal","麦芽糖",""),
                 ("I-Mal","异麦芽糖",""),
                 ("Tre","海藻糖",""),
                 ("Cel","纤维二糖",""),
                 ("Raf","棉子糖",""),
        ] if language else [
            ("Glc","Glucose",""),
            ("Fru","Fructose",""),
            ("Gal","Galactose",""),
            ("Man","Mannose",""),
            ("Xyl","Xylose",""),
            ("Ara","Arabinose",""),
            ("Rib","Ribose",""),
            ("dRib","Deoxyribose",""),
            ("Suc","Sucrose",""),
            ("Lac","Lactose",""),
            ("Mal","Maltose",""),
            ("I-Mal","Isomaltose",""),
            ("Tre","Trehalose",""),
            ("Cel","Cellobiose",""),
            ("Raf","Raffinose",""),
        ]
    ) # type: ignore

    Amino_Acids: EnumProperty(
        name = "氨基酸" if language else "Amino acids",
        default = "A",
        items = [("A","丙氨酸","Ala"),
                 ("R","精氨酸","Arg"),
                 ("D","天冬氨酸","Asp"),
                 ("N","天冬酰胺","Asn"),
                 ("C","半胱氨酸","Cys"),
                 ("E","谷氨酸","Glu"),
                 ("Q","谷氨酰胺","Gln"),
                 ("G","甘氨酸","Gly"),
                 ("H","组氨酸","His"),
                 ("I","异亮氨酸","Ile"),
                 ("L","亮氨酸","Leu"),
                 ("K","赖氨酸","Lys"),
                 ("M","甲硫氨酸","Met"),
                 ("F","苯丙氨酸","Phe"),
                 ("P","脯氨酸","Pro"),
                 ("S","丝氨酸","Ser"),
                 ("T","苏氨酸","Thr"),
                 ("W","色氨酸","Trp"),
                 ("Y","酪氨酸","Tyr"),
                 ("V","缬氨酸","Val"),
        ] if language else [
            ("A","Alanine","Ala"),
            ("R","Arginine","Arg"),
            ("D","Aspartic acid","Asp"),
            ("N","Asparagine","Asn"),
            ("C","Cysteine","Cys"),
            ("E","Glutamic acid","Glu"),
            ("Q","Glutamine","Gln"),
            ("G","Glycine","Gly"),
            ("H","Histidine","His"),
            ("I","Isoleucine","Ile"),
            ("L","Leucine","Leu"),
            ("K","Lysine","Lys"),
            ("M","Methionine","Met"),
            ("F","Phenylalanine","Phe"),
            ("P","Proline","Pro"),
            ("S","Serine","Ser"),
            ("T","Threonine","Thr"),
            ("W","Tryptophan","Trp"),
            ("Y","Tyrosine","Tyr"),
            ("V","Valine","Val"),
        ]
    ) # type: ignore

    Polymer_Units: EnumProperty(
        name = "聚合物单元" if language else "Polymer Units",
        default = "PE",
        items = [("PE","聚乙烯单元","Polyethylene"),
                 ("PP","聚丙烯单元","Polypropylene"),
                 ("PS","聚苯乙烯单元","Polystyrene"),
                 ("PVC","聚氯乙烯单元","Polyvinyl chloride"),
                 ("PTFE","聚四氟乙烯单元","Teflon"),
                 ("PVDC","聚偏二氯乙烯单元","Polyvinylidene chloride"),
                 ("PVA","聚乙烯醇单元","Polyvinyl alcohol"),
                 ("PEG","聚乙二醇单元","Polyethylene glycol"),
                 ("PMMA","聚甲基丙烯酸甲酯单元","Polymethyl methacrylate"),
                 ("PAN","聚丙烯腈单元","Polyacrylonitrile"),
                 ("PB","聚丁二烯单元","Polybutadiene"),
                 ("PVAC","聚乙酸乙烯酯单元","Polyvinyl acetate"),
                 ("PLA","聚乳酸单元","Polylactic acid"),
                 ("PET","聚对苯二甲酸乙二醇酯单元","Polyethylene terephthalate"),
                 ("PBT","聚对苯二甲酸丁二醇酯单元","Polybutylene terephthalate"),
                 ("Kevlar","聚对苯二甲酰对苯二胺单元","Poly-p-phenylene terephthamide"),
                 ("PC","聚碳酸酯单元","Polycarbonate"),
                 ("PEEK","聚醚醚酮单元","Polyether ether ketone"),
                 ("PA","聚己内酰胺单元","Polyamide"),
                 ("PI","聚酰亚胺单元","Polyimide"),
                 ("PAA","聚丙烯酸单元","Polyacrylic Acid"),
                 ("PAAm","聚丙烯酰胺单元","Polyacrylamide"),
                 ("PVP","聚乙烯吡咯烷酮单元","Polyvinylpyrrolidone"),
                 ("PDMS","聚二甲基硅氧烷单元","Polydimethylsiloxane"),
        ] if language else [
            ("PE","uPE","Polyethylene"),
            ("PP","uPP","Polypropylene"),
            ("PS","uPS","Polystyrene"),
            ("PVC","uPVC","Polyvinyl chloride"),
            ("PTFE","uPTFE","Teflon"),
            ("PVDC","uPVDC","Polyvinylidene chloride"),
            ("PVA","uPVA","Polyvinyl alcohol"),
            ("PEG","uPEG","Polyethylene glycol"),
            ("PMMA","uPMMA","Polymethyl methacrylate"),
            ("PAN","uPAN","Polyacrylonitrile"),
            ("PB","uPB","Polybutadiene"),
            ("PVAC","uPVAC","Polyvinyl acetate"),
            ("PLA","uPLA","Polylactic acid"),
            ("PET","uPET","Polyethylene terephthalate"),
            ("PBT","uPBT","Polybutylene terephthalate"),
            ("Kevlar","uKevlar","Poly-p-phenylene terephthamide"),
            ("PC","uPC","Polycarbonate"),
            ("PEEK","uPEEK","Polyether ether ketone"),
            ("PA","uPA","Polyamide"),
            ("PI","uPI","Polyimide"),
            ("PAA","uPAA","Polyacrylic Acid"),
            ("PAAm","uPAAm","Polyacrylamide"),
            ("PVP","uPVP","Polyvinylpyrrolidone"),
            ("PDMS","uPDMS","Polydimethylsiloxane"),
        ]
    ) # type: ignore

    distance: StringProperty(
        name = '',
        default = "键长 (Å)" if language else "Distance (Å)",
        description = "Length of an edge in Ångstrom"
    ) # type: ignore

    angle: StringProperty(
        name = '',
        default = "键角 (°)" if language else "Angle (°)",
        description = "Angle of two edges in degree"
    ) # type: ignore

    energy: StringProperty(
        name = '',
        default = '势能(kcal/mol)' if language else "Energy (kcal/mol)",
        description = "Molecular potential energy"
    ) # type: ignore

    avgfract: StringProperty(name='', default='x, y, z') # type:ignore

    view_uvw: FloatVectorProperty(
        name = "uvw",
        default = (1,0,0),
        description = "View direction vector (u,v,w)"
    ) # type: ignore

    view_hkl: IntVectorProperty(
        name = "hkl",
        default = (1,0,0),
        description = "View normal to hkl palne"
    ) # type: ignore

    view_axis_opposite: BoolProperty(
        name = "Opposite Direction",
        default = False,
        description = "View along the opposite direction",
        update = update_view_opposite
    ) # type: ignore

    env_texture: StringProperty(
        name = '',
        default = "选择环境贴图" if language else "Select Environment Texture",
        subtype = 'FILE_PATH',
    ) # type: ignore



class CHEM_PT_Build(bpy.types.Panel):
    bl_label = "分子骨架创建" if language else "Build Molecules"
    bl_idname = "CHEM_PT_BUILD"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ChemBlender'

    def draw(self, context):
        mytool = context.scene.my_tool
        layout = self.layout
        layout.prop(mytool, "choose")
        if mytool.choose == 'Saccharides':
            layout.prop(mytool, "Saccharides")
        elif mytool.choose == 'Amino_Acids':
            layout.prop(mytool, "Amino_Acids")
        elif mytool.choose == 'Polymer_Units':
            layout.prop(mytool, "Polymer_Units")
        elif mytool.choose == 'File':
            layout.prop(mytool, "filetext")
        elif mytool.choose == 'PubChem':
            layout.prop(mytool, "pubchemtext")
        else:
            layout.prop(mytool, "smilestext")

        layout.row()
        text = "创建球棍模型" if language else "Ball and Stick"
        layout.operator("chem.scaffold_build", text=text, icon="GREASEPENCIL")

class CHEM_PT_TOOLS(bpy.types.Panel):
    bl_label = "分子工具" if language else "ChemBlender Tools"
    bl_idname = "CHEM_PT_UTILITY"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ChemBlender'
    bl_options= {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        mytool = context.scene.my_tool

        row = layout.row(align=True)
        row.prop(mytool, "select_text")
        row.scale_x = 0.75
        text = "选择" if language else "Select"
        row.operator('mol3d.select', text = text)
        row = layout.row(align=True)
        text = "测量长度" if language else "Length Calc."
        row.operator("chem.button_distance", text=text)
        row.prop(mytool,"distance")
        row = layout.row(align=True)
        text = "测量角度" if language else "Angle Calc."
        row.operator("chem.button_angle", text=text)
        row.prop(mytool,"angle")
        row = layout.row(align=True)
        text = "势能计算" if language else "Energy Calc."
        row.operator("chem.button_energy", text=text)
        row.prop(mytool,"energy")

        row = layout.row()
        text = "设置原子" if language else "Set Atoms"
        row.operator("chem.set_atoms", text=text)
        text = "设置键" if language else "Set Bonds"
        row.operator("chem.set_bonds", text=text)

        row = layout.row()
        text = "补全氢原子" if language else "Add Hydrogens"
        row.operator("chem.add_hydrogens", text=text)
        text = "添加分支" if language else "Add Branches"
        row.operator("chem.add_branches", text=text)
        row = layout.row()
        text = "构象优化" if language else "Optimize Geometry"
        row.operator("chem.geometry_optimize", text=text)
        text = "构象更新" if language else "Update Geometry"
        row.operator("chem.geometry_update", text=text)
        row = layout.row()
        text = "选中对象导出为分子文件" if language else "Export Scaffold to Block File"
        row.operator("chem.export_block", text=text)
        row = layout.row()
        text = "选中网格转换为分子骨架" if language else "Convert Mesh to Mol Scaffold"
        row.operator("chem.mesh2scaffold", text=text)

class CRYSTAL_PT_TOOLS(bpy.types.Panel):
    bl_label = "晶体工具" if language else "Crystal Tools"
    bl_idname = "CRYSTAL_PT_UTILITY"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ChemBlender'
    bl_options= {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        mytool = context.scene.my_tool

        row = layout.row(align=True)
        text = "创建晶胞" if language else "Add New Cell"
        row.operator("chem.add_unit_cell", text=text)
        text = "添加骨架" if language else "Add New Crystal"
        row.operator("chem.add_crys_scaffold", text=text)
        
        row = layout.row(align=True)
        text = "对称选择" if language else "Symmetry Select"
        row.operator("chem.sel_symmetry", text=text)
        text = "对称复制" if language else "Symmetry Duplicate"
        row.operator("chem.duplicate_symmetry", text=text)

        row = layout.row(align=True)
        text = "超胞生成" if language else "Generate Supercell"
        row.operator("chem.supercell", text=text)
        text = "添加配位多面体" if language else "Add Coordination Polyhedra"
        row.operator("chem.add_coordpolyhedra", text=text)

        row = layout.row(align=True)
        text = "AVG. Fracts"
        row.operator("chem.avgfract", text=text)
        row.scale_x = 1.5
        row.prop(mytool, "avgfract")

        row = layout.row(align=True)
        text = "添加Dummy原子" if language else "Add Dummy"
        row.operator("chem.add_dummy", text=text)

        box = layout.box()
        box.label(text="Viewing Direction")
        row = box.row(align=True)
        row.operator("chem.view_set", text="a").mode = "A"
        row.operator("chem.view_set", text="b").mode = "B"
        row.operator("chem.view_set", text="c").mode = "C"
        row.separator()
        row.operator("chem.view_set", text="x").mode = "X"
        row.operator("chem.view_set", text="y").mode = "Y"
        row.operator("chem.view_set", text="z").mode = "Z"
        
        row = box.row(align=True)
        row.prop(mytool, "view_uvw", text="u,v,w")
        row.separator()
        row.operator("chem.view_set", text="Set").mode="uvw"
        row = box.row(align=True) 
        row.prop(mytool, "view_hkl", text="h,k,l")
        row.separator()
        row.operator("chem.view_set", text="Set").mode="hkl"
        row = box.row()
        row.prop(mytool, "view_axis_opposite", text="Opposite direction")



class CHEM_PT_RENDER(bpy.types.Panel):
    bl_label = "渲染工具" if language else "Render Tools"
    bl_idname = "CHEM_PT_RENDER"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ChemBlender'
    bl_options= {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        mytool = context.scene.my_tool
        layout.prop(mytool, "env_texture")

        row = layout.row(align=True)
        text = "添加视角摄像机" if language else "Add View Camera"
        row.operator("chem.add_camera", text=text)
        text = "快捷渲染" if language else "Quick Render"
        row.operator("chem.quick_render", text=text)