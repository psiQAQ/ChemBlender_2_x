import html
import json
import ntpath
from uuid import UUID

from ..model import (
    DiagnosticSeverity,
    ImportBatch,
    ImportDiagnostic,
    QualityStatus,
    SourceRecord,
    SourceRevision,
)
from .preview import ImportPreview
from .staging import StagedImportSession


SCHEMA_NAME = "chemblender_import_report"
SCHEMA_VERSION = 1
_DIAGNOSTIC_FIELDS = {
    "id",
    "severity",
    "quality_status",
    "source_revision_id",
    "source_id",
    "record_key",
    "entity_id",
    "field_path",
    "code",
    "message",
    "original_value",
    "normalized_value",
    "recovery_action",
    "scientific_consequence",
    "suggested_action",
}
_QUALITY_STATUSES = tuple(
    sorted(QualityStatus, key=lambda status: status.summary_order)
)
_QUALITY_NAMES = tuple(status.value for status in _QUALITY_STATUSES)
_SEVERITY_ORDER = {
    severity.value: severity.summary_order for severity in DiagnosticSeverity
}
_MARKDOWN_SYNTAX = frozenset("`*_[]()!~|")


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
                or revision.reader_api_version != "0.1"
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
        if (
            source.id != source_preview.source_id
            or revision.source_id != source.id
            or revision.content_hash != source_preview.content_hash
            or (
                source_preview.selected_reader_id is not None
                and revision.reader_id != source_preview.selected_reader_id
            )
            or revision.byte_size != source_preview.byte_size
            or revision.locator_kind != "absolute_path"
            or _path_key(revision.locator) != _path_key(source_preview.source_path)
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


def _counts():
    return {status.value: 0 for status in _QUALITY_STATUSES}


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


def _validated_document(document):
    try:
        normalized = json.loads(
            json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        _validate_document(normalized)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid diagnostics document") from error
    return normalized


def _uuid_text(value):
    if type(value) is not str:
        raise ValueError("UUID values must be strings")
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise ValueError("invalid UUID") from error
    if str(parsed) != value:
        raise ValueError("UUID values must use canonical text")
    return value


def _validate_counts(counts):
    if type(counts) is not dict or set(counts) != set(_QUALITY_NAMES):
        raise ValueError("invalid quality counts")
    if any(type(counts[name]) is not int or counts[name] < 0 for name in counts):
        raise ValueError("quality counts must be non-negative integers")


def _validate_summary_rows(rows, id_name):
    if type(rows) is not list:
        raise ValueError("summary rows must be a list")
    identifiers = []
    for row in rows:
        if type(row) is not dict or set(row) != {id_name, "counts"}:
            raise ValueError("invalid summary row")
        identifiers.append(_uuid_text(row[id_name]))
        _validate_counts(row["counts"])
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("summary row identifiers must be unique")
    if identifiers != sorted(identifiers):
        raise ValueError("summary rows must use canonical order")


def _required_text(value):
    return type(value) is str and bool(value)


def _optional_text(value):
    return value is None or _required_text(value)


def _validate_document(document):
    if type(document) is not dict or set(document) != {
        "schema_name",
        "schema_version",
        "session_id",
        "staged_batch_ids",
        "summary",
        "diagnostics",
    }:
        raise ValueError("invalid document fields")
    if document["schema_name"] != SCHEMA_NAME:
        raise ValueError("invalid schema name")
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != SCHEMA_VERSION
    ):
        raise ValueError("invalid schema version")
    _uuid_text(document["session_id"])
    batch_ids = document["staged_batch_ids"]
    if type(batch_ids) is not list:
        raise ValueError("staged_batch_ids must be a list")
    batch_ids = [_uuid_text(value) for value in batch_ids]
    if len(batch_ids) != len(set(batch_ids)):
        raise ValueError("staged_batch_ids must be unique")

    summary = document["summary"]
    if type(summary) is not dict or set(summary) != {
        "overall",
        "by_source",
        "by_entity",
    }:
        raise ValueError("invalid summary")
    _validate_counts(summary["overall"])
    _validate_summary_rows(summary["by_source"], "source_id")
    _validate_summary_rows(summary["by_entity"], "entity_id")

    diagnostics = document["diagnostics"]
    if type(diagnostics) is not list:
        raise ValueError("diagnostics must be a list")
    diagnostic_ids = []
    revision_sources = {}
    source_revisions = {}
    for item in diagnostics:
        if type(item) is not dict or set(item) != _DIAGNOSTIC_FIELDS:
            raise ValueError("invalid diagnostic fields")
        diagnostic_ids.append(_uuid_text(item["id"]))
        source_id = _uuid_text(item["source_id"])
        revision_id = _uuid_text(item["source_revision_id"])
        entity_id = item["entity_id"]
        if entity_id is not None:
            _uuid_text(entity_id)
        if item["severity"] not in _SEVERITY_ORDER:
            raise ValueError("invalid diagnostic severity")
        if item["quality_status"] not in _QUALITY_NAMES:
            raise ValueError("invalid diagnostic quality status")
        if not _optional_text(item["record_key"]):
            raise ValueError("invalid diagnostic record_key")
        for name in (
            "field_path",
            "code",
            "message",
            "scientific_consequence",
        ):
            if not _required_text(item[name]):
                raise ValueError(f"invalid diagnostic {name}")
        for name in ("recovery_action", "suggested_action"):
            if not _optional_text(item[name]):
                raise ValueError(f"invalid diagnostic {name}")
        existing_source = revision_sources.setdefault(revision_id, source_id)
        if existing_source != source_id:
            raise ValueError("source revision maps to multiple sources")
        existing_revision = source_revisions.setdefault(source_id, revision_id)
        if existing_revision != revision_id:
            raise ValueError("source maps to multiple revisions")
    if len(diagnostic_ids) != len(set(diagnostic_ids)):
        raise ValueError("diagnostic identifiers must be unique")

    expected = {
        "overall": _counts(),
        "by_source": {},
        "by_entity": {},
    }
    for item in diagnostics:
        status = item["quality_status"]
        expected["overall"][status] += 1
        expected["by_source"].setdefault(item["source_id"], _counts())[status] += 1
        if item["entity_id"] is not None:
            expected["by_entity"].setdefault(item["entity_id"], _counts())[
                status
            ] += 1
    expected_sources = [
        {"source_id": identifier, "counts": expected["by_source"][identifier]}
        for identifier in sorted(expected["by_source"])
    ]
    expected_entities = [
        {"entity_id": identifier, "counts": expected["by_entity"][identifier]}
        for identifier in sorted(expected["by_entity"])
    ]
    if (
        summary["overall"] != expected["overall"]
        or summary["by_source"] != expected_sources
        or summary["by_entity"] != expected_entities
    ):
        raise ValueError("summary does not match diagnostics")
    if diagnostics != sorted(
        diagnostics,
        key=lambda item: (
            _SEVERITY_ORDER[item["severity"]],
            item["source_id"],
            item["record_key"] or "",
            item["field_path"],
            item["code"],
            item["id"],
        ),
    ):
        raise ValueError("diagnostics are not in canonical order")


def _cell(value):
    if value is None:
        return ""
    if type(value) in (dict, list):
        value = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    value = html.escape(
        str(value).replace("\r", " ").replace("\n", " "),
        quote=False,
    )
    value = value.replace("\\", "\\\\")
    return "".join(
        f"\\{character}" if character in _MARKDOWN_SYNTAX else character
        for character in value
    )


def render_diagnostics_markdown(document):
    document = _validated_document(document)
    summary = document["summary"]
    quality_headers = [status.value.title() for status in _QUALITY_STATUSES]
    lines = [
        "# ChemBlender Import Diagnostics",
        "",
        f"- Session: `{_cell(document['session_id'])}`",
        f"- Diagnostics: `{len(document['diagnostics'])}`",
        "",
        "## Quality summary",
        "",
        "| Scope | ID | " + " | ".join(quality_headers) + " |",
        "| --- | --- | " + " | ".join("---" for _ in quality_headers) + " |",
    ]

    def add_summary_row(scope, identifier, counts):
        lines.append(
            "| {} | {} | {} |".format(
                scope,
                _cell(identifier),
                " | ".join(str(counts[status.value]) for status in _QUALITY_STATUSES),
            )
        )

    add_summary_row("overall", "", summary["overall"])
    for row in summary["by_source"]:
        add_summary_row("source", row["source_id"], row["counts"])
    for row in summary["by_entity"]:
        add_summary_row("entity", row["entity_id"], row["counts"])

    lines.extend(
        [
            "",
            "## Diagnostics",
            "",
            "| Severity | Source | Source revision | Record | Entity | Field | Code | Message | Original | Normalized | Recovery | Scientific consequence | Suggested action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in document["diagnostics"]:
        lines.append(
            "| {} |".format(
                " | ".join(
                    _cell(item[name])
                    for name in (
                        "severity",
                        "source_id",
                        "source_revision_id",
                        "record_key",
                        "entity_id",
                        "field_path",
                        "code",
                        "message",
                        "original_value",
                        "normalized_value",
                        "recovery_action",
                        "scientific_consequence",
                        "suggested_action",
                    )
                )
            )
        )
    return "\n".join(lines) + "\n"
