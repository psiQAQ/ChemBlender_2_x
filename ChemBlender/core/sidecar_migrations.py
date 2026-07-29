from copy import deepcopy
import hashlib
import json
from uuid import UUID, uuid5


CURRENT_MANIFEST_VERSION = "1.0"
LEGACY_MANIFEST_VERSION = "0.1"
HASHED_LEGACY_MANIFEST_VERSION = "0.2"
CURRENT_PROJECT_SCHEMA_VERSION = "1.0"
_EXPLICIT_TOPOLOGY_READERS = frozenset(
    ("cjson", "mol", "mol2", "mol_v2000", "pdb", "pqr", "sdf")
)
_EXPLICIT_TOPOLOGY_SUFFIXES = (
    ".cjson",
    ".mol",
    ".mol2",
    ".pdb",
    ".pqr",
    ".sdf",
)


def _uuid_value(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"$uuid"}
        or not isinstance(value["$uuid"], str)
    ):
        raise ValueError("invalid UUID tag")
    return UUID(value["$uuid"])


def _registry_entries(project, name):
    registry = project.get(name)
    if not isinstance(registry, dict) or set(registry) != {"$dict"}:
        return ()
    entries = registry["$dict"]
    return entries if isinstance(entries, list) else ()


def _legacy_topology_source(project, structure_id):
    for _key, revision in _registry_entries(project, "source_revisions"):
        if not isinstance(revision, dict):
            continue
        created = revision.get("created_entity_ids", {}).get("$tuple", ())
        if structure_id not in created:
            continue
        reader_id = revision.get("reader_id")
        if reader_id in _EXPLICIT_TOPOLOGY_READERS:
            return "explicit_file", "complete", ()
        break
    provenance = _registry_entries(project, "provenance")
    if len(provenance) == 1:
        record = provenance[0][1]
        source = record.get("source", "") if isinstance(record, dict) else ""
        if isinstance(source, str) and source.lower().endswith(
            _EXPLICIT_TOPOLOGY_SUFFIXES
        ):
            return "explicit_file", "complete", ()
    return (
        "distance_inferred",
        "ambiguous",
        (("legacy_origin", "unverified"),),
    )


def _encoded_tuple(values):
    return {"$tuple": [{"$tuple": list(item)} for item in values]}


