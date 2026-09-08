"""Trajectory plans and UI keep frame identity and avoid whole-array reads."""

from dataclasses import replace
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData, AtomFrameProperty, DatasetStatus, FrameProperty, ImportBatch, QCProject,
    builtin_scene_presets, plan_scene_preset,
)
from ChemBlender.ui.scientific_view import available_presets, scientific_bindings, timeline_frame
from tests.test_trajectory_frame_manager import frame_set
from tests.test_vibration_model import structure
from tests.test_scene_preset import grid


def trajectory_fixture(*, lazy=True):
    reference = structure()
    reference = replace(reference, coordinates=replace(reference.coordinates, unit="bohr"))
    values = numpy.arange(18, dtype=float).reshape(3, 2, 3) * .03
    frames, source = frame_set(values)
    frames = replace(frames, structure_id=reference.id,
                     data=ArrayData(source if lazy else values, ("frame", "atom", "xyz"), "bohr"),
                     comments=("source step 0", "source step 4", "source step 8"))
    force = AtomFrameProperty(uuid4(), "force-1", "atomic_force", "atom_frame",
        ArrayData(numpy.ones((3, 2, 3)) * 2., ("frame", "atom", "xyz"), "hartree_per_bohr"),
        DatasetStatus.PARTIAL, None, (), frames.id,
        ArrayData(numpy.array([[False, False], [True, True], [False, True]]),
                  ("frame", "atom"), "dimensionless"))
    time = FrameProperty(uuid4(), "time-1", "time", "frame",
        ArrayData(numpy.array([0., .4, .8]), ("frame",), "femtosecond"),
        DatasetStatus.COMPLETE, None, (), frames.id)
    project = QCProject(uuid4(), "0.1")
    project.commit(ImportBatch(structures=(reference,), datasets=(frames, force, time)))
    return project, reference, frames, force, time, source


class TrajectorySceneTests(unittest.TestCase):
    def test_static_timeline_plan_is_lazy_and_binds_force_to_its_frames(self):
        project, reference, frames, force, _, source = trajectory_fixture()
        preset = builtin_scene_presets()["trajectory_force"]
        self.assertEqual(available_presets(frames), ("trajectory", "trajectory_force"))
        self.assertEqual(available_presets(force), ("trajectory_force",))
        bindings = scientific_bindings(project, force, preset)
        self.assertEqual(bindings, {"structure": reference.id, "frames": frames.id, "force": force.id})
        self.assertEqual(scientific_bindings(project, frames, preset, str(force.id)), bindings)
        plan = plan_scene_preset(preset, project, bindings, {"frame_index": 2, "frame_start": 10, "frame_step": 4})
        self.assertEqual(dict(plan.settings)["frame_index"], 2)
        self.assertEqual(source.accessed, [])
        for key, value in (("frame_index", 3), ("frame_index", True), ("frame_step", 0), ("frame_start", 1.5)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                plan_scene_preset(preset, project, bindings, {key: value})
        foreign = replace(frames, id=uuid4())
        foreign_force = replace(force, id=uuid4(), frame_set_id=foreign.id)
        project.commit(ImportBatch(datasets=(foreign, foreign_force)))
        with self.assertRaisesRegex(ValueError, "compatible"):
            scientific_bindings(project, frames, preset, str(foreign_force.id))
        with self.assertRaisesRegex(ValueError, "trajectory axes"):
            plan_scene_preset(preset, project, dict(bindings, force=foreign_force.id), {})

    def test_timeline_clamps_with_integer_source_steps(self):
        self.assertEqual([timeline_frame(frame, 10, 4, 3) for frame in (0, 10, 13, 14, 18, 90)], [0, 0, 0, 1, 2, 2])
        for args in ((1, 1, 0, 3), (1, 1, 1, 0), (1., 1, 1, 3), (1, 1, True, 3)):
            with self.assertRaises(ValueError):
                timeline_frame(*args)

    def test_nci_preset_requires_density_pair_and_keeps_explicit_confirmation(self):
        project, reference, *_ = trajectory_fixture()
        base = grid(reference.id)
        rdg = replace(base, semantic_role="reduced_density_gradient",
            data=ArrayData(numpy.ones(base.grid_shape), ("x", "y", "z"), "dimensionless"))
        signed = replace(base, id=uuid4(), semantic_role="sign_lambda2_rho")
        project.commit(ImportBatch(datasets=(rdg, signed)))
        preset = builtin_scene_presets()["nci_surface"]
        self.assertEqual(available_presets(rdg)[0], "nci_surface")
        self.assertNotIn("nci_surface", available_presets(signed))
        bindings = scientific_bindings(project, rdg, preset, str(signed.id))
        with self.assertRaisesRegex(ValueError, "Confirm"):
            plan_scene_preset(preset, project, bindings, {})
        plan = plan_scene_preset(preset, project, bindings, {"pairing_confirmed": True})
        self.assertEqual(dict(plan.settings)["surface_isovalue"], .5)
        self.assertEqual(dict(plan.settings)["colormap"], "nci")
        self.assertTrue(dict(plan.settings)["pairing_confirmed"])


if __name__ == "__main__":
    unittest.main()
