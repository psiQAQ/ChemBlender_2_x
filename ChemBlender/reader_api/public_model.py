import math
from dataclasses import dataclass, field, fields
from uuid import UUID

from ..core import (
    ArrayData,
    AtomicIdentityData,
    AtomFrameProperty,
    AtomicProperty,
    BandPathBranch,
    BandStructure,
    BiologicalAtomSiteData,
    BiologicalChain,
    BiologicalHierarchy,
    BiologicalModel,
    BiologicalResidue,
    BasisConvention,
    BasisFunctionKind,
    BasisSet,
    BasisShell,
    CalculationMetadata,
    CalculationRecord,
    CalculationStatus,
    CategoricalData,
    ChemicalAnnotation,
    ConformerSet,
    CJSONEnvelope,
    CIFEnvelope,
    CriticalPointKind,
    DatasetStatus,
    DensityMatrix,
    DensityMatrixLevel,
    DensityMatrixSpin,
    DensityOfStates,
    DiagnosticSeverity,
    DiagnosticValue,
    EnergyReference,
    ExternalReference,
    ExcitationContribution,
    ExcitedStateReferences,
    ExcitedStateSet,
    FermiSurfaceMesh,
    FrameSet,
    FrameProperty,
    CellFrameProperty,
    Grid3D,
    ImportDiagnostic,
    IssueKind,
    MolecularTopology,
    MolecularRecord,
    RawRecordProperty,
    RecordPropertyColumn,
    TopologyRecord,
    TopologySource,
    OrbitalChannel,
    OrbitalKind,
    OrbitalSet,
    ParserIssue,
    ParserReport,
    PeriodicSiteData,
    PhononModeSet,
    PropertyDataset,
    ProvenanceRecord,
    QCSchemaEnvelope,
    QualityStatus,
    SourceRecord,
    SourceRevision,
    Spectrum,
    SpectrumKind,
    SpectrumProfile,
    SpinChannel,
    Structure,
    SurfaceProperty,
    SymmetryResult,
    TopologyConnection,
    TopologyGraph,
    TopologyPath,
    VibrationalModeSet,
)
from ..core.model_registry import MODEL_ENUMS as _MODEL_ENUMS
from ..core.model_registry import MODEL_TYPES as _MODEL_TYPES


_GROUP_TYPES = (
    ("sources", frozenset((SourceRecord,))),
    ("source_revisions", frozenset((SourceRevision,))),
    ("structures", frozenset((Structure,))),
    ("topologies", frozenset((TopologyRecord,))),
    ("molecular_records", frozenset((MolecularRecord,))),
    ("biological_hierarchies", frozenset((BiologicalHierarchy,))),
    ("annotations", frozenset((ChemicalAnnotation,))),
    ("external_references", frozenset((ExternalReference,))),
    ("cif_envelopes", frozenset((CIFEnvelope,))),
    ("qcschema_envelopes", frozenset((QCSchemaEnvelope,))),
    ("cjson_envelopes", frozenset((CJSONEnvelope,))),
    ("symmetry_results", frozenset((SymmetryResult,))),
    ("calculations", frozenset((CalculationRecord,))),
    ("datasets", frozenset((
        PropertyDataset, AtomicProperty, FrameSet, FrameProperty,
        AtomFrameProperty, CellFrameProperty, Grid3D, VibrationalModeSet,
        ExcitedStateSet, Spectrum, BandStructure, DensityOfStates,
        PhononModeSet, FermiSurfaceMesh, TopologyGraph, RecordPropertyColumn,
        ConformerSet,
    ))),
    ("basis_sets", frozenset((BasisSet,))),
    ("orbital_sets", frozenset((OrbitalSet,))),
    ("density_matrices", frozenset((DensityMatrix,))),
    ("provenance", frozenset((ProvenanceRecord,))),
    ("diagnostics", frozenset((ImportDiagnostic,))),
)
_PUBLIC_MODEL_TYPES = frozenset(
    model_type
    for name, model_type in _MODEL_TYPES.items()
    if name not in {"CalculationGroup", "ImportBatch", "QCProject"}
)
_PUBLIC_ENUM_TYPES = frozenset(_MODEL_ENUMS.values())


