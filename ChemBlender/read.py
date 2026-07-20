import bpy
import os,re
import numpy as np
import requests
from . import _math
from .Chem_data import ELEMENTS_DEFAULT, BONDS_DEFAULT, SYMOP_OPERATIONS
from bpy.props import IntProperty, FloatProperty, StringProperty, CollectionProperty

def add_bonds_based_on_distance(COORDS, Radii, BONDS, BOND_ORDERS):
    for i in range(len(COORDS)):
        for j in range(i+1, len(COORDS)):
            pos_i = np.array(COORDS[i])
            pos_j = np.array(COORDS[j])
            dist = np.linalg.norm(pos_i-pos_j)
            if dist < (Radii[i]+Radii[j]+0.4):   # 0.4 Å as tolerance distance
                BONDS.append((i,j))
                BOND_ORDERS.append(1)  # 键级默认预设为1

def attr_values_from_mol(mol):
    from rdkit import Chem
    periodic_table = Chem.GetPeriodicTable()
    from rdkit.Chem import AllChem
    """
    给原子和键设置基本属性的列表值.
    """
    ATOMS, AtomicNum, COORDS, BONDS, BOND_ORDERS = [],[],[],[],[]
    VDW_R, Radii, RingNum = [],[],[]
    atoms = mol.GetAtoms()
    bonds = mol.GetBonds()
    ring_info = mol.GetRingInfo()
    if not mol.GetNumConformers():
        AllChem.EmbedMolecule(mol)   # Generate a conformer
    conformer = mol.GetConformer()   # Get the first conformer
    cursor = bpy.context.scene.cursor.location
    for atom in atoms:
        ATOMS.append(atom.GetSymbol())
        pos = conformer.GetAtomPosition(atom.GetIdx())
        COORDS.append((pos.x+cursor.x, pos.y+cursor.y, pos.z+cursor.z))
        atomic_num = atom.GetAtomicNum()
        AtomicNum.append(atomic_num)
        VDW_R.append(periodic_table.GetRvdw(atomic_num))
        Radii.append(periodic_table.GetRcovalent(atomic_num))
    for i, bond in enumerate(bonds):
        BONDS.append((bond.GetBeginAtomIdx(),bond.GetEndAtomIdx()))
        BOND_ORDERS.append(bond.GetBondType())
        RingNum.append(find_in_list(i, ring_info.BondRings()))
    
    if not BONDS:
        add_bonds_based_on_distance(COORDS, Radii, BONDS, BOND_ORDERS)
    return ATOMS, AtomicNum, COORDS, BONDS, BOND_ORDERS, VDW_R, Radii, RingNum

def find_in_list(num, lst):
    for index, sublist in enumerate(lst, start=1):
        if num in sublist:
            return index
    return 0

def mol_2D_to_3D(mol):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.AddHs(mol)  # 添加氢原子
    AllChem.EmbedMolecule(mol)  # 生成3D构象
    AllChem.MMFFOptimizeMolecule(mol)  # 力场优化
    return mol

def is_valid_smiles(smiles_string):
    from rdkit import Chem
    """
    判断给定字符串是否是有效的SMILES字符串.
    """
    try:
        mol = Chem.MolFromSmiles(smiles_string)
        if mol:
            print(f"输入内容为SMILES字符串.")
            return True
        else:
            return False
    except Exception as e:
        print(f"解析SMILES时发生错误: {e}")
        return False

def check_type(moltext):
    """
    判断输入字符串文本的类型: XYZ/MOL/SDF/PDB/SMILES/CIF/CML等.
    根据文本格式或后缀名进行判断.
    """
    if os.path.exists(moltext):
        text_type = os.path.basename(moltext).split('.')[-1]
    elif is_valid_smiles(moltext):
        text_type = 'smiles'
    elif moltext.isdigit():
        text_type = 'cid'
    else:
        text_type = None
    return text_type

def download_sdf_from_pubchem(cid):
    """
    从PubChem网站根据CID号载入对应分子的SDF格式文件, 如Aspirin CID: 2244.
    此处下载均为2D分子, 需经过优化得到3D坐标.
    """
    try:
        # 获取SDF文件内容
        sdf_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/SDF"
        response_1 = requests.get(sdf_url)
        if response_1.status_code != 200:
            print(f"Failed to download SDF file for CID {cid}.")
            return None, None, None

        # 获取分子名称和IUPAC名称
        name_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/IUPACName,Title/JSON"
        response_2 = requests.get(name_url)
        if response_2.status_code != 200:
            print(f"Failed to get molecular names for CID {cid}.")
            return None, None, None
        
        data = response_2.json()
        properties = data.get("PropertyTable", {}).get("Properties", [{}])[0]
        common_name = properties.get("Title", "N/A")
        iupac_name = properties.get("IUPACName", "N/A")

        # 返回SDF内容和分子名称
        sdf_content = response_1.text
        return sdf_content, common_name, iupac_name
    
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None, None, None

