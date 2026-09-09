import shutil
from pathlib import Path

from chemblender_prepare.core.import_pipeline import ImportSource
from chemblender_prepare.core.import_pipeline import ValidationMode
from chemblender_prepare.core.import_pipeline.parse import stage_import_batch
from chemblender_prepare.reader_api.builtin_bridge import PublicBatchError
from chemblender_prepare.reader_api.builtin_bridge import _internal_batch_from_public_unchecked
from chemblender_prepare.reader_api.builtin_bridge import _validate_internal_batch_graph
from chemblender_prepare.reader_api.builtin_bridge import internal_batch_from_public
from chemblender_prepare.reader_api.builtin_bridge import public_batch_from_internal
from chemblender_prepare.reader_api.canonical_document import CanonicalDocumentError
from chemblender_prepare.reader_api.canonical_document import read_public_batch_bundle
from chemblender_prepare.reader_api.canonical_document import write_public_batch_bundle
from chemblender_prepare.reader_api.protocol import ParseRequest
from chemblender_prepare.reader_api.registry import _BuiltinReaderPlugin
from chemblender_prepare.reader_api.registry import builtin_reader_plugin_registry
from chemblender_prepare.reader_api.version import READER_API_VERSION
from chemblender_prepare.reader_api.worker_bridge import WorkerReaderIntegrityError
from chemblender_prepare.reader_api.worker_bridge import _DOCUMENT_PATH
from chemblender_prepare.reader_api.worker_bridge import _OPERATION
from chemblender_prepare.reader_api.worker_bridge import _SCHEMA_VERSION
from chemblender_prepare.reader_api.worker_bridge import _WorkerReaderCancelled
from chemblender_prepare.reader_api.worker_bridge import _file_sha256
from chemblender_prepare.reader_api.worker_bridge import _link_like
from chemblender_prepare.reader_api.worker_bridge import _reader_parameters
from chemblender_prepare.reader_api.worker_bridge import _task_file

from chemblender_prepare.worker.operation import OperationError
from chemblender_prepare.worker.operation import OperationOutput


def _remove_owned_bundle(task_directory, bundle):
    task_directory = Path(task_directory).resolve(strict=True)
    bundle = Path(bundle)
    if bundle != task_directory / "reader-bundle":
        raise OperationError(
            "reader_cleanup_failed",
            "refusing to remove an unexpected reader bundle",
        )
    if _link_like(bundle):
        raise OperationError(
            "reader_cleanup_failed",
            "refusing to remove a linked reader bundle",
        )
    if not bundle.exists():
        return
    if not bundle.is_dir():
        raise OperationError(
            "reader_cleanup_failed",
            "refusing to remove a non-directory reader bundle",
        )
    try:
        shutil.rmtree(bundle)
    except OSError as error:
        raise OperationError(
            "reader_cleanup_failed",
            "cannot remove reader bundle",
        ) from error


