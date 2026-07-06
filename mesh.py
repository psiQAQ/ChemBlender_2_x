import bpy
import bmesh
import numpy as np
import re
from math import dist
from . import _math
from .Chem_data import ELEMENTS_DEFAULT, BONDS_DEFAULT, FUNCTIONAL_GROUPS, IONIC_RADII, SYMOP_OPERATIONS

language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0

def create_object(coll, name, verts, edges, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, edges, faces)
    object = bpy.data.objects.new(name, mesh)
    coll.objects.link(object)
    return object

def copy_mesh_object(coll, mesh, new_name):
    new_mesh = mesh.copy()
    new_obj = bpy.data.objects.new(new_name, new_mesh)
    coll.objects.link(new_obj)
    return new_obj

# 结构参数
def get_link_vert(vert, edge):
    """
    已知边的一个点，获取另一个点
    """
    if edge.verts[0].index == vert.index:
        return edge.verts[1]
    else:
        return edge.verts[0]

def join_objects(obj_list):
    object = obj_list[0]
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in obj_list: obj.select_set(True)
    bpy.ops.object.join()
    return object

def remove_doubles(object):
    bpy.context.view_layer.objects.active = object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.001)
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')

def connect_by_distance(obj, min_dist, max_dist):
    if obj.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    sel_verts = [v for v in bm.verts if v.select]
    
    if len(sel_verts) < 2:
        return False, "至少选中2个点" if language else "At least select 2 vertices"
    
    create_edges = 0

    for i in range(len(sel_verts)):
        v1 = sel_verts[i]
        for j in range(i+1, len(sel_verts)):
            v2 = sel_verts[j]
            dist_ij = dist(v1.co, v2.co)
            if  dist_ij >= min_dist and dist_ij<= max_dist:
                try:
                    bm.edges.new([v1,v2])
                    create_edges += 1
                except:
                    continue
    bmesh.update_edit_mesh(obj.data)
    
    return True, f"已生成 {create_edges} 条边" if language else f"{create_edges} edges have been generated"

# 属性设置
############################################################################################
attr_types = {
    'FLOAT': 'value',
    'INT': 'value',
    'BOOLEAN': 'value',
    'QUATERNION': 'value',
    'FLOAT_COLOR': 'color',
    'FLOAT_VECTOR': 'vector',
}

def get_attr(obj, attr_name, datatype, domain):
    """
    获取对象特定域上的特定属性
    """
    bpy.ops.object.mode_set(mode='OBJECT')
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    attr = obj.data.attributes.get(attr_name)
    count = len(bm.verts) if domain == 'VERT' else len(bm.edges)
    if datatype == 'FLOAT_COLOR':
        m = 4
    elif datatype == 'FLOAT_VECTOR':
        m = 3
    else:
        m = 1
    tot_count = count*m
    seq = [0]*tot_count
    attr.data.foreach_get(attr_types[datatype],seq)
    attr.data.update()

    new_seq = []
    if datatype == 'FLOAT_COLOR':
        for i in range(count):
            new_seq.append(seq[m*i])
            new_seq.append(seq[m*i+1])
            new_seq.append(seq[m*i+2])
            new_seq.append(seq[m*i+3])
    elif datatype == 'FLOAT_VECTOR':
        for i in range(count):
            new_seq.append(seq[m*i])
            new_seq.append(seq[m*i+1])
            new_seq.append(seq[m*i+2])
    else:
        new_seq = seq
    bm.free()
    return new_seq

def get_layer(bm, datatype, domain, name):
    try:
        layers = {
            ('INT', 'VERT'): bm.verts.layers.int,
            ('INT', 'EDGE'): bm.edges.layers.int,
            ('FLOAT', 'VERT'): bm.verts.layers.float,
            ('FLOAT', 'EDGE'): bm.edges.layers.float,
            ('FLOAT_VECTOR', 'VERT'): bm.verts.layers.float_vector,
            ('FLOAT_VECTOR', 'EDGE'): bm.edges.layers.float_vector,
        }
        return layers[(datatype, domain)].get(name) or layers[(datatype, domain)].new(name)
    except KeyError:
        raise ValueError(f"Invalid datatype '{datatype}' or domain '{domain}'. Must be ('INT', 'FLOAT', 'FLOAT_VECTOR') and ('VERT', 'EDGE').")

def get_bond_key(atom_A, atom_B):
    if ELEMENTS_DEFAULT[atom_A][0] <= ELEMENTS_DEFAULT[atom_B][0]:
        bond_key = f'{atom_A},{atom_B}'
    else:
        bond_key = f'{atom_B},{atom_A}'
    if bond_key not in BONDS_DEFAULT: bond_key = 'Default'
    return bond_key

def add_attr(mesh_obj, attr_name, datatype, domain, attr_values):
    """
    给MESH对象特定的域添加特定的属性值.
    """
    attr = mesh_obj.data.attributes.get(attr_name)
    if not attr:
        attr = mesh_obj.data.attributes.new(attr_name, datatype, domain)
    attr.data.foreach_set(attr_types[datatype], attr_values)
    return attr

