import hashlib
from uuid import uuid4

from ..model import ImportBatch
from ..readers import (
    AmbiguousReaderError,
    CapabilitySupport,
    ReaderNotFoundError,
    ReaderRegistry,
)
from .parse import staged_reader_batch
from .preview import ImportPreview, SourcePreview
from .request import ImportRequest
from .staging import StagedImportSession


HASH_CHUNK_BYTES = 65536


class ImportCancelled(RuntimeError):
    pass


def _noop_progress(stage, completed, total):
    pass


def _not_cancelled():
    return False


def _check_cancelled(is_cancelled):
    if is_cancelled():
        raise ImportCancelled("import preflight was cancelled")


def _hash_file(path, is_cancelled):
    digest = hashlib.sha256()
    byte_size = 0
    _check_cancelled(is_cancelled)
    with path.open("rb") as stream:
        while True:
            _check_cancelled(is_cancelled)
            chunk = stream.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            byte_size += len(chunk)
    _check_cancelled(is_cancelled)
    return digest.hexdigest(), byte_size


def _unavailable_content_hash(source_id):
    return hashlib.sha256(
        b"chemblender:unavailable-source:v1\0" + source_id.bytes
    ).hexdigest()


def _failure_message(error):
    message = str(error).strip()
    return message or type(error).__name__


