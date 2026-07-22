import hashlib
import json
import math
import re
from pathlib import Path
from uuid import UUID, uuid5

from .model import (
    ArrayData,
    AtomicProperty,
    CJSONEnvelope,
    DatasetStatus,
    ExcitedStateReferences,
    ExcitedStateSet,
    FrameSet,
    ImportBatch,
    IssueKind,
    MolecularTopology,
    ParserIssue,
    ParserReport,
    PropertyDataset,
    ProvenanceRecord,
    Spectrum,
    SpectrumKind,
    SpectrumProfile,
    Structure,
)
from .readers import CapabilitySupport, ReaderDescriptor, SniffMatch, SniffResult


ADAPTER_VERSION = "0.1.0"
_IDENTITY_NAMESPACE = UUID("a53a54ab-2a6f-42cb-b46f-9faf15d43349")
_EV_TO_INVERSE_CENTIMETER = 8065.544005


class CJSONError(ValueError):
    pass


class CJSONCompatibilityError(CJSONError):
    pass


def _reject_constant(value):
    raise CJSONError(f"non-finite JSON value: {value}")


def _mapping(value, path):
    if not isinstance(value, dict):
        raise CJSONError(f"{path} must be an object")
    return value


def _identity(source_hash, role):
    return uuid5(_IDENTITY_NAMESPACE, f"{source_hash}:{role}")