def add_scaffold_attr(scaffold, ATOMS, AtomicNum, BOND_ORDERS, VDW_R, Radii, RingNum, SiteID, COLORS, Atom_Scale_f, Bond_Scale_f, U_Scale, U_v1, U_v2, U_v3):
    Aromatic = np.full(len(BOND_ORDERS), False)
    attributes = (
        {'name': 'atomic_num',       'type':'INT',      'domain':'POINT',  'values':AtomicNum},
        {'name': 'vdw_radius',       'type':'FLOAT',    'domain':'POINT',  'values':VDW_R},
        {'name': 'radius',           'type':'FLOAT',    'domain':'POINT',  'values':Radii},
        {'name': 'atom_scale_f',     'type':'FLOAT',    'domain':'POINT',  'values':Atom_Scale_f},
        {'name': 'u_scale',          'type':'FLOAT_VECTOR',   'domain':'POINT',  'values':U_Scale},
        {'name': 'u_v1',             'type':'FLOAT_VECTOR',   'domain':'POINT',  'values':U_v1},
        {'name': 'u_v2',             'type':'FLOAT_VECTOR',   'domain':'POINT',  'values':U_v2},
        {'name': 'u_v3',             'type':'FLOAT_VECTOR',   'domain':'POINT',  'values':U_v3},
        #{'name': 'u_rot',            'type':'FLOAT_VECTOR',   'domain':'POINT',  'values':U_Rot},
        #{'name': 'stick_radius',     'type':'FLOAT',    'domain':'POINT',  'values':STICK_R},
        #{'name': 'wire_radius',      'type':'FLOAT',    'domain':'POINT',  'values':WIRE_R},
        {'name': 'bond_order',       'type':'INT',      'domain':'EDGE',   'values':BOND_ORDERS},
        {'name': 'bond_scale_f',     'type':'FLOAT',    'domain':'EDGE',  'values':Bond_Scale_f},
        {'name': 'ring_num',         'type':'INT',      'domain':'EDGE',   'values':RingNum},
        {'name': 'is_aromatic',      'type':'BOOLEAN',   'domain':'EDGE',  'values':Aromatic},
        {'name': 'colour',           'type':'FLOAT_COLOR',    'domain':'POINT',  'values':COLORS},
        {'name': 'siteid',           'type':'INT',         'domain':'POINT',  'values':SiteID},
    ) 
    for attr in attributes:
        add_attr(scaffold, attr['name'], attr['type'], attr['domain'], attr['values'])

def mesh_to_mol_scaffold(obj):
    bpy.ops.object.mode_set(mode='OBJECT')
    atoms_num = len(obj.data.vertices)
    bonds_num = len(obj.data.edges)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.delete(type='ONLY_FACE')
    bpy.ops.object.mode_set(mode='OBJECT')
    ATOMS = ['C']*atoms_num
    AtomicNum = [6]*atoms_num
    VDW_R = [1.70]*atoms_num
    Radii = [0.76]*atoms_num
    COLORS = [0.12,0.12,0.12,1.0]*atoms_num
    SiteID = [0]*atoms_num
    Atom_Scale_f = [1]*atoms_num
    U_Scale = [1.0, 1.0, 1.0]*atoms_num
    #U_Rot = [0.0, 0.0, 0.0]*atoms_num
    U_v1 = [1.0, 0.0, 0.0]*atoms_num
    U_v2 = [0.0, 1.0, 0.0]*atoms_num
    U_v3 = [0.0, 0.0, 1.0]*atoms_num
    BOND_ORDERS = [1]*bonds_num
    Bond_Scale_f = [1]*bonds_num
    RingNum = [0]*bonds_num
    obj['Type'] = 'scaffold'
    obj['Elements'] = list(set(ATOMS))
    add_scaffold_attr(obj, ATOMS, AtomicNum, BOND_ORDERS, VDW_R, Radii, RingNum, SiteID, COLORS, Atom_Scale_f, Bond_Scale_f, U_Scale, U_v1, U_v2, U_v3)


# 设置原子
def set_sel_center_ligand(obj, center, ligand):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    sel_vert_idxs = get_sel_idxs(obj, 'VERT')
    if not sel_vert_idxs:
        return
    if "center" not in obj.data.attributes:
        add_attr(obj, 'center', 'BOOLEAN', 'POINT', [False]*len(obj.data.vertices))
    if "ligand" not in obj.data.attributes:
        add_attr(obj, 'ligand', 'BOOLEAN', 'POINT', [False]*len(obj.data.vertices))
    
    Centers = get_attr(obj, 'center', 'BOOLEAN', 'VERT')
    Ligands = get_attr(obj, 'ligand', 'BOOLEAN', 'VERT')

    for idx in sel_vert_idxs:
        Centers[idx] = center
        Ligands[idx] = ligand
    
    add_attr(obj, 'center', 'BOOLEAN', 'POINT', Centers)
    add_attr(obj, 'ligand', 'BOOLEAN', 'POINT', Ligands)