def json_2_molblock(moltext):
    from rdkit import Chem
    import json
    with open(moltext, "r") as f:
        json_str = f.read()
    data = json.loads(json_str)
    atoms_dict = data['PC_Compounds'][0]['atoms']
    bonds_dict = data['PC_Compounds'][0]['bonds']
    coords_list = data['PC_Compounds'][0]['coords'][0]
    x_list = coords_list['conformers'][0]['x']
    y_list = coords_list['conformers'][0]['y']
    z_list = coords_list['conformers'][0]['z']
    COORDS = [(x,y,z) for x,y,z in zip(x_list,y_list,z_list)]
    ATOMIC_NUMS = atoms_dict['element']
    ATOMS = [Chem.Atom(i) for i in ATOMIC_NUMS]
    bonds_aid1 = bonds_dict['aid1']
    bonds_aid2 = bonds_dict['aid2']
    BONDS = [(i-1,j-1) for i,j in zip(bonds_dict['aid1'],bonds_dict['aid2'])]
    BOND_ORDERS = bonds_dict['order'] 
    return atoms_to_molblock(ATOMS, COORDS, BONDS, BOND_ORDERS)


def atoms_to_molblock(ATOMS, COORDS, BONDS, BOND_ORDERS):
    from rdkit import Chem
    from rdkit.Geometry import Point3D
    mol = Chem.RWMol()
    for atom in ATOMS:
        mol.AddAtom(atom)
    for bond, order in zip(BONDS, BOND_ORDERS):
        mol.AddBond(
            bond[0], bond[1], Chem.BondType.values[order]
        )
    mol = mol.GetMol()
    conf = Chem.Conformer(mol.GetNumAtoms())
    for i, coord in enumerate(COORDS):
        conf.SetAtomPosition(i, Point3D(coord[0],coord[1],coord[2]))
    mol.AddConformer(conf)
    return Chem.MolToMolBlock(mol)

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

def read_MOL(moltext):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    text_type = check_type(moltext)
    # get mol object from moltext
    if text_type == 'smiles':
        mol = Chem.MolFromSmiles(moltext)
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        if len(moltext)>50: params.useRandomCoords = True
        params.numThreads = 1
        status = AllChem.EmbedMolecule(mol, params)
        if status == 0:
            try:
                AllChem.UFFOptimizeMolecule(mol)
            except:
                pass  
        block = Chem.MolToMolBlock(mol)
    elif text_type == 'xyz':
        mol = Chem.MolFromXYZFile(moltext)
    elif text_type == 'mol' or text_type == 'sdf':
        mol = Chem.MolFromMolFile(moltext, removeHs=False, sanitize=False)
    elif text_type == 'pdb':
        mol = Chem.MolFromPDBFile(moltext)
    elif text_type == 'cid':   # from PubChem
        block = download_sdf_from_pubchem(moltext)[0]
        mol = Chem.MolFromMolBlock(block)
        mol = mol_2D_to_3D(mol)   # conformation optimization
    elif text_type == 'json':
        block = json_2_molblock(moltext)
        mol = Chem.MolFromMolBlock(block)
    mol_list = [[attr_values_from_mol(mol)]]
    return mol_list

def get_atomic_number(symbol):
    from rdkit import Chem
    # 提取纯元素符号（去掉数字、电荷、同位素标记）
    core = re.sub(r'[^A-Za-z]', '', symbol).strip()
    # 处理同位素 D/T
    mapping = {"D": "H", "T": "H"}
    core = mapping.get(core, core)
    try:
        return Chem.GetPeriodicTable().GetAtomicNumber(core)
    except:
        return 1

def label_to_element(label):
    label = label.strip()
    ELEMENTS = list(ELEMENTS_DEFAULT.keys())
    if len(label) >= 2:
        e2 = label[:2].capitalize()
        if e2 in ELEMENTS:
            return e2
    e1 = label[:1].capitalize()
    if e1 in ELEMENTS:
        return e1
    return None

