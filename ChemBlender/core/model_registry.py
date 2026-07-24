from types import MappingProxyType

from . import model


_MODEL_TYPE_NAMES = (
    "ArrayData", "CIFEnvelope", "QCSchemaEnvelope", "CJSONEnvelope",
    "PeriodicSiteData", "MolecularTopology", "Structure", "SymmetryResult",
    "CalculationMetadata", "CalculationRecord", "PropertyDataset",
    "AtomicProperty", "FrameSet", "VibrationalModeSet", "ExcitationContribution",
    "ExcitedStateReferences", "ExcitedStateSet", "Spectrum", "BandPathBranch",
    "BandStructure", "DensityOfStates", "PhononModeSet", "SurfaceProperty",
    "FermiSurfaceMesh", "TopologyConnection", "TopologyPath", "TopologyGraph",
    "BasisShell", "BasisConvention", "BasisSet", "OrbitalChannel", "OrbitalSet",
    "DensityMatrix", "Grid3D", "ProvenanceRecord", "ParserIssue", "ParserReport",
    "ImportBatch", "QCProject", "SourceRecord", "SourceRevision",
    "DiagnosticValue", "ImportDiagnostic",
)

MODEL_TYPES = MappingProxyType({name: getattr(model, name) for name in _MODEL_TYPE_NAMES})
MODEL_ENUMS = MappingProxyType({
    name: getattr(model, name)
    for name in (
        "CalculationStatus", "DatasetStatus", "IssueKind", "BasisFunctionKind",
        "OrbitalKind", "DensityMatrixLevel", "DensityMatrixSpin", "SpectrumKind",
        "SpectrumProfile", "SpinChannel", "EnergyReference", "CriticalPointKind",
        "QualityStatus", "DiagnosticSeverity",
    )
})


def model_type_tag(value):
    cls = value if isinstance(value, type) else type(value)
    for tag, registered in MODEL_TYPES.items():
        if registered is cls:
            return tag
    raise TypeError(f"unregistered model type: {cls.__name__}")


def model_type_from_tag(tag):
    return MODEL_TYPES[tag]
