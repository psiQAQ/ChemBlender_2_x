from dataclasses import dataclass
from enum import Enum
from math import isfinite
from uuid import UUID

from .arrays import ArrayData
from .common import _require_text, _require_token, _require_uuid, _require_uuid_tuple
from .quality import QualityStatus


class TopologySource(str, Enum):
    EXPLICIT_FILE = "explicit_file"
    RDKIT_SANITIZED = "rdkit_sanitized"
    DISTANCE_INFERRED = "distance_inferred"
    USER_EDITED = "user_edited"


def _canonical_parameter_value(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not isfinite(value):
            raise ValueError("inference_parameters values must be finite")
        return value
    if type(value) is tuple:
        return tuple(_canonical_parameter_value(item) for item in value)
    raise TypeError("inference_parameters values must be immutable canonical values")


@dataclass(frozen=True, slots=True)
class TopologyRecord:
    id: UUID
    revision: str
    structure_id: UUID
    bond_indices: ArrayData
    bond_orders: ArrayData
    aromatic_flags: ArrayData | None
    stereo_labels: tuple[str, ...]
    source_kind: TopologySource
    quality_status: QualityStatus
    inference_parameters: tuple[tuple[str, object], ...]
    provenance_ids: tuple[UUID, ...]
    bond_lattice_shifts: ArrayData | None = None

    def __post_init__(self):
        import numpy

        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_uuid(self.structure_id, "structure_id")
        if not isinstance(self.bond_indices, ArrayData):
            raise TypeError("bond_indices must be ArrayData")
        indices = numpy.asarray(self.bond_indices.values)
        if (
            self.bond_indices.dims != ("bond", "endpoint")
            or len(self.bond_indices.shape) != 2
            or self.bond_indices.shape[1] != 2
            or self.bond_indices.unit != "dimensionless"
            or indices.dtype.kind not in "iu"
            or numpy.any(indices < 0)
        ):
            raise ValueError("bond_indices must contain non-negative integer pairs")
        bond_count = self.bond_indices.shape[0]
        if not isinstance(self.bond_orders, ArrayData):
            raise TypeError("bond_orders must be ArrayData")
        orders = numpy.asarray(self.bond_orders.values)
        if (
            self.bond_orders.dims != ("bond",)
            or self.bond_orders.shape != (bond_count,)
            or self.bond_orders.unit != "dimensionless"
            or orders.dtype.kind not in "iuf"
            or not numpy.all(numpy.isfinite(orders))
            or numpy.any(orders < 0.0)
        ):
            raise ValueError(
                "bond_orders must contain one non-negative value per bond"
            )
        if self.aromatic_flags is not None:
            if not isinstance(self.aromatic_flags, ArrayData):
                raise TypeError("aromatic_flags must be ArrayData or None")
            flags = numpy.asarray(self.aromatic_flags.values)
            if (
                self.aromatic_flags.dims != ("bond",)
                or self.aromatic_flags.shape != (bond_count,)
                or self.aromatic_flags.unit != "dimensionless"
                or flags.dtype.kind != "b"
            ):
                raise ValueError(
                    "aromatic_flags must contain one bool value per bond"
                )
        if self.bond_lattice_shifts is not None:
            if not isinstance(self.bond_lattice_shifts, ArrayData):
                raise TypeError("bond_lattice_shifts must be ArrayData or None")
            shifts = numpy.asarray(self.bond_lattice_shifts.values)
            if (
                self.bond_lattice_shifts.dims != ("bond", "xyz")
                or self.bond_lattice_shifts.shape != (bond_count, 3)
                or self.bond_lattice_shifts.unit != "dimensionless"
                or shifts.dtype.kind not in "iu"
            ):
                raise ValueError(
                    "bond_lattice_shifts must contain one integer xyz shift per bond"
                )
        labels = tuple(self.stereo_labels)
        if len(labels) != bond_count or any(
            not isinstance(label, str) for label in labels
        ):
            raise ValueError(
                "stereo_labels must contain one string value per bond"
            )
        if not isinstance(self.source_kind, TopologySource):
            raise TypeError("source_kind must be a TopologySource")
        if not isinstance(self.quality_status, QualityStatus):
            raise TypeError("quality_status must be a QualityStatus")
        parameters = tuple(self.inference_parameters)
        if any(
            type(item) is not tuple or len(item) != 2
            for item in parameters
        ):
            raise ValueError("inference_parameters must contain key-value tuples")
        normalized = []
        for key, value in parameters:
            try:
                _require_token(key, "inference_parameters key")
                normalized.append((key, _canonical_parameter_value(value)))
            except (TypeError, ValueError) as error:
                raise type(error)(f"inference_parameters: {error}") from error
        if len({key for key, _value in normalized}) != len(normalized):
            raise ValueError("inference_parameters must not repeat keys")
        normalized = tuple(sorted(normalized, key=lambda item: item[0]))
        if (
            self.source_kind is TopologySource.DISTANCE_INFERRED
            and not normalized
        ):
            raise ValueError(
                "inference_parameters are required for distance_inferred topology"
            )
        object.__setattr__(self, "stereo_labels", labels)
        object.__setattr__(self, "inference_parameters", normalized)
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )
