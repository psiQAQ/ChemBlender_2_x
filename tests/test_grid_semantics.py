from dataclasses import FrozenInstanceError, replace
import unittest
from uuid import UUID

import numpy

from ChemBlender.core import ArrayData, DatasetStatus, Grid3D
from ChemBlender.core import ImportBatch, ProvenanceRecord, QCProject
from ChemBlender.core.grid_semantics import (
    GRID_SEMANTIC_PRESETS,
    GridSemanticPreset,
    default_grid_isovalue,
    resolve_grid_semantics,
)


GRID_ID = UUID("10000000-0000-0000-0000-000000000001")
PROVENANCE_ID = UUID("20000000-0000-0000-0000-000000000002")
STRUCTURE_ID = UUID("30000000-0000-0000-0000-000000000003")
CALCULATION_ID = UUID("40000000-0000-0000-0000-000000000004")


def source_grid(*, values=None, status=DatasetStatus.AMBIGUOUS):
    if values is None:
        values = numpy.arange(-8.0, 8.0).reshape((2, 2, 2, 2))
    dims = ("dataset", "x", "y", "z") if values.ndim == 4 else ("x", "y", "z")
    return Grid3D(
        id=GRID_ID,
        revision="raw-grid-r1",
        semantic_role="scalar_field",
        domain="grid",
        data=ArrayData(values, dims, "unknown" if status is DatasetStatus.AMBIGUOUS else "dimensionless"),
        status=status,
        source_calculation=CALCULATION_ID,
        provenance_ids=(PROVENANCE_ID,),
        origin=(1.0, 2.0, 3.0),
        step_vectors=((0.5, 0.0, 0.0), (0.1, 0.5, 0.0), (0.0, 0.2, 0.5)),
        coordinate_unit="bohr",
        structure_id=STRUCTURE_ID,
    )


