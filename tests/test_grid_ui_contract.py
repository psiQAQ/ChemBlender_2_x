from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData, DatasetStatus, Grid3D, ImportBatch
from ChemBlender.core.cube import CUBE_READER
from ChemBlender.core.session import close_session, create_session
from ChemBlender.ui.grid import (
    grid_action_availability,
    grid_preview_summary,
    plan_grid_view,
    resolve_grid_selection,
)


ROOT = Path(__file__).resolve().parents[1]
TWO_DATASETS = ROOT / "tests/fixtures/cube/two-datasets.cube"


class GridUIContractTests(unittest.TestCase):
    def test_cube_preview_reports_bounded_dataset_summary(self):
        batch = CUBE_READER.parse(TWO_DATASETS)

        summary = grid_preview_summary(batch)

        self.assertEqual(summary.dataset_count, 2)
        self.assertEqual(summary.source_dataset_ids, ("5", "7"))
        self.assertEqual(summary.grid_shape, (2, 2, 1))
        self.assertEqual(summary.coordinate_unit, "bohr")
        self.assertEqual(summary.value_unit, "unknown")
        self.assertEqual(summary.quality, "ambiguous")
        self.assertEqual(summary.sample_ranges, ((10.0, 13.0), (100.0, 103.0)))
        self.assertEqual(summary.default_dataset_index, 0)

    def test_preview_bounds_many_dataset_ranges_and_identifiers(self):
        batch = CUBE_READER.parse(TWO_DATASETS)
        raw = next(value for value in batch.datasets if isinstance(value, Grid3D))
        values = numpy.arange(40 * 4.0).reshape((40, 2, 2, 1))
        grid = replace(
            raw,
            data=ArrayData(
                values,
                ("dataset", "x", "y", "z"),
                "unknown",
            ),
            structure_id=None,
            source_calculation=None,
            provenance_ids=(),
        )

        summary = grid_preview_summary(ImportBatch(datasets=(grid,)))

        self.assertEqual(summary.dataset_count, 40)
        self.assertEqual(len(summary.sample_ranges), 32)
        self.assertEqual(len(summary.source_dataset_ids), 33)
        self.assertEqual(summary.source_dataset_ids[-1], "…")

    def test_resolution_commits_derived_grid_without_changing_raw_grid(self):
        batch = CUBE_READER.parse(TWO_DATASETS)
        raw = next(value for value in batch.datasets if isinstance(value, Grid3D))
        before = numpy.array(raw.data.values, copy=True)
        with TemporaryDirectory() as temporary:
            session = create_session(temp_parent=temporary)
            try:
                session.project.commit(batch)

                resolved, created = resolve_grid_selection(
                    session,
                    raw.id,
                    dataset_index=1,
                    preset_id="molecular_orbital",
                    value_unit="inverse_bohr_to_three_halves",
                )

                self.assertTrue(created)
                self.assertIs(session.project.datasets[raw.id], raw)
                self.assertEqual(
                    numpy.asarray(raw.data.values).tolist(),
                    before.tolist(),
                )
                self.assertEqual(resolved.semantic_role, "molecular_orbital")
                self.assertIs(resolved.status, DatasetStatus.COMPLETE)
                self.assertEqual(session.active_entity_id, resolved.id)
                self.assertIn("grid_semantics", session.dirty_reasons)
                duplicate, duplicate_created = resolve_grid_selection(
                    session,
                    raw.id,
                    dataset_index=1,
                    preset_id="molecular_orbital",
                    value_unit="inverse_bohr_to_three_halves",
                )
                self.assertEqual(duplicate.id, resolved.id)
                self.assertFalse(duplicate_created)
            finally:
                close_session(session)

    def test_view_actions_delegate_to_existing_scene_presets(self):
        batch = CUBE_READER.parse(TWO_DATASETS)
        raw = next(value for value in batch.datasets if isinstance(value, Grid3D))
        with TemporaryDirectory() as temporary:
            session = create_session(temp_parent=temporary)
            try:
                session.project.commit(batch)
                raw_actions = grid_action_availability(session.project, raw.id)
                self.assertTrue(raw_actions.volume)
                self.assertFalse(raw_actions.signed_surface)
                self.assertEqual(raw_actions.property_grid_ids, ())
                self.assertEqual(
                    plan_grid_view(
                        session.project,
                        raw.id,
                        mode="volume",
                        dataset_index=1,
                    ).preset_id,
                    "grid_volume",
                )
                resolved, _ = resolve_grid_selection(
                    session,
                    raw.id,
                    dataset_index=1,
                    preset_id="molecular_orbital",
                    value_unit="inverse_bohr_to_three_halves",
                )
                prop = replace(
                    resolved,
                    id=uuid4(),
                    revision="property-r1",
                    semantic_role="electrostatic_potential",
                )
                session.project.commit(ImportBatch(datasets=(prop,)))

                actions = grid_action_availability(
                    session.project, resolved.id
                )
                self.assertTrue(actions.signed_surface)
                self.assertEqual(actions.property_grid_ids, (prop.id,))
                signed = plan_grid_view(
                    session.project,
                    resolved.id,
                    mode="signed_surface",
                    isovalue=0.2,
                )
                self.assertEqual(signed.preset_id, "signed_isosurface")
                self.assertEqual(dict(signed.settings)["isovalue"], 0.2)
                mapped = plan_grid_view(
                    session.project,
                    resolved.id,
                    mode="property_surface",
                    property_grid_id=prop.id,
                    isovalue=0.15,
                )
                self.assertEqual(mapped.preset_id, "property_on_surface")
                self.assertEqual(
                    {
                        value.name: value.entity_id
                        for value in mapped.bindings
                    },
                    {
                        "surface_grid": resolved.id,
                        "property_grid": prop.id,
                    },
                )
            finally:
                close_session(session)


if __name__ == "__main__":
    unittest.main()
