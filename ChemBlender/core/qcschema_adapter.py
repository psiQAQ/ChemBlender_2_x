import hashlib
import json
import math
import re
from pathlib import Path
from uuid import UUID, uuid5

from ..Chem_data import ELEMENTS_DEFAULT
from .model import (
    ArrayData,
    CalculationMetadata,
    CalculationRecord,
    CalculationStatus,
    DatasetStatus,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    PropertyDataset,
    ProvenanceRecord,
    QCSchemaEnvelope,
    Structure,
)
from .readers import (
    CapabilitySupport,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
)


ADAPTER_VERSION = "0.1.0"
_IDENTITY_NAMESPACE = UUID("ea4359f7-6844-421b-9bc4-d76398113d70")
_SUPPORTED_RESULTS = {
    ("qcschema_output", 1),
    ("qcschema_atomic_result", 2),
}
_SUPPORTED_MOLECULES = {
    ("qcschema_molecule", 2),
    ("qcschema_molecule", 3),
}
_ATOMIC_NUMBERS = {
    symbol: data[0] for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
}
_ENERGY_PROPERTIES = {
    "return_energy",
    "scf_one_electron_energy",
    "scf_two_electron_energy",
    "nuclear_repulsion_energy",
}
_COUNT_PREFIXES = ("calcinfo_n",)
_TOKEN = re.compile(r"[a-z][a-z0-9_]*")


class QCSchemaError(ValueError):
    pass


class QCSchemaCompatibilityError(QCSchemaError):
    pass


def _reject_constant(value):
    raise QCSchemaError(f"non-finite JSON value: {value}")


def _require_mapping(value, path):
    if not isinstance(value, dict):
        raise QCSchemaError(f"{path} must be an object")
    return value


def _require_text(value, path):
    if not isinstance(value, str) or not value:
        raise QCSchemaError(f"{path} must be a non-empty string")
    return value