def read_Cryst(moltext, text_type, length_factor, boundary):
    from rdkit import Chem
    periodic_table = Chem.GetPeriodicTable()

    result = read_cif(moltext) if text_type.lower() == 'cif' else read_poscar(moltext)
    if text_type.lower() == 'cif':
        (cell_lengths, cell_angles, space_group, space_group_num,
         atom_type_symbols, atom_site_labels,
         atom_sites_fx, atom_sites_fy, atom_sites_fz,
         symop_operations, atom_U_iso, atom_adp_type, atom_U_aniso,
         chemical_name_common, chemical_formula_sum,
         chemical_formula_weight, cell_volume) = result
        extra_info = {
            'chemical_name_common': chemical_name_common,
            'chemical_formula_sum': chemical_formula_sum,
            'chemical_formula_weight': chemical_formula_weight,
            'cell_volume': cell_volume,
        }
    else:
        (cell_lengths, cell_angles, space_group, space_group_num,
         atom_type_symbols, atom_site_labels,
         atom_sites_fx, atom_sites_fy, atom_sites_fz,
         symop_operations, atom_U_iso, atom_adp_type, atom_U_aniso) = result
        extra_info = {}

    length_a, length_b, length_c = cell_lengths
    angle_alpha, angle_beta, angle_gamma = cell_angles

    ATOMS, AtomicNum, FRACT_COORDS, CARTN_COORDS = [],[],[],[]
    VDW_R, Radii, RingNum = [],[],[]
    U_Iso, ADP_Type, U_Aniso = [],[],[]
    U_Scale, U_v1, U_v2, U_v3 = [],[],[],[]

    atom_type_symbols = atom_type_symbols if atom_type_symbols else atom_site_labels # Asymmetric unit. 
    fx, fy, fz = atom_sites_fx, atom_sites_fy, atom_sites_fz
    atom_sites_fracts = [[fx[i], fy[i], fz[i]] for i in range(len(atom_type_symbols))]
    atom_type_symbols = [label_to_element(sym) for sym in atom_type_symbols]

    original_atom_list = make_atom_list(atom_type_symbols,
    atom_site_labels,
    atom_sites_fx,
    atom_sites_fy,
    atom_sites_fz,
    atom_U_iso,
    atom_adp_type,
    atom_U_aniso)
    
    #print(original_atom_list)

    if cell_lengths[0] == None: #small molecule
        for i, (symbol, fract_xyz) in enumerate(zip(atom_type_symbols, atom_sites_fracts)):
            ATOMS.append(symbol)
            atomic_num = get_atomic_number(symbol)
            AtomicNum.append(atomic_num)
            CARTN_COORDS.append(fract_xyz)  
            VDW_R.append(periodic_table.GetRvdw(atomic_num))
            Radii.append(periodic_table.GetRcovalent(atomic_num))
            U_Iso.append(atom_U_iso[i])
            ADP_Type.append(atom_adp_type[i])
            u_aniso_raw = atom_U_aniso.get(atom_site_labels[i], None)
            if u_aniso_raw is not None:
                u_aniso_raw = u_aniso_raw + (1,)
            U_Aniso.append(u_aniso_raw)
        U_Scale = [1.0, 1.0, 1.0]*len(ATOMS)
        U_v1 = [1.0, 0.0, 0.0]*len(ATOMS)
        U_v2 = [0.0, 1.0, 0.0]*len(ATOMS)
        U_v3 = [1.0, 0.0, 1.0]*len(ATOMS)
    else: # crystal
        all_atoms_with_index = []
        for i, (symbol, fract_xyz) in enumerate(zip(atom_type_symbols, atom_sites_fracts)):
            atom_sym = re.sub('[\W0-9]', '', symbol)
            
            sym_fracts, sym_rotations = _math.fract_symop(fract_xyz, symop_operations)
            
            for fract, R in zip(sym_fracts, sym_rotations):
                fract_norm = np.array(fract, dtype=float) % 1.0
                
                # 对每个方向，确定可能的偏移量
                offsets = []
                for k in range(3):
                    axis_offsets = [0.0]  # 始终包含原始位置
                    if fract_norm[k] <= boundary:
                        axis_offsets.append(1.0)
                    if fract_norm[k] >= 1.0 - boundary:
                        axis_offsets.append(-1.0)
                    offsets.append(axis_offsets)
                
                # 笛卡尔积：枚举所有三个方向的偏移组合
                for dx in offsets[0]:
                    for dy in offsets[1]:
                        for dz in offsets[2]:
                            f = fract_norm.copy()
                            f[0] += dx; f[1] += dy; f[2] += dz
                            all_atoms_with_index.append((f, i, atom_sym, R))

        unique_atoms = []
        seen = set()
        for fract, i, elem, R in all_atoms_with_index:
            key = (tuple(np.round(fract, 4)), i) 
            if key not in seen:
                seen.add(key)
                unique_atoms.append((fract, i, elem, R))
        
        for fract, original_i, elem, R in unique_atoms:
            atomic_num = get_atomic_number(elem)
            
            ATOMS.append(elem)
            AtomicNum.append(atomic_num)
            FRACT_COORDS.append(fract)
            CARTN_COORDS.append(_math.fract_to_cartn(fract, length_a, length_b, length_c, 
                                angle_alpha, angle_beta, angle_gamma))  
            VDW_R.append(periodic_table.GetRvdw(atomic_num))
            Radii.append(periodic_table.GetRcovalent(atomic_num))
            U_Iso.append(atom_U_iso[original_i])
            ADP_Type.append(atom_adp_type[original_i])
            
            u_raw = atom_U_aniso.get(atom_site_labels[original_i], None)
            
            u_transformed = _math.transform_U_aniso(u_raw, R)
            det_sign = int(np.sign(np.linalg.det(np.array(R, dtype=float))))
            if u_transformed is not None:
                u_transformed = u_transformed + (det_sign,)
            U_Aniso.append(u_transformed)
        U_Scale, U_v1, U_v2, U_v3 = _math.compute_thermal_ellipsoid(U_Aniso, U_Iso, cell_lengths, cell_angles, prob_factor=1.54)
    
    #BONDS, BOND_ORDERS = [],[]
    BONDS, BOND_ORDERS = add_BONDS(ATOMS, CARTN_COORDS, length_factor)
    for bond in BONDS: RingNum.append(0)

    mol_list = [[ATOMS, AtomicNum, CARTN_COORDS, BONDS, BOND_ORDERS, VDW_R, Radii, RingNum,
                U_Scale, U_v1, U_v2, U_v3],
                 [cell_lengths, cell_angles, space_group, space_group_num, symop_operations],
                 original_atom_list, extra_info]
    return mol_list

