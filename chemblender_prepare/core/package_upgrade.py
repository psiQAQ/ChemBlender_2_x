"""Explicit external preparation of self-contained CBQ 1.1 project data.

This module never changes a source package. The CLI validates the original
container first and publishes the returned project to a new directory.
"""

from dataclasses import fields, replace
import hashlib
import json
from uuid import uuid5

from cbq_core.model import ProvenanceRecord, QCProject
from cbq_core.model.project import validate_project_graph
from cbq_core.sidecar import SidecarCompatibilityError
from cbq_core.sidecar_migrations import CURRENT_PROJECT_SCHEMA_VERSION


def upgrade_project(project: QCProject) -> QCProject:
    """Preserve identity/numerical data and explicitly prepare missing operations.

    New matrices change affected Structure revisions; existing saved View
    bindings remain stale until the user explicitly relinks and rebuilds them.
    Empty operation lists stay empty: whole-cell coordinates are still useful
    for source-site display/replication, but do not establish extra symmetry.
    """
    if not isinstance(project, QCProject):
        raise TypeError("project must be a QCProject")
    if project.schema_version not in ("0.1", "0.2", "1.0", "1.1"):
        raise SidecarCompatibilityError("unsupported project schema for upgrade")
    validate_project_graph(project)
    registries = {
        item.name: dict(getattr(project, item.name))
        for item in fields(project)
        if isinstance(getattr(project, item.name), dict)
    }
    upgraded = replace(project, schema_version=CURRENT_PROJECT_SCHEMA_VERSION, **registries)
    for structure in project.structures.values():
        periodic = structure.periodic
        if periodic is None or not periodic.symmetry_operations or periodic.symmetry_rotations is not None:
            continue
        from .gemmi_adapter import numeric_symmetry_operations
        from .formats.cif import _gemmi

        rotations, translations = numeric_symmetry_operations(periodic.symmetry_operations)
        periodic = replace(periodic, symmetry_rotations=rotations, symmetry_translations=translations)
        version = _gemmi().__version__
        payload = {
            "operation": "prepare_numeric_symmetry_v1",
            "structure_id": str(structure.id),
            "source_revision": structure.revision,
            "symmetry_operations": periodic.symmetry_operations,
            "rotations": rotations.values.tolist(),
            "translations": translations.values.tolist(),
            "gemmi_version": version,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        upgraded.structures[structure.id] = replace(structure, revision=digest, periodic=periodic)
        provenance = ProvenanceRecord(
            id=uuid5(structure.id, "prepare_numeric_symmetry_v1:" + digest),
            revision=digest,
            producer="chemblender_prepare",
            producer_version="0.1.0/gemmi-" + version,
            source=f"cbq:{project.id}/structure/{structure.id}",
            source_hash="",
            parent_ids=(structure.id,),
            operation="prepare_numeric_symmetry_v1",
            parameters=tuple(payload.items()) + (("target_revision", digest),),
        )
        upgraded.provenance[provenance.id] = provenance
    validate_project_graph(upgraded)
    return upgraded
