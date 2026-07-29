from collections.abc import Mapping
from dataclasses import fields, replace
import re
import shutil
from uuid import UUID, uuid4

from ..core.import_pipeline.parse import stage_import_batch
from ..core.import_pipeline.preflight import (
    ImportCancelled,
    _check_cancelled,
    _failure_message,
    _hash_and_prefix_file,
    _hash_file,
    _materialize_text_source,
    _register_preview,
    _unavailable_content_hash,
)
from ..core.import_pipeline.preview import ImportPreview
from ..core.import_pipeline.request import ImportRequest
from ..core.import_pipeline.staging import (
    StagedImportSession,
    _close_memmaps,
)
from ..core.readers import (
    AmbiguousReaderError,
    CapabilitySupport,
    ReaderNotFoundError,
)
from .builtin_bridge import (
    PublicBatchError,
    _internal_batch_from_public_unchecked,
    _validate_internal_batch_graph,
    internal_batch_from_public,
    public_batch_from_internal,
)
from .protocol import ParseRequest, ProgressEvent, SniffRequest
from .public_model import PublicImportBatch
from .registry import ReaderPluginRegistry, _BuiltinReaderPlugin
from .version import READER_API_VERSION


_RESERVED_PARAMETERS = frozenset(
    ("source_content_state", "validation_mode")
)
_PARAMETER = re.compile(r"[a-z][a-z0-9_.-]*", re.ASCII)
_SCIENTIFIC_GROUPS = (
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


def _noop_progress(stage, completed, total):
    pass


def _not_cancelled():
    return False


def _remove_reader_staging_root(root):
    if not root.exists():
        return
    if root.is_symlink() or root.is_junction() or not root.is_dir():
        raise RuntimeError("refusing to remove an unsafe reader staging root")
    shutil.rmtree(root)


class _BridgeCancelled(BaseException):
    pass


class _BridgeHostCallbackError(BaseException):
    def __init__(self, error):
        self.error = error


def _parameters(request, values):
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise TypeError("canonical_parameters_by_source must be a mapping")
    source_ids = {source.id for source in request.sources}
    if any(type(source_id) is not UUID for source_id in values):
        raise TypeError("canonical parameter source keys must be UUID values")
    if not set(values).issubset(source_ids):
        raise ValueError("canonical parameters must target an included source")
    normalized = {}
    for source_id, parameters in values.items():
        if not isinstance(parameters, Mapping):
            raise TypeError("canonical source parameters must be mappings")
        parameters = dict(parameters)
        if _RESERVED_PARAMETERS.intersection(parameters):
            raise ValueError("canonical parameters contain a reserved key")
        if any(
            type(key) is not str
            or not _PARAMETER.fullmatch(key)
            or type(value) is not str
            for key, value in parameters.items()
        ):
            raise TypeError("canonical parameters must map strings to strings")
        normalized[source_id] = tuple(sorted(parameters.items()))
    return normalized


def _cancel_callback(is_cancelled):
    def check():
        _check_bridge_cancelled(is_cancelled)
        return False

    return check


def _check_bridge_cancelled(is_cancelled):
    try:
        cancelled = is_cancelled()
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except Exception as error:
        raise _BridgeHostCallbackError(error) from error
    if type(cancelled) is not bool:
        raise _BridgeHostCallbackError(
            TypeError("is_cancelled must return bool")
        )
    if cancelled:
        raise _BridgeCancelled


def _plugin_progress(progress, is_cancelled):
    def report(event):
        if type(event) is not ProgressEvent:
            raise TypeError("reader progress must be a ProgressEvent")
        try:
            progress(
                f"reader.{event.stage}",
                event.completed,
                event.total,
            )
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception as error:
            raise _BridgeHostCallbackError(error) from error
        _check_bridge_cancelled(is_cancelled)

    return report


def _has_scientific_entities(batch):
    return any(getattr(batch, name) for name in _SCIENTIFIC_GROUPS)


def _staged_identity(batch):
    return tuple(
        (name, entity.id)
        for name in (
            "sources",
            "source_revisions",
            *_SCIENTIFIC_GROUPS,
        )
        for entity in getattr(batch, name)
    )


def _diagnostic_signature(diagnostic):
    return tuple(
        getattr(diagnostic, field.name)
        for field in fields(diagnostic)
        if field.name != "id"
    )


def _source_changed_failure(error):
    return (
        "preflight.source_changed",
        _failure_message(error),
        "the source could not be verified after reader selection",
    )


def preflight_reader_plugins(
    request,
    registry,
    session,
    *,
    canonical_parameters_by_source=None,
    progress=None,
    is_cancelled=None,
) -> ImportPreview:
    if type(request) is not ImportRequest:
        raise TypeError("request must be an ImportRequest")
    if type(registry) is not ReaderPluginRegistry:
        raise TypeError("registry must be a ReaderPluginRegistry")
    if type(session) is not StagedImportSession:
        raise TypeError("session must be a StagedImportSession")
    progress = _noop_progress if progress is None else progress
    is_cancelled = _not_cancelled if is_cancelled is None else is_cancelled
    if not callable(progress) or not callable(is_cancelled):
        raise TypeError("progress and is_cancelled must be callable")
    parameters_by_source = _parameters(
        request, canonical_parameters_by_source
    )
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
        source_path = _materialize_text_source(source, session)
        override = overrides.get(source.id)
        parameters = parameters_by_source.get(source.id, ())
        try:
            content_hash, byte_size, prefix = _hash_and_prefix_file(
                source_path, _cancel_callback(is_cancelled)
            )
        except _BridgeCancelled:
            raise ImportCancelled(
                "import preflight was cancelled"
            ) from None
        except _BridgeHostCallbackError as error:
            raise error.error from None
        except (KeyboardInterrupt, SystemExit, MemoryError, ImportCancelled):
            raise
        except OSError as error:
            content_hash = _unavailable_content_hash(source.id)
            byte_size = 0
            batch = stage_import_batch(
                source=source,
                validation_mode=request.validation_mode,
                content_hash=content_hash,
                byte_size=byte_size,
                plugin_id="chemblender.preflight",
                reader_id=override or "unresolved",
                reader_version="0",
                api_version=READER_API_VERSION,
                content_verified=False,
                failure=(
                    "preflight.source_unavailable",
                    _failure_message(error),
                    "the source content could not be read or verified",
                ),
            )
            source_previews.append(_register_preview(
                source, None, content_hash, byte_size, (), batch, session,
                batch_ids, diagnostic_ids,
            ))
            progress("source_error", completed + 3, total)
            _check_cancelled(is_cancelled)
            continue
        progress("hash", completed + 1, total)

        try:
            descriptor = registry.select(
                SniffRequest(source_path, prefix), override
            )
        except (KeyboardInterrupt, SystemExit, MemoryError, ImportCancelled):
            raise
        except ReaderNotFoundError as error:
            descriptor = None
            failure = (
                "preflight.reader_not_found",
                _failure_message(error),
                "no reader could interpret the source",
            )
        except AmbiguousReaderError as error:
            descriptor = None
            failure = (
                "preflight.reader_ambiguous",
                _failure_message(error),
                "the source reader selection is ambiguous",
            )
        except Exception as error:
            descriptor = None
            failure = (
                "preflight.reader_selection_failed",
                _failure_message(error),
                "reader selection could not be completed",
            )
        else:
            failure = None

        if descriptor is None:
            batch = stage_import_batch(
                source=source,
                validation_mode=request.validation_mode,
                content_hash=content_hash,
                byte_size=byte_size,
                plugin_id="chemblender.preflight",
                reader_id=override or "unresolved",
                reader_version="0",
                api_version=READER_API_VERSION,
                canonical_parameters=parameters,
                failure=failure,
            )
            source_previews.append(_register_preview(
                source, None, content_hash, byte_size, (), batch, session,
                batch_ids, diagnostic_ids,
            ))
            progress("reader_error", completed + 3, total)
            _check_cancelled(is_cancelled)
            continue

        capabilities = tuple(sorted(
            name
            for name, support in descriptor.capabilities.items()
            if support is not CapabilitySupport.UNSUPPORTED
        ))
        reader_staging_root = None
        materializer = None
        if not descriptor.availability.available:
            failure = (
                "preflight.reader_unavailable",
                (
                    f"{descriptor.availability.reason_code}: "
                    f"{descriptor.availability.detail}"
                ).rstrip(": "),
                "the selected reader cannot run in the current environment",
            )
            internal = None
            revision_id = None
        else:
            progress("reader", completed + 2, total)
            revision_id = uuid4()
            reader_staging_root = session.artifact_root / str(revision_id)
            reader_staging_root.mkdir()
            keep_reader_artifacts = False
            try:
                try:
                    parse_request = ParseRequest(
                        source_path,
                        content_hash,
                        request.validation_mode.value,
                        dict(parameters),
                        reader_staging_root,
                        _plugin_progress(progress, is_cancelled),
                        _cancel_callback(is_cancelled),
                        revision_id,
                    )
                    plugin = registry._plugin(descriptor.reader_id)
                    trusted_builtin = type(plugin) is _BuiltinReaderPlugin
                    preview_parser = (
                        plugin.core_descriptor.preview_request
                        if trusted_builtin
                        else None
                    )
                    if preview_parser is None:
                        public = registry.parse(
                            descriptor.reader_id,
                            parse_request,
                        )
                    else:
                        parse_request.progress(
                            ProgressEvent("parse", 0, 1)
                        )
                        public = public_batch_from_internal(
                            preview_parser(parse_request)
                        )
                        current_hash, _current_size = _hash_file(
                            source_path,
                            parse_request.is_cancelled,
                        )
                        if current_hash != content_hash:
                            raise ValueError(
                                "source content changed during preview parse"
                            )
                        parse_request.progress(
                            ProgressEvent("parse", 1, 1)
                        )
                except _BridgeCancelled:
                    raise ImportCancelled(
                        "import preflight was cancelled"
                    ) from None
                except _BridgeHostCallbackError as error:
                    raise error.error from None
                except ValueError as error:
                    if (
                        str(error) != "source_path must be a file"
                        or source_path.is_file()
                    ):
                        raise
                    internal = None
                    failure = _source_changed_failure(error)
                except OSError as error:
                    internal = None
                    failure = _source_changed_failure(error)
                else:
                    _check_cancelled(is_cancelled)
                    try:
                        internal = (
                            _internal_batch_from_public_unchecked(public)
                            if trusted_builtin
                            else internal_batch_from_public(public)
                        )
                        supplied_identity = bool(
                            internal.sources or internal.source_revisions
                        )
                        if (
                            not trusted_builtin
                            and _has_scientific_entities(internal)
                            and not supplied_identity
                        ):
                            raise ValueError(
                                "external scientific result omitted source identity"
                            )
                        internal = stage_import_batch(
                            source=source,
                            validation_mode=request.validation_mode,
                            content_hash=content_hash,
                            byte_size=byte_size,
                            plugin_id=descriptor.plugin_id,
                            reader_id=descriptor.reader_id,
                            reader_version=descriptor.reader_version,
                            api_version=READER_API_VERSION,
                            canonical_parameters=parameters,
                            parsed_batch=internal,
                            preserve_source_identity=supplied_identity,
                            revision_id=revision_id,
                        )
                        _validate_internal_batch_graph(internal)
                        failure = None
                        keep_reader_artifacts = (
                            _has_scientific_entities(internal)
                            and any(reader_staging_root.iterdir())
                        )
                        materialize_parser = (
                            plugin.core_descriptor.materialize_request
                            if trusted_builtin
                            else None
                        )
                        if materialize_parser is not None:
                            expected_identity = _staged_identity(internal)
                            expected_diagnostics = internal.diagnostics

                            def materialize(
                                materialize_progress,
                                materialize_cancelled,
                                *,
                                _parser=materialize_parser,
                                _request=parse_request,
                                _expected=expected_identity,
                                _expected_diagnostics=expected_diagnostics,
                                _source=source,
                                _validation=request.validation_mode,
                                _content_hash=content_hash,
                                _byte_size=byte_size,
                                _plugin_id=descriptor.plugin_id,
                                _reader_id=descriptor.reader_id,
                                _reader_version=descriptor.reader_version,
                                _parameters=parameters,
                                _revision_id=revision_id,
                            ):
                                before_artifacts = frozenset(
                                    _request.staging_root.iterdir()
                                )
                                try:
                                    parsed = _parser(
                                        ParseRequest(
                                            _request.source_path,
                                            _request.source_content_hash,
                                            _request.validation_mode,
                                            dict(
                                                _request.canonical_parameters
                                            ),
                                            _request.staging_root,
                                            _plugin_progress(
                                                materialize_progress,
                                                materialize_cancelled,
                                            ),
                                            _cancel_callback(
                                                materialize_cancelled
                                            ),
                                            _request.source_revision_id,
                                        )
                                    )
                                except _BridgeCancelled:
                                    raise ImportCancelled(
                                        "import materialization was cancelled"
                                    ) from None
                                except _BridgeHostCallbackError as error:
                                    raise error.error from None
                                if parsed is None:
                                    return None
                                candidate = None
                                try:
                                    parsed = _internal_batch_from_public_unchecked(
                                        public_batch_from_internal(parsed)
                                    )
                                    candidate = stage_import_batch(
                                        source=_source,
                                        validation_mode=_validation,
                                        content_hash=_content_hash,
                                        byte_size=_byte_size,
                                        plugin_id=_plugin_id,
                                        reader_id=_reader_id,
                                        reader_version=_reader_version,
                                        api_version=READER_API_VERSION,
                                        canonical_parameters=_parameters,
                                        parsed_batch=parsed,
                                        revision_id=_revision_id,
                                    )
                                    _validate_internal_batch_graph(candidate)
                                    if (
                                        _staged_identity(candidate) != _expected
                                        or tuple(
                                            map(
                                                _diagnostic_signature,
                                                candidate.diagnostics,
                                            )
                                        )
                                        != tuple(
                                            map(
                                                _diagnostic_signature,
                                                _expected_diagnostics,
                                            )
                                        )
                                    ):
                                        raise ValueError(
                                            "materialized reader result changed; "
                                            "refresh Import Preview"
                                        )
                                    diagnostic_ids = tuple(
                                        item.id for item in _expected_diagnostics
                                    )
                                    return replace(
                                        candidate,
                                        diagnostics=tuple(
                                            replace(item, id=identifier)
                                            for item, identifier in zip(
                                                candidate.diagnostics,
                                                diagnostic_ids,
                                                strict=True,
                                            )
                                        ),
                                        source_revisions=tuple(
                                            replace(
                                                revision,
                                                diagnostic_ids=diagnostic_ids,
                                            )
                                            for revision in candidate.source_revisions
                                        ),
                                    )
                                except BaseException as error:
                                    try:
                                        _close_memmaps(
                                            candidate or parsed,
                                            set(),
                                        )
                                    except BaseException as cleanup_error:
                                        error.add_note(
                                            "materialized array cleanup failed: "
                                            f"{cleanup_error}"
                                        )
                                    for artifact in tuple(
                                        _request.staging_root.iterdir()
                                    ):
                                        if artifact in before_artifacts:
                                            continue
                                        try:
                                            if artifact.is_file():
                                                artifact.unlink()
                                            elif artifact.is_dir():
                                                _remove_reader_staging_root(
                                                    artifact
                                                )
                                            else:
                                                raise RuntimeError(
                                                    "unsafe materialized artifact"
                                                )
                                        except BaseException as cleanup_error:
                                            error.add_note(
                                                "materialized artifact cleanup "
                                                f"failed: {cleanup_error}"
                                            )
                                    raise

                            materializer = materialize
                    except (
                        PublicBatchError,
                        TypeError,
                        ValueError,
                        KeyError,
                    ) as error:
                        internal = None
                        failure = (
                            "preflight.invalid_reader_result",
                            _failure_message(error),
                            "the reader result did not satisfy the import identity contract",
                        )
            finally:
                if not keep_reader_artifacts:
                    _remove_reader_staging_root(reader_staging_root)

        if internal is None:
            internal = stage_import_batch(
                source=source,
                validation_mode=request.validation_mode,
                content_hash=content_hash,
                byte_size=byte_size,
                plugin_id=descriptor.plugin_id,
                reader_id=descriptor.reader_id,
                reader_version=descriptor.reader_version,
                api_version=READER_API_VERSION,
                canonical_parameters=parameters,
                failure=failure,
                revision_id=revision_id,
            )
        try:
            progress("parse", completed + 3, total)
            _check_cancelled(is_cancelled)
        except BaseException:
            try:
                if (
                    reader_staging_root is not None
                    and reader_staging_root.exists()
                ):
                    _close_memmaps(internal, set())
                    _remove_reader_staging_root(reader_staging_root)
            except BaseException:
                pass
            raise
        source_previews.append(_register_preview(
            source,
            descriptor.reader_id,
            content_hash,
            byte_size,
            capabilities,
            internal,
            session,
            batch_ids,
            diagnostic_ids,
            source_id=internal.sources[0].id,
            materializer=materializer,
        ))

    return ImportPreview(
        session.id,
        tuple(source_previews),
        tuple(batch_ids),
        diagnostic_ids=tuple(diagnostic_ids),
    )