def set_sel_atoms_attr(obj, atomic_num, scale_f, radius_type, charge, coord_num, center_set, center, ligand, use_custom_color, custom_color, siteid):
    sel_vert_idxs = get_sel_idxs(obj, 'VERT')
    if not sel_vert_idxs:
        return
    
    Atomic_Nums = get_attr(obj, 'atomic_num', 'INT', 'VERT')
    VDW_R = get_attr(obj, 'vdw_radius', 'FLOAT', 'VERT')
    Radii = get_attr(obj, 'radius', 'FLOAT', 'VERT')
    COLORS = get_attr(obj, 'colour', 'FLOAT_COLOR', 'VERT')
    Atom_scales = get_attr(obj, 'atom_scale_f', 'FLOAT', 'VERT')
    SiteID = get_attr(obj, 'siteid', 'INT', 'VERT')
    
    if center_set: set_sel_center_ligand(obj, center, ligand)

    if atomic_num > 0:
        for idx in sel_vert_idxs:
            Atomic_Nums[idx] = atomic_num
            radius, vdw_radius = get_atom_radius(atomic_num, radius_type, charge, coord_num)
            VDW_R[idx] = vdw_radius
            Radii[idx] = radius 
    else:
        for idx in sel_vert_idxs:
            atomic_num = Atomic_Nums[idx]
            radius, vdw_radius = get_atom_radius(atomic_num, radius_type, charge, coord_num)
            VDW_R[idx] = vdw_radius
            Radii[idx] = radius

    for idx in sel_vert_idxs:
        Atom_scales[idx] = scale_f
        SiteID[idx] = siteid
        current_atomic_num = Atomic_Nums[idx]
        elem_symbol = next((k for k, v in ELEMENTS_DEFAULT.items() if v[0] == current_atomic_num), "Dummy")
        default_color = ELEMENTS_DEFAULT[elem_symbol][3]
        if use_custom_color:
            COLORS[4*idx],COLORS[4*idx+1],COLORS[4*idx+2],COLORS[4*idx+3] = custom_color
        else:
            COLORS[4*idx],COLORS[4*idx+1],COLORS[4*idx+2],COLORS[4*idx+3] = default_color
    add_attr(obj, 'atomic_num', 'INT', 'VERT', Atomic_Nums)
    add_attr(obj, 'radius', 'FLOAT', 'VERT', Radii)
    add_attr(obj, 'vdw_radius', 'FLOAT', 'VERT', VDW_R)
    add_attr(obj, 'atom_scale_f', 'FLOAT', 'VERT', Atom_scales)
    add_attr(obj, 'colour', 'FLOAT_COLOR', 'VERT', COLORS)
    add_attr(obj, 'siteid', 'INT', 'VERT', SiteID)
    
    # 根据新的原子调节键长
    if not obj.get('space group'):
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        atomic_num_layer = bm.verts.layers.int.get('atomic_num')
        for vert in bm.verts:
            if vert.select and len(vert.link_edges) == 1:
                edge = vert.link_edges[0]
                if edge.verts[0].index != vert.index:
                    link_vert = edge.verts[0]
                else:
                    link_vert = edge.verts[1]
                atom_id1 = vert[atomic_num_layer]
                atom_id2 = link_vert[atomic_num_layer]
                atom1 = list(ELEMENTS_DEFAULT.keys())[atom_id1]
                atom2 = list(ELEMENTS_DEFAULT.keys())[atom_id2]
                key = get_bond_key(atom1, atom2)
                dir = _math.normalize(np.array(vert.co)-np.array(link_vert.co))
                vert.co = np.array(link_vert.co) + dir * (BONDS_DEFAULT[key][2]+BONDS_DEFAULT[key][3])/2
        bmesh.update_edit_mesh(obj.data)
        bm.free()
    # bpy.ops.object.mode_set(mode='OBJECT')


def get_atom_radius(atomic_num, radius_type, charge, coord_num):
    from rdkit import Chem
    periodic_table = Chem.GetPeriodicTable()
    vdw_radius = periodic_table.GetRvdw(atomic_num)
    covalent_radius = periodic_table.GetRcovalent(atomic_num)
    if radius_type == 'C': charge = 0
    if charge == 0:
        return covalent_radius,vdw_radius
    else:
        try:
            inoic_radius = IONIC_RADII[atomic_num][charge][coord_num][0]
            crystal_radius = IONIC_RADII[atomic_num][charge][coord_num][1]
            if radius_type == 'I':
                return inoic_radius,vdw_radius
            elif radius_type == 'R':
                return crystal_radius,vdw_radius
        except KeyError:
            return covalent_radius,vdw_radius

# 设置键
def set_sel_bonds_attr(obj, bond_order, scale_f, ring_num, dashed_line, toggle_aromatic):
    from rdkit import Chem

    sel_edge_idxs = get_sel_idxs(obj, 'EDGE')
    Bond_Orders  = get_attr(obj, 'bond_order',   'INT',     'EDGE')
    Bond_Scale_f = get_attr(obj, 'bond_scale_f', 'FLOAT',   'EDGE')
    Ring_Nums    = get_attr(obj, 'ring_num',      'INT',     'EDGE')
    Aromatic     = get_attr(obj, 'is_aromatic',   'BOOLEAN', 'EDGE')

    try:
        Dashed_Lines = get_attr(obj, 'dashed', 'BOOLEAN', 'EDGE')
        if Dashed_Lines is None or len(Dashed_Lines) != len(Bond_Orders):
            raise ValueError
    except:
        Dashed_Lines = np.full(len(Bond_Orders), False, dtype=bool)
        add_attr(obj, 'dashed', 'BOOLEAN', 'EDGE', Dashed_Lines)

    # ── Toggle aromatic ────────────────────────────────────────────────────────
    if bond_order == 0 and toggle_aromatic and sel_edge_idxs:

        has_arom_flag = any(
            Bond_Orders[i] == 12 or Aromatic[i]
            for i in sel_edge_idxs
        )

        if has_arom_flag:
            # 芳香 → Kekulé：尝试用 RDKit 获取真实键级，失败则退回 1/2 交替
            kekule_orders = _try_kekulize(obj, sel_edge_idxs, Bond_Orders)
            for i in sel_edge_idxs:
                Bond_Orders[i] = kekule_orders.get(i, 1)
                Aromatic[i]    = False
        else:
            # Kekulé → 芳香：直接标记为 12
            for i in sel_edge_idxs:
                Bond_Orders[i] = 12
                Aromatic[i]    = True

    # ── 直接设置键级 ────────────────────────────────────────────────────────────
    if bond_order > 0:
        for idx in sel_edge_idxs:
            Bond_Orders[idx] = bond_order
            Aromatic[idx]    = (bond_order == 12)

    if ring_num > 0:
        for idx in sel_edge_idxs:
            Ring_Nums[idx] = ring_num

    for idx in sel_edge_idxs:
        Bond_Scale_f[idx] = scale_f
        Dashed_Lines[idx] = dashed_line

    add_attr(obj, 'bond_order',   'INT',     'EDGE', Bond_Orders)
    add_attr(obj, 'bond_scale_f', 'FLOAT',   'EDGE', Bond_Scale_f)
    add_attr(obj, 'ring_num',     'INT',     'EDGE', Ring_Nums)
    add_attr(obj, 'is_aromatic',  'BOOLEAN', 'EDGE', Aromatic)
    add_attr(obj, 'dashed',       'BOOLEAN', 'EDGE', Dashed_Lines)


