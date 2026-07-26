import json
from dataclasses import dataclass, field
from uuid import NAMESPACE_URL, UUID, uuid5

from .common import _require_uuid


def _uuid_tuple(values, name, *, minimum):
    if type(values) is not tuple:
        raise TypeError(f"{name} must be a tuple")
    if any(type(value) is not UUID for value in values):
        raise TypeError(f"{name} must contain UUID values")
    values = tuple(sorted(values, key=str))
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must contain unique UUID values")
    if len(values) < minimum:
        raise ValueError(
            f"{name} must contain at least {minimum} values"
        )
    return values


@dataclass(frozen=True, slots=True)
class CalculationGroup:
    suggestion_id: UUID
    source_revision_ids: tuple[UUID, ...]
    evidence_ids: tuple[UUID, ...]
    confirmed_by: str = "user"
    id: UUID = field(init=False)

    def __post_init__(self):
        _require_uuid(self.suggestion_id, "suggestion_id")
        source_revision_ids = _uuid_tuple(
            self.source_revision_ids,
            "source_revision_ids",
            minimum=2,
        )
        evidence_ids = _uuid_tuple(
            self.evidence_ids,
            "evidence_ids",
            minimum=1,
        )
        if self.confirmed_by != "user":
            raise ValueError("confirmed_by must be 'user'")
        object.__setattr__(self, "source_revision_ids", source_revision_ids)
        object.__setattr__(self, "evidence_ids", evidence_ids)
        payload = json.dumps(
            {
                "confirmed_by": self.confirmed_by,
                "evidence_ids": tuple(map(str, evidence_ids)),
                "source_revision_ids": tuple(map(str, source_revision_ids)),
                "suggestion_id": str(self.suggestion_id),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        object.__setattr__(
            self,
            "id",
            uuid5(
                NAMESPACE_URL,
                f"chemblender:calculation-group:v1:{payload}",
            ),
        )
