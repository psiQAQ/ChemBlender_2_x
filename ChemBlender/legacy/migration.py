from dataclasses import dataclass, fields, is_dataclass
import json
import re
from enum import Enum
from hashlib import sha256
from math import cos, isfinite, pi, sin, sqrt
from pathlib import Path
from uuid import UUID, uuid4

import numpy

from ..Chem_data import ELEMENTS_DEFAULT
from ..core import (
    ArrayData,
    PeriodicSiteData,
    ProjectSession,
    ProvenanceRecord,
    QCProject,
    QualityStatus,
    Structure,
    TopologyRecord,
    TopologySource,
    fractional_to_cartesian,
)
from ..core.model import ImportBatch
from ..core.model_registry import model_type_tag
from ..core.storage.publication import solidify_session
from ..core.sidecar import LazyNpyArray, _array_content_hash, close_project
from .extraction import (
    LegacyExtractionReport,
    LegacyMaterialSnapshot,
    LegacyNodeModifierSnapshot,
)


_REVISION = "legacy-migration-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class ViewSettings:
    radii: tuple[float, ...] | None
    vdw_radii: tuple[float, ...] | None
    atom_scales: tuple[float, ...] | None
    colors: tuple[tuple[float, float, float, float], ...] | None
    bond_scales: tuple[float, ...] | None
    dashed: tuple[bool, ...] | None
    materials: tuple[LegacyMaterialSnapshot, ...]
    node_modifiers: tuple[LegacyNodeModifierSnapshot, ...]


@dataclass(frozen=True, slots=True)
class ViewPlan:
    structure_id: UUID
    legacy_object_name: str
    kind: str
    settings: ViewSettings


@dataclass(frozen=True, slots=True)
class LegacyMigrationDiagnostic:
    object_name: str | None
    field_path: str
    code: str
    message: str
    quality_status: QualityStatus


@dataclass(frozen=True, slots=True)
class LegacyMigrationReport:
    source_path: str
    source_hash: str
    object_names: tuple[str, ...]
    diagnostics: tuple[LegacyMigrationDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class LegacyMigrationCommitResult:
    project: QCProject
    sidecar_path: Path
    cleanup_warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True, weakref_slot=True)
class LegacyMigrationPlan:
    project: QCProject
    view_plans: tuple[ViewPlan, ...]
    report: LegacyMigrationReport
    base_project: QCProject
    base_inventory: tuple[object, ...]
    candidate_inventory: tuple[object, ...]


def _copy_project(project):
    if type(project) is not QCProject:
        raise TypeError("base_project must be a QCProject")
    return QCProject(
        **{
            item.name: dict(getattr(project, item.name))
            if isinstance(getattr(project, item.name), dict)
            else getattr(project, item.name)
            for item in fields(QCProject)
        }
    )


def _diagnostic(diagnostics, object_name, field_path, message):
    diagnostics.append(
        LegacyMigrationDiagnostic(
            object_name,
            field_path,
            "legacy_unverified",
            message,
            QualityStatus.AMBIGUOUS,
        )
    )


def _source(report, diagnostics):
    if (
        type(report.source_verified) is bool
        and report.source_verified
        and type(report.source_hash) is str
        and _SHA256.fullmatch(report.source_hash)
        and report.source_path
    ):
        path = Path(report.source_path)
        try:
            linked = path.is_symlink() or getattr(path, "is_junction", lambda: False)()
            reparse = bool(getattr(path.stat(), "st_file_attributes", 0) & 0x400)
            if path.suffix.lower() == ".blend" and path.is_file() and not linked and not reparse:
                current_hash = sha256(path.read_bytes()).hexdigest()
                if current_hash == report.source_hash:
                    return str(path), current_hash
        except OSError:
            pass
        _diagnostic(diagnostics, None, "source_path", "legacy blend source changed or is not a trusted regular .blend file")
    else:
        _diagnostic(diagnostics, None, "source_path", "legacy blend source proof is invalid or was not verified by extraction")
    return "", ""


