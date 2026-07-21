import numpy as np
from . import mesh
from math import pi,cos,acos,sin,asin,atan2,sqrt

def get_length(vector):
    length = np.linalg.norm(vector)
    return length

def normalize(vector):
    return vector/get_length(vector) if get_length(vector) else vector

# rotate a vector around an axis
def rotate_vec(vec, axis, angle):
    u = normalize(axis)
    x, y, z = u[0], u[1], u[2]
    cos = np.cos(angle)
    sin = np.sin(angle)
    R = np.array([[cos+x*x*(1-cos), x*y*(1-cos)-z*sin, x*z*(1-cos)+y*sin],
                  [x*y*(1-cos)+z*sin, cos+y*y*(1-cos), y*z*(1-cos)-x*sin],
                  [x*z*(1-cos)-y*sin, y*z*(1-cos)+x*sin, cos+z*z*(1-cos)],])
    return np.dot(R, vec)

# calculate a vertical vector of the vec
def vertical_vec(pos1, pos2):
    v = normalize(pos2-pos1)
    if v[0] == 0 and v[1] == 0:
        vertical = np.array((1,0,0))
    else:
        vertical = normalize((-v[1], v[0], 0))
    return vertical

# get heading, pitch, bank vectors of a vert
def vert_hpb(vert, rotate_angle):
    vecs = []
    for edge in vert.link_edges:
        link_vert = mesh.get_link_vert(vert, edge)
        vecs.append(normalize(np.array(vert.co) - np.array(link_vert.co)))
    bank = np.array((0.0, 0.0, 0.0))
    for vec in vecs: bank += vec
    bank = normalize(bank)
    # 此处有待优化
    # -------------
    if len(vecs)>=3:
        if abs(np.dot(np.cross(vecs[0],vecs[1]),vecs[2])) <= 0.0025:   # coplanar vecs
            bank = np.cross(vecs[0],vecs[1])
    # -------------
    if len(vecs) == 0:
        bank = np.array((1, 0, 0))
        pitch = np.array((0, 1, 0))
    elif len(vecs) == 1:
        pitch = vertical_vec(np.array((0,0,0)), bank)
    elif len(vecs) >= 2:
        pitch = normalize(vecs[1]-vecs[0])
    pitch = rotate_vec(pitch, bank, rotate_angle)
    heading = np.cross(bank, pitch)
    return (bank, pitch, heading)

def branches_dir(vert, branches, deflection_angle):
    bank, pitch, heading = vert_hpb(vert, rotate_angle=pi/2)
    banks = []
    pitches = []
    if branches == 1:
        bank = rotate_vec(bank, heading, deflection_angle*pi/180)
        pitch = np.cross(heading, bank)
        banks.append(bank)
        pitches.append(pitch)
    elif branches == 2:
        bank_1 = rotate_vec(bank, heading, deflection_angle*pi/180)
        bank_2 = rotate_vec(bank_1, bank, pi)
        pitch_1 = np.cross(heading, bank_1)
        pitch_2 = np.cross(heading, bank_2)
        banks.append(bank_1)
        banks.append(bank_2)
        pitches.append(pitch_1)
        pitches.append(pitch_2)
    elif branches == 3:
        bank_1 = normalize(bank+2.824*pitch)
        bank_2 = rotate_vec(bank_1, bank, pi*2/3)
        bank_3 = rotate_vec(bank_1, bank, pi*4/3)
        pitch_1 = np.cross(heading, bank_1)
        pitch_2 = rotate_vec(pitch_1, bank, pi*2/3)
        pitch_3 = rotate_vec(pitch_1, bank, pi*4/3)
        banks.append(bank_1)
        banks.append(bank_2)
        banks.append(bank_3)
        pitches.append(pitch_1)
        pitches.append(pitch_2)
        pitches.append(pitch_3)
    elif branches == 4:
        bank_1 = pitch
        bank_2 = rotate_vec(bank_1, bank, pi*2/3)
        bank_3 = rotate_vec(bank_1, bank, pi*4/3)
        pitch_1 = np.cross(bank, bank_1)
        pitch_2 = np.cross(bank, bank_2)
        pitch_3 = np.cross(bank, bank_3)
        banks.append(bank_1)
        banks.append(bank_2)
        banks.append(bank_3)
        banks.append(bank)
        pitches.append(pitch_1)
        pitches.append(pitch_2)
        pitches.append(pitch_3)
        pitches.append(pitch)
    elif branches == 5:
        bank_1 = pitch
        bank_2 = rotate_vec(bank_1, bank, pi/2)
        bank_3 = rotate_vec(bank_1, bank, pi)
        bank_4 = rotate_vec(bank_1, bank, pi*3/2)
        pitch_1 = np.cross(bank, bank_1)
        pitch_2 = np.cross(bank, bank_2)
        pitch_3 = np.cross(bank, bank_3)
        pitch_4 = np.cross(bank, bank_4)
        banks.append(bank_1)
        banks.append(bank_2)
        banks.append(bank_3)
        banks.append(bank_4)
        banks.append(bank)
        pitches.append(pitch_1)
        pitches.append(pitch_2)
        pitches.append(pitch_3)
        pitches.append(pitch_4)
        pitches.append(pitch)
    return (banks, pitches)

