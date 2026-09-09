"""Preview and atomically add a verified CBQ package to an owned project."""

from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
import hashlib
import json
from uuid import UUID

from .model import Grid3D, ImportBatch, QCProject
from .model_registry import model_type_tag
from .session import ProjectSession
from .sidecar import (
    LazyNpyArray, _array_content_hash, _open_project_with_manifest, close_project,
)
from .storage.publication import solidify_session


_REGISTRIES = tuple(item.name for item in fields(QCProject)
                    if item.name not in {"id", "schema_version"})
_BATCH_REGISTRIES = tuple(item.name for item in fields(ImportBatch)
                          if item.name != "report")


@dataclass(frozen=True, slots=True)
class PackagePreview:
    source_project_id: str
    manifest_sha256: str
    counts: dict[str, int]
    conflicts: tuple[str, ...]
    source_duplicates: tuple[str, ...]
    readiness: tuple[str, ...]
    cleanup_warnings: tuple[str, ...] = ()


def _content(value):
    """Use scientific type tags and array content, never storage paths."""
    import numpy

    if isinstance(value, Enum):
        return [type(value).__name__, value.value]
    if isinstance(value, UUID):
        return ["uuid", str(value)]
    if isinstance(value, bytes):
        return ["bytes", hashlib.sha256(value).hexdigest()]
    if isinstance(value, LazyNpyArray):
        # Packages are opened with array verification before fingerprints are used.
        return ["array", value.content_hash]
    if isinstance(value, numpy.ndarray):
        return ["array", _array_content_hash(value)[0]]
    if is_dataclass(value):
        return [model_type_tag(value), {
            item.name: _content(getattr(value, item.name)) for item in fields(value)
            if item.init
        }]
    if isinstance(value, (tuple, list)):
        return [_content(item) for item in value]
    if isinstance(value, dict):
        return [[_content(key), _content(value[key])]
                for key in sorted(value, key=str)]
    if isinstance(value, numpy.generic):
        return value.item()
    return value


