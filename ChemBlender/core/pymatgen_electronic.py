import hashlib
from pathlib import Path
from uuid import uuid4

from .model import (
    ArrayData,
    BandPathBranch,
    BandStructure,
    DatasetStatus,
    DensityOfStates,
    EnergyReference,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    ProvenanceRecord,
)
from .pymatgen_adapter import adapt_pymatgen_structure
from .readers import CapabilitySupport, ReaderDescriptor, SniffMatch, SniffResult


ADAPTER_VERSION = "1"


class PymatgenElectronicDependencyError(RuntimeError):
    pass


def _pymatgen_electronic():
    try:
        import pymatgen.core
        from pymatgen.electronic_structure.bandstructure import BandStructure
        from pymatgen.electronic_structure.core import Orbital, Spin
        from pymatgen.electronic_structure.dos import CompleteDos
        from pymatgen.io.vasp import Vasprun
    except ModuleNotFoundError as error:
        if error.name == "pymatgen" or (
            error.name and error.name.startswith("pymatgen.")
        ):
            raise PymatgenElectronicDependencyError(
                "pymatgen-core is required in the ChemBlender core/worker environment"
            ) from error
        raise
    return pymatgen.core, BandStructure, CompleteDos, Orbital, Spin, Vasprun


def sniff_vasprun(source: Path, prefix: bytes) -> SniffResult:
    canonical = Path(source).name.lower() == "vasprun.xml"
    text = prefix.lower()
    looks_like_vasprun = b"<modeling" in text and (
        b"<generator" in text or b"name=\"program\"" in text or b"name='program'" in text
    )
    if canonical and looks_like_vasprun:
        return SniffResult(SniffMatch.EXACT, "canonical VASP vasprun.xml content")
    if looks_like_vasprun:
        return SniffResult(SniffMatch.PROBABLE, "VASP modeling XML content")
    if canonical:
        return SniffResult(SniffMatch.POSSIBLE, "canonical vasprun.xml filename")
    return SniffResult(SniffMatch.NONE, "not a VASP electronic result")


def _spin_order(mapping, spin_type):
    expected = [spin_type.up]
    if spin_type.down in mapping:
        expected.append(spin_type.down)
    if set(mapping) != set(expected):
        raise ValueError("pymatgen spin mapping must contain up and optional down")
    return tuple(expected)


def _same_structure(first, second):
    import numpy

    return (
        tuple(int(site.specie.Z) for site in first)
        == tuple(int(site.specie.Z) for site in second)
        and numpy.allclose(first.lattice.matrix, second.lattice.matrix)
        and numpy.allclose(first.frac_coords, second.frac_coords)
    )


def _object_hash(band_structure, complete_dos, occupations):
    import numpy

    digest = hashlib.sha256()
    for obj in (band_structure, complete_dos):
        if obj is None:
            continue
        structure = obj.structure
        digest.update(numpy.asarray(structure.lattice.matrix, dtype="<f8").tobytes())
        digest.update(numpy.asarray(structure.frac_coords, dtype="<f8").tobytes())
        digest.update(numpy.asarray([site.specie.Z for site in structure], dtype="<i4").tobytes())
    if band_structure is not None:
        for spin in sorted(band_structure.bands, key=int, reverse=True):
            digest.update(numpy.asarray(band_structure.bands[spin], dtype="<f8").tobytes())
    if complete_dos is not None:
        digest.update(numpy.asarray(complete_dos.energies, dtype="<f8").tobytes())
        for spin in sorted(complete_dos.densities, key=int, reverse=True):
            digest.update(numpy.asarray(complete_dos.densities[spin], dtype="<f8").tobytes())
    if occupations is not None:
        for spin in sorted(occupations, key=int, reverse=True):
            digest.update(numpy.asarray(occupations[spin], dtype="<f8").tobytes())
    return digest.hexdigest()


