import re
import tomllib
from dataclasses import dataclass
from enum import Enum

from .version import READER_API_VERSION


_ID_PATTERN = re.compile(r"[a-z][a-z0-9_.-]*", re.ASCII)
_CAPABILITY_PATTERN = re.compile(r"[a-z][a-z0-9_]*", re.ASCII)
_EXTENSION_PATTERN = re.compile(r"\.[a-z0-9][a-z0-9._+-]*", re.ASCII)
_VERSION_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)*", re.ASCII)
_API_RANGE_PATTERN = re.compile(r">=([0-9]+)\.([0-9]+),<([0-9]+)\.([0-9]+)", re.ASCII)
_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "plugin_id", "plugin_version", "chemblender_api", "execution_mode", "license", "readers"}
)
_READER_KEYS = frozenset({"reader_id", "reader_version", "extensions", "capabilities"})


class ExecutionMode(str, Enum):
    BUILT_IN = "built_in"
    EXTENSION = "extension"
    WORKER = "worker"


def _token(value, field):
    if type(value) is not str or not _ID_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a stable lowercase token")
    return value


def _version(value, field):
    if type(value) is not str or not _VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a numeric dot-separated version")
    return value


def _api_range(value):
    if type(value) is not str or not (match := _API_RANGE_PATTERN.fullmatch(value)):
        raise ValueError("chemblender_api must be >=MAJOR.MINOR,<MAJOR.MINOR")
    minimum, maximum = (int(match[1]), int(match[2])), (int(match[3]), int(match[4]))
    if minimum >= maximum:
        raise ValueError("chemblender_api range must not be empty or inverted")
    current = tuple(map(int, READER_API_VERSION.split(".")))
    if not minimum <= current < maximum:
        raise ValueError("chemblender_api range does not include this Reader API version")
    return value


def _sequence(values, field):
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError(f"{field} must be a non-empty list")
    return values


def _extensions(values):
    values = _sequence(values, "extensions")
    normalized = []
    for value in values:
        if type(value) is not str or not value:
            raise ValueError("extensions must contain non-empty strings")
        value = ("." + value.lstrip(".")).lower()
        if not _EXTENSION_PATTERN.fullmatch(value):
            raise ValueError("extension must be a normalized suffix")
        if value in normalized:
            continue
        normalized.append(value)
    return tuple(sorted(normalized))


def _capabilities(values):
    values = _sequence(values, "capabilities")
    for value in values:
        if type(value) is not str or not _CAPABILITY_PATTERN.fullmatch(value):
            raise ValueError("capabilities must contain lower_snake_case tokens")
    return tuple(sorted(set(values)))


@dataclass(frozen=True, slots=True)
class ReaderManifestEntry:
    reader_id: str
    reader_version: str
    extensions: tuple[str, ...]
    capabilities: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, "reader_id", _token(self.reader_id, "reader_id"))
        object.__setattr__(self, "reader_version", _version(self.reader_version, "reader_version"))
        object.__setattr__(self, "extensions", _extensions(self.extensions))
        object.__setattr__(self, "capabilities", _capabilities(self.capabilities))


@dataclass(frozen=True, slots=True)
class ReaderPluginManifest:
    schema_version: str
    plugin_id: str
    plugin_version: str
    chemblender_api: str
    execution_mode: ExecutionMode
    license: tuple[str, ...]
    readers: tuple[ReaderManifestEntry, ...]

    def __post_init__(self):
        if type(self.schema_version) is not str or self.schema_version != "1":
            raise ValueError("schema_version must be '1'")
        licenses = _sequence(self.license, "license")
        if any(type(item) is not str or not item or item != item.strip() for item in licenses):
            raise ValueError("license must contain non-empty strings")
        readers = _sequence(self.readers, "readers")
        if any(type(reader) is not ReaderManifestEntry for reader in readers):
            raise TypeError("readers must contain ReaderManifestEntry values")
        if len({reader.reader_id for reader in readers}) != len(readers):
            raise ValueError("reader_id values must be unique")
        try:
            execution_mode = ExecutionMode(self.execution_mode)
        except (TypeError, ValueError) as error:
            raise ValueError("execution_mode must be built_in, extension or worker") from error
        object.__setattr__(self, "plugin_id", _token(self.plugin_id, "plugin_id"))
        object.__setattr__(self, "plugin_version", _version(self.plugin_version, "plugin_version"))
        object.__setattr__(self, "chemblender_api", _api_range(self.chemblender_api))
        object.__setattr__(self, "execution_mode", execution_mode)
        object.__setattr__(self, "license", tuple(sorted(set(licenses))))
        object.__setattr__(self, "readers", tuple(sorted(readers, key=lambda reader: reader.reader_id)))

    @classmethod
    def from_toml(cls, source):
        if isinstance(source, bytes):
            source = source.decode("utf-8")
        if type(source) is not str:
            raise TypeError("TOML source must be str or UTF-8 bytes")
        data = tomllib.loads(source)
        unknown = set(data) - _TOP_LEVEL_KEYS
        if unknown:
            raise ValueError(f"unknown manifest fields: {sorted(unknown)}")
        if set(data) != _TOP_LEVEL_KEYS:
            raise ValueError("manifest has missing required fields")
        readers = data["readers"]
        if not isinstance(readers, list) or not readers:
            raise ValueError("readers must be a non-empty list")
        entries = []
        for reader in readers:
            if not isinstance(reader, dict):
                raise ValueError("reader entry must be a table")
            unknown = set(reader) - _READER_KEYS
            if unknown:
                raise ValueError(f"unknown reader fields: {sorted(unknown)}")
            if set(reader) != _READER_KEYS:
                raise ValueError("reader entry has missing required fields")
            entries.append(
                ReaderManifestEntry(
                    reader["reader_id"],
                    reader["reader_version"],
                    reader["extensions"],
                    reader["capabilities"],
                )
            )
        return cls(
            data["schema_version"],
            data["plugin_id"],
            data["plugin_version"],
            data["chemblender_api"],
            data["execution_mode"],
            data["license"],
            entries,
        )
