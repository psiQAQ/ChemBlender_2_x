import bpy
import numpy as np
from .Chem_data import ELEMENTS_DEFAULT, BONDS_DEFAULT
from bpy.props import IntProperty, FloatProperty, StringProperty, CollectionProperty

# generate BONDS list from pure ATOMS list(.xyz and some .pdb/.cif format),
# judging whether a bond is formed based on the distance between atoms.
def add_BONDS(ATOMS, COORDS, factor):
    ATOMS = ["H" if elem.upper() in ("D", "T") else elem for elem in ATOMS]
    n_atoms = len(ATOMS)
    if n_atoms < 2:
        return [], []

    coords = np.asarray(COORDS, dtype=np.float32)
    atoms = np.array(ATOMS)
    elem_order = {elem: info[0] for elem, info in ELEMENTS_DEFAULT.items()}

    def get_threshold(a1, a2):
        if elem_order[a1] <= elem_order[a2]:
            key = f"{a1},{a2}"
        else:
            key = f"{a2},{a1}"
        val = BONDS_DEFAULT.get(key, BONDS_DEFAULT["Default"])[3]
        if isinstance(val, (list, tuple)):
            val = val[0]
        return float(val) * factor

    max_thresh = 0.0
    elem_set = set(ATOMS)
    for a in elem_set:
        for b in elem_set:
            t = get_threshold(a, b)
            if t > max_thresh:
                max_thresh = t

    grid_size = max_thresh if max_thresh > 0 else 2.0
    grid = {}
    for idx in range(n_atoms):
        x, y, z = coords[idx]
        cell = (int(x // grid_size), int(y // grid_size), int(z // grid_size))
        grid.setdefault(cell, []).append(idx)

    bonds = []
    for i in range(n_atoms):
        elem_i = atoms[i]
        pi = coords[i]
        cx, cy, cz = (int(pi[0]//grid_size), int(pi[1]//grid_size), int(pi[2]//grid_size))
        
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for dz in (-1,0,1):
                    c = (cx+dx, cy+dy, cz+dz)
                    if c not in grid: continue
                    for j in grid[c]:
                        if j <= i: continue
                        elem_j = atoms[j]
                        # 原版精准距离
                        d = np.linalg.norm(pi - coords[j])
                        # 原版精准阈值
                        cutoff = get_threshold(elem_i, elem_j)
                        if d <= cutoff:
                            bonds.append((i, j))

    return bonds, [1]*len(bonds)

class CIF_Atom(bpy.types.PropertyGroup):
    label: StringProperty()
    element: StringProperty()
    x: FloatProperty()
    y: FloatProperty()
    z: FloatProperty()
    occupancy: FloatProperty(default=1.0)
    u_iso_equiv: FloatProperty(default=0.0)
    adp_type: StringProperty(default="Uiso")
    u11: FloatProperty(default=1.0)
    u22: FloatProperty(default=1.0)
    u33: FloatProperty(default=1.0)
    u12: FloatProperty(default=1.0)
    u13: FloatProperty(default=1.0)
    u23: FloatProperty(default=1.0)

class CIF_Structure(bpy.types.PropertyGroup):
    a: FloatProperty(default=5.0)
    b: FloatProperty(default=5.0)
    c: FloatProperty(default=5.0)
    alpha: FloatProperty(default=90.0)
    beta: FloatProperty(default=90.0)
    gamma: FloatProperty(default=90.0)
    sg_name: StringProperty(default='P1')
    sg_num: IntProperty(default=1)
    sym_ops: StringProperty(default='x,y,z')
    atoms: CollectionProperty(type=CIF_Atom)
    atom_count: IntProperty(default=0)
    chemical_name_common: StringProperty(default='')
    chemical_formula_sum: StringProperty(default='')
    chemical_formula_weight: FloatProperty(default=0.0)
    cell_volume: FloatProperty(default=0.0)

def _copy_cif_struct(src, dst):
    dst.a = src.a
    dst.b = src.b
    dst.c = src.c
    dst.alpha = src.alpha
    dst.beta  = src.beta
    dst.gamma = src.gamma
    dst.sg_name = src.sg_name
    dst.sg_num  = src.sg_num
    dst.sym_ops = src.sym_ops
    dst.chemical_name_common    = src.chemical_name_common
    dst.chemical_formula_sum    = src.chemical_formula_sum
    dst.chemical_formula_weight = src.chemical_formula_weight
    dst.cell_volume = src.cell_volume
    dst.atoms.clear()
    for sa in src.atoms:
        na = dst.atoms.add()
        na.label = sa.label; na.element = sa.element
        na.x = sa.x; na.y = sa.y; na.z = sa.z
        na.occupancy = sa.occupancy; na.u_iso_equiv = sa.u_iso_equiv
        na.adp_type = sa.adp_type
        na.u11 = sa.u11; na.u22 = sa.u22; na.u33 = sa.u33
        na.u12 = sa.u12; na.u13 = sa.u13; na.u23 = sa.u23
    dst.atom_count = src.atom_count

def init_cif_data(obj, cell_lengths, cell_angles, sg_info, atom_list, extra_info=None):
    a, b, c = cell_lengths
    alpha, beta, gamma = cell_angles
    sg_name, sg_num, sym_ops = sg_info
    sym_ops = ";".join(sym_ops)

    cif_data = obj.cif_original
    cif_data.a = a
    cif_data.b = b
    cif_data.c = c
    cif_data.alpha = alpha
    cif_data.beta = beta
    cif_data.gamma = gamma
    cif_data.sg_name = sg_name
    cif_data.sg_num = sg_num
    cif_data.sym_ops = sym_ops

    if extra_info:
        cif_data.chemical_name_common = extra_info.get('chemical_name_common', '')
        cif_data.chemical_formula_sum = extra_info.get('chemical_formula_sum', '')
        cif_data.chemical_formula_weight = extra_info.get('chemical_formula_weight', 0.0)
        cif_data.cell_volume = extra_info.get('cell_volume', 0.0)

    for atom_dict in atom_list:
        new_atom = cif_data.atoms.add()
        new_atom.label = atom_dict["label"]
        new_atom.element = atom_dict["element"]
        new_atom.x = atom_dict["x"]
        new_atom.y = atom_dict["y"]
        new_atom.z = atom_dict["z"]
        new_atom.occupancy = atom_dict["occupancy"]
        new_atom.u_iso_equiv = atom_dict["u_iso_equiv"]
        new_atom.adp_type = atom_dict["adp_type"]
        new_atom.u11 = atom_dict.get("u11", 0.0)
        new_atom.u22 = atom_dict.get("u22", 0.0)
        new_atom.u33 = atom_dict.get("u33", 0.0)
        new_atom.u12 = atom_dict.get("u12", 0.0)
        new_atom.u13 = atom_dict.get("u13", 0.0)
        new_atom.u23 = atom_dict.get("u23", 0.0)
    
    cif_data.atom_count = len(atom_list)
    _copy_cif_struct(obj.cif_original, obj.cif_current)

def copy_cif_data(src_obj, dst_obj):
    _copy_cif_struct(src_obj.cif_original, dst_obj.cif_original)
    _copy_cif_struct(src_obj.cif_current,  dst_obj.cif_current)
