import shutil
from pathlib import Path
from uuid import UUID, uuid4

from ..model import ImportBatch


_OWNER_MARKER = ".chemblender-import-owner"


def _is_link_like(path):
    return path.is_symlink() or path.is_junction()


def _path_identity(path):
    stat = path.stat(follow_symlinks=False)
    return stat.st_dev, stat.st_ino


class StagedImportSession:
    __slots__ = (
        "_artifact_identity",
        "_artifact_root",
        "_discarded",
        "_id",
        "_marker_identity",
        "_results",
        "_root",
        "_root_identity",
    )

    def __init__(self):
        raise TypeError("use StagedImportSession.create()")

    @classmethod
    def create(cls, *, temp_parent):
        if not isinstance(temp_parent, Path):
            raise TypeError("temp_parent must be a Path")
        parent = temp_parent.resolve(strict=True)
        if not parent.is_dir():
            raise ValueError("temp_parent must be a directory")
        workspace = parent / "chemblender-import-staging"
        workspace.mkdir(exist_ok=True)
        if _is_link_like(workspace) or workspace.resolve(strict=True).parent != parent:
            raise RuntimeError("staging workspace must stay beneath temp_parent")

        session_id = uuid4()
        root = workspace / str(session_id)
        root.mkdir()
        marker = root / _OWNER_MARKER
        artifact_root = root / "artifacts"
        try:
            with marker.open("xb") as stream:
                stream.write(f"{session_id}\n".encode("utf-8"))
            artifact_root.mkdir()
        except Exception:
            if artifact_root.is_dir() and not _is_link_like(artifact_root):
                artifact_root.rmdir()
            if marker.is_file() and not _is_link_like(marker):
                marker.unlink()
            root.rmdir()
            raise

        instance = object.__new__(cls)
        instance._id = session_id
        instance._root = root.resolve(strict=True)
        instance._artifact_root = artifact_root.resolve(strict=True)
        instance._root_identity = _path_identity(instance._root)
        instance._artifact_identity = _path_identity(instance._artifact_root)
        instance._marker_identity = _path_identity(marker)
        instance._results = {}
        instance._discarded = False
        return instance

    @property
    def id(self):
        return self._id

    @property
    def root(self):
        return self._root

    @property
    def artifact_root(self):
        return self._artifact_root

    @property
    def result_ids(self):
        return tuple(self._results)

    def register_result(self, result_id, batch):
        if self._discarded:
            raise RuntimeError("staged import session was discarded")
        if type(result_id) is not UUID:
            raise TypeError("result_id must be a UUID")
        if type(batch) is not ImportBatch:
            raise TypeError("batch must be an ImportBatch")
        if result_id in self._results:
            raise ValueError("result id is already registered")
        self._results[result_id] = batch

    def result(self, result_id):
        if self._discarded:
            raise RuntimeError("staged import session was discarded")
        if type(result_id) is not UUID:
            raise TypeError("result_id must be a UUID")
        return self._results[result_id]

    def discard(self):
        if self._discarded:
            return
        root = self._root
        if _is_link_like(root) or not root.is_dir():
            raise RuntimeError("refusing to remove an unsafe staging root")
        try:
            resolved = root.resolve(strict=True)
        except OSError as error:
            raise RuntimeError("refusing to remove an unsafe staging root") from error
        if (
            resolved != root
            or resolved.name != str(self._id)
            or resolved.parent.name != "chemblender-import-staging"
            or _path_identity(resolved) != self._root_identity
        ):
            raise RuntimeError("refusing to remove an unowned staging root")

        marker = resolved / _OWNER_MARKER
        if _is_link_like(marker) or not marker.is_file():
            raise RuntimeError("staging ownership marker is missing or unsafe")
        try:
            marker_identity = _path_identity(marker)
            marker_content = marker.read_bytes()
        except OSError as error:
            raise RuntimeError("cannot read the staging ownership marker") from error
        if (
            marker_identity != self._marker_identity
            or marker_content != f"{self._id}\n".encode("utf-8")
        ):
            raise RuntimeError("staging ownership marker does not match")

        artifact_root = self._artifact_root
        if (
            _is_link_like(artifact_root)
            or not artifact_root.is_dir()
            or artifact_root.resolve(strict=True).parent != resolved
            or _path_identity(artifact_root) != self._artifact_identity
        ):
            raise RuntimeError("refusing to remove an unsafe artifact root")

        shutil.rmtree(resolved)
        self._results.clear()
        self._discarded = True
