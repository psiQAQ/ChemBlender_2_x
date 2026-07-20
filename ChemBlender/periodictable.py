import bpy
language = 1 if 'zh_HAN' in bpy.context.preferences.view.language else 0

periodic_table_data = {
    1: {"symbol": "H", "name": "氢", "ename":"Hydrogen", "mass": 1.008, "radius": 120, "electron": "1s¹"},
    2: {"symbol": "He", "name": "氦", "ename":"Helium", "mass": 4.0026, "radius": 140, "electron": "1s²"},
    3: {"symbol": "Li", "name": "锂", "ename":"Lithium", "mass": 6.94, "radius": 182, "electron": "[He] 2s¹"},
    4: {"symbol": "Be", "name": "铍", "ename":"Beryllium", "mass": 9.0122, "radius": 153, "electron": "[He] 2s²"},
    5: {"symbol": "B", "name": "硼", "ename":"Boron", "mass": 10.81, "radius": 192, "electron": "[He] 2s² 2p¹"},
    6: {"symbol": "C", "name": "碳", "ename":"Carbon", "mass": 12.011, "radius": 170, "electron": "[He] 2s² 2p²"},
    7: {"symbol": "N", "name": "氮", "ename":"Nitrogen", "mass": 14.007, "radius": 155, "electron": "[He] 2s² 2p³"},
    8: {"symbol": "O", "name": "氧", "ename":"Oxygen", "mass": 15.999, "radius": 152, "electron": "[He] 2s² 2p⁴"},
    9: {"symbol": "F", "name": "氟", "ename":"Fluorine", "mass": 18.998, "radius": 147, "electron": "[He] 2s² 2p⁵"},
    10: {"symbol": "Ne", "name": "氖", "ename":"Neon", "mass": 20.180, "radius": 154, "electron": "[He] 2s² 2p⁶"},
    11: {"symbol": "Na", "name": "钠", "ename":"Sodium", "mass": 22.990, "radius": 227, "electron": "[Ne] 3s¹"},
    12: {"symbol": "Mg", "name": "镁", "ename":"Magnesium", "mass": 24.305, "radius": 173, "electron": "[Ne] 3s²"},
    13: {"symbol": "Al", "name": "铝", "ename":"Aluminum", "mass": 26.982, "radius": 184, "electron": "[Ne] 3s² 3p¹"},
    14: {"symbol": "Si", "name": "硅", "ename":"Silicon", "mass": 28.085, "radius": 210, "electron": "[Ne] 3s² 3p²"},
    15: {"symbol": "P", "name": "磷", "ename":"Phosphorus", "mass": 30.974, "radius": 180, "electron": "[Ne] 3s² 3p³"},
    16: {"symbol": "S", "name": "硫", "ename":"Sulfur", "mass": 32.06, "radius": 180, "electron": "[Ne] 3s² 3p⁴"},
    17: {"symbol": "Cl", "name": "氯", "ename":"Chlorine", "mass": 35.45, "radius": 175, "electron": "[Ne] 3s² 3p⁵"},
    18: {"symbol": "Ar", "name": "氩", "ename":"Argon", "mass": 39.95, "radius": 188, "electron": "[Ne] 3s² 3p⁶"},
    19: {"symbol": "K", "name": "钾", "ename":"Potassium", "mass": 39.10, "radius": 275, "electron": "[Ar] 4s¹"},
    20: {"symbol": "Ca", "name": "钙", "ename":"Calcium", "mass": 40.08, "radius": 231, "electron": "[Ar] 4s²"},
    21: {"symbol": "Sc", "name": "钪", "ename":"Scandium", "mass": 44.96, "radius": 211, "electron": "[Ar] 3d¹ 4s²"},
    22: {"symbol": "Ti", "name": "钛", "ename":"Titanium", "mass": 47.87, "radius": 193, "electron": "[Ar] 3d² 4s²"},
    23: {"symbol": "V", "name": "钒", "ename":"Vanadium", "mass": 50.94, "radius": 192, "electron": "[Ar] 3d³ 4s²"},
    24: {"symbol": "Cr", "name": "铬", "ename":"Chromium", "mass": 52.00, "radius": 185, "electron": "[Ar] 3d⁵ 4s¹"},
    25: {"symbol": "Mn", "name": "锰", "ename":"Manganese", "mass": 54.94, "radius": 185, "electron": "[Ar] 3d⁵ 4s²"},
    26: {"symbol": "Fe", "name": "铁", "ename":"Iron", "mass": 55.85, "radius": 180, "electron": "[Ar] 3d⁶ 4s²"},
    27: {"symbol": "Co", "name": "钴", "ename":"Cobalt", "mass": 58.93, "radius": 178, "electron": "[Ar] 3d⁷ 4s²"},
    28: {"symbol": "Ni", "name": "镍", "ename":"Nickel", "mass": 58.69, "radius": 163, "electron": "[Ar] 3d⁸ 4s²"},
    29: {"symbol": "Cu", "name": "铜", "ename":"Copper", "mass": 63.55, "radius": 140, "electron": "[Ar] 3d¹⁰ 4s¹"},
    30: {"symbol": "Zn", "name": "锌", "ename":"Zinc", "mass": 65.38, "radius": 139, "electron": "[Ar] 3d¹⁰ 4s²"},
    31: {"symbol": "Ga", "name": "镓", "ename":"Gallium", "mass": 69.72, "radius": 187, "electron": "[Ar] 3d¹⁰ 4s² 4p¹"},
    32: {"symbol": "Ge", "name": "锗", "ename":"Germanium", "mass": 72.63, "radius": 211, "electron": "[Ar] 3d¹⁰ 4s² 4p²"},
    33: {"symbol": "As", "name": "砷", "ename":"Arsenic", "mass": 74.92, "radius": 185, "electron": "[Ar] 3d¹⁰ 4s² 4p³"},
    34: {"symbol": "Se", "name": "硒", "ename":"Selenium", "mass": 78.97, "radius": 190, "electron": "[Ar] 3d¹⁰ 4s² 4p⁴"},
    35: {"symbol": "Br", "name": "溴", "ename":"Bromine", "mass": 79.90, "radius": 185, "electron": "[Ar] 3d¹⁰ 4s² 4p⁵"},
    36: {"symbol": "Kr", "name": "氪", "ename":"Krypton", "mass": 83.80, "radius": 202, "electron": "[Ar] 3d¹⁰ 4s² 4p⁶"},
    37: {"symbol": "Rb", "name": "铷", "ename":"Rubidium", "mass": 85.47, "radius": 303, "electron": "[Kr] 5s¹"},
    38: {"symbol": "Sr", "name": "锶", "ename":"Strontium", "mass": 87.62, "radius": 249, "electron": "[Kr] 5s²"},
    39: {"symbol": "Y", "name": "钇", "ename":"Yttrium", "mass": 88.91, "radius": 223, "electron": "[Kr] 4d¹ 5s²"},
    40: {"symbol": "Zr", "name": "锆", "ename":"Zirconium", "mass": 91.22, "radius": 206, "electron": "[Kr] 4d² 5s²"},
    41: {"symbol": "Nb", "name": "铌", "ename":"Niobium", "mass": 92.91, "radius": 198, "electron": "[Kr] 4d⁴ 5s¹"},
    42: {"symbol": "Mo", "name": "钼", "ename":"Molybdenum", "mass": 95.95, "radius": 190, "electron": "[Kr] 4d⁵ 5s¹"},
    43: {"symbol": "Tc", "name": "锝", "ename":"Technetium", "mass": 98.00, "radius": 183, "electron": "[Kr] 4d⁵ 5s²"},
    44: {"symbol": "Ru", "name": "钌", "ename":"Ruthenium", "mass": 101.1, "radius": 178, "electron": "[Kr] 4d⁷ 5s¹"},
    45: {"symbol": "Rh", "name": "铑", "ename":"Rhodium", "mass": 102.9, "radius": 173, "electron": "[Kr] 4d⁸ 5s¹"},
    46: {"symbol": "Pd", "name": "钯", "ename":"Palladium", "mass": 106.4, "radius": 169, "electron": "[Kr] 4d¹⁰"},
    47: {"symbol": "Ag", "name": "银", "ename":"Silver", "mass": 107.9, "radius": 165, "electron": "[Kr] 4d¹⁰ 5s¹"},
    48: {"symbol": "Cd", "name": "镉", "ename":"Cadmium", "mass": 112.4, "radius": 161, "electron": "[Kr] 4d¹⁰ 5s²"},
    49: {"symbol": "In", "name": "铟", "ename":"Indium", "mass": 114.8, "radius": 211, "electron": "[Kr] 4d¹⁰ 5s² 5p¹"},
    50: {"symbol": "Sn", "name": "锡", "ename":"Tin", "mass": 118.7, "radius": 217, "electron": "[Kr] 4d¹⁰ 5s² 5p²"},
    51: {"symbol": "Sb", "name": "锑", "ename":"Antimony", "mass": 121.8, "radius": 206, "electron": "[Kr] 4d¹⁰ 5s² 5p³"},
    52: {"symbol": "Te", "name": "碲", "ename":"Tellurium", "mass": 127.6, "radius": 206, "electron": "[Kr] 4d¹⁰ 5s² 5p⁴"},
    53: {"symbol": "I", "name": "碘", "ename":"Iodine", "mass": 126.9, "radius": 198, "electron": "[Kr] 4d¹⁰ 5s² 5p⁵"},
    54: {"symbol": "Xe", "name": "氙", "ename":"Xenon", "mass": 131.3, "radius": 216, "electron": "[Kr] 4d¹⁰ 5s² 5p⁶"},
    55: {"symbol": "Cs", "name": "铯", "ename":"Cesium", "mass": 132.9, "radius": 343, "electron": "[Xe] 6s¹"},
    56: {"symbol": "Ba", "name": "钡", "ename":"Barium", "mass": 137.3, "radius": 268, "electron": "[Xe] 6s²"},
    57: {"symbol": "La", "name": "镧", "ename":"Lanthanum", "mass": 138.9, "radius": 243, "electron": "[Xe] 5d¹ 6s²"},
    58: {"symbol": "Ce", "name": "铈", "ename":"Cerium", "mass": 140.1, "radius": 242, "electron": "[Xe] 4f¹ 5d¹ 6s²"},
    59: {"symbol": "Pr", "name": "镨", "ename":"Praseodymium", "mass": 140.9, "radius": 240, "electron": "[Xe] 4f³ 6s²"},
    60: {"symbol": "Nd", "name": "钕", "ename":"Neodymium", "mass": 144.2, "radius": 239, "electron": "[Xe] 4f⁴ 6s²"},
    61: {"symbol": "Pm", "name": "钷", "ename":"Promethium", "mass": 145.0, "radius": 238, "electron": "[Xe] 4f⁵ 6s²"},
    62: {"symbol": "Sm", "name": "钐", "ename":"Samarium", "mass": 150.4, "radius": 236, "electron": "[Xe] 4f⁶ 6s²"},
    63: {"symbol": "Eu", "name": "铕", "ename":"Europium", "mass": 152.0, "radius": 235, "electron": "[Xe] 4f⁷ 6s²"},
    64: {"symbol": "Gd", "name": "钆", "ename":"Gadolinium", "mass": 157.3, "radius": 234, "electron": "[Xe] 4f⁷ 5d¹ 6s²"},
    65: {"symbol": "Tb", "name": "铽", "ename":"Terbium", "mass": 158.9, "radius": 233, "electron": "[Xe] 4f⁹ 6s²"},
    66: {"symbol": "Dy", "name": "镝", "ename":"Dysprosium", "mass": 162.5, "radius": 231, "electron": "[Xe] 4f¹⁰ 6s²"},
    67: {"symbol": "Ho", "name": "钬", "ename":"Holmium", "mass": 164.9, "radius": 230, "electron": "[Xe] 4f¹¹ 6s²"},
    68: {"symbol": "Er", "name": "铒", "ename":"Erbium", "mass": 167.3, "radius": 229, "electron": "[Xe] 4f¹² 6s²"},
    69: {"symbol": "Tm", "name": "铥", "ename":"Thulium", "mass": 168.9, "radius": 227, "electron": "[Xe] 4f¹³ 6s²"},
    70: {"symbol": "Yb", "name": "镱", "ename":"Ytterbium", "mass": 173.1, "radius": 226, "electron": "[Xe] 4f¹⁴ 6s²"},
    71: {"symbol": "Lu", "name": "镥", "ename":"Lutetium", "mass": 175.0, "radius": 225, "electron": "[Xe] 4f¹⁴ 5d¹ 6s²"},
    72: {"symbol": "Hf", "name": "铪", "ename":"Hafnium", "mass": 178.5, "radius": 208, "electron": "[Xe] 4f¹⁴ 5d² 6s²"},
    73: {"symbol": "Ta", "name": "钽", "ename":"Tantalum", "mass": 181.0, "radius": 203, "electron": "[Xe] 4f¹⁴ 5d³ 6s²"},
    74: {"symbol": "W", "name": "钨", "ename":"Tungsten", "mass": 183.8, "radius": 193, "electron": "[Xe] 4f¹⁴ 5d⁴ 6s²"},
    75: {"symbol": "Re", "name": "铼", "ename":"Rhenium", "mass": 186.2, "radius": 188, "electron": "[Xe] 4f¹⁴ 5d⁵ 6s²"},
    76: {"symbol": "Os", "name": "锇", "ename":"Osmium", "mass": 190.2, "radius": 185, "electron": "[Xe] 4f¹⁴ 5d⁶ 6s²"},
    77: {"symbol": "Ir", "name": "铱", "ename":"Iridium", "mass": 192.2, "radius": 180, "electron": "[Xe] 4f¹⁴ 5d⁷ 6s²"},
    78: {"symbol": "Pt", "name": "铂", "ename":"Platinum", "mass": 195.1, "radius": 177, "electron": "[Xe] 4f¹⁴ 5d⁹ 6s¹"},
    79: {"symbol": "Au", "name": "金", "ename":"Gold", "mass": 197.0, "radius": 174, "electron": "[Xe] 4f¹⁴ 5d¹⁰ 6s¹"},
    80: {"symbol": "Hg", "name": "汞", "ename":"Mercury", "mass": 200.6, "radius": 171, "electron": "[Xe] 4f¹⁴ 5d¹⁰ 6s²"},
    81: {"symbol": "Tl", "name": "铊", "ename":"Thallium", "mass": 204.4, "radius": 215, "electron": "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p¹"},
    82: {"symbol": "Pb", "name": "铅", "ename":"Lead", "mass": 207.2, "radius": 202, "electron": "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p²"},
    83: {"symbol": "Bi", "name": "铋", "ename":"Bismuth", "mass": 209.0, "radius": 207, "electron": "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p³"},
    84: {"symbol": "Po", "name": "钋", "ename":"Polonium", "mass": 209.0, "radius": 197, "electron": "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p⁴"},
    85: {"symbol": "At", "name": "砹", "ename":"Astatine", "mass": 210.0, "radius": 196, "electron": "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p⁵"},
    86: {"symbol": "Rn", "name": "氡", "ename":"Radon", "mass": 222.0, "radius": 220, "electron": "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p⁶"},
    87: {"symbol": "Fr", "name": "钫", "ename":"Francium", "mass": 223.0, "radius": 348, "electron": "[Rn] 7s¹"},
    88: {"symbol": "Ra", "name": "镭", "ename":"Radium", "mass": 226.0, "radius": 283, "electron": "[Rn] 7s²"},
    89: {"symbol": "Ac", "name": "锕", "ename":"Actinium", "mass": 227.0, "radius": 258, "electron": "[Rn] 6d¹ 7s²"},
    90: {"symbol": "Th", "name": "钍", "ename":"Thorium", "mass": 232.0, "radius": 257, "electron": "[Rn] 6d² 7s²"},
    91: {"symbol": "Pa", "name": "镤", "ename":"Protactinium", "mass": 231.0, "radius": 253, "electron": "[Rn] 5f² 6d¹ 7s²"},
    92: {"symbol": "U", "name": "铀", "ename":"Uranium", "mass": 238.0, "radius": 240, "electron": "[Rn] 5f³ 6d¹ 7s²"},
    93: {"symbol": "Np", "name": "镎", "ename":"Neptunium", "mass": 237.0, "radius": 247, "electron": "[Rn] 5f⁴ 6d¹ 7s²"},
    94: {"symbol": "Pu", "name": "钚", "ename":"Plutonium", "mass": 244.0, "radius": 244, "electron": "[Rn] 5f⁶ 7s²"},
    95: {"symbol": "Am", "name": "镅", "ename":"Americium", "mass": 243.0, "radius": 244, "electron": "[Rn] 5f⁷ 7s²"},
    96: {"symbol": "Cm", "name": "锔", "ename":"Curium", "mass": 247.0, "radius": 245, "electron": "[Rn] 5f⁷ 6d¹ 7s²"},
    97: {"symbol": "Bk", "name": "锫", "ename":"Berkelium", "mass": 247.0, "radius": 243, "electron": "[Rn] 5f⁹ 7s²"},
    98: {"symbol": "Cf", "name": "锎", "ename":"Californium", "mass": 251.0, "radius": 242, "electron": "[Rn] 5f¹⁰ 7s²"},
    99: {"symbol": "Es", "name": "锿", "ename":"Einsteinium", "mass": 252.0, "radius": 241, "electron": "[Rn] 5f¹¹ 7s²"},
    100: {"symbol": "Fm", "name": "镄", "ename":"Fermium", "mass": 257.0, "radius": 240, "electron": "[Rn] 5f¹² 7s²"},
    101: {"symbol": "Md", "name": "钔", "ename":"Mendelevium", "mass": 258.0, "radius": 239, "electron": "[Rn] 5f¹³ 7s²"},
    102: {"symbol": "No", "name": "锘", "ename":"Nobelium", "mass": 259.0, "radius": 238, "electron": "[Rn] 5f¹⁴ 7s²"},
    103: {"symbol": "Lr", "name": "铹", "ename":"Lawrencium", "mass": 262.0, "radius": 237, "electron": "[Rn] 5f¹⁴ 6d¹ 7s²"},
    104: {"symbol": "Rf", "name": "𬬻", "ename":"Rutherfordium", "mass": 267.0, "radius": 230, "electron": "[Rn] 5f¹⁴ 6d² 7s²"},
    105: {"symbol": "Db", "name": "𬭊", "ename":"Dubnium", "mass": 270.0, "radius": 227, "electron": "[Rn] 5f¹⁴ 6d³ 7s²"},
    106: {"symbol": "Sg", "name": "𬭳", "ename":"Seaborgium", "mass": 271.0, "radius": 225, "electron": "[Rn] 5f¹⁴ 6d⁴ 7s²"},
    107: {"symbol": "Bh", "name": "𬭛", "ename":"Bohrium", "mass": 270.0, "radius": 220, "electron": "[Rn] 5f¹⁴ 6d⁵ 7s²"},
    108: {"symbol": "Hs", "name": "𬭶", "ename":"Hassium", "mass": 277.0, "radius": 216, "electron": "[Rn] 5f¹⁴ 6d⁶ 7s²"},
    109: {"symbol": "Mt", "name": "鿏", "ename":"Meitnerium", "mass": 276.0, "radius": 214, "electron": "[Rn] 5f¹⁴ 6d⁷ 7s²"},
    110: {"symbol": "Ds", "name": "𫟼", "ename":"Darmstadtium", "mass": 281.0, "radius": 212, "electron": "[Rn] 5f¹⁴ 6d⁸ 7s²"},
    111: {"symbol": "Rg", "name": "𬬭", "ename":"Roentgenium", "mass": 280.0, "radius": 210, "electron": "[Rn] 5f¹⁴ 6d⁹ 7s²"},
    112: {"symbol": "Cn", "name": "鎶", "ename":"Copernicium", "mass": 285.0, "radius": 208, "electron": "[Rn] 5f¹⁴ 6d¹⁰ 7s²"},
    113: {"symbol": "Nh", "name": "鉨", "ename":"Nihonium", "mass": 284.0, "radius": 206, "electron": "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p¹"},
    114: {"symbol": "Fl", "name": "鈇", "ename":"Flerovium", "mass": 289.0, "radius": 204, "electron": "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p²"},
    115: {"symbol": "Mc", "name": "镆", "ename":"Moscovium", "mass": 288.0, "radius": 202, "electron": "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p³"},
    116: {"symbol": "Lv", "name": "𫟷", "ename":"Livermorium", "mass": 293.0, "radius": 200, "electron": "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p⁴"},
    117: {"symbol": "Ts", "name": "鿬", "ename":"Tennessine", "mass": 294.0, "radius": 198, "electron": "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p⁵"},
    118: {"symbol": "Og", "name": "鿫", "ename":"Oganesson", "mass": 294.0, "radius": 197, "electron": "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p⁶"},
}

