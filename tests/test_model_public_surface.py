import unittest

from cbq_core import model as core


PUBLIC_MODEL_NAMES = {
    "ArrayData",
    "AtomicIdentityData",
    "AtomicProperty",
    "AtomFrameProperty",
    "BiologicalAtomSiteData",
    "BiologicalChain",
    "BiologicalHierarchy",
    "BiologicalModel",
    "BiologicalResidue",
    "BandPathBranch",
    "BandStructure",
    "BasisConvention",
    "BasisFunctionKind",
    "BasisSet",
    "BasisShell",
    "CalculationMetadata",
    "CalculationRecord",
    "CalculationGroup",
    "CalculationStatus",
    "CategoricalData",
    "ChemicalAnnotation",
    "ConformerSet",
    "CellFrameProperty",
    "CriticalPointKind",
    "CJSONEnvelope",
    "CIFEnvelope",
    "DatasetStatus",
    "DiagnosticSeverity",
    "DiagnosticValue",
    "DensityMatrix",
    "DensityMatrixLevel",
    "DensityMatrixSpin",
    "DensityOfStates",
    "DeclaredSymmetry",
    "EnergyReference",
    "ExternalReference",
    "ExcitationContribution",
    "ExcitedStateReferences",
    "ExcitedStateSet",
    "FrameSet",
    "FrameProperty",
    "FermiSurfaceMesh",
    "Grid3D",
    "ImportBatch",
    "ImportDiagnostic",
    "IssueKind",
    "MolecularTopology",
    "MolecularRecord",
    "RawRecordProperty",
    "RecordPropertyColumn",
    "TopologyRecord",
    "TopologySource",
    "OrbitalChannel",
    "OrbitalKind",
    "OrbitalSet",
    "ParserIssue",
    "ParserReport",
    "PeriodicSiteData",
    "PhononModeSet",
    "PropertyDataset",
    "ProvenanceRecord",
    "QCProject",
    "QCSchemaEnvelope",
    "QualityStatus",
    "Spectrum",
    "SpectrumKind",
    "SpectrumProfile",
    "SourceRecord",
    "SourceRevision",
    "SpinChannel",
    "Structure",
    "SurfaceProperty",
    "SymmetryResult",
    "TopologyConnection",
    "TopologyGraph",
    "TopologyPath",
    "VibrationalModeSet",
}


class ModelPublicSurfaceTests(unittest.TestCase):
    def test_foundational_types_are_split_but_publicly_reexported(self):
        expected_origins = {
            "ArrayData": "cbq_core.model.arrays",
            "CalculationStatus": "cbq_core.model.common",
            "IssueKind": "cbq_core.model.common",
            "ParserIssue": "cbq_core.model.diagnostics",
            "ParserReport": "cbq_core.model.diagnostics",
        }
        self.assertEqual(
            {
                name: getattr(core, name).__module__
                for name in expected_origins
            },
            expected_origins,
        )

    def test_public_model_names_remain_importable(self):
        missing = sorted(name for name in PUBLIC_MODEL_NAMES if not hasattr(core, name))
        self.assertEqual(missing, [])

    def test_public_model_names_are_exposed_by_shared_model(self):
        missing = sorted(PUBLIC_MODEL_NAMES - set(dir(core)))
        self.assertEqual(missing, [])
