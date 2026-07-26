"""Blender-owned ``ProjectSession`` lifecycle management."""

from dataclasses import dataclass
from pathlib import Path

from ..core import close_session, create_session
from ..core.project_service import (
    save_project_session_for_scenes,
    sync_project_session_links_for_scenes,
    verify_project_session_for_scenes,
)
from .view_cache import repair_project_view_caches


RECOVERY_MARKER = ".chemblender-session-recovery"
_FILE_SESSION = None
_RECOVERY_SESSIONS = {}
_SESSION_CLEANUP_CALLBACKS = []
_SESSION_MUTATION_CALLBACKS = []


@dataclass(slots=True)
class _SessionEntry:
    session: object
    status: str = "unlinked"
    message: str = ""


def _bpy():
    import bpy

    return bpy


def _failure_message(error):
    return "; ".join((str(error), *getattr(error, "__notes__", ())))


def _set_error(entry, error):
    entry.status = "error"
    entry.message = _failure_message(error)


def register_session_cleanup(callback):
    """Register an idempotent UI cleanup callback for session teardown."""
    if not callable(callback):
        raise TypeError("callback must be callable")
    if callback not in _SESSION_CLEANUP_CALLBACKS:
        _SESSION_CLEANUP_CALLBACKS.append(callback)


def unregister_session_cleanup(callback):
    """Remove a previously registered UI cleanup callback."""
    while callback in _SESSION_CLEANUP_CALLBACKS:
        _SESSION_CLEANUP_CALLBACKS.remove(callback)


def register_session_mutation(callback):
    """Register a small UI projection invalidator."""
    if not callable(callback):
        raise TypeError("callback must be callable")
    if callback not in _SESSION_MUTATION_CALLBACKS:
        _SESSION_MUTATION_CALLBACKS.append(callback)


def unregister_session_mutation(callback):
    while callback in _SESSION_MUTATION_CALLBACKS:
        _SESSION_MUTATION_CALLBACKS.remove(callback)


def _notify_session_mutation(session):
    for callback in tuple(_SESSION_MUTATION_CALLBACKS):
        callback(session)


def _run_session_cleanups(session):
    failure = None
    for callback in tuple(_SESSION_CLEANUP_CALLBACKS):
        try:
            callback(session)
        except BaseException as error:
            if failure is None:
                failure = error
            else:
                failure.add_note(f"UI cleanup failed: {_failure_message(error)}")
    return failure


def _close_session(session, *, preserve_temporary=False):
    failure = None
    if session.dirty:
        try:
            _write_recovery_marker(session)
        except BaseException as error:
            failure = error
        try:
            close_session(session, remove_temporary=False)
        except BaseException as error:
            if failure is None:
                failure = error
            else:
                failure.add_note(f"session close failed: {error}")
    else:
        close_session(session, remove_temporary=not preserve_temporary)
    if failure is not None:
        raise failure


def _close_owned_session(session):
    cleanup_failure = _run_session_cleanups(session)
    close_failure = None
    try:
        _close_session(
            session,
            preserve_temporary=cleanup_failure is not None,
        )
    except BaseException as error:
        close_failure = error
    if cleanup_failure is not None:
        if close_failure is not None:
            cleanup_failure.add_note(
                f"session close failed: {_failure_message(close_failure)}"
            )
        raise cleanup_failure
    if close_failure is not None:
        raise close_failure


def _remember_recovery(entry, error):
    _set_error(entry, error)
    _RECOVERY_SESSIONS[entry.session.id] = entry


def _new_entry(*, notify=True):
    global _FILE_SESSION
    session = create_session(temp_parent=Path(_bpy().app.tempdir))
    entry = _SessionEntry(session)
    _FILE_SESSION = entry
    if notify:
        _notify_session_mutation(session)
    return entry


def get_scene_session_status(scene):
    """Return the latest service or recovery status for ``scene``."""
    entry = _FILE_SESSION
    return (entry.status, entry.message) if entry else ("unlinked", "")


def get_scene_session(scene):
    """Return the loaded Blender file's shared session."""
    entry = _FILE_SESSION
    return entry.session if entry is not None else _new_entry().session


def _write_recovery_marker(session):
    (session.temporary_root / RECOVERY_MARKER).write_text(
        "".join(f"{reason}\n" for reason in sorted(session.dirty_reasons)),
        encoding="utf-8",
    )


