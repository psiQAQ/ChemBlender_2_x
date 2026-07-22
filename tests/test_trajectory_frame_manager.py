import unittest

import numpy

from ChemBlender.core import ArrayData, DatasetStatus, FrameSet
from ChemBlender.core.trajectory_frames import TrajectoryFrameManager


class IndexedOnlyArray:
    def __init__(self, values):
        self._values = numpy.asarray(values)
        self.shape = self._values.shape
        self.dtype = self._values.dtype
        self.accessed = []
        self.closed = False

    def __getitem__(self, index):
        self.accessed.append(index)
        return self._values[index]

    def __array__(self, dtype=None, copy=None):
        raise AssertionError("trajectory source must not be materialized as a whole")

    def close(self):
        self.closed = True


def frame_set(values):
    source = IndexedOnlyArray(values)
    frames = FrameSet(
        id=__import__("uuid").uuid4(),
        revision="frames-r1",
        semantic_role="coordinates",
        domain="frame",
        data=ArrayData(source, ("frame", "atom", "xyz"), "angstrom"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=__import__("uuid").uuid4(),
        comments=tuple(f"frame {index}" for index in range(source.shape[0])),
    )
    return frames, source


class TrajectoryFrameManagerTests(unittest.TestCase):
    def test_initialization_is_lazy_and_lru_is_bounded(self):
        frames, source = frame_set(numpy.arange(45).reshape((5, 3, 3)))
        manager = TrajectoryFrameManager(frames, cache_size=2)
        self.assertEqual(source.accessed, [])

        first = manager.frame(2)
        self.assertEqual(source.accessed, [2])
        self.assertFalse(first.flags.writeable)
        self.assertIs(manager.frame(2), first)
        self.assertEqual(source.accessed, [2])
        manager.frame(3)
        manager.frame(4)
        info = manager.cache_info()
        self.assertEqual(info.size, 2)
        self.assertEqual(info.max_size, 2)
        self.assertEqual(info.hits, 1)
        self.assertEqual(info.misses, 3)
        manager.frame(2)
        self.assertEqual(source.accessed, [2, 3, 4, 2])

    def test_prefetch_interpolation_and_streaming_mean(self):
        values = numpy.asarray(
            [
                [[0.0, 0.0, 0.0]],
                [[2.0, 4.0, 6.0]],
                [[4.0, 8.0, 12.0]],
                [[6.0, 12.0, 18.0]],
            ]
        )
        frames, source = frame_set(values)
        manager = TrajectoryFrameManager(frames, cache_size=3)
        manager.prefetch_around(1, before=1, after=1)
        self.assertEqual(source.accessed, [0, 1, 2])
        self.assertTrue(
            numpy.allclose(manager.interpolate(1, 2, 0.25), [[2.5, 5.0, 7.5]])
        )
        self.assertTrue(
            numpy.allclose(manager.mean(start=0, stop=4, step=2), [[2.0, 4.0, 6.0]])
        )
        self.assertNotIn(Ellipsis, source.accessed)

    def test_invalid_frame_is_rejected_only_when_accessed(self):
        values = numpy.asarray([[[0.0, 0.0, 0.0]], [[numpy.nan, 0.0, 0.0]]])
        frames, source = frame_set(values)
        manager = TrajectoryFrameManager(frames)
        self.assertTrue(numpy.allclose(manager.frame(0), [[0.0, 0.0, 0.0]]))
        with self.assertRaises(ValueError):
            manager.frame(1)
        self.assertEqual(source.accessed, [0, 1])

        complex_frames, _ = frame_set(
            numpy.asarray([[[1.0 + 1.0j, 0.0, 0.0]]])
        )
        with self.assertRaises(ValueError):
            TrajectoryFrameManager(complex_frames).frame(0)

    def test_close_releases_source_and_validates_arguments(self):
        frames, source = frame_set(numpy.zeros((2, 1, 3)))
        with self.assertRaises(ValueError):
            TrajectoryFrameManager(frames, cache_size=0)
        manager = TrajectoryFrameManager(frames)
        with self.assertRaises(IndexError):
            manager.frame(2)
        with self.assertRaises(ValueError):
            manager.interpolate(0, 1, 1.5)
        with self.assertRaises(ValueError):
            manager.mean(start=1, stop=1)
        manager.frame(0)
        manager.close()
        self.assertTrue(source.closed)
        self.assertEqual(manager.cache_info().size, 0)


if __name__ == "__main__":
    unittest.main()
