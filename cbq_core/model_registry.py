from dataclasses import fields, is_dataclass
from uuid import UUID
from .model import ImportBatch
from types import MappingProxyType

from . import model


_MODEL_TYPE_NAMES = (
    "ArrayData", "AtomicIdentityData", "CIFEnvelope", "QCSchemaEnvelope", "CJSONEnvelope",
    "BiologicalAtomSiteData", "BiologicalChain", "BiologicalHierarchy",
    "BiologicalModel", "BiologicalResidue", "ChemicalAnnotation", "ExternalReference",
    "PeriodicSiteData", "MolecularTopology", "TopologyRecord", "Structure", "SymmetryResult",
    "CalculationMetadata", "CalculationRecord", "CategoricalData",
    "PropertyDataset", "AtomicProperty", "FrameSet", "FrameProperty",
    "AtomFrameProperty", "CellFrameProperty", "VibrationalModeSet",
    "RawRecordProperty", "MolecularRecord", "RecordPropertyColumn", "ConformerSet",
    "ExcitationContribution",
    "ExcitedStateReferences", "ExcitedStateSet", "Spectrum", "BandPathBranch",
    "BandStructure", "DensityOfStates", "PhononModeSet", "SurfaceProperty",
    "FermiSurfaceMesh", "TopologyConnection", "TopologyPath", "TopologyGraph",
    "BasisShell", "BasisConvention", "BasisSet", "OrbitalChannel", "OrbitalSet",
    "DensityMatrix", "Grid3D", "ProvenanceRecord", "ParserIssue", "ParserReport",
    "ImportBatch", "QCProject", "SourceRecord", "SourceRevision",
    "DiagnosticValue", "ImportDiagnostic", "CalculationGroup",
)

MODEL_TYPES = MappingProxyType({name: getattr(model, name) for name in _MODEL_TYPE_NAMES})
MODEL_ENUMS = MappingProxyType({
    name: getattr(model, name)
    for name in (
        "CalculationStatus", "DatasetStatus", "IssueKind", "BasisFunctionKind",
        "OrbitalKind", "DensityMatrixLevel", "DensityMatrixSpin", "SpectrumKind",
        "SpectrumProfile", "SpinChannel", "EnergyReference", "CriticalPointKind",
        "QualityStatus", "DiagnosticSeverity",
        "TopologySource",
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


def _semantic_uuid_references(value):
    if type(value) is UUID:
        yield value
        return
    if type(value) in (tuple, list):
        for member in value:
            yield from _semantic_uuid_references(member)
        return
    model_root = ImportBatch.__module__.rsplit(".", 1)[0]
    value_module = type(value).__module__
    if not (
        is_dataclass(value)
        and (
            value_module == model_root
            or value_module.startswith(f"{model_root}.")
        )
    ):
        return
    for item in fields(value):
        if item.name in {"id", "parameters", "values"}:
            continue
        yield from _semantic_uuid_references(getattr(value, item.name))
