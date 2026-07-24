import subprocess
import sys
import unittest
from pathlib import Path

import ChemBlender.core as core
from ChemBlender.core.model_registry import MODEL_ENUMS, MODEL_TYPES


PUBLIC_CORE_NAMES = (
    "AnalysisReportError", "AmbiguousReaderError", "ASE_STRUCTURE_READER",
    "ASEDependencyError", "ArrayData", "AtomicProperty", "BandPathBranch",
    "BandStructure", "BasisConvention", "BasisFunctionKind", "BasisSet",
    "BasisShell", "CalculationRecord", "CalculationMetadata",
    "CalculationStatus", "CriticalPointKind", "CJSONEnvelope", "CJSON_READER",
    "CJSONCompatibilityError", "CJSONError", "CacheIdentityError", "CacheClearResult", "CIFEnvelope",
    "CapabilitySupport", "CCLIB_OUTPUT_READER", "CCLibDependencyError", "CIF_READER",
    "CUBE_READER", "DatasetStatus", "DiagnosticSeverity", "DiagnosticValue",
    "DensityMatrix", "DensityMatrixLevel",
    "DensityMatrixSpin", "DensityOfStates", "EnergyReference",
    "ExcitationContribution", "ExcitedStateReferences", "ExcitedStateSet", "FrameSet",
    "FrameCacheInfo", "FermiSurfaceMesh", "GemmiDependencyError", "Grid3D",
    "GBasisDependencyError", "ImportBatch", "ImportDiagnostic", "IssueKind", "LazyNpyArray",
    "IODATA_WAVEFUNCTION_READER", "IODataDependencyError", "MOL_V2000_READER",
    "MolecularTopology", "OrbitalChannel", "OrbitalKind", "OrbitalSet", "ParserIssue",
    "ParserReport", "PeriodicSiteData", "PhononModeSet", "PhonopyDependencyError",
    "PYMATGEN_VASP_GRID_READER", "PYMATGEN_VASP_ELECTRONIC_READER",
    "PymatgenDependencyError", "PymatgenElectronicDependencyError", "PropertyDataset",
    "ProjectSession", "ProjectServiceResult", "ProjectServiceStatus", "ProvenanceRecord", "QCProject", "QualityStatus", "QCSchemaEnvelope", "QCSCHEMA_READER",
    "QCSchemaCompatibilityError", "QCSchemaError", "ReaderDescriptor",
    "ReaderNotFoundError", "ReaderRegistry", "RecipeBinding", "RecipeCitation",
    "RecipeDefinition", "RecipeInputSpec", "RecipeOutputSpec", "RecipeParameterSpec",
    "RecipePlan", "RecipeValidationSpec", "RecipeViewSpec", "SniffMatch", "SniffResult",
    "SourceRecord", "SourceRevision", "Spectrum", "SpectrumKind", "SpectrumProfile", "SpinChannel", "SceneBindingSpec",
    "ScenePresetDefinition", "ScenePresetError", "ScenePresetPlan",
    "SidecarCompatibilityError", "SidecarError", "SidecarIntegrityError", "SidecarNotFoundError",
    "SpglibDependencyError", "Structure", "SurfaceProperty", "TopologyConnection",
    "TopologyGraph", "TopologyPath", "SymmetryResult", "VibrationalModeSet",
    "TrajectoryFrameManager", "XYZ_READER", "adapt_ase_atoms", "build_analysis_report",
    "export_qcschema", "export_cjson", "export_qcschema_atomic_result", "parse_cube",
    "parse_cjson", "parse_ase_structure", "parse_cclib_output", "parse_critic2_cpreport",
    "parse_qcschema", "parse_qcschema_atomic_result", "parse_qcschema_molecule", "parse_cif",
    "parse_xyz", "parse_mol_v2000", "sniff_qcschema", "sniff_cjson", "sniff_mol_v2000",
    "sniff_cube", "sniff_ase_structure", "sniff_cclib_output", "sniff_cif", "sniff_xyz",
    "adapt_ccdata", "adapt_iodata", "adapt_vasp_volumetric", "adapt_pymatgen_electronic",
    "adapt_phonopy_qpoints", "adapt_pyprocar_fermi_surface", "parse_vasp_volumetric",
    "parse_vasprun_electronic", "sniff_vasp_volumetric", "sniff_vasprun",
    "parse_iodata_wavefunction", "sniff_iodata_wavefunction", "evaluate_electron_density_grid",
    "evaluate_density_matrix_grid", "evaluate_electrostatic_potential_grid",
    "evaluate_molecular_orbital_grid", "derive_electronic_spectrum",
    "ExternalConnectorDescriptor", "ExternalConnectorError", "ExternalRecordRequest",
    "derive_grid_lod", "derive_phonon_frames", "derive_symmetry",
    "derive_vibrational_spectrum", "describe_report_artifact", "close_project",
    "close_session", "clear_derived_cache", "create_session", "derivation_cache_key", "open_project",
    "parser_cache_key", "render_cache_key",
    "render_analysis_report_markdown", "reader_capability_document", "builtin_recipes",
    "builtin_reader_descriptors", "builtin_reader_registry", "builtin_external_connectors",
    "builtin_scene_presets", "plan_recipe", "plan_scene_preset", "recipe_document",
    "recipe_from_document", "relink_project_session", "save_project", "save_project_session", "scene_plan_document", "scene_preset_document",
    "scene_preset_from_document", "scene_preset_for_recipe_view", "validate_scene_plan",
    "source_hash_bytes", "source_parse_identity", "diagnostic_from_parser_issue", "external_record_request_document",
    "external_record_request_from_document", "external_record_source_uri",
    "surface_render_cache_key", "volume_render_cache_key", "validate_analysis_report", "verify_project_session",
    "write_analysis_report_bundle",
)


class CorePublicApiTests(unittest.TestCase):
    def test_public_names_are_frozen(self):
        self.assertEqual(tuple(core.__all__), PUBLIC_CORE_NAMES)
        self.assertEqual(len(core.__all__), len(set(core.__all__)))
        self.assertEqual(len(core.__all__), 201)

    def test_public_names_resolve_to_attributes(self):
        missing = [name for name in core.__all__ if not hasattr(core, name)]
        self.assertEqual(missing, [])

    def test_registered_models_and_enums_match_the_facade(self):
        for name, model_type in {**MODEL_TYPES, **MODEL_ENUMS}.items():
            with self.subTest(name=name):
                self.assertIs(getattr(core, name), model_type)

    def test_import_does_not_load_blender_or_optional_stacks(self):
        code = (
            "import sys; import ChemBlender.core; "
            "forbidden = {'bpy', 'cclib', 'iodata', 'gbasis', 'ase', 'pymatgen'}; "
            "raise SystemExit(bool(forbidden & set(sys.modules)))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_api_document_contract(self):
        document = (
            Path(__file__).resolve().parents[1]
            / "docs/quantum-visualization/2.3.0/public-core-api.md"
        )
        self.assertTrue(document.is_file(), f"missing API document: {document}")
        content = document.read_bytes()
        self.assertFalse(content.startswith(b"\xef\xbb\xbf"))
        text = content.decode("utf-8")
        for heading in (
            "## 稳定模型门面",
            "## 存储 API",
            "## Session API",
            "## Reader 契约",
            "## Recipe 契约",
            "## 内部 Adapter 兼容面",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)
