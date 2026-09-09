import unittest

from cbq_core import model as core
from cbq_core import model


EXPECTED_MODULES = {
    "AtomicIdentityData": "cbq_core.model.chemical_identity",
    "PeriodicSiteData": "cbq_core.model.structure",
    "MolecularTopology": "cbq_core.model.structure",
    "TopologyRecord": "cbq_core.model.molecular_topology",
    "TopologySource": "cbq_core.model.molecular_topology",
    "Structure": "cbq_core.model.structure",
    "SymmetryResult": "cbq_core.model.structure",
    "PropertyDataset": "cbq_core.model.properties",
    "AtomicProperty": "cbq_core.model.properties",
    "AtomFrameProperty": "cbq_core.model.properties",
    "CellFrameProperty": "cbq_core.model.properties",
    "FrameProperty": "cbq_core.model.properties",
    "FrameSet": "cbq_core.model.properties",
    "CategoricalData": "cbq_core.model.categorical",
    "RawRecordProperty": "cbq_core.model.records",
    "MolecularRecord": "cbq_core.model.records",
    "RecordPropertyColumn": "cbq_core.model.records",
    "ConformerSet": "cbq_core.model.records",
    "Grid3D": "cbq_core.model.grids",
    "VibrationalModeSet": "cbq_core.model.spectroscopy",
    "ExcitationContribution": "cbq_core.model.spectroscopy",
    "ExcitedStateReferences": "cbq_core.model.spectroscopy",
    "ExcitedStateSet": "cbq_core.model.spectroscopy",
    "Spectrum": "cbq_core.model.spectroscopy",
    "BasisShell": "cbq_core.model.wavefunction",
    "BasisConvention": "cbq_core.model.wavefunction",
    "BasisSet": "cbq_core.model.wavefunction",
    "OrbitalChannel": "cbq_core.model.wavefunction",
    "OrbitalSet": "cbq_core.model.wavefunction",
    "DensityMatrix": "cbq_core.model.wavefunction",
    "BandPathBranch": "cbq_core.model.periodic",
    "BandStructure": "cbq_core.model.periodic",
    "DensityOfStates": "cbq_core.model.periodic",
    "PhononModeSet": "cbq_core.model.periodic",
    "SurfaceProperty": "cbq_core.model.periodic",
    "FermiSurfaceMesh": "cbq_core.model.periodic",
    "TopologyConnection": "cbq_core.model.topology",
    "TopologyPath": "cbq_core.model.topology",
    "TopologyGraph": "cbq_core.model.topology",
    "CIFEnvelope": "cbq_core.model.project",
    "QCSchemaEnvelope": "cbq_core.model.project",
    "CJSONEnvelope": "cbq_core.model.project",
    "CalculationMetadata": "cbq_core.model.project",
    "CalculationRecord": "cbq_core.model.project",
    "ProvenanceRecord": "cbq_core.model.project",
    "ImportBatch": "cbq_core.model.project",
    "QCProject": "cbq_core.model.project",
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