class GridSemanticTests(unittest.TestCase):
    def test_builtin_presets_are_frozen_complete_and_stable(self):
        self.assertEqual(
            tuple(GRID_SEMANTIC_PRESETS),
            (
                "generic_scalar",
                "molecular_orbital",
                "electron_density",
                "spin_density",
                "electrostatic_potential",
                "reduced_density_gradient",
                "sign_lambda2_rho",
            ),
        )
        for preset_id, preset in GRID_SEMANTIC_PRESETS.items():
            with self.subTest(preset_id=preset_id):
                self.assertIsInstance(preset, GridSemanticPreset)
                self.assertEqual(preset.preset_id, preset_id)
                self.assertTrue(preset.value_units)
                self.assertIn(
                    preset.default_surface_mode,
                    {"grid_volume", "signed_isosurface"},
                )
                self.assertIn(
                    preset.isovalue_policy,
                    {"absolute", "fraction_of_max_abs"},
                )
        with self.assertRaises(FrozenInstanceError):
            GRID_SEMANTIC_PRESETS["molecular_orbital"].signed = False

    def test_resolution_selects_one_dataset_without_mutating_source(self):
        source = source_grid()
        before = numpy.array(source.data.values, copy=True)
        first = resolve_grid_semantics(
            source,
            dataset_index=1,
            preset_id="molecular_orbital",
            value_unit="inverse_bohr_to_three_halves",
        )
        second = resolve_grid_semantics(
            source,
            dataset_index=1,
            preset_id="molecular_orbital",
            value_unit="inverse_bohr_to_three_halves",
        )
        resolved = first.datasets[0]
        provenance = first.provenance[0]

        self.assertEqual(resolved.id, second.datasets[0].id)
        self.assertEqual(resolved.revision, second.datasets[0].revision)
        self.assertEqual(provenance.id, second.provenance[0].id)
        self.assertEqual(resolved.semantic_role, "molecular_orbital")
        self.assertEqual(resolved.data.dims, ("x", "y", "z"))
        numpy.testing.assert_array_equal(resolved.data.values, before[1])
        numpy.testing.assert_array_equal(source.data.values, before)
        self.assertEqual(resolved.data.unit, "inverse_bohr_to_three_halves")
        self.assertIs(resolved.status, DatasetStatus.COMPLETE)
        self.assertEqual(resolved.source_calculation, CALCULATION_ID)
        self.assertEqual(resolved.structure_id, STRUCTURE_ID)
        self.assertEqual(resolved.origin, source.origin)
        self.assertEqual(resolved.step_vectors, source.step_vectors)
        self.assertEqual(resolved.provenance_ids, (provenance.id,))
        self.assertEqual(provenance.parent_ids, (GRID_ID, PROVENANCE_ID))
        self.assertEqual(provenance.operation, "resolve_grid_semantics")
        self.assertEqual(
            dict(provenance.parameters),
            {
                "dataset_index": 1,
                "isovalue_parameter": 0.05,
                "isovalue_policy": "fraction_of_max_abs",
                "preset_id": "molecular_orbital",
                "semantic_role": "molecular_orbital",
                "source_revision": "raw-grid-r1",
                "value_unit": "inverse_bohr_to_three_halves",
            },
        )

    def test_resolution_validates_source_index_preset_and_unit(self):
        source = source_grid()
        cases = (
            {"dataset_index": 2, "preset_id": "molecular_orbital", "value_unit": "inverse_bohr_to_three_halves"},
            {"dataset_index": True, "preset_id": "molecular_orbital", "value_unit": "inverse_bohr_to_three_halves"},
            {"dataset_index": 0, "preset_id": "missing", "value_unit": "dimensionless"},
            {"dataset_index": 0, "preset_id": "electron_density", "value_unit": "hartree"},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises((TypeError, ValueError, IndexError)):
                resolve_grid_semantics(source, **arguments)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            resolve_grid_semantics(
                source_grid(
                    values=numpy.ones((2, 2, 2)),
                    status=DatasetStatus.COMPLETE,
                ),
                dataset_index=0,
                preset_id="generic_scalar",
                value_unit="dimensionless",
            )
        nonfinite = source_grid(values=numpy.full((2, 2, 2), numpy.nan))
        with self.assertRaisesRegex(ValueError, "finite"):
            resolve_grid_semantics(
                nonfinite,
                dataset_index=0,
                preset_id="generic_scalar",
                value_unit="dimensionless",
            )

    def test_scalar_grid_accepts_only_dataset_zero(self):
        source = source_grid(values=numpy.arange(8.0).reshape((2, 2, 2)))
        resolved = resolve_grid_semantics(
            source,
            dataset_index=0,
            preset_id="generic_scalar",
            value_unit="dimensionless",
        ).datasets[0]
        numpy.testing.assert_array_equal(resolved.data.values, source.data.values)
        with self.assertRaises(IndexError):
            resolve_grid_semantics(
                source,
                dataset_index=1,
                preset_id="generic_scalar",
                value_unit="dimensionless",
            )

    def test_default_isovalue_policies_are_deterministic(self):
        source = source_grid()
        self.assertEqual(
            default_grid_isovalue(
                source, dataset_index=1, preset_id="molecular_orbital"
            ),
            0.35000000000000003,
        )
        self.assertEqual(
            default_grid_isovalue(
                source, dataset_index=0, preset_id="electron_density"
            ),
            0.001,
        )
        self.assertEqual(
            default_grid_isovalue(
                source, dataset_index=0, preset_id="reduced_density_gradient"
            ),
            0.5,
        )
        zero = source_grid(values=numpy.zeros((2, 2, 2)))
        with self.assertRaisesRegex(ValueError, "nonzero"):
            default_grid_isovalue(
                zero, dataset_index=0, preset_id="generic_scalar"
            )

    def test_resolved_batch_commits_after_its_raw_parent(self):
        raw = source_grid()
        raw = replace(raw, source_calculation=None, structure_id=None)
        source_provenance = ProvenanceRecord(
            id=PROVENANCE_ID,
            revision=raw.revision,
            producer="test",
            producer_version="1",
            source="source.cube",
            source_hash="a" * 64,
            parent_ids=(),
            operation="parse",
            parameters=(("format", "cube"),),
        )
        project = QCProject(
            id=UUID("50000000-0000-0000-0000-000000000005"),
            schema_version="0.2",
        )
        project.commit(
            ImportBatch(datasets=(raw,), provenance=(source_provenance,))
        )
        resolved = resolve_grid_semantics(
            raw,
            dataset_index=1,
            preset_id="molecular_orbital",
            value_unit="inverse_bohr_to_three_halves",
        )
        project.commit(resolved)
        self.assertIn(raw.id, project.datasets)
        self.assertIn(resolved.datasets[0].id, project.datasets)


if __name__ == "__main__":
    unittest.main()
