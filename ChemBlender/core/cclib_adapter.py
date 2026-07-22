import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from .model import (
    ArrayData,
    CalculationRecord,
    CalculationStatus,
    DatasetStatus,
    FrameSet,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    PropertyDataset,
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
_MAPPED_ATTRIBUTES = {
    "atomcharges",
    "atomcoords",
    "atomnos",
    "atomspins",
    "charge",
    "metadata",
    "mult",
    "scfenergies",
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
                PropertyDataset(
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
    },
    priority=80,
    sniff=sniff_cclib_output,
    parse=parse_cclib_output,
)