def read_cif(path):
    cell_lengths = [None, None, None]  # 晶胞长度a, b, c, 缺省为None
    cell_angles = [None, None, None]  # 晶胞夹角α, β, γ, 缺省为None
    cell_volume = 0.0
    space_group = 'P1'   # 小分子默认空间群为P1
    space_group_num = 1  # 空间群编号，默认P1对应编号为1
    atom_type_symbols = []
    atom_site_labels = []
    symop_operations = []
    atom_sites_fx = []
    atom_sites_fy = []
    atom_sites_fz = []
    # Thermal vibration parameters
    atom_U_iso = []
    atom_adp_type = []  #'Uiso' or 'Uani'
    atom_U_aniso = {}
    chemical_name_common = ''
    chemical_formula_sum = ''
    chemical_formula_weight = 0.0


    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        # ---------------- cell parameters ----------------    
        if line.startswith(("_cell_length_", "_cell_angle_")):
            key, val_str = line.split(None, 1)
            val_str = re.sub(r"\(.*\)", "", val_str).strip()
            try:
                val = float(val_str)
                if key == "_cell_length_a": cell_lengths[0] = val
                elif key == "_cell_length_b": cell_lengths[1] = val
                elif key == "_cell_length_c": cell_lengths[2] = val
                elif key == "_cell_angle_alpha": cell_angles[0] = val
                elif key == "_cell_angle_beta": cell_angles[1] = val
                elif key == "_cell_angle_gamma": cell_angles[2] = val
            except:
                pass
        
        elif line.startswith("_chemical_name_common"):
            parts = line.split(None, 1)
            if len(parts) > 1:
                chemical_name_common = parts[1].strip().strip("'\"")
            else:
                i += 1
                if i < len(lines):
                    chemical_name_common = lines[i].strip().strip("'\"")
        
        elif line.startswith("_chemical_formula_sum"):
            parts = line.split(None, 1)
            if len(parts) > 1:
                chemical_formula_sum = parts[1].strip().strip("'\"")
            else:
                i += 1
                if i < len(lines):
                    chemical_formula_sum = lines[i].strip().strip("'\"")
        
        elif line.startswith("_chemical_formula_weight"):
            parts = line.split(None, 1)
            if len(parts) > 1:
                try:
                    chemical_formula_weight = float(re.sub(r"\(.*\)", "", parts[1]).strip())
                except:
                    pass
        
        elif line.startswith("_cell_volume"):
            parts= line.split(None, 1)
            if len(parts) > 1:
                try:
                    cell_volume = float(re.sub(r"\(.*\)", "", parts[1]).strip())
                except:
                    pass


        # ---------------- space group ----------------
        elif line.startswith((
            "_symmetry_Int_Tables_number",
            "_space_group_IT_number"
        )):
            key, val_str = line.split(None, 1)
            val_str = re.sub(r"\(.*\)", "", val_str).strip()
            try:
                space_group_num = int(float(val_str))
            except:
                pass
            i += 1
            continue

        elif line.startswith((
            "_symmetry_space_group_name_H-M",
            "_space_group_name_H-M_alt",
            "_space_group_name_Hall"
        )):
            parts = line.split(None, 1)
            if len(parts) > 1:
                space_group = parts[1].strip("'\"").replace(" ", "")
            else:
                i += 1
                space_group = lines[i].strip("'\"").replace(" ", "")
            space_group = space_group.capitalize()
            
            if space_group_num == 1:
                for sg_name, sg_info in SYMOP_OPERATIONS.items():
                    if space_group in sg_info[1] or space_group in sg_info[1].replace('_', '') or sg_name == space_group:
                        space_group_num = sg_info[0]
                        break

            space_group = list(SYMOP_OPERATIONS.items())[space_group_num-1][0]
            i += 1
            continue

        # ---------------- loop block ----------------
        elif line.startswith("loop_"):
            headers = []
            i += 1
            while i < len(lines) and lines[i].startswith("_"):
                headers.append(lines[i])
                i += 1

            # ----------------------
            # PDB 小分子 CIF 解析
            # ----------------------
            is_pdb_atom = (
                "_chem_comp_atom.atom_id" in headers
                and "_chem_comp_atom.type_symbol" in headers
                and "_chem_comp_atom.model_Cartn_x" in headers
            )

            if is_pdb_atom:
                lbl = headers.index("_chem_comp_atom.atom_id")
                sym = headers.index("_chem_comp_atom.type_symbol")
                x = headers.index("_chem_comp_atom.model_Cartn_x")
                y = headers.index("_chem_comp_atom.model_Cartn_y")
                z = headers.index("_chem_comp_atom.model_Cartn_z")

                while i < len(lines) and not lines[i].startswith(("_", "loop_", "data_", "#")):
                    p = re.split(r"\s+", lines[i])
                    atom_site_labels.append(p[lbl])
                    atom_type_symbols.append(p[sym])
                    atom_sites_fx.append(float(p[x]))
                    atom_sites_fy.append(float(p[y]))
                    atom_sites_fz.append(float(p[z]))
                    # 小分子默认热振动
                    atom_U_iso.append(0.0)
                    atom_adp_type.append("Uiso")
                    i += 1
                continue

            is_aniso_loop = (
                "_atom_site_aniso_label" in headers
                and "_atom_site_aniso_U_11" in headers
            )

            if is_aniso_loop:
                ilbl = headers.index("_atom_site_aniso_label")
                i11 = headers.index("_atom_site_aniso_U_11")
                i22 = headers.index("_atom_site_aniso_U_22")
                i33 = headers.index("_atom_site_aniso_U_33")
                i23 = headers.index("_atom_site_aniso_U_23")
                i13 = headers.index("_atom_site_aniso_U_13")
                i12 = headers.index("_atom_site_aniso_U_12")

                while i<len(lines) and not lines[i].startswith(("loop_","_","data_")):
                    toks = re.split(r"\s+", lines[i])
                    if len(toks) > i12:
                        label = toks[ilbl]
                        U11 = float(re.sub(r"\(.*\)","",toks[i11]))
                        U22 = float(re.sub(r"\(.*\)","",toks[i22]))
                        U33 = float(re.sub(r"\(.*\)","",toks[i33]))
                        U23 = float(re.sub(r"\(.*\)","",toks[i23]))
                        U13 = float(re.sub(r"\(.*\)","",toks[i13]))
                        U12 = float(re.sub(r"\(.*\)","",toks[i12]))
                        atom_U_aniso[label] = (U11,U22,U33,U23,U13,U12)
                    i += 1
                    continue

            sym_keys = [
                "_space_group_symop_operation_xyz",
                "_symmetry_equiv_pos_as_xyz"
            ]
            sym_index = None
            for key in sym_keys:
                if key in headers:
                    sym_index = headers.index(key)
                    break

            ix = headers.index("_atom_site_fract_x") if "_atom_site_fract_x" in headers else None
            iy = headers.index("_atom_site_fract_y") if "_atom_site_fract_y" in headers else None
            iz = headers.index("_atom_site_fract_z") if "_atom_site_fract_z" in headers else None
            itype = headers.index("_atom_site_type_symbol") if "_atom_site_type_symbol" in headers else None
            ilabel = headers.index("_atom_site_label") if "_atom_site_label" in headers else None
            iUiso = headers.index("_atom_site_U_iso_or_equiv") if "_atom_site_U_iso_or_equiv" in headers else None
            iAdp = headers.index("_atom_site_adp_type") if "_atom_site_adp_type" in headers else None 
            
            # 读取数据
            while i < len(lines) and not lines[i].startswith(("loop_", "_", "data_")):
                line = lines[i].strip()
                if not line or line.startswith("#"):
                    i += 1
                    continue
                tokens = re.split(r"\s+", line)

                # 对称操作
                if sym_index is not None:
                    sym = re.sub(r'^\s*\d+\s+', '', line.strip()).strip("'\"")
                    if sym:
                        symop_operations.append(sym)

                # 原子类型
                if itype is not None and len(tokens) > itype:
                    atom_type_symbols.append(tokens[itype])

                # 原子标签
                if ilabel is not None and len(tokens) > ilabel:
                    atom_site_labels.append(tokens[ilabel])

                # 分数坐标 / 小分子笛卡尔坐标（OpenBabel）
                if ix is not None and iy is not None and iz is not None:
                    if len(tokens) > max(ix, iy, iz):
                        try:
                            fx = re.sub(r"\(.*\)", "", tokens[ix])
                            fy = re.sub(r"\(.*\)", "", tokens[iy])
                            fz = re.sub(r"\(.*\)", "", tokens[iz])
                            atom_sites_fx.append(float(fx))
                            atom_sites_fy.append(float(fy))
                            atom_sites_fz.append(float(fz))
                        except ValueError:
                            pass
                if ilabel is not None:
                    uval = 0.0
                    adp = "Uiso"
                    if iUiso is not None and len(tokens) > iUiso:
                        uval = float(re.sub(r"\(.*\)","",tokens[iUiso]))
                    if iAdp is not None and len(tokens) > iAdp:
                        adp = tokens[iAdp]
                    atom_U_iso.append(uval)
                    atom_adp_type.append(adp)

                i += 1
            continue
        i += 1

    # 无对称操作则默认 x,y,z
    if not symop_operations:
        try:
            symop_operations = SYMOP_OPERATIONS[space_group.capitalize()][4]
            if space_group_num == 1:
                space_group_num = SYMOP_OPERATIONS[space_group.capitalize()][0]
        except KeyError:
            symop_operations = ['x,y,z']

    # ---------------- 小分子自动清空晶胞 ----------------
    # 如果是 PDB 小分子 / OpenBabel 小分子，自动把晶胞设为 None
    has_pdb_atom = any("_chem_comp_atom" in l for l in lines)
    has_no_cell = (cell_lengths == [None, None, None])

    if has_pdb_atom or has_no_cell:
        cell_lengths = [None, None, None]
        cell_angles = [None, None, None]

    return (
        cell_lengths, cell_angles, space_group, space_group_num,
        atom_type_symbols, atom_site_labels,
        atom_sites_fx, atom_sites_fy, atom_sites_fz,
        symop_operations, atom_U_iso, atom_adp_type, atom_U_aniso,
        chemical_name_common, chemical_formula_sum,
        chemical_formula_weight, cell_volume
    )

