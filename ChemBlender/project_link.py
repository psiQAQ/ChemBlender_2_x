import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from uuid import UUID

from .core.sidecar import (
    SidecarCompatibilityError,
    SidecarIntegrityError,
    SidecarNotFoundError,
    open_project,
)


PROJECT_ID_KEY = "cbq_project_id"
PROJECT_SCHEMA_KEY = "cbq_project_schema_version"
SIDECAR_LOCATOR_KEY = "cbq_sidecar_locator"


class ProjectLinkStatus(str, Enum):
    CONNECTED = "connected"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    MISMATCH = "mismatch"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class ProjectLinkResult:
    status: ProjectLinkStatus
    path: Path | None
    project: object | None = None
    message: str = ""


def _blend_directory(blend_path):
    if blend_path:
        return Path(blend_path).resolve().parent
    return None


def write_project_link(scene, project, sidecar_path, *, blend_path=None):
    sidecar = Path(sidecar_path).resolve()
    base = _blend_directory(blend_path)
    locator = os.path.relpath(sidecar, base) if base is not None else str(sidecar)
    scene[PROJECT_ID_KEY] = str(project.id)
    scene[PROJECT_SCHEMA_KEY] = project.schema_version
    scene[SIDECAR_LOCATOR_KEY] = locator
    return locator


def resolve_project_link(scene, *, blend_path=None, verify_arrays=True):
    try:
        expected_id = UUID(scene[PROJECT_ID_KEY])
        expected_schema = scene[PROJECT_SCHEMA_KEY]
        locator = scene[SIDECAR_LOCATOR_KEY]
        if not isinstance(expected_schema, str) or not expected_schema:
            raise ValueError
        if not isinstance(locator, str) or not locator:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return ProjectLinkResult(ProjectLinkStatus.INVALID, None, message="invalid scene project link")

    path = Path(locator)
    base = _blend_directory(blend_path)
    if not path.is_absolute() and base is not None:
        path = base / path
    path = path.resolve()
    try:
        project = open_project(
            path,
            expected_schema_version=expected_schema,
            verify_arrays=verify_arrays,
        )
    except SidecarNotFoundError as error:
        return ProjectLinkResult(ProjectLinkStatus.MISSING, path, message=str(error))
    except SidecarCompatibilityError as error:
        return ProjectLinkResult(ProjectLinkStatus.INCOMPATIBLE, path, message=str(error))
    except SidecarIntegrityError as error:
        return ProjectLinkResult(ProjectLinkStatus.INVALID, path, message=str(error))

    if project.id != expected_id:
        return ProjectLinkResult(
            ProjectLinkStatus.MISMATCH,
            path,
            project=project,
            message="sidecar project UUID does not match scene link",
        )
    return ProjectLinkResult(ProjectLinkStatus.CONNECTED, path, project=project)
