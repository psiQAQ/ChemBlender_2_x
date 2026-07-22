"""Optional external-record fetch boundary with deterministic offline replay."""

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path, PurePosixPath
from uuid import uuid4

from ChemBlender.core import (
    external_record_request_from_document,
    external_record_request_document,
    external_record_source_uri,
    parse_cjson,
    parse_qcschema,
)
from ChemBlender.core.external_connector import ExternalConnectorError

from .operation import OperationError, OperationOutput
from .protocol import EntityReference


def _fixture_path(root, locator):
    if not isinstance(locator, str) or not locator or "\\" in locator:
        raise OperationError("invalid_connector_request", "offline_fixture must be a relative POSIX path")
    relative = PurePosixPath(locator)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        raise OperationError("invalid_connector_request", "offline_fixture must stay inside the project")
    path = (Path(root) / Path(*relative.parts)).resolve()
    try:
        path.relative_to(Path(root).resolve())
    except ValueError as error:
        raise OperationError("invalid_connector_request", "offline_fixture escapes the project") from error
    if not path.is_file():
        raise OperationError("external_record_missing", "offline external record fixture is missing")
    return path


def _batch_references(batch):
    groups = (
        batch.structures, batch.cif_envelopes, batch.qcschema_envelopes,
        batch.cjson_envelopes, batch.symmetry_results, batch.calculations,
        batch.datasets, batch.basis_sets, batch.orbital_sets,
        batch.density_matrices, batch.provenance,
    )
    return tuple(EntityReference(item.id, item.revision) for group in groups for item in group)


def _sanitize_batch(batch, source_uri, provider):
    provenance = tuple(
        replace(
            item,
            source=source_uri,
            parameters=item.parameters + (("connector_provider", provider),),
        )
        for item in batch.provenance
    )
    return replace(batch, provenance=provenance)


def _write_artifact(project_path, request, source_bytes):
    request_bytes = json.dumps(
        external_record_request_document(request),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    key = hashlib.sha256(request_bytes + b"\0" + source_bytes).hexdigest()
    relative = PurePosixPath("cache") / "external-record" / key / "record.json"
    path = Path(project_path) / Path(*relative.parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(source_bytes)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path, relative.as_posix(), key


def external_record_operation(context, worker_request):
    parameters = worker_request.parameters
    if not isinstance(parameters, dict):
        raise OperationError("invalid_connector_request", "connector parameters must be an object")
    transport = parameters.get("transport")
    required = {"connector_request", "transport"}
    if transport == "offline_fixture":
        required.add("offline_fixture")
    if set(parameters) != required:
        raise OperationError("invalid_connector_request", "connector parameter fields do not match transport")
    try:
        request = external_record_request_from_document(parameters["connector_request"])
    except (ExternalConnectorError, KeyError, TypeError) as error:
        raise OperationError("invalid_connector_request", str(error)) from error
    if transport == "provider":
        if request.authentication_ref is not None:
            variable = request.authentication_ref.removeprefix("env:")
            if not os.environ.get(variable):
                raise OperationError("authentication_missing", "external connector authentication is unavailable")
        raise OperationError("dependency_missing", f"optional {request.provider} connector backend is not installed")
    if transport != "offline_fixture":
        raise OperationError("invalid_connector_request", "unsupported connector transport")

    fixture = _fixture_path(context.project_path, parameters["offline_fixture"])
    source_bytes = fixture.read_bytes()
    artifact, relative, key = _write_artifact(context.project_path, request, source_bytes)
    parser = {"qcschema": parse_qcschema, "cjson": parse_cjson}[request.envelope_type]
    try:
        batch = parser(artifact)
    except Exception as error:
        raise OperationError("invalid_external_record", str(error) or type(error).__name__) from error
    source_uri = external_record_source_uri(request)
    batch = _sanitize_batch(batch, source_uri, request.provider)
    return OperationOutput(
        outputs=_batch_references(batch), artifacts=(relative,), cache_key=key,
        metadata={
            "provider": request.provider,
            "connector_version": request.connector_version,
            "envelope_type": request.envelope_type,
            "transport": "offline_fixture",
            "source_uri": source_uri,
        },
        batch=batch,
    )


def register_external_record_operation(registry):
    registry.register("external_record.fetch", "1", external_record_operation)
