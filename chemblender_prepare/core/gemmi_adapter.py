"""Compatibility facade for the native CIF reader."""

from chemblender_prepare.core.formats.cif import ADAPTER_VERSION
from chemblender_prepare.core.formats.cif import CIF_READER
from chemblender_prepare.core.formats.cif import GemmiDependencyError
from chemblender_prepare.core.formats.cif import numeric_symmetry_operations
from chemblender_prepare.core.formats.cif import parse_cif
from chemblender_prepare.core.formats.cif import sniff_cif

__all__ = (
    "ADAPTER_VERSION",
    "CIF_READER",
    "GemmiDependencyError",
    "numeric_symmetry_operations",
    "parse_cif",
    "sniff_cif",
)