class CHEMBLENDER_OT_CopyText(bpy.types.Operator):
    bl_idname = "chem.copy_text"
    bl_label = "Copy"
    bl_description = "Copy text to clipboard"
    
    text: bpy.props.StringProperty()
    
    def execute(self, context):
        context.window_manager.clipboard = self.text
        self.report({'INFO'}, f"Copied: {self.text}")
        return {'FINISHED'}


# 全局属性
bpy.types.WindowManager.active_atomic_num = bpy.props.IntProperty(default=6)


# 打开周期表
class CHEMBLENDER_OT_OpenPeriodicTable(bpy.types.Operator):
    bl_idname = "chem.open_periodic_table"
    bl_label = "🧪 Periodic Table"
    bl_description = "打开元素周期表" if language else "Open Periodic Table"


    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_popup(self, width=650)

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        z_cur = wm.active_atomic_num
        data = periodic_table_data.get(z_cur, None)

        row = layout.row()
        row.label(text="ChemBlender Periodic Table", icon='SHADERFX')

        row.separator()
        text="当前元素：" if language else f"Current Element: "
        row.label(text=text+f"{data['symbol']}", icon='DOT')

        layout.separator()
        box = layout.box()

        periods = [
            [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
            [3,4,0,0,0,0,0,0,0,0,0,0,5,6,7,8,9,10],
            [11,12,0,0,0,0,0,0,0,0,0,0,13,14,15,16,17,18],
            [19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36],
            [37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54],
            [55,56,57,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86],
            [87,88,89,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118],
            [0,0,58,59,60,61,62,63,64,65,66,67,68,69,70,71,0,0],
            [0,0,90,91,92,93,94,95,96,97,98,99,100,101,102,103,0,0]
        ]

        for period in periods:
            row = box.row()
            
            for num in period:
                if num == 0:
                    row.label(text="")
                else:
                    d = periodic_table_data[num]
                    is_selected = (num == z_cur)
                    btn = row.operator("chem.select_element", text=d["symbol"], emboss=True, depress=is_selected)
                    btn.atomic_num = num

        layout.separator()
        info_box = layout.box()
        # 只改动这一行：标题+右侧新增(Copy All)按钮，下面内容完全原样保留
        head_row = info_box.row(align=True)
        head_row.alignment = 'LEFT'
        if language:
            head_row.label(text=f"📊 元素详情：{data['name']}", icon='INFO')
            all_content = f"""元素：{data['name']}({data['symbol']})
原子序数：{z_cur}
原子量：{data['mass']}
范德华半径：{data['radius']} pm
电子排布：{data['electron']}"""
        else:
            head_row.label(text=f"📊 Element Details: {data['ename']}", icon='INFO')
            all_content = f"""Element: {data['ename']}({data['symbol']})
Atomic No.: {z_cur}
Atomic Mass: {data['mass']}
vdW Radius: {data['radius']} pm
Electron Config.: {data['electron']}"""
        head_row.operator("chem.copy_text", text="📋", emboss=False).text = all_content

        # =====下方四条属性【完全沿用你原版，位置、间距、复制图标丝毫未改】=====
        col = info_box.column()
        if language:
            row = col.row(align=True)
            row.alignment = 'LEFT'
            row.label(text=f"原子序数： {z_cur}")
            row.operator("chem.copy_text", text="📋", emboss=False).text = f"原子序数：{z_cur}"

            row = col.row(align=True)
            row.alignment = 'LEFT'
            row.label(text=f"原子量： {data['mass']}")
            row.operator("chem.copy_text", text="📋", emboss=False).text = f"原子量：{data['mass']}"

            row = col.row(align=True)
            row.alignment = 'LEFT'
            row.label(text=f"范德华半径： {data['radius']} pm")
            row.operator("chem.copy_text", text="📋", emboss=False).text = f"范德华半径：{data['radius']} pm"

            row = col.row(align=True)
            row.alignment = 'LEFT'
            row.label(text=f"电子排布： {data['electron']}")
            row.operator("chem.copy_text", text="📋", emboss=False).text = f"电子排布：{data['electron']}"

        else:
            row = col.row(align=True)
            row.alignment = 'LEFT'
            row.label(text=f"Atomic No.:  {z_cur}")
            row.operator("chem.copy_text", text="📋", emboss=False).text = f"Atomic Number: {z_cur}"

            row = col.row(align=True)
            row.alignment = 'LEFT'
            row.label(text=f"Atomic Mass:  {data['mass']}")
            row.operator("chem.copy_text", text="📋", emboss=False).text = f"Atomic Mass: {data['mass']}"

            row = col.row(align=True)
            row.alignment = 'LEFT'
            row.label(text=f"vdW Radius:  {data['radius']} pm")
            row.operator("chem.copy_text", text="📋", emboss=False).text = f"Van der Waals Radius: {data['radius']} pm"

            row = col.row(align=True)
            row.alignment = 'LEFT'
            row.label(text=f"Electron Config.:  {data['electron']}")
            row.operator("chem.copy_text", text="📋", emboss=False).text = f"Electron Configuration: {data['electron']}"

    def execute(self, context):
        return {'FINISHED'}


# 选择元素
class CHEMBLENDER_OT_SelectElement(bpy.types.Operator):
    bl_idname = "chem.select_element"
    bl_label = "选择元素" if language else "Select Element"
    atomic_num: bpy.props.IntProperty()

    def execute(self, context):
        context.window_manager.active_atomic_num = self.atomic_num
        return {'FINISHED'}


class CHEMBLENDER_PT_PeriodicPanel(bpy.types.Panel):
    bl_label = "ChemBlender Informatics"
    bl_idname = "CHEMBLENDER_PT_periodic"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Periodic Table'

    def draw(self, context):
        layout = self.layout
        layout.operator("chem.open_periodic_table", icon='FILE_TEXT')