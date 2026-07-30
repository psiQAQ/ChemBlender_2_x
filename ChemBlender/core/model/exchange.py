from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from .arrays import ArrayData
from .categorical import CategoricalData
from .common import _require_token, _require_uuid, _require_uuid_tuple


def _require_exchange_text(value, name):
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not value:
        raise ValueError(f"{name} must be non-empty")


def _require_exchange_token(value, name):
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    _require_token(value, name)


@dataclass(frozen=True, slots=True)
class ChemicalAnnotation:
    id: UUID
    revision: str
    target_entity_id: UUID
    namespace: str
    key: str
    value: str | int | float | bool
    source: str
    confidence: float | None
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_exchange_text(self.revision, "revision")
        _require_uuid(self.target_entity_id, "target_entity_id")
        _require_exchange_token(self.namespace, "namespace")
        _require_exchange_token(self.key, "key")
        if type(self.value) not in (str, int, float, bool):
            raise TypeError("value must be an immutable scalar")
        if isinstance(self.value, str) and not self.value:
            raise ValueError("string value must be non-empty")
        if isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("float value must be finite")
        _require_exchange_text(self.source, "source")
        if self.confidence is not None:
            if type(self.confidence) is not float:
                raise TypeError("confidence must be a float or None")
            if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
                raise ValueError("confidence must be from 0 to 1")
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class ExternalReference:
    id: UUID
    revision: str
    target_entity_id: UUID
    namespace: str
    identifier: str
    source: str
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_exchange_text(self.revision, "revision")
        _require_uuid(self.target_entity_id, "target_entity_id")
        _require_exchange_token(self.namespace, "namespace")
        _require_exchange_text(self.identifier, "identifier")
        _require_exchange_text(self.source, "source")
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class BiologicalModel:
    number: int | None

    def __post_init__(self):
        if self.number is not None:
            if type(self.number) is not int:
                raise TypeError("model number must be an integer or None")
            if self.number <= 0:
                raise ValueError("model number must be positive")


@dataclass(frozen=True, slots=True)
class BiologicalChain:
    chain_id: str
    segment_index: int

    def __post_init__(self):
        if type(self.chain_id) is not str:
            raise TypeError("chain_id must be a string")
        if type(self.segment_index) is not int:
            raise TypeError("segment_index must be an integer")
        if self.segment_index < 0:
            raise ValueError("segment_index must be non-negative")


@dataclass(frozen=True, slots=True)
class BiologicalResidue:
    chain_index: int
    residue_name: str
    sequence_number: int
    insertion_code: str
    hetero: bool

    def __post_init__(self):
        if type(self.chain_index) is not int:
            raise TypeError("chain_index must be an integer")
        if self.chain_index < 0:
            raise ValueError("chain_index must be non-negative")
        _require_exchange_text(self.residue_name, "residue_name")
        if type(self.sequence_number) is not int:
            raise TypeError("sequence_number must be an integer")
        if type(self.insertion_code) is not str:
            raise TypeError("insertion_code must be a string")
        if type(self.hetero) is not bool:
            raise TypeError("hetero must be a bool")


@dataclass(frozen=True, slots=True)
class BiologicalAtomSiteData:
    serial_numbers: ArrayData
    residue_indices: ArrayData
    alternate_locations: CategoricalData
    record_kinds: CategoricalData

    def __post_init__(self):
        import numpy

        arrays = (self.serial_numbers, self.residue_indices)
        if any(not isinstance(value, ArrayData) for value in arrays):
            raise TypeError("atom-site numeric columns must be ArrayData")
        if any(
            value.dims != ("atom",)
            or value.unit != "dimensionless"
            or numpy.dtype(value.dtype).kind not in "iu"
            for value in arrays
        ):
            raise ValueError(
                "atom-site numeric columns must be dimensionless integer atom arrays"
            )
        if any(
            not isinstance(value, CategoricalData)
            for value in (self.alternate_locations, self.record_kinds)
        ):
            raise TypeError("atom-site categorical columns must be CategoricalData")
        atom_count = self.serial_numbers.shape[0]
        if (
            self.residue_indices.shape != (atom_count,)
            or self.alternate_locations.dims != ("atom",)
            or self.alternate_locations.shape != (atom_count,)
            or self.record_kinds.dims != ("atom",)
            or self.record_kinds.shape != (atom_count,)
        ):
            raise ValueError("atom-site columns must have matching atom dimensions")
        serials = numpy.asarray(self.serial_numbers.values)
        residue_indices = numpy.asarray(self.residue_indices.values)
        if numpy.any(serials <= 0):
            raise ValueError("serial numbers must be positive")
        if numpy.any(residue_indices < 0):
            raise ValueError("residue indices must be non-negative")
        if any(not value for value in self.alternate_locations.categories):
            raise ValueError("alternate-location categories must be non-empty")
        if any(
            value not in {"atom", "hetatm"}
            for value in self.record_kinds.categories
        ):
            raise ValueError("record kinds must be atom or hetatm")
        record_kinds = numpy.asarray(self.record_kinds.codes.values)
        if numpy.any(record_kinds == self.record_kinds.missing_code):
            raise ValueError("record kind is required for every atom site")

    @property
    def atom_count(self):
        return self.serial_numbers.shape[0]


@dataclass(frozen=True, slots=True)
class BiologicalHierarchy:
    id: UUID
    revision: str
    structure_id: UUID
    model: BiologicalModel
    chains: tuple[BiologicalChain, ...]
    residues: tuple[BiologicalResidue, ...]
    atom_sites: BiologicalAtomSiteData
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        import numpy

        _require_uuid(self.id, "id")
        _require_exchange_text(self.revision, "revision")
        _require_uuid(self.structure_id, "structure_id")
        if not isinstance(self.model, BiologicalModel):
            raise TypeError("model must be BiologicalModel")
        chains = tuple(self.chains)
        residues = tuple(self.residues)
        if any(not isinstance(value, BiologicalChain) for value in chains):
            raise TypeError("chains must contain BiologicalChain values")
        if any(not isinstance(value, BiologicalResidue) for value in residues):
            raise TypeError("residues must contain BiologicalResidue values")
        chain_keys = tuple((value.chain_id, value.segment_index) for value in chains)
        if len(chain_keys) != len(set(chain_keys)):
            raise ValueError("chain keys must be unique")
        if any(value.chain_index >= len(chains) for value in residues):
            raise ValueError("residue chain index is outside chains")
        residue_keys = tuple(
            (
                value.chain_index,
                value.sequence_number,
                value.insertion_code,
                value.hetero,
            )
            for value in residues
        )
        if len(residue_keys) != len(set(residue_keys)):
            raise ValueError("residue keys must be unique")
        if not isinstance(self.atom_sites, BiologicalAtomSiteData):
            raise TypeError("atom_sites must be BiologicalAtomSiteData")
        residue_indices = numpy.asarray(self.atom_sites.residue_indices.values)
        if residue_indices.size and int(residue_indices.max()) >= len(residues):
            raise ValueError("atom-site residue index is outside residues")
        object.__setattr__(self, "chains", chains)
        object.__setattr__(self, "residues", residues)
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )

    @property
    def atom_count(self):
        return self.atom_sites.atom_count