def _try_kekulize(obj, sel_edge_idxs, Bond_Orders):
    from rdkit import Chem

    result = {}
    try:
        mol, atom_map = scaffold_to_mol(obj)
        # 仅在分子较小或可 Kekulize 时继续
        mol_copy = Chem.RWMol(Chem.Mol(mol))
        Chem.Kekulize(mol_copy, clearAromaticFlags=False)

        for i in sel_edge_idxs:
            edge   = obj.data.edges[i]
            v1, v2 = edge.vertices
            bond   = mol_copy.GetBondBetweenAtoms(atom_map[v1], atom_map[v2])
            if bond:
                result[i] = int(bond.GetBondTypeAsDouble())

    except Exception:
        result = _greedy_kekulize_fallback(obj, sel_edge_idxs)

    return result

def _greedy_kekulize_fallback(obj, sel_edge_idxs):
    sel_set = set(sel_edge_idxs)
    
    edges = {}
    all_verts = set()
    for i in sel_set:
        v1, v2 = obj.data.edges[i].vertices
        edges[i] = (v1, v2)
        all_verts.add(v1)
        all_verts.add(v2)
    
    matched_verts = set()
    result = {}
    
    for i in sel_edge_idxs:  # 遍历顺序影响结果，但保证合法性
        v1, v2 = edges[i]
        if v1 not in matched_verts and v2 not in matched_verts:
            result[i] = 2
            matched_verts.add(v1)
            matched_verts.add(v2)
        else:
            result[i] = 1
    
    return result

# 选择
############################################################################################
def select_all(obj, domain):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type=domain)
    bpy.ops.mesh.select_all(action='SELECT')

def deselect_all(obj):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')

def get_sel_idxs(obj, domain):
    """
    获取所选对象特定域的编号
    """
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    sel_idxs = []
    if domain == 'VERT':
        sel_idxs = [vert.index for vert in bm.verts if vert.select]
    elif domain == 'EDGE':
        sel_idxs = [edge.index for edge in bm.edges if edge.select]
    bmesh.update_edit_mesh(obj.data)
    bm.free()
    bpy.ops.object.mode_set(mode='OBJECT')
    return sel_idxs

def get_cell_parameters(obj):
    def parse_str_array(s):
        return [float(v.strip()) for v in s.split(',')]
    
    length_a, length_b, length_c = parse_str_array(obj['cell lengths'])
    angle_alpha, angle_beta, angle_gamma = parse_str_array(obj['cell angles'])
    space_group = obj['space group'].strip()
    space_group_num = obj['SG No.']
    symop_operations = obj['symops']
    if space_group_num is None:
        try:
            space_group_num = SYMOP_OPERATIONS[space_group][0]
        except KeyError:
            space_group_num = 1
    if symop_operations is None:
        symop_operations = SYMOP_OPERATIONS[space_group][4]
    return (length_a,length_b,length_c,angle_alpha,angle_beta,angle_gamma,space_group,space_group_num,symop_operations)

def get_cell_vectors(obj):
    if not obj or obj.get("cell lengths") is None:
        return None
    a, b, c, alpha, beta, gamma, _, _, _ = get_cell_parameters(obj)
    fracts = [[1,0,0], [0,1,0], [0,0,1]]
    vec_a, vec_b, vec_c = [_math.fract_to_cartn(f, a, b, c, alpha, beta, gamma) for f in fracts]
    return vec_a, vec_b, vec_c

def select_verts(obj, elements):   # 'C', 'H'
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)

    atom_num = get_layer(bm, 'INT', 'VERT', 'atomic_num')
    Elements = list(ELEMENTS_DEFAULT.keys())

    for vert in bm.verts:
        vert[atom_num] = 0 if vert[atom_num] == -1 else vert[atom_num]
        if Elements[vert[atom_num]] in elements:
            vert.select_set(True)

def select_edges(obj, bond_syms):   # ['C','H']
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    atom_num = get_layer(bm, 'INT', 'VERT', 'atomic_num')
    Elements = list(ELEMENTS_DEFAULT.keys())
    for edge in bm.edges:
        atom1 = Elements[edge.verts[0][atom_num]]
        atom2 = Elements[edge.verts[1][atom_num]]
        if [atom1,atom2] in bond_syms or [atom2,atom1] in bond_syms:
            edge.select_set(True)

