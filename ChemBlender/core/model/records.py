from dataclasses import dataclass
from uuid import UUID

from .arrays import ArrayData
from .categorical import CategoricalData
from .common import DatasetStatus, _require_text, _require_uuid, _require_uuid_tuple
from .properties import PropertyDataset


@dataclass(frozen=True, slots=True)
class RawRecordProperty:
    name: str
    value: str

    def __post_init__(self):
        if not isinstance(self.name, str) or not isinstance(self.value, str):
            raise TypeError("raw record property name and value must be strings")


@dataclass(frozen=True, slots=True)
class MolecularRecord:
    id: UUID
    revision: str
    source_revision_id: UUID
    record_key: str
    structure_id: UUID
    topology_id: UUID | None
    raw_block: bytes
    title: str
    source_record_index: int
    block_version: str | None
    writer_name: str | None
    writer_version: str | None
    ordered_raw_properties: tuple[RawRecordProperty, ...]
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_uuid(self.source_revision_id, "source_revision_id")
        _require_text(self.record_key, "record_key")
        _require_uuid(self.structure_id, "structure_id")
        if self.topology_id is not None:
            _require_uuid(self.topology_id, "topology_id")
        if not isinstance(self.raw_block, bytes):
            raise TypeError("raw_block must be bytes")
        if not isinstance(self.title, str):
            raise TypeError("title must be a string")
        if isinstance(self.source_record_index, bool) or not isinstance(
            self.source_record_index, int
        ):
            raise TypeError("source_record_index must be an integer")
        if self.source_record_index < 0:
            raise ValueError("source_record_index must be non-negative")
        for value, name in (
            (self.block_version, "block_version"),
            (self.writer_name, "writer_name"),
            (self.writer_version, "writer_version"),
        ):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string or None")
        properties = tuple(self.ordered_raw_properties)
        if any(type(item) is not RawRecordProperty for item in properties):
            raise TypeError("ordered_raw_properties must contain RawRecordProperty values")
        object.__setattr__(self, "ordered_raw_properties", properties)
        object.__setattr__(self, "provenance_ids", _require_uuid_tuple(self.provenance_ids, "provenance_ids"))


def _record_mask(data, mask):
    import numpy

    if (
        not isinstance(mask, ArrayData)
        or mask.dims != ("record",)
        or mask.shape != (data.shape[0],)
        or mask.unit != "dimensionless"
        or numpy.dtype(mask.dtype) != numpy.dtype(numpy.bool_)
    ):
        raise ValueError("validity mask must be a matching dimensionless boolean record array")


@dataclass(frozen=True, slots=True)
class RecordPropertyColumn(PropertyDataset):
    record_ids: tuple[UUID, ...]
    validity_mask: ArrayData | None = None

    def __post_init__(self):
        import numpy

        super(RecordPropertyColumn, self).__post_init__()
        if self.domain != "record" or not self.data.dims or self.data.dims[0] != "record":
            raise ValueError("RecordPropertyColumn must use record domain and leading record dimension")
        record_ids = _require_uuid_tuple(self.record_ids, "record_ids")
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("record_ids must be unique")
        if len(record_ids) != self.data.shape[0]:
            raise ValueError("record_ids must match the record dimension")
        if isinstance(self.data, CategoricalData):
            if self.validity_mask is not None:
                raise ValueError("CategoricalData uses missing_code, not a validity mask")
            if self.status is DatasetStatus.COMPLETE and numpy.any(
                numpy.asarray(self.data.codes.values) == self.data.missing_code
            ):
                raise ValueError("Complete categorical property must not contain missing codes")
        else:
            numeric_or_logical = numpy.dtype(self.data.dtype).kind in "biufc"
            if self.status is DatasetStatus.COMPLETE and self.validity_mask is not None:
                raise ValueError("Complete record property must not use a validity mask")
            if self.status is DatasetStatus.PARTIAL and numeric_or_logical and self.validity_mask is None:
                raise ValueError("Partial numeric or logical property requires a validity mask")
            if self.validity_mask is not None:
                _record_mask(self.data, self.validity_mask)
        object.__setattr__(self, "record_ids", record_ids)


@dataclass(frozen=True, slots=True)
class ConformerSet(PropertyDataset):
    reference_structure_id: UUID
    reference_topology_id: UUID | None
    record_ids: tuple[UUID, ...]
    record_keys: tuple[str, ...]
    atom_mappings: ArrayData

    def __post_init__(self):
        import numpy

        super(ConformerSet, self).__post_init__()
        _require_uuid(self.reference_structure_id, "reference_structure_id")
        if self.reference_topology_id is not None:
            _require_uuid(self.reference_topology_id, "reference_topology_id")
        if not isinstance(self.data, ArrayData):
            raise TypeError("ConformerSet data must be ArrayData")
        if (
            self.domain != "conformer"
            or self.data.dims != ("conformer", "atom", "xyz")
            or any(size <= 0 for size in self.data.shape)
            or self.data.shape[2] != 3
            or self.data.unit in {"dimensionless", "unknown"}
        ):
            raise ValueError("ConformerSet must use positive conformer, atom and xyz coordinates")
        if not isinstance(self.atom_mappings, ArrayData):
            raise TypeError("atom_mappings must be ArrayData")
        mappings = numpy.asarray(self.atom_mappings.values)
        if (
            self.atom_mappings.dims != ("conformer", "atom")
            or self.atom_mappings.shape != self.data.shape[:2]
            or self.atom_mappings.unit != "dimensionless"
            or mappings.dtype.kind not in "iu"
            or mappings.dtype.kind == "b"
        ):
            raise ValueError("atom_mappings must be integer conformer atom mappings")
        atom_count = self.data.shape[1]
        if any(sorted(row.tolist()) != list(range(atom_count)) for row in mappings):
            raise ValueError("each atom mapping must be a permutation")
        record_ids = _require_uuid_tuple(self.record_ids, "record_ids")
        record_keys = tuple(self.record_keys)
        if (
            len(record_ids) != self.data.shape[0]
            or len(record_ids) != len(set(record_ids))
            or len(record_keys) != self.data.shape[0]
            or len(record_keys) != len(set(record_keys))
            or any(not isinstance(key, str) or not key for key in record_keys)
        ):
            raise ValueError("conformer record IDs and keys must be unique and match conformer count")
        object.__setattr__(self, "record_ids", record_ids)
        object.__setattr__(self, "record_keys", record_keys)