def functional_group_coords(vert, bank, pitch, fg_name, rotate_angle, n_carbon):
    origin = np.array(vert.co)
    if fg_name == 'Benzyl':   # bond_length_CC: 1.4355
        C1 = origin
        C2 = C1 + bank * 0.71775 + pitch * 1.24318
        C3 = C2 + bank * 1.4355
        C4 = C1 + bank * 2.871
        C6 = C1 + bank * 0.71775 - pitch * 1.24318
        C5 = C6 + bank * 1.4355
        coords = [C1, C2, C3, C4, C5, C6]
    elif fg_name == 'Carboxyl':   # bond_length_CO: 1.3125
        C1 = origin
        O1 = C1 + bank * 0.65625 + pitch * 1.13666
        O2 = C1 + bank * 0.65625 - pitch * 1.13666
        coords = [C1, O1, O2]
    elif fg_name == 'Hexatomic Ring':
        C1 = origin
        bank_1 = normalize(bank+2.824*pitch)
        bank_2 = rotate_vec(bank_1, bank, pi*2/3)
        bank_3 = rotate_vec(bank_1, bank, pi*4/3)
        C2 = C1 + bank_2 * 1.4355
        C3 = C2 + bank * 1.4355
        C4 = C3 + bank_3 * 1.4355
        C5 = C4 - bank_2 * 1.4355
        C6 = C5 - bank * 1.4355
        coords = [C1, C2, C3, C4, C5, C6]
    elif fg_name == 'n-Chain':
        C1 = origin
        bank_1 = normalize(bank+2.824*pitch)
        banks = [bank_1, bank]
        coords = [C1]
        for i in range(n_carbon-1):
            new_C = origin + banks[i%2] * 1.4355
            coords.append(new_C)
            origin = new_C
        origin = C1
    coords = [rotate_vec(coord-origin, bank, rotate_angle*pi/180)+origin for coord in coords]
    return coords
# type: ignore

# get symmetry operation component from a string
# ref. International Tables for Crystallography (2006). Vol. A, Section 11.1.1, p.810.
# 11.1. Point coordinates, symmetry operations and their symbols
# BY W.FISCHER AND E.KOCH
def convert_symop_xyz_to_vec(string):  # eg. string = "3/4-x"
    rotate_comp = []
    string = string.strip().lower()
    for symbol in ['x','y','z']:
        i = string.find(symbol)
        value = 0.0 if i == -1 else -1.0 if string[i-1]=='-' else 1.0
        rotate_comp.append(value)
    i = string.find("/")
    transl_comp = 0.0 if i == -1 else float(string[max(i-2,0):i])/float(string[i+1:i+2])
    return(rotate_comp, transl_comp)


# get symmetry operation matrices (W, w) from strings. W is the rotation part, and w is the
# translation part.
def symop_xyz_to_matrix(strings):    # eg. strings = "-x+y, 1/2+y, -z-1/2"
    rotate_matrix = [convert_symop_xyz_to_vec(str)[0] for str in strings.split(",")]
    transl_matrix = [convert_symop_xyz_to_vec(str)[1] for str in strings.split(",")]
    return (rotate_matrix, transl_matrix)

