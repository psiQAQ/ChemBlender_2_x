import unittest

import ChemBlender.core as core
from ChemBlender.core import model


EXPECTED_MODULES = {
    "PeriodicSiteData": "ChemBlender.core.model.structure",
    "MolecularTopology": "ChemBlender.core.model.structure",
    "Structure": "ChemBlender.core.model.structure",
    "SymmetryResult": "ChemBlender.core.model.structure",
    "PropertyDataset": "ChemBlender.core.model.properties",
    "AtomicProperty": "ChemBlender.core.model.properties",
    "FrameSet": "ChemBlender.core.model.properties",
    "Grid3D": "ChemBlender.core.model.grids",
    "VibrationalModeSet": "ChemBlender.core.model.spectroscopy",
    "ExcitationContribution": "ChemBlender.core.model.spectroscopy",
    "ExcitedStateReferences": "ChemBlender.core.model.spectroscopy",
    "ExcitedStateSet": "ChemBlender.core.model.spectroscopy",
    "Spectrum": "ChemBlender.core.model.spectroscopy",
    "BasisShell": "ChemBlender.core.model.wavefunction",
    "BasisConvention": "ChemBlender.core.model.wavefunction",
    "BasisSet": "ChemBlender.core.model.wavefunction",
    "OrbitalChannel": "ChemBlender.core.model.wavefunction",
    "OrbitalSet": "ChemBlender.core.model.wavefunction",
    "DensityMatrix": "ChemBlender.core.model.wavefunction",
    "BandPathBranch": "ChemBlender.core.model.periodic",
    "BandStructure": "ChemBlender.core.model.periodic",
    "DensityOfStates": "ChemBlender.core.model.periodic",
    "PhononModeSet": "ChemBlender.core.model.periodic",
    "SurfaceProperty": "ChemBlender.core.model.periodic",
    "FermiSurfaceMesh": "ChemBlender.core.model.periodic",
    "TopologyConnection": "ChemBlender.core.model.topology",
    "TopologyPath": "ChemBlender.core.model.topology",
    "TopologyGraph": "ChemBlender.core.model.topology",
    "CIFEnvelope": "ChemBlender.core.model.project",
    "QCSchemaEnvelope": "ChemBlender.core.model.project",
    "CJSONEnvelope": "ChemBlender.core.model.project",
    "CalculationMetadata": "ChemBlender.core.model.project",
    "CalculationRecord": "ChemBlender.core.model.project",
    "ProvenanceRecord": "ChemBlender.core.model.project",
    "ImportBatch": "ChemBlender.core.model.project",
    "QCProject": "ChemBlender.core.model.project",
}


class ModelModuleTests(unittest.TestCase):
    def test_domain_types_have_focused_module_origins(self):
        actual = {
            name: getattr(model, name).__module__
            for name in EXPECTED_MODULES
        }
        self.assertEqual(actual, EXPECTED_MODULES)
        for name in EXPECTED_MODULES:
            with self.subTest(name=name):
                self.assertIs(getattr(core, name), getattr(model, name))


if __name__ == "__main__":
    unittest.main()
