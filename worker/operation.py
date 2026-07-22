import re
from dataclasses import dataclass
from pathlib import Path

from ChemBlender.core import ImportBatch

from .protocol import EntityReference


_ERROR_CODE = re.compile(r"[a-z][a-z0-9_.-]*")


class OperationError(RuntimeError):
    def __init__(self, code, message):
        if not isinstance(code, str) or not _ERROR_CODE.fullmatch(code):
            raise ValueError("operation error code must be a lower token")
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class OperationOutput:
    outputs: tuple[EntityReference, ...] = ()
    artifacts: tuple[str, ...] = ()
    cache_key: str | None = None
    metadata: dict | None = None
    batch: ImportBatch | None = None


@dataclass(frozen=True, slots=True)
class OperationContext:
    project_path: Path
    project: object
    cancel_path: Path | None

    def is_cancelled(self):
        return self.cancel_path is not None and self.cancel_path.exists()
