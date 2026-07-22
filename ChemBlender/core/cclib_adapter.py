import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from .model import (
    ArrayData,
    AtomicProperty,
    CalculationRecord,
    CalculationStatus,
    DatasetStatus,
    ExcitationContribution,
    ExcitedStateReferences,
    ExcitedStateSet,
    FrameSet,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    PropertyDataset,
    ProvenanceRecord,
    Structure,
    SpinChannel,
    VibrationalModeSet,
)
from .readers import (
    CapabilitySupport,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
)


ADAPTER_VERSION = "4"
_MAPPED_ATTRIBUTES = {
    "atomcharges",
    "atomcoords",
    "atomnos",
    "atomspins",
    "charge",
    "metadata",
    "mult",
    "scfenergies",
    "etdips",
    "etenergies",
    "etmagdips",
    "etoscs",
    "etrotats",
    "etsecs",
    "etsyms",
    "etveldips",
    "vibdisps",
    "vibfconsts",
    "vibfreqs",
    "vibirs",
    "vibramans",
    "vibrmasses",
    "vibsyms",
}


class CCLibDependencyError(ImportError):
    pass


def sniff_cclib_output(source: Path, prefix: bytes) -> SniffResult:
    del source
    if b"Entering Gaussian System" in prefix or b"Gaussian, Inc." in prefix:
        return SniffResult(SniffMatch.EXACT, "Gaussian output marker")
    if re.search(rb"\*\s+O\s+R\s+C\s+A\s+\*", prefix):
        return SniffResult(SniffMatch.EXACT, "ORCA output banner")
    return SniffResult(SniffMatch.NONE, "no supported cclib output marker")


def _source_identity(source):
    source = Path(source)
    try:
        content = source.read_bytes()
    except FileNotFoundError:
        return source, "", "in_memory"
    source_hash = hashlib.sha256(content).hexdigest()
    return source, source_hash, source_hash


def _array(data, name, rank, *, shape=None):
    import numpy

    values = numpy.asarray(getattr(data, name))
    if values.ndim != rank or (shape is not None and values.shape != shape):
        expected = f"rank {rank}" if shape is None else f"shape {shape}"
        raise ValueError(f"cclib {name} must have {expected}")
    if not numpy.isfinite(values).all():
        raise ValueError(f"cclib {name} contains non-finite values")
    return values


def _semantic_name(name):
    token = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    if not token or not token[0].isalpha():
        raise ValueError(f"cclib property name cannot form a semantic token: {name}")
    return token


def _data_attributes(data):
    getattributes = getattr(data, "getattributes", None)
    if callable(getattributes):
        return getattributes()
    return {key: value for key, value in vars(data).items() if not key.startswith("_")}


def _status(metadata, issues):
    success = metadata.get("success")
    if success is True:
        return CalculationStatus.SUCCESS
    if success is False:
        return CalculationStatus.FAILED
    issues.append(
        ParserIssue(
            IssueKind.AMBIGUOUS,
            "calculation.status",
            "cclib metadata does not report calculation success",
        )
    )
    return CalculationStatus.INCOMPLETE


