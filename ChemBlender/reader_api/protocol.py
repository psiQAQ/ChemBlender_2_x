import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from ..core.readers import SniffResult
from .descriptors import PublicReaderDescriptor
from .manifest import ReaderPluginManifest
from .public_model import PublicImportBatch


_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*", re.ASCII)
_PARAMETER = re.compile(r"[a-z][a-z0-9_.-]*", re.ASCII)
_VALIDATION_MODES = frozenset({"strict", "balanced", "maximum"})
_SNIFF_PREFIX_BYTES = 65536


@dataclass(frozen=True, slots=True)
class SniffRequest:
    source_path: Path
    prefix: bytes

    def __post_init__(self):
        if not isinstance(self.source_path, Path):
            raise TypeError("source_path must be a Path")
        source_path = self.source_path.resolve(strict=True)
        if not source_path.is_file():
            raise ValueError("source_path must be a file")
        if type(self.prefix) is not bytes:
            raise TypeError("prefix must be bytes")
        if len(self.prefix) > _SNIFF_PREFIX_BYTES:
            raise ValueError("prefix exceeds the sniff byte limit")
        object.__setattr__(self, "source_path", source_path)


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    stage: str
    completed: int
    total: int
    message: str = ""

    def __post_init__(self):
        if type(self.stage) is not str or not _TOKEN.fullmatch(self.stage):
            raise ValueError("stage must be a stable lowercase token")
        if (
            type(self.completed) is not int
            or type(self.total) is not int
            or self.completed < 0
            or self.total < 0
            or self.completed > self.total
        ):
            raise ValueError("progress counts must satisfy 0 <= completed <= total")
        if type(self.message) is not str:
            raise TypeError("message must be a string")


@dataclass(frozen=True, slots=True)
class ParseRequest:
    source_path: Path
    source_content_hash: str
    validation_mode: str
    canonical_parameters: Mapping[str, str]
    staging_root: Path
    progress: Callable[[ProgressEvent], None]
    is_cancelled: Callable[[], bool]
    source_revision_id: UUID = field(default_factory=uuid4)

    def __post_init__(self):
        if not isinstance(self.source_path, Path):
            raise TypeError("source_path must be a Path")
        source_path = self.source_path.resolve(strict=True)
        if not source_path.is_file():
            raise ValueError("source_path must be a file")
        if (
            type(self.source_content_hash) is not str
            or not _SHA256.fullmatch(self.source_content_hash)
        ):
            raise ValueError("source_content_hash must be lowercase SHA-256")
        if (
            type(self.validation_mode) is not str
            or self.validation_mode not in _VALIDATION_MODES
        ):
            raise ValueError("validation_mode must be strict, balanced or maximum")
        if not isinstance(self.canonical_parameters, Mapping):
            raise TypeError("canonical_parameters must be a mapping")
        parameters = dict(self.canonical_parameters)
        if any(
            type(key) is not str
            or not _PARAMETER.fullmatch(key)
            or type(value) is not str
            for key, value in parameters.items()
        ):
            raise TypeError(
                "canonical_parameters must map stable string keys to strings"
            )
        if not isinstance(self.staging_root, Path):
            raise TypeError("staging_root must be a Path")
        staging_root = self.staging_root.resolve(strict=True)
        if not staging_root.is_dir():
            raise ValueError("staging_root must be a directory")
        if not callable(self.progress) or not callable(self.is_cancelled):
            raise TypeError("progress and is_cancelled must be callable")
        if type(self.source_revision_id) is not UUID:
            raise TypeError("source_revision_id must be a UUID")
        object.__setattr__(self, "source_path", source_path)
        object.__setattr__(self, "staging_root", staging_root)
        object.__setattr__(
            self,
            "canonical_parameters",
            MappingProxyType(dict(sorted(parameters.items()))),
        )


@runtime_checkable
class ReaderPlugin(Protocol):
    manifest: ReaderPluginManifest
    descriptor: PublicReaderDescriptor
    priority: int

    def sniff(self, request: SniffRequest) -> SniffResult: ...

    def parse(self, request: ParseRequest) -> PublicImportBatch: ...
