import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


_TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9_.-]*")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _require_uuid(value, name):
    if type(value) is not UUID:
        raise TypeError(f"{name} must be a UUID")


def _require_uuid_tuple(values, name):
    if type(values) is not tuple:
        raise TypeError(f"{name} must be a tuple")
    if any(type(value) is not UUID for value in values):
        raise TypeError(f"{name} must contain UUID values")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must contain unique UUID values")


def _require_token(value, name):
    if type(value) is not str or not _TOKEN_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be a stable lowercase token")


@dataclass(frozen=True, slots=True)
class SourcePreview:
    source_id: UUID
    source_path: Path
    selected_reader_id: str | None = None
    content_hash: str | None = None
    byte_size: int | None = None
    capabilities: tuple[str, ...] = ()
    staged_batch_ids: tuple[UUID, ...] = ()
    diagnostic_ids: tuple[UUID, ...] = ()

    def __post_init__(self):
        _require_uuid(self.source_id, "source_id")
        if not isinstance(self.source_path, Path):
            raise TypeError("source_path must be a Path")
        if not self.source_path.is_absolute():
            raise ValueError("source_path must be absolute")
        object.__setattr__(
            self,
            "source_path",
            self.source_path.resolve(strict=False),
        )
        if self.selected_reader_id is not None:
            _require_token(self.selected_reader_id, "selected_reader_id")
        if self.content_hash is not None and (
            type(self.content_hash) is not str
            or not _SHA256_PATTERN.fullmatch(self.content_hash)
        ):
            raise ValueError("content_hash must be lowercase SHA-256 hex or None")
        if self.byte_size is not None and (
            type(self.byte_size) is not int or self.byte_size < 0
        ):
            raise ValueError("byte_size must be a non-negative integer or None")
        if type(self.capabilities) is not tuple:
            raise TypeError("capabilities must be a tuple")
        for capability in self.capabilities:
            _require_token(capability, "capability")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("capabilities must be unique")
        _require_uuid_tuple(self.staged_batch_ids, "staged_batch_ids")
        _require_uuid_tuple(self.diagnostic_ids, "diagnostic_ids")


@dataclass(frozen=True, slots=True)
class ImportPreview:
    session_id: UUID
    source_previews: tuple[SourcePreview, ...]
    staged_batch_ids: tuple[UUID, ...] = ()
    conflict_ids: tuple[UUID, ...] = ()
    grouping_suggestion_ids: tuple[UUID, ...] = ()
    diagnostic_ids: tuple[UUID, ...] = ()
    default_view_plan_ids: tuple[UUID, ...] = ()

    def __post_init__(self):
        _require_uuid(self.session_id, "session_id")
        if type(self.source_previews) is not tuple:
            raise TypeError("source_previews must be a tuple")
        if any(
            type(source_preview) is not SourcePreview
            for source_preview in self.source_previews
        ):
            raise TypeError("source_previews must contain SourcePreview values")
        source_ids = tuple(
            source_preview.source_id for source_preview in self.source_previews
        )
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source previews must have unique source ids")
        for name in (
            "staged_batch_ids",
            "conflict_ids",
            "grouping_suggestion_ids",
            "diagnostic_ids",
            "default_view_plan_ids",
        ):
            _require_uuid_tuple(getattr(self, name), name)
