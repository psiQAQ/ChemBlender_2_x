import unittest

import ChemBlender.core as core


PUBLIC_MODEL_NAMES = {
    "ArrayData", "AtomicProperty", "BandStructure", "BasisSet",
    "CalculationRecord", "CJSONEnvelope", "CIFEnvelope", "DensityMatrix",
    "DensityOfStates", "ExcitedStateSet", "FrameSet", "FermiSurfaceMesh",
    "Grid3D", "ImportBatch", "MolecularTopology", "OrbitalSet",
    "ParserIssue", "ParserReport", "PeriodicSiteData", "PhononModeSet",
    "PropertyDataset", "ProvenanceRecord", "QCProject", "QCSchemaEnvelope",
    "Spectrum", "Structure", "SymmetryResult", "TopologyGraph",
    "VibrationalModeSet",
}


class ModelPublicSurfaceTests(unittest.TestCase):
    def test_public_model_names_remain_importable(self):
        missing = sorted(name for name in PUBLIC_MODEL_NAMES if not hasattr(core, name))
        self.assertEqual(missing, [])