def close_scene_session(scene):
    """Close and forget the loaded Blender file's shared session."""
    global _FILE_SESSION
    entry = _FILE_SESSION
    if entry is None:
        return
    try:
        _close_owned_session(entry.session)
    except BaseException as error:
        _set_error(entry, error)
        raise
    _FILE_SESSION = None


def new_scene_session(scene):
    """Replace the loaded Blender file's session with an empty session."""
    close_scene_session(scene)
    return _new_entry().session


def _drain_scene_sessions():
    global _FILE_SESSION
    entry = _FILE_SESSION
    _FILE_SESSION = None
    if entry is None:
        return None
    try:
        _close_owned_session(entry.session)
    except BaseException as error:
        _remember_recovery(entry, error)
        return error
    return None


def _record_result(result):
    entry = _FILE_SESSION
    entry.status = result.status.value
    entry.message = result.message


def _load_post_handler(_dummy):
    bpy = _bpy()
    cleanup_failure = _drain_scene_sessions()
    session = _new_entry(notify=False).session
    verification_failure = None
    try:
        result = verify_project_session_for_scenes(
            session=session,
            scenes=tuple(bpy.data.scenes),
            blend_path=bpy.data.filepath,
        )
    except BaseException as error:
        verification_failure = error
    else:
        if result.status.value != "unsaved":
            _record_result(result)
        if result.status.value == "connected":
            try:
                repair_project_view_caches(
                    session=session,
                    objects=tuple(getattr(bpy.data, "objects", ())),
                    blend_path=bpy.data.filepath,
                )
                _notify_session_mutation(session)
            except BaseException as error:
                verification_failure = error
    entry = _FILE_SESSION
    if verification_failure is not None:
        if cleanup_failure is not None:
            verification_failure.add_note(
                f"stale session cleanup failed: {_failure_message(cleanup_failure)}"
            )
        _set_error(entry, verification_failure)
    if cleanup_failure is not None and verification_failure is None:
        _set_error(entry, cleanup_failure)


def _save_pre_handler(_dummy):
    bpy = _bpy()
    blend_path = bpy.data.filepath
    entry = _FILE_SESSION
    if (
        entry is None
        or not blend_path
        or Path(blend_path).suffix.lower() != ".blend"
    ):
        return
    session = entry.session
    reasons = session.dirty_reasons
    if not reasons and (
        session.sidecar_path is None
        or session.link_status != "connected"
    ):
        return
    link_retry_reasons = {"project_link", "view_cache"}
    desired_sidecar = Path(blend_path).resolve().with_suffix(".cbq")
    same_sidecar = (
        session.sidecar_path is not None
        and Path(session.sidecar_path).resolve() == desired_sidecar
    )
    link_only = (
        same_sidecar
        and (
            not reasons
            or reasons <= link_retry_reasons
        )
    )
    try:
        if link_only:
            result = sync_project_session_links_for_scenes(
                session=session,
                scenes=tuple(bpy.data.scenes),
                blend_path=blend_path,
            )
        else:
            result = save_project_session_for_scenes(
                session=session,
                scenes=tuple(bpy.data.scenes),
                blend_path=blend_path,
            )
        _record_result(result)
        if session.link_status == "connected":
            repair_project_view_caches(
                session=session,
                objects=tuple(getattr(bpy.data, "objects", ())),
                blend_path=blend_path,
            )
    except BaseException as error:
        _set_error(entry, error)


def _register_handler(callbacks, handler):
    while handler in callbacks:
        callbacks.remove(handler)
    callbacks.append(handler)


def _remove_handler(callbacks, handler):
    while handler in callbacks:
        callbacks.remove(handler)


def register():
    handlers = _bpy().app.handlers
    handlers.persistent(_load_post_handler)
    handlers.persistent(_save_pre_handler)
    _register_handler(handlers.load_post, _load_post_handler)
    _register_handler(handlers.save_pre, _save_pre_handler)


def unregister():
    handlers = _bpy().app.handlers
    _remove_handler(handlers.load_post, _load_post_handler)
    _remove_handler(handlers.save_pre, _save_pre_handler)
    failure = _drain_scene_sessions()
    for session_id, entry in tuple(_RECOVERY_SESSIONS.items()):
        try:
            _close_owned_session(entry.session)
        except BaseException as error:
            _set_error(entry, error)
            if failure is None:
                failure = error
            else:
                failure.add_note(f"session cleanup failed: {_failure_message(error)}")
        else:
            _RECOVERY_SESSIONS.pop(session_id, None)
    if failure is not None:
        raise failure