def _fingerprint(value):
    return hashlib.sha256(json.dumps(_content(value), sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def display_readiness(project):
    """Missing display inputs are diagnostics, not package-integrity failures."""
    notes = []
    for structure in project.structures.values():
        periodic = structure.periodic
        if periodic is not None and periodic.symmetry_operations and (
            getattr(periodic, "symmetry_rotations", None) is None
            or getattr(periodic, "symmetry_translations", None) is None
        ):
            notes.append(f"Structure {structure.id}: numeric symmetry operations missing; "
                         "use external upgrade before symmetry expansion")
        if not structure.topology_ids and structure.topology is None:
            notes.append(f"Structure {structure.id}: no prepared bonds; atoms can be displayed")
    for orbitals in project.orbital_sets.values():
        from .orbital_browser import orbital_rows
        count = sum(bool(row.cached_dataset_ids) for channel in orbitals.channels
                    for row in orbital_rows(project, orbitals, channel.label))
        notes.append(f"Orbital set {orbitals.id}: {count} prepared orbital grids; "
                     "other orbitals require external preparation")
    for dataset in project.datasets.values():
        if isinstance(dataset, Grid3D) and dataset.semantic_role in {"scalar_field", "unknown"}:
            notes.append(f"Grid {dataset.id}: generic scalar data; assign known physical "
                         "semantics externally before a quantity-specific preset")
    return tuple(notes)


def _preview(current, incoming, manifest):
    existing = {identifier: (name, entity) for name in _REGISTRIES
                for identifier, entity in getattr(current, name).items()}
    conflicts, duplicates = [], []
    counts = {name: len(getattr(incoming, name)) for name in _REGISTRIES}
    counts.update(new=0, reused=0)
    for name in _REGISTRIES:
        for identifier, entity in getattr(incoming, name).items():
            previous = existing.get(identifier)
            if previous is None:
                counts["new"] += 1
            elif previous[0] != name or _fingerprint(previous[1]) != _fingerprint(entity):
                conflicts.append(f"UUID {identifier} has different content ({name})")
            else:
                counts["reused"] += 1
    hashes = {}
    for revision in current.source_revisions.values():
        hashes.setdefault(revision.content_hash, set()).add(revision.source_id)
    for revision in incoming.source_revisions.values():
        # Existing UUIDs are reused or rejected by the content check above.
        if revision.id in current.source_revisions:
            continue
        others = hashes.get(revision.content_hash, set()) - {revision.source_id}
        if others:
            duplicates.append(f"Source {revision.source_id} shares content with "
                              + ", ".join(sorted(map(str, others))))
    return PackagePreview(str(incoming.id), manifest.get("manifest_sha256", ""),
                          counts, tuple(conflicts), tuple(sorted(set(duplicates))),
                          display_readiness(incoming))


def preview_package(session, path):
    if not isinstance(session, ProjectSession):
        raise TypeError("session must be a ProjectSession")
    incoming, manifest = _open_project_with_manifest(path, verify_arrays=True)
    try:
        return _preview(session.project, incoming, manifest)
    finally:
        close_project(incoming)


def import_package(session, path, *, allow_duplicate_sources=False,
                   expected_manifest_sha256=None, progress=None, is_cancelled=None):
    """Verify again and publish before swapping the live project; retain all Views."""
    if not isinstance(session, ProjectSession):
        raise TypeError("session must be a ProjectSession")
    if type(allow_duplicate_sources) is not bool:
        raise TypeError("allow_duplicate_sources must be bool")
    incoming, manifest = _open_project_with_manifest(path, verify_arrays=True)
    try:
        preview = _preview(session.project, incoming, manifest)
        if expected_manifest_sha256 is not None and preview.manifest_sha256 != expected_manifest_sha256:
            raise ValueError("CBQ changed after preview; preview it again")
        if preview.conflicts:
            raise ValueError("; ".join(preview.conflicts))
        if preview.source_duplicates and not allow_duplicate_sources:
            raise ValueError("Duplicate sources require explicit confirmation: "
                             + "; ".join(preview.source_duplicates))
        if not preview.counts["new"]:
            return preview
        current = session.project
        warnings = commit_session_batch(session, ImportBatch(**{
            name: tuple(entity for identifier, entity in getattr(incoming, name).items()
                        if identifier not in getattr(current, name))
            for name in _BATCH_REGISTRIES
        }), calculation_groups=tuple(
            group for identifier, group in incoming.calculation_groups.items()
            if identifier not in current.calculation_groups),
            progress=progress, is_cancelled=is_cancelled)
        preview = replace(preview, cleanup_warnings=warnings)
        return preview
    finally:
        close_project(incoming)


def commit_session_batch(session, batch, *, calculation_groups=(),
                         progress=None, is_cancelled=None):
    """Publish a validated local batch before swapping the project; retain Views."""
    if not isinstance(session, ProjectSession):
        raise TypeError("session must be a ProjectSession")
    current = session.project
    candidate = QCProject(id=current.id, schema_version=current.schema_version,
                          **{name: dict(getattr(current, name)) for name in _REGISTRIES})
    candidate.commit(batch)
    candidate.commit_calculation_groups(calculation_groups)
    # Imports and Mesh Apply are unsaved edits; never overwrite the saved sidecar.
    session.temporary_root.mkdir(parents=True, exist_ok=True)
    destination = session.temporary_root / "project.cbq"
    candidate_session = ProjectSession(id=session.id, project=candidate,
        temporary_root=session.temporary_root, sidecar_path=session.sidecar_path,
        link_status=session.link_status)
    published = solidify_session(candidate_session, destination,
        transfer_verified_project=True, progress=progress, is_cancelled=is_cancelled)
    if not isinstance(published.project, QCProject):
        raise RuntimeError("publication did not return its verified project")
    session.project = published.project
    session.sidecar_path = published.path
    session.mark_dirty("import")
    try:
        close_project(current)
    except Exception as error:
        return (f"Previous project cleanup: {error}",)
    return ()
