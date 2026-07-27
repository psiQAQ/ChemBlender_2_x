import hashlib
import os
import re
import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath

from ..core.worker_protocol import (
    WORKER_VERSION,
    WorkerRequest,
    WorkerResult,
    WorkerStatus,
)
from .builtin_bridge import PublicBatchError, internal_batch_from_public
from .canonical_document import CanonicalDocumentError, read_public_batch_bundle


__all__ = (
    "WorkerReaderError",
    "WorkerReaderExecutionError",
    "WorkerReaderIntegrityError",
    "parse_with_worker",
)

_OPERATION_ID = "reader.parse"
_OPERATION_VERSION = "0.1"
_OPERATION = f"{_OPERATION_ID}@{_OPERATION_VERSION}"
_SCHEMA_VERSION = "0.1"
_BUNDLE_PATH = "reader-bundle"
_DOCUMENT_PATH = f"{_BUNDLE_PATH}/import-batch.json"
_PARAMETER_FIELDS = frozenset(
    {
        "reader_id",
        "source_artifact",
        "source_sha256",
        "validation_mode",
        "canonical_parameters",
    }
)
_METADATA_FIELDS = frozenset(
    {
        "operation",
        "schema_version",
        "document_path",
        "document_sha256",
        "artifact_sha256",
    }
)
_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_ARTIFACT = re.compile(
    r"reader-bundle/artifacts/[0-9a-f]{64}\.npy",
    re.ASCII,
)
_VALIDATION_MODES = frozenset({"strict", "balanced", "maximum"})


class WorkerReaderError(Exception):
    pass


class WorkerReaderExecutionError(WorkerReaderError):
    pass


class WorkerReaderIntegrityError(WorkerReaderError):
    pass


class _WorkerReaderCancelled(Exception):
    pass


def _link_like(path):
    return path.is_symlink() or (
        hasattr(path, "is_junction") and path.is_junction()
    )


def _task_file(root, relative):
    if type(relative) is not str or not relative or "\\" in relative:
        raise WorkerReaderIntegrityError(
            "artifact path must be a safe relative POSIX path"
        )
    pure = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    parts = relative.split("/")
    if (
        pure.is_absolute()
        or windows.drive
        or Path(relative).is_absolute()
        or any(
            part in {"", ".", ".."}
            or ":" in part
            or part.endswith((".", " "))
            for part in parts
        )
    ):
        raise WorkerReaderIntegrityError(
            "artifact path must be a safe relative POSIX path"
        )
    try:
        root = Path(root)
        if _link_like(root):
            raise WorkerReaderIntegrityError("task directory must not be a link")
        resolved_root = root.resolve(strict=True)
        if not resolved_root.is_dir():
            raise WorkerReaderIntegrityError("task directory must be a directory")
        candidate = root
        for part in pure.parts:
            candidate /= part
            if _link_like(candidate):
                raise WorkerReaderIntegrityError("artifact path must not use links")
        candidate = candidate.resolve(strict=True)
        candidate.relative_to(resolved_root)
    except WorkerReaderIntegrityError:
        raise
    except (OSError, ValueError) as error:
        raise WorkerReaderIntegrityError(
            "artifact must exist inside the task directory"
        ) from error
    if not candidate.is_file():
        raise WorkerReaderIntegrityError("artifact must be a regular file")
    return candidate


def _bundle_inventory(root, artifact_paths):
    try:
        root = Path(root)
        if _link_like(root):
            raise WorkerReaderIntegrityError("task directory must not be a link")
        resolved_root = root.resolve(strict=True)
        bundle = resolved_root / _BUNDLE_PATH
        if _link_like(bundle) or not bundle.is_dir():
            raise WorkerReaderIntegrityError(
                "reader bundle must be a regular directory"
            )
        files = set()
        directories = {_BUNDLE_PATH}

        def walk(directory):
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if entry.is_symlink() or _link_like(path):
                        raise WorkerReaderIntegrityError(
                            "reader bundle must not contain links"
                        )
                    relative = path.relative_to(resolved_root).as_posix()
                    if entry.is_dir(follow_symlinks=False):
                        directories.add(relative)
                        walk(path)
                    elif entry.is_file(follow_symlinks=False):
                        files.add(relative)
                    else:
                        raise WorkerReaderIntegrityError(
                            "reader bundle contains an unsupported entry"
                        )

        walk(bundle)
    except WorkerReaderIntegrityError:
        raise
    except (OSError, ValueError) as error:
        raise WorkerReaderIntegrityError(
            "cannot inspect reader bundle"
        ) from error
    expected_files = {_DOCUMENT_PATH, *artifact_paths}
    expected_directories = {
        _BUNDLE_PATH,
        f"{_BUNDLE_PATH}/artifacts",
    }
    if files != expected_files or directories != expected_directories:
        raise WorkerReaderIntegrityError("worker bundle inventory mismatch")


