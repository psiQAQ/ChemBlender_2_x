import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from uuid import uuid4

from ..core.import_pipeline import ImportSource, ValidationMode
from ..core.import_pipeline.parse import stage_import_batch
from ..core.model.sources import source_parse_identity
from ..core.readers import SniffResult
from .builtin_bridge import (
    _internal_batch_from_public_unchecked,
    _validate_internal_batch_graph,
    internal_batch_from_public,
)
from .canonical_document import (
    read_public_batch_bundle,
    write_public_batch_bundle,
)
from .protocol import ParseRequest, SniffRequest
from .public_model import ArrayData, PublicImportBatch
from .registry import ReaderPluginRegistry, _BuiltinReaderPlugin
from .version import READER_API_VERSION


_SCHEMA_VERSION = "0.1"
_SNIFF_PREFIX_BYTES = 65536
_TOKEN = re.compile(r"[a-z][a-z0-9_]*", re.ASCII)
_RESERVED_IDENTITY_PARAMETERS = frozenset(
    {"source_content_state", "validation_mode"}
)
_CHECK_NAMES = (
    "manifest",
    "bounded_sniff",
    "deterministic_sniff",
    "availability",
    "parse_output",
    "source_identity",
    "entity_references",
    "required_units",
    "diagnostics",
    "canonical_round_trip",
    "cancellation",
    "exception_isolation",
)
_ENTITY_GROUPS = (
    "structures",
    "topologies",
    "molecular_records",
    "cif_envelopes",
    "qcschema_envelopes",
    "cjson_envelopes",
    "symmetry_results",
    "calculations",
    "datasets",
    "basis_sets",
    "orbital_sets",
    "density_matrices",
    "provenance",
)
_BUILTIN_PROVENANCE_PRODUCERS = {
    "cube": "ChemBlender Cube reader",
    "xyz": "ChemBlender XYZ reader",
}


@dataclass(frozen=True, slots=True)
class ReaderConformanceCase:
    name: str
    registry: ReaderPluginRegistry
    reader_id: str
    source_path: Path
    expected_capabilities: tuple[str, ...]
    validation_mode: str = "balanced"
    canonical_parameters: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self):
        if type(self.name) is not str or not self.name:
            raise TypeError("name must be a non-empty string")
        if type(self.registry) is not ReaderPluginRegistry:
            raise TypeError("registry must be a ReaderPluginRegistry")
        if type(self.reader_id) is not str or not self.reader_id:
            raise TypeError("reader_id must be a non-empty string")
        if not isinstance(self.source_path, Path):
            raise TypeError("source_path must be a Path")
        source_path = self.source_path.resolve(strict=True)
        if not source_path.is_file():
            raise ValueError("source_path must be a file")
        capabilities = tuple(sorted(set(self.expected_capabilities)))
        if any(type(item) is not str or not _TOKEN.fullmatch(item) for item in capabilities):
            raise TypeError("expected_capabilities must contain stable tokens")
        if type(self.validation_mode) is not str:
            raise TypeError("validation_mode must be a string")
        if not isinstance(self.canonical_parameters, Mapping):
            raise TypeError("canonical_parameters must be a mapping")
        parameters = dict(self.canonical_parameters)
        if any(type(key) is not str or type(value) is not str for key, value in parameters.items()):
            raise TypeError("canonical_parameters must map strings to strings")
        if _RESERVED_IDENTITY_PARAMETERS & parameters.keys():
            raise ValueError("canonical_parameters cannot replace identity parameters")
        object.__setattr__(self, "source_path", source_path)
        object.__setattr__(self, "expected_capabilities", capabilities)
        object.__setattr__(
            self,
            "canonical_parameters",
            MappingProxyType(dict(sorted(parameters.items()))),
        )


@dataclass(frozen=True, slots=True)
class ReaderConformanceCheck:
    name: str
    passed: bool
    detail: str

    def __post_init__(self):
        if type(self.name) is not str or not self.name:
            raise TypeError("name must be a non-empty string")
        if type(self.passed) is not bool or type(self.detail) is not str:
            raise TypeError("passed must be bool and detail must be str")


