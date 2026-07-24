import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from ..model import (
    DiagnosticSeverity,
    ImportBatch,
    ImportDiagnostic,
    QualityStatus,
    SourceRecord,
    SourceRevision,
    diagnostic_from_parser_issue,
    source_parse_identity,
)


_ENTITY_GROUPS = (
    "structures",
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


def staged_reader_batch(
    *,
    source,
    validation_mode,
    content_hash,
    byte_size,
    runtime,
    reader_override,
    content_verified=True,
    parsed_batch=None,
    failure=None,
):
    parsed_batch = ImportBatch() if parsed_batch is None else parsed_batch
    revision_id = uuid4()
    if runtime is None:
        plugin_id = "chemblender.preflight"
        reader_id = reader_override or "unresolved"
        reader_version = "0"
        api_version = "0.1"
        execution_mode = "built_in"
    else:
        descriptor = runtime.descriptor
        plugin_id = runtime.plugin_id
        reader_id = descriptor.reader_id
        reader_version = descriptor.reader_version
        api_version = runtime.api_version
        execution_mode = runtime.execution_mode

    parameters = (
        ("execution_mode", execution_mode),
        ("reader_override", reader_override),
        (
            "source_content_state",
            "verified" if content_verified else "unavailable",
        ),
        ("validation_mode", validation_mode.value),
    )
    parameters_hash = hashlib.sha256(
        json.dumps(
            parameters,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    parse_identity = source_parse_identity(
        content_hash,
        plugin_id,
        reader_id,
        reader_version,
        parameters,
    )

    diagnostics = [
        replace(item, source_revision_id=revision_id)
        for item in parsed_batch.diagnostics
    ]
    if parsed_batch.report is not None:
        diagnostics.extend(
            diagnostic_from_parser_issue(
                issue,
                revision_id,
                reader_id=reader_id,
            )
            for issue in parsed_batch.report.issues
        )
    if failure is not None:
        code, message, consequence = failure
        diagnostics.append(
            ImportDiagnostic(
                id=uuid4(),
                severity=DiagnosticSeverity.ERROR,
                quality_status=QualityStatus.INVALID,
                source_revision_id=revision_id,
                record_key=None,
                entity_id=None,
                field_path="source",
                code=code,
                message=message,
                original_value=None,
                normalized_value=None,
                recovery_action=None,
                scientific_consequence=consequence,
                suggested_action=None,
            )
        )

    created_entity_ids = tuple(
        entity.id
        for name in _ENTITY_GROUPS
        for entity in getattr(parsed_batch, name)
    )
    source_record = SourceRecord(
        id=source.id,
        display_name=source.path.name,
        source_kind="local_file",
        created_at_utc=datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    )
    revision = SourceRevision(
        id=revision_id,
        source_id=source.id,
        content_hash=content_hash,
        byte_size=byte_size,
        locator=str(source.path),
        locator_kind="absolute_path",
        original_filename=source.path.name,
        reader_plugin_id=plugin_id,
        reader_id=reader_id,
        reader_version=reader_version,
        reader_api_version=api_version,
        import_parameters_hash=parameters_hash,
        parse_identity=parse_identity,
        created_entity_ids=created_entity_ids,
        diagnostic_ids=tuple(item.id for item in diagnostics),
    )
    return replace(
        parsed_batch,
        sources=(source_record,),
        source_revisions=(revision,),
        diagnostics=tuple(diagnostics),
    )
