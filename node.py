import  bpy
import os
from .Chem_data import ELEMENTS_DEFAULT
# Get the plugin directory path
dir_path = os.path.dirname(__file__)
language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0
file = "Chem_Nodes.blend" if language else "Chem_Nodes_En.blend"
filepath = os.path.join(dir_path, file)

def add_geometry_nodetree(obj, GN_modifier_name, nodetree_name):
    bpy.context.view_layer.objects.active = obj
    GN_modifier = obj.modifiers.new(GN_modifier_name, 'NODES')
    bpy.ops.node.new_geometry_node_group_assign()
    GN_modifier.node_group.name = nodetree_name
    return GN_modifier

# nodetree means the Geometry Node Modifier
def set_io_nodes(nodetree, in_location, out_location):
    group = nodetree.node_group
    try:
        _input = group.nodes['Group Input']
    except:
        _input = group.nodes['组输入']
    _input.location = in_location
    try:
        _output = group.nodes['Group Output']
    except:
        _output = group.nodes['组输出']
    _output.location = out_location
    _input.label = 'in_node'
    _output.label = 'out_node'
    return (_input, _output)

# add a common geometry node in given nodetree
def add_node(nodetree, name, location, label):
    node = nodetree.node_group.nodes.new(name)
    node.location = location
    node.label = label
    return node

def add_node_group(nodetree, name, location): 
    new_group = nodetree.node_group.nodes.new(type="GeometryNodeGroup")
    new_group.node_tree = bpy.data.node_groups[name]
    new_group.location = location
    return new_group

# find the node in node_group through node label
def get_node(nodetree, node_label):
    target_node = None
    for node in nodetree.node_group.nodes:
        if node.label == node_label:
            target_node = node
    return target_node

def get_node_group(nodetree, group_name):
    target_ng = None
    for ng in nodetree.node_group.nodes:
        if ng.type == 'GROUP':
            if ng.node_tree.name.startswith(group_name):
                target_ng = ng
    return target_ng


# create links between two nodes or nodegroups
def nodes_link(nodetree, node_a, socket_out, node_b, socket_in):
    link = nodetree.node_group.links.new
    link(node_a.outputs[socket_out], node_b.inputs[socket_in])

def append(node_group_name, link=False):
    node = bpy.data.node_groups.get(node_group_name)
    if not node or link:
        bpy.ops.wm.append(
            'EXEC_DEFAULT',
            directory = os.path.join(filepath, 'NodeTree'),
            filename = node_group_name,
            link = link
        )

def Ball_Stick_nodetree(nodetree):
    a,b = (0,0)
    _input, _output = set_io_nodes(nodetree, (a,b), (a+800,b))
    attribute = "CH_添加分子属性" if language else "CH_Add Attributes"
    molecule = "CH_分子球棍模型" if language else "CH_Ball and Stick"
    material = "CH_添加分子材质" if language else "CH_Add Material"
    for node_group_name in [attribute, molecule, material]:
        append(node_group_name)
    _add_mol_attr = add_node_group(nodetree, attribute, (a+200,0))
    _ball_stick = add_node_group(nodetree, molecule, (a+400,0))
    _ball_stick.inputs[6].default_value = 0.5
    _add_material = add_node_group(nodetree, material, (a+600,0))
    nodes_link(nodetree, _input, 0, _add_mol_attr, 0)
    nodes_link(nodetree, _add_mol_attr, 0, _ball_stick, 0)
    nodes_link(nodetree, _ball_stick, 0, _add_material, 0)
    nodes_link(nodetree, _add_material, 0, _output, 0)

def Supercell(scaffold, nodetree, full_cell_cutoff):
    cell_lengths = tuple(map(float,scaffold['cell lengths'].strip("").split(',')))
    cell_angles = tuple(map(float,scaffold['cell angles'].strip("").split(',')))
    a,b = (0,0)
    _input, _output = set_io_nodes(nodetree, (a,b), (a+400,b))
    name1 = "负向边界" if language else "Negative Boundaries"
    name2 = "正向边界" if language else "Positive Boundaries"
    nodetree.node_group.interface.new_socket(name=name1,in_out='INPUT',socket_type='NodeSocketVector')
    nodetree.node_group.interface.new_socket(name=name2,in_out='INPUT',socket_type='NodeSocketVector')
    supercell = "CH_超胞" if language else "CH_Supercell"
    append(supercell)
    _supercell = add_node_group(nodetree, supercell, (a+200,0))
    _supercell.inputs[1].default_value = cell_lengths
    _supercell.inputs[2].default_value = cell_angles
    _supercell.inputs[5].default_value = full_cell_cutoff
    nodes_link(nodetree, _input, 0, _supercell, 0)
    nodes_link(nodetree, _input, 1, _supercell, 3)
    nodes_link(nodetree, _input, 2, _supercell, 4)
    nodes_link(nodetree, _supercell, 0, _output, 0)

