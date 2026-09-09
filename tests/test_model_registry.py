import unittest
from dataclasses import dataclass
from pathlib import Path

from cbq_core.model import AtomicProperty
from cbq_core.model import FrameSet
from cbq_core.model import Grid3D
from cbq_core.model import ProvenanceRecord
from cbq_core.model import Structure
from cbq_core.model import TopologyRecord
from cbq_core.model_registry import MODEL_ENUMS
from cbq_core.model_registry import MODEL_TYPES
from cbq_core.model_registry import model_type_from_tag
from cbq_core.model_registry import model_type_tag
from cbq_core.sidecar import SidecarIntegrityError
from cbq_core.sidecar import _Encoder
from cbq_core.sidecar import close_project
from cbq_core.sidecar import open_project
from tests.test_sidecar_storage import PROJECT_ID, sample_project


EXPECTED_MODEL_TYPES = {
    "ArrayData", "AtomicIdentityData", "CIFEnvelope", "QCSchemaEnvelope", "CJSONEnvelope",
    "BiologicalAtomSiteData", "BiologicalChain", "BiologicalHierarchy",
    "BiologicalModel", "BiologicalResidue", "ChemicalAnnotation", "ExternalReference",
    "PeriodicSiteData", "MolecularTopology", "TopologyRecord", "Structure", "SymmetryResult",
    "CalculationMetadata", "CalculationRecord", "CategoricalData",
    "PropertyDataset", "AtomicProperty", "FrameSet", "FrameProperty",
    "AtomFrameProperty", "CellFrameProperty", "VibrationalModeSet",
    "RawRecordProperty", "MolecularRecord", "RecordPropertyColumn", "ConformerSet",
    "ExcitationContribution", "ExcitedStateReferences", "ExcitedStateSet",
    "Spectrum", "BandPathBranch", "BandStructure", "DensityOfStates",
    "PhononModeSet", "SurfaceProperty", "FermiSurfaceMesh",
    "TopologyConnection", "TopologyPath", "TopologyGraph", "BasisShell",
    "BasisConvention", "BasisSet", "OrbitalChannel", "OrbitalSet",
    "DensityMatrix", "Grid3D", "ProvenanceRecord", "ParserIssue",
    "ParserReport", "ImportBatch", "QCProject", "SourceRecord", "SourceRevision",
    "DiagnosticValue", "ImportDiagnostic", "CalculationGroup",
}

EXPECTED_MODEL_ENUMS = {
    "CalculationStatus", "DatasetStatus", "IssueKind", "BasisFunctionKind",
    "OrbitalKind", "DensityMatrixLevel", "DensityMatrixSpin", "SpectrumKind",
    "SpectrumProfile", "SpinChannel", "EnergyReference",
    "CriticalPointKind",
    "QualityStatus", "DiagnosticSeverity", "TopologySource",
}

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sidecar" / "model-v01"


class ModelRegistryTests(unittest.TestCase):
    def test_mapping_key_sets_are_exact_and_immutable(self):
        self.assertEqual(set(MODEL_TYPES), EXPECTED_MODEL_TYPES)
        self.assertEqual(set(MODEL_ENUMS), EXPECTED_MODEL_ENUMS)
        with self.assertRaises(TypeError):
            MODEL_TYPES["UnregisteredType"] = object
        with self.assertRaises(TypeError):
            MODEL_ENUMS["UnregisteredType"] = object

    def test_every_model_tag_round_trips_to_its_identical_class(self):
        self.assertEqual(len(set(MODEL_TYPES.values())), len(MODEL_TYPES))
        for tag, class_type in MODEL_TYPES.items():
            self.assertIs(model_type_from_tag(tag), class_type)
            self.assertEqual(model_type_tag(class_type), tag)

    def test_structure_tag_is_stable_for_class_and_instance(self):
        structure = next(iter(sample_project().structures.values()))
        self.assertEqual(model_type_tag(Structure), "Structure")
        self.assertEqual(model_type_tag(structure), "Structure")
        self.assertIs(model_type_from_tag("Structure"), Structure)

    def test_unknown_tag_is_rejected(self):
        with self.assertRaises(KeyError):
            model_type_from_tag("UnregisteredType")

    def test_unregistered_same_name_dataclass_is_rejected(self):
        @dataclass
        class Structure:
            value: int

        with self.assertRaises(TypeError):
            model_type_tag(Structure)
        with self.assertRaisesRegex(SidecarIntegrityError, "unsupported manifest value: Structure"):
            _Encoder(Path.cwd()).encode(Structure(1))

    def test_committed_v01_fixture_restores_concrete_types(self):
        project = open_project(FIXTURE)
        try:
            self.assertEqual(project.id, PROJECT_ID)
            structure = next(iter(project.structures.values()))
            self.assertIs(type(structure), Structure)
            self.assertIsNone(structure.topology)
            topology = project.topologies[structure.topology_ids[0]]
            self.assertIs(type(topology), TopologyRecord)
            self.assertIs(type(next(iter(project.datasets.values()))), AtomicProperty)
            self.assertEqual(
                {type(value) for value in project.datasets.values()},
                {AtomicProperty, FrameSet, Grid3D},
            )
            self.assertIs(type(next(iter(project.provenance.values()))), ProvenanceRecord)
        finally:
            close_project(project)
