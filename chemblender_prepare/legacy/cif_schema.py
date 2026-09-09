"""Historical RNA schema for private Blender migration processes only.

Field names and defaults are preserved from ChemBlender/read.py at 54ecf4c.
No parser, add-on registration or scientific dependency is loaded here.
"""
from contextlib import contextmanager

import bpy
from bpy.props import StringProperty, FloatProperty, IntProperty, CollectionProperty


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


@contextmanager
def legacy_cif_schema():
    names = ("cif_original", "cif_current")
    if any(hasattr(bpy.types.Object, name) for name in names):
        raise RuntimeError("Legacy migration requires a private factory-startup Blender process")
    registered, attached = [], []
    try:
        for cls in (CIF_Atom, CIF_Structure):
            bpy.utils.register_class(cls)
            registered.append(cls)
        for name in names:
            setattr(bpy.types.Object, name, bpy.props.PointerProperty(type=CIF_Structure))
            attached.append(name)
        yield
    finally:
        for name in reversed(attached):
            delattr(bpy.types.Object, name)
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)
