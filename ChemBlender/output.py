import bpy
import os
from .legacy.scaffold_bridge import (
    route_legacy_export,
    route_legacy_scientific_edit,
)
from bpy.types import Operator
from bpy.props import IntProperty, FloatProperty, BoolProperty, StringProperty,EnumProperty, FloatVectorProperty
language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0

def xyz_block(name, atoms):
    lines = []
    lines.append(str(len(atoms)))
    lines.append(name)
    for x, y, z, atomic_num, symbol in atoms:
        lines.append(f"{symbol:<3s}  {x:12.6f}  {y:12.6f}  {z:12.6f}")
    return lines

class SaveMolButton(Operator):
    """Open the unified project export action."""
    bl_idname = "chem.molecule_output"
    bl_label = "保存分子文件" if language else "Export Molecular File"
    bl_description = "打开项目实体导出" if language else "Open unified project entity export"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return route_legacy_export(
            lambda operator_id: getattr(
                bpy.ops.chemblender,
                operator_id.rsplit(".", 1)[1],
            )("INVOKE_DEFAULT")
        )
        
    def invoke(self, context, event):
        return self.execute(context)


class UpdateCIFFromMesh(Operator):
    bl_idname = "chem.update_cif_from_mesh"
    bl_label = "更新CIF数据" if language else "Update CIF from Mesh"
    bl_description = ("打开统一的科学修改操作"
                      if language else
                      "Open unified Apply Scientific Edits")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return route_legacy_scientific_edit(
            lambda operator_id: getattr(
                bpy.ops.chemblender,
                operator_id.rsplit(".", 1)[1],
            )("INVOKE_DEFAULT")
        )


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