def select_bond_orders(obj, bond_orders):
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    bond_order = get_layer(bm, 'INT', 'EDGE', 'bond_order')
    for edge in bm.edges:
        if re.sub('[\W]','',f'{edge[bond_order]}') in bond_orders:
            edge.select_set(True)

# 数值计算
############################################################################################
def calc_length():
    """计算边的长度，需在编辑模式下选中边之后执行"""
    if bpy.context.mode == 'EDIT_MESH':
        obj = bpy.context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        locations = []
        for edge in bm.edges:
            if edge.select:
                locations.append(edge.verts[0].co)
                locations.append(edge.verts[1].co)
                break
        if len(locations) == 0: return "N.A."

        pos1 = np.array(locations[0])
        pos2 = np.array(locations[1])
        distance = _math.get_length(pos1-pos2)
        distance = str(float('%.3f' % distance)) + " Å"   # 保留小数点后三位
        return distance

def calc_angle():
    """计算两边的夹角，需在编辑模式下选中两条边后执行"""
    if bpy.context.mode == 'EDIT_MESH':
        obj = bpy.context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        locations = []
        for edge in bm.edges:
            if edge.select:
                locations.append(edge.verts[0].co)
                locations.append(edge.verts[1].co)
                if len(locations) == 4: break
        if len(locations) < 4: return "N.A."

        pos1 = np.array(locations[0])
        pos2 = np.array(locations[1])
        pos3 = np.array(locations[2])
        pos4 = np.array(locations[3])
        epsilon = 0.000001
        if _math.get_length(pos2-pos3) < epsilon or _math.get_length(pos1-pos4) < epsilon:
            vec1 = _math.normalize(pos2-pos1)
            vec2 = _math.normalize(pos3-pos4)
        else:
            vec1 = _math.normalize(pos1-pos2)
            vec2 = _math.normalize(pos3-pos4)
        rad = np.arccos(np.dot(vec1,vec2))
        angle = np.rad2deg(rad)
        angle = str(float('%.2f' % angle)) + "°"   # 保留小数点后三位
        return angle

def get_sel_xyz(obj):
    # in EDIT mode
    bm = bmesh.from_edit_mesh(obj.data)
    sel_xyz = []
    sum_xyz = np.array((0.0, 0.0, 0.0))
    counts = 0
    for vert in bm.verts:
        if vert.select == True:
            sel_xyz.append(vert.co)
            sum_xyz += vert.co
            counts += 1
    avg_xyz = sum_xyz / counts
    return avg_xyz, sel_xyz


# 结构优化 
############################################################################################
def scaffold_to_mol(scaffold):
    from rdkit import Chem
    
    BOND_TYPE_MAP = {
        1: Chem.BondType.SINGLE,
        2: Chem.BondType.DOUBLE,
        3: Chem.BondType.TRIPLE,
        12: Chem.BondType.AROMATIC
    }
    atoms = []
    bonds = []

    # 读取原子和化学键属性
    Atomic_Nums = get_attr(scaffold, 'atomic_num', 'INT', 'VERT')
    Bond_Orders = get_attr(scaffold, 'bond_order', 'INT', 'EDGE')
    Bond_Orders = [bo if bo != 0 else 1 for bo in Bond_Orders]

    unknown = set(Bond_Orders) - BOND_TYPE_MAP.keys()
    if unknown:
        raise ValueError(f"Unknown bond_order: {unknown}")

    rdmol = Chem.RWMol()
    atom_map = {}
    
    for vert, atomic_num in zip(scaffold.data.vertices, Atomic_Nums):
        atom_map[vert.index] = rdmol.AddAtom(Chem.Atom(atomic_num))
    conformer = Chem.Conformer(rdmol.GetNumAtoms())
    for vert in scaffold.data.vertices:
        conformer.SetAtomPosition(atom_map[vert.index],tuple(vert.co))
    rdmol.AddConformer(conformer, assignId = True)

    for edge, bond_order in zip(scaffold.data.edges, Bond_Orders):
        v1,v2 = edge.vertices
        rdmol.AddBond(atom_map[v1], atom_map[v2], BOND_TYPE_MAP[bond_order])
    rdmol.SetProp("_Name", scaffold.name)
    
    mol = rdmol.GetMol()
    Chem.SanitizeMol(mol,sanitizeOps=Chem.SANITIZE_ALL ^ Chem.SANITIZE_KEKULIZE)
    return mol, atom_map


