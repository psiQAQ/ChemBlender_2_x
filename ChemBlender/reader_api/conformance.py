import hashlib
import json
import platform
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from uuid import uuid4

from ..core.import_pipeline import ImportSource, ValidationMode
from ..core.import_pipeline.parse import stage_import_batch
from ..core.import_pipeline.staging import _close_memmaps
from ..core.model.sources import source_parse_identity
from ..core.model import QualityStatus
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
from .protocol import ParseRequest, ProgressEvent, SniffRequest
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
_V1_CHECK_NAMES = (
    *_CHECK_NAMES,
    "quality_diagnostics",
    "progress_monotonicity",
    "artifact_security",
    "declared_capabilities",
)
_ENTITY_GROUPS = (
    "structures",
    "topologies",
    "molecular_records",
    "biological_hierarchies",
    "annotations",
    "external_references",
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
        "identity_batch": None,
        "parse_temporary": None,
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
        temporary = TemporaryDirectory()
        state["parse_temporary"] = temporary
        request = _parse_request(
            case,
            state["source_hash"],
            Path(temporary.name),
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
        identity_batch = batch
        plugin = case.registry._plugin(case.reader_id)
        if not batch.source_revisions and type(plugin) is _BuiltinReaderPlugin:
            request = state["parse_request"]
            identity_batch = stage_import_batch(
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
                parsed_batch=_internal_batch_from_public_unchecked(batch),
                revision_id=request.source_revision_id,
            )
        state["identity_batch"] = identity_batch
        revisions = tuple(identity_batch.source_revisions)
        if revisions:
            source_ids = {value.id for value in identity_batch.sources}
            entity_ids = set(_entity_ids(identity_batch))
            diagnostic_ids = {value.id for value in identity_batch.diagnostics}
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
        identity_batch = state["identity_batch"] or batch
        diagnostic_ids = {value.id for value in identity_batch.diagnostics}
        source_revisions = {
            value.id: value for value in identity_batch.source_revisions
        }
        references_complete = all(
            value.source_revision_id in source_revisions
            and value.id in source_revisions[value.source_revision_id].diagnostic_ids
            for value in identity_batch.diagnostics
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
        temporary = TemporaryDirectory()
        results = []
        try:
            root = Path(temporary.name)
            residues = []
            for name in ("first", "second"):
                staging_root = root / name
                staging_root.mkdir()
                request = _parse_request(
                    case,
                    state["source_hash"],
                    staging_root,
                    is_cancelled=lambda: True,
                )
                results.append(case.registry.parse(case.reader_id, request))
                residues.extend(
                    path.relative_to(root).as_posix()
                    for path in sorted(staging_root.rglob("*"))
                )
            first, second = results
            reports = (
                getattr(first, "report", None),
                getattr(second, "report", None),
            )
            valid = all(
                report is not None
                and report.issues
                and report.issues[0].path == "reader.parse"
                and "cancel" in report.issues[0].message
                for report in reports
            )
            stable = valid and reports[0] == reports[1] and not residues
            detail = "pre-cancelled parse returns stable cancellation evidence"
            if residues:
                detail = (
                    "cancelled parse left staging residue: "
                    + ", ".join(residues)
                )
            return stable, detail
        finally:
            for batch in results:
                if type(batch) is PublicImportBatch:
                    _close_memmaps(batch, set())
            temporary.cleanup()

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
    try:
        for name, action in zip(_CHECK_NAMES, actions, strict=True):
            checks.append(_run_check(name, action, case.registry, state))
    finally:
        if type(state["batch"]) is PublicImportBatch:
            _close_memmaps(state["batch"], set())
        if state["parse_temporary"] is not None:
            state["parse_temporary"].cleanup()
    return ReaderConformanceResult(
        _SCHEMA_VERSION,
        case.name,
        case.reader_id,
        tuple(checks),
    )


def _progress_is_monotonic(events):
    previous = {}
    for event in events:
        if type(event) is not ProgressEvent:
            return False
        prior = previous.get(event.stage)
        if prior is not None and (
            event.total != prior.total or event.completed < prior.completed
        ):
            return False
        previous[event.stage] = event
    return bool(events)


def _artifact_inventory_is_safe(root):
    root = root.resolve()
    for path in root.rglob("*"):
        if path.is_symlink():
            return False
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            return False
        if path.is_file() and path.parent.name == "artifacts":
            if (
                path.suffix != ".npy"
                or re.fullmatch(r"[0-9a-f]{64}", path.stem) is None
            ):
                return False
    return True


def _v1_checks(case, legacy):
    staging = TemporaryDirectory()
    state = {"batch": None}
    try:
        return _v1_checks_in_staging(
            case,
            legacy,
            Path(staging.name),
            state,
        )
    finally:
        if type(state["batch"]) is PublicImportBatch:
            _close_memmaps(state["batch"], set())
        staging.cleanup()


def _v1_checks_in_staging(case, legacy, staging_root, state):
    descriptor = case.registry.select(
        SniffRequest(case.source_path, b""),
        case.reader_id,
    )
    events = []
    batch = None
    parse_error = None
    try:
        batch = case.registry.parse(
            case.reader_id,
            ParseRequest(
                source_path=case.source_path,
                source_content_hash=_source_hash(case.source_path),
                validation_mode=case.validation_mode,
                canonical_parameters=case.canonical_parameters,
                staging_root=staging_root,
                progress=events.append,
                is_cancelled=lambda: False,
                source_revision_id=uuid4(),
            ),
        )
        state["batch"] = batch
    except Exception as error:
        parse_error = type(error).__name__

    quality_values = (
        ()
        if type(batch) is not PublicImportBatch
        else tuple(
            value.quality_status
            for value in _walk(batch)
            if is_dataclass(value) and hasattr(value, "quality_status")
        )
    )
    quality_ok = (
        type(batch) is PublicImportBatch
        and batch.report is not None
        and all(isinstance(value, QualityStatus) for value in quality_values)
    )
    progress_ok = parse_error is None and _progress_is_monotonic(events)

    artifact_ok = False
    if type(batch) is PublicImportBatch:
        try:
            with TemporaryDirectory() as temporary:
                root = Path(temporary) / "bundle"
                write_public_batch_bundle(root, batch)
                read_public_batch_bundle(root)
                artifact_ok = _artifact_inventory_is_safe(root)
        except Exception:
            artifact_ok = False

    declared_ok = set(case.expected_capabilities) <= set(
        descriptor.capabilities
    )

    extra = (
        ReaderConformanceCheck(
            "quality_diagnostics",
            quality_ok,
            (
                "quality values and parser diagnostics are canonical"
                if quality_ok
                else "quality or parser diagnostics are invalid"
            ),
        ),
        ReaderConformanceCheck(
            "progress_monotonicity",
            progress_ok,
            (
                "progress is bounded and monotonic per stage"
                if progress_ok
                else f"progress is not monotonic ({parse_error or 'event regression'})"
            ),
        ),
        ReaderConformanceCheck(
            "artifact_security",
            artifact_ok,
            (
                "canonical artifacts are content-addressed and path-safe"
                if artifact_ok
                else "canonical artifact inventory is unsafe or invalid"
            ),
        ),
        ReaderConformanceCheck(
            "declared_capabilities",
            declared_ok,
            (
                "parsed capabilities are declared by the reader"
                if declared_ok
                else "parsed capabilities are not declared by the reader"
            ),
        ),
    )
    diagnostics = (
        []
        if type(batch) is not PublicImportBatch or batch.report is None
        else [
            {
                "kind": issue.kind.value,
                "message": issue.message,
                "path": issue.path,
            }
            for issue in batch.report.issues
        ]
    )
    return (*legacy.checks, *extra), diagnostics


def _environment(process_isolation):
    return {
        "implementation": platform.python_implementation(),
        "machine": platform.machine(),
        "platform": platform.system(),
        "process_isolation": process_isolation,
        "python": platform.python_version(),
    }


def run_reader_conformance_v1(
    cases,
    *,
    optional_skip_reasons=None,
    process_isolation="in_process",
):
    """Return the v1 machine-readable suite document without changing the 0.1 API."""
    cases = tuple(cases)
    if not cases or any(type(case) is not ReaderConformanceCase for case in cases):
        raise TypeError("cases must contain ReaderConformanceCase values")
    if len({case.name for case in cases}) != len(cases):
        raise ValueError("case names must be unique")
    if process_isolation not in {"in_process", "subprocess"}:
        raise ValueError("process_isolation must be in_process or subprocess")
    reasons = {} if optional_skip_reasons is None else dict(optional_skip_reasons)
    if set(reasons) - {case.name for case in cases}:
        raise ValueError("optional skip case is not present")
    if any(type(reason) is not str or not reason.strip() for reason in reasons.values()):
        raise ValueError("optional skip reason must be a non-empty string")

    descriptors = tuple(
        case.registry.select(
            SniffRequest(case.source_path, b""),
            case.reader_id,
        )
        for case in cases
    )
    plugin_identity = {
        (descriptor.plugin_id, descriptor.plugin_version)
        for descriptor in descriptors
    }
    if len(plugin_identity) != 1:
        raise ValueError("all cases must belong to one plugin")
    plugin_id, plugin_version = plugin_identity.pop()

    results = []
    for case, descriptor in zip(cases, descriptors, strict=True):
        fixture = {
            "path": case.source_path.name,
            "sha256": _source_hash(case.source_path),
        }
        if case.name in reasons:
            results.append(
                {
                    "case_id": case.name,
                    "checks": [],
                    "diagnostics": [],
                    "duration_seconds": 0.0,
                    "fixture": fixture,
                    "reader": {
                        "id": descriptor.reader_id,
                        "version": descriptor.reader_version,
                    },
                    "required": False,
                    "skip_reason": reasons[case.name],
                    "status": "skip",
                }
            )
            continue

        started = time.perf_counter()
        legacy = run_reader_conformance(case)
        checks, diagnostics = _v1_checks(case, legacy)
        if tuple(check.name for check in checks) != _V1_CHECK_NAMES:
            raise RuntimeError("v1 checks are not in canonical order")
        duration = round(time.perf_counter() - started, 6)
        status = "pass" if all(check.passed for check in checks) else "fail"
        diagnostics.extend(
            {
                "kind": "conformance_failure",
                "message": check.detail,
                "path": f"checks.{check.name}",
            }
            for check in checks
            if not check.passed
        )
        results.append(
            {
                "case_id": case.name,
                "checks": [
                    {
                        "detail": check.detail,
                        "id": check.name,
                        "status": "pass" if check.passed else "fail",
                    }
                    for check in checks
                ],
                "diagnostics": sorted(
                    diagnostics,
                    key=lambda value: (
                        value["path"],
                        value["kind"],
                        value["message"],
                    ),
                ),
                "duration_seconds": duration,
                "fixture": fixture,
                "reader": {
                    "id": descriptor.reader_id,
                    "version": descriptor.reader_version,
                },
                "required": True,
                "skip_reason": None,
                "status": status,
            }
        )

    summary = {
        status: sum(result["status"] == status for result in results)
        for status in ("fail", "pass", "skip")
    }
    return {
        "cases": results,
        "environment": _environment(process_isolation),
        "passed": summary["fail"] == 0,
        "plugin": {"id": plugin_id, "version": plugin_version},
        "reader_api_version": READER_API_VERSION,
        "schema_version": "1",
        "summary": summary,
    }
