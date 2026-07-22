"""Built-in reader registry and deterministic capability matrix."""

from .ase_adapter import ASE_STRUCTURE_READER
from .cclib_adapter import CCLIB_OUTPUT_READER
from .cjson_adapter import CJSON_READER
from .cube import CUBE_READER
from .gemmi_adapter import CIF_READER
from .iodata_adapter import IODATA_WAVEFUNCTION_READER
from .mol_v2000 import MOL_V2000_READER
from .pymatgen_adapter import PYMATGEN_VASP_GRID_READER
from .pymatgen_electronic import PYMATGEN_VASP_ELECTRONIC_READER
from .qcschema_adapter import QCSCHEMA_READER
from .readers import ReaderDescriptor, ReaderRegistry
from .xyz import XYZ_READER


def builtin_reader_descriptors():
    return tuple(
        sorted(
            (
                ASE_STRUCTURE_READER,
                CCLIB_OUTPUT_READER,
                CIF_READER,
                CJSON_READER,
                CUBE_READER,
                IODATA_WAVEFUNCTION_READER,
                MOL_V2000_READER,
                PYMATGEN_VASP_ELECTRONIC_READER,
                PYMATGEN_VASP_GRID_READER,
                QCSCHEMA_READER,
                XYZ_READER,
            ),
            key=lambda reader: reader.reader_id,
        )
    )


def builtin_reader_registry():
    return ReaderRegistry(builtin_reader_descriptors())


def reader_capability_document(readers=None):
    readers = builtin_reader_descriptors() if readers is None else tuple(readers)
    if any(not isinstance(reader, ReaderDescriptor) for reader in readers):
        raise TypeError("readers must contain ReaderDescriptor values")
    readers = sorted(readers, key=lambda reader: reader.reader_id)
    if len({reader.reader_id for reader in readers}) != len(readers):
        raise ValueError("reader catalog contains duplicate reader IDs")
    return {
        "schema_name": "chemblender_reader_capability_matrix",
        "schema_version": 1,
        "readers": [
            {
                "reader_id": reader.reader_id,
                "reader_version": reader.reader_version,
                "extensions": list(reader.extensions),
                "capabilities": {
                    name: reader.capabilities[name].value
                    for name in sorted(reader.capabilities)
                },
            }
            for reader in readers
        ],
    }
