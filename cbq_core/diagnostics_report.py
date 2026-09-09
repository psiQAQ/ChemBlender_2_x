"""Validation and rendering of persisted import diagnostics."""
import html
import json
from uuid import UUID
from .model import DiagnosticSeverity, QualityStatus


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


def _counts():
    return {status.value: 0 for status in _QUALITY_STATUSES}


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
