import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from uuid import UUID

from .core.sidecar import (
    SidecarCompatibilityError,
    SidecarIntegrityError,
    SidecarNotFoundError,
    _open_project_with_manifest,
    close_project,
)


PROJECT_ID_KEY = "cbq_project_id"
PROJECT_SCHEMA_KEY = "cbq_project_schema_version"
SIDECAR_LOCATOR_KEY = "cbq_sidecar_locator"
MANIFEST_HASH_KEY = "cbq_manifest_sha256"


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


@dataclass(frozen=True, slots=True)
class _SceneRollbackFailure:
    key: str
    operation: str
    error: Exception


class _ProjectLinkWriteRecoveryError(RuntimeError):
    def __init__(self, write_error, rollback_errors, residual_keys):
        super().__init__("scene project link write failed and rollback was incomplete")
        self.write_error = write_error
        self.rollback_errors = tuple(rollback_errors)
        self.residual_keys = tuple(residual_keys)


def _blend_directory(blend_path):
    if blend_path:
        return Path(blend_path).resolve().parent
    return None


def _sidecar_locator(sidecar_path, *, blend_path=None):
    sidecar = Path(sidecar_path).resolve()
    base = _blend_directory(blend_path)
    if base is None:
        return str(sidecar)
    try:
        return os.path.relpath(sidecar, base)
    except ValueError:
        return str(sidecar)


def _resolve_sidecar_path(locator, *, blend_path=None):
    path = Path(locator)
    base = _blend_directory(blend_path)
    if not path.is_absolute() and base is not None:
        path = base / path
    return path.resolve()


def _valid_manifest_hash(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _write_scene_values(scene, values):
    missing = object()
    previous = {
        key: scene[key] if key in scene else missing
        for key in values
    }
    attempted = []
    try:
        for key, value in values.items():
            attempted.append(key)
            scene[key] = value
    except Exception as write_error:
        rollback_errors = []
        for key in reversed(attempted):
            operation = "delete" if previous[key] is missing else "set"
            try:
                if operation == "delete":
                    if key in scene:
                        del scene[key]
                else:
                    scene[key] = previous[key]
            except Exception as error:
                rollback_errors.append(
                    _SceneRollbackFailure(key, operation, error)
                )

        residual_keys = []
        for key, old_value in previous.items():
            try:
                matches = (
                    key not in scene
                    if old_value is missing
                    else key in scene and scene[key] == old_value
                )
                matches = bool(matches)
            except Exception:
                matches = False
            if not matches:
                residual_keys.append(key)

        if rollback_errors or residual_keys:
            raise _ProjectLinkWriteRecoveryError(
                write_error,
                rollback_errors,
                residual_keys,
            ) from write_error
        raise


def write_project_link(scene, project, sidecar_path, *, blend_path=None):
    sidecar = Path(sidecar_path).resolve()
    verified, manifest = _open_project_with_manifest(
        sidecar,
        expected_project_id=project.id,
        expected_schema_version=project.schema_version,
        verify_arrays=True,
    )
    try:
        manifest_hash = manifest.get("manifest_sha256")
        if not _valid_manifest_hash(manifest_hash):
            raise SidecarCompatibilityError(
                "sidecar manifest does not provide a verified hash"
            )
        project_id = verified.id
        schema_version = verified.schema_version
    finally:
        close_project(verified)

    locator = _sidecar_locator(sidecar, blend_path=blend_path)
    _write_scene_values(
        scene,
        {
            PROJECT_ID_KEY: str(project_id),
            PROJECT_SCHEMA_KEY: schema_version,
            SIDECAR_LOCATOR_KEY: locator,
            MANIFEST_HASH_KEY: manifest_hash,
        },
    )
    return locator


def resolve_project_link(scene, *, blend_path=None, verify_arrays=True):
    try:
        expected_id = UUID(scene[PROJECT_ID_KEY])
        expected_schema = scene[PROJECT_SCHEMA_KEY]
        locator = scene[SIDECAR_LOCATOR_KEY]
        expected_hash = scene[MANIFEST_HASH_KEY]
        if not isinstance(expected_schema, str) or not expected_schema:
            raise ValueError
        if (
            not isinstance(locator, str)
            or not locator
            or "\0" in locator
        ):
            raise ValueError
        if not _valid_manifest_hash(expected_hash):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return ProjectLinkResult(
            ProjectLinkStatus.INVALID,
            None,
            message="invalid scene project link",
        )

    path = _resolve_sidecar_path(locator, blend_path=blend_path)
    try:
        project, manifest = _open_project_with_manifest(
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

    manifest_hash = manifest.get("manifest_sha256")
    if not _valid_manifest_hash(manifest_hash):
        close_project(project)
        return ProjectLinkResult(
            ProjectLinkStatus.INCOMPATIBLE,
            path,
            message="sidecar manifest does not provide a verified hash",
        )
    if project.id != expected_id or manifest_hash != expected_hash:
        close_project(project)
        return ProjectLinkResult(
            ProjectLinkStatus.MISMATCH,
            path,
            message="sidecar project UUID or manifest hash does not match scene link",
        )
    return ProjectLinkResult(ProjectLinkStatus.CONNECTED, path, project=project)