def mol_optimize(scaffold, force_field, addHs, update):
    """
    对选中的分子骨架进行构象优化，并更新顶点坐标
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem
    import numpy as np

    mol, atom_map = scaffold_to_mol(scaffold)
    if addHs: mol = Chem.AddHs(mol)

    # **强制更新原子属性，计算隐含价电子**
    mol.UpdatePropertyCache(strict=False)

    # 生成构象并进行MMFF优化
    conf = mol.GetConformer()
    original_coords = []
    for i in range(mol.GetNumAtoms()):
        pos = conf.GetAtomPosition(i)
        original_coords.append((pos.x, pos.y, pos.z))

    if update:
        try:
            # 优先尝试：标准RDKit构象生成（普通分子正常）
            params = AllChem.ETKDGv3()
            if len(scaffold.data.vertices) > 50:
                params.useRandomCoords = True
            params.numThreads = 1
            status = AllChem.EmbedMolecule(mol, params)
            
            if status != 0:
                AllChem.EmbedMolecule(mol, AllChem.ETKDG())
        except:
            # 失败时（碳纳米管/共轭体系）：安全备用方案
            import random
            new_conf = Chem.Conformer(mol.GetNumAtoms())
            for i in range(mol.GetNumAtoms()):
                x, y, z = original_coords[i]
                dx = (random.random() - 0.5) * 0.7
                dy = (random.random() - 0.5) * 0.7
                dz = (random.random() - 0.5) * 0.7
                new_conf.SetAtomPosition(i, (x+dx, y+dy, z+dz))
            mol.AddConformer(new_conf)
    try:
        if force_field == 'MMFF':
            AllChem.MMFFOptimizeMolecule(mol)
        elif force_field == 'UFF':
            AllChem.UFFOptimizeMolecule(mol)
    except:
        ff = AllChem.UFFGetMoleculeForceField(mol)
        ff.Minimize()

    # 获取优化后的原子坐标
    conf = mol.GetConformer()
    new_positions = {i: np.array(conf.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())}

    # 更新Blender中的顶点坐标
    for vert in scaffold.data.vertices:
        idx = atom_map[vert.index]
        vert.co = new_positions[idx]

def calc_energy(scaffold):
    """
    计算当前构象在MMFF94力场下的分子势能
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol, atom_map = scaffold_to_mol(scaffold)

    mol.UpdatePropertyCache(strict=False)
    try:
        props = AllChem.MMFFGetMoleculeProperties(mol)
        ff = AllChem.MMFFGetMoleculeForceField(mol, props)
        energy = ff.CalcEnergy()
        energy = str(float('%.2f' % energy)) + " kcal/mol"   # 保留小数点后三位
        return energy
    except:
        return "Error"



# 常见元素的原子价规则
#####################
valence_dict = {
    1: 1, # H
    6: 4, # C
    7: 3, # N
    8: 2, # O
    9: 1, # F
    15: 3, # P
    16: 2, # S
    17: 1 # Cl
    }
#####################
def add_functional_groups(scaffold, coords, fg_name, n_carbon):
    from rdkit import Chem
    periodic_table = Chem.GetPeriodicTable()
    coll = bpy.context.collection
    if fg_name == 'n-Chain':
        ATOMS = ['C']*n_carbon
        BONDS = [(i,i+1) for i in range(n_carbon-1)]
        BOND_ORDERS = [1]*(n_carbon-1)
        COLORS = [0.12,0.12,0.12,1.0]*n_carbon
    else:
        ATOMS = FUNCTIONAL_GROUPS[fg_name]['Atoms']
        BONDS = FUNCTIONAL_GROUPS[fg_name]['Bonds']
        BOND_ORDERS = FUNCTIONAL_GROUPS[fg_name]['Bond_Orders']
        COLORS = FUNCTIONAL_GROUPS[fg_name]['COLORS']
    new_struct = create_object(coll, 'new_molecule', coords, BONDS, [])
    AtomicNum = [ELEMENTS_DEFAULT[atom][0] for atom in ATOMS]
    Atom_Scale_f = [1]*len(ATOMS)
    U_Scale = [1.0, 1.0, 1.0]*len(ATOMS)
    #U_Rot = [0.0, 0.0, 0.0]*len(ATOMS)
    U_v1 = [1.0, 0.0, 0.0]*len(ATOMS)
    U_v2 = [0.0, 1.0, 0.0]*len(ATOMS)
    U_v3 = [0.0, 0.0, 1.0]*len(ATOMS)
    Bond_Scale_f = [1]*len(BONDS)
    SiteID = [0]*len(ATOMS)
    VDW_R = [periodic_table.GetRvdw(atomic_num) for atomic_num in AtomicNum]
    Radii = [periodic_table.GetRcovalent(atomic_num) for atomic_num in AtomicNum]
    RingNum = [0]*len(BONDS)
    add_scaffold_attr(new_struct, ATOMS, AtomicNum, BOND_ORDERS, VDW_R, Radii, RingNum, SiteID, COLORS, Atom_Scale_f, Bond_Scale_f, U_Scale, U_v1, U_v2, U_v3)
    new_scaffold = join_objects([scaffold, new_struct])
    remove_doubles(new_scaffold)

def add_new_scaffold(scaffold, new_verts):
    bm = bmesh.from_edit_mesh(scaffold.data)
    old_vert_count = len(bm.verts)
    old_edge_count = len(bm.edges)
    sum = 0
    for new_vert in new_verts:
        index = new_vert[0]
        new_pos = new_vert[1]
        for pos in new_pos:
            sum += 1
            new_vert = bm.verts.new(pos)
            bm.verts.ensure_lookup_table()
            new_edge = bm.edges.new([new_vert, bm.verts[index]])
    bmesh.update_edit_mesh(scaffold.data)
    return old_vert_count, old_edge_count


