import bpy
import os, re, json
from .panel import CHEM_texts
from .read import CIF_Atom, CIF_Structure
from bpy.types import (
    Operator,
    Menu,
)
from bpy.props import (
    StringProperty,
)

# Get the plugin directory path
dir_path = os.path.dirname(__file__)

geo_node_group = {}
cat_list = []

# 生成分类菜单
def cat_generator():
    for item in geo_node_group.items():
        def my_list(self, context):
            layout = self.layout
            for name_group in geo_node_group[self.bl_label]:
                props = layout.operator(
                    NODE_OT_group_add.bl_idname,
                    text=re.sub(r'.*?_', '', name_group), # 去除前缀
                )
                props.name_group = name_group

        menu_type = type("NODE_MT_group_" + item[0], (bpy.types.Menu,), {
            "bl_idname": "NODE_MT_group_" + item[0].replace(" ", "_"),   # Replace spaces with underscores to avoid alpha-numeric suffic warning
            "bl_space_type": 'NODE_EDITOR',
            "bl_label": item[0],
            "draw": my_list,
        })
        def generate_menu_draw(name, label): # 强制唯一引用
            def draw_menu(self, context):
                self.layout.menu(name, text=label)
            return draw_menu

        draw_callback = generate_menu_draw(menu_type.bl_idname, menu_type.bl_label)
        bpy.utils.register_class(menu_type)
        bpy.types.NODE_MT_chem_GN_menu.append(draw_callback)
        cat_list.append((menu_type, draw_callback))


def clear_generated_menus():
    for menu_type, draw_callback in reversed(cat_list):
        try:
            bpy.types.NODE_MT_chem_GN_menu.remove(draw_callback)
        except (AttributeError, ValueError, RuntimeError):
            pass
        try:
            bpy.utils.unregister_class(menu_type)
        except (ValueError, RuntimeError):
            pass
    cat_list.clear()


class NODE_MT_chem_GN_menu(Menu):
    bl_label = "Chem Nodes"
    bl_idname = 'NODE_MT_chem_GN_menu'

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'GeometryNodeTree'

    def draw(self, context):
        pass

language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0
class NODE_OT_group_add(Operator):
    """Add node group"""
    bl_idname = "chem.add_node_group"
    bl_label = "Add node group"
    bl_options = {'REGISTER', 'UNDO'}

    name_group: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.space_data.node_tree is not None  # Ensure there is a node tree in the context

    def execute(self, context):
        old_groups = set(bpy.data.node_groups)

        # 查找 .blend 文件
        
        file = "Chem_Nodes.blend" if language else "Chem_Nodes_En.blend"
        filepath = os.path.join(dir_path, file)
        print(f"正在加载 .blend 文件: {filepath}")
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"未在目录 {dir_path} 中找到 {file} 文件")

        # 加载 .blend 文件中的节点组
        with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
            if self.name_group in data_from.node_groups:
                data_to.node_groups.append(self.name_group)
        
        # 确保新导入的节点组在 bpy.data.node_groups 中可用
        new_groups = list(set(bpy.data.node_groups) - old_groups)
        for group in new_groups:
            for node in group.nodes:
                if node.type == "GEOMETRY":
                    name_new = node.node_tree.name.split(".")[0]
                    node.node_tree = bpy.data.node_groups[name_new]
        
        # 删除无效副本节点组
        for group in new_groups:
            if "." in group.name:
                bpy.data.node_groups.remove(group)

        # 添加新的几何节点组到当前节点树
        bpy.ops.node.add_node(type="GeometryNodeGroup")
        node = context.selected_nodes[0]
        node.node_tree = bpy.data.node_groups[self.name_group]
        bpy.ops.transform.translate('INVOKE_DEFAULT')

        return {'FINISHED'}

# Register the plugin's menu
def add_chem_button(self, context):
    if context.area.ui_type == 'GeometryNodeTree':
        self.layout.menu('NODE_MT_chem_GN_menu', text="Chem Nodes", icon='FORWARD')

def register():
    global geo_node_group

    clear_generated_menus()
    json_file = "GN_menu.json" if language else "GN_menu_En.json"
    with open(os.path.join(dir_path, json_file), 'r', encoding='utf-8') as stream:
        geo_node_group = json.load(stream)

    try:
        bpy.types.NODE_MT_add.remove(add_chem_button)
    except (ValueError, RuntimeError):
        pass
    bpy.types.NODE_MT_add.append(add_chem_button)

    for owner, name in (
        (bpy.types.Object, "cif_original"),
        (bpy.types.Object, "cif_current"),
        (bpy.types.Scene, "my_tool"),
    ):
        if hasattr(owner, name):
            delattr(owner, name)
    bpy.types.Object.cif_original = bpy.props.PointerProperty(type=CIF_Structure)
    bpy.types.Object.cif_current = bpy.props.PointerProperty(type=CIF_Structure)
    bpy.types.Scene.my_tool = bpy.props.PointerProperty(type=CHEM_texts)
    cat_generator()


def unregister():
    clear_generated_menus()
    try:
        bpy.types.NODE_MT_add.remove(add_chem_button)
    except (ValueError, RuntimeError):
        pass

    for owner, name in (
        (bpy.types.Object, "cif_original"),
        (bpy.types.Object, "cif_current"),
        (bpy.types.Scene, "my_tool"),
    ):
        if hasattr(owner, name):
            delattr(owner, name)