def _reader_parse(context, request):
    try:
        parameters = _reader_parameters(request)
        source = _task_file(
            context.task_directory,
            parameters["source_artifact"],
        )
    except WorkerReaderIntegrityError as error:
        raise OperationError("reader_request_invalid", str(error)) from error
    try:
        source_hash = _file_sha256(source, context.is_cancelled)
    except _WorkerReaderCancelled:
        return OperationOutput()
    except WorkerReaderIntegrityError as error:
        raise OperationError(
            "reader_source_invalid",
            "cannot read source artifact",
        ) from error
    if source_hash != parameters["source_sha256"]:
        raise OperationError(
            "reader_source_invalid",
            "source artifact hash mismatch",
        )

    registry = builtin_reader_plugin_registry()
    descriptor = next(
        (
            value
            for value in registry.descriptors
            if value.reader_id == parameters["reader_id"]
        ),
        None,
    )
    if descriptor is None:
        raise OperationError("reader_not_found", "worker reader is not registered")
    if not descriptor.availability.available:
        raise OperationError(
            "reader_unavailable",
            descriptor.availability.reason_code,
        )

    from .wavefunction_operations import _progress
    report_progress = _progress(context)
    batch = registry.parse(
        descriptor.reader_id,
        ParseRequest(
            source_path=source,
            source_content_hash=parameters["source_sha256"],
            validation_mode=parameters["validation_mode"],
            canonical_parameters=parameters["canonical_parameters"],
            staging_root=context.task_directory,
            progress=lambda event: report_progress(event.completed, event.total) if report_progress else None,
            is_cancelled=context.is_cancelled,
            source_revision_id=request.request_id,
        ),
    )
    if context.is_cancelled():
        return OperationOutput()
    entity_fields = (
        "sources",
        "source_revisions",
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
    failed_paths = {"reader.parse", "reader.source", "reader.availability"}
    if (
        not any(getattr(batch, field) for field in entity_fields)
        and batch.report is not None
        and any(issue.path in failed_paths for issue in batch.report.issues)
    ):
        raise OperationError(
            "reader_parse_failed",
            "reader returned a failed public batch: " + "; ".join(
                issue.message for issue in batch.report.issues if issue.path in failed_paths),
        )

    try:
        plugin = registry._plugin(descriptor.reader_id)
        internal = (
            _internal_batch_from_public_unchecked(batch)
            if type(plugin) is _BuiltinReaderPlugin
            else internal_batch_from_public(batch)
        )
        internal = stage_import_batch(
            source=ImportSource(source),
            validation_mode=ValidationMode(parameters["validation_mode"]),
            content_hash=parameters["source_sha256"],
            byte_size=source.stat().st_size,
            plugin_id=descriptor.plugin_id,
            reader_id=descriptor.reader_id,
            reader_version=descriptor.reader_version,
            api_version=READER_API_VERSION,
            canonical_parameters=tuple(
                sorted(parameters["canonical_parameters"].items())
            ),
            parsed_batch=internal,
            revision_id=request.request_id,
        )
        _validate_internal_batch_graph(internal)
        batch = public_batch_from_internal(internal)
    except (PublicBatchError, TypeError, ValueError, KeyError, OSError) as error:
        raise OperationError(
            "reader_output_invalid",
            "reader result did not satisfy the import identity contract",
        ) from error

    task_directory = Path(context.task_directory).resolve(strict=True)
    bundle = task_directory / "reader-bundle"
    try:
        bundle.mkdir()
    except FileExistsError as error:
        raise OperationError(
            "reader_output_invalid",
            "reader bundle already exists",
        ) from error
    except OSError as error:
        raise OperationError(
            "reader_output_invalid",
            "cannot create reader bundle",
        ) from error
    completed = False
    try:
        try:
            write_public_batch_bundle(bundle, batch)
            reopened = read_public_batch_bundle(bundle)
            internal_batch_from_public(reopened)
        except (CanonicalDocumentError, PublicBatchError, OSError) as error:
            raise OperationError(
                "reader_output_invalid",
                "reader canonical bundle validation failed",
            ) from error

        document = task_directory / Path(*_DOCUMENT_PATH.split("/"))
        try:
            artifact_hashes = {
                path.relative_to(task_directory).as_posix(): _file_sha256(
                    path,
                    context.is_cancelled,
                )
                for path in sorted((bundle / "artifacts").glob("*.npy"))
            }
            document_hash = _file_sha256(document, context.is_cancelled)
        except _WorkerReaderCancelled:
            return OperationOutput()
        except WorkerReaderIntegrityError as error:
            raise OperationError(
                "reader_output_invalid",
                "cannot hash reader output",
            ) from error
        output = OperationOutput(
            artifacts=(_DOCUMENT_PATH, *artifact_hashes),
            metadata={
                "operation": _OPERATION,
                "schema_version": _SCHEMA_VERSION,
                "document_path": _DOCUMENT_PATH,
                "document_sha256": document_hash,
                "artifact_sha256": artifact_hashes,
            },
        )
        completed = True
        return output
    finally:
        if not completed:
            _remove_owned_bundle(task_directory, bundle)


def register_reader_operation(registry):
    registry.register("reader.parse", "0.1", _reader_parse)
