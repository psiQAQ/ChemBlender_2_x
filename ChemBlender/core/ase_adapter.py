import hashlib
from pathlib import Path
from uuid import uuid4

from .model import (
    ArrayData,
    AtomicProperty,
    DatasetStatus,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    PeriodicSiteData,
    ProvenanceRecord,
    Structure,
)
from .readers import CapabilitySupport, ReaderDescriptor, SniffMatch, SniffResult


ADAPTER_VERSION = "1"
_CORE_ARRAYS = {"numbers", "positions"}


class ASEDependencyError(RuntimeError):
    pass


def _ase():
    try:
        import ase
        import ase.io
    except ModuleNotFoundError as error:
        if error.name == "ase" or (error.name and error.name.startswith("ase.")):
            raise ASEDependencyError(
                "ASE is required in the ChemBlender core/worker environment"
            ) from error
        raise
    return ase


def sniff_ase_structure(source: Path, prefix: bytes) -> SniffResult:
    name = source.name.upper()
    if name in {"POSCAR", "CONTCAR"}:
        return SniffResult(SniffMatch.EXACT, f"canonical VASP {name} filename")
    try:
        lines = prefix.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        return SniffResult(SniffMatch.NONE, "content is not UTF-8 structure text")
    if len(lines) >= 2 and "Properties=" in lines[1] and "Lattice=" in lines[1]:
        return SniffResult(SniffMatch.EXACT, "extended XYZ lattice and properties")
    if source.suffix.lower() in {".vasp", ".poscar", ".contcar"} and len(lines) >= 8:
        try:
            float(lines[1].split()[0])
            for line in lines[2:5]:
                if len(line.split()) != 3:
                    raise ValueError
                tuple(float(value) for value in line.split())
        except (ValueError, IndexError):
            return SniffResult(SniffMatch.NONE, "missing POSCAR scale or lattice")
        return SniffResult(SniffMatch.EXACT, "POSCAR scale and three lattice vectors")
    return SniffResult(SniffMatch.NONE, "missing ASE periodic structure markers")


def _site_labels(symbols):
    counts = {}
    labels = []
    for symbol in symbols:
        counts[symbol] = counts.get(symbol, 0) + 1
        labels.append(f"{symbol}{counts[symbol]}")
    return tuple(labels)


def _fixed_axes(atoms):
    import numpy

    from ase.constraints import FixAtoms, FixScaled

    fixed = numpy.zeros((len(atoms), 3), dtype=bool)
    unsupported = []
    for constraint in atoms.constraints:
        if isinstance(constraint, FixScaled):
            fixed[numpy.asarray(constraint.index, dtype=int)] |= numpy.asarray(
                constraint.mask, dtype=bool
            )
        elif isinstance(constraint, FixAtoms):
            fixed[numpy.asarray(constraint.index, dtype=int)] = True
        else:
            unsupported.append(type(constraint).__name__)
    return fixed, tuple(unsupported)


