import re
from dataclasses import dataclass, field
from uuid import UUID

from .common import (
    _ID_PATTERN,
    CalculationStatus,
    OrbitalKind,
    SpectrumKind,
    _require_text,
    _require_token,
    _require_uuid,
    _require_uuid_tuple,
)
from .diagnostics import ParserReport
from .grids import Grid3D
from .periodic import (
    BandStructure,
    DensityOfStates,
    FermiSurfaceMesh,
    PhononModeSet,
)
from .properties import AtomicProperty, FrameSet, PropertyDataset
from .sources import SourceRecord, SourceRevision
from .spectroscopy import (
    ExcitedStateSet,
    Spectrum,
    VibrationalModeSet,
)
from .structure import Structure, SymmetryResult
from .topology import TopologyGraph
from .wavefunction import BasisSet, DensityMatrix, OrbitalSet


@dataclass(frozen=True, slots=True)
class CIFEnvelope:
    id: UUID
    revision: str
    block_name: str
    source_bytes: bytes
    tag_names: tuple[str, ...]
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_text(self.block_name, "block_name")
        if not isinstance(self.source_bytes, bytes) or not self.source_bytes:
            raise ValueError("source_bytes must be non-empty bytes")
        tag_names = tuple(self.tag_names)
        if any(
            not isinstance(tag, str) or not tag.startswith("_")
            for tag in tag_names
        ):
            raise ValueError("tag_names must contain CIF tags")
        object.__setattr__(self, "tag_names", tag_names)
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class QCSchemaEnvelope:
    id: UUID
    revision: str
    schema_name: str
    schema_version: int
    source_bytes: bytes
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_token(self.schema_name, "schema_name", _ID_PATTERN)
        if isinstance(self.schema_version, bool) or not isinstance(
            self.schema_version, int
        ) or self.schema_version <= 0:
            raise ValueError("schema_version must be a positive integer")
        if not isinstance(self.source_bytes, bytes) or not self.source_bytes:
            raise ValueError("source_bytes must be non-empty bytes")
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class CJSONEnvelope:
    id: UUID
    revision: str
    format_version: int
    source_bytes: bytes
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        if isinstance(self.format_version, bool) or self.format_version not in (0, 1):
            raise ValueError("format_version must be CJSON version 0 or 1")
        if not isinstance(self.source_bytes, bytes) or not self.source_bytes:
            raise ValueError("source_bytes must be non-empty bytes")
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class CalculationMetadata:
    driver: str
    method: str
    basis: str | None
    molecular_charge: int
    molecular_multiplicity: int
    program: str
    program_version: str
    error_type: str | None = None
    error_message: str | None = None
    qcschema_envelope_id: UUID | None = None

    def __post_init__(self):
        for value, name in (
            (self.driver, "driver"),
            (self.method, "method"),
            (self.program, "program"),
            (self.program_version, "program_version"),
        ):
            _require_text(value, name)
        if self.basis is not None and not isinstance(self.basis, str):
            raise TypeError("basis must be a string or None")
        for value, name in (
            (self.molecular_charge, "molecular_charge"),
            (self.molecular_multiplicity, "molecular_multiplicity"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if self.molecular_multiplicity <= 0:
            raise ValueError("molecular_multiplicity must be positive")
        for value, name in (
            (self.error_type, "error_type"),
            (self.error_message, "error_message"),
        ):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string or None")
        if self.qcschema_envelope_id is not None:
            _require_uuid(self.qcschema_envelope_id, "qcschema_envelope_id")


@dataclass(frozen=True, slots=True)
class CalculationRecord:
    id: UUID
    revision: str
    status: CalculationStatus
    input_structure_ids: tuple[UUID, ...]
    result_structure_ids: tuple[UUID, ...]
    dataset_ids: tuple[UUID, ...]
    provenance_ids: tuple[UUID, ...]
    metadata: CalculationMetadata | None = None

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        if not isinstance(self.status, CalculationStatus):
            raise TypeError("status must be a CalculationStatus")
        for name in (
            "input_structure_ids",
            "result_structure_ids",
            "dataset_ids",
            "provenance_ids",
        ):
            object.__setattr__(self, name, _require_uuid_tuple(getattr(self, name), name))
        if self.metadata is not None and not isinstance(
            self.metadata, CalculationMetadata
        ):
            raise TypeError("metadata must be CalculationMetadata or None")


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    id: UUID
    revision: str
    producer: str
    producer_version: str
    source: str
    source_hash: str
    parent_ids: tuple[UUID, ...]
    operation: str
    parameters: tuple[tuple[str, object], ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        for name in ("revision", "producer", "producer_version", "operation"):
            _require_text(getattr(self, name), name)
        if not isinstance(self.source, str):
            raise TypeError("source must be a string")
        if self.source_hash and not re.fullmatch(r"[0-9a-f]{64}", self.source_hash):
            raise ValueError("source_hash must be an empty string or SHA-256 hex")
        object.__setattr__(
            self,
            "parent_ids",
            _require_uuid_tuple(self.parent_ids, "parent_ids"),
        )
        parameters = tuple(self.parameters)
        if any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0]
            for item in parameters
        ):
            raise ValueError("parameters must contain non-empty string keys")
        object.__setattr__(self, "parameters", parameters)


@dataclass(frozen=True, slots=True)
class ImportBatch:
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

    def __post_init__(self):
        groups = (
            ("sources", SourceRecord),
            ("source_revisions", SourceRevision),
            ("structures", Structure),
            ("cif_envelopes", CIFEnvelope),
            ("qcschema_envelopes", QCSchemaEnvelope),
            ("cjson_envelopes", CJSONEnvelope),
            ("symmetry_results", SymmetryResult),
            ("calculations", CalculationRecord),
            ("datasets", PropertyDataset),
            ("basis_sets", BasisSet),
            ("orbital_sets", OrbitalSet),
            ("density_matrices", DensityMatrix),
            ("provenance", ProvenanceRecord),
        )
        for name, entity_type in groups:
            values = tuple(getattr(self, name))
            if any(not isinstance(value, entity_type) for value in values):
                raise TypeError(f"{name} contains an invalid entity type")
            object.__setattr__(self, name, values)
        if self.report is not None and not isinstance(self.report, ParserReport):
            raise TypeError("report must be a ParserReport")


@dataclass(slots=True)
class QCProject:
    id: UUID
    schema_version: str
    sources: dict[UUID, SourceRecord] = field(default_factory=dict)
    source_revisions: dict[UUID, SourceRevision] = field(default_factory=dict)
    structures: dict[UUID, Structure] = field(default_factory=dict)
    cif_envelopes: dict[UUID, CIFEnvelope] = field(default_factory=dict)
    qcschema_envelopes: dict[UUID, QCSchemaEnvelope] = field(default_factory=dict)
    cjson_envelopes: dict[UUID, CJSONEnvelope] = field(default_factory=dict)
    symmetry_results: dict[UUID, SymmetryResult] = field(default_factory=dict)
    calculations: dict[UUID, CalculationRecord] = field(default_factory=dict)
    datasets: dict[UUID, PropertyDataset | Grid3D] = field(default_factory=dict)
    basis_sets: dict[UUID, BasisSet] = field(default_factory=dict)
    orbital_sets: dict[UUID, OrbitalSet] = field(default_factory=dict)
    density_matrices: dict[UUID, DensityMatrix] = field(default_factory=dict)
    provenance: dict[UUID, ProvenanceRecord] = field(default_factory=dict)

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.schema_version, "schema_version")
        self._validate_registries()

    def commit(self, batch):
        if not isinstance(batch, ImportBatch):
            raise TypeError("batch must be an ImportBatch")

        incoming_entity_groups = (
            batch.structures,
            batch.cif_envelopes,
            batch.qcschema_envelopes,
            batch.cjson_envelopes,
            batch.symmetry_results,
            batch.calculations,
            batch.datasets,
            batch.basis_sets,
            batch.orbital_sets,
            batch.density_matrices,
            batch.provenance,
        )
        incoming_groups = (
            batch.sources,
            batch.source_revisions,
            *incoming_entity_groups,
        )
        incoming = tuple(entity for group in incoming_groups for entity in group)
        incoming_ids = tuple(entity.id for entity in incoming)
        if len(set(incoming_ids)) != len(incoming_ids):
            raise ValueError("batch contains duplicate entity UUIDs")

        existing_ids = self._all_entity_ids()
        if existing_ids.intersection(incoming_ids):
            raise ValueError("batch UUID already exists in project")

        sources = dict(self.sources)
        sources.update((source.id, source) for source in batch.sources)
        source_revisions = dict(self.source_revisions)
        source_revisions.update(
            (revision.id, revision) for revision in batch.source_revisions
        )
        source_ids = set(sources)
        source_revision_ids = set(source_revisions)
        structures = dict(self.structures)
        structures.update(
            (structure.id, structure) for structure in batch.structures
        )
        structure_ids = set(structures)
        cif_envelope_ids = set(self.cif_envelopes).union(
            envelope.id for envelope in batch.cif_envelopes
        )
        qcschema_envelope_ids = set(self.qcschema_envelopes).union(
            envelope.id for envelope in batch.qcschema_envelopes
        )
        cjson_envelope_ids = set(self.cjson_envelopes).union(
            envelope.id for envelope in batch.cjson_envelopes
        )
        symmetry_result_ids = set(self.symmetry_results).union(
            result.id for result in batch.symmetry_results
        )
        calculation_ids = set(self.calculations).union(
            calculation.id for calculation in batch.calculations
        )
        datasets = dict(self.datasets)
        datasets.update((dataset.id, dataset) for dataset in batch.datasets)
        dataset_ids = set(datasets)
        basis_sets = dict(self.basis_sets)
        basis_sets.update((basis.id, basis) for basis in batch.basis_sets)
        basis_set_ids = set(basis_sets)
        orbital_set_ids = set(self.orbital_sets).union(
            orbital_set.id for orbital_set in batch.orbital_sets
        )
        density_matrix_ids = set(self.density_matrices).union(
            matrix.id for matrix in batch.density_matrices
        )
        provenance_ids = set(self.provenance).union(
            record.id for record in batch.provenance
        )

        for structure in batch.structures:
            if (
                structure.periodic is not None
                and structure.periodic.cif_envelope_id is not None
                and structure.periodic.cif_envelope_id not in cif_envelope_ids
            ):
                raise ValueError(
                    "periodic structure has a dangling CIF envelope reference"
                )
        for envelope in batch.cif_envelopes:
            self._require_references(
                envelope.provenance_ids,
                provenance_ids,
                "CIF envelope provenance",
            )
        for envelope in batch.qcschema_envelopes:
            self._require_references(
                envelope.provenance_ids,
                provenance_ids,
                "QCSchema envelope provenance",
            )
        for envelope in batch.cjson_envelopes:
            self._require_references(
                envelope.provenance_ids,
                provenance_ids,
                "CJSON envelope provenance",
            )
        for result in batch.symmetry_results:
            try:
                input_structure = structures[result.structure_id]
            except KeyError as error:
                raise ValueError(
                    "SymmetryResult has a dangling input structure reference"
                ) from error
            try:
                standard_structure = structures[result.standardized_structure_id]
            except KeyError as error:
                raise ValueError(
                    "SymmetryResult has a dangling standardized structure reference"
                ) from error
            if result.equivalent_atoms.shape[0] != len(input_structure.atomic_numbers):
                raise ValueError(
                    "SymmetryResult input atom mappings do not match structure"
                )
            if result.std_mapping_to_primitive.shape[0] != len(
                standard_structure.atomic_numbers
            ):
                raise ValueError(
                    "SymmetryResult standard atom mapping does not match structure"
                )
            self._require_references(
                result.provenance_ids,
                provenance_ids,
                "symmetry provenance",
            )

        for calculation in batch.calculations:
            self._require_references(
                calculation.input_structure_ids + calculation.result_structure_ids,
                structure_ids,
                "calculation structure",
            )
            self._require_references(
                calculation.dataset_ids,
                dataset_ids,
                "calculation dataset",
            )
            self._require_references(
                calculation.provenance_ids,
                provenance_ids,
                "calculation provenance",
            )
            if (
                calculation.metadata is not None
                and calculation.metadata.qcschema_envelope_id is not None
                and calculation.metadata.qcschema_envelope_id
                not in qcschema_envelope_ids
            ):
                raise ValueError(
                    "calculation has a dangling QCSchema envelope reference"
                )
        for dataset in batch.datasets:
            if (
                dataset.source_calculation is not None
                and dataset.source_calculation not in calculation_ids
            ):
                raise ValueError("dataset has a dangling calculation reference")
            self._require_references(
                dataset.provenance_ids,
                provenance_ids,
                "dataset provenance",
            )
            if isinstance(dataset, AtomicProperty):
                try:
                    reference = structures[dataset.structure_id]
                except KeyError as error:
                    raise ValueError(
                        "AtomicProperty has a dangling structure reference"
                    ) from error
                if dataset.data.shape[0] != len(reference.atomic_numbers):
                    raise ValueError(
                        "AtomicProperty atom dimension must match its structure"
                    )
            if isinstance(dataset, FrameSet):
                try:
                    reference = structures[dataset.structure_id]
                except KeyError as error:
                    raise ValueError(
                        "FrameSet has a dangling structure reference"
                    ) from error
                if dataset.data.shape[1] != len(reference.atomic_numbers):
                    raise ValueError(
                        "FrameSet atom dimension must match its structure"
                    )
                if dataset.data.unit != reference.coordinates.unit:
                    raise ValueError(
                        "FrameSet and structure coordinate units must match"
                    )
            if isinstance(dataset, VibrationalModeSet):
                try:
                    reference = structures[dataset.structure_id]
                except KeyError as error:
                    raise ValueError(
                        "VibrationalModeSet has a dangling structure reference"
                    ) from error
                if dataset.displacements.shape[1] != len(reference.atomic_numbers):
                    raise ValueError(
                        "VibrationalModeSet atom dimension must match its structure"
                    )
            if isinstance(dataset, ExcitedStateSet):
                if dataset.structure_id not in structure_ids:
                    raise ValueError(
                        "ExcitedStateSet has a dangling structure reference"
                    )
                referenced_ids = tuple(
                    reference_id
                    for references in dataset.state_references
                    for reference_id in references.referenced_ids
                )
                self._require_references(
                    referenced_ids,
                    dataset_ids,
                    "excited-state derived dataset",
                )
            if isinstance(dataset, Spectrum):
                source = datasets.get(dataset.source_dataset_id)
                expected_type = (
                    VibrationalModeSet
                    if dataset.kind in (SpectrumKind.IR, SpectrumKind.RAMAN)
                    else ExcitedStateSet
                )
                if not isinstance(source, expected_type):
                    raise ValueError(
                        f"Spectrum has a dangling {expected_type.__name__} reference"
                    )
            if (
                isinstance(dataset, Grid3D)
                and dataset.structure_id is not None
                and dataset.structure_id not in structure_ids
            ):
                raise ValueError("Grid3D has a dangling structure reference")
            if isinstance(dataset, (BandStructure, DensityOfStates)):
                try:
                    reference = structures[dataset.structure_id]
                except KeyError as error:
                    raise ValueError(
                        f"{type(dataset).__name__} has a dangling structure reference"
                    ) from error
                projections = dataset.projections
                if projections is not None:
                    atom_axis = 3 if isinstance(dataset, BandStructure) else 2
                    if projections.shape[atom_axis] != len(reference.atomic_numbers):
                        raise ValueError(
                            f"{type(dataset).__name__} projection atom dimension must match structure"
                        )
            if isinstance(dataset, PhononModeSet):
                try:
                    reference = structures[dataset.structure_id]
                except KeyError as error:
                    raise ValueError(
                        "PhononModeSet has a dangling structure reference"
                    ) from error
                if dataset.eigenvectors.shape[2] != len(reference.atomic_numbers):
                    raise ValueError(
                        "PhononModeSet atom dimension must match its structure"
                    )
            if isinstance(dataset, FermiSurfaceMesh):
                if dataset.structure_id not in structure_ids:
                    raise ValueError(
                        "FermiSurfaceMesh has a dangling structure reference"
                    )
                source = datasets.get(dataset.band_structure_id)
                if not isinstance(source, BandStructure):
                    raise ValueError(
                        "FermiSurfaceMesh has a dangling band structure reference"
                    )
                if source.structure_id != dataset.structure_id:
                    raise ValueError(
                        "FermiSurfaceMesh and BandStructure must use the same structure"
                    )
                if dataset.spin_index >= source.data.shape[0]:
                    raise ValueError("FermiSurfaceMesh spin index is outside BandStructure")
                if max(dataset.band_indices.values) >= source.data.shape[2]:
                    raise ValueError("FermiSurfaceMesh band index is outside BandStructure")
            if isinstance(dataset, TopologyGraph):
                if dataset.structure_id not in structure_ids:
                    raise ValueError("TopologyGraph has a dangling structure reference")
                if dataset.source_grid_id is not None:
                    source = datasets.get(dataset.source_grid_id)
                    if not isinstance(source, Grid3D):
                        raise ValueError("TopologyGraph has a dangling source grid reference")
                    if source.structure_id != dataset.structure_id:
                        raise ValueError("TopologyGraph and source grid must use the same structure")
        for basis in batch.basis_sets:
            try:
                reference = structures[basis.structure_id]
            except KeyError as error:
                raise ValueError("BasisSet has a dangling structure reference") from error
            if any(
                shell.center_atom >= len(reference.atomic_numbers)
                for shell in basis.shells
            ):
                raise ValueError("BasisSet shell center is outside its structure")
            self._require_references(
                basis.provenance_ids,
                provenance_ids,
                "basis provenance",
            )
        for orbital_set in batch.orbital_sets:
            if orbital_set.structure_id not in structure_ids:
                raise ValueError("OrbitalSet has a dangling structure reference")
            try:
                basis = basis_sets[orbital_set.basis_set_id]
            except KeyError as error:
                raise ValueError("OrbitalSet has a dangling basis reference") from error
            if basis.structure_id != orbital_set.structure_id:
                raise ValueError("OrbitalSet structure must match its BasisSet")
            expected_width = basis.basis_function_count * (
                2 if orbital_set.kind is OrbitalKind.GENERALIZED else 1
            )
            if any(
                channel.coefficients.shape[1] != expected_width
                for channel in orbital_set.channels
            ):
                raise ValueError("OrbitalSet coefficient width must match its BasisSet")
            self._require_references(
                orbital_set.provenance_ids,
                provenance_ids,
                "orbital provenance",
            )
        for matrix in batch.density_matrices:
            if matrix.structure_id not in structure_ids:
                raise ValueError("DensityMatrix has a dangling structure reference")
            try:
                basis = basis_sets[matrix.basis_set_id]
            except KeyError as error:
                raise ValueError("DensityMatrix has a dangling basis reference") from error
            if basis.structure_id != matrix.structure_id:
                raise ValueError("DensityMatrix structure must match its BasisSet")
            if matrix.data.shape != (
                basis.basis_function_count,
                basis.basis_function_count,
            ):
                raise ValueError("DensityMatrix width must match its BasisSet")
            if (
                matrix.source_calculation is not None
                and matrix.source_calculation not in calculation_ids
            ):
                raise ValueError("DensityMatrix has a dangling calculation reference")
            self._require_references(
                matrix.provenance_ids,
                provenance_ids,
                "density matrix provenance",
            )
        all_ids = (
            source_ids
            | source_revision_ids
            | structure_ids
            | cif_envelope_ids
            | qcschema_envelope_ids
            | cjson_envelope_ids
            | symmetry_result_ids
            | calculation_ids
            | dataset_ids
            | basis_set_ids
            | orbital_set_ids
            | density_matrix_ids
            | provenance_ids
        )
        self._validate_source_revision_references(
            source_revisions.values(),
            source_ids,
            all_ids,
        )
        for record in batch.provenance:
            self._require_references(record.parent_ids, all_ids, "provenance parent")
        if batch.report is not None and set(batch.report.created_entity_ids) != set(
            entity.id
            for group in incoming_entity_groups
            for entity in group
        ):
            raise ValueError("parser report created IDs must match the import batch")

        self.sources.update((entity.id, entity) for entity in batch.sources)
        self.source_revisions.update(
            (entity.id, entity) for entity in batch.source_revisions
        )
        self.structures.update((entity.id, entity) for entity in batch.structures)
        self.cif_envelopes.update(
            (entity.id, entity) for entity in batch.cif_envelopes
        )
        self.qcschema_envelopes.update(
            (entity.id, entity) for entity in batch.qcschema_envelopes
        )
        self.cjson_envelopes.update(
            (entity.id, entity) for entity in batch.cjson_envelopes
        )
        self.symmetry_results.update(
            (entity.id, entity) for entity in batch.symmetry_results
        )
        self.calculations.update((entity.id, entity) for entity in batch.calculations)
        self.datasets.update((entity.id, entity) for entity in batch.datasets)
        self.basis_sets.update((entity.id, entity) for entity in batch.basis_sets)
        self.orbital_sets.update((entity.id, entity) for entity in batch.orbital_sets)
        self.density_matrices.update(
            (entity.id, entity) for entity in batch.density_matrices
        )
        self.provenance.update((entity.id, entity) for entity in batch.provenance)

    def _all_entity_ids(self):
        groups = (
            self.sources,
            self.source_revisions,
            self.structures,
            self.cif_envelopes,
            self.qcschema_envelopes,
            self.cjson_envelopes,
            self.symmetry_results,
            self.calculations,
            self.datasets,
            self.basis_sets,
            self.orbital_sets,
            self.density_matrices,
            self.provenance,
        )
        ids = [entity_id for group in groups for entity_id in group]
        if len(set(ids)) != len(ids):
            raise ValueError("project registries contain duplicate entity UUIDs")
        return set(ids)

    def _validate_registries(self):
        groups = (
            (self.sources, SourceRecord, "sources"),
            (self.source_revisions, SourceRevision, "source_revisions"),
            (self.structures, Structure, "structures"),
            (self.cif_envelopes, CIFEnvelope, "cif_envelopes"),
            (self.qcschema_envelopes, QCSchemaEnvelope, "qcschema_envelopes"),
            (self.cjson_envelopes, CJSONEnvelope, "cjson_envelopes"),
            (self.symmetry_results, SymmetryResult, "symmetry_results"),
            (self.calculations, CalculationRecord, "calculations"),
            (self.datasets, PropertyDataset, "datasets"),
            (self.basis_sets, BasisSet, "basis_sets"),
            (self.orbital_sets, OrbitalSet, "orbital_sets"),
            (self.density_matrices, DensityMatrix, "density_matrices"),
            (self.provenance, ProvenanceRecord, "provenance"),
        )
        for registry, entity_type, name in groups:
            if not isinstance(registry, dict):
                raise TypeError(f"{name} must be a dict")
            if any(
                not isinstance(entity, entity_type) or entity_id != entity.id
                for entity_id, entity in registry.items()
            ):
                raise ValueError(f"{name} keys and entity IDs must match")
        all_ids = self._all_entity_ids()
        self._validate_source_revision_references(
            self.source_revisions.values(),
            set(self.sources),
            all_ids,
        )

    @staticmethod
    def _require_references(references, valid_ids, name):
        if any(reference not in valid_ids for reference in references):
            raise ValueError(f"{name} reference is dangling")

    @staticmethod
    def _validate_source_revision_references(revisions, source_ids, all_ids):
        for revision in revisions:
            if revision.source_id not in source_ids:
                raise ValueError(
                    "source revision has a dangling source reference"
                )
            if any(
                entity_id not in all_ids
                for entity_id in revision.created_entity_ids
            ):
                raise ValueError(
                    "source revision has a dangling created entity reference"
                )
            if revision.diagnostic_ids:
                raise ValueError(
                    "source revision has dangling diagnostic references"
                )
