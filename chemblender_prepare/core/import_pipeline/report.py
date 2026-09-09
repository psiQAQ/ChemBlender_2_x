from cbq_core.diagnostics_report import (
    SCHEMA_NAME,
    SCHEMA_VERSION,
    _DIAGNOSTIC_FIELDS,
    _QUALITY_STATUSES,
    _QUALITY_NAMES,
    _SEVERITY_ORDER,
    _MARKDOWN_SYNTAX,
    _counts,
    _validated_document,
    _uuid_text,
    _validate_counts,
    _validate_summary_rows,
    _required_text,
    _optional_text,
    _validate_document,
    _cell,
    render_diagnostics_markdown
)
import html
import json
import ntpath
from uuid import UUID

from cbq_core.model import DiagnosticSeverity
from cbq_core.model import ImportBatch
from cbq_core.model import ImportDiagnostic
from cbq_core.model import QualityStatus
from cbq_core.model import SourceRecord
from cbq_core.model import SourceRevision
from chemblender_prepare.core.readers import READER_API_VERSION
from chemblender_prepare.core.import_pipeline.preview import ImportPreview
from chemblender_prepare.core.import_pipeline.staging import StagedImportSession




def _path_key(value):
    return ntpath.normcase(ntpath.normpath(str(value).replace("/", "\\")))


def _live_diagnostics(preview, session):
    if type(preview) is not ImportPreview:
        raise TypeError("preview must be an ImportPreview")
    if type(session) is not StagedImportSession:
        raise TypeError("staged_session must be a StagedImportSession")
    if preview.session_id != session.id:
        raise ValueError("preview session does not match staged session")

    used_batch_ids = []
    diagnostic_ids = []
    diagnostics = []
    for source_preview in preview.source_previews:
        if len(source_preview.staged_batch_ids) != 1:
            raise ValueError("each source preview must have exactly one staged batch")
        batch_id = source_preview.staged_batch_ids[0]
        used_batch_ids.append(batch_id)
        try:
            batch = session.result(batch_id)
        except KeyError as error:
            raise ValueError("preview references an unknown staged batch") from error
        if (
            type(batch) is not ImportBatch
            or len(batch.sources) != 1
            or len(batch.source_revisions) != 1
            or type(batch.sources[0]) is not SourceRecord
            or type(batch.source_revisions[0]) is not SourceRevision
        ):
            raise ValueError(
                "staged batch must contain exactly one source and revision"
            )
        source = batch.sources[0]
        revision = batch.source_revisions[0]
        if source_preview.selected_reader_id is None:
            if (
                revision.reader_plugin_id != "chemblender.preflight"
                or revision.reader_version != "0"
                or revision.reader_api_version != READER_API_VERSION
                or not batch.diagnostics
                or any(
                    type(item) is not ImportDiagnostic
                    or not item.code.startswith("preflight.")
                    for item in batch.diagnostics
                )
            ):
                raise ValueError(
                    "missing selected reader requires preflight failure provenance"
                )
        locator_matches = (
            (
                revision.locator_kind == "absolute_path"
                and _path_key(revision.locator)
                == _path_key(source_preview.source_path)
            )
            or (
                revision.locator_kind == "inline_text"
                and source.source_kind == "text"
                and revision.locator == "inline:smiles"
                and source_preview.source_path
                == session.artifact_root / f"{source.id}.smi"
            )
        )
        if (
            source.id != source_preview.source_id
            or revision.source_id != source.id
            or revision.content_hash != source_preview.content_hash
            or (
                source_preview.selected_reader_id is not None
                and revision.reader_id != source_preview.selected_reader_id
            )
            or revision.byte_size != source_preview.byte_size
            or not locator_matches
        ):
            raise ValueError("staged source and revision do not match source preview")

        batch_diagnostic_ids = tuple(item.id for item in batch.diagnostics)
        if batch_diagnostic_ids != source_preview.diagnostic_ids:
            raise ValueError("staged diagnostics do not match source preview")
        if revision.diagnostic_ids != batch_diagnostic_ids:
            raise ValueError("revision diagnostic references do not match staged batch")
        if any(
            type(item) is not ImportDiagnostic
            or item.source_revision_id != revision.id
            for item in batch.diagnostics
        ):
            raise ValueError(
                "diagnostic source revision does not match staged revision"
            )
        diagnostic_ids.extend(batch_diagnostic_ids)
        diagnostics.extend((source.id, item) for item in batch.diagnostics)

    if (
        len(used_batch_ids) != len(set(used_batch_ids))
        or tuple(used_batch_ids) != preview.staged_batch_ids
    ):
        raise ValueError("preview staged batch ids are duplicated or inconsistent")
    if tuple(diagnostic_ids) != preview.diagnostic_ids:
        raise ValueError("preview diagnostic ids are inconsistent")
    return tuple(diagnostics)




def _summary(diagnostics):
    overall = _counts()
    by_source = {}
    by_entity = {}
    for source_id, item in diagnostics:
        status = item.quality_status.value
        overall[status] += 1
        by_source.setdefault(source_id, _counts())[status] += 1
        if item.entity_id is not None:
            by_entity.setdefault(item.entity_id, _counts())[status] += 1
    return {
        "overall": overall,
        "by_source": [
            {"source_id": str(identifier), "counts": by_source[identifier]}
            for identifier in sorted(by_source, key=str)
        ],
        "by_entity": [
            {"entity_id": str(identifier), "counts": by_entity[identifier]}
            for identifier in sorted(by_entity, key=str)
        ],
    }


def import_summary(preview, staged_session):
    return _summary(_live_diagnostics(preview, staged_session))


def _plain_diagnostic_value(value):
    if value is None:
        return None
    tag = value[0]
    if tag == "none":
        return None
    if tag in {"bool", "int", "float", "str"}:
        return value[1]
    if tag == "sequence":
        return [_plain_diagnostic_value(item) for item in value[1]]
    if tag == "mapping":
        return {
            _plain_diagnostic_value(key): _plain_diagnostic_value(item)
            for key, item in value[1]
        }
    raise ValueError("unknown canonical diagnostic value tag")


def _diagnostic_document(source_id, item):
    return {
        "id": str(item.id),
        "severity": item.severity.value,
        "quality_status": item.quality_status.value,
        "source_revision_id": str(item.source_revision_id),
        "source_id": str(source_id),
        "record_key": item.record_key,
        "entity_id": None if item.entity_id is None else str(item.entity_id),
        "field_path": item.field_path,
        "code": item.code,
        "message": item.message,
        "original_value": None
        if item.original_value is None
        else _plain_diagnostic_value(item.original_value.value),
        "normalized_value": None
        if item.normalized_value is None
        else _plain_diagnostic_value(item.normalized_value.value),
        "recovery_action": item.recovery_action,
        "scientific_consequence": item.scientific_consequence,
        "suggested_action": item.suggested_action,
    }


def diagnostics_document(preview, staged_session):
    diagnostics = _live_diagnostics(preview, staged_session)
    diagnostics = sorted(
        diagnostics,
        key=lambda entry: (
            entry[1].severity.summary_order,
            str(entry[0]),
            entry[1].record_key or "",
            entry[1].field_path,
            entry[1].code,
            str(entry[1].id),
        ),
    )
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "session_id": str(preview.session_id),
        "staged_batch_ids": [str(identifier) for identifier in preview.staged_batch_ids],
        "summary": _summary(diagnostics),
        "diagnostics": [
            _diagnostic_document(source_id, item)
            for source_id, item in diagnostics
        ],
    }
