import operator
from dataclasses import dataclass

import bpy

from cbq_core.model import AtomFrameProperty
from cbq_core.model import FrameSet
from cbq_core.trajectory_frames import TrajectoryFrameManager
from .dataset_view import (
    _GROUP_NAME, _MODIFIER_NAME, _coordinate_scale, _require_structure_match, write_vector_view,
)


_BINDINGS = {}
_PROPERTY_NAMES = (
    "cb_trajectory_dataset_id",
    "cb_trajectory_dataset_revision",
    "cb_trajectory_frame_start",
    "cb_trajectory_frame_step",
    "cb_trajectory_frame_index",
    "cb_trajectory_cache_size",
    "cb_trajectory_prefetch_ahead",
    "cb_trajectory_force_status",
    "cb_trajectory_frame_label",
    "cb_trajectory_follow_timeline",
    "cb_trajectory_time",
    "cb_trajectory_time_unit",
    "cb_trajectory_time_dataset_id",
    "cb_trajectory_time_dataset_revision",
)


@dataclass(slots=True)
class _TrajectoryBinding:
    obj: object
    manager: TrajectoryFrameManager
    frame_start: int
    frame_step: int
    prefetch_ahead: int
    frame_force: object = None
    follow_timeline: bool = True


def _integer(value, name, *, positive=False):
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    try:
        value = operator.index(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an integer") from error
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _frame_index(scene_frame, binding):
    index = (scene_frame - binding.frame_start) // binding.frame_step
    return min(max(index, 0), binding.manager.frame_count - 1)


def _apply_frame(binding, index):
    import numpy

    values = binding.manager.frame(index)
    scale = _coordinate_scale(binding.manager.unit)
    binding.obj.data.vertices.foreach_set(
        "co", (numpy.asarray(values, dtype=float) * scale).reshape(-1)
    )
    binding.obj["cb_trajectory_frame_index"] = int(index)
    binding.obj["cb_trajectory_frame_label"] = binding.manager.frames.comments[index]
    binding.obj.data.update()
    force = binding.frame_force
    if force is not None:
        # Never leave another frame's force visible on the current coordinates.
        modifier = binding.obj.modifiers.get(_MODIFIER_NAME)
        original_group = modifier.node_group if modifier is not None and modifier.type == "NODES" else None
        shared_before = bpy.data.node_groups.get(_GROUP_NAME)
        try:
            if force.validity_mask is not None and not numpy.all(
                force.validity_mask.values[index]
            ):
                raise ValueError("force values are missing in this frame")
            modifier = write_vector_view(
                binding.obj, force.data.values[index], dataset_id=force.id,
                revision=force.revision, semantic_role=force.semantic_role,
                unit=force.data.unit,
                display_scale=binding.obj.get("cb_vector_display_scale", 1.0),
            )
            # A scientific View owns a copy with its native emission material.
            # Updating vector values must not replace that material with the
            # shared legacy arrow group.
            if original_group is not None and original_group.get("cb_scientific_owned"):
                temporary_group = modifier.node_group
                modifier.node_group = original_group
                if temporary_group != shared_before and temporary_group.users == 0:
                    bpy.data.node_groups.remove(temporary_group)
            elif binding.obj.get("cb_scene_preset_id") == "trajectory_force":
                # The first selected frame may have no forces. Add its material
                # when a later frame first supplies vectors, using saved style.
                import json
                from .scientific_materials import apply_structure_materials

                settings = json.loads(binding.obj["cb_scene_settings_json"])
                apply_structure_materials(binding.obj, opacity=settings["material_opacity"])
        except (ValueError, IndexError) as error:
            if modifier is not None:
                modifier.show_viewport = modifier.show_render = False
            binding.obj["cb_trajectory_force_status"] = str(error)
        else:
            modifier.show_viewport = modifier.show_render = True
            binding.obj["cb_trajectory_force_status"] = "current frame"
    if binding.prefetch_ahead:
        binding.manager.prefetch_around(index, after=binding.prefetch_ahead)


def _apply_binding(binding, scene_frame):
    _apply_frame(binding, _frame_index(scene_frame, binding))


def _frame_change_handler(scene, depsgraph=None):
    del depsgraph
    stale = []
    for key, binding in tuple(_BINDINGS.items()):
        try:
            if binding.follow_timeline and binding.obj.name in scene.objects:
                _apply_binding(binding, scene.frame_current)
        except ReferenceError:
            binding.manager.close()
            stale.append(key)
    for key in stale:
        _BINDINGS.pop(key, None)


def _load_pre_handler(_unused):
    # File loads discard objects and close the previous session's lazy arrays.
    # Release bindings first, before a new file can register playback again.
    for binding in _BINDINGS.values():
        binding.manager.close()
    _BINDINGS.clear()


def _close_session_bindings(session):
    for key, binding in tuple(_BINDINGS.items()):
        if session.project.datasets.get(binding.manager.frames.id) is binding.manager.frames:
            binding.manager.close()
            _BINDINGS.pop(key, None)


def _remove_handlers():
    for handlers, name in (
        (bpy.app.handlers.frame_change_post, "_frame_change_handler"),
        (bpy.app.handlers.load_pre, "_load_pre_handler"),
    ):
        for handler in tuple(handlers):
            if (
                getattr(handler, "__module__", None) == __name__
                and getattr(handler, "__name__", None) == name
            ):
                handlers.remove(handler)


def configure_trajectory_view(
    obj,
    frames,
    *,
    frame_start=1,
    frame_step=1,
    cache_size=3,
    prefetch_ahead=0,
    frame_force=None,
    frame_index=None,
    follow_timeline=True,
):
    if not isinstance(frames, FrameSet):
        raise TypeError("frames must be a FrameSet")
    frame_start = _integer(frame_start, "frame_start")
    frame_step = _integer(frame_step, "frame_step", positive=True)
    cache_size = _integer(cache_size, "cache_size", positive=True)
    prefetch_ahead = _integer(prefetch_ahead, "prefetch_ahead")
    if prefetch_ahead < 0:
        raise ValueError("prefetch_ahead must be non-negative")
    if type(follow_timeline) is not bool:
        raise TypeError("follow_timeline must be boolean")
    if frame_index is not None:
        frame_index = _integer(frame_index, "frame_index")
        if not 0 <= frame_index < frames.data.shape[0]:
            raise IndexError("trajectory frame index is outside the frame set")
    _require_structure_match(obj, frames.structure_id, frames.data.shape[1])
    if frame_force is not None and (
        not isinstance(frame_force, AtomFrameProperty)
        or frame_force.frame_set_id != frames.id
        or frame_force.semantic_role != "atomic_force"
        or frame_force.data.dims != ("frame", "atom", "xyz")
        or frame_force.data.shape != frames.data.shape
    ):
        raise ValueError("force dataset does not match the selected trajectory")
    key = obj.as_pointer()
    manager = TrajectoryFrameManager(frames, cache_size=cache_size)
    binding = _TrajectoryBinding(
        obj, manager, frame_start, frame_step, prefetch_ahead, frame_force, follow_timeline
    )
    try:
        if frame_index is None:
            _apply_binding(binding, bpy.context.scene.frame_current)
        else:
            _apply_frame(binding, frame_index)
    except Exception:
        manager.close()
        raise
    previous = _BINDINGS.get(key)
    if previous is not None:
        previous.manager.close()
    _BINDINGS[key] = binding
    obj["cb_trajectory_dataset_id"] = str(frames.id)
    obj["cb_trajectory_dataset_revision"] = frames.revision
    obj["cb_trajectory_frame_start"] = frame_start
    obj["cb_trajectory_frame_step"] = frame_step
    obj["cb_trajectory_cache_size"] = cache_size
    obj["cb_trajectory_prefetch_ahead"] = prefetch_ahead
    obj["cb_trajectory_follow_timeline"] = follow_timeline


def apply_trajectory_frame(obj, frames, index, *, frame_force=None, frame_start=1, frame_step=1):
    """Set one scientific frame, recreating a lost runtime manager after reopen."""
    index = _integer(index, "index")
    if not 0 <= index < frames.data.shape[0]:
        raise IndexError("trajectory frame index is outside the frame set")
    binding = _BINDINGS.get(obj.as_pointer())
    if binding is None or binding.manager.frames is not frames or binding.frame_force is not frame_force:
        configure_trajectory_view(obj, frames, frame_start=frame_start, frame_step=frame_step,
            frame_index=index, follow_timeline=False, frame_force=frame_force)
    else:
        _apply_frame(binding, index)


def clear_trajectory_view(obj):
    key = obj.as_pointer()
    binding = _BINDINGS.pop(key, None)
    if binding is not None:
        binding.manager.close()
    for name in _PROPERTY_NAMES:
        if name in obj:
            del obj[name]


def register():
    from .ui.session import register_session_cleanup

    register_session_cleanup(_close_session_bindings)
    _remove_handlers()
    bpy.app.handlers.frame_change_post.append(_frame_change_handler)
    bpy.app.handlers.persistent(_load_pre_handler)
    bpy.app.handlers.load_pre.append(_load_pre_handler)


def unregister():
    from .ui.session import unregister_session_cleanup

    unregister_session_cleanup(_close_session_bindings)
    _load_pre_handler(None)
    _remove_handlers()