# ==========================
def read_poscar(path):
    from rdkit import Chem
    periodic_table = Chem.GetPeriodicTable()

    # ===========================
    # 1. POSCAR/VASP Parsing
    # ===========================
    def poscar(path):
        with open(path,'r') as f:
            lines = [line.strip() for line in f if line.strip()]
        scale = float(lines[1])
        cell = []
        for i in range(2,5):
            vals = list(map(float, lines[i].split()))
            cell.append([v * scale for v in vals])

        line6 = lines[5].split()
        if line6[0].isalpha():
            elements = line6
            counts = list(map(int, lines[6].split()))
            coord_start = 8
        else:
            raise ValueError("请使用带元素名称的新版POSCAR")

        coord_type = lines[coord_start - 1].lower()
        fracts, atomic_nums = [], []
        total_atoms = sum(counts)

        for element, count in zip(elements, counts):
            atomic_num = get_atomic_number(element)
            atomic_nums += [atomic_num] * count

        for i in range(coord_start, coord_start + total_atoms):
            x,y,z = list(map(float, lines[i].split()))[:3]
            if 'cart' in coord_type: # Cartesian
                fract = np.linalg.solve(np.array(cell).T, np.array([x,y,z]))
                fracts.append(fract.tolist())
            else: # Direct
                fracts.append([x,y,z])

        return cell, fracts, atomic_nums, elements, counts

    def get_crystal_system(cell):
        cell_lengths, cell_angles = _math.get_cell_lengths_angles(cell)
        crys_sys = _math.get_crystal_system_from_params(cell_lengths, cell_angles)
        return crys_sys

    def apply_symmetry(op_str, x, y, z):
        exprs = [e.strip() for e in op_str.split(',')]
        safe_dict = {'x': x, 'y': y, 'z': z}
        new_coords = []
        for expr in exprs:
            expr = expr.replace(' ', '')
            val = eval(expr, {"__builtins__": None}, safe_dict)
            new_coords.append(val % 1.0)
        return tuple(new_coords)

    def test_space_group(fracts, atomic_nums, symmetry_ops, tol=0.01):
        for op in symmetry_ops:
            transformed = []
            for (x,y,z), num_t in zip(fracts, atomic_nums):
                nx, ny, nz = apply_symmetry(op, x,y,z)
                transformed.append((nx, ny, nz, num_t))

            for (nx, ny, nz, num_t) in transformed:
                found = False
                for (px, py, pz), num_p in zip(fracts, atomic_nums):
                    if num_t != num_p: continue
                    dx = abs((nx - px + 0.5) % 1 - 0.5)
                    dy = abs((ny - py + 0.5) % 1 - 0.5)
                    dz = abs((nz - pz + 0.5) % 1 - 0.5)
                    if dx < tol and dy < tol and dz < tol:
                        found = True
                        break
                if not found:
                    return False
        return True

    def find_space_group(path):
        cell, fracts, atomic_nums, elements, counts = poscar(path)
        crystal_sys = get_crystal_system(cell)

        candidate_groups = {}
        for name, info in SYMOP_OPERATIONS.items():
            num, sym, sys, pg, ops = info
            if crystal_sys == "trigonal":
                if sys in ["trigonal", "hexagonal"]:
                    candidate_groups[name] = info
            else:
                if sys == crystal_sys:
                    candidate_groups[name] = info

        candidates = [(-len(info[4]), name, info) for name, info in candidate_groups.items()]
        candidates.sort()

        for _, name, info in candidates:
            num, sym, sys, pg, ops = info
            if test_space_group(fracts, atomic_nums, ops):
                return {
                    "number": num,
                    "symbol": sym,
                    "crystal_system": sys,
                    "point_group": pg,
                    "symops": ops
                }, cell, fracts, atomic_nums, elements, counts

        return {"error": "未找到"}, cell, fracts, atomic_nums, elements, counts

    # ===========================
    sg_result, cell, fracts, atomic_nums, elements, counts = find_space_group(path)
    cell_lengths, cell_angles = _math.get_cell_lengths_angles(cell)

    # 原子类型符号
    atom_type_symbols = []
    for elem, cnt in zip(elements, counts):
        atom_type_symbols += [elem] * cnt

    # 原子坐标拆分
    atom_sites_fx = [f[0] for f in fracts]
    atom_sites_fy = [f[1] for f in fracts]
    atom_sites_fz = [f[2] for f in fracts]

    # 原子标签（如 Si1, Si2, O1, O2...）
    atom_site_labels = []
    for elem, cnt in zip(elements, [atomic_nums.count(n) for n in [get_atomic_number(e) for e in elements]]):
        for i in range(cnt):
            atom_site_labels.append(f"{elem}{i+1}")

    # 空间群 & 对称操作
    space_group = sg_result["symbol"] if "error" not in sg_result else None
    space_group_num = sg_result["number"] if "error" not in sg_result else None
    symop_operations = sg_result["symops"] if "error" not in sg_result else []

    atom_count = len(atom_type_symbols)
    atom_U_iso = [0.0]*atom_count
    atom_adp_type = ["Uiso"]*atom_count
    atom_U_aniso = {}

    # ===========================
    return (
        cell_lengths, cell_angles, space_group, space_group_num,
        atom_type_symbols, atom_site_labels,
        atom_sites_fx, atom_sites_fy, atom_sites_fz,
        symop_operations, atom_U_iso, atom_adp_type, atom_U_aniso
    )

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

