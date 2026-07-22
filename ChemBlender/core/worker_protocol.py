"""Versioned JSON contract shared by the Blender client and external worker."""

import json
import math
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4


PROTOCOL_VERSION = "1"
WORKER_VERSION = "0.1.0"
_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ProtocolError(ValueError):
    pass


class WorkerStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


def _require_text(value, name):
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"{name} must be a non-empty string")


def _json_value(value, path="parameters"):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProtocolError(f"{path} must not contain NaN or Infinity")
        return value
    if isinstance(value, list):
        return [_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ProtocolError(f"{path} keys must be strings")
        return {key: _json_value(value[key], f"{path}.{key}") for key in sorted(value)}
    raise ProtocolError(f"{path} contains unsupported {type(value).__name__}")


def _artifact_path(value):
    _require_text(value, "artifact")
    path = PurePosixPath(value)
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or "\\" in value
    ):
        raise ProtocolError("artifact paths must stay inside the sidecar")
    return value


@dataclass(frozen=True, slots=True)
class EntityReference:
    entity_id: UUID
    revision: str

    def __post_init__(self):
        if not isinstance(self.entity_id, UUID):
            raise ProtocolError("entity_id must be a UUID")
        _require_text(self.revision, "revision")


@dataclass(frozen=True, slots=True)
class WorkerRequest:
    request_id: UUID
    project_locator: str
    project_id: UUID
    project_schema_version: str
    operation_id: str
    operation_version: str
    inputs: tuple[EntityReference, ...]
    parameters: dict
    protocol_version: str = PROTOCOL_VERSION

    def __post_init__(self):
        if self.protocol_version != PROTOCOL_VERSION:
            raise ProtocolError("unsupported worker protocol version")
        if not isinstance(self.request_id, UUID) or not isinstance(self.project_id, UUID):
            raise ProtocolError("request_id and project_id must be UUIDs")
        for value, name in (
            (self.project_locator, "project_locator"),
            (self.project_schema_version, "project_schema_version"),
            (self.operation_version, "operation_version"),
        ):
            _require_text(value, name)
        if not isinstance(self.operation_id, str) or not _TOKEN.fullmatch(self.operation_id):
            raise ProtocolError("operation_id must be a lower token")
        inputs = tuple(self.inputs)
        if any(not isinstance(item, EntityReference) for item in inputs):
            raise ProtocolError("inputs must contain EntityReference values")
        identities = {item.entity_id for item in inputs}
        if len(identities) != len(inputs):
            raise ProtocolError("inputs must not contain duplicate identities")
        if not isinstance(self.parameters, dict):
            raise ProtocolError("parameters must be a JSON object")
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(self, "parameters", _json_value(self.parameters))


@dataclass(frozen=True, slots=True)
class WorkerError:
    code: str
    message: str

    def __post_init__(self):
        if not isinstance(self.code, str) or not _TOKEN.fullmatch(self.code):
            raise ProtocolError("error code must be a lower token")
        _require_text(self.message, "error message")


@dataclass(frozen=True, slots=True)
class WorkerResult:
    request_id: UUID
    status: WorkerStatus
    outputs: tuple[EntityReference, ...] = ()
    artifacts: tuple[str, ...] = ()
    cache_key: str | None = None
    metadata: dict | None = None
    error: WorkerError | None = None
    protocol_version: str = PROTOCOL_VERSION
    worker_version: str = WORKER_VERSION

    def __post_init__(self):
        if self.protocol_version != PROTOCOL_VERSION:
            raise ProtocolError("unsupported worker protocol version")
        if not isinstance(self.request_id, UUID):
            raise ProtocolError("request_id must be a UUID")
        if not isinstance(self.status, WorkerStatus):
            raise ProtocolError("status must be WorkerStatus")
        _require_text(self.worker_version, "worker_version")
        outputs = tuple(self.outputs)
        artifacts = tuple(_artifact_path(value) for value in self.artifacts)
        if any(not isinstance(item, EntityReference) for item in outputs):
            raise ProtocolError("outputs must contain EntityReference values")
        if len({item.entity_id for item in outputs}) != len(outputs):
            raise ProtocolError("outputs must not contain duplicate entity IDs")
        if self.cache_key is not None and (
            not isinstance(self.cache_key, str) or not _SHA256.fullmatch(self.cache_key)
        ):
            raise ProtocolError("cache_key must be SHA-256 hex")
        metadata = {} if self.metadata is None else self.metadata
        if not isinstance(metadata, dict):
            raise ProtocolError("metadata must be a JSON object")
        metadata = _json_value(metadata, "metadata")
        if self.status is WorkerStatus.SUCCESS:
            if self.error is not None:
                raise ProtocolError("success result must not contain an error")
        elif not isinstance(self.error, WorkerError):
            raise ProtocolError("non-success result requires a WorkerError")
        if self.status is not WorkerStatus.SUCCESS and (
            outputs or artifacts or self.cache_key is not None
        ):
            raise ProtocolError("non-success result must not publish outputs")
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "metadata", metadata)


