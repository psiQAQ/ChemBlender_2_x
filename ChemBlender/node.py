import  bpy
import os
from .Chem_data import ELEMENTS_DEFAULT
# Get the plugin directory path
dir_path = os.path.dirname(__file__)
language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0
file = "Chem_Nodes.blend" if language else "Chem_Nodes_En.blend"
filepath = os.path.join(dir_path, file)
_STRUCTURE_BALL_STICK_MODIFIER = "ChemBlender Ball and Stick"
_STRUCTURE_BALL_STICK_CONTRACT = "structure_ball_stick_v1"
_PERIODIC_CELL_MODIFIER = "ChemBlender Periodic Cell"
_PERIODIC_CELL_CONTRACT = "periodic_cell_edges_v1"
_PERIODIC_ADP_MODIFIER = "ChemBlender Thermal Ellipsoids"
_PERIODIC_ADP_CONTRACT = "periodic_thermal_ellipsoid_v1"
_NODE_CONTRACT_VERSION = 1
_LEGACY_SUPERCELL_CONTRACT = "legacy_supercell_wrapper_v1"
_LEGACY_SUPERCELL_ASSET_CONTRACT = "legacy_supercell_asset_v1"
_LEGACY_POLYHEDRA_CONTRACT = "legacy_coord_polyhedra_wrapper_v1"
_LEGACY_POLYHEDRA_ASSET_CONTRACT = "legacy_coord_polyhedra_asset_v1"
_LEGACY_POLYHEDRA_REMOVE_CONTRACT = "legacy_remove_coplanar_edges_v1"
_LEGACY_ATOMIC_SELECTION_CONTRACT = "legacy_atomic_selection_v1"
_PERIODIC_OCCUPANCY_MODIFIER = "ChemBlender Site Occupancy"
_PERIODIC_OCCUPANCY_CONTRACT = "periodic_site_occupancy_v1"
_LEGACY_BALL_STICK_CONTRACT = "legacy_ball_stick_wrapper_v1"
_LEGACY_ATTRIBUTE_ASSET_CONTRACT = "legacy_atom_attributes_asset_v1"
_LEGACY_MOLECULE_ASSET_CONTRACT = "legacy_ball_stick_asset_v1"
_LEGACY_MATERIAL_ASSET_CONTRACT = "legacy_molecule_material_asset_v1"
_LEGACY_CELL_EDGES_CONTRACT = "legacy_cell_edges_wrapper_v1"
_LEGACY_EDGE_SWEEP_ASSET_CONTRACT = "legacy_cell_edge_sweep_asset_v1"
_LEGACY_AXES_ASSET_CONTRACT = "legacy_cell_axes_asset_v1"

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
    for owner in (nodetree.node_group, nodetree):
        if owner.get("cbq_contract") is not None and not _validate_contract(
            owner,
            _LEGACY_BALL_STICK_CONTRACT,
        ):
            raise RuntimeError("incompatible legacy ball-and-stick wrapper")
    attribute = "CH_添加分子属性" if language else "CH_Add Attributes"
    molecule = "CH_分子球棍模型" if language else "CH_Ball and Stick"
    material = "CH_添加分子材质" if language else "CH_Add Material"
    _require_or_append_legacy_groups(
        (
            (attribute, _LEGACY_ATTRIBUTE_ASSET_CONTRACT),
            (molecule, _LEGACY_MOLECULE_ASSET_CONTRACT),
            (material, _LEGACY_MATERIAL_ASSET_CONTRACT),
        )
    )
    _input, _output = set_io_nodes(nodetree, (a,b), (a+800,b))
    _add_mol_attr = add_node_group(nodetree, attribute, (a+200,0))
    _ball_stick = add_node_group(nodetree, molecule, (a+400,0))
    _ball_stick.inputs[6].default_value = 0.5
    _add_material = add_node_group(nodetree, material, (a+600,0))
    nodes_link(nodetree, _input, 0, _add_mol_attr, 0)
    nodes_link(nodetree, _add_mol_attr, 0, _ball_stick, 0)
    nodes_link(nodetree, _ball_stick, 0, _add_material, 0)
    nodes_link(nodetree, _add_material, 0, _output, 0)
    _stamp_contract(nodetree.node_group, _LEGACY_BALL_STICK_CONTRACT)
    _stamp_contract(nodetree, _LEGACY_BALL_STICK_CONTRACT)


