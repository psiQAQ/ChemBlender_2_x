import hashlib
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ..model import (
    ArrayData,
    AtomicIdentityData,
    CategoricalData,
    CIFEnvelope,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    PeriodicSiteData,
    ProvenanceRecord,
    Structure,
)
from ..readers import (
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


def _lattice(gemmi, small):
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
    return lattice


def _numeric_matrix(gemmi, block, tags, atom_count):
    import numpy

    columns = tuple(_column_strings(gemmi, block, tag) for tag in tags)
    if not any(columns):
        return None
    if any(len(column) != atom_count for column in columns):
        raise ValueError(f"CIF coordinate columns {tags!r} are incomplete")
    return numpy.asarray(
        [
            [gemmi.cif.as_number(columns[axis][atom]) for axis in range(3)]
            for atom in range(atom_count)
        ],
        dtype=float,
    )


def _coordinates(gemmi, block, lattice, atom_count):
    import numpy

    fractional = _numeric_matrix(
        gemmi,
        block,
        (
            "_atom_site_fract_x",
            "_atom_site_fract_y",
            "_atom_site_fract_z",
        ),
        atom_count,
    )
    cartesian_source = _numeric_matrix(
        gemmi,
        block,
        (
            "_atom_site_Cartn_x",
            "_atom_site_Cartn_y",
            "_atom_site_Cartn_z",
        ),
        atom_count,
    )
    if fractional is None and cartesian_source is None:
        raise ValueError("CIF atom sites require fractional or Cartesian coordinates")
    if fractional is not None and not numpy.all(numpy.isfinite(fractional)):
        raise ValueError("CIF fractional coordinates must be finite")
    if cartesian_source is not None and not numpy.all(
        numpy.isfinite(cartesian_source)
    ):
        raise ValueError("CIF Cartesian coordinates must be finite")
    issues = []
    if fractional is None:
        fractional = cartesian_source @ numpy.linalg.inv(lattice)
        issues.append(
            ParserIssue(
                IssueKind.WARNING,
                "structure.periodic.fractional_coordinates",
                "fractional coordinates were derived from CIF Cartesian coordinates",
            )
        )
        return fractional, cartesian_source, tuple(issues)
    cartesian = fractional @ lattice
    if cartesian_source is not None and not numpy.allclose(
        cartesian,
        cartesian_source,
        rtol=0.0,
        atol=1.0e-6,
    ):
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                "structure.coordinates",
                (
                    "CIF fractional and Cartesian coordinates disagree; "
                    "fractional coordinates were used"
                ),
            )
        )
    return fractional, cartesian, tuple(issues)


def _categorical(values):
    import numpy

    categories = tuple(dict.fromkeys(value for value in values if value is not None))
    positions = {value: index for index, value in enumerate(categories)}
    return CategoricalData(
        ArrayData(
            numpy.asarray(
                [positions.get(value, -1) for value in values],
                dtype=numpy.int64,
            ),
            ("atom",),
            "dimensionless",
        ),
        categories,
        -1,
    )


def _atomic_identity(labels):
    import numpy

    atom_count = len(labels)
    zeros = lambda: ArrayData(
        numpy.zeros(atom_count, dtype=numpy.int64),
        ("atom",),
        "dimensionless",
    )
    return AtomicIdentityData(
        isotopes=zeros(),
        formal_charges=zeros(),
        atom_map_numbers=zeros(),
        atom_names=_categorical(labels),
        stereo_labels=_categorical((None,) * atom_count),
    )


def _read_document(gemmi, content):
    try:
        return gemmi.cif.read_string(content)
    except RuntimeError as error:
        if "duplicate block name" not in str(error).lower():
            raise
        document = gemmi.cif.read_string(content, check_level=0)
        names = tuple(block.name for block in document)
        if len(names) == len(set(names)):
            raise
        for block in document:
            tags = tuple(tag.lower() for tag in _tag_names(block))
            if len(tags) != len(set(tags)):
                raise RuntimeError(
                    f"duplicate CIF tag in block {block.name!r}"
                ) from error
        return document


def _block_keys(block_names):
    counts = {}
    used = set()
    keys = []
    for name in block_names:
        count = counts.get(name, 0) + 1
        counts[name] = count
        key = name if count == 1 else f"{name}#{count}"
        while key in used:
            count += 1
            counts[name] = count
            key = f"{name}#{count}"
        used.add(key)
        keys.append(key)
    return tuple(keys)


