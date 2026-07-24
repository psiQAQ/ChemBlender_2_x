import importlib.util
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ChemBlender.core.readers import ReaderAvailability

from .manifest import ExecutionMode, _capabilities, _extensions, _token, _version


_MODULE_ROOT_PATTERN = re.compile(r"[a-z_][a-z0-9_]*", re.ASCII)


def _probe_availability(module_name, execution_mode):
    mode = ExecutionMode(execution_mode)
    if type(module_name) is not str or not _MODULE_ROOT_PATTERN.fullmatch(module_name):
        raise ValueError("module_name must be a lowercase top-level module identifier")
    try:
        present = importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        present = False
    except Exception:
        return ReaderAvailability(
            False,
            mode,
            "dependency_probe_failed",
            "find_spec raised an exception",
        )
    if not present:
        return ReaderAvailability(False, mode, "dependency_missing", module_name)
    return ReaderAvailability(True, mode, "available", "")


@dataclass(frozen=True, slots=True)
class PublicReaderDescriptor:
    plugin_id: str
    plugin_version: str
    reader_id: str
    reader_version: str
    execution_mode: ExecutionMode
    extensions: tuple[str, ...]
    capabilities: Mapping[str, bool]
    availability: ReaderAvailability

    def __post_init__(self):
        _token(self.plugin_id, "plugin_id")
        _version(self.plugin_version, "plugin_version")
        _token(self.reader_id, "reader_id")
        _version(self.reader_version, "reader_version")
        mode = ExecutionMode(self.execution_mode)
        extensions = _extensions(list(self.extensions))
        if not isinstance(self.capabilities, Mapping):
            raise TypeError("capabilities must be a mapping")
        capabilities = dict(self.capabilities)
        for capability, available in capabilities.items():
            _capabilities([capability])
            if type(available) is not bool:
                raise TypeError("capability values must be bool")
        if type(self.availability) is not ReaderAvailability:
            raise TypeError("availability must be ReaderAvailability")
        if self.availability.execution_mode != mode:
            raise ValueError("availability execution_mode must match descriptor")
        object.__setattr__(self, "execution_mode", mode)
        object.__setattr__(self, "extensions", extensions)
        object.__setattr__(
            self,
            "capabilities",
            MappingProxyType(dict(sorted(capabilities.items()))),
        )
