from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import unittest
from uuid import uuid4

import numpy

import ChemBlender.core as core
import ChemBlender.reader_api as reader_api
import ChemBlender.reader_api.builtin_bridge as builtin_bridge
from ChemBlender.core.cube import CUBE_READER
from ChemBlender.core.xyz import XYZ_READER


ROOT = Path(__file__).resolve().parents[1]
XYZ = ROOT / "tests" / "fixtures" / "xyz" / "water.xyz"
CUBE = ROOT / "tests" / "fixtures" / "cube" / "sheared.cube"

SCIENTIFIC_TYPES = (
    "ArrayData", "SourceRecord", "SourceRevision", "CIFEnvelope",
    "QCSchemaEnvelope", "CJSONEnvelope", "PeriodicSiteData",
    "MolecularTopology", "TopologyRecord", "Structure", "SymmetryResult",
    "CalculationMetadata", "CalculationRecord", "PropertyDataset",
    "AtomicProperty", "FrameSet", "Grid3D", "VibrationalModeSet",
    "ExcitedStateSet", "Spectrum", "BandStructure", "DensityOfStates",
    "PhononModeSet", "FermiSurfaceMesh", "TopologyGraph",
    "ExcitationContribution", "ExcitedStateReferences", "BandPathBranch",
    "SurfaceProperty", "TopologyConnection", "TopologyPath", "BasisShell",
    "BasisConvention", "BasisSet", "OrbitalChannel", "OrbitalSet",
    "DensityMatrix", "ProvenanceRecord", "ParserIssue", "ParserReport",
    "DiagnosticValue", "ImportDiagnostic",
)
ENUM_TYPES = (
    "CalculationStatus", "DatasetStatus", "IssueKind", "BasisFunctionKind",
    "OrbitalKind", "DensityMatrixLevel", "DensityMatrixSpin", "SpectrumKind",
    "SpectrumProfile", "SpinChannel", "EnergyReference", "CriticalPointKind",
    "QualityStatus", "DiagnosticSeverity", "TopologySource",
)