def set_new_scaffold_attr(scaffold, old_vert_count, old_edge_count, atomic_num, bond_order):
    from rdkit import Chem
    periodic_table = Chem.GetPeriodicTable()

    AtomicNum = get_attr(scaffold, 'atomic_num', 'INT', 'VERT')
    BOND_ORDERS = get_attr(scaffold, 'bond_order', 'INT', 'EDGE')
    RingNum = get_attr(scaffold, 'ring_num', 'INT', 'EDGE')
    VDW_R = get_attr(scaffold, 'vdw_radius', 'FLOAT', 'VERT')
    Radii = get_attr(scaffold, 'radius', 'FLOAT', 'VERT')
    COLORS = get_attr(scaffold, 'colour', 'FLOAT_COLOR', 'VERT')
    SiteID = get_attr(scaffold, 'siteid', 'INT', 'VERT')
    Atom_Scale_f = get_attr(scaffold, 'atom_scale_f', 'FLOAT', 'VERT')
    Bond_Scale_f = get_attr(scaffold, 'bond_scale_f','FLOAT','EDGE')
    U_Scale = get_attr(scaffold, 'u_scale', 'FLOAT_VECTOR', 'VERT')
    #U_Rot = get_attr(scaffold, 'u_rot', 'FLOAT_VECTOR', 'VERT')
    U_v1 = get_attr(scaffold, 'u_v1', 'FLOAT_VECTOR', 'VERT')
    U_v2 = get_attr(scaffold, 'u_v2', 'FLOAT_VECTOR', 'VERT')
    U_v3 = get_attr(scaffold, 'u_v3', 'FLOAT_VECTOR', 'VERT')

    num_new_verts = len(scaffold.data.vertices) - old_vert_count
    num_new_edges = len(scaffold.data.edges) - old_edge_count

    h_vdw = periodic_table.GetRvdw(atomic_num)
    h_cov = periodic_table.GetRcovalent(atomic_num)
    color = list(list(ELEMENTS_DEFAULT.items())[atomic_num][1][3])

    AtomicNum = AtomicNum[:old_vert_count] + [atomic_num] * num_new_verts
    VDW_R = VDW_R[:old_vert_count] + [h_vdw] * num_new_verts
    Radii = Radii[:old_vert_count] + [h_cov] * num_new_verts
    Atom_Scale_f  = Atom_Scale_f[:old_vert_count]  + [1.0] * num_new_verts
    U_Scale = U_Scale[:old_vert_count*3] + [1.0, 1.0, 1.0] * num_new_verts
    #U_Rot = U_Rot[:old_vert_count*3] + [0.0, 0.0, 0.0] * num_new_verts
    U_v1 = U_v1[:old_vert_count*3] + [1.0, 0.0, 0.0] * num_new_verts
    U_v2 = U_v2[:old_vert_count*3] + [0.0, 1.0, 0.0] * num_new_verts
    U_v3 = U_v3[:old_vert_count*3] + [0.0, 0.0, 1.0] * num_new_verts
    COLORS  = COLORS[:old_vert_count*4]  + color * num_new_verts
    SiteID = SiteID[:old_vert_count] + [0] * num_new_verts
    BOND_ORDERS = BOND_ORDERS[:old_edge_count] + [bond_order] * num_new_edges
    RingNum = RingNum[:old_edge_count] + [0] * num_new_edges
    Bond_Scale_f  = Bond_Scale_f[:old_edge_count]  + [1.0] * num_new_edges

    #AtomicNum = [atomic_num if x == 0 else x for x in AtomicNum]
    #BOND_ORDERS = [bond_order if x == 0 else x for x in BOND_ORDERS]
    #VDW_R = [periodic_table.GetRvdw(atomic_num) if x == 0 else x for x in VDW_R]
    #Radii = [periodic_table.GetRcovalent(atomic_num) if x == 0 else x for x in Radii]
    ATOMS = [list(ELEMENTS_DEFAULT.keys())[atomic_num] for atomic_num in AtomicNum]
    add_scaffold_attr(scaffold, ATOMS, AtomicNum, BOND_ORDERS, VDW_R, Radii, RingNum, SiteID, COLORS, Atom_Scale_f, Bond_Scale_f, U_Scale, U_v1, U_v2, U_v3)

def add_hydrogens(scaffold):
    """
    给分子骨架结构补全氢原子，确保价态饱和，并考虑空间构象
    """
    # 读取原子和化学键属性
    Atomic_Nums = get_attr(scaffold, 'atomic_num', 'INT', 'VERT')
    Bond_Orders = get_attr(scaffold, 'bond_order', 'INT', 'EDGE')

    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.new()
    bm.from_mesh(scaffold.data)
    
    # 计算每个原子的成键情况
    atom_links = {v.index: {
        "bond_count": 0,
        "bond_order_sum": 0,
        "neighbors": []
    } for v in bm.verts}
    
    for edge in bm.edges:
        v1,v2 = edge.verts
        bond_order = Bond_Orders[edge.index]  # 读取键级
        if bond_order == 12: bond_order = 1.5
        atom_links[v1.index]["bond_count"] += 1
        atom_links[v1.index]["bond_order_sum"] += bond_order
        atom_links[v1.index]["neighbors"].append(v2)

        atom_links[v2.index]["bond_count"] += 1
        atom_links[v2.index]["bond_order_sum"] += bond_order
        atom_links[v2.index]["neighbors"].append(v1)
    
    # 计算每个顶点处新添加的氢原子位置
    new_verts = []
    for v in bm.verts:
        atomic_num = Atomic_Nums[v.index]
        if atomic_num not in valence_dict:
            continue   # 跳过不需要补氢的原子
        max_valence = valence_dict[atomic_num]
        current_valence = atom_links[v.index]["bond_order_sum"]
        num_hydrogens = max_valence - current_valence
        if num_hydrogens <= 0:
            continue  # 价键已满，无需补氢

        bond_count = atom_links[v.index]["bond_count"]
        hybridization = 3 + bond_count - atom_links[v.index]["bond_order_sum"]   # sp:1, sp2:2, sp3:3
        new_H_pos = new_hydrogens(v, bond_count, hybridization, Atomic_Nums)
        new_verts.append((v.index, new_H_pos))

    # 添加氢原子顶点和化学键
    old_vert_count, old_edge_count = add_new_scaffold(scaffold, new_verts)
    
    # 设置新的原子和键属性
    set_new_scaffold_attr(scaffold, old_vert_count, old_edge_count, atomic_num=1, bond_order=1)
    # bpy.ops.object.mode_set(mode='OBJECT')


