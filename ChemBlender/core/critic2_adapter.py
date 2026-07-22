"""Adapter for critic2 cpreport JSON output."""

import json
import math
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from .cache_identity import parser_cache_key, source_hash_bytes
from .model import (
    ArrayData,
    CriticalPointKind,
    DatasetStatus,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    ProvenanceRecord,
    TopologyConnection,
    TopologyGraph,
)


ADAPTER_ID = "critic2-cpreport-json"
ADAPTER_VERSION = "1"
CRITIC2_REVIEWED_VERSION = "1.3.15"


def _finite(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _integer(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, int) or (positive and value <= 0):
        raise ValueError(f"{name} must be an integer")
    return value


def _vector(values, name, converter=_finite):
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError(f"{name} must contain three values")
    return tuple(converter(value, name) for value in values)


def _kind(signature, is_nucleus):
    if not isinstance(is_nucleus, bool):
        raise ValueError("is_nucleus must be boolean")
    if signature == -3:
        return CriticalPointKind.NUCLEAR if is_nucleus else CriticalPointKind.ATTRACTOR
    if is_nucleus:
        raise ValueError("only a rank-3 signature -3 point can be a nucleus")
    try:
        return {
            -1: CriticalPointKind.BOND,
            1: CriticalPointKind.RING,
            3: CriticalPointKind.CAGE,
        }[signature]
    except KeyError as error:
        raise ValueError("unsupported critical point signature") from error


def _required(document, fields, label):
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be an object")
    missing = set(fields) - set(document)
    if missing:
        raise ValueError(f"{label} is missing fields: {', '.join(sorted(missing))}")


def _load(path):
    path = Path(path)
    try:
        source = path.read_bytes()
        document = json.loads(
            source.decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value: {value}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("cannot read critic2 cpreport JSON") from error
    return path, source, document


def parse_critic2_cpreport(
    path,
    *,
    structure_id,
    source_grid_id=None,
    source_calculation=None,
    coordinate_unit="bohr",
    field_semantic_role="electron_density",
    field_unit="inverse_cubic_bohr",
    laplacian_unit="inverse_bohr_fifth",
):
    if not isinstance(structure_id, UUID):
        raise TypeError("structure_id must be a UUID")
    for value, name in (
        (source_grid_id, "source_grid_id"),
        (source_calculation, "source_calculation"),
    ):
        if value is not None and not isinstance(value, UUID):
            raise TypeError(f"{name} must be a UUID")
    for value, name in (
        (coordinate_unit, "coordinate_unit"),
        (field_semantic_role, "field_semantic_role"),
        (field_unit, "field_unit"),
        (laplacian_unit, "laplacian_unit"),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be non-empty")

    path, source, document = _load(path)
    _required(document, ("critical_points",), "critic2 document")
    section = document["critical_points"]
    _required(
        section,
        (
            "number_of_nonequivalent_cps",
            "nonequivalent_cps",
            "number_of_cell_cps",
            "cell_cps",
        ),
        "critical_points",
    )
    nonequivalent = section["nonequivalent_cps"]
    cell_points = section["cell_cps"]
    if not isinstance(nonequivalent, list) or not isinstance(cell_points, list):
        raise ValueError("critical point collections must be arrays")
    if section["number_of_nonequivalent_cps"] != len(nonequivalent):
        raise ValueError("nonequivalent critical point count does not match")

    issues = []
    if section["number_of_cell_cps"] != len(cell_points):
        issues.append(
            ParserIssue(
                IssueKind.WARNING,
                "critical_points.number_of_cell_cps",
                "critic2 declared cell count differs from cell_cps length; list length used",
            )
        )

    nonequivalent_by_id = {}
    for point in nonequivalent:
        _required(
            point,
            (
                "id",
                "name",
                "multiplicity",
                "rank",
                "signature",
                "field",
                "laplacian",
                "hessian_eigenvalues",
                "is_nucleus",
            ),
            "nonequivalent critical point",
        )
        point_id = _integer(point["id"], "critical point id", positive=True)
        if point_id in nonequivalent_by_id:
            raise ValueError("duplicate nonequivalent critical point id")
        rank = _integer(point["rank"], "critical point rank")
        signature = _integer(point["signature"], "critical point signature")
        if rank != 3:
            raise ValueError("critic2 critical point rank must be 3")
        kind = _kind(signature, point["is_nucleus"])
        name = point["name"]
        if not isinstance(name, str) or not name:
            raise ValueError("critical point name must be non-empty")
        nonequivalent_by_id[point_id] = {
            "name": name,
            "kind": kind,
            "rank": rank,
            "signature": signature,
            "multiplicity": _integer(
                point["multiplicity"], "critical point multiplicity", positive=True
            ),
            "field": _finite(point["field"], "critical point field"),
            "laplacian": _finite(point["laplacian"], "critical point laplacian"),
            "hessian": _vector(
                point["hessian_eigenvalues"], "hessian eigenvalues"
            ),
        }

    source_hash = source_hash_bytes(source)
    options = {
        "structure_id": structure_id,
        "source_grid_id": source_grid_id,
        "source_calculation": source_calculation,
        "coordinate_unit": coordinate_unit,
        "field_semantic_role": field_semantic_role,
        "field_unit": field_unit,
        "laplacian_unit": laplacian_unit,
    }
    revision = parser_cache_key(source_hash, ADAPTER_ID, ADAPTER_VERSION, options)
    graph_id = uuid5(NAMESPACE_URL, f"chemblender:{ADAPTER_ID}:{revision}")
    point_ids = {}
    cell_by_id = {}
    positions = []
    names = []
    kinds = []
    ranks = []
    signatures = []
    multiplicities = []
    fields = []
    laplacians = []
    hessians = []
    for point in cell_points:
        _required(
            point,
            ("id", "rank", "signature", "cartesian_coordinates", "nonequivalent_id"),
            "cell critical point",
        )
        cell_id = _integer(point["id"], "cell critical point id", positive=True)
        if cell_id in cell_by_id:
            raise ValueError("duplicate cell critical point id")
        nonequivalent_id = _integer(
            point["nonequivalent_id"], "nonequivalent_id", positive=True
        )
        try:
            source_point = nonequivalent_by_id[nonequivalent_id]
        except KeyError as error:
            raise ValueError("cell critical point has dangling nonequivalent mapping") from error
        rank = _integer(point["rank"], "cell critical point rank")
        signature = _integer(point["signature"], "cell critical point signature")
        if rank != source_point["rank"] or signature != source_point["signature"]:
            raise ValueError("cell and nonequivalent critical point classifications disagree")
        stable_id = uuid5(graph_id, f"critical-point:{cell_id}")
        point_ids[cell_id] = stable_id
        cell_by_id[cell_id] = point
        positions.append(_vector(point["cartesian_coordinates"], "cartesian coordinates"))
        names.append(source_point["name"])
        kinds.append(source_point["kind"])
        ranks.append(rank)
        signatures.append(signature)
        multiplicities.append(source_point["multiplicity"])
        fields.append(source_point["field"])
        laplacians.append(source_point["laplacian"])
        hessians.append(source_point["hessian"])

    connections = []
    for cell_id, point in cell_by_id.items():
        signature = _integer(point["signature"], "cell critical point signature")
        if signature not in {-1, 1}:
            continue
        field = "attractors" if signature == -1 else "repulsors"
        branches = point.get(field)
        if not isinstance(branches, list) or len(branches) != 2:
            raise ValueError(f"{field} must contain exactly two connections")
        relationship = field[:-1]
        for branch_index, branch in enumerate(branches):
            _required(
                branch,
                ("cell_id", "lvec", "distance", "path_length"),
                "topology connection",
            )
            endpoint = _integer(branch["cell_id"], "connection endpoint", positive=True)
            try:
                endpoint_id = point_ids[endpoint]
            except KeyError as error:
                raise ValueError("topology connection has a dangling endpoint") from error
            connection_id = uuid5(
                graph_id, f"connection:{cell_id}:{relationship}:{branch_index}:{endpoint}"
            )
            connections.append(
                TopologyConnection(
                    id=connection_id,
                    critical_point_id=point_ids[cell_id],
                    endpoint_id=endpoint_id,
                    relationship=relationship,
                    lattice_vector=_vector(
                        branch["lvec"],
                        "connection lattice vector",
                        lambda value, name: _integer(value, name),
                    ),
                    distance=_finite(branch["distance"], "connection distance"),
                    path_length=_finite(branch["path_length"], "connection path length"),
                    length_unit=coordinate_unit,
                )
            )

    import numpy

    provenance_id = uuid5(graph_id, "provenance")
    parents = (structure_id,) + (() if source_grid_id is None else (source_grid_id,))
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="critic2",
        producer_version=CRITIC2_REVIEWED_VERSION,
        source=str(path),
        source_hash=source_hash,
        parent_ids=parents,
        operation="parse_cpreport_json",
        parameters=tuple((key, value) for key, value in options.items()),
    )
    graph = TopologyGraph(
        id=graph_id,
        revision=revision,
        semantic_role="topology_graph",
        domain="topology",
        data=ArrayData(numpy.asarray(positions, dtype=float), ("critical_point", "xyz"), coordinate_unit),
        status=DatasetStatus.COMPLETE,
        source_calculation=source_calculation,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
        source_grid_id=source_grid_id,
        critical_point_ids=tuple(point_ids.values()),
        names=tuple(names),
        kinds=tuple(kinds),
        ranks=tuple(ranks),
        signatures=tuple(signatures),
        multiplicities=tuple(multiplicities),
        field_semantic_role=field_semantic_role,
        field_values=ArrayData(numpy.asarray(fields), ("critical_point",), field_unit),
        laplacians=ArrayData(numpy.asarray(laplacians), ("critical_point",), laplacian_unit),
        hessian_eigenvalues=ArrayData(
            numpy.asarray(hessians), ("critical_point", "eigenvalue"), laplacian_unit
        ),
        connections=tuple(connections),
        paths=(),
    )
    report = ParserReport(
        reader_id=ADAPTER_ID,
        reader_version=ADAPTER_VERSION,
        created_entity_ids=(graph_id, provenance_id),
        parsed_capabilities=("topology",),
        issues=tuple(issues),
    )
    return ImportBatch(datasets=(graph,), provenance=(provenance,), report=report)