def _integral(value, path, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QCSchemaError(f"{path} must be an integer")
    integer = int(value)
    if not math.isfinite(float(value)) or integer != value or (positive and integer <= 0):
        raise QCSchemaError(f"{path} must be an integer")
    return integer


def _identity(source_hash, role):
    return uuid5(_IDENTITY_NAMESPACE, f"{source_hash}:{role}")


def _load_document(source):
    source = Path(source)
    try:
        source_bytes = source.read_bytes()
        document = json.loads(
            source_bytes.decode("utf-8-sig"), parse_constant=_reject_constant
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise QCSchemaError(f"cannot read QCSchema JSON: {source}") from error
    return source, source_bytes, _require_mapping(document, "document")


def _structure(molecule, source_hash, role, provenance_id):
    import numpy

    molecule = _require_mapping(molecule, role)
    symbols = molecule.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        raise QCSchemaError(f"{role}.symbols must be a non-empty array")
    try:
        atomic_numbers = tuple(_ATOMIC_NUMBERS[symbol] for symbol in symbols)
    except (KeyError, TypeError) as error:
        raise QCSchemaError(f"{role}.symbols contains an unknown element") from error
    geometry = numpy.asarray(molecule.get("geometry"), dtype=float)
    if geometry.size != len(symbols) * 3 or not numpy.all(numpy.isfinite(geometry)):
        raise QCSchemaError(f"{role}.geometry must contain three finite values per atom")
    geometry = geometry.reshape((len(symbols), 3))
    charge = _integral(
        molecule.get("molecular_charge", 0),
        f"{role}.molecular_charge",
    )
    multiplicity = _integral(
        molecule.get("molecular_multiplicity", 1),
        f"{role}.molecular_multiplicity",
        positive=True,
    )
    revision = hashlib.sha256(
        json.dumps(
            {
                "symbols": symbols,
                "geometry": geometry.tolist(),
                "molecular_charge": charge,
                "molecular_multiplicity": multiplicity,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return Structure(
        id=_identity(source_hash, role),
        revision=revision,
        atomic_numbers=atomic_numbers,
        coordinates=ArrayData(geometry, ("atom", "xyz"), "bohr"),
        molecular_charge=charge,
        molecular_multiplicity=multiplicity,
    )


def _array_spec(name, value, driver, atom_count):
    import numpy

    if isinstance(value, bool):
        return None
    try:
        array = numpy.asarray(value)
    except Exception:
        return None
    if array.dtype.kind not in "iuf" or not numpy.all(numpy.isfinite(array)):
        return None
    array = numpy.asarray(value, dtype=float)
    if name == "return_result":
        if driver == "energy" and array.size == 1:
            return array.reshape(()), (), "hartree", DatasetStatus.COMPLETE
        if driver == "gradient" and array.size == atom_count * 3:
            return (
                array.reshape((atom_count, 3)),
                ("atom", "xyz"),
                "hartree_per_bohr",
                DatasetStatus.COMPLETE,
            )
        if driver == "hessian" and array.size == (atom_count * 3) ** 2:
            width = atom_count * 3
            return (
                array.reshape((width, width)),
                ("coordinate", "coordinate_2"),
                "hartree_per_square_bohr",
                DatasetStatus.COMPLETE,
            )
        return array, tuple(f"axis_{index}" for index in range(array.ndim)), "unknown", DatasetStatus.AMBIGUOUS
    if name in _ENERGY_PROPERTIES or name.endswith("_energy"):
        unit = "hartree"
    elif name.startswith(_COUNT_PREFIXES):
        unit = "dimensionless"
    elif name.endswith("_dipole_moment") and array.size == 3:
        return array.reshape((3,)), ("xyz",), "elementary_charge_bohr", DatasetStatus.COMPLETE
    elif name == "return_gradient" and array.size == atom_count * 3:
        return array.reshape((atom_count, 3)), ("atom", "xyz"), "hartree_per_bohr", DatasetStatus.COMPLETE
    elif name == "return_hessian" and array.size == (atom_count * 3) ** 2:
        width = atom_count * 3
        return array.reshape((width, width)), ("coordinate", "coordinate_2"), "hartree_per_square_bohr", DatasetStatus.COMPLETE
    else:
        unit = "unknown"
    dims = () if array.ndim == 0 else tuple(f"axis_{index}" for index in range(array.ndim))
    return array, dims, unit, DatasetStatus.COMPLETE if unit != "unknown" else DatasetStatus.AMBIGUOUS


def _dataset(name, value, driver, atom_count, source_hash, calculation_id, provenance_id, issues):
    spec = _array_spec(name, value, driver, atom_count)
    if spec is None:
        issues.append(ParserIssue(IssueKind.UNSUPPORTED, f"properties.{name}" if name != "return_result" else name, "non-numeric value is preserved only in the raw QCSchema envelope"))
        return None
    values, dims, unit, status = spec
    if status is DatasetStatus.AMBIGUOUS:
        issues.append(ParserIssue(IssueKind.AMBIGUOUS, f"properties.{name}" if name != "return_result" else name, "numeric value has no supported QCSchema unit mapping"))
    revision = hashlib.sha256(values.tobytes() + unit.encode("ascii")).hexdigest()
    return PropertyDataset(
        id=_identity(source_hash, f"dataset:{name}"),
        revision=revision,
        semantic_role=name if _TOKEN.fullmatch(name) else "qcschema_property",
        domain="global",
        data=ArrayData(values, dims, unit),
        status=status,
        source_calculation=calculation_id,
        provenance_ids=(provenance_id,),
    )


def parse_qcschema_atomic_result(source):
    source, source_bytes, document = _load_document(source)
    schema_name = document.get("schema_name")
    schema_version = document.get("schema_version")
    identity = (schema_name, schema_version)
    if identity not in _SUPPORTED_RESULTS:
        raise QCSchemaCompatibilityError(f"unsupported QCSchema result {schema_name}/{schema_version}")

    source_hash = hashlib.sha256(source_bytes).hexdigest()
    revision = source_hash
    provenance_id = _identity(source_hash, "provenance")
    envelope_id = _identity(source_hash, "envelope")
    calculation_id = _identity(source_hash, "calculation")
    issues = []

    if schema_version == 1:
        input_molecule = result_molecule = _require_mapping(document.get("molecule"), "molecule")
        specification = document
    else:
        input_data = _require_mapping(document.get("input_data"), "input_data")
        input_molecule = _require_mapping(input_data.get("molecule"), "input_data.molecule")
        result_molecule = _require_mapping(document.get("molecule"), "molecule")
        specification = _require_mapping(input_data.get("specification"), "input_data.specification")

    input_structure = _structure(input_molecule, source_hash, "input_molecule", provenance_id)
    result_structure = _structure(result_molecule, source_hash, "result_molecule", provenance_id)
    structures = (input_structure,)
    if result_structure.revision != input_structure.revision:
        structures += (result_structure,)
    else:
        result_structure = input_structure

    driver = _require_text(specification.get("driver"), "driver")
    model = _require_mapping(specification.get("model"), "model")
    method = _require_text(model.get("method"), "model.method")
    basis_value = model.get("basis")
    basis = basis_value if isinstance(basis_value, str) else None
    if basis_value is not None and basis is None:
        issues.append(ParserIssue(IssueKind.UNSUPPORTED, "model.basis", "structured basis is preserved only in the raw QCSchema envelope"))

    charge = _integral(input_molecule.get("molecular_charge", 0), "molecular_charge")
    multiplicity = _integral(input_molecule.get("molecular_multiplicity", 1), "molecular_multiplicity", positive=True)
    result_provenance = _require_mapping(document.get("provenance"), "provenance")
    creator = str(result_provenance.get("creator") or "unknown")
    creator_version = str(result_provenance.get("version") or "unknown")
    program = str(specification.get("program") or creator)
    error = document.get("error")
    error_type = error_message = None
    if error is not None:
        error = _require_mapping(error, "error")
        error_type = str(error.get("error_type") or "unknown")
        error_message = str(error.get("error_message") or "")
    success = document.get("success")
    if not isinstance(success, bool):
        raise QCSchemaError("success must be a boolean")
    if not success and error is None:
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "error",
                "failed QCSchema result does not include a structured error",
            )
        )

    properties = _require_mapping(document.get("properties"), "properties")
    datasets = []
    for name, value in properties.items():
        if not isinstance(name, str) or not name:
            raise QCSchemaError("properties keys must be non-empty strings")
        dataset = _dataset(name, value, driver, len(result_structure.atomic_numbers), source_hash, calculation_id, provenance_id, issues)
        if dataset is not None:
            datasets.append(dataset)
    return_dataset = _dataset("return_result", document.get("return_result"), driver, len(result_structure.atomic_numbers), source_hash, calculation_id, provenance_id, issues)
    if return_dataset is not None and all(item.semantic_role != "return_result" for item in datasets):
        datasets.append(return_dataset)

    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer=creator,
        producer_version=creator_version,
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse_qcschema",
        parameters=(("schema_name", schema_name), ("schema_version", schema_version), ("routine", result_provenance.get("routine"))),
    )
    envelope = QCSchemaEnvelope(
        id=envelope_id,
        revision=revision,
        schema_name=schema_name,
        schema_version=schema_version,
        source_bytes=json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        provenance_ids=(provenance_id,),
    )
    metadata = CalculationMetadata(
        driver=driver,
        method=method,
        basis=basis,
        molecular_charge=charge,
        molecular_multiplicity=multiplicity,
        program=program,
        program_version=creator_version,
        error_type=error_type,
        error_message=error_message,
        qcschema_envelope_id=envelope_id,
    )
    status = CalculationStatus.SUCCESS if success else CalculationStatus.FAILED
    calculation = CalculationRecord(
        id=calculation_id,
        revision=revision,
        status=status,
        input_structure_ids=(input_structure.id,),
        result_structure_ids=(result_structure.id,),
        dataset_ids=tuple(item.id for item in datasets),
        provenance_ids=(provenance_id,),
        metadata=metadata,
    )
    created_ids = tuple(item.id for item in structures) + (envelope_id, calculation_id) + tuple(item.id for item in datasets) + (provenance_id,)
    capabilities = ["structure", "calculation_record"]
    if any(item.data.unit == "hartree" for item in datasets):
        capabilities.append("energy")
    if driver == "gradient" and return_dataset is not None and return_dataset.status is DatasetStatus.COMPLETE:
        capabilities.append("gradient")
    report = ParserReport(
        reader_id=f"qcschema_atomic_result_v{schema_version}",
        reader_version=ADAPTER_VERSION,
        created_entity_ids=created_ids,
        parsed_capabilities=tuple(capabilities),
        issues=tuple(issues),
    )
    return ImportBatch(
        structures=structures,
        qcschema_envelopes=(envelope,),
        calculations=(calculation,),
        datasets=tuple(datasets),
        provenance=(provenance,),
        report=report,
    )


def export_qcschema_atomic_result(envelope):
    if not isinstance(envelope, QCSchemaEnvelope):
        raise TypeError("envelope must be a QCSchemaEnvelope")
    try:
        return json.loads(envelope.source_bytes.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise QCSchemaError("QCSchema envelope is not valid UTF-8 JSON") from error


def parse_qcschema_molecule(source):
    source, source_bytes, document = _load_document(source)
    schema_name = document.get("schema_name")
    schema_version = document.get("schema_version")
    if (schema_name, schema_version) not in _SUPPORTED_MOLECULES:
        raise QCSchemaCompatibilityError(
            f"unsupported QCSchema molecule {schema_name}/{schema_version}"
        )
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    provenance_id = _identity(source_hash, "provenance")
    envelope_id = _identity(source_hash, "envelope")
    structure = _structure(document, source_hash, "molecule", provenance_id)
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=source_hash,
        producer="ChemBlender QCSchema adapter",
        producer_version=ADAPTER_VERSION,
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse_qcschema",
        parameters=(("schema_name", schema_name), ("schema_version", schema_version)),
    )
    envelope = QCSchemaEnvelope(
        id=envelope_id,
        revision=source_hash,
        schema_name=schema_name,
        schema_version=schema_version,
        source_bytes=json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        provenance_ids=(provenance_id,),
    )
    report = ParserReport(
        reader_id=f"qcschema_molecule_v{schema_version}",
        reader_version=ADAPTER_VERSION,
        created_entity_ids=(structure.id, envelope.id, provenance.id),
        parsed_capabilities=("structure",),
        issues=(),
    )
    return ImportBatch(
        structures=(structure,),
        qcschema_envelopes=(envelope,),
        provenance=(provenance,),
        report=report,
    )


def export_qcschema(envelope):
    return export_qcschema_atomic_result(envelope)


def sniff_qcschema(source, prefix):
    try:
        text = prefix.decode("utf-8-sig")
    except UnicodeError:
        return SniffResult(SniffMatch.NONE, "prefix is not UTF-8 JSON text")
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        name_match = re.search(r'"schema_name"\s*:\s*"([a-z0-9_]+)"', text)
        version_match = re.search(r'"schema_version"\s*:\s*([0-9]+)', text)
        if name_match and version_match:
            identity = (name_match.group(1), int(version_match.group(1)))
            if identity in _SUPPORTED_RESULTS or identity in _SUPPORTED_MOLECULES:
                return SniffResult(
                    SniffMatch.PROBABLE,
                    f"prefix declares {identity[0]}/{identity[1]}",
                )
        return SniffResult(SniffMatch.NONE, "prefix is not recognizable QCSchema JSON")
    if not isinstance(document, dict):
        return SniffResult(SniffMatch.NONE, "JSON root is not an object")
    identity = (document.get("schema_name"), document.get("schema_version"))
    if identity in _SUPPORTED_RESULTS or identity in _SUPPORTED_MOLECULES:
        return SniffResult(SniffMatch.EXACT, f"recognized {identity[0]}/{identity[1]}")
    if isinstance(identity[0], str) and identity[0].startswith("qcschema_"):
        return SniffResult(SniffMatch.POSSIBLE, f"unsupported QCSchema identity {identity[0]}/{identity[1]}")
    return SniffResult(SniffMatch.NONE, "JSON does not declare a QCSchema identity")


def parse_qcschema(source):
    _, _, document = _load_document(source)
    identity = (document.get("schema_name"), document.get("schema_version"))
    if identity in _SUPPORTED_RESULTS:
        return parse_qcschema_atomic_result(source)
    if identity in _SUPPORTED_MOLECULES:
        return parse_qcschema_molecule(source)
    raise QCSchemaCompatibilityError(f"unsupported QCSchema document {identity[0]}/{identity[1]}")


QCSCHEMA_READER = ReaderDescriptor(
    reader_id="qcschema",
    reader_version=ADAPTER_VERSION,
    extensions=(".json",),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "calculation_record": CapabilitySupport.PARTIAL,
        "energy": CapabilitySupport.PARTIAL,
        "gradient": CapabilitySupport.PARTIAL,
    },
    priority=100,
    sniff=sniff_qcschema,
    parse=parse_qcschema,
)
