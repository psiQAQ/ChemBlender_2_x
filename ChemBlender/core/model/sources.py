import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from .common import (
    _ID_PATTERN,
    _require_text,
    _require_token,
    _require_uuid,
    _require_uuid_tuple,
)


def source_parse_identity(
    content_hash, reader_plugin_id, reader_id, reader_version, parameters
):
    _require_text(content_hash, "content_hash")
    if len(content_hash) != 64 or any(
        character not in "0123456789abcdef" for character in content_hash
    ):
        raise ValueError("content_hash must be SHA-256 hex")
    _require_token(reader_plugin_id, "reader_plugin_id", _ID_PATTERN)
    _require_token(reader_id, "reader_id", _ID_PATTERN)
    _require_text(reader_version, "reader_version")
    parameters = _canonical_parameter_pairs(parameters)
    encoded = json.dumps(
        {
            "content_hash": content_hash,
            "parameters": parameters,
            "plugin_id": reader_plugin_id,
            "reader_id": reader_id,
            "reader_version": reader_version,
        },
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceRecord:
    id: UUID
    display_name: str
    source_kind: str
    created_at_utc: str

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.display_name, "display_name")
        _require_token(self.source_kind, "source_kind")
        _require_text(self.created_at_utc, "created_at_utc")


@dataclass(frozen=True, slots=True)
class SourceRevision:
    id: UUID
    source_id: UUID
    content_hash: str
    byte_size: int
    locator: str
    locator_kind: str
    original_filename: str
    reader_plugin_id: str
    reader_id: str
    reader_version: str
    reader_api_version: str
    import_parameters_hash: str
    parse_identity: str
    created_entity_ids: tuple[UUID, ...]
    diagnostic_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_uuid(self.source_id, "source_id")
        for name in ("content_hash", "import_parameters_hash", "parse_identity"):
            value = getattr(self, name)
            _require_text(value, name)
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError(f"{name} must be SHA-256 hex")
        if (
            isinstance(self.byte_size, bool)
            or not isinstance(self.byte_size, int)
            or self.byte_size < 0
        ):
            raise ValueError("byte_size must be a non-negative integer")
        for name in (
            "locator",
            "original_filename",
            "reader_version",
            "reader_api_version",
        ):
            _require_text(getattr(self, name), name)
        _require_token(self.locator_kind, "locator_kind")
        _require_token(self.reader_plugin_id, "reader_plugin_id", _ID_PATTERN)
        _require_token(self.reader_id, "reader_id", _ID_PATTERN)
        object.__setattr__(
            self,
            "created_entity_ids",
            _require_uuid_tuple(self.created_entity_ids, "created_entity_ids"),
        )
        object.__setattr__(
            self,
            "diagnostic_ids",
            _require_uuid_tuple(self.diagnostic_ids, "diagnostic_ids"),
        )


def _canonical_parameter_pairs(parameters):
    parameters = tuple(parameters)
    if any(not isinstance(item, tuple) or len(item) != 2 for item in parameters):
        raise ValueError("parameters must contain key-value tuples")
    for key, _ in parameters:
        _require_text(key, "parameter key")
    if len({key for key, _ in parameters}) != len(parameters):
        raise ValueError("parameters must not repeat keys")
    return tuple(sorted(parameters, key=lambda item: item[0]))
