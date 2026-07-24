import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4


_TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9_.-]*")


def _require_token(value, name):
    if type(value) is not str or not _TOKEN_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be a stable lowercase token")


class ValidationMode(str, Enum):
    STRICT = "strict"
    BALANCED = "balanced"
    MAXIMUM = "maximum"


@dataclass(frozen=True, slots=True)
class ImportSource:
    path: Path
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self):
        if not isinstance(self.path, Path):
            raise TypeError("path must be a Path")
        if type(self.id) is not UUID:
            raise TypeError("id must be a UUID")
        canonical = self.path.resolve(strict=True)
        if not canonical.is_file():
            raise ValueError("source path must be a file")
        object.__setattr__(self, "path", canonical)


@dataclass(frozen=True, slots=True)
class ReaderOverride:
    source_id: UUID
    reader_id: str

    def __post_init__(self):
        if type(self.source_id) is not UUID:
            raise TypeError("source_id must be a UUID")
        _require_token(self.reader_id, "reader_id")


@dataclass(frozen=True, slots=True)
class ImportRequest:
    sources: tuple[ImportSource, ...]
    validation_mode: ValidationMode = ValidationMode.BALANCED
    reader_overrides: tuple[ReaderOverride, ...] = ()
    duplicate_policy: str | None = None
    grouping_policy: str = "suggest"
    default_view_policy: str = "automatic"

    def __post_init__(self):
        if type(self.sources) is not tuple:
            raise TypeError("sources must be a tuple")
        if not self.sources:
            raise ValueError("sources must not be empty")
        if any(type(source) is not ImportSource for source in self.sources):
            raise TypeError("sources must contain ImportSource values")
        paths = tuple(source.path for source in self.sources)
        if len(paths) != len(set(paths)):
            raise ValueError("source paths must be canonical and unique")
        source_ids = tuple(source.id for source in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source ids must be unique")
        if type(self.validation_mode) is not ValidationMode:
            raise TypeError("validation_mode must be a ValidationMode")
        if type(self.reader_overrides) is not tuple:
            raise TypeError("reader_overrides must be a tuple")
        if any(
            type(override) is not ReaderOverride
            for override in self.reader_overrides
        ):
            raise TypeError("reader_overrides must contain ReaderOverride values")
        override_ids = tuple(
            override.source_id for override in self.reader_overrides
        )
        if any(source_id not in source_ids for source_id in override_ids):
            raise ValueError("reader override must target an included source")
        if len(override_ids) != len(set(override_ids)):
            raise ValueError("each source may have only one override")
        if self.duplicate_policy is not None:
            _require_token(self.duplicate_policy, "duplicate_policy")
        _require_token(self.grouping_policy, "grouping_policy")
        _require_token(self.default_view_policy, "default_view_policy")