def _validate_public_batch_values(batch):
    active = set()
    validated = set()

    def visit(value, *, array_values=False):
        value_type = type(value)
        if callable(value):
            raise TypeError("public batch values must not be callable")
        if value is None or value_type in (str, bytes, bool, int, UUID):
            return
        if value_type is float:
            if not math.isfinite(value):
                raise TypeError("public batch floats must be finite")
            return
        if value_type in _PUBLIC_ENUM_TYPES:
            return
        if array_values:
            from ..core.sidecar import LazyNpyArray
            import numpy

            if value_type in (memoryview, numpy.ndarray, numpy.memmap, LazyNpyArray):
                dtype = numpy.asarray(value).dtype if value_type is memoryview else numpy.dtype(value.dtype)
                if (
                    dtype.hasobject
                    or dtype.fields is not None
                    or dtype.subdtype is not None
                ):
                    raise TypeError(
                        "ArrayData values must not use object, structured or subarray dtype"
                    )
                return
            raise TypeError("ArrayData values use an unapproved array type")
        if value_type in (list, dict, set, bytearray):
            raise TypeError("public batch values must be immutable")
        if value_type is tuple:
            for item in value:
                visit(item)
            return
        if value_type is not PublicImportBatch and value_type not in _PUBLIC_MODEL_TYPES:
            raise TypeError(
                f"unregistered public batch value: {value_type.__name__}"
            )
        identity = id(value)
        if identity in active:
            raise TypeError("public batch values must not be recursive")
        if identity in validated:
            return
        active.add(identity)
        try:
            for field in fields(value):
                try:
                    field_value = getattr(value, field.name)
                except AttributeError as error:
                    raise TypeError(
                        f"incomplete public batch value: {value_type.__name__}"
                    ) from error
                visit(
                    field_value,
                    array_values=value_type is ArrayData and field.name == "values",
                )
        finally:
            active.remove(identity)
        validated.add(identity)

    visit(batch)


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class PublicImportBatch:
    sources: tuple[SourceRecord, ...] = ()
    source_revisions: tuple[SourceRevision, ...] = ()
    structures: tuple[Structure, ...] = ()
    topologies: tuple[TopologyRecord, ...] = ()
    molecular_records: tuple[MolecularRecord, ...] = ()
    biological_hierarchies: tuple[BiologicalHierarchy, ...] = field(
        default=(), kw_only=True
    )
    annotations: tuple[ChemicalAnnotation, ...] = field(default=(), kw_only=True)
    external_references: tuple[ExternalReference, ...] = field(
        default=(), kw_only=True
    )
    cif_envelopes: tuple[CIFEnvelope, ...] = ()
    qcschema_envelopes: tuple[QCSchemaEnvelope, ...] = ()
    cjson_envelopes: tuple[CJSONEnvelope, ...] = ()
    symmetry_results: tuple[SymmetryResult, ...] = ()
    calculations: tuple[CalculationRecord, ...] = ()
    datasets: tuple[PropertyDataset | Grid3D, ...] = ()
    basis_sets: tuple[BasisSet, ...] = ()
    orbital_sets: tuple[OrbitalSet, ...] = ()
    density_matrices: tuple[DensityMatrix, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    report: ParserReport | None = None
    diagnostics: tuple[ImportDiagnostic, ...] = ()

    def __post_init__(self):
        for name, allowed_types in _GROUP_TYPES:
            values = tuple(getattr(self, name))
            if any(type(value) not in allowed_types for value in values):
                raise TypeError(f"{name} contains an invalid entity type")
            object.__setattr__(self, name, values)
        if self.report is not None and type(self.report) is not ParserReport:
            raise TypeError("report must be a ParserReport")