# from one fract_xyz to multi equiv fracts in one cell through symmetry operations.
def fract_symop(fract_xyz, symop_operations):
    sym_fracts = []
    sym_rotations = []
    for symop in symop_operations:
        sym_matrix = symop_xyz_to_matrix(symop)
        npS = np.array(sym_matrix[0])
        npT = np.array(sym_matrix[1])
        npA = np.array(fract_xyz)
        npB = np.matmul(npS,npA) + npT    # Applying symmetry and translation.
        npB = npB % 1.0
        sym_fracts.append(npB)
        sym_rotations.append(npS)
    return sym_fracts, sym_rotations

def transform_U_aniso(u_aniso_tuple, R):
    if u_aniso_tuple is None:
        return None
    U11, U22, U33, U23, U13, U12 = u_aniso_tuple
    U_mat = np.array([
        [U11, U12, U13],
        [U12, U22, U23],
        [U13, U23, U33]
    ])
    R = np.array(R, dtype=float)
    U_new = R @ U_mat @ R.T
    return (U_new[0,0], U_new[1,1], U_new[2,2],
            U_new[1,2], U_new[0,2], U_new[0,1])

def fract_symop_expand(fract_xyz, symop_operations, boundary):
    sym_fracts, _ = fract_symop(fract_xyz, symop_operations)
    sym_fracts = fracts_normalize(sym_fracts, boundary)
    return sym_fracts

def make_cell_matrix(cell_lengths, cell_angles):
    a, b, c = cell_lengths
    alpha, beta, gamma = np.radians(cell_angles)
    v = (cos(alpha)-cos(beta)*cos(gamma)) / sin(gamma)
    M = np.array([
        [a, b*cos(gamma), c*cos(beta)],
        [0, b*sin(gamma), c*v],
        [0, 0, c*sqrt(sin(beta)**2-v**2)]
    ])
    M_inv = np.linalg.inv(M)
    return M, M_inv

def get_cell_lengths_angles(cell_vecs):
        a_vec, b_vec, c_vec = np.array(cell_vecs)
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

def get_crystal_system_from_params(cell_lengths, cell_angles):
    a, b, c = cell_lengths
    alpha, beta, gamma = cell_angles
    eps = 0.5
    if abs(a-b)<eps and abs(b-c)<eps and abs(alpha-90)<eps and abs(beta-90)<eps and abs(gamma-90)<eps:
        return "cubic"
    if abs(a-b)<eps and abs(gamma-120)<eps:
        return "trigonal"
    if abs(a-b)<eps and abs(alpha-90)<eps and abs(beta-90)<eps and abs(gamma-90)<eps:
        return "tetragonal"
    if abs(alpha-90)<eps and abs(beta-90)<eps and abs(gamma-90)<eps:
        return "orthorhombic"
    if abs(alpha-90)>eps or abs(beta-90)>eps or abs(gamma-90)>eps:
        return "monoclinic"
    return "triclinic"

def calc_cell_volume(a, b, c, alpha, beta, gamma):
    al = np.radians(alpha)
    be = np.radians(beta)
    ga = np.radians(gamma)
    vol = a*b*c * np.sqrt(
        1 - np.cos(al)**2 - np.cos(be)**2 - np.cos(ga)**2
        + 2*np.cos(al)*np.cos(be)*np.cos(ga)
    )
    return round(vol, 4)

def fract_to_cartn(fract_xyz,a,b,c,alpha,beta,gamma):
    M, _ = make_cell_matrix((a,b,c),(alpha,beta,gamma))
    cartn_xyz = np.matmul(M, np.array(fract_xyz))
    return cartn_xyz

def cartn_to_fract(cartn_xyz,a,b,c,alpha,beta,gamma):
    _, M_inv = make_cell_matrix((a,b,c),(alpha,beta,gamma))
    fract_xyz = np.matmul(M_inv, np.array(cartn_xyz))
    return fract_xyz


