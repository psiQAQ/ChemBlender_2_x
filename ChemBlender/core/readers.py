import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path
from types import MappingProxyType

from .model import ImportBatch


_READER_ID_PATTERN = re.compile(r"[a-z][a-z0-9_.-]*", re.ASCII)
_CAPABILITY_PATTERN = re.compile(r"[a-z][a-z0-9_]*", re.ASCII)


class CapabilitySupport(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


class SniffMatch(IntEnum):
    NONE = 0
    POSSIBLE = 1
    PROBABLE = 2
    EXACT = 3


@dataclass(frozen=True, slots=True)
class SniffResult:
    match: SniffMatch
    evidence: str

    def __post_init__(self):
        if not isinstance(self.match, SniffMatch):
            raise TypeError("match must be a SniffMatch")
        if not isinstance(self.evidence, str) or not self.evidence:
            raise ValueError("evidence must be a non-empty string")


@dataclass(frozen=True, slots=True)
class ReaderDescriptor:
    reader_id: str
    reader_version: str
    extensions: tuple[str, ...]
    capabilities: Mapping[str, CapabilitySupport]
    priority: int
    sniff: Callable[[Path, bytes], SniffResult]
    parse: Callable[[Path], ImportBatch]

    def __post_init__(self):
        if (
            not isinstance(self.reader_id, str)
            or not _READER_ID_PATTERN.fullmatch(self.reader_id)
        ):
            raise ValueError("reader_id must be a lowercase ASCII identifier")
        if (
            not isinstance(self.reader_version, str)
            or not self.reader_version
            or not self.reader_version.isascii()
        ):
            raise ValueError("reader_version must be non-empty ASCII")

        extensions = []
        for extension in self.extensions:
            if not isinstance(extension, str) or not extension:
                raise ValueError("extensions must contain non-empty strings")
            extension = extension.lower()
            if not extension.startswith("."):
                extension = "." + extension
            if extension == ".":
                raise ValueError("extension must contain a suffix")
            if extension not in extensions:
                extensions.append(extension)

        capabilities = dict(self.capabilities)
        for capability, support in capabilities.items():
            if (
                not isinstance(capability, str)
                or not _CAPABILITY_PATTERN.fullmatch(capability)
            ):
                raise ValueError("capability must be a lower_snake_case token")
            if not isinstance(support, CapabilitySupport):
                raise TypeError("capability values must be CapabilitySupport")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an integer")
        if not callable(self.sniff) or not callable(self.parse):
            raise TypeError("sniff and parse must be callable")

        object.__setattr__(self, "extensions", tuple(extensions))
        object.__setattr__(self, "capabilities", MappingProxyType(capabilities))


class ReaderRegistry:
    def __init__(self, readers: Iterable[ReaderDescriptor] = ()):
        self._readers = {}
        for reader in readers:
            self.register(reader)

    def register(self, reader):
        if not isinstance(reader, ReaderDescriptor):
            raise TypeError("reader must be a ReaderDescriptor")
        if reader.reader_id in self._readers:
            raise ValueError(f"duplicate reader_id: {reader.reader_id}")
        self._readers[reader.reader_id] = reader