def _occupancies(gemmi, block, atom_count):
    import numpy

    raw = _column_strings(gemmi, block, "_atom_site_occupancy")
    if not raw:
        return (
            numpy.ones(atom_count, dtype=float),
            (
                ParserIssue(
                    IssueKind.WARNING,
                    "structure.periodic.occupancies",
                    "missing CIF occupancy column was defaulted to 1",
                ),
            ),
        )
    if len(raw) != atom_count:
        raise ValueError("CIF occupancy column does not match atom sites")
    values = numpy.asarray(
        [gemmi.cif.as_number(value) for value in raw],
        dtype=float,
    )
    issues = tuple(
        ParserIssue(
            IssueKind.MISSING,
            f"structure.periodic.occupancies[{index}]",
            "missing CIF occupancy was preserved as missing",
        )
        for index, value in enumerate(values)
        if numpy.isnan(value)
    )
    return values, issues


def _site_strings(gemmi, block, tag, atom_count, default):
    raw = _column_strings(gemmi, block, tag)
    if not raw:
        return (default,) * atom_count
    if len(raw) != atom_count:
        raise ValueError(f"CIF {tag} column does not match atom sites")
    return tuple(
        default if value in {".", "?", ""} else value
        for value in raw
    )


def _isotropic_displacements(gemmi, block, atom_count):
    import numpy

    u_values = _column_strings(gemmi, block, "_atom_site_U_iso_or_equiv")
    b_values = _column_strings(gemmi, block, "_atom_site_B_iso_or_equiv")
    if not u_values and not b_values:
        return None, ()
    raw = u_values or b_values
    if len(raw) != atom_count:
        raise ValueError("CIF isotropic displacement column does not match atom sites")
    values = numpy.asarray(
        [gemmi.cif.as_number(value) for value in raw],
        dtype=float,
    )
    issues = []
    if b_values and not u_values:
        values = values / (8.0 * numpy.pi**2)
        issues.append(
            ParserIssue(
                IssueKind.WARNING,
                "structure.periodic.isotropic_displacements",
                "CIF B_iso values were converted to U_iso using B/(8*pi^2)",
            )
        )
    issues.extend(
        ParserIssue(
            IssueKind.MISSING,
            f"structure.periodic.isotropic_displacements[{index}]",
            "missing CIF isotropic displacement was preserved as missing",
        )
        for index, value in enumerate(values)
        if numpy.isnan(value)
    )
    return (
        ArrayData(values, ("atom",), "angstrom_squared"),
        tuple(issues),
    )


def _anisotropic_displacements(gemmi, block, labels):
    import numpy

    aniso_labels = _column_strings(gemmi, block, "_atom_site_aniso_label")
    if not aniso_labels:
        return None, ()
    if len(aniso_labels) != len(set(aniso_labels)):
        raise ValueError("CIF anisotropic labels must be unique")
    u_tags = tuple(
        f"_atom_site_aniso_U_{component}"
        for component in ("11", "22", "33", "12", "13", "23")
    )
    b_tags = tuple(
        f"_atom_site_aniso_B_{component}"
        for component in ("11", "22", "33", "12", "13", "23")
    )
    u_columns = tuple(_column_strings(gemmi, block, tag) for tag in u_tags)
    b_columns = tuple(_column_strings(gemmi, block, tag) for tag in b_tags)
    columns = u_columns if any(u_columns) else b_columns
    if not any(columns) or any(
        len(column) != len(aniso_labels) for column in columns
    ):
        raise ValueError("CIF anisotropic displacement columns are incomplete")
    by_label = {}
    for row, label in enumerate(aniso_labels):
        values = numpy.asarray(
            [
                gemmi.cif.as_number(columns[column][row])
                for column in range(6)
            ],
            dtype=float,
        )
        if b_columns and not any(u_columns):
            values = values / (8.0 * numpy.pi**2)
        by_label[label] = values
    issues = []
    rows = []
    for atom, label in enumerate(labels):
        values = by_label.get(label)
        if values is None or numpy.any(numpy.isnan(values)):
            rows.append((numpy.nan,) * 6)
            if values is not None:
                issues.append(
                    ParserIssue(
                        IssueKind.INVALID,
                        (
                            "structure.periodic."
                            f"anisotropic_displacements[{atom}]"
                        ),
                        (
                            "partial CIF anisotropic displacement row "
                            "was preserved as missing"
                        ),
                    )
                )
        else:
            rows.append(tuple(values))
    if b_columns and not any(u_columns):
        issues.append(
            ParserIssue(
                IssueKind.WARNING,
                "structure.periodic.anisotropic_displacements",
                "CIF B_ij values were converted to U_ij using B/(8*pi^2)",
            )
        )
    return (
        ArrayData(
            numpy.asarray(rows, dtype=float),
            ("atom", "tensor_component"),
            "angstrom_squared",
        ),
        tuple(issues),
    )