def _band_dataset(band_structure, structure_id, revision, provenance_id, occupations):
    import numpy

    _, band_type, _, orbital_type, spin_type, _ = _pymatgen_electronic()
    if not isinstance(band_structure, band_type):
        raise TypeError("band_structure must be a pymatgen BandStructure")
    spins = _spin_order(band_structure.bands, spin_type)
    values = numpy.stack(
        [numpy.asarray(band_structure.bands[spin], dtype=float).T for spin in spins]
    )
    occupation_data = None
    if occupations is not None:
        if set(occupations) != set(spins):
            raise ValueError("occupation spin channels must match band energies")
        occupation_values = numpy.stack(
            [numpy.asarray(occupations[spin], dtype=float).T for spin in spins]
        )
        occupation_data = ArrayData(
            occupation_values,
            ("spin", "kpoint", "band"),
            "dimensionless",
        )

    projection_data = None
    orbital_labels = ()
    projections = getattr(band_structure, "projections", None)
    if projections:
        if set(projections) != set(spins):
            raise ValueError("projection spin channels must match band energies")
        projected = numpy.stack(
            [numpy.asarray(projections[spin], dtype=float).transpose(1, 0, 3, 2) for spin in spins]
        )
        orbital_count = projected.shape[-1]
        available = tuple(member.name for member in orbital_type)
        if orbital_count > len(available):
            raise ValueError("projection orbital axis exceeds pymatgen Orbital labels")
        orbital_labels = available[:orbital_count]
        projection_data = ArrayData(
            projected,
            ("spin", "kpoint", "band", "atom", "orbital"),
            "dimensionless",
        )

    kpoints = numpy.asarray([point.frac_coords for point in band_structure.kpoints], dtype=float)
    distances = getattr(band_structure, "distance", None)
    if distances is None:
        cartesian = numpy.asarray([point.cart_coords for point in band_structure.kpoints], dtype=float)
        distances = numpy.concatenate(([0.0], numpy.cumsum(numpy.linalg.norm(numpy.diff(cartesian, axis=0), axis=1))))
    labels = tuple(point.label for point in band_structure.kpoints)
    branches = tuple(
        BandPathBranch(
            int(branch["start_index"]),
            int(branch["end_index"]),
            labels[int(branch["start_index"])],
            labels[int(branch["end_index"])],
        )
        for branch in getattr(band_structure, "branches", ())
    )
    return BandStructure(
        id=uuid4(),
        revision=revision,
        semantic_role="band_structure",
        domain="band",
        data=ArrayData(values, ("spin", "kpoint", "band"), "electron_volt"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
        occupations=occupation_data,
        kpoints=ArrayData(kpoints, ("kpoint", "reciprocal_axis"), "dimensionless"),
        reciprocal_lattice=ArrayData(
            numpy.asarray(band_structure.lattice_rec.matrix, dtype=float),
            ("reciprocal_vector", "cartesian_axis"),
            "inverse_angstrom",
        ),
        distances=ArrayData(numpy.asarray(distances, dtype=float), ("kpoint",), "inverse_angstrom"),
        spin_channels=tuple("alpha" if spin == spin_type.up else "beta" for spin in spins),
        labels=labels,
        branches=branches,
        projections=projection_data,
        orbital_labels=orbital_labels,
        fermi_energy=float(band_structure.efermi),
        energy_reference=EnergyReference.ABSOLUTE,
    )


def _dos_dataset(complete_dos, structure_id, revision, provenance_id):
    import numpy

    _, _, complete_dos_type, _, spin_type, _ = _pymatgen_electronic()
    if not isinstance(complete_dos, complete_dos_type):
        raise TypeError("complete_dos must be a pymatgen CompleteDos")
    spins = _spin_order(complete_dos.densities, spin_type)
    values = numpy.stack([numpy.asarray(complete_dos.densities[spin], dtype=float) for spin in spins])
    orbitals = sorted(
        {orbital for site_pdos in complete_dos.pdos.values() for orbital in site_pdos},
        key=lambda orbital: int(orbital),
    )
    projections = None
    orbital_labels = ()
    if orbitals:
        projected = numpy.zeros((len(spins), len(complete_dos.energies), len(complete_dos.structure), len(orbitals)))
        orbital_indices = {orbital: index for index, orbital in enumerate(orbitals)}
        site_indices = {id(site): index for index, site in enumerate(complete_dos.structure)}
        for site, site_pdos in complete_dos.pdos.items():
            atom_index = site_indices.get(id(site))
            if atom_index is None:
                atom_index = complete_dos.structure.index(site)
            for orbital, spin_pdos in site_pdos.items():
                for spin_index, spin in enumerate(spins):
                    if spin in spin_pdos:
                        projected[spin_index, :, atom_index, orbital_indices[orbital]] = spin_pdos[spin]
        if complete_dos.norm_vol is not None:
            projected /= float(complete_dos.norm_vol)
        projections = ArrayData(
            projected,
            ("spin", "energy", "atom", "orbital"),
            "states_per_electron_volt_per_cubic_angstrom" if complete_dos.norm_vol is not None else "states_per_electron_volt",
        )
        orbital_labels = tuple(orbital.name for orbital in orbitals)
    unit = "states_per_electron_volt_per_cubic_angstrom" if complete_dos.norm_vol is not None else "states_per_electron_volt"
    return DensityOfStates(
        id=uuid4(),
        revision=revision,
        semantic_role="density_of_states",
        domain="energy",
        data=ArrayData(values, ("spin", "energy"), unit),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
        energies=ArrayData(numpy.asarray(complete_dos.energies, dtype=float), ("energy",), "electron_volt"),
        spin_channels=tuple("alpha" if spin == spin_type.up else "beta" for spin in spins),
        projections=projections,
        orbital_labels=orbital_labels,
        fermi_energy=float(complete_dos.efermi),
        energy_reference=EnergyReference.ABSOLUTE,
    )


def adapt_pymatgen_electronic(
    *,
    band_structure=None,
    complete_dos=None,
    occupations=None,
    source="",
    source_bytes=b"",
):
    pmg_core, *_ = _pymatgen_electronic()
    if band_structure is None and complete_dos is None:
        raise ValueError("band_structure or complete_dos is required")
    structures = [obj.structure for obj in (band_structure, complete_dos) if obj is not None]
    if any(structure is None for structure in structures):
        raise ValueError("periodic electronic data requires an associated structure")
    if any(not _same_structure(structures[0], other) for other in structures[1:]):
        raise ValueError("band structure and DOS must describe the same structure")
    revision = hashlib.sha256(source_bytes).hexdigest() if source_bytes else _object_hash(band_structure, complete_dos, occupations)
    structure = adapt_pymatgen_structure(structures[0], revision)
    provenance_id = uuid4()
    datasets = []
    issues = []
    capabilities = ["structure"]
    if band_structure is not None:
        dataset = _band_dataset(band_structure, structure.id, revision, provenance_id, occupations)
        datasets.append(dataset)
        capabilities.append("band_structure")
        if dataset.occupations is None:
            issues.append(ParserIssue(IssueKind.MISSING, "band_structure.occupations", "occupations are unavailable"))
        if dataset.projections is None:
            issues.append(ParserIssue(IssueKind.MISSING, "band_structure.projections", "orbital projections are unavailable"))
        else:
            capabilities.append("projection")
    if complete_dos is not None:
        dataset = _dos_dataset(complete_dos, structure.id, revision, provenance_id)
        datasets.append(dataset)
        capabilities.append("dos")
        if dataset.projections is not None and "projection" not in capabilities:
            capabilities.append("projection")
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="pymatgen electronic adapter",
        producer_version=f"{ADAPTER_VERSION}/pymatgen-core-{pmg_core.__version__}",
        source=str(source),
        source_hash=revision,
        parent_ids=(),
        operation="parse_and_normalize",
        parameters=(("energy_reference", "absolute"), ("reciprocal_convention", "2pi")),
    )
    created = (structure.id, *(dataset.id for dataset in datasets), provenance.id)
    return ImportBatch(
        structures=(structure,),
        datasets=tuple(datasets),
        provenance=(provenance,),
        report=ParserReport(
            reader_id="pymatgen-vasprun-electronic",
            reader_version=ADAPTER_VERSION,
            created_entity_ids=created,
            parsed_capabilities=tuple(capabilities),
            issues=tuple(issues),
        ),
    )


def parse_vasprun_electronic(source: Path):
    *_, vasprun_type = _pymatgen_electronic()
    source = Path(source)
    content = source.read_bytes()
    result = vasprun_type(str(source), parse_projected_eigen=True)
    band_structure = result.get_band_structure(line_mode=False)
    occupations = {
        spin: values[:, :, 1].T for spin, values in result.eigenvalues.items()
    }
    return adapt_pymatgen_electronic(
        band_structure=band_structure,
        complete_dos=result.complete_dos,
        occupations=occupations,
        source=str(source.resolve()),
        source_bytes=content,
    )


PYMATGEN_VASP_ELECTRONIC_READER = ReaderDescriptor(
    reader_id="pymatgen-vasprun-electronic",
    reader_version=ADAPTER_VERSION,
    extensions=(".xml",),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "band_structure": CapabilitySupport.SUPPORTED,
        "dos": CapabilitySupport.SUPPORTED,
        "projection": CapabilitySupport.PARTIAL,
    },
    priority=130,
    sniff=sniff_vasprun,
    parse=parse_vasprun_electronic,
)
