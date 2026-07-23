import unittest

import ChemBlender.core as core


PUBLIC_MODEL_NAMES = {
    "ArrayData",
    "AtomicProperty",
    "BandPathBranch",
    "BandStructure",
    "BasisConvention",
    "BasisFunctionKind",
    "BasisSet",
    "BasisShell",
    "CalculationMetadata",
    "CalculationRecord",
    "CalculationStatus",
    "CriticalPointKind",
    "CJSONEnvelope",
    "CIFEnvelope",
    "DatasetStatus",
    "DensityMatrix",
    "DensityMatrixLevel",
    "DensityMatrixSpin",
    "DensityOfStates",
    "EnergyReference",
    "ExcitationContribution",
    "ExcitedStateReferences",
    "ExcitedStateSet",
    "FrameSet",
    "FermiSurfaceMesh",
    "Grid3D",
    "ImportBatch",
    "IssueKind",
    "MolecularTopology",
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
    "Spectrum",
    "SpectrumKind",
    "SpectrumProfile",
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
    def test_public_model_names_remain_importable(self):
        missing = sorted(name for name in PUBLIC_MODEL_NAMES if not hasattr(core, name))
        self.assertEqual(missing, [])

    def test_public_model_names_are_declared_in_core_all(self):
        missing = sorted(PUBLIC_MODEL_NAMES - set(core.__all__))
        self.assertEqual(missing, [])