def init_cif_current(obj):
    _copy_cif_struct(obj.cif_original, obj.cif_current)

def copy_cif_data(src_obj, dst_obj):
    _copy_cif_struct(src_obj.cif_original, dst_obj.cif_original)
    _copy_cif_struct(src_obj.cif_current,  dst_obj.cif_current)

def make_atom_list(
    atom_type_symbols,
    atom_site_labels,
    atom_sites_fx,
    atom_sites_fy,
    atom_sites_fz,
    atom_U_iso,
    atom_adp_type,
    atom_U_aniso
):
    atom_list = []
    n = len(atom_type_symbols)

    for i in range(n):
        label = atom_site_labels[i]
        elem = atom_type_symbols[i]
        x = atom_sites_fx[i]
        y = atom_sites_fy[i]
        z = atom_sites_fz[i]
        u_iso = atom_U_iso[i]
        adp_type = atom_adp_type[i]

        u11 = u22 = u33 = u12 = u13 = u23 = 0.0

        if adp_type == "Uani" and label in atom_U_aniso:
            u11, u22, u33, u23, u13, u12 = atom_U_aniso[label]

        atom_dict = {
            "label": label,
            "element": elem,
            "x": x,
            "y": y,
            "z": z,
            "occupancy": 1.0,
            "u_iso_equiv": u_iso,
            "adp_type": adp_type,
            "u11": u11,
            "u22": u22,
            "u33": u33,
            "u12": u12,
            "u13": u13,
            "u23": u23,
        }
        atom_list.append(atom_dict)

    return atom_list