def _first_text(gemmi, block, tags):
    for tag in tags:
        value = block.find_value(tag)
        if value and value not in {".", "?"}:
            return gemmi.cif.as_string(value)
    return None


def _declared_symmetry(gemmi, block):
    name = _first_text(
        gemmi,
        block,
        (
            "_space_group_name_H-M_alt",
            "_symmetry_space_group_name_H-M",
        ),
    )
    hall_symbol = _first_text(
        gemmi,
        block,
        (
            "_space_group_name_Hall",
            "_symmetry_space_group_name_Hall",
        ),
    )
    number_text = _first_text(
        gemmi,
        block,
        (
            "_space_group_IT_number",
            "_symmetry_Int_Tables_number",
        ),
    )
    number = None
    issues = []
    if number_text is not None:
        parsed = gemmi.cif.as_number(number_text)
        if (
            not parsed.is_integer()
            or not 1 <= int(parsed) <= 230
        ):
            issues.append(
                ParserIssue(
                    IssueKind.INVALID,
                    "structure.periodic.declared_space_group_number",
                    "declared CIF international number is invalid",
                )
            )
        else:
            number = int(parsed)
    operation_tags = (
        "_space_group_symop_operation_xyz",
        "_symmetry_equiv_pos_as_xyz",
    )
    operations = ()
    for tag in operation_tags:
        operations = _column_strings(gemmi, block, tag)
        if operations:
            operations = tuple(value.replace(" ", "") for value in operations)
            break
    for symbol in (name, hall_symbol):
        if symbol is None or number is None:
            continue
        group = gemmi.find_spacegroup_by_name(symbol)
        if group is not None and group.number != number:
            issues.append(
                ParserIssue(
                    IssueKind.AMBIGUOUS,
                    "structure.periodic.declared_symmetry",
                    (
                        f"declared CIF group {symbol!r} conflicts with "
                        f"international number {number}"
                    ),
                )
            )
    return name, number, hall_symbol, operations, tuple(issues)


def _parse_block(
    gemmi,
    block,
    *,
    source_hash,
    envelope_id,
    block_name,
    block_key,
    block_index,
):
    import numpy

    try:
        small = gemmi.make_small_structure_from_block(block)
    except RuntimeError as error:
        raise ValueError(
            f"Gemmi could not create a crystal structure: {error}"
        ) from error
    if not small.sites:
        raise ValueError("CIF block does not contain atom sites")

    atom_count = len(small.sites)
    lattice = _lattice(gemmi, small)
    fractional, cartesian, coordinate_issues = _coordinates(
        gemmi,
        block,
        lattice,
        atom_count,
    )
    atomic_numbers = tuple(site.element.atomic_number for site in small.sites)
    if any(number <= 0 for number in atomic_numbers):
        raise ValueError("CIF atom sites must use recognized element symbols")
    labels = tuple(site.label for site in small.sites)
    if len(labels) != len(set(labels)):
        raise ValueError("CIF atom-site labels must be unique")
    occupancies, occupancy_issues = _occupancies(
        gemmi,
        block,
        atom_count,
    )
    isotropic, isotropic_issues = _isotropic_displacements(
        gemmi,
        block,
        atom_count,
    )
    anisotropic, anisotropic_issues = _anisotropic_displacements(
        gemmi,
        block,
        labels,
    )
    adp_types = _site_strings(
        gemmi,
        block,
        "_atom_site_adp_type",
        atom_count,
        "none",
    )
    disorder_groups = tuple(max(0, int(site.disorder_group)) for site in small.sites)
    disorder_assemblies = _site_strings(
        gemmi,
        block,
        "_atom_site_disorder_assembly",
        atom_count,
        "none",
    )
    structure_id = uuid5(
        NAMESPACE_URL,
        (
            f"chemblender:cif:{ADAPTER_VERSION}:{source_hash}:"
            f"{block_key}:structure"
        ),
    )
    (
        space_group_name,
        space_group_number,
        hall_symbol,
        symmetry_operations,
        declared_symmetry_issues,
    ) = _declared_symmetry(
        gemmi,
        block,
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
        cif_block_name=block_name,
        cif_block_key=block_key,
        cif_block_index=block_index,
        disorder_assemblies=disorder_assemblies,
        declared_hall_symbol=hall_symbol,
    )
    structure = Structure(
        id=structure_id,
        revision=f"{source_hash}:{block_key}",
        atomic_numbers=atomic_numbers,
        coordinates=ArrayData(cartesian, ("atom", "xyz"), "angstrom"),
        cell=ArrayData(lattice, ("cell_vector", "xyz"), "angstrom"),
        periodic=periodic,
        atomic_identity=_atomic_identity(labels),
    )
    normalizations = []
    has_fractional = bool(
        _column_strings(gemmi, block, "_atom_site_fract_x")
    )
    has_cartesian = bool(
        _column_strings(gemmi, block, "_atom_site_Cartn_x")
    )
    if has_cartesian and not has_fractional:
        normalizations.append("cartesian_to_fractional")
    elif has_cartesian:
        normalizations.append("fractional_preferred_over_cartesian")
    if not _column_strings(gemmi, block, "_atom_site_occupancy"):
        normalizations.append("occupancy_default_1")
    if (
        _column_strings(gemmi, block, "_atom_site_B_iso_or_equiv")
        and not _column_strings(gemmi, block, "_atom_site_U_iso_or_equiv")
    ):
        normalizations.append("b_iso_to_u_iso")
    if (
        _column_strings(gemmi, block, "_atom_site_aniso_B_11")
        and not _column_strings(gemmi, block, "_atom_site_aniso_U_11")
    ):
        normalizations.append("b_ij_to_u_ij")
    issues = list(
        coordinate_issues
        + occupancy_issues
        + isotropic_issues
        + anisotropic_issues
        + declared_symmetry_issues
    )
    if numpy.any(occupancies[numpy.isfinite(occupancies)] < 1.0):
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
    return structure, tuple(issues), tuple(normalizations)


