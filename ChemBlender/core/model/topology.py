from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from .arrays import ArrayData
from .common import (
    CriticalPointKind,
    _require_token,
    _require_uuid,
    _require_uuid_tuple,
)
from .properties import PropertyDataset


@dataclass(frozen=True, slots=True)
class TopologyConnection:
    id: UUID
    critical_point_id: UUID
    endpoint_id: UUID
    relationship: str
    lattice_vector: tuple[int, int, int]
    distance: float
    path_length: float
    length_unit: str

    def __post_init__(self):
        for value, name in (
            (self.id, "id"),
            (self.critical_point_id, "critical_point_id"),
            (self.endpoint_id, "endpoint_id"),
        ):
            _require_uuid(value, name)
        if self.critical_point_id == self.endpoint_id:
            raise ValueError("topology connection endpoint must differ from its origin")
        if self.relationship not in {"attractor", "repulsor"}:
            raise ValueError("unsupported topology connection relationship")
        lattice_vector = tuple(self.lattice_vector)
        if len(lattice_vector) != 3 or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in lattice_vector
        ):
            raise ValueError("lattice_vector must contain three integers")
        for value, name in (
            (self.distance, "distance"),
            (self.path_length, "path_length"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0.0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
        _require_token(self.length_unit, "length_unit")
        object.__setattr__(self, "lattice_vector", lattice_vector)


@dataclass(frozen=True, slots=True)
class TopologyPath:
    id: UUID
    start_id: UUID
    end_id: UUID
    samples: ArrayData

    def __post_init__(self):
        import numpy

        for value, name in (
            (self.id, "id"),
            (self.start_id, "start_id"),
            (self.end_id, "end_id"),
        ):
            _require_uuid(value, name)
        if self.start_id == self.end_id:
            raise ValueError("topology path endpoints must differ")
        values = numpy.asarray(self.samples.values)
        if (
            self.samples.dims != ("sample", "xyz")
            or self.samples.shape[0] < 2
            or self.samples.shape[1] != 3
            or self.samples.unit in {"dimensionless", "unknown"}
            or numpy.iscomplexobj(values)
            or not numpy.all(numpy.isfinite(values))
        ):
            raise ValueError("topology path samples must be finite length coordinates")


@dataclass(frozen=True, slots=True)
class TopologyGraph(PropertyDataset):
    structure_id: UUID
    source_grid_id: UUID | None
    critical_point_ids: tuple[UUID, ...]
    names: tuple[str, ...]
    kinds: tuple[CriticalPointKind, ...]
    ranks: tuple[int, ...]
    signatures: tuple[int, ...]
    multiplicities: tuple[int, ...]
    field_semantic_role: str
    field_values: ArrayData
    laplacians: ArrayData
    hessian_eigenvalues: ArrayData
    connections: tuple[TopologyConnection, ...]
    paths: tuple[TopologyPath, ...]

    def __post_init__(self):
        import numpy

        super(TopologyGraph, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        if self.source_grid_id is not None:
            _require_uuid(self.source_grid_id, "source_grid_id")
        _require_token(self.field_semantic_role, "field_semantic_role")
        positions = numpy.asarray(self.data.values)
        if (
            self.semantic_role != "topology_graph"
            or self.domain != "topology"
            or self.data.dims != ("critical_point", "xyz")
            or self.data.shape[0] <= 0
            or self.data.shape[1] != 3
            or self.data.unit in {"dimensionless", "unknown"}
            or numpy.iscomplexobj(positions)
            or not numpy.all(numpy.isfinite(positions))
        ):
            raise ValueError("TopologyGraph positions must be finite length coordinates")
        count = self.data.shape[0]
        ids = _require_uuid_tuple(self.critical_point_ids, "critical_point_ids")
        names = tuple(self.names)
        kinds = tuple(self.kinds)
        ranks = tuple(self.ranks)
        signatures = tuple(self.signatures)
        multiplicities = tuple(self.multiplicities)
        if len(ids) != count or len(set(ids)) != count:
            raise ValueError("critical_point_ids must be unique and match positions")
        if len(names) != count or any(not isinstance(name, str) or not name for name in names):
            raise ValueError("critical point names must match positions")
        if len(kinds) != count or any(not isinstance(kind, CriticalPointKind) for kind in kinds):
            raise ValueError("critical point kinds must match positions")
        if len(ranks) != count or any(value != 3 for value in ranks):
            raise ValueError("critical point ranks must all be 3")
        if len(signatures) != count or any(value not in {-3, -1, 1, 3} for value in signatures):
            raise ValueError("critical point signatures must be -3, -1, 1 or 3")
        expected_kinds = {
            CriticalPointKind.NUCLEAR: -3,
            CriticalPointKind.ATTRACTOR: -3,
            CriticalPointKind.BOND: -1,
            CriticalPointKind.RING: 1,
            CriticalPointKind.CAGE: 3,
        }
        if any(expected_kinds[kind] != signature for kind, signature in zip(kinds, signatures)):
            raise ValueError("critical point kind and signature disagree")
        if len(multiplicities) != count or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in multiplicities
        ):
            raise ValueError("critical point multiplicities must be positive integers")
        arrays = (
            (self.field_values, ("critical_point",), (count,), "field_values"),
            (self.laplacians, ("critical_point",), (count,), "laplacians"),
            (
                self.hessian_eigenvalues,
                ("critical_point", "eigenvalue"),
                (count, 3),
                "hessian_eigenvalues",
            ),
        )
        for array, dims, shape, name in arrays:
            values = numpy.asarray(array.values)
            if (
                not isinstance(array, ArrayData)
                or array.dims != dims
                or array.shape != shape
                or array.unit == "unknown"
                or numpy.iscomplexobj(values)
                or not numpy.all(numpy.isfinite(values))
            ):
                raise ValueError(f"{name} must contain finite critical-point values")
        connections = tuple(self.connections)
        paths = tuple(self.paths)
        id_set = set(ids)
        if any(not isinstance(value, TopologyConnection) for value in connections):
            raise TypeError("connections must contain TopologyConnection values")
        if len({value.id for value in connections}) != len(connections):
            raise ValueError("topology connection IDs must be unique")
        if any(
            value.critical_point_id not in id_set
            or value.endpoint_id not in id_set
            or value.length_unit != self.data.unit
            for value in connections
        ):
            raise ValueError("topology connection endpoint or unit is invalid")
        if any(not isinstance(value, TopologyPath) for value in paths):
            raise TypeError("paths must contain TopologyPath values")
        if len({value.id for value in paths}) != len(paths):
            raise ValueError("topology path IDs must be unique")
        if any(
            value.start_id not in id_set
            or value.end_id not in id_set
            or value.samples.unit != self.data.unit
            for value in paths
        ):
            raise ValueError("topology path endpoint or unit is invalid")
        object.__setattr__(self, "critical_point_ids", ids)
        object.__setattr__(self, "names", names)
        object.__setattr__(self, "kinds", kinds)
        object.__setattr__(self, "ranks", ranks)
        object.__setattr__(self, "signatures", signatures)
        object.__setattr__(self, "multiplicities", multiplicities)
        object.__setattr__(self, "connections", connections)
        object.__setattr__(self, "paths", paths)