def get_asymmetric_unit(fracts, atomic_nums, symops, tol=0.01):
    """从完整原子列表中提取不对称单元"""
    remaining = list(zip(fracts, atomic_nums))
    asymmetric = []

    while remaining:
        fract, num = remaining[0]
        asymmetric.append((fract, num))
        
        equiv_set = []
        for op in symops:
            nx, ny, nz = apply_symmetry(op, *fract)
            equiv_set.append((nx % 1.0, ny % 1.0, nz % 1.0))
        
        new_remaining = []
        for f, n in remaining:
            if n != num:
                new_remaining.append((f, n))
                continue
            is_equiv = False
            for ef in equiv_set:
                dx = abs((f[0]-ef[0]+0.5)%1-0.5)
                dy = abs((f[1]-ef[1]+0.5)%1-0.5)
                dz = abs((f[2]-ef[2]+0.5)%1-0.5)
                if dx<tol and dy<tol and dz<tol:
                    is_equiv = True
                    break
            if not is_equiv:
                new_remaining.append((f, n))
        remaining = new_remaining

    return asymmetric

def apply_symmetry(op_str, x, y, z):
        exprs = [e.strip() for e in op_str.split(',')]
        safe_dict = {'x': x, 'y': y, 'z': z}
        return tuple(eval(expr, {"__builtins__": None}, safe_dict) % 1.0 for expr in exprs)

