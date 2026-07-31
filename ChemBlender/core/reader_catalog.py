"""Built-in reader registry and deterministic capability matrix."""

from .ase_adapter import ASE_STRUCTURE_READER
from .cclib_adapter import CCLIB_OUTPUT_READER
from .cjson_adapter import CJSON_READER
from .cube import CUBE_READER
from .formats.cif import CIF_READER
from .formats.extxyz import EXTXYZ_READER
from .formats.mol2 import MOL2_READER
from .formats.pdb import PDB_READER
from .formats.pqr import PQR_READER
from .iodata_adapter import IODATA_WAVEFUNCTION_READER
from .formats.mol import MOL_READER
from .formats.poscar import POSCAR_READER
from .formats.sdf import SDF_READER
from .formats.smiles import SMILES_READER
from .mol_v2000 import MOL_V2000_READER
from .pymatgen_adapter import PYMATGEN_VASP_GRID_READER
from .pymatgen_electronic import PYMATGEN_VASP_ELECTRONIC_READER
from .qcschema_adapter import QCSCHEMA_READER
from .readers import READER_API_VERSION, ReaderDescriptor, ReaderRegistry
from .xyz import XYZ_READER


_OPTIONAL_READER_DEPENDENCIES = {
    "ase-structure": "ase",
    "cclib_output": "cclib",
    "cif": "gemmi",
    "iodata_wavefunction": "iodata",
    "mol": "rdkit",
    "mol-v2000": "rdkit",
    "sdf": "rdkit",
    "smiles": "rdkit",
    "pymatgen-vasp-grid": "pymatgen",
    "pymatgen-vasprun-electronic": "pymatgen",
}

_READER_BASENAMES = {
    "poscar": ("CONTCAR", "POSCAR"),
}

_READER_FIXTURE_FAMILIES = {
    "ase-structure": ("ASE extXYZ", "ASE POSCAR"),
    "cclib_output": ("Gaussian output", "ORCA output"),
    "cif": ("CIF crystal", "CIF disorder", "CIF multi-block"),
    "cjson": ("CJSON result envelope",),
    "cube": ("Gaussian Cube", "multi-dataset Cube"),
    "extxyz": ("ASE extXYZ", "libAtoms extXYZ", "OVITO extXYZ"),
    "iodata_wavefunction": ("FCHK", "Molden"),
    "mol": ("MOL V2000", "MOL V3000"),
    "mol-v2000": ("MOL V2000",),
    "mol2": ("Tripos MOL2", "MOL2 multi-record", "MOL2 substructure"),
    "pdb": ("PDB altloc", "PDB CONECT", "PDB multi-model"),
    "poscar": ("VASP 4", "VASP 5", "POSCAR velocity"),
    "pqr": ("PQR chain", "PQR no-chain"),
    "pymatgen-vasp-grid": ("CHGCAR", "ELFCAR", "LOCPOT", "PARCHG"),
    "pymatgen-vasprun-electronic": ("vasprun.xml band/DOS",),
    "qcschema": ("QCSchema AtomicResult", "QCSchema Molecule"),
    "sdf": ("SDF malformed-record recovery", "SDF multi-record"),
    "smiles": ("SMILES file", "SMILES text"),
    "xyz": ("XYZ single-frame", "XYZ trajectory"),
}

_READER_EXPORTS = {
    "cif": ("cif", "F5", "project_browser", "preview_confirmation"),
    "cjson": ("cjson", "F5", "core", "controlled_envelope"),
    "extxyz": ("extxyz", "F5", "project_browser", "preview_confirmation"),
    "mol": ("mol", "F5", "project_browser", "preview_confirmation"),
    "mol-v2000": ("mol", "F5", "project_browser", "preview_confirmation"),
    "poscar": ("poscar", "F5", "project_browser", "preview_confirmation"),
    "qcschema": ("qcschema", "F5", "core", "source_envelope"),
    "sdf": ("sdf", "F5", "project_browser", "preview_confirmation"),
    "smiles": ("smiles", "F5", "project_browser", "preview_confirmation"),
    "xyz": ("xyz", "F5", "project_browser", "lossless"),
}


def _export_document(reader_id):
    format_id, maturity, execution_mode, loss_policy = _READER_EXPORTS.get(
        reader_id,
        (None, "F0", "none", "not_available"),
    )
    return {
        "format_id": format_id,
        "maturity": maturity,
        "execution_mode": execution_mode,
        "loss_policy": loss_policy,
    }


def builtin_reader_descriptors():
    return tuple(
        sorted(
            (
                ASE_STRUCTURE_READER,
                CCLIB_OUTPUT_READER,
                CIF_READER,
                CJSON_READER,
                CUBE_READER,
                EXTXYZ_READER,
                IODATA_WAVEFUNCTION_READER,
                MOL_READER,
                MOL2_READER,
                MOL_V2000_READER,
                PDB_READER,
                PQR_READER,
                POSCAR_READER,
                SDF_READER,
                SMILES_READER,
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
        "schema_version": 2,
        "reader_api_version": READER_API_VERSION,
        "readers": [
            {
                "plugin_id": "chemblender.builtin",
                "reader_id": reader.reader_id,
                "reader_version": reader.reader_version,
                "reader_api_version": READER_API_VERSION,
                "execution_mode": "built_in",
                "availability_contract": (
                    {
                        "kind": "python_module",
                        "module": _OPTIONAL_READER_DEPENDENCIES[reader.reader_id],
                    }
                    if reader.reader_id in _OPTIONAL_READER_DEPENDENCIES
                    else {"kind": "always"}
                ),
                "extensions": list(reader.extensions),
                "basenames": list(_READER_BASENAMES.get(reader.reader_id, ())),
                "capabilities": {
                    name: reader.capabilities[name].value
                    for name in sorted(reader.capabilities)
                },
                "export": _export_document(reader.reader_id),
                "fixture_families": list(
                    _READER_FIXTURE_FAMILIES.get(
                        reader.reader_id,
                        (reader.reader_id,),
                    )
                ),
            }
            for reader in readers
        ],
    }