def parse_cif(source: Path) -> ImportBatch:
    gemmi = _gemmi()
    source = Path(source)
    content = source.read_bytes()
    source_hash = hashlib.sha256(content).hexdigest()
    try:
        document = _read_document(gemmi, content)
    except RuntimeError as error:
        raise ValueError(f"Gemmi could not parse CIF: {error}") from error
    if not document:
        raise ValueError("CIF document does not contain a data block")

    blocks = tuple(document)
    block_names = tuple(block.name for block in blocks)
    block_keys = _block_keys(block_names)
    envelope_id = uuid5(
        NAMESPACE_URL,
        f"chemblender:cif:{ADAPTER_VERSION}:{source_hash}:envelope",
    )
    provenance_id = uuid5(envelope_id, "provenance")
    tag_names = tuple(
        dict.fromkeys(tag for block in blocks for tag in _tag_names(block))
    )
    envelope = CIFEnvelope(
        id=envelope_id,
        revision=source_hash,
        block_name=block_names[0],
        source_bytes=content,
        tag_names=tag_names,
        provenance_ids=(provenance_id,),
        block_names=block_names,
        block_keys=block_keys,
    )
    issues = [
        ParserIssue(
            IssueKind.AMBIGUOUS,
            f"cif.blocks[{index}].name",
            (
                f"duplicate CIF block name {name!r} was assigned "
                f"source-local key {block_keys[index]!r}"
            ),
        )
        for index, name in enumerate(block_names)
        if block_names[:index].count(name)
    ]
    structures = []
    normalizations = []
    for index, (block, block_name, block_key) in enumerate(
        zip(blocks, block_names, block_keys)
    ):
        try:
            structure, block_issues, block_normalizations = _parse_block(
                gemmi,
                block,
                source_hash=source_hash,
                envelope_id=envelope_id,
                block_name=block_name,
                block_key=block_key,
                block_index=index,
            )
        except ValueError as error:
            issues.append(
                ParserIssue(
                    IssueKind.WARNING,
                    f"cif.blocks[{index}]",
                    f"block {block_key!r} has no importable structure: {error}",
                )
            )
            continue
        structures.append(structure)
        issues.extend(block_issues)
        normalizations.extend(
            f"{block_key}:{operation}"
            for operation in block_normalizations
        )
    if not structures:
        issues.append(
            ParserIssue(
                IssueKind.INVALID,
                "cif.blocks",
                "CIF document does not contain an importable atom-site block",
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
        parameters=(
            ("format", "cif"),
            ("block_keys", block_keys),
            ("normalizations", tuple(normalizations)),
        ),
    )
    report = ParserReport(
        reader_id="cif",
        reader_version=ADAPTER_VERSION,
        created_entity_ids=tuple(
            [structure.id for structure in structures]
            + [envelope_id, provenance_id]
        ),
        parsed_capabilities=("structure", "crystal", "cif_envelope"),
        issues=tuple(issues),
    )
    return ImportBatch(
        structures=tuple(structures),
        cif_envelopes=(envelope,),
        provenance=(provenance,),
        report=report,
    )


CIF_READER = ReaderDescriptor(
    reader_id="cif",
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
