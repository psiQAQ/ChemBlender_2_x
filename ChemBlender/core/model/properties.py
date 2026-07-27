from dataclasses import dataclass
from uuid import UUID

from .arrays import ArrayData
from .categorical import CategoricalData
from .common import (
    DatasetStatus,
    _require_text,
    _require_token,
    _require_uuid,
    _require_uuid_tuple,
)


@dataclass(frozen=True, slots=True)
class PropertyDataset:
    id: UUID
    revision: str
    semantic_role: str
    domain: str
    data: ArrayData | CategoricalData
    status: DatasetStatus
    source_calculation: UUID | None
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_token(self.semantic_role, "semantic_role")
        _require_token(self.domain, "domain")
        if not isinstance(self.data, (ArrayData, CategoricalData)):
            raise TypeError("data must be ArrayData or CategoricalData")
        if not isinstance(self.status, DatasetStatus):
            raise TypeError("status must be a DatasetStatus")
        if self.data.unit == "unknown" and self.status is not DatasetStatus.AMBIGUOUS:
            raise ValueError("unknown unit requires ambiguous dataset status")
        if self.source_calculation is not None:
            _require_uuid(self.source_calculation, "source_calculation")
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class AtomicProperty(PropertyDataset):
    structure_id: UUID

    def __post_init__(self):
        super(AtomicProperty, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        if self.domain != "atom" or not self.data.dims or self.data.dims[0] != "atom":
            raise ValueError(
                "AtomicProperty must use atom domain and leading atom dimension"
            )


@dataclass(frozen=True, slots=True)
class FrameSet(PropertyDataset):
    structure_id: UUID
    comments: tuple[str, ...]

    def __post_init__(self):
        super(FrameSet, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        if self.semantic_role != "coordinates" or self.domain != "frame":
            raise ValueError("FrameSet must describe frame coordinates")
        if self.data.dims != ("frame", "atom", "xyz") or any(
            size <= 0 for size in self.data.shape
        ):
            raise ValueError(
                "FrameSet data must have positive (frame, atom, xyz) dimensions"
            )
        if self.data.shape[2] != 3:
            raise ValueError("FrameSet xyz dimension must have length 3")
        if self.data.unit in {"dimensionless", "unknown"}:
            raise ValueError(
                "FrameSet coordinate unit must be known dimensional length"
            )
        comments = tuple(self.comments)
        if len(comments) != self.data.shape[0] or any(
            not isinstance(comment, str) for comment in comments
        ):
            raise ValueError(
                "FrameSet comments must contain one string per frame"
            )
        object.__setattr__(self, "comments", comments)


def _validate_frame_property(
    value,
    *,
    domain,
    data_prefix,
    mask_prefix,
    exact_dims=False,
):
    import numpy

    _require_uuid(value.frame_set_id, "frame_set_id")
    if value.domain != domain:
        raise ValueError(f"{type(value).__name__} must use {domain} domain")
    if (
        value.data.dims != data_prefix
        if exact_dims
        else value.data.dims[: len(data_prefix)] != data_prefix
    ):
        dimensions = ", ".join(data_prefix)
        raise ValueError(
            f"{type(value).__name__} must use leading {dimensions} dimensions"
        )
    mask = value.validity_mask
    if isinstance(value.data, CategoricalData):
        if mask is not None:
            raise ValueError("CategoricalData uses missing_code, not a validity mask")
        if value.status is DatasetStatus.COMPLETE and numpy.any(
            numpy.asarray(value.data.codes.values) == value.data.missing_code
        ):
            raise ValueError(
                "Complete categorical property must not contain missing codes"
            )
        return
    if value.status is DatasetStatus.COMPLETE and mask is not None:
        raise ValueError("Complete frame property must not use a validity mask")
    numeric_or_logical = numpy.dtype(value.data.dtype).kind in "biufc"
    if value.status is DatasetStatus.PARTIAL and numeric_or_logical and mask is None:
        raise ValueError("Partial numeric or logical property requires a validity mask")
    if mask is None:
        return
    if (
        not isinstance(mask, ArrayData)
        or mask.dims != mask_prefix
        or mask.shape != value.data.shape[: len(mask_prefix)]
        or mask.unit != "dimensionless"
        or numpy.dtype(mask.dtype) != numpy.dtype(numpy.bool_)
    ):
        raise ValueError(
            "validity mask must be a matching dimensionless boolean array"
        )


@dataclass(frozen=True, slots=True)
class FrameProperty(PropertyDataset):
    frame_set_id: UUID
    validity_mask: ArrayData | None = None

    def __post_init__(self):
        super(FrameProperty, self).__post_init__()
        _validate_frame_property(
            self,
            domain="frame",
            data_prefix=("frame",),
            mask_prefix=("frame",),
        )


@dataclass(frozen=True, slots=True)
class AtomFrameProperty(PropertyDataset):
    frame_set_id: UUID
    validity_mask: ArrayData | None = None

    def __post_init__(self):
        super(AtomFrameProperty, self).__post_init__()
        _validate_frame_property(
            self,
            domain="atom_frame",
            data_prefix=("frame", "atom"),
            mask_prefix=("frame", "atom"),
        )


@dataclass(frozen=True, slots=True)
class CellFrameProperty(PropertyDataset):
    frame_set_id: UUID
    validity_mask: ArrayData | None = None

    def __post_init__(self):
        super(CellFrameProperty, self).__post_init__()
        _validate_frame_property(
            self,
            domain="cell_frame",
            data_prefix=("frame", "cell_vector", "xyz"),
            mask_prefix=("frame",),
            exact_dims=True,
        )
        if self.data.shape[1:] != (3, 3):
            raise ValueError("CellFrameProperty cells must be 3 by 3")