def _adapt_vibrations(
    data,
    *,
    atom_count,
    structure_id,
    calculation_id,
    provenance_id,
    revision,
    issues,
):
    import numpy

    attributes = (
        "vibfreqs",
        "vibdisps",
        "vibrmasses",
        "vibfconsts",
        "vibirs",
        "vibramans",
        "vibsyms",
    )
    if not any(hasattr(data, name) for name in attributes):
        return None
    if not hasattr(data, "vibfreqs"):
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "vibration.frequencies",
                "cclib did not parse vibrational frequencies",
            )
        )
        return None
    if not hasattr(data, "vibdisps"):
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "vibration.displacements",
                "cclib did not parse vibrational displacements",
            )
        )
        return None

    frequencies = _array(data, "vibfreqs", 1)
    if frequencies.size == 0 or numpy.iscomplexobj(frequencies):
        raise ValueError("cclib vibfreqs must contain real mode frequencies")
    mode_count = frequencies.shape[0]
    displacements = _array(
        data,
        "vibdisps",
        3,
        shape=(mode_count, atom_count, 3),
    )
    if numpy.iscomplexobj(displacements):
        raise ValueError("cclib vibdisps must contain real Cartesian displacements")

    optional_specs = (
        ("vibrmasses", "vibration.reduced_mass", "dalton"),
        ("vibfconsts", "vibration.force_constant", "millidyne_per_angstrom"),
        ("vibirs", "vibration.ir_intensity", "kilometer_per_mole"),
        (
            "vibramans",
            "vibration.raman_activity",
            "angstrom_four_per_dalton",
        ),
    )
    optional = {}
    for attribute, path, unit in optional_specs:
        if not hasattr(data, attribute):
            issues.append(
                ParserIssue(
                    IssueKind.MISSING,
                    path,
                    f"cclib did not parse {attribute}",
                )
            )
            optional[attribute] = None
            continue
        values = _array(data, attribute, 1, shape=(mode_count,))
        if numpy.iscomplexobj(values):
            raise ValueError(f"cclib {attribute} must contain real values")
        optional[attribute] = ArrayData(
            numpy.array(values, dtype=float, copy=True),
            ("mode",),
            unit,
        )

    symmetries = None
    if hasattr(data, "vibsyms"):
        symmetries = tuple(getattr(data, "vibsyms"))
        if len(symmetries) != mode_count or any(
            not isinstance(value, str) or not value for value in symmetries
        ):
            raise ValueError("cclib vibsyms must contain one label per mode")
    else:
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "vibration.symmetry",
                "cclib did not parse vibration symmetry labels",
            )
        )

    return VibrationalModeSet(
        id=uuid4(),
        revision=revision,
        semantic_role="vibrational_modes",
        domain="mode",
        data=ArrayData(
            numpy.array(frequencies, dtype=float, copy=True),
            ("mode",),
            "inverse_centimeter",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=calculation_id,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
        displacements=ArrayData(
            numpy.array(displacements, dtype=float, copy=True),
            ("mode", "atom", "xyz"),
            "angstrom",
        ),
        reduced_masses=optional["vibrmasses"],
        force_constants=optional["vibfconsts"],
        ir_intensities=optional["vibirs"],
        raman_activities=optional["vibramans"],
        symmetries=symmetries,
        displacement_convention="cclib_cartesian",
    )


def _multiplicity(label):
    prefixes = {
        "singlet": 1,
        "doublet": 2,
        "triplet": 3,
        "quartet": 4,
        "quintet": 5,
    }
    normalized = label.strip().lower()
    return next(
        (value for prefix, value in prefixes.items() if normalized.startswith(prefix)),
        None,
    )


def _adapt_configurations(values, state_count):
    from numbers import Integral

    if len(values) != state_count:
        raise ValueError("cclib etsecs must contain one configuration list per state")
    states = []
    for state in values:
        contributions = []
        for item in state:
            if len(item) != 3 or len(item[0]) != 2 or len(item[1]) != 2:
                raise ValueError("cclib etsecs entries must contain two orbitals and a coefficient")
            occupied, virtual, coefficient = item
            occupied_index, occupied_spin = occupied
            virtual_index, virtual_spin = virtual
            if (
                isinstance(occupied_index, bool)
                or not isinstance(occupied_index, Integral)
                or occupied_index < 0
                or isinstance(virtual_index, bool)
                or not isinstance(virtual_index, Integral)
                or virtual_index < 0
                or occupied_spin not in (0, 1)
                or virtual_spin not in (0, 1)
            ):
                raise ValueError("cclib etsecs contains an invalid orbital or spin index")
            contributions.append(
                ExcitationContribution(
                    occupied_orbital=int(occupied_index),
                    occupied_spin=(
                        SpinChannel.ALPHA if occupied_spin == 0 else SpinChannel.BETA
                    ),
                    virtual_orbital=int(virtual_index),
                    virtual_spin=(
                        SpinChannel.ALPHA if virtual_spin == 0 else SpinChannel.BETA
                    ),
                    coefficient=float(coefficient),
                )
            )
        states.append(tuple(contributions))
    return tuple(states)


def _adapt_excited_states(
    data,
    *,
    structure_id,
    calculation_id,
    provenance_id,
    revision,
    issues,
):
    import numpy

    attributes = (
        "etenergies",
        "etoscs",
        "etrotats",
        "etdips",
        "etveldips",
        "etmagdips",
        "etsyms",
        "etsecs",
    )
    if not any(hasattr(data, name) for name in attributes):
        return None
    if not hasattr(data, "etenergies"):
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "excited_state.energies",
                "cclib did not parse excited-state energies",
            )
        )
        return None

    energies = _array(data, "etenergies", 1)
    if (
        energies.size == 0
        or numpy.iscomplexobj(energies)
        or numpy.any(energies < 0.0)
    ):
        raise ValueError("cclib etenergies must contain real non-negative energies")
    state_count = energies.shape[0]

    optional = {}
    for attribute, path, shape, dims, unit in (
        (
            "etoscs",
            "excited_state.oscillator_strength",
            (state_count,),
            ("state",),
            "dimensionless",
        ),
        (
            "etrotats",
            "excited_state.rotatory_strength",
            (state_count,),
            ("state",),
            "unknown",
        ),
        (
            "etdips",
            "excited_state.electric_transition_dipole",
            (state_count, 3),
            ("state", "xyz"),
            "elementary_charge_bohr",
        ),
        (
            "etveldips",
            "excited_state.velocity_transition_dipole",
            (state_count, 3),
            ("state", "xyz"),
            "elementary_charge_bohr",
        ),
        (
            "etmagdips",
            "excited_state.magnetic_transition_dipole",
            (state_count, 3),
            ("state", "xyz"),
            "elementary_charge_bohr",
        ),
    ):
        if not hasattr(data, attribute):
            issues.append(
                ParserIssue(
                    IssueKind.MISSING,
                    path,
                    f"cclib did not parse {attribute}",
                )
            )
            optional[attribute] = None
            continue
        values = _array(data, attribute, len(shape), shape=shape)
        if numpy.iscomplexobj(values):
            raise ValueError(f"cclib {attribute} must contain real values")
        if attribute == "etoscs" and numpy.any(values < 0.0):
            raise ValueError("cclib etoscs must contain non-negative values")
        optional[attribute] = ArrayData(
            numpy.array(values, dtype=float, copy=True), dims, unit
        )

    status = DatasetStatus.COMPLETE
    if optional["etrotats"] is not None:
        status = DatasetStatus.AMBIGUOUS
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                "excited_state.rotatory_strength.unit",
                "cclib does not define one cross-parser rotatory-strength unit",
            )
        )

    symmetries = None
    multiplicities = (None,) * state_count
    if hasattr(data, "etsyms"):
        symmetries = tuple(getattr(data, "etsyms"))
        if len(symmetries) != state_count or any(
            not isinstance(value, str) or not value for value in symmetries
        ):
            raise ValueError("cclib etsyms must contain one label per state")
        multiplicities = tuple(_multiplicity(label) for label in symmetries)
        if any(value is None for value in multiplicities):
            issues.append(
                ParserIssue(
                    IssueKind.AMBIGUOUS,
                    "excited_state.multiplicity",
                    "one or more cclib symmetry labels have unknown multiplicity",
                )
            )
    else:
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "excited_state.symmetry",
                "cclib did not parse excited-state symmetry labels",
            )
        )

    configurations = None
    if hasattr(data, "etsecs"):
        try:
            configurations = _adapt_configurations(
                getattr(data, "etsecs"), state_count
            )
        except (TypeError, ValueError, OverflowError) as error:
            issues.append(
                ParserIssue(
                    IssueKind.INVALID,
                    "excited_state.configurations",
                    str(error),
                )
            )
    else:
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "excited_state.configurations",
                "cclib did not parse excited-state configurations",
            )
        )

    return ExcitedStateSet(
        id=uuid4(),
        revision=revision,
        semantic_role="excited_states",
        domain="state",
        data=ArrayData(
            numpy.array(energies, dtype=float, copy=True),
            ("state",),
            "inverse_centimeter",
        ),
        status=status,
        source_calculation=calculation_id,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
        oscillator_strengths=optional["etoscs"],
        rotatory_strengths=optional["etrotats"],
        electric_transition_dipoles=optional["etdips"],
        velocity_transition_dipoles=optional["etveldips"],
        magnetic_transition_dipoles=optional["etmagdips"],
        symmetries=symmetries,
        multiplicities=multiplicities,
        configurations=configurations,
        state_references=tuple(
            ExcitedStateReferences() for _ in range(state_count)
        ),
    )