class PublicImportBatchTests(unittest.TestCase):
    def test_scientific_facade_reexports_exact_trusted_types(self):
        for name in SCIENTIFIC_TYPES + ENUM_TYPES:
            with self.subTest(name=name):
                self.assertIs(getattr(reader_api, name), getattr(core, name))
        self.assertFalse(hasattr(reader_api, "QCProject"))
        self.assertFalse(hasattr(reader_api, "ImportBatch"))

    def test_container_is_frozen_slotted_and_sequence_isolated(self):
        source = core.SourceRecord(uuid4(), "water", "local_file", "2026-07-24T00:00:00Z")
        sources = [source]
        batch = reader_api.PublicImportBatch(sources=sources)
        sources.clear()
        self.assertEqual(batch.sources, (source,))
        self.assertFalse(hasattr(batch, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            batch.sources = ()
        self.assertFalse(hasattr(batch, "commit"))

    def test_container_requires_exact_trusted_entity_types(self):
        class UntrustedSource(core.SourceRecord):
            pass

        source = core.SourceRecord(uuid4(), "water", "local_file", "2026-07-24T00:00:00Z")
        untrusted = UntrustedSource(uuid4(), "water", "local_file", "2026-07-24T00:00:00Z")
        with self.assertRaises(TypeError):
            reader_api.PublicImportBatch(sources=(untrusted,))
        with self.assertRaises(TypeError):
            reader_api.PublicImportBatch(datasets=(object(),))
        self.assertEqual(reader_api.PublicImportBatch(sources=(source,)).sources, (source,))

    def test_container_accepts_every_approved_exact_dataset_type(self):
        dataset_types = (
            core.PropertyDataset, core.AtomicProperty, core.FrameSet, core.Grid3D,
            core.VibrationalModeSet, core.ExcitedStateSet, core.Spectrum,
            core.BandStructure, core.DensityOfStates, core.PhononModeSet,
            core.FermiSurfaceMesh, core.TopologyGraph,
        )
        for dataset_type in dataset_types:
            with self.subTest(dataset_type=dataset_type.__name__):
                dataset = object.__new__(dataset_type)
                self.assertIs(
                    reader_api.PublicImportBatch(datasets=(dataset,)).datasets[0],
                    dataset,
                )

    def test_container_rejects_parser_report_subclass(self):
        class UntrustedReport(core.ParserReport):
            pass

        with self.assertRaises(TypeError):
            reader_api.PublicImportBatch(report=object.__new__(UntrustedReport))

    def test_builtin_bridge_hides_implementation_dependencies(self):
        self.assertEqual(
            builtin_bridge.__all__,
            (
                "PublicBatchError",
                "PublicBatchValidationError",
                "public_batch_from_internal",
                "internal_batch_from_public",
            ),
        )
        for name in (
            "QCProject", "ImportBatch", "CURRENT_PROJECT_SCHEMA_VERSION",
            "uuid4", "PublicImportBatch",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(builtin_bridge, name))

    def test_container_has_identity_equality_and_retains_arrays_without_copying(self):
        internal = XYZ_READER.parse(XYZ)
        batch = reader_api.PublicImportBatch(
            structures=internal.structures,
            provenance=internal.provenance,
            report=internal.report,
        )
        same_values = internal.structures[0].coordinates.values
        self.assertIs(batch.structures[0], internal.structures[0])
        self.assertIs(batch.structures[0].coordinates.values, same_values)
        self.assertNotEqual(batch, reader_api.PublicImportBatch(structures=internal.structures))

    def test_conversion_requires_exact_container_types_and_rejects_subclasses(self):
        class UntrustedSource(core.SourceRecord):
            pass

        source = UntrustedSource(uuid4(), "water", "local_file", "2026-07-24T00:00:00Z")
        internal = core.ImportBatch(sources=(source,))
        with self.assertRaises(TypeError):
            reader_api.public_batch_from_internal(internal)
        with self.assertRaises(TypeError):
            reader_api.public_batch_from_internal(object())
        with self.assertRaises(TypeError):
            reader_api.internal_batch_from_public(object())

    def test_xyz_round_trip_preserves_entities_arrays_and_report(self):
        internal = XYZ_READER.parse(XYZ)
        public = reader_api.public_batch_from_internal(internal)
        restored = reader_api.internal_batch_from_public(public)
        self.assertIs(public.structures[0], internal.structures[0])
        self.assertIs(restored.structures[0], internal.structures[0])
        self.assertEqual(restored.structures[0].id, internal.structures[0].id)
        self.assertEqual(restored.structures[0].revision, internal.structures[0].revision)
        self.assertEqual(restored.structures[0].coordinates.dims, ("atom", "xyz"))
        self.assertEqual(restored.structures[0].coordinates.unit, "angstrom")
        self.assertIs(restored.structures[0].coordinates.values, internal.structures[0].coordinates.values)
        self.assertIs(restored.provenance[0], internal.provenance[0])
        self.assertIs(restored.report, internal.report)

    def test_cube_round_trip_preserves_sheared_grid(self):
        internal = CUBE_READER.parse(CUBE)
        restored = reader_api.internal_batch_from_public(
            reader_api.public_batch_from_internal(internal)
        )
        grid = restored.datasets[0]
        original = internal.datasets[0]
        self.assertIs(grid, original)
        self.assertIs(restored.structures[0], internal.structures[0])
        self.assertEqual(grid.origin, (0.0, 0.0, 0.0))
        self.assertEqual(grid.step_vectors, ((1.0, 0.0, 0.0), (0.2, 1.0, 0.0), (0.0, 0.3, 1.0)))
        self.assertEqual(grid.coordinate_unit, "bohr")
        self.assertEqual(grid.data.values[1, 0, 1], 5.0)
        self.assertIs(grid.data.values, original.data.values)

    def test_conversion_wraps_graph_validation_failures(self):
        internal = CUBE_READER.parse(CUBE)
        dangling = replace(internal.datasets[0], structure_id=uuid4())
        with self.assertRaises(reader_api.PublicBatchValidationError):
            reader_api.internal_batch_from_public(
                reader_api.PublicImportBatch(
                    structures=internal.structures,
                    datasets=(dangling,),
                    provenance=internal.provenance,
                    report=internal.report,
                )
            )
        with self.assertRaises(reader_api.PublicBatchValidationError):
            reader_api.internal_batch_from_public(
                reader_api.PublicImportBatch(
                    structures=internal.structures,
                    datasets=internal.datasets,
                    provenance=internal.provenance,
                    report=replace(internal.report, created_entity_ids=()),
                )
            )

    def test_public_to_internal_rejects_unsafe_nested_values(self):
        for value in (lambda: None, [], {}, frozenset(("unsafe",)), object()):
            with self.subTest(value_type=type(value).__name__):
                provenance = core.ProvenanceRecord(
                    uuid4(),
                    "revision",
                    "test",
                    "1",
                    "source",
                    "",
                    (),
                    "parse",
                    (("unsafe", value),),
                )
                with self.assertRaises(reader_api.PublicBatchValidationError):
                    reader_api.internal_batch_from_public(
                        reader_api.PublicImportBatch(provenance=(provenance,))
                    )

    def test_public_to_internal_accepts_approved_immutable_nested_values(self):
        array = core.ArrayData(
            numpy.asarray([1.0]),
            ("value",),
            "dimensionless",
        )
        values = (
            None,
            "text",
            b"bytes",
            True,
            1,
            1.5,
            uuid4(),
            core.IssueKind.WARNING,
            ("nested", 2),
            array,
        )
        provenance = core.ProvenanceRecord(
            uuid4(),
            "revision",
            "test",
            "1",
            "source",
            "",
            (),
            "parse",
            tuple((f"value_{index}", value) for index, value in enumerate(values)),
        )
        restored = reader_api.internal_batch_from_public(
            reader_api.PublicImportBatch(provenance=(provenance,))
        )

        self.assertIs(restored.provenance[0], provenance)
        self.assertIs(
            restored.provenance[0].parameters[-1][1],
            array,
        )
        self.assertIs(
            restored.provenance[0].parameters[-1][1].values,
            array.values,
        )


if __name__ == "__main__":
    unittest.main()