def _reference_document(reference):
    return {"entity_id": str(reference.entity_id), "revision": reference.revision}


def _reference_from_document(document):
    if not isinstance(document, dict) or set(document) != {"entity_id", "revision"}:
        raise ProtocolError("invalid entity reference")
    try:
        return EntityReference(UUID(document["entity_id"]), document["revision"])
    except (TypeError, ValueError) as error:
        if isinstance(error, ProtocolError):
            raise
        raise ProtocolError("invalid entity reference") from error


def request_document(request):
    if not isinstance(request, WorkerRequest):
        raise TypeError("request must be a WorkerRequest")
    return {
        "protocol_version": request.protocol_version,
        "request_id": str(request.request_id),
        "project_locator": request.project_locator,
        "project_id": str(request.project_id),
        "project_schema_version": request.project_schema_version,
        "operation_id": request.operation_id,
        "operation_version": request.operation_version,
        "inputs": [_reference_document(item) for item in request.inputs],
        "parameters": request.parameters,
    }


def result_document(result):
    if not isinstance(result, WorkerResult):
        raise TypeError("result must be a WorkerResult")
    return {
        "protocol_version": result.protocol_version,
        "worker_version": result.worker_version,
        "request_id": str(result.request_id),
        "status": result.status.value,
        "outputs": [_reference_document(item) for item in result.outputs],
        "artifacts": list(result.artifacts),
        "cache_key": result.cache_key,
        "metadata": result.metadata,
        "error": None
        if result.error is None
        else {"code": result.error.code, "message": result.error.message},
    }


def _atomic_document(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_request(path, request):
    _atomic_document(path, request_document(request))


def write_result(path, result):
    _atomic_document(path, result_document(result))


def _read_document(path):
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=_raise_constant,
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise ProtocolError(f"cannot read protocol document: {Path(path).name}") from error


def _raise_constant(value):
    raise ValueError(f"non-finite JSON value: {value}")


def read_request(path):
    document = _read_document(path)
    fields = {
        "protocol_version",
        "request_id",
        "project_locator",
        "project_id",
        "project_schema_version",
        "operation_id",
        "operation_version",
        "inputs",
        "parameters",
    }
    if not isinstance(document, dict) or set(document) != fields:
        raise ProtocolError("invalid worker request fields")
    try:
        return WorkerRequest(
            protocol_version=document["protocol_version"],
            request_id=UUID(document["request_id"]),
            project_locator=document["project_locator"],
            project_id=UUID(document["project_id"]),
            project_schema_version=document["project_schema_version"],
            operation_id=document["operation_id"],
            operation_version=document["operation_version"],
            inputs=tuple(_reference_from_document(item) for item in document["inputs"]),
            parameters=document["parameters"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ProtocolError):
            raise
        raise ProtocolError("invalid worker request") from error


def read_result(path):
    document = _read_document(path)
    fields = {
        "protocol_version",
        "worker_version",
        "request_id",
        "status",
        "outputs",
        "artifacts",
        "cache_key",
        "metadata",
        "error",
    }
    if not isinstance(document, dict) or set(document) != fields:
        raise ProtocolError("invalid worker result fields")
    try:
        error = document["error"]
        if error is not None:
            if not isinstance(error, dict) or set(error) != {"code", "message"}:
                raise ProtocolError("invalid worker error")
            error = WorkerError(error["code"], error["message"])
        return WorkerResult(
            protocol_version=document["protocol_version"],
            worker_version=document["worker_version"],
            request_id=UUID(document["request_id"]),
            status=WorkerStatus(document["status"]),
            outputs=tuple(_reference_from_document(item) for item in document["outputs"]),
            artifacts=tuple(document["artifacts"]),
            cache_key=document["cache_key"],
            metadata=document["metadata"],
            error=error,
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ProtocolError):
            raise
        raise ProtocolError("invalid worker result") from error
