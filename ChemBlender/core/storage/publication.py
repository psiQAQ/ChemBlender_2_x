import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from ..model import QCProject
from ..session import ProjectSession
from ..sidecar import (
    _open_project_with_manifest,
    _write_project_tree,
    close_project,
)
from ..sidecar_migrations import CURRENT_PROJECT_SCHEMA_VERSION


_ORPHAN_SUFFIX = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})\.(tmp|backup)"
)


@dataclass(frozen=True, slots=True)
class PublishedProject:
    path: Path
    project_id: UUID
    schema_version: str
    manifest_sha256: str
    generation_id: UUID


@dataclass(frozen=True, slots=True)
class PublicationRecoveryReport:
    destination: Path
    temporary_paths: tuple[Path, ...]
    backup_paths: tuple[Path, ...]

    @property
    def has_orphans(self):
        return bool(self.temporary_paths or self.backup_paths)


class PublicationRecoveryError(RuntimeError):
    def __init__(
        self,
        *,
        publication_error,
        rollback_error,
        report,
        candidate_path,
        destination_path,
        backup_path,
    ):
        super().__init__(
            f"sidecar publication failed ({publication_error}) and rollback "
            f"was incomplete ({rollback_error})"
        )
        self.publication_error = publication_error
        self.rollback_error = rollback_error
        self.report = report
        self.candidate_path = candidate_path
        self.destination_path = destination_path
        self.backup_path = backup_path


def _is_link_like(path):
    return path.is_symlink() or (
        hasattr(path, "is_junction") and path.is_junction()
    )


def _validated_destination(destination):
    destination = Path(destination)
    if destination.suffix.lower() != ".cbq":
        raise ValueError("published sidecar must use the .cbq suffix")
    if _is_link_like(destination):
        raise ValueError("published sidecar destination must not be a link")
    parent = destination.parent
    try:
        parent = parent.resolve(strict=True)
    except OSError as error:
        raise ValueError("published sidecar parent must exist") from error
    if not parent.is_dir():
        raise ValueError("published sidecar parent must be a directory")
    destination = parent / destination.name
    if destination.exists() and not destination.is_dir():
        raise ValueError("published sidecar destination must be a directory")
    return destination


def _new_stage(destination):
    while True:
        path = destination.parent / f".{destination.name}.{uuid4()}.tmp"
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return path


def _new_backup(destination):
    while True:
        path = destination.parent / f".{destination.name}.{uuid4()}.backup"
        if not path.exists() and not _is_link_like(path):
            return path


def _verified_project(path, project_id):
    project, manifest = _open_project_with_manifest(
        path,
        expected_project_id=project_id,
        expected_schema_version=CURRENT_PROJECT_SCHEMA_VERSION,
        verify_arrays=True,
    )
    try:
        return PublishedProject(
            path=path,
            project_id=project_id,
            schema_version=manifest["project_schema_version"],
            manifest_sha256=manifest["manifest_sha256"],
            generation_id=UUID(manifest["generation_id"]),
        )
    finally:
        close_project(project)


def _verify_staged_project(path, project_id):
    return _verified_project(path, project_id)


def _verify_published_project(path, project_id):
    return _verified_project(path, project_id)


def _same_generation(left, right):
    return (
        left.project_id == right.project_id
        and left.schema_version == right.schema_version
        and left.manifest_sha256 == right.manifest_sha256
        and left.generation_id == right.generation_id
    )


def _recovery_error(
    *,
    publication_error,
    rollback_error,
    destination,
    candidate,
    backup,
):
    try:
        report = _orphan_report(destination)
    except OSError:
        temporary_paths = (
            (candidate,)
            if candidate is not None
            and candidate != destination
            and candidate.name.endswith(".tmp")
            else ()
        )
        backup_paths = (backup,) if backup is not None else ()
        report = PublicationRecoveryReport(
            destination=destination,
            temporary_paths=temporary_paths,
            backup_paths=backup_paths,
        )
    return PublicationRecoveryError(
        publication_error=publication_error,
        rollback_error=rollback_error,
        report=report,
        candidate_path=candidate,
        destination_path=destination,
        backup_path=backup,
    )


def _restore_final_failure(destination, stage, backup, staged, publication_error):
    try:
        current = _verified_project(destination, staged.project_id)
        if not _same_generation(staged, current):
            raise RuntimeError(
                "destination no longer contains the staged generation"
            )
    except Exception as rollback_error:
        raise _recovery_error(
            publication_error=publication_error,
            rollback_error=rollback_error,
            destination=destination,
            candidate=destination,
            backup=backup,
        ) from publication_error

    try:
        os.replace(destination, stage)
    except Exception as rollback_error:
        raise _recovery_error(
            publication_error=publication_error,
            rollback_error=rollback_error,
            destination=destination,
            candidate=destination,
            backup=backup,
        ) from publication_error

    if backup is not None and backup.exists():
        try:
            os.replace(backup, destination)
        except Exception as rollback_error:
            raise _recovery_error(
                publication_error=publication_error,
                rollback_error=rollback_error,
                destination=destination,
                candidate=stage,
                backup=backup,
            ) from publication_error


def solidify_session(session, destination):
    if not isinstance(session, ProjectSession):
        raise TypeError("session must be a ProjectSession")
    if not isinstance(session.project, QCProject):
        raise TypeError("session.project must be a QCProject")
    destination = _validated_destination(destination)
    stage = _new_stage(destination)
    backup = None
    _write_project_tree(stage, session.project)
    staged = _verify_staged_project(stage, session.project.id)

    if destination.exists():
        backup = _new_backup(destination)
        os.replace(destination, backup)
    try:
        os.replace(stage, destination)
    except Exception as publication_error:
        if backup is not None and backup.exists():
            try:
                os.replace(backup, destination)
            except Exception as rollback_error:
                raise _recovery_error(
                    publication_error=publication_error,
                    rollback_error=rollback_error,
                    destination=destination,
                    candidate=stage,
                    backup=backup,
                ) from publication_error
        raise

    try:
        published = _verify_published_project(destination, session.project.id)
        if not _same_generation(staged, published):
            raise RuntimeError(
                "published generation does not match verified stage"
            )
    except Exception as publication_error:
        _restore_final_failure(
            destination,
            stage,
            backup,
            staged,
            publication_error,
        )
        raise

    if backup is not None:
        try:
            shutil.rmtree(backup)
        except OSError:
            pass
    session.sidecar_path = destination
    return published


def inspect_publication_orphans(destination):
    destination = _validated_destination(destination)
    return _orphan_report(destination)


def _orphan_report(destination):
    prefix = f".{destination.name}."
    temporary = []
    backups = []
    for path in destination.parent.iterdir():
        if (
            not path.name.startswith(prefix)
            or not path.is_dir()
            or _is_link_like(path)
        ):
            continue
        match = _ORPHAN_SUFFIX.fullmatch(path.name[len(prefix) :])
        if match is None:
            continue
        try:
            identifier = UUID(match.group(1))
        except ValueError:
            continue
        if str(identifier) != match.group(1):
            continue
        if match.group(2) == "tmp":
            temporary.append(path.resolve())
        else:
            backups.append(path.resolve())
    return PublicationRecoveryReport(
        destination=destination,
        temporary_paths=tuple(sorted(temporary, key=lambda path: path.name)),
        backup_paths=tuple(sorted(backups, key=lambda path: path.name)),
    )
