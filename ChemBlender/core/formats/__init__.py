"""Low-level native text-format parsers."""

from .cif import CIF_READER, GemmiDependencyError, parse_cif, sniff_cif
from .extxyz import (
    ExtXYZComment,
    ExtXYZFrame,
    ExtXYZMetadataEntry,
    ExtXYZPropertyField,
    ExtXYZSyntaxError,
    iter_extxyz_frames,
    parse_extxyz_comment,
    parse_properties_descriptor,
)
from .mol import MOL_READER, parse_mol, sniff_mol
from .poscar import POSCAR_READER, parse_poscar, sniff_poscar
from .sdf import SDF_READER, parse_sdf, sniff_sdf
from .smiles import SMILES_READER, parse_smiles, parse_smiles_text, sniff_smiles

__all__ = (
    "ExtXYZComment",
    "ExtXYZFrame",
    "ExtXYZMetadataEntry",
    "ExtXYZPropertyField",
    "ExtXYZSyntaxError",
    "CIF_READER",
    "GemmiDependencyError",
    "MOL_READER",
    "POSCAR_READER",
    "SDF_READER",
    "SMILES_READER",
    "iter_extxyz_frames",
    "parse_mol",
    "parse_poscar",
    "parse_cif",
    "parse_sdf",
    "parse_smiles",
    "parse_smiles_text",
    "parse_extxyz_comment",
    "parse_properties_descriptor",
    "sniff_mol",
    "sniff_poscar",
    "sniff_cif",
    "sniff_sdf",
    "sniff_smiles",
)