def new_hydrogens(vert, bond_count, hybridization, Atomic_Nums):
    """
    根据已有的键连接和杂化类型，计算剩余的成键方向
    """
    new_directions = []
    new_H_pos = []
    deflection_angle = 0 if bond_count == hybridization else 54.75
    branches = valence_dict[Atomic_Nums[vert.index]]
    if bond_count == 0:  # 单独的点
        if branches == 1:
            new_directions.append((1,0,0))
        elif branches == 2:
            new_directions.append((0.5, 0.866, 0.0))
            new_directions.append((0.5, -0.866, 0.0))
        elif branches == 3:
            new_directions.append((0.5, 0.866, 0.0))
            new_directions.append((0.5, -0.866, 0.0))
            new_directions.append((-1.0, 0.0, 0.0))
        else:
            new_directions.append((0.57735, 0.57735, 0.57735))
            new_directions.append((0.57735, -0.57735, 0.57735))
            new_directions.append((-0.57735, 0.57735, 0.57735))
            new_directions.append((-0.57735, -0.57735, 0.57735))
    else:
        new_directions = _math.branches_dir(vert, hybridization-bond_count+branches-3, deflection_angle)[0]

    for direction in new_directions:
        new_H_pos.append(np.array(vert.co) + 1.09*np.array(direction))

    return new_H_pos
    
def para_branches(scaffold, atomic_num, branches, calc_SA, default_angle, rotate_angle, deflection_angle):
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(scaffold.data)
    atomic_num_layer = bm.verts.layers.int.get('atomic_num')
    bond_order_layer = bm.edges.layers.int.get('bond_order')
    new_verts = []
    for vert in bm.verts:
        new_coords = []
        if vert.select == True:
            origin_atomic_num = vert[atomic_num_layer]
            origin_atom = list(ELEMENTS_DEFAULT.keys())[origin_atomic_num]
            new_atom = list(ELEMENTS_DEFAULT.keys())[atomic_num]
            bond_key = get_bond_key(origin_atom, new_atom)
            bond_length = (BONDS_DEFAULT[bond_key][2]+BONDS_DEFAULT[bond_key][3])/2
            bank, pitch, heading = _math.vert_hpb(vert, rotate_angle=0)
            saturation = 0
            for edge in vert.link_edges: saturation += edge[bond_order_layer]
            if calc_SA: branches = abs(ELEMENTS_DEFAULT[origin_atom][8])-saturation
            if default_angle:
                rotate_angle = 90
                deflection_angle = 54.735 if branches == 2 else 0
                #if atomic_num in [8,16] and branches == 1:   # O,S atom
                #    rotate_angle = 0
                #    deflection_angle = 60
            banks = _math.branches_dir(vert, branches, deflection_angle)[0]
            for vec in banks:
                vec = _math.rotate_vec(vec, bank, rotate_angle*3.1416/180)
                #if atomic_num == 7: # N atom
                #    axis = pitch if branches == 1 else heading
                #    vec = _math.rotate_vec(vec, axis, 15*3.1416/180)
                new_coord = np.array(vert.co)+vec*bond_length
                new_coords.append(new_coord)
            new_verts.append((vert.index, new_coords))
    bpy.ops.mesh.select_all(action='DESELECT')
    return new_verts

def unit_cell_edges(obj_name, coll_mol, length_a, length_b, length_c, angle_alpha, angle_beta, angle_gamma, space_group, space_group_num, symop_operations):
    fract_corners_xyz = [[0,0,0], [1,0,0], [1,1,0], [0,1,0], [0,0,1], [1,0,1], [1,1,1], [0,1,1]]
    cartn_corners = [_math.fract_to_cartn(corner, length_a, length_b, length_c, 
                                            angle_alpha, angle_beta, angle_gamma) for corner in fract_corners_xyz]
    cell_edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    mesh = bpy.data.meshes.new('cell_edges_'+obj_name)
    new_obj = bpy.data.objects.new(mesh.name, mesh)
    coll_mol.objects.link(new_obj)
    mesh.from_pydata(cartn_corners,cell_edges,[])
    bpy.context.view_layer.objects.active = new_obj
    new_obj.select_set(True)

    # store basic infomation of crystal cell in customic properties of Cell_Edges object
    new_obj['Type'] = 'unit_cell'
    new_obj['cell lengths'] = f'{length_a},{length_b},{length_c}'
    new_obj['cell angles'] = f'{angle_alpha},{angle_beta},{angle_gamma}'
    new_obj['space group'] = space_group
    new_obj['SG No.'] = space_group_num
    new_obj['symops'] = symop_operations
    '''bpy.ops.object.convert(target='CURVE')
    bpy.context.object.data.bevel_depth = 0.01
    bpy.ops.object.select_all(action='DESELECT')'''
    return new_obj