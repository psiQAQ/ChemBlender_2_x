import operator
import re
from math import isfinite
from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID


_UNIT_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
_ID_PATTERN = re.compile(r"[a-z][a-z0-9_.-]*")


def _require_uuid(value, name):
    if not isinstance(value, UUID):
        raise TypeError(f"{name} must be a UUID")


def _require_uuid_tuple(values, name):
    values = tuple(values)
    for value in values:
        _require_uuid(value, name)
    return values


def _require_token(value, name, pattern=_UNIT_PATTERN):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{name} must be a lower_snake_case token")


def _require_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


class CalculationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class DatasetStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"


class IssueKind(str, Enum):
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ArrayData:
    values: object
    dims: tuple[str, ...]
    unit: str
    shape: tuple[int, ...] = field(init=False)
    dtype: str = field(init=False)

    def __post_init__(self):
        try:
            raw_shape = self.values.shape
        except AttributeError as error:
            raise TypeError("values must expose a shape") from error

        shape = []
        for dimension in raw_shape:
            if isinstance(dimension, bool):
                raise ValueError("array dimensions must be non-negative integers")
            try:
                size = operator.index(dimension)
            except TypeError as error:
                raise ValueError(
                    "array dimensions must be non-negative integers"
                ) from error
            if size < 0:
                raise ValueError("array dimensions must be non-negative integers")
            shape.append(size)

        dims = tuple(self.dims)
        if len(shape) != len(dims):
            raise ValueError("dims must match array rank")
        if len(set(dims)) != len(dims) or any(
            not isinstance(dim, str) or not dim for dim in dims
        ):
            raise ValueError("dims must be unique non-empty names")
        if not isinstance(self.unit, str) or not _UNIT_PATTERN.fullmatch(self.unit):
            raise ValueError("unit must be a lower_snake_case token")

        dtype = getattr(self.values, "dtype", getattr(self.values, "format", "unknown"))
        object.__setattr__(self, "dims", dims)
        object.__setattr__(self, "shape", tuple(shape))
        object.__setattr__(self, "dtype", str(dtype))


@dataclass(frozen=True, slots=True)
class Structure:
    id: UUID
    revision: str
    atomic_numbers: tuple[int, ...]
    coordinates: ArrayData
    cell: ArrayData | None = None

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        atomic_numbers = tuple(self.atomic_numbers)
        if any(
            isinstance(number, bool)
            or not isinstance(number, int)
            or not 0 <= number <= 118
            for number in atomic_numbers
        ):
            raise ValueError("atomic numbers must be integers from 0 to 118")
        if self.coordinates.dims != ("atom", "xyz") or self.coordinates.shape != (
            len(atomic_numbers),
            3,
        ):
            raise ValueError("coordinates must have dims (atom, xyz) and shape (n, 3)")
        if self.coordinates.unit in {"dimensionless", "unknown"}:
            raise ValueError("coordinate unit must be known dimensional length")
        if self.cell is not None:
            if self.cell.dims != ("cell_vector", "xyz") or self.cell.shape != (3, 3):
                raise ValueError("cell must have dims (cell_vector, xyz) and shape (3, 3)")
            if self.cell.unit != self.coordinates.unit:
                raise ValueError("cell and coordinates must use the same unit")
        object.__setattr__(self, "atomic_numbers", atomic_numbers)


