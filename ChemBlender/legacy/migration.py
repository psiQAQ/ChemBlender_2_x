from dataclasses import dataclass, fields
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
from ..core.storage.publication import solidify_session
from ..core.sidecar import close_project
from .extraction import LegacyExtractionReport, LegacyObjectSnapshot


_REVISION = "legacy-migration-v1"


@dataclass(frozen=True, slots=True)
class ViewSettings:
    radii: tuple[float, ...] | None
    vdw_radii: tuple[float, ...] | None
    atom_scales: tuple[float, ...] | None
    colors: tuple[tuple[float, float, float, float], ...] | None
    bond_scales: tuple[float | None, ...]
    dashed: tuple[bool | None, ...]


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
    if report.source_path:
        path = Path(report.source_path)
        if path.is_file():
            return str(path), sha256(path.read_bytes()).hexdigest()
        _diagnostic(diagnostics, None, "source_path", "legacy blend source is not a regular file")
    else:
        _diagnostic(diagnostics, None, "source_path", "legacy blend source path is unavailable")
    return "", ""


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
        edges.append((left, right, order))
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
    )


def _view_settings(snapshot, diagnostics):
    count = len(snapshot.atomic_numbers)
    def values(name, value, width=1):
        if value is None:
            return None
        if len(value) != count or any(len(item) != width for item in value if width > 1):
            _diagnostic(diagnostics, snapshot.name, name, f"legacy {name} shape does not match atom count")
            return None
        return value
    return ViewSettings(
        values("radii", snapshot.radii), values("vdw_radii", snapshot.vdw_radii),
        values("atom_scales", snapshot.atom_scales), values("colors", snapshot.colors, 4),
        tuple(edge.scale for edge in snapshot.edges), tuple(edge.dashed for edge in snapshot.edges),
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
        else:
            if not snapshot.atomic_numbers or any(type(number) is not int or not 1 <= number <= 118 for number in snapshot.atomic_numbers):
                raise ValueError("atomic_numbers must contain values from 1 to 118")
            coordinates = _coordinates(snapshot.coordinates, len(snapshot.atomic_numbers))
            topology = _molecule_topology(snapshot, uuid4(), record.id, diagnostics)
            structure = Structure(id=topology.structure_id, revision=_REVISION, atomic_numbers=tuple(snapshot.atomic_numbers), coordinates=coordinates, topology_ids=(topology.id,))
            topologies.append(topology)
        structures.append(structure)
        provenance.append(record)
        view_plans.append(ViewPlan(structure.id, snapshot.name, snapshot.kind, _view_settings(snapshot, diagnostics)))
    candidate.commit(ImportBatch(structures=tuple(structures), topologies=tuple(topologies), provenance=tuple(provenance)))
    report = LegacyMigrationReport(source, source_hash, tuple(snapshot.name for snapshot in extraction_report.objects), tuple(diagnostics))
    return candidate, tuple(view_plans), report


def commit_legacy_migration(project_session, candidate_project):
    if type(project_session) is not ProjectSession:
        raise TypeError("project_session must be a ProjectSession")
    if type(candidate_project) is not QCProject or candidate_project.id != project_session.project.id:
        raise ValueError("candidate_project must be a copy of the session project")
    destination = project_session.sidecar_path or project_session.temporary_root / "project.cbq"
    candidate_session = ProjectSession(project_session.id, candidate_project, project_session.temporary_root, project_session.sidecar_path, link_status=project_session.link_status)
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
