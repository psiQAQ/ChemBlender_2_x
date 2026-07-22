from dataclasses import dataclass
from pathlib import Path

from ChemBlender.core import ImportBatch

from .protocol import EntityReference


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