@dataclass(frozen=True, slots=True)
class CalculationRecord:
    id: UUID
    revision: str
    status: CalculationStatus
    input_structure_ids: tuple[UUID, ...]
    result_structure_ids: tuple[UUID, ...]
    dataset_ids: tuple[UUID, ...]
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        if not isinstance(self.status, CalculationStatus):
            raise TypeError("status must be a CalculationStatus")
        for name in (
            "input_structure_ids",
            "result_structure_ids",
            "dataset_ids",
            "provenance_ids",
        ):
            object.__setattr__(self, name, _require_uuid_tuple(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class PropertyDataset:
    id: UUID
    revision: str
    semantic_role: str
    domain: str
    data: ArrayData
    status: DatasetStatus
    source_calculation: UUID | None
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_token(self.semantic_role, "semantic_role")
        _require_token(self.domain, "domain")
        if not isinstance(self.data, ArrayData):
            raise TypeError("data must be ArrayData")
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
class Grid3D(PropertyDataset):
    origin: tuple[float, float, float]
    step_vectors: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    coordinate_unit: str

    def __post_init__(self):
        super(Grid3D, self).__post_init__()
        if self.data.dims[-3:] != ("x", "y", "z"):
            raise ValueError("Grid3D data must end with dims (x, y, z)")
        if any(size <= 0 for size in self.grid_shape):
            raise ValueError("Grid3D spatial dimensions must be positive")
        origin = self._vector(self.origin, "origin")
        steps = tuple(self._vector(vector, "step_vector") for vector in self.step_vectors)
        if len(steps) != 3:
            raise ValueError("step_vectors must contain three vectors")
        determinant = (
            steps[0][0] * (steps[1][1] * steps[2][2] - steps[1][2] * steps[2][1])
            - steps[0][1] * (steps[1][0] * steps[2][2] - steps[1][2] * steps[2][0])
            + steps[0][2] * (steps[1][0] * steps[2][1] - steps[1][1] * steps[2][0])
        )
        if determinant == 0.0:
            raise ValueError("step_vectors must be linearly independent")
        _require_token(self.coordinate_unit, "coordinate_unit")
        if self.coordinate_unit == "dimensionless":
            raise ValueError("coordinate_unit must be dimensional length")
        if (
            self.coordinate_unit == "unknown"
            and self.status is not DatasetStatus.AMBIGUOUS
        ):
            raise ValueError("unknown coordinate unit requires ambiguous dataset status")
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "step_vectors", steps)

    @staticmethod
    def _vector(values, name):
        values = tuple(values)
        if len(values) != 3 or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            for value in values
        ):
            raise ValueError(f"{name} must contain three finite numbers")
        return tuple(float(value) for value in values)

    @property
    def grid_shape(self):
        return self.data.shape[-3:]


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    id: UUID
    revision: str
    producer: str
    producer_version: str
    source: str
    source_hash: str
    parent_ids: tuple[UUID, ...]
    operation: str
    parameters: tuple[tuple[str, object], ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        for name in ("revision", "producer", "producer_version", "operation"):
            _require_text(getattr(self, name), name)
        if not isinstance(self.source, str):
            raise TypeError("source must be a string")
        if self.source_hash and not re.fullmatch(r"[0-9a-f]{64}", self.source_hash):
            raise ValueError("source_hash must be an empty string or SHA-256 hex")
        object.__setattr__(
            self,
            "parent_ids",
            _require_uuid_tuple(self.parent_ids, "parent_ids"),
        )
        parameters = tuple(self.parameters)
        if any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0]
            for item in parameters
        ):
            raise ValueError("parameters must contain non-empty string keys")
        object.__setattr__(self, "parameters", parameters)


@dataclass(frozen=True, slots=True)
class ParserIssue:
    kind: IssueKind
    path: str
    message: str

    def __post_init__(self):
        if not isinstance(self.kind, IssueKind):
            raise TypeError("kind must be an IssueKind")
        _require_text(self.path, "path")
        _require_text(self.message, "message")


@dataclass(frozen=True, slots=True)
class ParserReport:
    reader_id: str
    reader_version: str
    created_entity_ids: tuple[UUID, ...]
    parsed_capabilities: tuple[str, ...]
    issues: tuple[ParserIssue, ...]

    def __post_init__(self):
        _require_token(self.reader_id, "reader_id", _ID_PATTERN)
        _require_text(self.reader_version, "reader_version")
        object.__setattr__(
            self,
            "created_entity_ids",
            _require_uuid_tuple(self.created_entity_ids, "created_entity_ids"),
        )
        capabilities = tuple(self.parsed_capabilities)
        for capability in capabilities:
            _require_token(capability, "parsed_capability")
        issues = tuple(self.issues)
        if any(not isinstance(issue, ParserIssue) for issue in issues):
            raise TypeError("issues must contain ParserIssue values")
        object.__setattr__(self, "parsed_capabilities", capabilities)
        object.__setattr__(self, "issues", issues)