def adapt_ccdata(data, source, *, cclib_version="unknown") -> ImportBatch:
    import numpy

    source, source_hash, revision = _source_identity(source)
    if not hasattr(data, "atomnos") or not hasattr(data, "atomcoords"):
        raise ValueError("cclib data requires atomnos and atomcoords")

    atomnos = _array(data, "atomnos", 1)
    if atomnos.size == 0 or not numpy.issubdtype(atomnos.dtype, numpy.integer):
        raise ValueError("cclib atomnos must be a non-empty integer array")
    atomic_numbers = tuple(int(number) for number in atomnos)
    if any(not 0 <= number <= 118 for number in atomic_numbers):
        raise ValueError("cclib atomnos must be from 0 to 118")

    atomcoords = _array(data, "atomcoords", 3)
    if atomcoords.shape[0] == 0 or atomcoords.shape[1:] != (len(atomnos), 3):
        raise ValueError("cclib atomcoords must have shape (frame, atom, 3)")
    atomcoords = numpy.asarray(atomcoords, dtype=float)

    metadata = getattr(data, "metadata", {})
    if not isinstance(metadata, Mapping):
        raise ValueError("cclib metadata must be a mapping")
    metadata = dict(metadata)
    issues = []
    calculation_status = _status(metadata, issues)

    structure_id = uuid4()
    calculation_id = uuid4()
    provenance_id = uuid4()
    structure = Structure(
        id=structure_id,
        revision=revision,
        atomic_numbers=atomic_numbers,
        coordinates=ArrayData(
            numpy.array(atomcoords[-1], copy=True),
            ("atom", "xyz"),
            "angstrom",
        ),
    )

    datasets = []
    parsed_capabilities = ["structure"]
    if atomcoords.shape[0] > 1:
        datasets.append(
            FrameSet(
                id=uuid4(),
                revision=revision,
                semantic_role="coordinates",
                domain="frame",
                data=ArrayData(
                    numpy.array(atomcoords, copy=True),
                    ("frame", "atom", "xyz"),
                    "angstrom",
                ),
                status=DatasetStatus.COMPLETE,
                source_calculation=calculation_id,
                provenance_ids=(provenance_id,),
                structure_id=structure_id,
                comments=("",) * atomcoords.shape[0],
            )
        )
        parsed_capabilities.append("trajectory")

    if hasattr(data, "scfenergies"):
        energies = _array(data, "scfenergies", 1)
        if energies.size == 0:
            raise ValueError("cclib scfenergies must not be empty")
        datasets.append(
            PropertyDataset(
                id=uuid4(),
                revision=revision,
                semantic_role="scf_energy",
                domain="calculation_step",
                data=ArrayData(
                    numpy.array(energies, dtype=float, copy=True),
                    ("step",),
                    "electron_volt",
                ),
                status=DatasetStatus.COMPLETE,
                source_calculation=calculation_id,
                provenance_ids=(provenance_id,),
            )
        )
        parsed_capabilities.append("energy")
    else:
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "energy.scf",
                "cclib did not parse SCF energies",
            )
        )

    property_count = 0
    for attribute, suffix, unit in (
        ("atomcharges", "charge", "elementary_charge"),
        ("atomspins", "spin_population", "dimensionless"),
    ):
        properties = getattr(data, attribute, None)
        if properties is None:
            continue
        if not isinstance(properties, Mapping):
            raise ValueError(f"cclib {attribute} must be a mapping")
        for name in sorted(properties):
            values = numpy.asarray(properties[name])
            if values.shape != (len(atomnos),) or not numpy.isfinite(values).all():
                raise ValueError(
                    f"cclib {attribute}[{name!r}] must have shape ({len(atomnos)},)"
                )
            datasets.append(
                AtomicProperty(
                    id=uuid4(),
                    revision=revision,
                    semantic_role=f"{_semantic_name(name)}_{suffix}",
                    domain="atom",
                    data=ArrayData(
                        numpy.array(values, dtype=float, copy=True),
                        ("atom",),
                        unit,
                    ),
                    status=DatasetStatus.COMPLETE,
                    source_calculation=calculation_id,
                    provenance_ids=(provenance_id,),
                    structure_id=structure_id,
                )
            )
            property_count += 1
    if property_count:
        parsed_capabilities.append("atomic_property")
    else:
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "atomic_property",
                "cclib did not parse atomic charges or spin populations",
            )
        )

    vibrations = _adapt_vibrations(
        data,
        atom_count=len(atomnos),
        structure_id=structure_id,
        calculation_id=calculation_id,
        provenance_id=provenance_id,
        revision=revision,
        issues=issues,
    )
    if vibrations is not None:
        datasets.append(vibrations)
        parsed_capabilities.append("vibration")

    excited_states = _adapt_excited_states(
        data,
        structure_id=structure_id,
        calculation_id=calculation_id,
        provenance_id=provenance_id,
        revision=revision,
        issues=issues,
    )
    if excited_states is not None:
        datasets.append(excited_states)
        parsed_capabilities.append("excited_state")

    attributes = _data_attributes(data)
    unmapped = tuple(sorted(set(attributes) - _MAPPED_ATTRIBUTES))
    if unmapped:
        issues.append(
            ParserIssue(
                IssueKind.UNSUPPORTED,
                "cclib.attributes",
                "adapter did not map: " + ", ".join(unmapped),
            )
        )

    parameters = (
        ("format", "cclib_output"),
        ("cclib_version", str(cclib_version)),
        ("package", str(metadata.get("package", "unknown"))),
        ("package_version", str(metadata.get("package_version", "unknown"))),
        ("methods", tuple(metadata.get("methods", ()))),
        ("basis_set", str(metadata.get("basis_set", "unknown"))),
        ("charge", getattr(data, "charge", None)),
        ("multiplicity", getattr(data, "mult", None)),
        ("unmapped_attributes", unmapped),
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="ChemBlender cclib adapter",
        producer_version=ADAPTER_VERSION,
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=parameters,
    )
    calculation = CalculationRecord(
        id=calculation_id,
        revision=revision,
        status=calculation_status,
        input_structure_ids=(),
        result_structure_ids=(structure_id,),
        dataset_ids=tuple(dataset.id for dataset in datasets),
        provenance_ids=(provenance_id,),
    )
    created_entity_ids = (
        structure_id,
        calculation_id,
        *(dataset.id for dataset in datasets),
        provenance_id,
    )
    report = ParserReport(
        reader_id="cclib_output",
        reader_version=ADAPTER_VERSION,
        created_entity_ids=created_entity_ids,
        parsed_capabilities=tuple(parsed_capabilities),
        issues=tuple(issues),
    )
    return ImportBatch(
        structures=(structure,),
        calculations=(calculation,),
        datasets=tuple(datasets),
        provenance=(provenance,),
        report=report,
    )


def parse_cclib_output(source) -> ImportBatch:
    try:
        import cclib
        from cclib.io import ccread
    except ImportError as error:
        raise CCLibDependencyError(
            "cclib output parsing requires the optional cclib dependency"
        ) from error

    source = Path(source)
    data = ccread(str(source))
    if data is None:
        raise ValueError(f"cclib could not parse output: {source}")
    return adapt_ccdata(data, source, cclib_version=cclib.__version__)


CCLIB_OUTPUT_READER = ReaderDescriptor(
    reader_id="cclib_output",
    reader_version=ADAPTER_VERSION,
    extensions=(".log", ".out"),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "trajectory": CapabilitySupport.SUPPORTED,
        "energy": CapabilitySupport.SUPPORTED,
        "atomic_property": CapabilitySupport.SUPPORTED,
        "vibration": CapabilitySupport.SUPPORTED,
        "excited_state": CapabilitySupport.SUPPORTED,
    },
    priority=80,
    sniff=sniff_cclib_output,
    parse=parse_cclib_output,
)
