import hashlib
from pathlib import Path
from uuid import uuid4

from .model import (
    ArrayData,
    DatasetStatus,
    Grid3D,
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
_SOURCE_KINDS = {"chgcar", "parchg", "elfcar", "locpot"}


class PymatgenDependencyError(RuntimeError):
    pass


def _pymatgen():
    try:
        import pymatgen.core
        from pymatgen.io.common import VolumetricData
        from pymatgen.io.vasp import Chgcar, Elfcar, Locpot
    except ModuleNotFoundError as error:
        if error.name == "pymatgen" or (
            error.name and error.name.startswith("pymatgen.")
        ):
            raise PymatgenDependencyError(
                "pymatgen-core is required in the ChemBlender core/worker environment"
            ) from error
        raise
    return pymatgen.core, VolumetricData, Chgcar, Elfcar, Locpot


def _source_kind(source):
    name = Path(source).name.upper()
    if name in {"CHGCAR", "PARCHG", "ELFCAR", "LOCPOT"}:
        return name.lower()
    suffix = Path(source).suffix.lower().lstrip(".")
    if suffix in _SOURCE_KINDS:
        return suffix
    raise ValueError("VASP volumetric reader requires CHGCAR/PARCHG/ELFCAR/LOCPOT")


def sniff_vasp_volumetric(source: Path, prefix: bytes) -> SniffResult:
    try:
        kind = _source_kind(source)
    except ValueError:
        return SniffResult(SniffMatch.NONE, "filename does not identify a VASP grid")
    if not prefix:
        return SniffResult(SniffMatch.POSSIBLE, f"{kind} filename with empty prefix")
    return SniffResult(SniffMatch.EXACT, f"canonical VASP {kind.upper()} filename")


def _content_hash(volume):
    import numpy

    digest = hashlib.sha256()
    digest.update(numpy.asarray(volume.structure.lattice.matrix, dtype="<f8").tobytes())
    digest.update(numpy.asarray(volume.structure.frac_coords, dtype="<f8").tobytes())
    digest.update(
        numpy.asarray([site.specie.Z for site in volume.structure], dtype="<i4").tobytes()
    )
    for key in sorted(volume.data):
        values = numpy.asarray(volume.data[key])
        digest.update(key.encode("ascii"))
        digest.update(str(values.dtype).encode("ascii"))
        digest.update(numpy.asarray(values.shape, dtype="<i8").tobytes())
        digest.update(numpy.ascontiguousarray(values).tobytes())
    return digest.hexdigest()


def _site_labels(symbols):
    counts = {}
    labels = []
    for symbol in symbols:
        counts[symbol] = counts.get(symbol, 0) + 1
        labels.append(f"{symbol}{counts[symbol]}")
    return tuple(labels)


def adapt_pymatgen_structure(pmg_structure, revision):
    import numpy

    if any(not site.is_ordered for site in pmg_structure):
        raise ValueError("pymatgen structure must use ordered sites")
    lattice = numpy.asarray(pmg_structure.lattice.matrix, dtype=float)
    fractional = numpy.asarray(pmg_structure.frac_coords, dtype=float)
    cartesian = numpy.asarray(pmg_structure.cart_coords, dtype=float)
    if (
        not numpy.all(numpy.isfinite(lattice))
        or not numpy.all(numpy.isfinite(fractional))
        or not numpy.all(numpy.isfinite(cartesian))
        or abs(numpy.linalg.det(lattice)) < 1e-12
    ):
        raise ValueError("pymatgen structure must be finite and non-singular")
    symbols = tuple(site.specie.symbol for site in pmg_structure)
    structure_id = uuid4()
    return Structure(
        id=structure_id,
        revision=revision,
        atomic_numbers=tuple(int(site.specie.Z) for site in pmg_structure),
        coordinates=ArrayData(cartesian, ("atom", "xyz"), "angstrom"),
        cell=ArrayData(lattice, ("cell_vector", "xyz"), "angstrom"),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(
                fractional, ("atom", "xyz"), "dimensionless"
            ),
            site_labels=_site_labels(symbols),
            occupancies=ArrayData(
                numpy.ones(len(pmg_structure)), ("atom",), "dimensionless"
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",) * len(pmg_structure),
            disorder_groups=(0,) * len(pmg_structure),
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=(),
            cif_envelope_id=None,
            pbc=(True, True, True),
        ),
    )


def _component_roles(source_kind, keys):
    keys = set(keys)
    soc = {"total", "diff_x", "diff_y", "diff_z"}
    if source_kind in {"chgcar", "parchg"}:
        prefix = "partial_" if source_kind == "parchg" else ""
        if soc.issubset(keys) and keys <= soc | {"diff"}:
            return (
                ("total", f"{prefix}charge_density" if prefix else "electron_density"),
                ("diff_x", f"{prefix}magnetization_density_x"),
                ("diff_y", f"{prefix}magnetization_density_y"),
                ("diff_z", f"{prefix}magnetization_density_z"),
            )
        if keys == {"total"}:
            return (("total", f"{prefix}charge_density" if prefix else "electron_density"),)
        if keys == {"total", "diff"}:
            return (
                ("total", f"{prefix}charge_density" if prefix else "electron_density"),
                ("diff", f"{prefix}spin_density"),
            )
    elif source_kind == "elfcar":
        if keys == {"total"}:
            return (("total", "electron_localization_function"),)
        if keys == {"total", "diff"}:
            return (
                ("total", "electron_localization_function_alpha"),
                ("diff", "electron_localization_function_beta"),
            )
    elif source_kind == "locpot":
        if soc.issubset(keys) and keys <= soc | {"diff"}:
            return (
                ("total", "local_potential"),
                ("diff_x", "magnetic_potential_x"),
                ("diff_y", "magnetic_potential_y"),
                ("diff_z", "magnetic_potential_z"),
            )
        if keys == {"total"}:
            return (("total", "local_potential"),)
        if keys == {"total", "diff"}:
            return (
                ("total", "local_potential_alpha"),
                ("diff", "local_potential_beta"),
            )
    raise ValueError(
        f"unsupported {source_kind.upper()} volumetric components: {', '.join(sorted(keys))}"
    )


def _has_augmentation(volume):
    augmentation = getattr(volume, "data_aug", None) or {}
    return any(bool(value) for value in augmentation.values())


def adapt_vasp_volumetric(
    volume,
    *,
    source_kind,
    source="",
    source_bytes=b"",
):
    import numpy

    pmg_core, volumetric_type, *_ = _pymatgen()
    if not isinstance(volume, volumetric_type):
        raise TypeError("volume must be a pymatgen VolumetricData object")
    source_kind = str(source_kind).lower()
    if source_kind not in _SOURCE_KINDS:
        raise ValueError("source_kind must be chgcar, parchg, elfcar, or locpot")
    source_hash = (
        hashlib.sha256(source_bytes).hexdigest() if source_bytes else _content_hash(volume)
    )
    structure = adapt_pymatgen_structure(volume.structure, source_hash)
    lattice = numpy.asarray(structure.cell.values, dtype=float)
    cell_volume = abs(float(numpy.linalg.det(lattice)))
    components = _component_roles(source_kind, volume.data)
    issues = []
    if _has_augmentation(volume):
        issues.append(
            ParserIssue(
                IssueKind.UNSUPPORTED,
                "volumetric_data.augmentation",
                "PAW augmentation occupancies remain available only in the source file",
            )
        )

    datasets = []
    provenance = []
    for key, semantic_role in components:
        values = numpy.asarray(volume.data[key], dtype=float)
        if values.ndim != 3 or any(size <= 0 for size in values.shape):
            raise ValueError(f"VASP component {key} must be a non-empty 3D array")
        if not numpy.all(numpy.isfinite(values)):
            raise ValueError(f"VASP component {key} must contain finite values")
        is_density = source_kind in {"chgcar", "parchg"}
        normalized = values / cell_volume if is_density else values.copy()
        unit = (
            "inverse_cubic_angstrom"
            if is_density
            else "dimensionless"
            if source_kind == "elfcar"
            else "electron_volt"
        )
        provenance_id = uuid4()
        dataset_id = uuid4()
        shape = values.shape
        step_vectors = tuple(
            tuple(float(component) / shape[index] for component in lattice[index])
            for index in range(3)
        )
        datasets.append(
            Grid3D(
                id=dataset_id,
                revision=source_hash,
                semantic_role=semantic_role,
                domain="grid",
                data=ArrayData(normalized, ("x", "y", "z"), unit),
                status=DatasetStatus.COMPLETE,
                source_calculation=None,
                provenance_ids=(provenance_id,),
                origin=(0.0, 0.0, 0.0),
                step_vectors=step_vectors,
                coordinate_unit="angstrom",
                structure_id=structure.id,
            )
        )
        provenance.append(
            ProvenanceRecord(
                id=provenance_id,
                revision=source_hash,
                producer="pymatgen VASP grid adapter",
                producer_version=(
                    f"{ADAPTER_VERSION}/pymatgen-core-{pmg_core.__version__}"
                ),
                source=str(source),
                source_hash=source_hash,
                parent_ids=(),
                operation="parse_and_normalize",
                parameters=(
                    ("format", source_kind),
                    ("source_component", key),
                    ("normalization", "divide_by_cell_volume" if is_density else "none"),
                    ("cell_volume_angstrom_cubed", cell_volume),
                ),
            )
        )

    created = [structure.id]
    for dataset, record in zip(datasets, provenance):
        created.extend((dataset.id, record.id))
    return ImportBatch(
        structures=(structure,),
        datasets=tuple(datasets),
        provenance=tuple(provenance),
        report=ParserReport(
            reader_id="pymatgen-vasp-grid",
            reader_version=ADAPTER_VERSION,
            created_entity_ids=tuple(created),
            parsed_capabilities=("structure", "crystal", "grid"),
            issues=tuple(issues),
        ),
    )


def parse_vasp_volumetric(source: Path) -> ImportBatch:
    _, _, chgcar_type, elfcar_type, locpot_type = _pymatgen()
    source = Path(source)
    source_kind = _source_kind(source)
    parser = {
        "chgcar": chgcar_type,
        "parchg": chgcar_type,
        "elfcar": elfcar_type,
        "locpot": locpot_type,
    }[source_kind]
    content = source.read_bytes()
    volume = parser.from_file(str(source))
    return adapt_vasp_volumetric(
        volume,
        source_kind=source_kind,
        source=str(source.resolve()),
        source_bytes=content,
    )


PYMATGEN_VASP_GRID_READER = ReaderDescriptor(
    reader_id="pymatgen-vasp-grid",
    reader_version=ADAPTER_VERSION,
    extensions=(".chgcar", ".parchg", ".elfcar", ".locpot"),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "crystal": CapabilitySupport.SUPPORTED,
        "grid": CapabilitySupport.SUPPORTED,
    },
    priority=120,
    sniff=sniff_vasp_volumetric,
    parse=parse_vasp_volumetric,
)
