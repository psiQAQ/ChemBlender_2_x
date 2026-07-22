import operator
from dataclasses import dataclass

import bpy

from .core import FrameSet, TrajectoryFrameManager
from .dataset_view import _coordinate_scale, _require_structure_match


_BINDINGS = {}
_PROPERTY_NAMES = (
    "cb_trajectory_dataset_id",
    "cb_trajectory_dataset_revision",
    "cb_trajectory_frame_start",
    "cb_trajectory_frame_step",
    "cb_trajectory_frame_index",
    "cb_trajectory_cache_size",
    "cb_trajectory_prefetch_ahead",
)


@dataclass(slots=True)
class _TrajectoryBinding:
    obj: object
    manager: TrajectoryFrameManager
    frame_start: int
    frame_step: int
    prefetch_ahead: int


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


def _apply_binding(binding, scene_frame):
    import numpy

    index = _frame_index(scene_frame, binding)
    values = binding.manager.frame(index)
    scale = _coordinate_scale(binding.manager.unit)
    binding.obj.data.vertices.foreach_set(
        "co", (numpy.asarray(values, dtype=float) * scale).reshape(-1)
    )
    binding.obj["cb_trajectory_frame_index"] = int(index)
    binding.obj.data.update()
    if binding.prefetch_ahead:
        binding.manager.prefetch_around(index, after=binding.prefetch_ahead)


def _frame_change_handler(scene, depsgraph=None):
    del depsgraph
    stale = []
    for key, binding in tuple(_BINDINGS.items()):
        try:
            _apply_binding(binding, scene.frame_current)
        except ReferenceError:
            binding.manager.close()
            stale.append(key)
    for key in stale:
        _BINDINGS.pop(key, None)


def _remove_handlers():
    handlers = bpy.app.handlers.frame_change_post
    for handler in tuple(handlers):
        if (
            getattr(handler, "__module__", None) == __name__
            and getattr(handler, "__name__", None) == "_frame_change_handler"
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
):
    if not isinstance(frames, FrameSet):
        raise TypeError("frames must be a FrameSet")
    frame_start = _integer(frame_start, "frame_start")
    frame_step = _integer(frame_step, "frame_step", positive=True)
    cache_size = _integer(cache_size, "cache_size", positive=True)
    prefetch_ahead = _integer(prefetch_ahead, "prefetch_ahead")
    if prefetch_ahead < 0:
        raise ValueError("prefetch_ahead must be non-negative")
    _require_structure_match(obj, frames.structure_id, frames.data.shape[1])
    key = obj.as_pointer()
    manager = TrajectoryFrameManager(frames, cache_size=cache_size)
    binding = _TrajectoryBinding(
        obj, manager, frame_start, frame_step, prefetch_ahead
    )
    try:
        _apply_binding(binding, bpy.context.scene.frame_current)
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


def clear_trajectory_view(obj):
    key = obj.as_pointer()
    binding = _BINDINGS.pop(key, None)
    if binding is not None:
        binding.manager.close()
    for name in _PROPERTY_NAMES:
        if name in obj:
            del obj[name]


def register():
    _remove_handlers()
    bpy.app.handlers.frame_change_post.append(_frame_change_handler)


def unregister():
    for binding in _BINDINGS.values():
        binding.manager.close()
    _BINDINGS.clear()
    _remove_handlers()