@dataclass(frozen=True, slots=True)
class ReaderConformanceResult:
    schema_version: str
    case_name: str
    reader_id: str
    checks: tuple[ReaderConformanceCheck, ...]

    def __post_init__(self):
        if self.schema_version != _SCHEMA_VERSION:
            raise ValueError("schema_version must be '0.1'")
        if type(self.case_name) is not str or type(self.reader_id) is not str:
            raise TypeError("case_name and reader_id must be strings")
        checks = tuple(self.checks)
        if any(type(check) is not ReaderConformanceCheck for check in checks):
            raise TypeError("checks must contain ReaderConformanceCheck values")
        if tuple(check.name for check in checks) != _CHECK_NAMES:
            raise ValueError("checks must match the ordered conformance checks")
        object.__setattr__(self, "checks", checks)

    @property
    def passed(self):
        return all(check.passed for check in self.checks)

    def as_dict(self):
        return {
            "schema_version": self.schema_version,
            "case_name": self.case_name,
            "reader_id": self.reader_id,
            "passed": self.passed,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "detail": check.detail,
                }
                for check in self.checks
            ],
        }


def _source_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _prefix(path):
    with path.open("rb") as stream:
        return stream.read(_SNIFF_PREFIX_BYTES)


def _identity_parameters(case):
    return tuple(
        sorted(
            (
                ("source_content_state", "verified"),
                ("validation_mode", case.validation_mode),
                *case.canonical_parameters.items(),
            )
        )
    )


