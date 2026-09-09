import math
from dataclasses import dataclass, field, fields
from uuid import UUID

from cbq_core.model import ArrayData
from cbq_core.model import AtomicIdentityData
from cbq_core.model import AtomFrameProperty
from cbq_core.model import AtomicProperty
from cbq_core.model import BandPathBranch
from cbq_core.model import BandStructure
from cbq_core.model import BiologicalAtomSiteData
from cbq_core.model import BiologicalChain
from cbq_core.model import BiologicalHierarchy
from cbq_core.model import BiologicalModel
from cbq_core.model import BiologicalResidue
from cbq_core.model import BasisConvention
from cbq_core.model import BasisFunctionKind
from cbq_core.model import BasisSet
from cbq_core.model import BasisShell
from cbq_core.model import CalculationMetadata
from cbq_core.model import CalculationRecord
from cbq_core.model import CalculationStatus
from cbq_core.model import CategoricalData
from cbq_core.model import ChemicalAnnotation
from cbq_core.model import ConformerSet
from cbq_core.model import CJSONEnvelope
from cbq_core.model import CIFEnvelope
from cbq_core.model import CriticalPointKind
from cbq_core.model import DatasetStatus
from cbq_core.model import DensityMatrix
from cbq_core.model import DensityMatrixLevel
from cbq_core.model import DensityMatrixSpin
from cbq_core.model import DensityOfStates
from cbq_core.model import DiagnosticSeverity
from cbq_core.model import DiagnosticValue
from cbq_core.model import EnergyReference
from cbq_core.model import ExternalReference
from cbq_core.model import ExcitationContribution
from cbq_core.model import ExcitedStateReferences
from cbq_core.model import ExcitedStateSet
from cbq_core.model import FermiSurfaceMesh
from cbq_core.model import FrameSet
from cbq_core.model import FrameProperty
from cbq_core.model import CellFrameProperty
from cbq_core.model import Grid3D
from cbq_core.model import ImportDiagnostic
from cbq_core.model import IssueKind
from cbq_core.model import MolecularTopology
from cbq_core.model import MolecularRecord
from cbq_core.model import RawRecordProperty
from cbq_core.model import RecordPropertyColumn
from cbq_core.model import TopologyRecord
from cbq_core.model import TopologySource
from cbq_core.model import OrbitalChannel
from cbq_core.model import OrbitalKind
from cbq_core.model import OrbitalSet
from cbq_core.model import ParserIssue
from cbq_core.model import ParserReport
from cbq_core.model import PeriodicSiteData
from cbq_core.model import PhononModeSet
from cbq_core.model import PropertyDataset
from cbq_core.model import ProvenanceRecord
from cbq_core.model import QCSchemaEnvelope
from cbq_core.model import QualityStatus
from cbq_core.model import SourceRecord
from cbq_core.model import SourceRevision
from cbq_core.model import Spectrum
from cbq_core.model import SpectrumKind
from cbq_core.model import SpectrumProfile
from cbq_core.model import SpinChannel
from cbq_core.model import Structure
from cbq_core.model import SurfaceProperty
from cbq_core.model import SymmetryResult
from cbq_core.model import TopologyConnection
from cbq_core.model import TopologyGraph
from cbq_core.model import TopologyPath
from cbq_core.model import VibrationalModeSet
from cbq_core.model_registry import MODEL_ENUMS as _MODEL_ENUMS
from cbq_core.model_registry import MODEL_TYPES as _MODEL_TYPES


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
            from cbq_core.sidecar import LazyNpyArray
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
