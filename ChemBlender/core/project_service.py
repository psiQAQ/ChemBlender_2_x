import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .model import QCProject
from .session import ProjectSession
from .sidecar import (
    SidecarCompatibilityError,
    SidecarIntegrityError,
    SidecarNotFoundError,
    _open_project_with_manifest,
    close_project,
)
from .storage.publication import solidify_session


class ProjectServiceStatus(str, Enum):
    UNSAVED = "unsaved"
    CONNECTED = "connected"
    MISSING = "missing"
    MISMATCH = "mismatch"
    INCOMPATIBLE = "incompatible"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class ProjectServiceResult:
    status: ProjectServiceStatus
    message: str = ""
    path: Path | None = None
    manifest_sha256: str | None = None
    project: QCProject | None = None


@dataclass(frozen=True, slots=True)
class CacheClearResult:
    sidecar_path: Path
    removed_paths: tuple[Path, ...]
    failed_path: Path | None = None
    message: str = ""

    @property
    def removed_count(self):
        return len(self.removed_paths)

    @property
    def complete(self):
        return self.failed_path is None


def _require_session(session):
    if not isinstance(session, ProjectSession):
        raise TypeError("session must be a ProjectSession")


def _service_status(status):
    return ProjectServiceStatus(status.value)


def _project_links():
    from .. import project_link

    return project_link


def _error_result(error, path, expected_project):
    if isinstance(error, SidecarNotFoundError):
        status = ProjectServiceStatus.MISSING
    elif isinstance(error, SidecarIntegrityError):
        status = ProjectServiceStatus.INVALID
    else:
        try:
            candidate, _manifest = _open_project_with_manifest(
                path,
                expected_schema_version=expected_project.schema_version,
                verify_arrays=True,
            )
        except SidecarNotFoundError:
            status = ProjectServiceStatus.MISSING
        except SidecarIntegrityError:
            status = ProjectServiceStatus.INVALID
        except SidecarCompatibilityError:
            status = ProjectServiceStatus.INCOMPATIBLE
        else:
            try:
                status = (
                    ProjectServiceStatus.MISMATCH
                    if candidate.id != expected_project.id
                    else ProjectServiceStatus.INCOMPATIBLE
                )
            finally:
                close_project(candidate)
    return ProjectServiceResult(status, str(error), path)


def _adopt_project(session, project, path):
    previous = session.project
    close_project(previous)
    session.project = project
    session.sidecar_path = path
    session.link_status = ProjectServiceStatus.CONNECTED.value


def save_project_session(*, session, scene, blend_path):
    _require_session(session)
    if not blend_path:
        return ProjectServiceResult(
            ProjectServiceStatus.UNSAVED,
            "save the Blender file before publishing its project",
        )
    blend = Path(blend_path)
    if blend.suffix.lower() != ".blend":
        return ProjectServiceResult(
            ProjectServiceStatus.INVALID,
            "saved Blender path must use the .blend suffix",
            blend,
        )
    destination = blend.resolve().with_suffix(".cbq")
    published = solidify_session(session, destination)
    links = _project_links()
    try:
        links.write_project_link(
            scene,
            session.project,
            destination,
            blend_path=blend,
        )
    except (SidecarNotFoundError, SidecarCompatibilityError, SidecarIntegrityError) as error:
        result = _error_result(error, destination, session.project)
        session.sidecar_path = published.path
        session.link_status = result.status.value
        return result
    except Exception:
        session.sidecar_path = published.path
        session.link_status = ProjectServiceStatus.INVALID.value
        raise
    session.link_status = ProjectServiceStatus.CONNECTED.value
    return ProjectServiceResult(
        ProjectServiceStatus.CONNECTED,
        path=published.path,
        manifest_sha256=scene[links.MANIFEST_HASH_KEY],
        project=session.project,
    )


def verify_project_session(
    *,
    session,
    scene,
    blend_path=None,
    verify_arrays=True,
):
    _require_session(session)
    links = _project_links()
    resolved = links.resolve_project_link(
        scene,
        blend_path=blend_path,
        verify_arrays=verify_arrays,
    )
    status = _service_status(resolved.status)
    if status is not ProjectServiceStatus.CONNECTED:
        return ProjectServiceResult(status, resolved.message, resolved.path)
    _adopt_project(session, resolved.project, resolved.path)
    return ProjectServiceResult(
        status,
        resolved.message,
        resolved.path,
        scene[links.MANIFEST_HASH_KEY],
        session.project,
    )


def relink_project_session(
    *,
    session,
    scene,
    sidecar_path,
    blend_path=None,
):
    _require_session(session)
    links = _project_links()
    path = Path(sidecar_path).resolve()
    candidate_scene = {}
    try:
        links.write_project_link(
            candidate_scene,
            session.project,
            path,
            blend_path=blend_path,
        )
    except (SidecarNotFoundError, SidecarCompatibilityError, SidecarIntegrityError) as error:
        return _error_result(error, path, session.project)

    resolved = links.resolve_project_link(candidate_scene, blend_path=blend_path)
    status = _service_status(resolved.status)
    if status is not ProjectServiceStatus.CONNECTED:
        return ProjectServiceResult(status, resolved.message, resolved.path)
    try:
        links._write_scene_values(
            scene,
            {
                key: candidate_scene[key]
                for key in (
                    links.PROJECT_ID_KEY,
                    links.PROJECT_SCHEMA_KEY,
                    links.SIDECAR_LOCATOR_KEY,
                    links.MANIFEST_HASH_KEY,
                )
            },
        )
    except Exception:
        close_project(resolved.project)
        raise
    _adopt_project(session, resolved.project, resolved.path)
    return ProjectServiceResult(
        status,
        resolved.message,
        resolved.path,
        candidate_scene[links.MANIFEST_HASH_KEY],
        session.project,
    )


def _is_link_like(path):
    return path.is_symlink() or (
        hasattr(path, "is_junction") and path.is_junction()
    )


def _validate_cache_tree(path, root):
    if _is_link_like(path):
        raise ValueError("refusing to clear a linked cache path")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("cache path must stay inside the sidecar") from error
    pending = [path]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                child = Path(entry.path)
                if _is_link_like(child):
                    raise ValueError("refusing to clear a linked cache child")
                if entry.is_dir(follow_symlinks=False):
                    pending.append(child)


def clear_derived_cache(*, sidecar_path):
    root = Path(sidecar_path)
    if root.suffix.lower() != ".cbq":
        raise ValueError("sidecar directory must use the .cbq suffix")
    if _is_link_like(root):
        raise ValueError("sidecar root must not be a link")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("sidecar root must be a directory")
    cache = root / "cache"
    if _is_link_like(cache):
        raise ValueError("sidecar cache root must be a directory, not a link")
    if not cache.exists():
        return CacheClearResult(root, ())
    if not cache.is_dir():
        raise ValueError("sidecar cache root must be a directory, not a link")

    targets = []
    for path in (cache / "derivation", cache / "render"):
        if _is_link_like(path):
            raise ValueError("refusing to clear a linked cache path")
        if path.exists():
            targets.append(path)
    targets = tuple(targets)
    for path in targets:
        if not path.is_dir():
            raise ValueError("derived cache namespace must be a directory")
        _validate_cache_tree(path, root)

    removed = []
    for path in targets:
        try:
            shutil.rmtree(path)
        except OSError as error:
            return CacheClearResult(root, tuple(removed), path, str(error))
        removed.append(path)
    return CacheClearResult(root, tuple(removed))