def _persisted_value(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not isfinite(value):
            raise TypeError("non-finite persisted float")
        return ("float", value.hex())
    if type(value) is bytes:
        return ("bytes", value.hex())
    if type(value) is UUID:
        return ("uuid", str(value))
    if isinstance(value, Enum):
        return ("enum", type(value).__module__, type(value).__qualname__, _persisted_value(value.value))
    if type(value) is ArrayData:
        values = value.values
        content_hash = (
            values.content_hash
            if isinstance(values, LazyNpyArray) and not values.loaded
            else _array_content_hash(values)[0]
        )
        return ("array", content_hash, _persisted_value(value.dims), value.unit)
    if type(value) is tuple:
        return ("tuple", tuple(_persisted_value(item) for item in value))
    if type(value) is list:
        return ("list", tuple(_persisted_value(item) for item in value))
    if type(value) is dict:
        entries = [(_persisted_value(key), _persisted_value(item)) for key, item in value.items()]
        return ("dict", tuple(sorted(entries, key=lambda item: repr(item[0]))))
    if is_dataclass(value):
        try:
            type_name = model_type_tag(value)
        except TypeError as error:
            raise TypeError(f"unsupported persisted value: {type(value).__name__}") from error
        return (
            "dataclass",
            type_name,
            tuple((item.name, _persisted_value(getattr(value, item.name))) for item in fields(value) if item.init),
        )
    raise TypeError(f"unsupported persisted value: {type(value).__name__}")


def _content_fingerprint(value):
    return sha256(
        json.dumps(_persisted_value(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _project_inventory(project):
    inventory = [("project", str(project.id), project.schema_version)]
    for field in fields(QCProject):
        values = getattr(project, field.name)
        if not isinstance(values, dict):
            inventory.append((field.name, values))
            continue
        entries = []
        for key, value in sorted(values.items(), key=lambda item: str(item[0])):
            entries.append(
                (
                    str(key),
                    type(value).__module__,
                    type(value).__qualname__,
                    str(getattr(value, "id", key)),
                    getattr(value, "revision", None),
                    id(value),
                    _content_fingerprint(value),
                )
            )
        inventory.append((field.name, tuple(entries)))
    return tuple(inventory)


def _cell(parameters):
    if len(parameters) != 6 or any(not isfinite(value) for value in parameters):
        raise ValueError("cell must contain six finite values")
    a, b, c, alpha, beta, gamma = parameters
    if min(a, b, c) <= 0.0 or not 0.0 < min(alpha, beta, gamma) < 180.0:
        raise ValueError("cell lengths must be positive and angles must be between 0 and 180")
    alpha, beta, gamma = (value * pi / 180.0 for value in (alpha, beta, gamma))
    sin_gamma = sin(gamma)
    if abs(sin_gamma) <= 1.0e-12:
        raise ValueError("cell is singular")
    c_x = c * cos(beta)
    c_y = c * (cos(alpha) - cos(beta) * cos(gamma)) / sin_gamma
    c_z_squared = c * c - c_x * c_x - c_y * c_y
    if c_z_squared <= 1.0e-12:
        raise ValueError("cell is singular")
    return ArrayData(
        numpy.asarray(
            ((a, 0.0, 0.0), (b * cos(gamma), b * sin_gamma, 0.0), (c_x, c_y, sqrt(c_z_squared))),
            dtype=float,
        ),
        ("cell_vector", "xyz"),
        "angstrom",
    )


def _coordinates(values, count):
    if len(values) != count or any(len(row) != 3 or not all(isfinite(value) for value in row) for row in values):
        raise ValueError("atomic_numbers and coordinates must have matching finite (atom, xyz) shape")
    return ArrayData(numpy.asarray(values, dtype=float), ("atom", "xyz"), "angstrom")


def _molecule_topology(snapshot, structure_id, provenance_id, diagnostics):
    edges = []
    for index, edge in enumerate(snapshot.edges):
        endpoints = tuple(edge.vertices)
        if len(endpoints) != 2 or any(type(value) is not int or not 0 <= value < len(snapshot.atomic_numbers) for value in endpoints):
            raise ValueError("edge vertices must be valid atomic-number indices")
        if endpoints[0] == endpoints[1]:
            raise ValueError("edge vertices must differ")
        left, right = sorted(endpoints)
        if edge.order is None:
            _diagnostic(diagnostics, snapshot.name, f"edges[{index}].order", "legacy bond order is missing")
            order = 0.0
        elif not isfinite(edge.order) or edge.order < 0:
            raise ValueError("edge order must be finite and non-negative")
        else:
            order = float(edge.order)
        edges.append((left, right, order, index))
    if len({edge[:2] for edge in edges}) != len(edges):
        raise ValueError("legacy edges must not repeat")
    edges.sort()
    return TopologyRecord(
        id=uuid4(), revision=_REVISION, structure_id=structure_id,
        bond_indices=ArrayData(numpy.asarray([edge[:2] for edge in edges], dtype=int).reshape((-1, 2)), ("bond", "endpoint"), "dimensionless"),
        bond_orders=ArrayData(numpy.asarray([edge[2] for edge in edges], dtype=float), ("bond",), "dimensionless"),
        aromatic_flags=None, stereo_labels=("",) * len(edges),
        source_kind=TopologySource.EXPLICIT_FILE,
        quality_status=QualityStatus.AMBIGUOUS if any(edge.order is None for edge in snapshot.edges) else QualityStatus.COMPLETE,
        inference_parameters=(), provenance_ids=(provenance_id,),
    ), tuple(edge[3] for edge in edges)


def _valid_material(value):
    try:
        return (
            type(value) is LegacyMaterialSnapshot
            and isinstance(value.name, str)
            and bool(value.name.strip())
            and type(value.diffuse_color) is tuple
            and len(value.diffuse_color) == 4
            and all(type(item) in (int, float) and isfinite(item) and 0.0 <= item <= 1.0 for item in value.diffuse_color)
            and all(type(item) in (int, float) and isfinite(item) and 0.0 <= item <= 1.0 for item in (value.metallic, value.roughness))
        )
    except TypeError:
        return False


def _valid_node_value(value):
    if type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return isfinite(value)
    return (
        type(value) is tuple
        and 2 <= len(value) <= 4
        and all(type(item) in (int, float) and isfinite(item) for item in value)
    )


def _view_settings(snapshot, diagnostics, count, edge_indices):
    def values(name, value, valid):
        if value is None:
            _diagnostic(diagnostics, snapshot.name, name, f"legacy {name} is unavailable")
            return None
        try:
            valid_values = len(value) == count and all(valid(item) for item in value)
        except TypeError:
            valid_values = False
        if not valid_values:
            _diagnostic(diagnostics, snapshot.name, name, f"legacy {name} is invalid")
            return None
        return value
    def bonds(name, valid):
        values = tuple(getattr(snapshot.edges[index], name) for index in edge_indices)
        if not values:
            return values
        if any(not valid(value) for value in values):
            _diagnostic(diagnostics, snapshot.name, f"edges.{name}", f"legacy bond {name} is invalid or unavailable")
            return None
        return values
    materials = []
    legacy_materials = snapshot.materials if type(snapshot.materials) is tuple else ()
    if legacy_materials is not snapshot.materials:
        _diagnostic(diagnostics, snapshot.name, "materials", "legacy material display is invalid")
    for index, material in enumerate(legacy_materials):
        if _valid_material(material):
            materials.append(material)
        else:
            _diagnostic(diagnostics, snapshot.name, f"materials[{index}]", "legacy material display is invalid")
    node_modifiers = []
    legacy_modifiers = snapshot.node_modifiers if type(snapshot.node_modifiers) is tuple else ()
    if legacy_modifiers is not snapshot.node_modifiers:
        _diagnostic(diagnostics, snapshot.name, "node_modifiers", "legacy node modifier display is invalid")
    for index, modifier in enumerate(legacy_modifiers):
        if (
            type(modifier) is not LegacyNodeModifierSnapshot
            or not isinstance(modifier.name, str)
            or not modifier.name.strip()
            or modifier.node_group_name is not None
            and (not isinstance(modifier.node_group_name, str) or not modifier.node_group_name.strip())
            or type(modifier.inputs) is not tuple
        ):
            _diagnostic(diagnostics, snapshot.name, f"node_modifiers[{index}]", "legacy node modifier identity is invalid")
            continue
        inputs = []
        keys = set()
        for item in modifier.inputs:
            if type(item) is not tuple or len(item) != 2 or not isinstance(item[0], str) or not item[0].strip() or item[0] in keys or not _valid_node_value(item[1]):
                _diagnostic(diagnostics, snapshot.name, f"node_modifiers[{index}].inputs", "legacy node modifier input is invalid")
                continue
            keys.add(item[0])
            inputs.append(item)
        node_modifiers.append(
            LegacyNodeModifierSnapshot(
                modifier.name, modifier.node_group_name, tuple(inputs)
            )
        )
    return ViewSettings(
        values("radii", snapshot.radii, lambda value: type(value) in (int, float) and isfinite(value) and value > 0.0),
        values("vdw_radii", snapshot.vdw_radii, lambda value: type(value) in (int, float) and isfinite(value) and value > 0.0),
        values("atom_scales", snapshot.atom_scales, lambda value: type(value) in (int, float) and isfinite(value) and value > 0.0),
        values("colors", snapshot.colors, lambda value: len(value) == 4 and all(type(item) in (int, float) and isfinite(item) and 0.0 <= item <= 1.0 for item in value)),
        bonds("scale", lambda value: type(value) in (int, float) and isfinite(value) and value > 0.0),
        bonds("dashed", lambda value: type(value) is bool),
        tuple(materials), tuple(node_modifiers),
    )


def _periodic_structure(snapshot):
    cif = snapshot.cif_current or snapshot.cif_original
    if cif is None:
        raise ValueError("crystal requires cif_current or cif_original")
    cell = _cell(cif.cell)
    try:
        atomic_numbers = tuple(ELEMENTS_DEFAULT[atom.element][0] for atom in cif.atoms)
    except KeyError as error:
        raise ValueError("CIF atom element is unknown") from error
    if not atomic_numbers or any(not 1 <= number <= 118 for number in atomic_numbers):
        raise ValueError("CIF atomic numbers must be from 1 to 118")
    fractional = ArrayData(numpy.asarray([atom.coordinates for atom in cif.atoms], dtype=float), ("atom", "xyz"), "dimensionless")
    periodic = PeriodicSiteData(
        fractional_coordinates=fractional, site_labels=tuple(atom.label for atom in cif.atoms),
        occupancies=ArrayData(numpy.asarray([atom.occupancy for atom in cif.atoms], dtype=float), ("atom",), "dimensionless"),
        isotropic_displacements=ArrayData(numpy.asarray([atom.u_iso_equiv for atom in cif.atoms], dtype=float), ("atom",), "angstrom_squared"),
        anisotropic_displacements=ArrayData(numpy.asarray([atom.uij for atom in cif.atoms], dtype=float), ("atom", "tensor_component"), "angstrom_squared"),
        adp_types=tuple(atom.adp_type for atom in cif.atoms), disorder_groups=(0,) * len(cif.atoms),
        declared_space_group_name=cif.space_group, declared_space_group_number=cif.space_group_number,
        symmetry_operations=cif.symmetry_operations, cif_envelope_id=None,
    )
    return Structure(id=uuid4(), revision=_REVISION, atomic_numbers=atomic_numbers,
        coordinates=fractional_to_cartesian(fractional, cell),
        cell=cell, periodic=periodic)


def plan_legacy_migration(extraction_report, base_project):
    if type(extraction_report) is not LegacyExtractionReport:
        raise TypeError("extraction_report must be a LegacyExtractionReport")
    candidate = _copy_project(base_project)
    diagnostics = []
    source, source_hash = _source(extraction_report, diagnostics)
    for item in extraction_report.diagnostics:
        _diagnostic(diagnostics, item.object_name, item.code, item.message)
    structures = []
    topologies = []
    provenance = []
    view_plans = []
    for snapshot in extraction_report.objects:
        if snapshot.kind == "cell":
            continue
        if snapshot.kind not in {"scaffold", "crystal"}:
            raise ValueError("legacy object kind is unsupported")
        record = ProvenanceRecord(id=uuid4(), revision=_REVISION, producer="ChemBlender", producer_version="2.3.0",
            source=source, source_hash=source_hash, parent_ids=(), operation="legacy_blend_migration",
            parameters=(("legacy_object_name", snapshot.name), ("legacy_collection_parents", tuple(snapshot.collections))))
        if snapshot.kind == "crystal":
            structure = _periodic_structure(snapshot)
            edge_indices = ()
        else:
            if not snapshot.atomic_numbers or any(type(number) is not int or not 1 <= number <= 118 for number in snapshot.atomic_numbers):
                raise ValueError("atomic_numbers must contain values from 1 to 118")
            coordinates = _coordinates(snapshot.coordinates, len(snapshot.atomic_numbers))
            topology, edge_indices = _molecule_topology(snapshot, uuid4(), record.id, diagnostics)
            structure = Structure(id=topology.structure_id, revision=_REVISION, atomic_numbers=tuple(snapshot.atomic_numbers), coordinates=coordinates, topology_ids=(topology.id,))
            topologies.append(topology)
        structures.append(structure)
        provenance.append(record)
        view_plans.append(ViewPlan(structure.id, snapshot.name, snapshot.kind, _view_settings(snapshot, diagnostics, len(structure.atomic_numbers), edge_indices)))
    candidate.commit(ImportBatch(structures=tuple(structures), topologies=tuple(topologies), provenance=tuple(provenance)))
    report = LegacyMigrationReport(source, source_hash, tuple(snapshot.name for snapshot in extraction_report.objects), tuple(diagnostics))
    return LegacyMigrationPlan(
        candidate,
        tuple(view_plans),
        report,
        base_project,
        _project_inventory(base_project),
        _project_inventory(candidate),
    )


def commit_legacy_migration(project_session, plan):
    if type(project_session) is not ProjectSession:
        raise TypeError("project_session must be a ProjectSession")
    if type(plan) is not LegacyMigrationPlan:
        raise TypeError("plan must be a LegacyMigrationPlan")
    if project_session.project is not plan.base_project:
        raise ValueError("session base project no longer matches the migration plan")
    if _project_inventory(project_session.project) != plan.base_inventory:
        raise ValueError("session base project inventory changed after migration planning")
    if _project_inventory(plan.project) != plan.candidate_inventory:
        raise ValueError("migration candidate inventory changed after planning")
    destination = project_session.sidecar_path or project_session.temporary_root / "project.cbq"
    candidate_session = ProjectSession(project_session.id, plan.project, project_session.temporary_root, project_session.sidecar_path, link_status=project_session.link_status)
    published = solidify_session(candidate_session, destination, transfer_verified_project=True)
    reopened = published.project
    if type(reopened) is not QCProject:
        raise RuntimeError("publication did not transfer its verified project")
    previous = project_session.project
    project_session.project = reopened
    project_session.sidecar_path = published.path
    project_session.mark_dirty("legacy_migration")
    warnings = []
    try:
        close_project(previous)
    except Exception as error:
        warnings.append(f"previous project cleanup failed: {error}")
    return LegacyMigrationCommitResult(reopened, published.path, tuple(warnings))
