from dataclasses import dataclass

from ..core import (
    ArrayData,
    AtomicProperty,
    BandPathBranch,
    BandStructure,
    BasisConvention,
    BasisFunctionKind,
    BasisSet,
    BasisShell,
    CalculationMetadata,
    CalculationRecord,
    CalculationStatus,
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
    ExcitationContribution,
    ExcitedStateReferences,
    ExcitedStateSet,
    FermiSurfaceMesh,
    FrameSet,
    Grid3D,
    ImportDiagnostic,
    IssueKind,
    MolecularTopology,
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


_GROUP_TYPES = (
    ("sources", frozenset((SourceRecord,))),
    ("source_revisions", frozenset((SourceRevision,))),
    ("structures", frozenset((Structure,))),
    ("cif_envelopes", frozenset((CIFEnvelope,))),
    ("qcschema_envelopes", frozenset((QCSchemaEnvelope,))),
    ("cjson_envelopes", frozenset((CJSONEnvelope,))),
    ("symmetry_results", frozenset((SymmetryResult,))),
    ("calculations", frozenset((CalculationRecord,))),
    ("datasets", frozenset((
        PropertyDataset, AtomicProperty, FrameSet, Grid3D, VibrationalModeSet,
        ExcitedStateSet, Spectrum, BandStructure, DensityOfStates,
        PhononModeSet, FermiSurfaceMesh, TopologyGraph,
    ))),
    ("basis_sets", frozenset((BasisSet,))),
    ("orbital_sets", frozenset((OrbitalSet,))),
    ("density_matrices", frozenset((DensityMatrix,))),
    ("provenance", frozenset((ProvenanceRecord,))),
    ("diagnostics", frozenset((ImportDiagnostic,))),
)


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class PublicImportBatch:
    sources: tuple[SourceRecord, ...] = ()
    source_revisions: tuple[SourceRevision, ...] = ()
    structures: tuple[Structure, ...] = ()
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
