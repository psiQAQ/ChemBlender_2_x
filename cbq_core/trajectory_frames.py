import operator
from collections import OrderedDict
from dataclasses import dataclass
from math import isfinite

from .model import FrameSet


@dataclass(frozen=True, slots=True)
class FrameCacheInfo:
    hits: int
    misses: int
    size: int
    max_size: int


def _integer(value, name, *, minimum=None):
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    try:
        value = operator.index(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an integer") from error
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


class TrajectoryFrameManager:
    def __init__(self, frames, *, cache_size=3):
        if not isinstance(frames, FrameSet):
            raise TypeError("frames must be a FrameSet")
        cache_size = _integer(cache_size, "cache_size", minimum=1)
        self.frames = frames
        self.cache_size = cache_size
        self._cache = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._closed = False

    @property
    def frame_count(self):
        return self.frames.data.shape[0]

    @property
    def atom_count(self):
        return self.frames.data.shape[1]

    @property
    def unit(self):
        return self.frames.data.unit

    def frame(self, index):
        import numpy

        if self._closed:
            raise RuntimeError("trajectory frame manager is closed")
        index = _integer(index, "index")
        if not 0 <= index < self.frame_count:
            raise IndexError("trajectory frame index is outside the frame set")
        try:
            result = self._cache.pop(index)
        except KeyError:
            self._misses += 1
            values = numpy.asarray(self.frames.data.values[index])
            if values.shape != (self.atom_count, 3):
                raise ValueError("trajectory frame must have shape (atom, xyz)")
            if numpy.iscomplexobj(values) or not numpy.all(numpy.isfinite(values)):
                raise ValueError("trajectory frame coordinates must be finite and real")
            result = numpy.array(values, dtype=float, copy=True)
            result.flags.writeable = False
            self._cache[index] = result
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return result
        self._hits += 1
        self._cache[index] = result
        return result

    def prefetch_around(self, index, *, before=0, after=1):
        index = _integer(index, "index")
        before = _integer(before, "before", minimum=0)
        after = _integer(after, "after", minimum=0)
        if not 0 <= index < self.frame_count:
            raise IndexError("trajectory frame index is outside the frame set")
        for candidate in range(
            max(0, index - before), min(self.frame_count, index + after + 1)
        ):
            self.frame(candidate)

    def interpolate(self, left_index, right_index, fraction):
        import numpy

        if (
            isinstance(fraction, bool)
            or not isinstance(fraction, (int, float))
            or not isfinite(fraction)
            or not 0.0 <= fraction <= 1.0
        ):
            raise ValueError("fraction must be finite from 0 to 1")
        left = self.frame(left_index)
        right = self.frame(right_index)
        result = numpy.asarray(left * (1.0 - fraction) + right * fraction)
        result.flags.writeable = False
        return result

    def mean(self, *, start=0, stop=None, step=1):
        import numpy

        start = _integer(start, "start", minimum=0)
        stop = self.frame_count if stop is None else _integer(stop, "stop", minimum=0)
        step = _integer(step, "step", minimum=1)
        indices = range(start, min(stop, self.frame_count), step)
        total = None
        count = 0
        for index in indices:
            values = self.frame(index)
            if total is None:
                total = numpy.array(values, dtype=numpy.float64, copy=True)
            else:
                total += values
            count += 1
        if count == 0:
            raise ValueError("trajectory mean requires at least one frame")
        total /= count
        total.flags.writeable = False
        return total

    def cache_info(self):
        return FrameCacheInfo(
            self._hits, self._misses, len(self._cache), self.cache_size
        )

    def clear_cache(self):
        self._cache.clear()

    def close(self):
        self.clear_cache()
        source = self.frames.data.values
        close = getattr(source, "close", None)
        if callable(close):
            close()
        self._closed = True