def _remove_verified_bundle(root):
    try:
        root = Path(root).resolve(strict=True)
        bundle = root / _BUNDLE_PATH
        if _link_like(bundle) or not bundle.is_dir():
            raise WorkerReaderIntegrityError(
                "invalid worker reader bundle is unsafe"
            )
        shutil.rmtree(bundle)
    except WorkerReaderIntegrityError:
        raise
    except OSError as error:
        raise WorkerReaderIntegrityError(
            "cannot remove invalid worker reader bundle"
        ) from error


def _file_sha256(path, is_cancelled=None):
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            while True:
                if is_cancelled is not None and is_cancelled():
                    raise _WorkerReaderCancelled
                chunk = stream.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as error:
        raise WorkerReaderIntegrityError("cannot hash worker artifact") from error
    return digest.hexdigest()


def _reader_parameters(request):
    if type(request) is not WorkerRequest:
        raise WorkerReaderIntegrityError("request must be a WorkerRequest")
    if (
        request.operation_id != _OPERATION_ID
        or request.operation_version != _OPERATION_VERSION
        or request.inputs
        or set(request.parameters) != _PARAMETER_FIELDS
    ):
        raise WorkerReaderIntegrityError("invalid reader worker request")
    values = request.parameters
    if (
        type(values["reader_id"]) is not str
        or not _TOKEN.fullmatch(values["reader_id"])
        or type(values["source_artifact"]) is not str
        or type(values["source_sha256"]) is not str
        or not _SHA256.fullmatch(values["source_sha256"])
        or type(values["validation_mode"]) is not str
        or values["validation_mode"] not in _VALIDATION_MODES
        or type(values["canonical_parameters"]) is not dict
        or any(
            type(key) is not str
            or not _TOKEN.fullmatch(key)
            or type(value) is not str
            for key, value in values["canonical_parameters"].items()
        )
    ):
        raise WorkerReaderIntegrityError("invalid reader worker parameters")
    return values


def parse_with_worker(request, result, task_directory):
    parameters = _reader_parameters(request)
    if type(result) is not WorkerResult:
        raise WorkerReaderIntegrityError("result must be a WorkerResult")
    if result.request_id != request.request_id:
        raise WorkerReaderIntegrityError("worker result request ID mismatch")
    if result.worker_version != WORKER_VERSION:
        raise WorkerReaderIntegrityError("worker result version mismatch")
    if result.status is not WorkerStatus.SUCCESS:
        code = result.error.code if result.error is not None else result.status.value
        raise WorkerReaderExecutionError(f"reader worker failed: {code}")
    if (
        result.outputs
        or result.cache_key is not None
        or set(result.metadata) != _METADATA_FIELDS
    ):
        raise WorkerReaderIntegrityError("invalid reader worker result")

    metadata = result.metadata
    artifact_hashes = metadata["artifact_sha256"]
    if (
        metadata["operation"] != _OPERATION
        or metadata["schema_version"] != _SCHEMA_VERSION
        or metadata["document_path"] != _DOCUMENT_PATH
        or type(metadata["document_sha256"]) is not str
        or not _SHA256.fullmatch(metadata["document_sha256"])
        or type(artifact_hashes) is not dict
        or any(
            type(path) is not str
            or not _ARTIFACT.fullmatch(path)
            or type(digest) is not str
            or not _SHA256.fullmatch(digest)
            for path, digest in artifact_hashes.items()
        )
        or len(result.artifacts) != len(set(result.artifacts))
        or set(result.artifacts) != {_DOCUMENT_PATH, *artifact_hashes}
    ):
        raise WorkerReaderIntegrityError("invalid reader worker metadata")

    _bundle_inventory(task_directory, artifact_hashes)
    source = _task_file(task_directory, parameters["source_artifact"])
    if _file_sha256(source) != parameters["source_sha256"]:
        raise WorkerReaderIntegrityError("source artifact hash mismatch")
    document = _task_file(task_directory, _DOCUMENT_PATH)
    if _file_sha256(document) != metadata["document_sha256"]:
        raise WorkerReaderIntegrityError("canonical document hash mismatch")
    for relative, expected in artifact_hashes.items():
        if _file_sha256(_task_file(task_directory, relative)) != expected:
            raise WorkerReaderIntegrityError("worker artifact hash mismatch")
    try:
        public = read_public_batch_bundle(Path(task_directory) / _BUNDLE_PATH)
        batch = internal_batch_from_public(public)
    except (CanonicalDocumentError, PublicBatchError) as error:
        raise WorkerReaderIntegrityError(
            "invalid worker reader canonical bundle"
        ) from error
    if (
        len(batch.source_revisions) != 1
        or batch.source_revisions[0].id != request.request_id
    ):
        _remove_verified_bundle(task_directory)
        raise WorkerReaderIntegrityError(
            "worker source revision identity does not match request"
        )
    return batch
