import hashlib
from pathlib import Path
from uuid import uuid4

from .model import (
    ArrayData,
    CIFEnvelope,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    PeriodicSiteData,
    ProvenanceRecord,
    Structure,
)
from .readers import (
    CapabilitySupport,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
)


ADAPTER_VERSION = "1"


class GemmiDependencyError(RuntimeError):
    pass


def _gemmi():
    try:
        import gemmi
    except ModuleNotFoundError as error:
        if error.name == "gemmi":
            raise GemmiDependencyError(
                "Gemmi is required in the ChemBlender core/worker environment"
            ) from error
        raise
    return gemmi


def sniff_cif(source: Path, prefix: bytes) -> SniffResult:
    del source
    try:
        text = prefix.decode("utf-8-sig").lower()
    except UnicodeDecodeError:
        return SniffResult(SniffMatch.NONE, "content is not UTF-8 CIF text")
    has_block = any(line.lstrip().startswith("data_") for line in text.splitlines())
    has_cell = "_cell_length_a" in text
    has_site = "_atom_site_" in text
    if has_block and has_cell and has_site:
        return SniffResult(SniffMatch.EXACT, "CIF block with cell and atom sites")
    if has_block and (has_cell or has_site):
        return SniffResult(SniffMatch.POSSIBLE, "partial crystallographic CIF prefix")
    return SniffResult(SniffMatch.NONE, "missing crystallographic CIF markers")


def _tag_names(block):
    names = []
    for item in block:
        if item.pair is not None:
            names.append(item.pair[0])
        elif item.loop is not None:
            names.extend(item.loop.tags)
    return tuple(names)


def _column_strings(gemmi, block, tag):
    column = block.find_values(tag)
    return tuple(gemmi.cif.as_string(value) for value in column)


def _site_map(gemmi, block, tag):
    labels = _column_strings(gemmi, block, "_atom_site_label")
    values = _column_strings(gemmi, block, tag)
    if not values:
        return {}
    if len(values) != len(labels):
        raise ValueError(f"CIF {tag} column does not match atom-site labels")
    return dict(zip(labels, values))


def _lattice_and_cartesian(gemmi, small):
    import numpy

    fractional_axes = (
        gemmi.Fractional(1.0, 0.0, 0.0),
        gemmi.Fractional(0.0, 1.0, 0.0),
        gemmi.Fractional(0.0, 0.0, 1.0),
    )
    lattice = numpy.asarray(
        [tuple(small.cell.orthogonalize(axis)) for axis in fractional_axes],
        dtype=float,
    )
    if not numpy.all(numpy.isfinite(lattice)) or abs(numpy.linalg.det(lattice)) < 1e-12:
        raise ValueError("CIF unit cell must be finite and non-singular")
    fractional = numpy.asarray([tuple(site.fract) for site in small.sites], dtype=float)
    if not numpy.all(numpy.isfinite(fractional)):
        raise ValueError("CIF fractional coordinates must be finite")
    return lattice, fractional, fractional @ lattice