def update_cif_from_mesh(obj):
    from rdkit import Chem
    cif_data = obj.cif_current
    if cif_data.atom_count == 0:
        return False, "No CIF data found."
    
    cell_lengths = (cif_data.a, cif_data.b, cif_data.c)
    cell_angles = (cif_data.alpha, cif_data.beta, cif_data.gamma)
    periodic_table = Chem.GetPeriodicTable()
    atomic_num_to_symbol = {num: sym for sym, (num, *_) in ELEMENTS_DEFAULT.items()}

    from . import mesh as mesh_mod
    Atomic_Nums = mesh_mod.get_attr(obj, 'atomic_num', 'INT', 'VERT')

    fracts = []
    atom_atomic_nums = []
    for vert, atomic_num in zip(obj.data.vertices, Atomic_Nums):
        fx,fy,fz = _math.cartn_to_fract(
            tuple(vert.co), *cell_lengths, *cell_angles
        )
        fracts.append((fx % 1.0, fy % 1.0, fz % 1.0))
        atom_atomic_nums.append(atomic_num)

    def test_space_group(fracts, Atomic_Nums, symmetry_ops, tol=0.01):
        for op in symmetry_ops:
            for (x, y, z), num_t in zip(fracts, Atomic_Nums):
                nx, ny, nz = apply_symmetry(op, x, y, z)
                found = False
                for (px,py,pz), num_p in zip(fracts, Atomic_Nums):
                    if num_t != num_p: continue
                    dx = abs((nx-px+0.5)%1-0.5)
                    dy = abs((ny-py+0.5)%1-0.5)
                    dz = abs((nz-pz+0.5)%1-0.5)
                    if dx<tol and dy<tol and dz<tol:
                        found = True
                        break
                if not found:
                    return False
        return True
    
    crystal_sys = _math.get_crystal_system_from_params(cell_lengths, cell_angles)
    candidates = []
    for name, info in SYMOP_OPERATIONS.items():
        num, sym, sys, pg, ops = info
        if crystal_sys == "trigonal":
            if sys in ["trigonal", "hexagonal"]:
                candidates.append((-len(ops), name, info))
        else:
            if sys == crystal_sys:
                candidates.append((-len(ops), name, info))
    candidates.sort()

    space_group = 'P1'
    space_group_num = 1
    symop_operations = ['x,y,z']
    for _, name, info in candidates:
        num, sym, sys, pg, ops = info
        if test_space_group(fracts, atom_atomic_nums, ops):
            space_group = sym
            space_group_num = num
            symop_operations = ops
            break

    cif_data.sg_name = space_group
    cif_data.sg_num  = space_group_num
    cif_data.sym_ops = ';'.join(symop_operations)

    cif_data.cell_volume = _math.calc_cell_volume(*cell_lengths, *cell_angles)

    asym_atoms = get_asymmetric_unit(fracts, atom_atomic_nums, symop_operations)

    cif_data.atoms.clear()
    elem_count = {}
    total_weight = 0.0
    elem_idx = {}

    for (fx, fy, fz), atomic_num in asym_atoms:
        symbol = atomic_num_to_symbol.get(atomic_num, 'C')
        elem_idx[symbol] = elem_idx.get(symbol, 0) + 1

        new_atom = cif_data.atoms.add()
        new_atom.label       = f"{symbol}{elem_idx[symbol]}"
        new_atom.element     = symbol
        new_atom.x           = fx
        new_atom.y           = fy
        new_atom.z           = fz
        new_atom.occupancy   = 1.0
        new_atom.u_iso_equiv = 0.0
        new_atom.adp_type    = 'Uiso'
        new_atom.u11 = new_atom.u22 = new_atom.u33 = 0.0
        new_atom.u12 = new_atom.u13 = new_atom.u23 = 0.0

        elem_count[symbol] = elem_count.get(symbol, 0) + 1
        total_weight += periodic_table.GetAtomicWeight(atomic_num)

    cif_data.atom_count = len(asym_atoms)

    def hill_sort_key(sym):
        if sym == 'C': return (0, sym)
        if sym == 'H': return (1, sym)
        return (2, sym)

    formula_parts = [f"{s}{n}" if n > 1 else s
                     for s, n in sorted(elem_count.items(), key=lambda x: hill_sort_key(x[0]))]
    cif_data.chemical_formula_sum    = ' '.join(formula_parts)
    cif_data.chemical_formula_weight = round(total_weight, 3)

    return True, f"CIF updated. Space group: {space_group} (No.{space_group_num})"