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
from .gaussian_input import (
    GAUSSIAN_INPUT_READER,
    parse_gaussian_input,
    sniff_gaussian_input,
)
from .mol import MOL_READER, parse_mol, sniff_mol
from .orca_input import ORCA_INPUT_READER, parse_orca_input, sniff_orca_input
from .poscar import POSCAR_READER, parse_poscar, sniff_poscar
from .sdf import SDF_READER, parse_sdf, sniff_sdf
from .smiles import SMILES_READER, parse_smiles, parse_smiles_text, sniff_smiles

__all__ = (
    "ExtXYZComment",
    "ExtXYZFrame",
    "ExtXYZMetadataEntry",
    "ExtXYZPropertyField",
    "ExtXYZSyntaxError",
    "GAUSSIAN_INPUT_READER",
    "CIF_READER",
    "GemmiDependencyError",
    "MOL_READER",
    "ORCA_INPUT_READER",
    "POSCAR_READER",
    "SDF_READER",
    "SMILES_READER",
    "iter_extxyz_frames",
    "parse_mol",
    "parse_gaussian_input",
    "parse_orca_input",
    "parse_poscar",
    "parse_cif",
    "parse_sdf",
    "parse_smiles",
    "parse_smiles_text",
    "parse_extxyz_comment",
    "parse_properties_descriptor",
    "sniff_mol",
    "sniff_gaussian_input",
    "sniff_orca_input",
    "sniff_poscar",
    "sniff_cif",
    "sniff_sdf",
    "sniff_smiles",
)
