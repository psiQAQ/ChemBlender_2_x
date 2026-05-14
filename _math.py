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
    for symop in symop_operations:
        sym_matrix = symop_xyz_to_matrix(symop)
        npS = np.array(sym_matrix[0])
        npT = np.array(sym_matrix[1])
        npA = np.array(fract_xyz)
        npB = np.matmul(npS,npA) + npT    # Applying symmetry and translation.
        npB = npB % 1.0
        sym_fracts.append(npB)
    return sym_fracts

def fract_symop_expand(fract_xyz, symop_operations, boundary):
    sym_fracts = fract_symop(fract_xyz, symop_operations)
    sym_fracts = fracts_normalize(sym_fracts, boundary)
    sym_fracts = fracts_normalize(sym_fracts, boundary)
    return sym_fracts


def fract_to_cartn(fract_xyz,a,b,c,alpha,beta,gamma):
    alpha = np.deg2rad(alpha)
    beta = np.deg2rad(beta)
    gamma = np.deg2rad(gamma)
    v = (cos(alpha)-cos(beta)*cos(gamma))/sin(gamma)
    M = np.array([[a, b*cos(gamma), c*cos(beta)],
                [0, b*sin(gamma), c*v],
                [0, 0, c*sqrt(pow(sin(beta),2)-v*v)]])
    cartn_xyz = np.matmul(M, np.array(fract_xyz))
    return cartn_xyz

def cartn_to_fract(cartn_xyz,a,b,c,alpha,beta,gamma):
    alpha = np.deg2rad(alpha)
    beta = np.deg2rad(beta)
    gamma = np.deg2rad(gamma)
    v = (cos(alpha)-cos(beta)*cos(gamma))/sin(gamma)
    M = np.array([[a, b*cos(gamma), c*cos(beta)],
                    [0, b*sin(gamma), c*v],
                    [0, 0, c*sqrt(pow(sin(beta),2)-v*v)]])
    inv_M = np.linalg.inv(M)
    fract_xyz = np.matmul(inv_M, np.array(cartn_xyz))
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
        if fract[1] <= boundary and fract[0] >= -boundary:
            new_fract = (fract[0], fract[1]+1, fract[2])
            new_sym_fracts.append(new_fract)
        if fract[2] <= boundary and fract[0] >= -boundary:
            new_fract = (fract[0], fract[1], fract[2]+1)
            new_sym_fracts.append(new_fract)
    
    for fract in sym_fracts:
        if fract[0] >= 1-boundary and fract[0] <= 1+boundary:
            new_fract = (fract[0]-1, fract[1], fract[2])
            new_sym_fracts.append(new_fract)
        if fract[1] >= 1-boundary and fract[0] <= 1+boundary:
            new_fract = (fract[0], fract[1]-1, fract[2])
            new_sym_fracts.append(new_fract)
        if fract[2] >= 1-boundary and fract[0] <= 1+boundary:
            new_fract = (fract[0], fract[1], fract[2]-1)
            new_sym_fracts.append(new_fract)

    sym_fracts = list(set([tuple(fract) for fract in new_sym_fracts]))
    # print(sym_fracts)
    return sym_fracts


def deduplicate_fracts(fracts, digits):
    """
    按四舍五入 + 误差范围去重
    相同位置的原子只保留一个
    """
    seen = set()
    unique = []
    
    for x, y, z in fracts:
        # 四舍五入到指定位数（默认 4 位小数）
        key = (round(x, digits), round(y, digits), round(z, digits))
        
        if key not in seen:
            seen.add(key)
            unique.append((float(x), float(y), float(z)))
    
    return unique