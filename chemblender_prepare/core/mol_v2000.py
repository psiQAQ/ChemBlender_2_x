"""Deprecated V2000-only compatibility alias for :mod:`formats.mol`."""

from chemblender_prepare.core.formats.mol import _CAPABILITIES
from chemblender_prepare.core.formats.mol import parse_mol_v2000
from chemblender_prepare.core.formats.mol import parse_mol_v2000_request
from chemblender_prepare.core.readers import ReaderDescriptor
from chemblender_prepare.core.readers import SniffMatch
from chemblender_prepare.core.readers import SniffResult


MOL_V2000_REPLACEMENT = "mol"


def sniff_mol_v2000(source, prefix):
    return SniffResult(
        SniffMatch.NONE,
        "deprecated mol-v2000 alias is available only by explicit reader ID; use mol",
    )


MOL_V2000_READER = ReaderDescriptor(
    reader_id="mol-v2000",
    reader_version="2",
    extensions=(".mol",),
    capabilities=_CAPABILITIES,
    priority=10,
    sniff=sniff_mol_v2000,
    parse=parse_mol_v2000,
    parse_request=parse_mol_v2000_request,
)