def _canonical(document):
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _finite_array(value, path, *, dtype=float):
    import numpy

    try:
        raw = numpy.asarray(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise CJSONError(f"{path} must be a numeric array") from error
    if raw.dtype.kind not in "iuf" or not numpy.all(numpy.isfinite(raw)):
        raise CJSONError(f"{path} must contain finite values")
    if dtype is int and numpy.any(raw != numpy.floor(raw)):
        raise CJSONError(f"{path} must contain integers")
    array = numpy.asarray(raw, dtype=dtype)
    return array


def _integer(value, path, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CJSONError(f"{path} must be an integer")
    integer = int(value)
    if not math.isfinite(float(value)) or integer != value or (positive and integer <= 0):
        raise CJSONError(f"{path} must be an integer")
    return integer


def _topology(document, atom_count):
    import numpy

    bonds = document.get("bonds")
    if bonds is None:
        return None
    bonds = _mapping(bonds, "bonds")
    connections = _mapping(bonds.get("connections"), "bonds.connections")
    indices = _finite_array(
        connections.get("index"), "bonds.connections.index", dtype=int
    )
    if indices.ndim != 1 or indices.size % 2:
        raise CJSONError("bonds.connections.index must contain atom-index pairs")
    indices = indices.reshape((-1, 2))
    if indices.size and (
        numpy.any(indices < 0)
        or numpy.any(indices >= atom_count)
        or numpy.any(indices[:, 0] == indices[:, 1])
    ):
        raise CJSONError("bond atom indices must reference distinct structure atoms")
    raw_orders = bonds.get("order", [1] * len(indices))
    orders = _finite_array(raw_orders, "bonds.order")
    if (
        orders.shape != (len(indices),)
        or numpy.any(orders != numpy.floor(orders))
        or numpy.any(orders < 1.0)
        or numpy.any(orders > 6.0)
    ):
        raise CJSONError("bonds.order must contain one integer from 1 to 6 per bond")
    return MolecularTopology(
        bond_indices=ArrayData(indices, ("bond", "endpoint"), "dimensionless"),
        bond_orders=ArrayData(orders, ("bond",), "dimensionless"),
    )


def _atomic_dataset(
    source_hash,
    name,
    values,
    unit,
    structure_id,
    provenance_id,
    *,
    status=DatasetStatus.COMPLETE,
):
    import numpy

    array = numpy.asarray(values)
    dims = ("atom",) if array.ndim == 1 else ("atom", "xyz")
    revision = hashlib.sha256(array.tobytes() + unit.encode("ascii")).hexdigest()
    return AtomicProperty(
        id=_identity(source_hash, f"dataset:{name}"),
        revision=revision,
        semantic_role=name,
        domain="atom",
        data=ArrayData(array, dims, unit),
        status=status,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
    )


def _atom_datasets(atoms, atom_count, source_hash, structure_id, provenance_id, issues):
    import numpy

    datasets = []
    if "formalCharges" in atoms:
        values = _finite_array(atoms["formalCharges"], "atoms.formalCharges", dtype=int)
        if values.shape != (atom_count,):
            raise CJSONError("atoms.formalCharges must match the atom count")
        datasets.append(_atomic_dataset(source_hash, "formal_charge", values, "elementary_charge", structure_id, provenance_id))
    if "selected" in atoms:
        values = numpy.asarray(atoms["selected"])
        if values.shape != (atom_count,) or values.dtype.kind not in "biu":
            raise CJSONError("atoms.selected must match the atom count and contain booleans")
        datasets.append(_atomic_dataset(source_hash, "selected", values.astype(bool), "dimensionless", structure_id, provenance_id))
    partial = atoms.get("partialCharges", {})
    if partial:
        partial = _mapping(partial, "atoms.partialCharges")
        for method, raw in sorted(partial.items()):
            values = _finite_array(raw, f"atoms.partialCharges.{method}")
            if values.shape != (atom_count,):
                raise CJSONError(f"atoms.partialCharges.{method} must match the atom count")
            semantic = re.sub(r"[^a-z0-9]+", "_", str(method).lower()).strip("_") + "_charge"
            if semantic == "_charge":
                raise CJSONError("partial charge method names must be non-empty")
            datasets.append(_atomic_dataset(source_hash, semantic, values, "elementary_charge", structure_id, provenance_id))
    if "forces" in atoms:
        values = _finite_array(atoms["forces"], "atoms.forces")
        if values.size != atom_count * 3:
            raise CJSONError("atoms.forces must contain three values per atom")
        datasets.append(_atomic_dataset(source_hash, "force", values.reshape((atom_count, 3)), "unknown", structure_id, provenance_id, status=DatasetStatus.AMBIGUOUS))
        issues.append(ParserIssue(IssueKind.AMBIGUOUS, "atoms.forces", "CJSON does not declare a force unit"))
    return datasets


def _trajectory(atoms, atom_count, source_hash, structure_id, provenance_id):
    coords = _mapping(atoms.get("coords", {}), "atoms.coords")
    if "3dSets" not in coords:
        return None
    values = _finite_array(coords["3dSets"], "atoms.coords.3dSets")
    if values.ndim != 2 or values.shape[1] != atom_count * 3:
        raise CJSONError("atoms.coords.3dSets must contain complete coordinate frames")
    values = values.reshape((values.shape[0], atom_count, 3))
    revision = hashlib.sha256(values.tobytes()).hexdigest()
    return FrameSet(
        id=_identity(source_hash, "dataset:trajectory"),
        revision=revision,
        semantic_role="coordinates",
        domain="frame",
        data=ArrayData(values, ("frame", "atom", "xyz"), "angstrom"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
        comments=("",) * values.shape[0],
    )


def _electronic_spectra(document, source_hash, structure_id, provenance_id):
    import numpy

    spectra = document.get("spectra")
    if not isinstance(spectra, dict) or not isinstance(spectra.get("electronic"), dict):
        return []
    electronic = spectra["electronic"]
    energies_ev = _finite_array(electronic.get("energies"), "spectra.electronic.energies")
    strengths = _finite_array(electronic.get("intensities"), "spectra.electronic.intensities")
    if energies_ev.ndim != 1 or strengths.shape != energies_ev.shape or numpy.any(energies_ev < 0.0) or numpy.any(strengths < 0.0):
        raise CJSONError("electronic energies and intensities must be matching non-negative arrays")
    state_count = len(energies_ev)
    energies = energies_ev * _EV_TO_INVERSE_CENTIMETER
    rotation = None
    status = DatasetStatus.COMPLETE
    if "rotation" in electronic:
        rotation_values = _finite_array(electronic["rotation"], "spectra.electronic.rotation")
        if rotation_values.shape != energies_ev.shape:
            raise CJSONError("spectra.electronic.rotation must match energies")
        rotation = ArrayData(rotation_values, ("state",), "unknown")
        status = DatasetStatus.AMBIGUOUS
    states_id = _identity(source_hash, "dataset:excited_states")
    states = ExcitedStateSet(
        id=states_id,
        revision=hashlib.sha256(energies.tobytes() + strengths.tobytes()).hexdigest(),
        semantic_role="excited_states",
        domain="state",
        data=ArrayData(energies, ("state",), "inverse_centimeter"),
        status=status,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
        oscillator_strengths=ArrayData(strengths, ("state",), "dimensionless"),
        rotatory_strengths=rotation,
        electric_transition_dipoles=None,
        velocity_transition_dipoles=None,
        magnetic_transition_dipoles=None,
        symmetries=None,
        multiplicities=(None,) * state_count,
        configurations=None,
        state_references=tuple(ExcitedStateReferences() for _ in range(state_count)),
    )
    uv_vis = Spectrum(
        id=_identity(source_hash, "dataset:uv_vis_spectrum"),
        revision=states.revision,
        semantic_role="uv_vis_spectrum",
        domain="frequency",
        data=ArrayData(strengths.copy(), ("sample",), "dimensionless"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        axis=ArrayData(energies.copy(), ("sample",), "inverse_centimeter"),
        kind=SpectrumKind.UV_VIS,
        profile=SpectrumProfile.STICK,
        source_dataset_id=states_id,
        fwhm=None,
        selection_policy="all_states",
    )
    result = [states, uv_vis]
    if rotation is not None:
        result.append(
            Spectrum(
                id=_identity(source_hash, "dataset:ecd_spectrum"),
                revision=states.revision,
                semantic_role="ecd_spectrum",
                domain="frequency",
                data=ArrayData(rotation.values.copy(), ("sample",), "unknown"),
                status=DatasetStatus.AMBIGUOUS,
                source_calculation=None,
                provenance_ids=(provenance_id,),
                axis=ArrayData(energies.copy(), ("sample",), "inverse_centimeter"),
                kind=SpectrumKind.ECD,
                profile=SpectrumProfile.STICK,
                source_dataset_id=states_id,
                fwhm=None,
                selection_policy="all_states",
            )
        )
    return result


def parse_cjson(source):
    import numpy

    source = Path(source)
    try:
        source_bytes = source.read_bytes()
        document = json.loads(source_bytes.decode("utf-8-sig"), parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CJSONError(f"cannot read CJSON: {source}") from error
    document = _mapping(document, "document")
    version = document.get("chemicalJson", document.get("chemical json"))
    if version not in (0, 1) or isinstance(version, bool):
        raise CJSONCompatibilityError(f"unsupported CJSON version {version}")
    atoms = _mapping(document.get("atoms"), "atoms")
    elements = _mapping(atoms.get("elements"), "atoms.elements")
    atomic_numbers = _finite_array(elements.get("number"), "atoms.elements.number", dtype=int)
    if atomic_numbers.ndim != 1 or not len(atomic_numbers) or numpy.any(atomic_numbers < 0) or numpy.any(atomic_numbers > 118):
        raise CJSONError("atoms.elements.number must contain atomic numbers from 0 to 118")
    atom_count = len(atomic_numbers)
    issues = []
    cell = None
    if isinstance(document.get("unitCell"), dict) and "cellVectors" in document["unitCell"]:
        vectors = _finite_array(document["unitCell"]["cellVectors"], "unitCell.cellVectors")
        if vectors.size != 9:
            raise CJSONError("unitCell.cellVectors must contain nine values")
        cell = ArrayData(vectors.reshape((3, 3)), ("cell_vector", "xyz"), "angstrom")
    coords_object = _mapping(atoms.get("coords", {}), "atoms.coords")
    if "3d" in coords_object:
        coordinates = _finite_array(coords_object["3d"], "atoms.coords.3d")
        if coordinates.size != atom_count * 3:
            raise CJSONError("atoms.coords.3d must contain three values per atom")
        coordinates = coordinates.reshape((atom_count, 3))
    elif "3dFractional" in coords_object and cell is not None:
        fractional = _finite_array(
            coords_object["3dFractional"], "atoms.coords.3dFractional"
        )
        if fractional.size != atom_count * 3:
            raise CJSONError("atoms.coords.3dFractional must contain three values per atom")
        coordinates = fractional.reshape((atom_count, 3)) @ cell.values
    else:
        coordinates = numpy.zeros((atom_count, 3), dtype=float)
        issues.append(ParserIssue(IssueKind.MISSING, "atoms.coords.3d", "missing coordinates were initialized to zero like Avogadro CjsonFormat"))

    properties = document.get("properties", {})
    properties = _mapping(properties, "properties")
    charge = _integer(properties.get("totalCharge", 0), "properties.totalCharge")
    multiplicity = _integer(properties.get("totalSpinMultiplicity", 1), "properties.totalSpinMultiplicity", positive=True)
    topology = _topology(document, atom_count)

    source_hash = hashlib.sha256(source_bytes).hexdigest()
    provenance_id = _identity(source_hash, "provenance")
    structure_id = _identity(source_hash, "structure")
    structure_revision = hashlib.sha256(
        atomic_numbers.tobytes() + coordinates.tobytes() + (b"" if topology is None else topology.bond_indices.values.tobytes())
    ).hexdigest()
    structure = Structure(
        id=structure_id,
        revision=structure_revision,
        atomic_numbers=tuple(int(value) for value in atomic_numbers),
        coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"),
        cell=cell,
        molecular_charge=charge,
        molecular_multiplicity=multiplicity,
        topology=topology,
    )
    atom_fields = dict(atoms)
    if "partialCharges" not in atom_fields and "partialCharges" in document:
        atom_fields["partialCharges"] = document["partialCharges"]
    datasets = _atom_datasets(atom_fields, atom_count, source_hash, structure_id, provenance_id, issues)
    trajectory = _trajectory(atoms, atom_count, source_hash, structure_id, provenance_id)
    if trajectory is not None:
        datasets.append(trajectory)
    datasets.extend(_electronic_spectra(document, source_hash, structure_id, provenance_id))

    vibrations = document.get("vibrations")
    if isinstance(vibrations, dict) and "frequencies" in vibrations:
        frequencies = _finite_array(vibrations["frequencies"], "vibrations.frequencies")
        if frequencies.ndim != 1:
            raise CJSONError("vibrations.frequencies must be one-dimensional")
        datasets.append(
            PropertyDataset(
                id=_identity(source_hash, "dataset:vibrational_frequencies"),
                revision=hashlib.sha256(frequencies.tobytes()).hexdigest(),
                semantic_role="vibrational_frequencies",
                domain="mode",
                data=ArrayData(frequencies, ("mode",), "inverse_centimeter"),
                status=DatasetStatus.PARTIAL,
                source_calculation=None,
                provenance_ids=(provenance_id,),
            )
        )
        for field in ("eigenVectors", "intensities", "ramanIntensities"):
            if field in vibrations:
                issues.append(ParserIssue(IssueKind.AMBIGUOUS, f"vibrations.{field}", "CJSON does not declare the convention or unit required by the typed vibration model"))
    for field in ("orbitals", "cube", "surfaces"):
        if field in document:
            issues.append(ParserIssue(IssueKind.UNSUPPORTED, field, "field is preserved in the raw CJSON envelope pending a lossless typed mapping"))

    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=source_hash,
        producer="ChemBlender CJSON adapter",
        producer_version=ADAPTER_VERSION,
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse_cjson",
        parameters=(("chemical_json_version", version),),
    )
    envelope = CJSONEnvelope(
        id=_identity(source_hash, "envelope"),
        revision=source_hash,
        format_version=version,
        source_bytes=_canonical(document),
        provenance_ids=(provenance_id,),
    )
    created_ids = (structure.id, envelope.id, *(dataset.id for dataset in datasets), provenance.id)
    capabilities = ["structure"]
    if topology is not None:
        capabilities.append("topology")
    if trajectory is not None:
        capabilities.append("trajectory")
    if any(isinstance(item, ExcitedStateSet) for item in datasets):
        capabilities.extend(("excited_state", "spectrum"))
    report = ParserReport(
        reader_id="cjson",
        reader_version=ADAPTER_VERSION,
        created_entity_ids=created_ids,
        parsed_capabilities=tuple(capabilities),
        issues=tuple(issues),
    )
    return ImportBatch(
        structures=(structure,),
        cjson_envelopes=(envelope,),
        datasets=tuple(datasets),
        provenance=(provenance,),
        report=report,
    )


def export_cjson(envelope):
    if not isinstance(envelope, CJSONEnvelope):
        raise TypeError("envelope must be a CJSONEnvelope")
    try:
        return json.loads(envelope.source_bytes.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CJSONError("CJSON envelope is not valid UTF-8 JSON") from error


def sniff_cjson(source, prefix):
    try:
        text = prefix.decode("utf-8-sig")
    except UnicodeError:
        return SniffResult(SniffMatch.NONE, "prefix is not UTF-8 text")
    match = re.search(r'"chemical(?:Json| json)"\s*:\s*([0-9]+)', text)
    if not match:
        return SniffResult(SniffMatch.NONE, "JSON does not declare chemicalJson")
    version = int(match.group(1))
    return SniffResult(
        SniffMatch.EXACT if version in (0, 1) else SniffMatch.POSSIBLE,
        f"CJSON version {version}",
    )


CJSON_READER = ReaderDescriptor(
    reader_id="cjson",
    reader_version=ADAPTER_VERSION,
    extensions=(".cjson",),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "topology": CapabilitySupport.SUPPORTED,
        "trajectory": CapabilitySupport.PARTIAL,
        "excited_state": CapabilitySupport.PARTIAL,
        "spectrum": CapabilitySupport.PARTIAL,
        "vibration": CapabilitySupport.PARTIAL,
        "grid": CapabilitySupport.PARTIAL,
        "orbital": CapabilitySupport.PARTIAL,
    },
    priority=100,
    sniff=sniff_cjson,
    parse=parse_cjson,
)