def _identity_parameters_hash(parameters):
    return hashlib.sha256(
        json.dumps(
            parameters, allow_nan=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()


def _parse_request(case, source_hash, staging_root, is_cancelled=lambda: False):
    return ParseRequest(
        source_path=case.source_path,
        source_content_hash=source_hash,
        validation_mode=case.validation_mode,
        canonical_parameters=case.canonical_parameters,
        staging_root=staging_root,
        progress=lambda event: None,
        is_cancelled=is_cancelled,
        source_revision_id=uuid4(),
    )


def _error_detail(error, registry):
    details = [type(error).__name__]
    details.extend(issue.message for issue in registry.last_sniff_diagnostics)
    return "; ".join(details)


def _select(case):
    return case.registry.select(
        SniffRequest(case.source_path, _prefix(case.source_path))
    )


def _entity_ids(batch):
    return tuple(
        entity.id
        for name in _ENTITY_GROUPS
        for entity in getattr(batch, name)
    )


def _walk(value, seen=None):
    seen = set() if seen is None else seen
    if id(value) in seen:
        return
    if isinstance(value, (str, bytes, int, float, bool, type(None))):
        return
    seen.add(id(value))
    yield value
    if is_dataclass(value):
        for field in fields(value):
            yield from _walk(getattr(value, field.name), seen)
    elif isinstance(value, Mapping):
        for key in sorted(value):
            yield from _walk(key, seen)
            yield from _walk(value[key], seen)
    elif isinstance(value, (tuple, list, frozenset)):
        for item in value:
            yield from _walk(item, seen)


def _artifact_hashes(root):
    return tuple(
        (path.relative_to(root).as_posix(), _source_hash(path))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def _run_check(name, action, registry, state):
    try:
        passed, detail = action()
    except Exception as error:
        state["isolated_exception_types"].append(type(error).__name__)
        return ReaderConformanceCheck(name, False, _error_detail(error, registry))
    return ReaderConformanceCheck(name, passed, detail)


def run_reader_conformance(case):
    if type(case) is not ReaderConformanceCase:
        raise TypeError("case must be a ReaderConformanceCase")

    state = {
        "descriptor": None,
        "batch": None,
        "parse_request": None,
        "source_hash": _source_hash(case.source_path),
        "isolated_exception_types": [],
    }

    def manifest():
        descriptor = case.registry.select(
            SniffRequest(case.source_path, b""), case.reader_id
        )
        state["descriptor"] = descriptor
        return (
            descriptor.reader_id == case.reader_id,
            "registered manifest and descriptor are valid",
        )

    def bounded_sniff():
        prefix = _prefix(case.source_path)
        descriptor = _select(case)
        state["descriptor"] = descriptor
        return (
            len(prefix) <= _SNIFF_PREFIX_BYTES and descriptor.reader_id == case.reader_id,
            f"{len(prefix)} byte prefix selected {descriptor.reader_id}",
        )

    def deterministic_sniff():
        request = SniffRequest(case.source_path, _prefix(case.source_path))
        plugin = case.registry._plugin(case.reader_id)
        first = plugin.sniff(request)
        second = plugin.sniff(request)
        first_selected = case.registry.select(request)
        second_selected = case.registry.select(request)
        return (
            type(first) is SniffResult
            and type(second) is SniffResult
            and first == second
            and first_selected.reader_id == case.reader_id
            and second_selected.reader_id == case.reader_id,
            "exact SniffResult values and registry selections are stable",
        )

    def availability():
        descriptor = state["descriptor"]
        if descriptor is None:
            descriptor = case.registry.select(
                SniffRequest(case.source_path, b""), case.reader_id
            )
        value = descriptor.availability
        return (
            value.available,
            f"{value.reason_code}: {value.detail}".rstrip(": "),
        )

    def parse_output():
        with TemporaryDirectory() as temporary:
            request = _parse_request(
                case,
                state["source_hash"],
                Path(temporary),
            )
            state["parse_request"] = request
            batch = case.registry.parse(
                case.reader_id,
                request,
            )
        exception_type = case.registry._last_parse_exception_type
        if exception_type is not None:
            state["isolated_exception_types"].append(exception_type)
        if type(batch) is not PublicImportBatch:
            return False, f"expected PublicImportBatch, got {type(batch).__name__}"
        errors = () if batch.report is None else tuple(
            issue for issue in batch.report.issues
            if issue.path in {"reader.parse", "reader.source", "reader.availability"}
        )
        if errors:
            return False, "; ".join(issue.message for issue in errors)
        state["batch"] = batch
        return True, "exact PublicImportBatch"

    def source_identity():
        batch = state["batch"]
        if type(batch) is not PublicImportBatch:
            return False, "parse output unavailable"
        descriptor = state["descriptor"]
        revisions = tuple(batch.source_revisions)
        if revisions:
            source_ids = {value.id for value in batch.sources}
            entity_ids = set(_entity_ids(batch))
            diagnostic_ids = {value.id for value in batch.diagnostics}
            parameters = _identity_parameters(case)
            expected_identity = source_parse_identity(
                state["source_hash"],
                descriptor.plugin_id,
                descriptor.reader_id,
                descriptor.reader_version,
                parameters,
            )
            expected_parameters_hash = _identity_parameters_hash(parameters)
            valid = all(
                value.id == state["parse_request"].source_revision_id
                and value.content_hash == state["source_hash"]
                and value.source_id in source_ids
                and value.byte_size == case.source_path.stat().st_size
                and value.original_filename == case.source_path.name
                and value.reader_plugin_id == descriptor.plugin_id
                and value.reader_id == descriptor.reader_id
                and value.reader_version == descriptor.reader_version
                and value.reader_api_version == READER_API_VERSION
                and value.import_parameters_hash == expected_parameters_hash
                and value.parse_identity == expected_identity
                and len(value.created_entity_ids)
                == len(set(value.created_entity_ids))
                and set(value.created_entity_ids) == entity_ids
                and len(value.diagnostic_ids) == len(set(value.diagnostic_ids))
                and set(value.diagnostic_ids) == diagnostic_ids
                for value in revisions
            )
            return valid, "all SourceRevisions bind this case completely"
        entity_ids = _entity_ids(batch)
        provenance = tuple(batch.provenance)
        report = batch.report
        expected_producer = _BUILTIN_PROVENANCE_PRODUCERS.get(
            descriptor.reader_id
        )
        revisions_match = all(
            getattr(value, "revision", state["source_hash"]) == state["source_hash"]
            for name in _ENTITY_GROUPS
            for value in getattr(batch, name)
        )
        provenance_matches = len(provenance) == 1 and all(
            value.revision == state["source_hash"]
            and value.producer == expected_producer
            and value.producer_version == descriptor.reader_version
            and value.source == str(case.source_path)
            and value.source_hash == state["source_hash"]
            and value.operation == "parse"
            and tuple(
                item for item in value.parameters if item[0] == "format"
            ) == (("format", descriptor.reader_id),)
            for value in provenance
        )
        return (
            descriptor.plugin_id == "chemblender.builtin"
            and expected_producer is not None
            and case.validation_mode == "balanced"
            and not case.canonical_parameters
            and report is not None
            and report.reader_id == descriptor.reader_id
            and report.reader_version == descriptor.reader_version
            and bool(entity_ids)
            and revisions_match
            and provenance_matches,
            "strict built-in provenance fallback binds source identity",
        )

    def entity_references():
        batch = state["batch"]
        if type(batch) is not PublicImportBatch:
            return False, "parse output unavailable"
        plugin = case.registry._plugin(case.reader_id)
        if type(plugin) is _BuiltinReaderPlugin:
            request = state["parse_request"]
            descriptor = plugin.descriptor
            internal = _internal_batch_from_public_unchecked(batch)
            internal = stage_import_batch(
                source=ImportSource(case.source_path),
                validation_mode=ValidationMode(request.validation_mode),
                content_hash=request.source_content_hash,
                byte_size=case.source_path.stat().st_size,
                plugin_id=descriptor.plugin_id,
                reader_id=descriptor.reader_id,
                reader_version=descriptor.reader_version,
                api_version=READER_API_VERSION,
                canonical_parameters=tuple(
                    sorted(request.canonical_parameters.items())
                ),
                parsed_batch=internal,
                revision_id=request.source_revision_id,
            )
            _validate_internal_batch_graph(internal)
        else:
            internal = internal_batch_from_public(batch)
        report = internal.report
        expected = _entity_ids(batch)
        actual = () if report is None else report.created_entity_ids
        return (
            actual == expected,
            "public graph and report created entity IDs are exact",
        )

    def required_units():
        batch = state["batch"]
        if type(batch) is not PublicImportBatch:
            return False, "parse output unavailable"
        arrays = [value for value in _walk(batch) if isinstance(value, ArrayData)]
        coordinate_units = [
            getattr(value, "coordinate_unit")
            for value in _walk(batch)
            if is_dataclass(value) and hasattr(value, "coordinate_unit")
        ]
        valid = all(_TOKEN.fullmatch(value.unit) for value in arrays)
        valid = valid and all(
            type(value) is str and _TOKEN.fullmatch(value)
            for value in coordinate_units
        )
        return valid, "all reachable array and coordinate units are canonical"

    def diagnostics():
        batch = state["batch"]
        descriptor = state["descriptor"]
        if type(batch) is not PublicImportBatch or batch.report is None:
            return False, "parser report unavailable"
        report = batch.report
        diagnostic_ids = {value.id for value in batch.diagnostics}
        source_revisions = {value.id: value for value in batch.source_revisions}
        references_complete = all(
            value.source_revision_id in source_revisions
            and value.id in source_revisions[value.source_revision_id].diagnostic_ids
            for value in batch.diagnostics
        )
        return (
            report.reader_id == descriptor.reader_id
            and report.reader_version == descriptor.reader_version
            and tuple(sorted(report.parsed_capabilities)) == case.expected_capabilities
            and references_complete
            and all(value in diagnostic_ids for revision in source_revisions.values() for value in revision.diagnostic_ids),
            "reader metadata, capabilities, and diagnostic references are complete",
        )

    def canonical_round_trip():
        batch = state["batch"]
        if type(batch) is not PublicImportBatch:
            return False, "parse output unavailable"
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            write_public_batch_bundle(first, batch)
            restored = read_public_batch_bundle(first)
            write_public_batch_bundle(second, restored)
            same_document = (first / "import-batch.json").read_bytes() == (second / "import-batch.json").read_bytes()
            same_artifacts = _artifact_hashes(first) == _artifact_hashes(second)
        return same_document and same_artifacts, "canonical document bytes and artifact hashes match"

    def cancellation():
        with TemporaryDirectory() as temporary:
            request = _parse_request(
                case,
                state["source_hash"],
                Path(temporary),
                is_cancelled=lambda: True,
            )
            first = case.registry.parse(case.reader_id, request)
            second = case.registry.parse(case.reader_id, request)
        reports = (getattr(first, "report", None), getattr(second, "report", None))
        valid = all(
            report is not None
            and report.issues
            and report.issues[0].path == "reader.parse"
            and "cancel" in report.issues[0].message
            for report in reports
        )
        stable = valid and reports[0] == reports[1]
        return stable, "pre-cancelled parse returns stable cancellation evidence"

    def exception_isolation():
        types = tuple(dict.fromkeys(state["isolated_exception_types"]))
        if types:
            return True, f"isolated exceptions: {', '.join(types)}"
        return True, "no exception observed"

    actions = (
        manifest,
        bounded_sniff,
        deterministic_sniff,
        availability,
        parse_output,
        source_identity,
        entity_references,
        required_units,
        diagnostics,
        canonical_round_trip,
        cancellation,
        exception_isolation,
    )
    checks = []
    for name, action in zip(_CHECK_NAMES, actions, strict=True):
        checks.append(_run_check(name, action, case.registry, state))
    return ReaderConformanceResult(
        _SCHEMA_VERSION,
        case.name,
        case.reader_id,
        tuple(checks),
    )
