import operator

import bpy

from .core import FrameSet
from .dataset_view import _coordinate_scale, _require_structure_match


_BINDINGS = {}
_PROPERTY_NAMES = (
    "cb_trajectory_dataset_id",
    "cb_trajectory_dataset_revision",
    "cb_trajectory_frame_start",
    "cb_trajectory_frame_step",
    "cb_trajectory_frame_index",
)


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
    _, frames, frame_start, frame_step = binding
    index = (scene_frame - frame_start) // frame_step
    return min(max(index, 0), frames.data.shape[0] - 1)


def _apply_binding(binding, scene_frame):
    import numpy

    obj, frames, _, _ = binding
    index = _frame_index(scene_frame, binding)
    values = numpy.asarray(frames.data.values)[index]
    if numpy.iscomplexobj(values) or not numpy.all(numpy.isfinite(values)):
        raise ValueError("trajectory frame coordinates must be finite and real")
    scale = _coordinate_scale(frames.data.unit)
    obj.data.vertices.foreach_set(
        "co", (numpy.asarray(values, dtype=float) * scale).reshape(-1)
    )
    obj["cb_trajectory_frame_index"] = int(index)
    obj.data.update()


def _frame_change_handler(scene, depsgraph=None):
    del depsgraph
    stale = []
    for key, binding in tuple(_BINDINGS.items()):
        try:
            _apply_binding(binding, scene.frame_current)
        except ReferenceError:
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


def configure_trajectory_view(obj, frames, *, frame_start=1, frame_step=1):
    import numpy

    if not isinstance(frames, FrameSet):
        raise TypeError("frames must be a FrameSet")
    frame_start = _integer(frame_start, "frame_start")
    frame_step = _integer(frame_step, "frame_step", positive=True)
    _require_structure_match(obj, frames.structure_id, frames.data.shape[1])
    values = numpy.asarray(frames.data.values)
    if numpy.iscomplexobj(values) or not numpy.all(numpy.isfinite(values)):
        raise ValueError("trajectory coordinates must be finite and real")
    key = obj.as_pointer()
    binding = (obj, frames, frame_start, frame_step)
    _BINDINGS[key] = binding
    obj["cb_trajectory_dataset_id"] = str(frames.id)
    obj["cb_trajectory_dataset_revision"] = frames.revision
    obj["cb_trajectory_frame_start"] = frame_start
    obj["cb_trajectory_frame_step"] = frame_step
    _apply_binding(binding, bpy.context.scene.frame_current)


def clear_trajectory_view(obj):
    key = obj.as_pointer()
    _BINDINGS.pop(key, None)
    for name in _PROPERTY_NAMES:
        if name in obj:
            del obj[name]


def register():
    _remove_handlers()
    bpy.app.handlers.frame_change_post.append(_frame_change_handler)


def unregister():
    _BINDINGS.clear()
    _remove_handlers()
