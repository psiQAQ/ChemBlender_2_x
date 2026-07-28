import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

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
    revision_id=None,
):
    if runtime is None:
        plugin_id = "chemblender.preflight"
        reader_id = reader_override or "unresolved"
        reader_version = "0"
        api_version = "0.1"
    else:
        descriptor = runtime.descriptor
        plugin_id = runtime.plugin_id
        reader_id = descriptor.reader_id
        reader_version = descriptor.reader_version
        api_version = runtime.api_version

    return stage_import_batch(
        source=source,
        validation_mode=validation_mode,
        content_hash=content_hash,
        byte_size=byte_size,
        plugin_id=plugin_id,
        reader_id=reader_id,
        reader_version=reader_version,
        api_version=api_version,
        content_verified=content_verified,
        parsed_batch=parsed_batch,
        failure=failure,
        revision_id=revision_id,
    )


def stage_import_batch(
    *,
    source,
    validation_mode,
    content_hash,
    byte_size,
    plugin_id,
    reader_id,
    reader_version,
    api_version,
    canonical_parameters=(),
    content_verified=True,
    parsed_batch=None,
    failure=None,
    preserve_source_identity=False,
    revision_id=None,
):
    if revision_id is not None and type(revision_id) is not UUID:
        raise TypeError("revision_id must be a UUID or None")
    parsed_batch = ImportBatch() if parsed_batch is None else parsed_batch
    parameters = (
        (
            "source_content_state",
            "verified" if content_verified else "unavailable",
        ),
        ("validation_mode", validation_mode.value),
        *tuple(canonical_parameters),
    )
    parameters = tuple(sorted(parameters))
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

    if preserve_source_identity:
        _validate_supplied_identity(
            parsed_batch,
            source=source,
            content_hash=content_hash,
            byte_size=byte_size,
            plugin_id=plugin_id,
            reader_id=reader_id,
            reader_version=reader_version,
            api_version=api_version,
            parameters_hash=parameters_hash,
            parse_identity=parse_identity,
            revision_id=revision_id,
        )
        return parsed_batch

    revision_id = uuid4() if revision_id is None else revision_id
    if reader_id == "smiles" and any(
        record.source_revision_id != revision_id
        for record in parsed_batch.molecular_records
    ):
        raise ValueError("SMILES entities must use the authoritative source revision")
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
        display_name=source.display_name,
        source_kind=source.source_kind,
        created_at_utc=datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    )
    revision = SourceRevision(
        id=revision_id,
        source_id=source.id,
        content_hash=content_hash,
        byte_size=byte_size,
        locator=("inline:smiles" if source.text is not None else str(source.path)),
        locator_kind=("inline_text" if source.text is not None else "absolute_path"),
        original_filename=("inline.smi" if source.text is not None else source.path.name),
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


def _validate_supplied_identity(
    batch,
    *,
    source,
    content_hash,
    byte_size,
    plugin_id,
    reader_id,
    reader_version,
    api_version,
    parameters_hash,
    parse_identity,
    revision_id,
):
    if len(batch.sources) != 1 or len(batch.source_revisions) != 1:
        raise ValueError(
            "reader result must contain exactly one source and source revision"
        )
    source_record = batch.sources[0]
    revision = batch.source_revisions[0]
    created_entity_ids = tuple(
        entity.id
        for name in _ENTITY_GROUPS
        for entity in getattr(batch, name)
    )
    expected = {
        "source display name": (
            source_record.display_name,
            source.display_name,
        ),
        "source kind": (source_record.source_kind, source.source_kind),
        "revision source id": (revision.source_id, source_record.id),
        "content hash": (revision.content_hash, content_hash),
        "byte size": (revision.byte_size, byte_size),
        "locator": (revision.locator, "inline:smiles" if source.text is not None else str(source.path)),
        "locator kind": (revision.locator_kind, "inline_text" if source.text is not None else "absolute_path"),
        "original filename": (revision.original_filename, "inline.smi" if source.text is not None else source.path.name),
        "reader plugin id": (revision.reader_plugin_id, plugin_id),
        "reader id": (revision.reader_id, reader_id),
        "reader version": (revision.reader_version, reader_version),
        "reader API version": (revision.reader_api_version, api_version),
        "import parameters hash": (
            revision.import_parameters_hash,
            parameters_hash,
        ),
        "parse identity": (revision.parse_identity, parse_identity),
        "created entity IDs": (
            revision.created_entity_ids,
            created_entity_ids,
        ),
        "diagnostic IDs": (
            revision.diagnostic_ids,
            tuple(item.id for item in batch.diagnostics),
        ),
    }
    if revision_id is not None:
        expected["revision id"] = (revision.id, revision_id)
    for name, (actual, wanted) in expected.items():
        if actual != wanted:
            raise ValueError(f"reader result {name} does not match import source")
