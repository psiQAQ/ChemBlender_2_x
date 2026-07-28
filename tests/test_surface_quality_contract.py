from dataclasses import replace
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    Grid3D,
    ImportBatch,
    QCProject,
    builtin_scene_presets,
    plan_scene_preset,
)
from ChemBlender.core import scene_preset as scene_preset_module
from ChemBlender.ui.project_browser.model import ViewRecord


def grid(*, status=DatasetStatus.COMPLETE):
    return Grid3D(
        id=uuid4(),
        revision="grid-r1",
        semantic_role="scalar_field",
        domain="grid",
        data=ArrayData(
            numpy.arange(8.0).reshape((2, 2, 2)),
            ("x", "y", "z"),
            (
                "unknown"
                if status is DatasetStatus.AMBIGUOUS
                else "electron_per_bohr_cubed"
            ),
        ),
        status=status,
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


class SurfaceQualityContractTests(unittest.TestCase):
    def test_ambiguous_grid_can_plan_report_ineligible_preview_surface(self):
        source = grid(status=DatasetStatus.AMBIGUOUS)
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(datasets=(source,)))

        plan = plan_scene_preset(
            builtin_scene_presets()["signed_isosurface"],
            project,
            {"grid": source.id},
            {"isovalue": 0.1},
        )
        record = ViewRecord(
            object_name="Ambiguous preview",
            entity_id=source.id,
            revision=source.revision,
            view_kind=plan.view_kind,
            label="Ambiguous preview",
            quality="ambiguous",
            report_eligible=False,
        )

        self.assertEqual(record.quality, "ambiguous")
        self.assertFalse(record.report_eligible)

    def test_affine_alignment_uses_documented_tolerance_without_resampling(self):
        guard = getattr(scene_preset_module, "grids_share_affine", None)
        self.assertIsNotNone(guard)
        source = grid()
        close = replace(
            source,
            id=uuid4(),
            revision="close-r1",
            semantic_role="electrostatic_potential",
            origin=(5.0e-10, 0.0, 0.0),
        )
        mismatched = replace(
            close,
            id=uuid4(),
            revision="mismatched-r1",
            origin=(2.0e-9, 0.0, 0.0),
        )

        self.assertTrue(guard(source, close))
        self.assertFalse(guard(source, mismatched))
        self.assertFalse(
            guard(
                source,
                replace(source, id=uuid4(), coordinate_unit="angstrom"),
            )
        )
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(datasets=(source, close, mismatched)))
        preset = builtin_scene_presets()["property_on_surface"]
        self.assertEqual(
            plan_scene_preset(
                preset,
                project,
                {
                    "surface_grid": source.id,
                    "property_grid": close.id,
                },
                {},
            ).view_kind,
            "property_on_surface",
        )
        with self.assertRaisesRegex(ValueError, "affine"):
            plan_scene_preset(
                preset,
                project,
                {
                    "surface_grid": source.id,
                    "property_grid": mismatched.id,
                },
                {},
            )

    def test_complete_surface_view_is_report_eligible(self):
        source = grid()
        record = ViewRecord(
            object_name="Resolved surface",
            entity_id=source.id,
            revision=source.revision,
            view_kind="signed_isosurface",
            label="Resolved surface",
            quality="complete",
            report_eligible=True,
        )

        self.assertEqual(record.quality, "complete")
        self.assertTrue(record.report_eligible)
        with self.assertRaisesRegex(ValueError, "report eligible"):
            ViewRecord(
                object_name="Unsafe preview",
                entity_id=source.id,
                revision=source.revision,
                view_kind="signed_isosurface",
                label="Unsafe preview",
                quality="ambiguous",
                report_eligible=True,
            )


if __name__ == "__main__":
    unittest.main()
