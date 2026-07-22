import argparse
import re
from pathlib import Path

from ChemBlender.core import ImportBatch, close_project, open_project, save_project
from ChemBlender.core.sidecar import SidecarError

from .protocol import (
    EntityReference,
    ProtocolError,
    WorkerError,
    WorkerRequest,
    WorkerResult,
    WorkerStatus,
    read_request,
    write_result,
)
from .operation import OperationContext, OperationError, OperationOutput


_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*")


class OperationRegistry:
    def __init__(self):
        self._operations = {}

    def register(self, operation_id, operation_version, operation):
        if not isinstance(operation_id, str) or not _TOKEN.fullmatch(operation_id):
            raise ValueError("operation_id must be a lower token")
        if not isinstance(operation_version, str) or not operation_version:
            raise ValueError("operation_version must be non-empty")
        if not callable(operation):
            raise TypeError("operation must be callable")
        key = (operation_id, operation_version)
        if key in self._operations:
            raise ValueError("operation is already registered")
        self._operations[key] = operation

    def get(self, operation_id, operation_version):
        try:
            return self._operations[(operation_id, operation_version)]
        except KeyError as error:
            raise LookupError(
                f"unsupported operation: {operation_id}@{operation_version}"
            ) from error


def _entities(project):
    registries = (
        project.structures,
        project.cif_envelopes,
        project.qcschema_envelopes,
        project.cjson_envelopes,
        project.symmetry_results,
        project.calculations,
        project.datasets,
        project.basis_sets,
        project.orbital_sets,
        project.density_matrices,
        project.provenance,
    )
    return {entity_id: entity for registry in registries for entity_id, entity in registry.items()}


def _validate_references(project, references, label):
    entities = _entities(project)
    for reference in references:
        entity = entities.get(reference.entity_id)
        if entity is None or entity.revision != reference.revision:
            raise ValueError(
                f"{label} entity is missing or stale: {reference.entity_id}"
            )


def _batch_references(batch):
    groups = (
        batch.structures,
        batch.cif_envelopes,
        batch.qcschema_envelopes,
        batch.cjson_envelopes,
        batch.symmetry_results,
        batch.calculations,
        batch.datasets,
        batch.basis_sets,
        batch.orbital_sets,
        batch.density_matrices,
        batch.provenance,
    )
    return tuple(
        EntityReference(entity.id, entity.revision)
        for group in groups
        for entity in group
    )


def _resolve_project_path(request_path, locator):
    path = Path(locator)
    if not path.is_absolute():
        path = Path(request_path).resolve().parent / path
    return path.resolve()


def _error(request_id, status, code, message):
    return WorkerResult(
        request_id=request_id,
        status=status,
        error=WorkerError(code, message or code),
    )


def run_request(request_path, result_path, registry, *, cancel_path=None):
    if not isinstance(registry, OperationRegistry):
        raise TypeError("registry must be an OperationRegistry")
    request = read_request(request_path)
    project_path = _resolve_project_path(request_path, request.project_locator)
    cancel_path = None if cancel_path is None else Path(cancel_path)
    project = None
    try:
        if cancel_path is not None and cancel_path.exists():
            result = _error(
                request.request_id,
                WorkerStatus.CANCELLED,
                "cancelled",
                "request was cancelled before execution",
            )
        else:
            try:
                operation = registry.get(
                    request.operation_id, request.operation_version
                )
            except LookupError as error:
                result = _error(
                    request.request_id,
                    WorkerStatus.ERROR,
                    "unsupported_operation",
                    str(error),
                )
            else:
                try:
                    project = open_project(
                        project_path,
                        expected_project_id=request.project_id,
                        expected_schema_version=request.project_schema_version,
                    )
                    _validate_references(project, request.inputs, "input")
                except (SidecarError, ValueError) as error:
                    result = _error(
                        request.request_id,
                        WorkerStatus.ERROR,
                        "project_error",
                        str(error),
                    )
                else:
                    context = OperationContext(project_path, project, cancel_path)
                    try:
                        output = operation(context, request)
                        if not isinstance(output, OperationOutput):
                            raise TypeError("operation must return OperationOutput")
                    except OperationError as error:
                        result = _error(
                            request.request_id,
                            WorkerStatus.ERROR,
                            error.code,
                            str(error) or error.code,
                        )
                    except Exception as error:
                        result = _error(
                            request.request_id,
                            WorkerStatus.ERROR,
                            "operation_failed",
                            str(error) or type(error).__name__,
                        )
                    else:
                        if context.is_cancelled():
                            result = _error(
                                request.request_id,
                                WorkerStatus.CANCELLED,
                                "cancelled",
                                "request was cancelled before result publication",
                            )
                        else:
                            if output.batch is not None:
                                try:
                                    if not isinstance(output.batch, ImportBatch):
                                        raise TypeError(
                                            "operation batch must be an ImportBatch"
                                        )
                                    if set(output.outputs) != set(
                                        _batch_references(output.batch)
                                    ):
                                        raise ValueError(
                                            "operation outputs must exactly match its batch"
                                        )
                                    project.commit(output.batch)
                                    save_project(project_path, project)
                                except Exception as error:
                                    result = _error(
                                        request.request_id,
                                        WorkerStatus.ERROR,
                                        "output_commit_failed",
                                        str(error) or type(error).__name__,
                                    )
                                    write_result(result_path, result)
                                    return result
                            close_project(project)
                            project = None
                            try:
                                published = open_project(
                                    project_path,
                                    expected_project_id=request.project_id,
                                    expected_schema_version=request.project_schema_version,
                                )
                                _validate_references(
                                    published, output.outputs, "output"
                                )
                                for artifact in output.artifacts:
                                    candidate = (project_path / artifact).resolve()
                                    candidate.relative_to(project_path)
                                    if not candidate.is_file():
                                        raise ValueError(
                                            f"output artifact is missing: {artifact}"
                                        )
                            except (SidecarError, ValueError) as error:
                                result = _error(
                                    request.request_id,
                                    WorkerStatus.ERROR,
                                    "output_validation_failed",
                                    str(error),
                                )
                            else:
                                result = WorkerResult(
                                    request_id=request.request_id,
                                    status=WorkerStatus.SUCCESS,
                                    outputs=output.outputs,
                                    artifacts=output.artifacts,
                                    cache_key=output.cache_key,
                                    metadata=output.metadata,
                                )
                            finally:
                                if "published" in locals():
                                    close_project(published)
        write_result(result_path, result)
        return result
    finally:
        if project is not None:
            close_project(project)


def default_registry():
    registry = OperationRegistry()
    registry.register(
        "project.verify",
        "1",
        lambda context, request: OperationOutput(
            metadata={
                "project_id": str(context.project.id),
                "schema_version": context.project.schema_version,
            }
        ),
    )
    from .wavefunction_operations import register_wavefunction_operations

    register_wavefunction_operations(registry)
    from .qcengine_operation import register_qcschema_compute_operation

    register_qcschema_compute_operation(registry)
    from .connector_operation import register_external_record_operation

    register_external_record_operation(registry)
    return registry


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one ChemBlender worker request")
    parser.add_argument("request")
    parser.add_argument("result")
    parser.add_argument("--cancel-file")
    args = parser.parse_args(argv)
    try:
        result = run_request(
            args.request,
            args.result,
            default_registry(),
            cancel_path=args.cancel_file,
        )
    except ProtocolError as error:
        parser.error(str(error))
    return 0 if result.status is WorkerStatus.SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