def fracts_normalize(sym_fracts, boundary):
    # coordinates normalization (e.g. 1.15 becomes 0.15, -0.25 becomes 0.75, etc)
    for i in range(len(sym_fracts)):
        if sym_fracts[i][0]<-boundary: sym_fracts[i] = np.array(sym_fracts[i]) + np.array((1,0,0))
        if sym_fracts[i][0]>1+boundary: sym_fracts[i] = np.array(sym_fracts[i]) - np.array((1,0,0))
        if sym_fracts[i][1]<-boundary: sym_fracts[i] = np.array(sym_fracts[i]) + np.array((0,1,0))
        if sym_fracts[i][1]>1+boundary: sym_fracts[i] = np.array(sym_fracts[i]) - np.array((0,1,0))
        if sym_fracts[i][2]<-boundary: sym_fracts[i] = np.array(sym_fracts[i]) + np.array((0,0,1))
        if sym_fracts[i][2]>1+boundary: sym_fracts[i] = np.array(sym_fracts[i]) - np.array((0,0,1))
    
    # remove duplicates (same position)
    sym_fracts = list(set([tuple(fract) for fract in sym_fracts]))
    new_sym_fracts = sym_fracts
    # boundary = 0.0  # the value is between 0.0 and 1.0
    for fract in sym_fracts:
        if fract[0] <= boundary and fract[0] >= -boundary:
            new_fract = (fract[0]+1, fract[1], fract[2])
            new_sym_fracts.append(new_fract)
        if fract[1] <= boundary and fract[1] >= -boundary:
            new_fract = (fract[0], fract[1]+1, fract[2])
            new_sym_fracts.append(new_fract)
        if fract[2] <= boundary and fract[2] >= -boundary:
            new_fract = (fract[0], fract[1], fract[2]+1)
            new_sym_fracts.append(new_fract)
    
    for fract in sym_fracts:
        if fract[0] >= 1-boundary and fract[0] <= 1+boundary:
            new_fract = (fract[0]-1, fract[1], fract[2])
            new_sym_fracts.append(new_fract)
        if fract[1] >= 1-boundary and fract[1] <= 1+boundary:
            new_fract = (fract[0], fract[1]-1, fract[2])
            new_sym_fracts.append(new_fract)
        if fract[2] >= 1-boundary and fract[2] <= 1+boundary:
            new_fract = (fract[0], fract[1], fract[2]-1)
            new_sym_fracts.append(new_fract)

    sym_fracts = list(set([tuple(fract) for fract in new_sym_fracts]))
    return sym_fracts


def deduplicate_fracts(fracts, digits):
    seen = set()
    unique = []
    
    for x, y, z in fracts:
        # 四舍五入到指定位数（默认 4 位小数）
        key = (round(x, digits), round(y, digits), round(z, digits))
        
        if key not in seen:
            seen.add(key)
            unique.append((float(x), float(y), float(z)))
    
    return unique


def compute_thermal_ellipsoid(U_Aniso, U_Iso, cell_lengths, cell_angles, prob_factor=1.54):
    scales = []
    vec1 = []   # 第一个特征向量（主轴1）
    vec2 = []   # 第二个特征向量（主轴2）
    vec3 = []   # 第三个特征向量（主轴3）

    if cell_angles is not None:
        a,b,c = cell_lengths
        M, _ = make_cell_matrix(cell_lengths, cell_angles)
        A = M @ np.diag([1.0/a, 1.0/b, 1.0/c])
    else:
        A = None

    for i in range(len(U_Aniso)):
        u_aniso = U_Aniso[i]
        u_iso = U_Iso[i]

        if u_aniso is not None and len(u_aniso) >= 6:
            U11, U22, U33, U23, U13, U12 = u_aniso[:6]
            det_sign = u_aniso[6] if len(u_aniso) > 6 else 1
            U_mat = np.array([
                [U11, U12, U13],
                [U12, U22, U23],
                [U13, U23, U33]
            ])

            if A is not None:
                U_cart = A @ U_mat @ A.T
            else:
                U_cart = U_mat

            eigvals, eigvecs = np.linalg.eigh(U_cart)
            eigvals = np.clip(eigvals, 0.0, None)
      
            idx = np.argsort(eigvals)[::-1]  # 降序
            eigvals = eigvals[idx]
            eigvecs = eigvecs[:, idx]

            if det_sign < 0:
                eigvecs = -eigvecs

            scale = prob_factor * np.sqrt(eigvals)
            v1 = eigvecs[:, 0]
            v2 = eigvecs[:, 1]
            v3 = eigvecs[:, 2]

        else:
            u_iso = float(u_iso) if u_iso and u_iso > 0 else 0.001
            scale = [prob_factor * np.sqrt(u_iso)] * 3
            v1 = np.array([1, 0, 0])
            v2 = np.array([0, 1, 0])
            v3 = np.array([0, 0, 1])

        scales.extend(scale)
        vec1.extend(v1)
        vec2.extend(v2)
        vec3.extend(v3)

    return scales, vec1, vec2, vec3
