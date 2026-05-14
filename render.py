import bpy
import bpy
import os

def quick_render(operator_self):
    scene = bpy.context.scene
    mytool = scene.my_tool
    world = scene.world

    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'GPU'
    scene.world.use_nodes = True

    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.cycles.preview_samples = 12
    scene.cycles.samples = 12

    tree = world.node_tree
    nodes = tree.nodes
    links = tree.links

    if "Background" not in nodes:
        bg = nodes.new(type='ShaderNodeBackground')
        world_output = nodes.new(type='ShaderNodeOutputWorld')
        links.new(bg.outputs[0], world_output.inputs[0])
    else:
        bg = nodes["Background"]

    bg.inputs["Strength"].default_value = 1.0

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