def parse_cif(source: Path) -> ImportBatch:
    import numpy

    gemmi = _gemmi()
    source = Path(source)
    content = source.read_bytes()
    source_hash = hashlib.sha256(content).hexdigest()
    try:
        document = gemmi.cif.read_file(str(source))
    except RuntimeError as error:
        raise ValueError(f"Gemmi could not parse CIF: {error}") from error
    if len(document) != 1:
        raise ValueError("CIF reader requires exactly one data block")
    block = document.sole_block()
    try:
        small = gemmi.make_small_structure_from_block(block)
    except RuntimeError as error:
        raise ValueError(
            f"Gemmi could not create a crystal structure: {error}"
        ) from error
    if not small.sites:
        raise ValueError("CIF block does not contain atom sites")

    lattice, fractional, cartesian = _lattice_and_cartesian(gemmi, small)
    atomic_numbers = tuple(site.element.atomic_number for site in small.sites)
    if any(number <= 0 for number in atomic_numbers):
        raise ValueError("CIF atom sites must use recognized element symbols")
    labels = tuple(site.label for site in small.sites)
    occupancies = numpy.asarray([site.occ for site in small.sites], dtype=float)
    if not numpy.all(numpy.isfinite(occupancies)):
        raise ValueError("CIF occupancies must be finite")

    tags = _tag_names(block)
    lower_tags = {tag.lower() for tag in tags}
    has_u_iso = bool(
        lower_tags
        & {"_atom_site_u_iso_or_equiv", "_atom_site_b_iso_or_equiv"}
    )
    isotropic = None
    if has_u_iso:
        u_tag = (
            "_atom_site_U_iso_or_equiv"
            if "_atom_site_u_iso_or_equiv" in lower_tags
            else "_atom_site_B_iso_or_equiv"
        )
        raw_u_values = _site_map(gemmi, block, u_tag)
        isotropic = ArrayData(
            numpy.asarray(
                [
                    numpy.nan
                    if raw_u_values.get(site.label) in {None, ".", "?"}
                    else site.u_iso
                    for site in small.sites
                ],
                dtype=float,
            ),
            ("atom",),
            "angstrom_squared",
        )

    aniso_labels = set(_column_strings(gemmi, block, "_atom_site_aniso_label"))
    anisotropic = None
    if aniso_labels:
        values = []
        for site in small.sites:
            if site.label not in aniso_labels:
                values.append((numpy.nan,) * 6)
                continue
            aniso = site.aniso
            values.append(
                (
                    aniso.u11,
                    aniso.u22,
                    aniso.u33,
                    aniso.u12,
                    aniso.u13,
                    aniso.u23,
                )
            )
        anisotropic = ArrayData(
            numpy.asarray(values, dtype=float),
            ("atom", "tensor_component"),
            "angstrom_squared",
        )

    adp_map = _site_map(gemmi, block, "_atom_site_adp_type")
    adp_types = tuple(adp_map.get(label, "none") or "none" for label in labels)
    disorder_groups = tuple(max(0, int(site.disorder_group)) for site in small.sites)
    envelope_id = uuid4()
    provenance_id = uuid4()
    structure_id = uuid4()
    space_group_name = small.spacegroup_hm or None
    space_group_number = small.spacegroup_number or None
    symmetry_operations = tuple(
        operation.replace(" ", "") for operation in small.symops
    )
    periodic = PeriodicSiteData(
        fractional_coordinates=ArrayData(
            fractional, ("atom", "xyz"), "dimensionless"
        ),
        site_labels=labels,
        occupancies=ArrayData(occupancies, ("atom",), "dimensionless"),
        isotropic_displacements=isotropic,
        anisotropic_displacements=anisotropic,
        adp_types=adp_types,
        disorder_groups=disorder_groups,
        declared_space_group_name=space_group_name,
        declared_space_group_number=space_group_number,
        symmetry_operations=symmetry_operations,
        cif_envelope_id=envelope_id,
    )
    structure = Structure(
        id=structure_id,
        revision=source_hash,
        atomic_numbers=atomic_numbers,
        coordinates=ArrayData(cartesian, ("atom", "xyz"), "angstrom"),
        cell=ArrayData(lattice, ("cell_vector", "xyz"), "angstrom"),
        periodic=periodic,
    )
    envelope = CIFEnvelope(
        id=envelope_id,
        revision=source_hash,
        block_name=block.name,
        source_bytes=content,
        tag_names=tags,
        provenance_ids=(provenance_id,),
    )
    issues = []
    if numpy.any(occupancies < 1.0):
        issues.append(
            ParserIssue(
                IssueKind.WARNING,
                "structure.periodic.occupancies",
                "partial occupancies were preserved; symmetry derivation is disabled",
            )
        )
    if any(disorder_groups):
        issues.append(
            ParserIssue(
                IssueKind.WARNING,
                "structure.periodic.disorder_groups",
                "disorder groups were preserved; symmetry derivation is disabled",
            )
        )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=source_hash,
        producer="Gemmi CIF adapter",
        producer_version=f"{ADAPTER_VERSION}/gemmi-{gemmi.__version__}",
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=(("format", "cif"), ("block_name", block.name)),
    )
    report = ParserReport(
        reader_id="gemmi-cif",
        reader_version=ADAPTER_VERSION,
        created_entity_ids=(structure_id, envelope_id, provenance_id),
        parsed_capabilities=("structure", "crystal", "cif_envelope"),
        issues=tuple(issues),
    )
    return ImportBatch(
        structures=(structure,),
        cif_envelopes=(envelope,),
        provenance=(provenance,),
        report=report,
    )


CIF_READER = ReaderDescriptor(
    reader_id="gemmi-cif",
    reader_version=ADAPTER_VERSION,
    extensions=(".cif",),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "crystal": CapabilitySupport.SUPPORTED,
        "cif_envelope": CapabilitySupport.SUPPORTED,
    },
    priority=100,
    sniff=sniff_cif,
    parse=parse_cif,
)