def CoordPolyhedra(nodetree, append_mode, RMin, RMax, atomic_num):
    a,b=(0,0)
    _input, _output = set_io_nodes(nodetree, (a,b), (a+1000,b))
    group = nodetree.node_group

    coordpoly_name = "CH_配位多面体" if language else "CH_Coord Polyhedra"
    remove_name = "CH_移除共面边" if language else "CH_Remove Coplanar Edges"
    material_name = "CH_添加分子材质" if language else "CH_Add Material"
    append(coordpoly_name)
    append(remove_name)

    if not append_mode: # 逐个添加
        nodes_to_remove = []
        for node in group.nodes:
            if node.type == 'GROUP' and node.node_tree:
                if node.node_tree.name in [coordpoly_name, remove_name]:
                    nodes_to_remove.append(node)
        for n in nodes_to_remove:
            group.nodes.remove(n)

    _joingeo = None
    for node in group.nodes:
        if node.type == 'JOIN_GEOMETRY':
            _joingeo = node
            break

    if not _joingeo:
        _joingeo = add_node(nodetree,'GeometryNodeJoinGeometry', (a+800,0), '')
        _material = get_node_group(nodetree, material_name)
        if _material:
            nodes_link(nodetree, _material, 0, _joingeo, 0)
        nodes_link(nodetree, _joingeo, 0, _output, 0)

    existing_poly = len([
        n for n in group.nodes if n.type == 'GROUP' and n.node_tree and coordpoly_name in n.node_tree.name
    ])

    y_pos = b + 250 + (existing_poly*250)
    _coordpoly = add_node_group(nodetree, coordpoly_name, (250,y_pos))
    if append_mode:
        _coordpoly.inputs[1].default_value = '自定义' if language else 'Customize'
        _coordpoly.inputs[5].default_value = atomic_num
    _coordpoly.inputs[2].default_value = RMin
    _coordpoly.inputs[3].default_value = RMax
    _remove = add_node_group(nodetree, remove_name, (450,y_pos))

    nodes_link(nodetree, _input, 0, _coordpoly, 0)
    nodes_link(nodetree, _coordpoly, 0, _remove, 0)
    nodes_link(nodetree, _remove, 0, _joingeo, 0)


def crys_filter(scaffold, molname, filters):
    if not filters:
        return
    
    nodetree = add_geometry_nodetree(scaffold, 'GN_Crys_Filter_'+molname, 'Nodetree_Crys_Filter')
    a,b=(0,0)
    _input, _output = set_io_nodes(nodetree, (a,b), (a+200*len(filters)+200, b))
    filter_element = "CH_过滤原子" if language else "CH_Filter Element"
    append(filter_element)

    previous_output = _input
    x_offset = 250
    for i, element in enumerate(filters):
        if not element:
            continue
        atomic_num = ELEMENTS_DEFAULT[element][0]
        _filter = add_node_group(nodetree, filter_element, (a+x_offset,b))
        _filter.inputs[1].default_value = atomic_num
        nodes_link(nodetree, previous_output, 0, _filter, 0)

        previous_output = _filter
        x_offset += 250

    nodes_link(nodetree, previous_output, 0, _output, 0)

def crys_expand(scaffold, cell_lengths, cell_angles, grow_iter):
    nodetree = add_geometry_nodetree(scaffold, 'GN_expand', 'Ex_scaffold')
    a,b=(0,0)
    _input, _output = set_io_nodes(nodetree, (a,b), (a+400, b))
    cell_expand = "CH_晶胞扩展" if language else "CH_Cell Expand"
    append(cell_expand)

    expand = add_node_group(nodetree, cell_expand, (a+200,b))
    a, b, c = cell_lengths
    alpha, beta, gamma = cell_angles
    expand.inputs[1].default_value = grow_iter
    expand.inputs[2].default_value[0] = a
    expand.inputs[2].default_value[1] = b
    expand.inputs[2].default_value[2] = c
    expand.inputs[3].default_value[0] = alpha
    expand.inputs[3].default_value[1] = beta
    expand.inputs[3].default_value[2] = gamma
    nodes_link(nodetree, _input, 0, expand, 0)
    nodes_link(nodetree, expand, 0, _output, 0)

    bpy.ops.object.modifier_apply(modifier='GN_expand')
        
 
