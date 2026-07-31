from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData, DatasetStatus, Grid3D
from ChemBlender.core.grid_cache_service import (
    VolumeCacheRequest,
    prepare_volume_cache,
)
from tests.test_task_state_machine import load_tasks_without_bpy


def sample_grid():
    return Grid3D(
        id=uuid4(),
        revision="grid-r1",
        semantic_role="molecular_orbital",
        domain="grid",
        data=ArrayData(
            numpy.arange(16.0).reshape((2, 2, 2, 2)),
            ("dataset", "x", "y", "z"),
            "inverse_bohr_to_three_halves",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        origin=(0.0, 0.0, 0.0),
        step_vectors=(
            (0.5, 0.0, 0.0),
            (0.0, 0.5, 0.0),
            (0.0, 0.0, 0.5),
        ),
        coordinate_unit="bohr",
    )


class FakeWriter:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.write_calls = 0

    def populate(self, values, transform, metadata):
        if self.fail:
            raise OSError("writer failed")
        self.values = numpy.array(values, copy=True)
        self.transform = transform
        self.metadata = dict(metadata)
        return object()

    def write(self, path, _payload, metadata):
        self.write_calls += 1
        Path(path).write_text(
            metadata["chemblender_render_cache_key"],
            encoding="ascii",
        )

    def validate(self, path, grid_names, render_key):
        self.validated_names = tuple(grid_names)
        if Path(path).read_text(encoding="ascii") != render_key:
            raise RuntimeError("invalid cache")


class GridCacheServiceTests(unittest.TestCase):
    def request(self, temporary):
        return VolumeCacheRequest(
            Path(temporary) / "volume" / f"{'a' * 64}.vdb",
            dataset_index=1,
        )

    def prepare(self, grid, request, writer, *, cancel_stage=None):
        events = []

        def progress(stage, fraction):
            events.append((stage, fraction))

        result = prepare_volume_cache(
            grid,
            request,
            writer=writer,
            cancelled=lambda: (
                cancel_stage is not None
                and events
                and events[-1][0] == cancel_stage
            ),
            progress=progress,
        )
        return result, events

    def test_cache_miss_publishes_short_sibling_and_cache_hit_is_immediate(self):
        with TemporaryDirectory() as temporary:
            grid = sample_grid()
            request = self.request(temporary)
            writer = FakeWriter()

            result, events = self.prepare(grid, request, writer)

            self.assertEqual(result.status, "published")
            self.assertEqual(result.cache_path, request.cache_path)
            self.assertTrue(result.cache_path.is_file())
            self.assertEqual(writer.write_calls, 1)
            self.assertEqual(writer.values.shape, (2, 2, 2))
            self.assertEqual(
                writer.metadata["chemblender_dataset_index"], 1
            )
            self.assertEqual(events[-1], ("published", 1.0))
            self.assertEqual(
                list(request.cache_path.parent.glob(".*.tmp")),
                [],
            )

            hit, hit_events = self.prepare(grid, request, writer)

            self.assertEqual(hit.status, "cache_hit")
            self.assertEqual(writer.write_calls, 1)
            self.assertEqual(hit_events, [("cache_hit", 1.0)])

    def test_each_cancellation_checkpoint_preserves_prior_cache(self):
        stages = (
            "before_array_load",
            "after_dataset_slice",
            "after_vdb_population",
            "before_publish",
        )
        for stage in stages:
            with self.subTest(stage=stage), TemporaryDirectory() as temporary:
                grid = sample_grid()
                request = self.request(temporary)
                request.cache_path.parent.mkdir(parents=True)
                request.cache_path.write_text("prior", encoding="ascii")
                writer = FakeWriter()

                result, events = self.prepare(
                    grid,
                    request,
                    writer,
                    cancel_stage=stage,
                )

                self.assertEqual(result.status, "cancelled")
                self.assertIn((stage, result.progress), events)
                self.assertEqual(
                    request.cache_path.read_text(encoding="ascii"),
                    "prior",
                )
                self.assertEqual(
                    list(request.cache_path.parent.glob(".*.tmp")),
                    [],
                )

    def test_vdb_task_worker_cancels_before_publish_without_staging_leak(self):
        with TemporaryDirectory() as temporary:
            tasks = load_tasks_without_bpy()
            request = self.request(temporary)
            task = tasks.Task()

            def prepare(cancelled, progress):
                def track(stage, fraction):
                    progress(f"vdb.{stage}", fraction)
                    if stage == "before_publish":
                        task.request_cancel()

                return prepare_volume_cache(
                    sample_grid(),
                    request,
                    writer=FakeWriter(),
                    cancelled=cancelled,
                    progress=track,
                )

            worker = tasks.TaskWorker(task, prepare)
            worker.start("vdb.prepare")
            self.assertTrue(worker.join(1))

            self.assertIsNone(worker.error)
            self.assertEqual(worker.result.status, "cancelled")
            self.assertEqual(task.snapshot().state.value, "cancelled")
            self.assertFalse(request.cache_path.exists())
            self.assertEqual(
                list(request.cache_path.parent.glob(".*.tmp")),
                [],
            )

    def test_vdb_task_worker_returns_ready_cache_without_bpy(self):
        with TemporaryDirectory() as temporary:
            tasks = load_tasks_without_bpy()
            request = self.request(temporary)
            task = tasks.Task()

            worker = tasks.TaskWorker(
                task,
                lambda cancelled, progress: prepare_volume_cache(
                    sample_grid(),
                    request,
                    writer=FakeWriter(),
                    cancelled=cancelled,
                    progress=lambda stage, fraction: progress(
                        f"vdb.{stage}", fraction
                    ),
                ),
            )
            worker.start("vdb.prepare")
            self.assertTrue(worker.join(1))

            self.assertIsNone(worker.error)
            self.assertEqual(task.snapshot().state.value, "succeeded")
            self.assertEqual(worker.result.status, "published")
            self.assertEqual(worker.result.cache_path, request.cache_path)
            self.assertTrue(request.cache_path.is_file())

    def test_writer_and_publish_failure_cleanup_without_replacing_prior(self):
        for failure in ("writer", "publish"):
            with self.subTest(failure=failure), TemporaryDirectory() as temporary:
                grid = sample_grid()
                request = self.request(temporary)
                request.cache_path.parent.mkdir(parents=True)
                request.cache_path.write_text("prior", encoding="ascii")
                writer = FakeWriter(fail=failure == "writer")
                context = (
                    patch(
                        "ChemBlender.core.grid_cache_service.os.replace",
                        side_effect=OSError("publish failed"),
                    )
                    if failure == "publish"
                    else patch(
                        "ChemBlender.core.grid_cache_service.os.replace",
                        wraps=__import__("os").replace,
                    )
                )

                with context, self.assertRaisesRegex(OSError, "failed"):
                    self.prepare(grid, request, writer)

                self.assertEqual(
                    request.cache_path.read_text(encoding="ascii"),
                    "prior",
                )
                self.assertEqual(
                    list(request.cache_path.parent.glob(".*.tmp")),
                    [],
                )

    def test_request_rejects_final_filesystem_link(self):
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(OSError, "filesystem link"):
                VolumeCacheRequest(Path("cache.vdb"))


if __name__ == "__main__":
    unittest.main()