def _require_mesh_object(obj):
    if not isinstance(obj, bpy.types.Object) or obj.type != "MESH":
        raise TypeError("obj must be a Blender Mesh object")


def _stamp_contract(owner, contract):
    owner["cbq_contract"] = contract
    owner["cbq_contract_version"] = _NODE_CONTRACT_VERSION


def _validate_contract(owner, contract):
    return (
        owner.get("cbq_contract") == contract
        and owner.get("cbq_contract_version") == _NODE_CONTRACT_VERSION
    )


def _require_or_append_legacy_groups(contracts):
    missing = []
    for name, contract in contracts:
        group = bpy.data.node_groups.get(name)
        if group is None:
            missing.append((name, contract))
        elif not _validate_contract(group, contract):
            raise RuntimeError(f"incompatible node group already uses {name}")
    for name, _contract in missing:
        if bpy.data.node_groups.get(name) is None:
            append(name)
    for name, contract in missing:
        _stamp_contract(bpy.data.node_groups[name], contract)


def _ensure_generated_modifier(obj, name, contract, build):
    _require_mesh_object(obj)
    modifier = obj.modifiers.get(name)
    if modifier is not None:
        if (
            modifier.type != "NODES"
            or modifier.node_group is None
            or not _validate_contract(modifier.node_group, contract)
            or not _validate_contract(modifier, contract)
        ):
            raise RuntimeError(f"incompatible modifier already uses {name}")
        return modifier
    modifier = obj.modifiers.new(name, "NODES")
    group = bpy.data.node_groups.new(
        f"{obj.name} {name} Nodes",
        "GeometryNodeTree",
    )
    try:
        group.is_modifier = True
        group.interface.new_socket(
            name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
        )
        group.interface.new_socket(
            name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        group.nodes.new("NodeGroupInput")
        group.nodes.new("NodeGroupOutput")
        modifier.node_group = group
        build(modifier)
        _stamp_contract(group, contract)
        _stamp_contract(modifier, contract)
        return modifier
    except BaseException as error:
        from .views.structure import _run_cleanup

        error = _run_cleanup(
            error,
            f"{name} modifier cleanup failed",
            lambda: obj.modifiers.remove(modifier),
        )
        if group.users == 0:
            error = _run_cleanup(
                error,
                f"{name} node-group cleanup failed",
                lambda: bpy.data.node_groups.remove(group),
            )
        raise error


def ensure_structure_ball_stick_modifier(obj):
    return _ensure_generated_modifier(
        obj,
        _STRUCTURE_BALL_STICK_MODIFIER,
        _STRUCTURE_BALL_STICK_CONTRACT,
        Ball_Stick_nodetree,
    )


def _periodic_cell_nodetree(nodetree):
    _input, _output = set_io_nodes(nodetree, (0, 0), (600, 0))
    mesh_to_curve = add_node(
        nodetree,
        "GeometryNodeMeshToCurve",
        (180, 0),
        "",
    )
    profile = add_node(
        nodetree,
        "GeometryNodeCurvePrimitiveCircle",
        (180, -180),
        "",
    )
    profile.inputs["Resolution"].default_value = 8
    profile.inputs["Radius"].default_value = 0.02
    curve_to_mesh = add_node(
        nodetree,
        "GeometryNodeCurveToMesh",
        (400, 0),
        "",
    )
    nodes_link(nodetree, _input, 0, mesh_to_curve, 0)
    nodes_link(nodetree, mesh_to_curve, 0, curve_to_mesh, 0)
    nodes_link(nodetree, profile, 0, curve_to_mesh, 1)
    nodes_link(nodetree, curve_to_mesh, 0, _output, 0)


def ensure_periodic_cell_modifier(obj):
    return _ensure_generated_modifier(
        obj,
        _PERIODIC_CELL_MODIFIER,
        _PERIODIC_CELL_CONTRACT,
        _periodic_cell_nodetree,
    )


def _periodic_adp_nodetree(nodetree):
    _input, _output = set_io_nodes(nodetree, (0, 0), (800, 0))
    points = add_node(
        nodetree,
        "GeometryNodeMeshToPoints",
        (180, 0),
        "",
    )
    points.mode = "VERTICES"
    sphere = add_node(
        nodetree,
        "GeometryNodeMeshIcoSphere",
        (180, -220),
        "",
    )
    sphere.inputs["Radius"].default_value = 1.0
    sphere.inputs["Subdivisions"].default_value = 2
    scale = add_node(
        nodetree,
        "GeometryNodeInputNamedAttribute",
        (380, -120),
        "",
    )
    scale.data_type = "FLOAT_VECTOR"
    scale.inputs["Name"].default_value = "cbq_adp_scale"
    rotation = add_node(
        nodetree,
        "GeometryNodeInputNamedAttribute",
        (380, -280),
        "",
    )
    rotation.data_type = "FLOAT_VECTOR"
    rotation.inputs["Name"].default_value = "cbq_adp_rotation"
    instances = add_node(
        nodetree,
        "GeometryNodeInstanceOnPoints",
        (600, 0),
        "",
    )
    realized = add_node(
        nodetree,
        "GeometryNodeRealizeInstances",
        (760, 0),
        "",
    )
    nodes_link(nodetree, _input, 0, points, 0)
    nodes_link(nodetree, points, 0, instances, 0)
    nodes_link(nodetree, sphere, 0, instances, 2)
    nodes_link(nodetree, rotation, 0, instances, 5)
    nodes_link(nodetree, scale, 0, instances, 6)
    nodes_link(nodetree, instances, 0, realized, 0)
    nodes_link(nodetree, realized, 0, _output, 0)


def ensure_periodic_adp_modifier(obj):
    return _ensure_generated_modifier(
        obj,
        _PERIODIC_ADP_MODIFIER,
        _PERIODIC_ADP_CONTRACT,
        _periodic_adp_nodetree,
    )


def _periodic_occupancy_nodetree(nodetree, mode, material):
    _input, _output = set_io_nodes(nodetree, (0, 0), (900, 0))
    if mode == "pie":
        nodes_link(nodetree, _input, 0, _output, 0)
        return
    points = add_node(
        nodetree,
        "GeometryNodeMeshToPoints",
        (180, 0),
        "",
    )
    points.mode = "VERTICES"
    sphere = add_node(
        nodetree,
        "GeometryNodeMeshIcoSphere",
        (180, -220),
        "",
    )
    sphere.inputs["Radius"].default_value = 1.0
    sphere.inputs["Subdivisions"].default_value = 2
    scale = add_node(
        nodetree,
        "GeometryNodeInputNamedAttribute",
        (380, -160),
        "",
    )
    scale.data_type = "FLOAT_VECTOR"
    scale.inputs["Name"].default_value = "cbq_occupancy_scale"
    instances = add_node(
        nodetree,
        "GeometryNodeInstanceOnPoints",
        (560, 0),
        "",
    )
    realized = add_node(
        nodetree,
        "GeometryNodeRealizeInstances",
        (710, 0),
        "",
    )
    set_material = add_node(
        nodetree,
        "GeometryNodeSetMaterial",
        (710, -140),
        "",
    )
    set_material.inputs["Material"].default_value = material
    nodes_link(nodetree, _input, 0, points, 0)
    nodes_link(nodetree, points, 0, instances, 0)
    nodes_link(nodetree, sphere, 0, instances, 2)
    nodes_link(nodetree, scale, 0, instances, 6)
    nodes_link(nodetree, instances, 0, realized, 0)
    nodes_link(nodetree, realized, 0, set_material, 0)
    nodes_link(nodetree, set_material, 0, _output, 0)


def ensure_periodic_occupancy_modifier(obj, mode, material):
    if mode not in {"opacity", "pie", "split_site"}:
        raise ValueError("occupancy node mode must replace source atoms")
    existing = obj.modifiers.get(_PERIODIC_OCCUPANCY_MODIFIER)
    if existing is not None and (
        existing.get("cbq_occupancy_mode") != mode
        or existing.get("cbq_material_name") != material.name
        or existing.node_group is None
        or existing.node_group.get("cbq_occupancy_mode") != mode
        or existing.node_group.get("cbq_material_name") != material.name
    ):
        raise RuntimeError(
            f"incompatible modifier already uses {_PERIODIC_OCCUPANCY_MODIFIER}"
        )
    modifier = _ensure_generated_modifier(
        obj,
        _PERIODIC_OCCUPANCY_MODIFIER,
        _PERIODIC_OCCUPANCY_CONTRACT,
        lambda nodetree: _periodic_occupancy_nodetree(
            nodetree,
            mode,
            material,
        ),
    )
    if existing is None:
        modifier["cbq_occupancy_mode"] = mode
        modifier["cbq_material_name"] = material.name
        modifier.node_group["cbq_occupancy_mode"] = mode
        modifier.node_group["cbq_material_name"] = material.name
    return modifier


def preflight_legacy_supercell_contract():
    name = "CH_超胞" if language else "CH_Supercell"
    group = bpy.data.node_groups.get(name)
    if group is not None and not _validate_contract(
        group,
        _LEGACY_SUPERCELL_ASSET_CONTRACT,
    ):
        raise RuntimeError(f"incompatible node group already uses {name}")



def Supercell(scaffold, nodetree, full_cell_cutoff):
    cell_lengths = tuple(map(float,scaffold['cell lengths'].strip("").split(',')))
    cell_angles = tuple(map(float,scaffold['cell angles'].strip("").split(',')))
    preflight_legacy_supercell_contract()
    if (
        nodetree.node_group.get("cbq_contract") is not None
        and not _validate_contract(
            nodetree.node_group,
            _LEGACY_SUPERCELL_CONTRACT,
        )
    ):
        raise RuntimeError("incompatible legacy supercell wrapper")
    if (
        nodetree.get("cbq_contract") is not None
        and not _validate_contract(nodetree, _LEGACY_SUPERCELL_CONTRACT)
    ):
        raise RuntimeError("incompatible legacy supercell modifier")
    a,b = (0,0)
    _input, _output = set_io_nodes(nodetree, (a,b), (a+400,b))
    name1 = "负向边界" if language else "Negative Boundaries"
    name2 = "正向边界" if language else "Positive Boundaries"
    nodetree.node_group.interface.new_socket(name=name1,in_out='INPUT',socket_type='NodeSocketVector')
    nodetree.node_group.interface.new_socket(name=name2,in_out='INPUT',socket_type='NodeSocketVector')
    supercell = "CH_超胞" if language else "CH_Supercell"
    _require_or_append_legacy_groups(
        ((supercell, _LEGACY_SUPERCELL_ASSET_CONTRACT),)
    )
    _supercell = add_node_group(nodetree, supercell, (a+200,0))
    _supercell.inputs[1].default_value = cell_lengths
    _supercell.inputs[2].default_value = cell_angles
    _supercell.inputs[5].default_value = full_cell_cutoff
    nodes_link(nodetree, _input, 0, _supercell, 0)
    nodes_link(nodetree, _input, 1, _supercell, 3)
    nodes_link(nodetree, _input, 2, _supercell, 4)
    nodes_link(nodetree, _supercell, 0, _output, 0)
    _stamp_contract(
        nodetree.node_group,
        _LEGACY_SUPERCELL_CONTRACT,
    )
    _stamp_contract(nodetree, _LEGACY_SUPERCELL_CONTRACT)


def Cell_Edges(nodetree, cell_lengths, cell_angles):
    a,b=(0,0)
    group = nodetree.node_group
    sweep_edge_name = "CH_边线扫描" if language else "CH_Edge Sweep"
    axes_arrows_name = "CH_晶轴箭头" if language else "CH_Axes Arrows"
    if (
        group.get("cbq_contract") is not None
        and not _validate_contract(group, _LEGACY_CELL_EDGES_CONTRACT)
    ):
        raise RuntimeError("incompatible legacy cell-edges wrapper")
    if (
        nodetree.get("cbq_contract") is not None
        and not _validate_contract(nodetree, _LEGACY_CELL_EDGES_CONTRACT)
    ):
        raise RuntimeError("incompatible legacy cell-edges modifier")
    _require_or_append_legacy_groups(
        (
            (sweep_edge_name, _LEGACY_EDGE_SWEEP_ASSET_CONTRACT),
            (axes_arrows_name, _LEGACY_AXES_ASSET_CONTRACT),
        )
    )
    _input, _output = set_io_nodes(nodetree, (a,b), (a+600,b))
    a, b, c = cell_lengths
    alpha, beta, gamma = cell_angles

    _joingeo = add_node(nodetree,'GeometryNodeJoinGeometry', (a+400,0), '')
    _sweep_edge = add_node_group(nodetree, sweep_edge_name, (a+200,200))
    _axes_arrows = add_node_group(nodetree, axes_arrows_name,(a+200,-50))
    _sweep_edge.inputs[1].default_value = 0.01
    _axes_arrows.inputs[3].default_value[0] = a
    _axes_arrows.inputs[3].default_value[1] = b
    _axes_arrows.inputs[3].default_value[2] = c
    _axes_arrows.inputs[4].default_value[0] = alpha
    _axes_arrows.inputs[4].default_value[1] = beta
    _axes_arrows.inputs[4].default_value[2] = gamma

    nodes_link(nodetree, _input, 0, _sweep_edge, 0)
    nodes_link(nodetree, _axes_arrows, 0, _joingeo, 0)
    nodes_link(nodetree, _sweep_edge, 0, _joingeo, 0)
    nodes_link(nodetree, _joingeo, 0, _output, 0)
    _stamp_contract(group, _LEGACY_CELL_EDGES_CONTRACT)
    _stamp_contract(nodetree, _LEGACY_CELL_EDGES_CONTRACT)



def CoordPolyhedra(nodetree, set_mode, append_mode, RMin, RMax, center_nums, ligand_nums):
    group = nodetree.node_group
    coordpoly_name = "CH_配位多面体" if language else "CH_Coord Polyhedra"
    remove_name = "CH_移除共面边" if language else "CH_Remove Coplanar Edges"
    atomicnum_sel = "CH_原子序数选中项" if language else "CH_AtomicNum Selection"
    material_name = "CH_添加分子材质" if language else "CH_Add Material"
    if not (
        group.get("cbq_contract") is None
        or (
            group.get("cbq_contract") == _LEGACY_BALL_STICK_CONTRACT
            and group.get("cbq_contract_version") == _NODE_CONTRACT_VERSION
        )
        or _validate_contract(group, _LEGACY_POLYHEDRA_CONTRACT)
    ):
        raise RuntimeError("incompatible legacy coordination-polyhedra wrapper")
    if not (
        nodetree.get("cbq_contract") is None
        or (
            nodetree.get("cbq_contract") == _LEGACY_BALL_STICK_CONTRACT
            and nodetree.get("cbq_contract_version") == _NODE_CONTRACT_VERSION
        )
        or _validate_contract(nodetree, _LEGACY_POLYHEDRA_CONTRACT)
    ):
        raise RuntimeError("incompatible legacy coordination-polyhedra modifier")
    _require_or_append_legacy_groups(
        (
            (coordpoly_name, _LEGACY_POLYHEDRA_ASSET_CONTRACT),
            (remove_name, _LEGACY_POLYHEDRA_REMOVE_CONTRACT),
            (atomicnum_sel, _LEGACY_ATOMIC_SELECTION_CONTRACT),
        )
    )
    a,b=(0,0)
    _input, _output = set_io_nodes(nodetree, (a,b), (a+1000,b))

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
    if set_mode == '1':
        _coordpoly.inputs[1].default_value = '自定义' if language else 'Customize'
    #if append_mode:
        _center_sel = add_node_group(nodetree, atomicnum_sel, (-200,y_pos))
        _ligand_sel = add_node_group(nodetree, atomicnum_sel, (0,y_pos))
        for i,center_num in enumerate(center_nums):
            try:
                _center_sel.inputs[i].default_value = center_num
            except Exception as e:
                pass
        for i,ligand_num in enumerate(ligand_nums):
            try:
                _ligand_sel.inputs[i].default_value = ligand_num
            except Exception as e:
                pass
        nodes_link(nodetree, _center_sel, 0, _coordpoly, 2)
        nodes_link(nodetree, _ligand_sel, 0, _coordpoly, 3)
    _coordpoly.inputs[4].default_value = RMin
    _coordpoly.inputs[5].default_value = RMax
    _remove = add_node_group(nodetree, remove_name, (450,y_pos))

    nodes_link(nodetree, _input, 0, _coordpoly, 0)
    nodes_link(nodetree, _coordpoly, 0, _remove, 0)
    nodes_link(nodetree, _remove, 0, _joingeo, 0)
    _stamp_contract(group, _LEGACY_POLYHEDRA_CONTRACT)
    _stamp_contract(nodetree, _LEGACY_POLYHEDRA_CONTRACT)


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
        
 