def preflight_import(
    request,
    registry,
    session,
    *,
    progress=_noop_progress,
    is_cancelled=_not_cancelled,
):
    if type(request) is not ImportRequest:
        raise TypeError("request must be an ImportRequest")
    if type(registry) is not ReaderRegistry:
        raise TypeError("registry must be a ReaderRegistry")
    if type(session) is not StagedImportSession:
        raise TypeError("session must be a StagedImportSession")
    if not callable(progress):
        raise TypeError("progress must be callable")
    if not callable(is_cancelled):
        raise TypeError("is_cancelled must be callable")

    overrides = {
        override.source_id: override.reader_id
        for override in request.reader_overrides
    }
    total = len(request.sources) * 3
    progress("preflight", 0, total)
    source_previews = []
    batch_ids = []
    diagnostic_ids = []

    for index, source in enumerate(request.sources):
        completed = index * 3
        _check_cancelled(is_cancelled)
        reader_override = overrides.get(source.id)
        runtime = None
        try:
            content_hash, byte_size = _hash_file(source.path, is_cancelled)
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except OSError as error:
            unavailable_hash = _unavailable_content_hash(source.id)
            batch = staged_reader_batch(
                source=source,
                validation_mode=request.validation_mode,
                content_hash=unavailable_hash,
                byte_size=0,
                runtime=None,
                reader_override=reader_override,
                content_verified=False,
                failure=(
                    "preflight.source_unavailable",
                    _failure_message(error),
                    "the source content could not be read or verified",
                ),
            )
            source_previews.append(
                _register_preview(
                    source,
                    None,
                    unavailable_hash,
                    0,
                    (),
                    batch,
                    session,
                    batch_ids,
                    diagnostic_ids,
                )
            )
            progress("source_error", completed + 3, total)
            _check_cancelled(is_cancelled)
            continue
        progress("hash", completed + 1, total)

        _check_cancelled(is_cancelled)
        try:
            descriptor = registry.select(source.path, reader_override)
            runtime = registry.runtime(descriptor.reader_id)
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except ReaderNotFoundError as error:
            failure = (
                "preflight.reader_not_found",
                _failure_message(error),
                "no reader could interpret the source",
            )
        except AmbiguousReaderError as error:
            failure = (
                "preflight.reader_ambiguous",
                _failure_message(error),
                "the source reader selection is ambiguous",
            )
        except OSError as error:
            failure = (
                "preflight.reader_selection_failed",
                _failure_message(error),
                "reader selection could not be completed",
            )
        else:
            failure = None
        if failure is not None:
            batch = staged_reader_batch(
                source=source,
                validation_mode=request.validation_mode,
                content_hash=content_hash,
                byte_size=byte_size,
                runtime=None,
                reader_override=reader_override,
                failure=failure,
            )
            source_previews.append(
                _register_preview(
                    source,
                    None,
                    content_hash,
                    byte_size,
                    (),
                    batch,
                    session,
                    batch_ids,
                    diagnostic_ids,
                )
            )
            progress("reader_error", completed + 3, total)
            _check_cancelled(is_cancelled)
            continue

        _check_cancelled(is_cancelled)
        try:
            availability = runtime.current_availability()
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except ImportCancelled:
            raise
        except (ImportError, OSError) as error:
            failure = (
                "preflight.reader_availability_failed",
                _failure_message(error),
                "reader availability could not be determined",
            )
        else:
            failure = None
        capabilities = tuple(
            sorted(
                name
                for name, support in descriptor.capabilities.items()
                if support is not CapabilitySupport.UNSUPPORTED
            )
        )
        if failure is not None or not availability.available:
            if failure is None:
                failure = (
                    "preflight.reader_unavailable",
                    f"{availability.reason_code}: {availability.detail}".rstrip(": "),
                    "the selected reader cannot run in the current environment",
                )
            batch = staged_reader_batch(
                source=source,
                validation_mode=request.validation_mode,
                content_hash=content_hash,
                byte_size=byte_size,
                runtime=runtime,
                reader_override=reader_override,
                failure=failure,
            )
            source_previews.append(
                _register_preview(
                    source,
                    descriptor.reader_id,
                    content_hash,
                    byte_size,
                    capabilities,
                    batch,
                    session,
                    batch_ids,
                    diagnostic_ids,
                )
            )
            progress("reader_unavailable", completed + 3, total)
            _check_cancelled(is_cancelled)
            continue
        progress("reader", completed + 2, total)

        _check_cancelled(is_cancelled)
        try:
            parsed_batch = descriptor.parse(source.path)
            if type(parsed_batch) is not ImportBatch:
                raise TypeError("reader parse must return ImportBatch")
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except ImportCancelled:
            raise
        except (ValueError, UnicodeError, OSError, ImportError) as error:
            failure = (
                "preflight.parse_failed",
                _failure_message(error),
                "no scientific entities were staged from this source",
            )
            parsed_batch = None
        _check_cancelled(is_cancelled)
        if parsed_batch is not None:
            try:
                current_hash, current_size = _hash_file(
                    source.path,
                    is_cancelled,
                )
            except (KeyboardInterrupt, SystemExit, MemoryError):
                raise
            except OSError as error:
                failure = (
                    "preflight.source_changed",
                    _failure_message(error),
                    "the source could not be verified after parsing",
                )
                parsed_batch = None
            else:
                if (current_hash, current_size) != (content_hash, byte_size):
                    failure = (
                        "preflight.source_changed",
                        "source content changed during preflight",
                        "the parsed entities do not match the verified source revision",
                    )
                    parsed_batch = None

        batch = staged_reader_batch(
            source=source,
            validation_mode=request.validation_mode,
            content_hash=content_hash,
            byte_size=byte_size,
            runtime=runtime,
            reader_override=reader_override,
            parsed_batch=parsed_batch,
            failure=failure,
        )
        source_previews.append(
            _register_preview(
                source,
                descriptor.reader_id,
                content_hash,
                byte_size,
                capabilities,
                batch,
                session,
                batch_ids,
                diagnostic_ids,
            )
        )
        progress("parse", completed + 3, total)
        _check_cancelled(is_cancelled)

    return ImportPreview(
        session_id=session.id,
        source_previews=tuple(source_previews),
        staged_batch_ids=tuple(batch_ids),
        diagnostic_ids=tuple(diagnostic_ids),
    )


def _register_preview(
    source,
    reader_id,
    content_hash,
    byte_size,
    capabilities,
    batch,
    session,
    batch_ids,
    diagnostic_ids,
):
    batch_id = uuid4()
    session.register_result(batch_id, batch)
    batch_ids.append(batch_id)
    source_diagnostic_ids = tuple(item.id for item in batch.diagnostics)
    diagnostic_ids.extend(source_diagnostic_ids)
    return SourcePreview(
        source_id=source.id,
        source_path=source.path,
        selected_reader_id=reader_id,
        content_hash=content_hash,
        byte_size=byte_size,
        capabilities=capabilities,
        staged_batch_ids=(batch_id,),
        diagnostic_ids=source_diagnostic_ids,
    )
