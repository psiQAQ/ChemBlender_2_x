import bpy
import os,re
import numpy as np
import requests
from . import _math
from .Chem_data import ELEMENTS_DEFAULT, BONDS_DEFAULT, SYMOP_OPERATIONS

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
    # print(RingNum)
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
    BONDS, BOND_ORDERS = [],[]
    for i, atom1 in enumerate(ATOMS):
        for j, atom2 in enumerate(ATOMS):
            if i < j:
                key = f"{atom1},{atom2}" if ELEMENTS_DEFAULT[atom1][0] <= ELEMENTS_DEFAULT[atom2][0] else f"{atom2},{atom1}"
                if key not in BONDS_DEFAULT: key = "Default"
                coord1 = np.array(COORDS[i])
                coord2 = np.array(COORDS[j])
                distance = np.linalg.norm(coord1-coord2)
                if distance <= BONDS_DEFAULT[key][3]*factor:
                    BONDS.append((i,j))
                    BOND_ORDERS.append(1)
    return (BONDS, BOND_ORDERS)

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

def read_Cryst(moltext, text_type, length_factor, boundary):
    from rdkit import Chem
    periodic_table = Chem.GetPeriodicTable()
    cell_lengths, cell_angles, space_group, space_group_num, atom_type_symbols, atom_site_labels, atom_sites_fx, atom_sites_fy, atom_sites_fz, symop_operations = read_cif(moltext) if text_type.lower() == 'cif' else read_poscar(moltext)
    length_a, length_b, length_c = cell_lengths
    angle_alpha, angle_beta, angle_gamma = cell_angles

    ATOMS, AtomicNum, FRACT_COORDS, CARTN_COORDS = [],[],[],[]
    VDW_R, Radii, RingNum = [],[],[]
    atom_type_symbols = atom_type_symbols if atom_type_symbols else atom_site_labels # Asymmetric unit. 
    fx, fy, fz = atom_sites_fx, atom_sites_fy, atom_sites_fz
    atom_sites_fracts = [[fx[i], fy[i], fz[i]] for i in range(len(atom_type_symbols))]
    atom_sites_dic = {}
    # print(atom_type_symbols)
    # print(atom_sites_fracts)
    # print(symop_operations)
    if cell_lengths[0] == None:
        for symbol, fract_xyz in zip(atom_type_symbols, atom_sites_fracts):
            ATOMS.append(symbol)
            atomic_num = periodic_table.GetAtomicNumber(symbol)
            AtomicNum.append(atomic_num)
            CARTN_COORDS.append(fract_xyz)  
            VDW_R.append(periodic_table.GetRvdw(atomic_num))
            Radii.append(periodic_table.GetRcovalent(atomic_num))
    else:
        for symbol, fract_xyz in zip(atom_type_symbols, atom_sites_fracts):
            atom_sym = re.sub('[\W0-9]', '', symbol)
            # Symmetry equivalent positions (non-normalized)
            sym_fracts = _math.fract_symop(fract_xyz, symop_operations)
            
            # coordinates normalization (e.g. 1.15 becomes 0.15, -0.25 becomes 0.75, etc)
            sym_fracts = _math.fracts_normalize(sym_fracts, boundary)
            if atom_sym in atom_sites_dic:
                for fract in sym_fracts:
                    atom_sites_dic[atom_sym].append(fract)
            else:
                atom_sites_dic.update({atom_sym: sym_fracts})
        # After the coordinates translation, some of the atoms can overlap
        # remove duplicates (same position)
        for elem in atom_sites_dic:
            atom_sites_dic[elem] = _math.deduplicate_fracts(atom_sites_dic[elem], digits=4)
        print(atom_sites_dic)
        for key, value in atom_sites_dic.items():
            atomic_num = periodic_table.GetAtomicNumber(key)
            for fract in value:
                ATOMS.append(key)
                AtomicNum.append(atomic_num)
                FRACT_COORDS.append(fract)
                CARTN_COORDS.append(_math.fract_to_cartn(fract, length_a, length_b, length_c, 
                                    angle_alpha, angle_beta, angle_gamma))  
                VDW_R.append(periodic_table.GetRvdw(atomic_num))
                Radii.append(periodic_table.GetRcovalent(atomic_num))
    # print(ATOMS)
    # print(len(ATOMS))
    # print([(float(f[0]), float(f[1]), float(f[2])) for f in FRACT_COORDS])
    BONDS, BOND_ORDERS = add_BONDS(ATOMS, CARTN_COORDS, length_factor)
    for bond in BONDS: RingNum.append(0)
    mol_list = [[ATOMS, AtomicNum, CARTN_COORDS, BONDS, BOND_ORDERS, VDW_R, Radii, RingNum],
                 [cell_lengths, cell_angles, space_group, space_group_num, symop_operations],
                 ]
    return mol_list

