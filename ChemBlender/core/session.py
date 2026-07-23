import shutil
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from .model import QCProject
from .sidecar import close_project
from .sidecar_migrations import CURRENT_PROJECT_SCHEMA_VERSION


_OWNER_MARKER = ".chemblender-session-owner"


def _is_link_like(path):
    return path.is_symlink() or path.is_junction()


def _dirty_reason(value):
    if not isinstance(value, str):
        raise TypeError("dirty reason must be a string")
    if not value or value.strip() != value:
        raise ValueError("dirty reason must be non-empty without surrounding whitespace")
    return value


@dataclass(slots=True)
class ProjectSession:
    id: UUID
    project: QCProject
    temporary_root: Path
    sidecar_path: Path | None = None
    active_entity_id: UUID | None = None
    active_view_object_name: str | None = None
    link_status: str = "unlinked"
    _dirty_reasons: set[str] = field(default_factory=set, init=False, repr=False)
    _owned_temporary_root: Path = field(init=False, repr=False)

    def __post_init__(self):
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")
        if not isinstance(self.project, QCProject):
            raise TypeError("project must be a QCProject")
        self.temporary_root = Path(self.temporary_root)
        self._owned_temporary_root = self.temporary_root
        if self.sidecar_path is not None:
            self.sidecar_path = Path(self.sidecar_path)

    @property
    def dirty(self):
        return bool(self._dirty_reasons)

    @property
    def dirty_reasons(self):
        return frozenset(self._dirty_reasons)

    def mark_dirty(self, reason):
        self._dirty_reasons.add(_dirty_reason(reason))

    def clear_dirty(self, reason):
        self._dirty_reasons.remove(_dirty_reason(reason))


def create_session(*, temp_parent, project=None):
    if project is None:
        project = QCProject(
            id=uuid4(),
            schema_version=CURRENT_PROJECT_SCHEMA_VERSION,
        )
    elif not isinstance(project, QCProject):
        raise TypeError("project must be a QCProject")

    parent = Path(temp_parent).resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("temp_parent must be a directory")
    workspace = parent / "chemblender"
    workspace.mkdir(exist_ok=True)
    if _is_link_like(workspace) or workspace.resolve(strict=True).parent != parent:
        raise RuntimeError("session workspace must stay beneath temp_parent")

    session_id = uuid4()
    root = workspace / str(session_id)
    root.mkdir()
    marker = root / _OWNER_MARKER
    marker_created = False
    try:
        with marker.open("xb") as stream:
            marker_created = True
            stream.write(f"{session_id}\n".encode("utf-8"))
    except Exception:
        if marker_created:
            try:
                marker.unlink()
            except OSError:
                pass
        try:
            root.rmdir()
        except OSError:
            pass
        raise
    return ProjectSession(
        id=session_id,
        project=project,
        temporary_root=root,
    )


def close_session(session, *, remove_temporary=True):
    if not isinstance(session, ProjectSession):
        raise TypeError("session must be a ProjectSession")
    close_project(session.project)
    if not remove_temporary:
        return

    root = Path(session.temporary_root)
    if _is_link_like(root) or not root.is_dir():
        raise RuntimeError("refusing to remove an unsafe session root")
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise RuntimeError("refusing to remove an unsafe session root") from error
    if (
        resolved != session._owned_temporary_root
        or resolved.name != str(session.id)
        or resolved.parent.name != "chemblender"
    ):
        raise RuntimeError("refusing to remove an unowned session root")

    marker = resolved / _OWNER_MARKER
    if marker.is_symlink() or not marker.is_file():
        raise RuntimeError("session ownership marker is missing")
    try:
        marker_content = marker.read_bytes()
    except OSError as error:
        raise RuntimeError("cannot read the session ownership marker") from error
    if marker_content != f"{session.id}\n".encode("utf-8"):
        raise RuntimeError("session ownership marker does not match")
    shutil.rmtree(resolved)
