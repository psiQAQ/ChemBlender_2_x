"""Compatibility facade for the native CIF reader."""

from .formats.cif import (
    ADAPTER_VERSION,
    CIF_READER,
    GemmiDependencyError,
    parse_cif,
    sniff_cif,
)

__all__ = (
    "ADAPTER_VERSION",
    "CIF_READER",
    "GemmiDependencyError",
    "parse_cif",
    "sniff_cif",
)
