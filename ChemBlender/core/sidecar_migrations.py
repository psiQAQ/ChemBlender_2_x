from copy import deepcopy


CURRENT_MANIFEST_VERSION = "0.2"
LEGACY_MANIFEST_VERSION = "0.1"
CURRENT_PROJECT_SCHEMA_VERSION = "0.2"


def migrate_manifest(document):
    from .sidecar import SidecarCompatibilityError, SidecarIntegrityError

    if not isinstance(document, dict):
        raise SidecarIntegrityError("sidecar manifest must be an object")
    version = document.get("manifest_version")
    if version == CURRENT_MANIFEST_VERSION:
        project = document.get("project")
        if (
            isinstance(project, dict)
            and project.get("$type") == "QCProject"
            and "diagnostics" not in project
        ):
            migrated = deepcopy(document)
            migrated["project"]["diagnostics"] = {"$dict": []}
            return migrated
        return document
    if version != LEGACY_MANIFEST_VERSION:
        raise SidecarCompatibilityError("unsupported sidecar manifest version")

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
    project = document.get("project")
    if (
        not isinstance(project, dict)
        or project.get("$type") != "QCProject"
        or project.get("schema_version") != LEGACY_MANIFEST_VERSION
        or "sources" in project
        or "source_revisions" in project
    ):
        raise SidecarIntegrityError("invalid legacy QCProject payload")

    migrated = deepcopy(document)
    migrated["manifest_version"] = CURRENT_MANIFEST_VERSION
    migrated["project_schema_version"] = CURRENT_PROJECT_SCHEMA_VERSION
    migrated["project"]["schema_version"] = CURRENT_PROJECT_SCHEMA_VERSION
    migrated["project"]["sources"] = {"$dict": []}
    migrated["project"]["source_revisions"] = {"$dict": []}
    migrated["project"]["diagnostics"] = {"$dict": []}
    return migrated
