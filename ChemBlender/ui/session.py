"""Blender-owned ``ProjectSession`` lifecycle management."""

from dataclasses import dataclass
from pathlib import Path
from weakref import ref

from ..core import close_session, create_session, save_project_session, verify_project_session


RECOVERY_MARKER = ".chemblender-session-recovery"
_SCENE_SESSIONS = {}
_RECOVERY_SESSIONS = {}
_SESSION_CLEANUP_CALLBACKS = []


@dataclass(slots=True)
class _SessionEntry:
    session: object
    status: str = "unlinked"
    message: str = ""
    scene_ref: object | None = None
    scene: object | None = None


def _bpy():
    import bpy

    return bpy


def _scene_key(scene):
    try:
        ref(scene)
    except TypeError:
        return ("pointer", scene.as_pointer())
    return ("weak", id(scene))


def _entry_matches(entry, scene):
    return (
        entry.scene_ref() is scene
        if entry.scene_ref is not None
        else entry.scene is scene
    )


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


def _release_weak_scene(key, scene_ref):
    entry = _SCENE_SESSIONS.get(key)
    if entry is None or entry.scene_ref is not scene_ref:
        return
    _SCENE_SESSIONS.pop(key, None)
    try:
        _close_owned_session(entry.session)
    except BaseException as error:
        _remember_recovery(entry, error)


def _new_entry(scene):
    key = _scene_key(scene)
    session = create_session(temp_parent=Path(_bpy().app.tempdir))
    if key[0] == "weak":
        scene_ref = ref(
            scene,
            lambda reference, key=key: _release_weak_scene(key, reference),
        )
        entry = _SessionEntry(session, scene_ref=scene_ref)
    else:
        entry = _SessionEntry(session, scene=scene)
    _SCENE_SESSIONS[key] = entry
    return entry


def _entry_for(scene):
    key = _scene_key(scene)
    entry = _SCENE_SESSIONS.get(key)
    if entry is not None and not _entry_matches(entry, scene):
        _SCENE_SESSIONS.pop(key, None)
        try:
            _close_owned_session(entry.session)
        except BaseException as error:
            _remember_recovery(entry, error)
        entry = None
    return key, entry


def get_scene_session_status(scene):
    """Return the latest service or recovery status for ``scene``."""
    _key, entry = _entry_for(scene)
    return (entry.status, entry.message) if entry else ("unlinked", "")


def get_scene_session(scene):
    """Return ``scene``'s in-memory session, creating one when needed."""
    _key, entry = _entry_for(scene)
    return entry.session if entry is not None else _new_entry(scene).session


def _write_recovery_marker(session):
    (session.temporary_root / RECOVERY_MARKER).write_text(
        "".join(f"{reason}\n" for reason in sorted(session.dirty_reasons)),
        encoding="utf-8",
    )


def close_scene_session(scene):
    """Close and forget ``scene``'s owned session."""
    key, entry = _entry_for(scene)
    if entry is None:
        return
    try:
        _close_owned_session(entry.session)
    except BaseException as error:
        _set_error(entry, error)
        raise
    _SCENE_SESSIONS.pop(key, None)


def new_scene_session(scene):
    """Replace ``scene``'s session with an empty current-schema session."""
    close_scene_session(scene)
    return _new_entry(scene).session


def _drain_scene_sessions():
    failures = []
    for key, entry in tuple(_SCENE_SESSIONS.items()):
        _SCENE_SESSIONS.pop(key, None)
        try:
            _close_owned_session(entry.session)
        except BaseException as error:
            _remember_recovery(entry, error)
            failures.append(error)
    if not failures:
        return None
    failure = failures[0]
    for error in failures[1:]:
        failure.add_note(f"session cleanup failed: {_failure_message(error)}")
    return failure


def _record_result(scene, result):
    _key, entry = _entry_for(scene)
    entry.status = result.status.value
    entry.message = result.message


def _load_post_handler(_dummy):
    bpy = _bpy()
    cleanup_failure = _drain_scene_sessions()
    for scene in tuple(bpy.data.scenes):
        session = _new_entry(scene).session
        verification_failure = None
        try:
            result = verify_project_session(
                session=session,
                scene=scene,
                blend_path=bpy.data.filepath,
            )
        except BaseException as error:
            verification_failure = error
        else:
            _record_result(scene, result)
        _key, entry = _entry_for(scene)
        if verification_failure is not None:
            if cleanup_failure is not None:
                verification_failure.add_note(
                    f"stale session cleanup failed: {_failure_message(cleanup_failure)}"
                )
            _set_error(entry, verification_failure)
        if cleanup_failure is not None:
            if verification_failure is None:
                _set_error(entry, cleanup_failure)


def _save_pre_handler(_dummy):
    bpy = _bpy()
    blend_path = bpy.data.filepath
    _key, entry = _entry_for(bpy.context.scene)
    if (
        entry is None
        or not entry.session.dirty
        or not blend_path
        or Path(blend_path).suffix.lower() != ".blend"
    ):
        return
    try:
        result = save_project_session(
            session=entry.session,
            scene=bpy.context.scene,
            blend_path=blend_path,
        )
    except BaseException as error:
        _set_error(entry, error)
    else:
        _record_result(bpy.context.scene, result)


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