def read_cif(path):
    cell_lengths = [None, None, None]  # 晶胞长度a, b, c, 缺省为None
    cell_angles = [None, None, None]  # 晶胞夹角α, β, γ, 缺省为None
    space_group = 'P1'   # 小分子默认空间群为P1
    space_group_num = 1  # 空间群编号，默认P1对应编号为1
    atom_type_symbols = []
    atom_site_labels = []
    symop_operations = []
    atom_sites_fx = []
    atom_sites_fy = []
    atom_sites_fz = []

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
                    if sg_info[1] == space_group or sg_name == space_group:
                        space_group_num = sg_info[0]
                        break
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
            # 【新增】PDB 小分子 CIF 解析
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

            # 读取数据
            while i < len(lines) and not lines[i].startswith(("loop_", "_")):
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
        symop_operations
    )

# ==========================
def read_poscar(path):
    from rdkit import Chem
    periodic_table = Chem.GetPeriodicTable()

    # ===========================
    # 1. 读取 POSCAR/VASP
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
            atomic_num = periodic_table.GetAtomicNumber(element)
            atomic_nums += [atomic_num] * count

        for i in range(coord_start, coord_start + total_atoms):
            x,y,z = list(map(float, lines[i].split()))[:3]
            if 'cart' in coord_type:
                fract = np.linalg.solve(np.array(cell).T, np.array([x,y,z]))
                fracts.append(fract.tolist())
            else:
                fracts.append([x,y,z])

        return cell, fracts, atomic_nums, elements, counts

    # ===========================
    # 2. 晶胞长度 + 角度
    # ===========================
    def get_cell_lengths_angles(cell):
        a_vec, b_vec, c_vec = np.array(cell)
        a = np.linalg.norm(a_vec)
        b = np.linalg.norm(b_vec)
        c = np.linalg.norm(c_vec)

        def angle(u, v):
            dot = np.clip(np.dot(u, v) / (np.linalg.norm(u)*np.linalg.norm(v)), -1, 1)
            return np.degrees(np.arccos(dot))

        alpha = angle(b_vec, c_vec)
        beta  = angle(a_vec, c_vec)
        gamma = angle(a_vec, b_vec)
        return (float(a), float(b), float(c)), (float(alpha), float(beta), float(gamma))

    # ===========================
    # 3. 晶系判断
    # ===========================
    def get_crystal_system(cell):
        a_vec, b_vec, c_vec = np.array(cell)
        a = np.linalg.norm(a_vec)
        b = np.linalg.norm(b_vec)
        c = np.linalg.norm(c_vec)

        def angle(u, v):
            dot = np.clip(np.dot(u, v) / (np.linalg.norm(u)*np.linalg.norm(v)), -1,1)
            return np.degrees(np.arccos(dot))

        alpha = angle(b_vec, c_vec)
        beta  = angle(a_vec, c_vec)
        gamma = angle(a_vec, b_vec)
        eps = 0.5

        if abs(a-b)<eps and abs(b-c)<eps and abs(alpha-90)<eps and abs(beta-90)<eps and abs(gamma-90)<eps:
            return "cubic"
        if abs(a - b) < eps and abs(gamma - 120) < eps:
            return "trigonal"
        if abs(a-b) < eps and abs(alpha-90)<eps and abs(beta-90)<eps and abs(gamma-90)<eps:
            return "tetragonal"
        if abs(alpha-90)<eps and abs(beta-90)<eps and abs(gamma-90)<eps:
            return "orthorhombic"
        if abs(alpha-90)>eps or abs(beta-90)>eps or abs(gamma-90)>eps:
            return "monoclinic"
        return "triclinic"

    # ===========================
    # 4. 对称操作
    # ===========================
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

    # ===========================
    # 5. 空间群识别
    # ===========================
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
    cell_lengths, cell_angles = get_cell_lengths_angles(cell)

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
    for elem, cnt in zip(elements, [atomic_nums.count(n) for n in [periodic_table.GetAtomicNumber(e) for e in elements]]):
        for i in range(cnt):
            atom_site_labels.append(f"{elem}{i+1}")

    # 空间群 & 对称操作
    space_group = sg_result["symbol"] if "error" not in sg_result else None
    space_group_num = sg_result["number"] if "error" not in sg_result else None
    symop_operations = sg_result["symops"] if "error" not in sg_result else []

    # ===========================
    return (
        cell_lengths, cell_angles, space_group, space_group_num,
        atom_type_symbols, atom_site_labels,
        atom_sites_fx, atom_sites_fy, atom_sites_fz,
        symop_operations
    )