def adapt_ase_atoms(atoms, *, source="", source_bytes=b"", format_name="ase"):
    import numpy

    ase = _ase()
    if not isinstance(atoms, ase.Atoms):
        raise TypeError("atoms must be an ASE Atoms object")
    if len(atoms) == 0:
        raise ValueError("ASE structure must contain at least one atom")
    positions = numpy.asarray(atoms.get_positions(), dtype=float)
    if not numpy.all(numpy.isfinite(positions)):
        raise ValueError("ASE positions must be finite")

    pbc = tuple(bool(value) for value in atoms.get_pbc())
    cell = numpy.asarray(atoms.cell.array, dtype=float)
    periodic = None
    cell_data = None
    if any(pbc):
        if not numpy.all(numpy.isfinite(cell)) or abs(numpy.linalg.det(cell)) < 1e-12:
            raise ValueError("periodic ASE structure requires a finite non-singular cell")
        fractional = numpy.asarray(atoms.get_scaled_positions(wrap=False), dtype=float)
        periodic = PeriodicSiteData(
            fractional_coordinates=ArrayData(
                fractional, ("atom", "xyz"), "dimensionless"
            ),
            site_labels=_site_labels(atoms.get_chemical_symbols()),
            occupancies=ArrayData(
                numpy.ones(len(atoms)), ("atom",), "dimensionless"
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",) * len(atoms),
            disorder_groups=(0,) * len(atoms),
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=(),
            cif_envelope_id=None,
            pbc=pbc,
        )
        cell_data = ArrayData(cell, ("cell_vector", "xyz"), "angstrom")

    source_hash = hashlib.sha256(source_bytes).hexdigest() if source_bytes else ""
    revision = source_hash or f"ase-{ase.__version__}"
    structure_id = uuid4()
    provenance_id = uuid4()
    structure = Structure(
        id=structure_id,
        revision=revision,
        atomic_numbers=tuple(int(value) for value in atoms.get_atomic_numbers()),
        coordinates=ArrayData(positions, ("atom", "xyz"), "angstrom"),
        cell=cell_data,
        periodic=periodic,
    )

    issues = []
    datasets = []
    fixed, unsupported_constraints = _fixed_axes(atoms)
    if numpy.any(fixed):
        datasets.append(
            AtomicProperty(
                id=uuid4(),
                revision=revision,
                semantic_role="fixed_axes",
                domain="atom",
                data=ArrayData(fixed, ("atom", "xyz"), "dimensionless"),
                status=DatasetStatus.COMPLETE,
                source_calculation=None,
                provenance_ids=(provenance_id,),
                structure_id=structure_id,
            )
        )
    for name in unsupported_constraints:
        issues.append(
            ParserIssue(
                IssueKind.UNSUPPORTED,
                f"atoms.constraints.{name}",
                "ASE constraint was preserved only in the source file",
            )
        )
    for name in atoms.arrays:
        if name not in _CORE_ARRAYS:
            issues.append(
                ParserIssue(
                    IssueKind.UNSUPPORTED,
                    f"atoms.arrays.{name}",
                    "ASE atom array has no normalized unit/semantic mapping",
                )
            )

    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="ASE structure adapter",
        producer_version=f"{ADAPTER_VERSION}/ase-{ase.__version__}",
        source=str(source),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=(("format", format_name), ("pbc", pbc)),
    )
    created = [structure_id, *(dataset.id for dataset in datasets), provenance_id]
    capabilities = ["structure"]
    if periodic is not None:
        capabilities.append("crystal")
    if datasets:
        capabilities.append("atomic_property")
    return ImportBatch(
        structures=(structure,),
        datasets=tuple(datasets),
        provenance=(provenance,),
        report=ParserReport(
            reader_id="ase-structure",
            reader_version=ADAPTER_VERSION,
            created_entity_ids=tuple(created),
            parsed_capabilities=tuple(capabilities),
            issues=tuple(issues),
        ),
    )


def parse_ase_structure(source: Path) -> ImportBatch:
    ase = _ase()
    source = Path(source)
    content = source.read_bytes()
    name = source.name.upper()
    if name in {"POSCAR", "CONTCAR"} or source.suffix.lower() in {
        ".vasp",
        ".poscar",
        ".contcar",
    }:
        format_name = "vasp"
    elif source.suffix.lower() in {".xyz", ".extxyz"}:
        format_name = "extxyz"
    else:
        raise ValueError("ASE structure reader requires POSCAR/CONTCAR or extXYZ")
    atoms = ase.io.read(source, index=0, format=format_name)
    return adapt_ase_atoms(
        atoms,
        source=str(source.resolve()),
        source_bytes=content,
        format_name=format_name,
    )


ASE_STRUCTURE_READER = ReaderDescriptor(
    reader_id="ase-structure",
    reader_version=ADAPTER_VERSION,
    extensions=(".vasp", ".poscar", ".contcar", ".extxyz", ".xyz"),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "crystal": CapabilitySupport.SUPPORTED,
        "atomic_property": CapabilitySupport.PARTIAL,
    },
    priority=110,
    sniff=sniff_ase_structure,
    parse=parse_ase_structure,
)
