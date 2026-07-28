import shutil
from dataclasses import fields, is_dataclass
from pathlib import Path
from uuid import UUID, uuid4

from ..model import ImportBatch


_OWNER_MARKER = ".chemblender-import-owner"


def _collect_mapped_buffers(value, seen, views, memmaps, numpy):
    identity = id(value)
    if identity in seen:
        return
    seen.add(identity)
    if isinstance(value, memoryview):
        try:
            owner = value.obj
        except ValueError:
            return
        views.append(value)
        _collect_mapped_buffers(owner, seen, views, memmaps, numpy)
        return
    if isinstance(value, numpy.memmap):
        memmaps.append(value)
        return
    if isinstance(value, numpy.ndarray):
        base = getattr(value, "base", None)
        if base is not None:
            _collect_mapped_buffers(base, seen, views, memmaps, numpy)
        return
    if isinstance(value, tuple):
        for item in value:
            _collect_mapped_buffers(item, seen, views, memmaps, numpy)
    elif is_dataclass(value):
        for field in fields(value):
            _collect_mapped_buffers(
                getattr(value, field.name),
                seen,
                views,
                memmaps,
                numpy,
            )


def _close_memmaps(value, seen):
    import numpy

    views = []
    memmaps = []
    _collect_mapped_buffers(value, seen, views, memmaps, numpy)
    for view in reversed(views):
        view.release()
    closed = set()
    for value in memmaps:
        mmap = getattr(value, "_mmap", None)
        if mmap is not None and id(mmap) not in closed:
            mmap.close()
            closed.add(id(mmap))


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
        "_materializers",
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
        instance._materializers = {}
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

    def register_result(self, result_id, batch, *, materializer=None):
        if self._discarded:
            raise RuntimeError("staged import session was discarded")
        if type(result_id) is not UUID:
            raise TypeError("result_id must be a UUID")
        if type(batch) is not ImportBatch:
            raise TypeError("batch must be an ImportBatch")
        if materializer is not None and not callable(materializer):
            raise TypeError("materializer must be callable or None")
        if result_id in self._results:
            raise ValueError("result id is already registered")
        self._results[result_id] = batch
        if materializer is not None:
            self._materializers[result_id] = materializer

    def result(self, result_id):
        if self._discarded:
            raise RuntimeError("staged import session was discarded")
        if type(result_id) is not UUID:
            raise TypeError("result_id must be a UUID")
        return self._results[result_id]

    def has_pending_materializer(self, result_id):
        self.result(result_id)
        return result_id in self._materializers

    def materialize_result(
        self,
        result_id,
        *,
        progress=lambda _stage, _completed, _total: None,
        is_cancelled=lambda: False,
    ):
        current = self.result(result_id)
        if not callable(progress) or not callable(is_cancelled):
            raise TypeError("progress and is_cancelled must be callable")
        materializer = self._materializers.get(result_id)
        if materializer is None:
            return current
        replacement = materializer(progress, is_cancelled)
        if replacement is None:
            replacement = current
        if type(replacement) is not ImportBatch:
            raise TypeError("materializer must return ImportBatch or None")
        self._results[result_id] = replacement
        del self._materializers[result_id]
        if replacement is not current:
            _close_memmaps(current, set())
        return replacement

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

        _close_memmaps(tuple(self._results.values()), set())
        shutil.rmtree(resolved)
        self._materializers.clear()
        self._results.clear()
        self._discarded = True