@dataclass(frozen=True, slots=True)
class ImportBatch:
    structures: tuple[Structure, ...] = ()
    calculations: tuple[CalculationRecord, ...] = ()
    datasets: tuple[PropertyDataset | Grid3D, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    report: ParserReport | None = None

    def __post_init__(self):
        groups = (
            ("structures", Structure),
            ("calculations", CalculationRecord),
            ("datasets", PropertyDataset),
            ("provenance", ProvenanceRecord),
        )
        for name, entity_type in groups:
            values = tuple(getattr(self, name))
            if any(not isinstance(value, entity_type) for value in values):
                raise TypeError(f"{name} contains an invalid entity type")
            object.__setattr__(self, name, values)
        if self.report is not None and not isinstance(self.report, ParserReport):
            raise TypeError("report must be a ParserReport")


@dataclass(slots=True)
class QCProject:
    id: UUID
    schema_version: str
    structures: dict[UUID, Structure] = field(default_factory=dict)
    calculations: dict[UUID, CalculationRecord] = field(default_factory=dict)
    datasets: dict[UUID, PropertyDataset | Grid3D] = field(default_factory=dict)
    provenance: dict[UUID, ProvenanceRecord] = field(default_factory=dict)

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.schema_version, "schema_version")
        self._validate_registries()

    def commit(self, batch):
        if not isinstance(batch, ImportBatch):
            raise TypeError("batch must be an ImportBatch")

        incoming_groups = (
            batch.structures,
            batch.calculations,
            batch.datasets,
            batch.provenance,
        )
        incoming = tuple(entity for group in incoming_groups for entity in group)
        incoming_ids = tuple(entity.id for entity in incoming)
        if len(set(incoming_ids)) != len(incoming_ids):
            raise ValueError("batch contains duplicate entity UUIDs")

        existing_ids = self._all_entity_ids()
        if existing_ids.intersection(incoming_ids):
            raise ValueError("batch UUID already exists in project")

        structure_ids = set(self.structures).union(
            structure.id for structure in batch.structures
        )
        calculation_ids = set(self.calculations).union(
            calculation.id for calculation in batch.calculations
        )
        dataset_ids = set(self.datasets).union(dataset.id for dataset in batch.datasets)
        provenance_ids = set(self.provenance).union(
            record.id for record in batch.provenance
        )

        for calculation in batch.calculations:
            self._require_references(
                calculation.input_structure_ids + calculation.result_structure_ids,
                structure_ids,
                "calculation structure",
            )
            self._require_references(
                calculation.dataset_ids,
                dataset_ids,
                "calculation dataset",
            )
            self._require_references(
                calculation.provenance_ids,
                provenance_ids,
                "calculation provenance",
            )
        for dataset in batch.datasets:
            if (
                dataset.source_calculation is not None
                and dataset.source_calculation not in calculation_ids
            ):
                raise ValueError("dataset has a dangling calculation reference")
            self._require_references(
                dataset.provenance_ids,
                provenance_ids,
                "dataset provenance",
            )
        all_ids = structure_ids | calculation_ids | dataset_ids | provenance_ids
        for record in batch.provenance:
            self._require_references(record.parent_ids, all_ids, "provenance parent")
        if batch.report is not None and set(batch.report.created_entity_ids) != set(
            incoming_ids
        ):
            raise ValueError("parser report created IDs must match the import batch")

        self.structures.update((entity.id, entity) for entity in batch.structures)
        self.calculations.update((entity.id, entity) for entity in batch.calculations)
        self.datasets.update((entity.id, entity) for entity in batch.datasets)
        self.provenance.update((entity.id, entity) for entity in batch.provenance)

    def _all_entity_ids(self):
        groups = (self.structures, self.calculations, self.datasets, self.provenance)
        ids = [entity_id for group in groups for entity_id in group]
        if len(set(ids)) != len(ids):
            raise ValueError("project registries contain duplicate entity UUIDs")
        return set(ids)

    def _validate_registries(self):
        groups = (
            (self.structures, Structure, "structures"),
            (self.calculations, CalculationRecord, "calculations"),
            (self.datasets, PropertyDataset, "datasets"),
            (self.provenance, ProvenanceRecord, "provenance"),
        )
        for registry, entity_type, name in groups:
            if not isinstance(registry, dict):
                raise TypeError(f"{name} must be a dict")
            if any(
                not isinstance(entity, entity_type) or entity_id != entity.id
                for entity_id, entity in registry.items()
            ):
                raise ValueError(f"{name} keys and entity IDs must match")
        self._all_entity_ids()

    @staticmethod
    def _require_references(references, valid_ids, name):
        if any(reference not in valid_ids for reference in references):
            raise ValueError(f"{name} reference is dangling")