def _migrate_topology_records(project, migrated_topology_ids=None):
    topology_entries = list(_registry_entries(project, "topologies"))
    changed = "topologies" not in project
    for _key, topology in topology_entries:
        if (
            isinstance(topology, dict)
            and topology.get("$type") == "TopologyRecord"
            and "bond_lattice_shifts" not in topology
        ):
            topology["bond_lattice_shifts"] = None
            changed = True
    structures = _registry_entries(project, "structures")
    for _key, structure in structures:
        if not isinstance(structure, dict) or structure.get("$type") != "Structure":
            continue
        if "topology_ids" not in structure:
            structure["topology_ids"] = {"$tuple": []}
            changed = True
        legacy = structure.get("topology")
        if legacy is None:
            continue
        structure_id = structure.get("id")
        topology_uuid = uuid5(
            _uuid_value(structure_id),
            "chemblender.topology.legacy.v1",
        )
        topology_id = {"$uuid": str(topology_uuid)}
        bond_indices = legacy.get("bond_indices") if isinstance(legacy, dict) else None
        bond_orders = legacy.get("bond_orders") if isinstance(legacy, dict) else None
        shape = (
            bond_indices.get("values", {}).get("shape")
            if isinstance(bond_indices, dict)
            else None
        )
        bond_count = shape[0] if isinstance(shape, list) and shape else 0
        source, quality, parameters = _legacy_topology_source(
            project,
            structure_id,
        )
        revision = hashlib.sha256(
            json.dumps(
                legacy,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        topology_entries.append(
            [
                topology_id,
                {
                    "$type": "TopologyRecord",
                    "id": topology_id,
                    "revision": revision,
                    "structure_id": structure_id,
                    "bond_indices": bond_indices,
                    "bond_orders": bond_orders,
                    "aromatic_flags": None,
                    "stereo_labels": {"$tuple": [""] * bond_count},
                    "source_kind": {
                        "$enum": "TopologySource",
                        "value": source,
                    },
                    "quality_status": {
                        "$enum": "QualityStatus",
                        "value": quality,
                    },
                    "inference_parameters": _encoded_tuple(parameters),
                    "provenance_ids": {"$tuple": []},
                    "bond_lattice_shifts": None,
                },
            ]
        )
        structure["topology"] = None
        structure["topology_ids"] = {"$tuple": [topology_id]}
        if migrated_topology_ids is not None:
            migrated_topology_ids.add(topology_uuid)
        changed = True
    if changed:
        project["topologies"] = {"$dict": topology_entries}
    return changed


def migrate_manifest(document, *, migrated_topology_ids=None):
    from .sidecar import SidecarCompatibilityError, SidecarIntegrityError

    def migrate_topologies(project):
        try:
            _migrate_topology_records(project, migrated_topology_ids)
        except (KeyError, TypeError, ValueError) as error:
            raise SidecarIntegrityError(
                "invalid legacy topology payload"
            ) from error

    if not isinstance(document, dict):
        raise SidecarIntegrityError("sidecar manifest must be an object")
    version = document.get("manifest_version")
    if version not in (
        CURRENT_MANIFEST_VERSION,
        LEGACY_MANIFEST_VERSION,
        HASHED_LEGACY_MANIFEST_VERSION,
    ):
        raise SidecarCompatibilityError("unsupported sidecar manifest version")

    project = document.get("project")
    if version == CURRENT_MANIFEST_VERSION:
        if not isinstance(project, dict) or project.get("$type") != "QCProject":
            return document
    elif version == LEGACY_MANIFEST_VERSION:
        expected_fields = {
            "format",
            "manifest_version",
            "project_id",
            "project_schema_version",
            "project",
        }
        if set(document) != expected_fields:
            raise SidecarIntegrityError(
                "legacy sidecar manifest has invalid top-level fields"
            )
        if document.get("project_schema_version") != LEGACY_MANIFEST_VERSION:
            raise SidecarCompatibilityError("unsupported legacy project schema")
        if (
            not isinstance(project, dict)
            or project.get("$type") != "QCProject"
            or project.get("schema_version") != LEGACY_MANIFEST_VERSION
            or "sources" in project
            or "source_revisions" in project
        ):
            raise SidecarIntegrityError("invalid legacy QCProject payload")
    elif (
        document.get("project_schema_version")
        != HASHED_LEGACY_MANIFEST_VERSION
        or not isinstance(project, dict)
        or project.get("$type") != "QCProject"
        or project.get("schema_version")
        != HASHED_LEGACY_MANIFEST_VERSION
    ):
        raise SidecarIntegrityError("invalid legacy QCProject payload")

    missing = tuple(
        name
        for name in (
            "sources",
            "source_revisions",
            "diagnostics",
            "calculation_groups",
            "topologies",
            "molecular_records",
            "biological_hierarchies",
            "annotations",
            "external_references",
        )
        if name not in project
    )
    has_legacy_structure = any(
        isinstance(structure, dict)
        and (
            "topology_ids" not in structure
            or structure.get("topology") is not None
            or "atomic_identity" not in structure
        )
        for _key, structure in _registry_entries(project, "structures")
    )
    has_legacy_topology = any(
        isinstance(topology, dict)
        and topology.get("$type") == "TopologyRecord"
        and "bond_lattice_shifts" not in topology
        for _key, topology in _registry_entries(project, "topologies")
    )
    if (
        version == CURRENT_MANIFEST_VERSION
        and not missing
        and not has_legacy_structure
        and not has_legacy_topology
    ):
        return document

    migrated = deepcopy(document)
    for name in (
        "sources",
        "source_revisions",
        "diagnostics",
        "calculation_groups",
        "topologies",
        "molecular_records",
        "biological_hierarchies",
        "annotations",
        "external_references",
    ):
        migrated["project"].setdefault(name, {"$dict": []})
    for _key, structure in _registry_entries(migrated["project"], "structures"):
        if (
            isinstance(structure, dict)
            and structure.get("$type") == "Structure"
            and "atomic_identity" not in structure
        ):
            structure["atomic_identity"] = None
    migrate_topologies(migrated["project"])
    if version != CURRENT_MANIFEST_VERSION:
        migrated["manifest_version"] = CURRENT_MANIFEST_VERSION
        migrated["project_schema_version"] = CURRENT_PROJECT_SCHEMA_VERSION
        migrated["project"]["schema_version"] = CURRENT_PROJECT_SCHEMA_VERSION
    return migrated
