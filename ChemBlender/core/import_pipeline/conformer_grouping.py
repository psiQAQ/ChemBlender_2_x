"""Explicit, fail-closed SDF conformer grouping suggestions."""

from dataclasses import dataclass
import hashlib
import json
from math import isfinite
from uuid import NAMESPACE_URL, UUID, uuid5

from ..model import (
    ArrayData,
    CategoricalData,
    ConformerSet,
    DatasetStatus,
    ImportBatch,
    MolecularRecord,
    ProvenanceRecord,
    RecordPropertyColumn,
)


_VERSION = "1"
_MAX_SYMMETRY_MATCHES = 4096


class ConformerGroupingCancelled(Exception):
    """Signal cooperative cancellation before any grouping result is returned."""


def _check_cancel(is_cancelled):
    if is_cancelled is None:
        return
    cancelled = is_cancelled()
    if type(cancelled) is not bool:
        raise TypeError("is_cancelled must return a bool")
    if cancelled:
        raise ConformerGroupingCancelled()


def _uuid_tuple(values, name, *, minimum=0):
    if type(values) is not tuple:
        raise TypeError(f"{name} must be a tuple")
    if any(type(value) is not UUID for value in values):
        raise TypeError(f"{name} must contain UUID values")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must contain unique UUID values")
    if len(values) < minimum:
        raise ValueError(f"{name} must contain at least {minimum} values")
    return values


def _stable_id(kind, payload):
    document = json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return uuid5(NAMESPACE_URL, f"chemblender:{kind}:v{_VERSION}:{document}")


def _digest(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ConformerGroupEvidence:
    record_id: UUID
    kind: str
    atom_mapping: tuple[int, ...]
    requires_review: bool = False

    def __post_init__(self):
        if type(self.record_id) is not UUID:
            raise TypeError("record_id must be a UUID")
        if self.kind not in {
            "reference",
            "complete_atom_maps",
            "canonical_ranks_isomorphism",
            "ambiguous_symmetric_isomorphism",
        }:
            raise ValueError("kind is not a supported conformer grouping evidence kind")
        mapping = tuple(self.atom_mapping)
        if (
            not mapping
            or any(type(value) is not int or value < 0 for value in mapping)
            or sorted(mapping) != list(range(len(mapping)))
        ):
            raise ValueError("atom_mapping must be a non-empty integer permutation")
        if type(self.requires_review) is not bool:
            raise TypeError("requires_review must be a bool")
        if self.kind == "ambiguous_symmetric_isomorphism" and not self.requires_review:
            raise ValueError("ambiguous symmetry evidence requires review")
        object.__setattr__(self, "atom_mapping", mapping)


@dataclass(frozen=True, slots=True)
class ConformerGroupSuggestion:
    reference_record_id: UUID
    record_ids: tuple[UUID, ...]
    record_keys: tuple[str, ...]
    record_revisions: tuple[str, ...]
    atom_mappings: tuple[tuple[int, ...], ...]
    evidence: tuple[ConformerGroupEvidence, ...]
    snapshot: str
    id: UUID = None

    def __post_init__(self):
        if type(self.reference_record_id) is not UUID:
            raise TypeError("reference_record_id must be a UUID")
        record_ids = _uuid_tuple(self.record_ids, "record_ids", minimum=2)
        if self.reference_record_id != record_ids[0]:
            raise ValueError("reference_record_id must be the first record")
        record_keys = tuple(self.record_keys)
        revisions = tuple(self.record_revisions)
        if (
            len(record_keys) != len(record_ids)
            or len(revisions) != len(record_ids)
            or any(type(value) is not str or not value for value in record_keys)
            or any(type(value) is not str or not value for value in revisions)
        ):
            raise ValueError("record keys and revisions must match record IDs")
        mappings = tuple(tuple(mapping) for mapping in self.atom_mappings)
        if len(mappings) != len(record_ids) or not mappings:
            raise ValueError("atom_mappings must match record IDs")
        atom_count = len(mappings[0])
        if any(
            not mapping
            or len(mapping) != atom_count
            or any(type(value) is not int or value < 0 for value in mapping)
            or sorted(mapping) != list(range(atom_count))
            for mapping in mappings
        ):
            raise ValueError("atom_mappings must contain matching integer permutations")
        evidence = tuple(self.evidence)
        if (
            len(evidence) != len(record_ids)
            or any(type(item) is not ConformerGroupEvidence for item in evidence)
            or tuple(item.record_id for item in evidence) != record_ids
            or tuple(item.atom_mapping for item in evidence) != mappings
        ):
            raise ValueError("evidence must match record IDs and atom mappings")
        if type(self.snapshot) is not str or len(self.snapshot) != 64:
            raise ValueError("snapshot must be a SHA-256 hex string")
        payload = {
            "atom_mappings": mappings,
            "evidence": tuple(
                {
                    "kind": item.kind,
                    "record_id": str(item.record_id),
                    "requires_review": item.requires_review,
                }
                for item in evidence
            ),
            "record_ids": tuple(map(str, record_ids)),
            "record_keys": record_keys,
            "record_revisions": revisions,
            "snapshot": self.snapshot,
        }
        stable_id = _stable_id("conformer-group-suggestion", payload)
        if self.id is not None and self.id != stable_id:
            raise ValueError("id must match the immutable suggestion contents")
        object.__setattr__(self, "record_ids", record_ids)
        object.__setattr__(self, "record_keys", record_keys)
        object.__setattr__(self, "record_revisions", revisions)
        object.__setattr__(self, "atom_mappings", mappings)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "id", stable_id)

    @property
    def requires_review(self):
        return any(item.requires_review for item in self.evidence)


@dataclass(frozen=True, slots=True)
class ConformerGroupAcceptance:
    suggestion: ConformerGroupSuggestion
    conformer_set: ConformerSet
    property_columns: tuple[RecordPropertyColumn, ...]
    provenance: ProvenanceRecord

    def __post_init__(self):
        if type(self.suggestion) is not ConformerGroupSuggestion:
            raise TypeError("suggestion must be a ConformerGroupSuggestion")
        if type(self.conformer_set) is not ConformerSet:
            raise TypeError("conformer_set must be a ConformerSet")
        columns = tuple(self.property_columns)
        if any(type(column) is not RecordPropertyColumn for column in columns):
            raise TypeError("property_columns must contain RecordPropertyColumn values")
        if type(self.provenance) is not ProvenanceRecord:
            raise TypeError("provenance must be a ProvenanceRecord")
        if self.conformer_set.record_ids != self.suggestion.record_ids:
            raise ValueError("ConformerSet records must match its suggestion")
        if self.conformer_set.provenance_ids != (self.provenance.id,):
            raise ValueError("ConformerSet must carry the grouping provenance")
        object.__setattr__(self, "property_columns", columns)


def _ordered_records(batch):
    if type(batch) is not ImportBatch:
        raise TypeError("batch must be an ImportBatch")
    records = batch.molecular_records
    if len({record.id for record in records}) != len(records):
        raise ValueError("records must have unique IDs")
    structures = {structure.id: structure for structure in batch.structures}
    topologies = {topology.id: topology for topology in batch.topologies}
    ordered = tuple(
        sorted(
            records,
            key=lambda record: (
                str(record.source_revision_id),
                record.source_record_index,
                record.record_key,
                str(record.id),
            ),
        )
    )
    entries = []
    for record in ordered:
        try:
            structure = structures[record.structure_id]
            topology = topologies[record.topology_id]
        except KeyError as error:
            raise ValueError("conformer grouping requires record structure and topology") from error
        if structure.atomic_identity is None:
            raise ValueError("conformer grouping requires atomic identity")
        entries.append((record, structure, topology))
    return tuple(entries)


def _rdkit_molecule(record):
    from rdkit import Chem

    molecule = Chem.MolFromMolBlock(
        record.raw_block.decode("utf-8", errors="replace"),
        sanitize=False,
        removeHs=False,
        strictParsing=True,
    )
    if molecule is None:
        raise ValueError("record raw block no longer parses as an SDF molecule")
    molecule.UpdatePropertyCache(strict=False)
    Chem.AssignStereochemistry(molecule, cleanIt=False, force=True)
    return molecule


def _identity_values(identity, name):
    import numpy

    value = getattr(identity, name)
    if hasattr(value, "codes"):
        codes = numpy.asarray(value.codes.values)
        return tuple(
            None if code == value.missing_code else value.categories[int(code)]
            for code in codes
        )
    return tuple(numpy.asarray(value.values).tolist())


def _complete_unique_atom_maps(structure):
    values = _identity_values(structure.atomic_identity, "atom_map_numbers")
    return bool(values) and all(value > 0 for value in values) and len(values) == len(set(values))


def _exact_model_mapping(reference, candidate, mapping):
    import numpy

    _reference_record, reference_structure, reference_topology = reference
    _candidate_record, candidate_structure, candidate_topology = candidate
    if len(mapping) != len(reference_structure.atomic_numbers) or len(mapping) != len(candidate_structure.atomic_numbers):
        return False
    fields = ("formal_charges", "isotopes", "stereo_labels")
    if any(
        reference_structure.atomic_numbers[index]
        != candidate_structure.atomic_numbers[mapping[index]]
        for index in range(len(mapping))
    ):
        return False
    for name in fields:
        first = _identity_values(reference_structure.atomic_identity, name)
        second = _identity_values(candidate_structure.atomic_identity, name)
        if any(first[index] != second[mapping[index]] for index in range(len(mapping))):
            return False
    reference_edges = {
        (int(left), int(right)): index
        for index, (left, right) in enumerate(numpy.asarray(reference_topology.bond_indices.values))
    }
    candidate_edges = {
        (int(left), int(right)): index
        for index, (left, right) in enumerate(numpy.asarray(candidate_topology.bond_indices.values))
    }
    if len(reference_edges) != len(candidate_edges):
        return False
    reference_orders = numpy.asarray(reference_topology.bond_orders.values)
    candidate_orders = numpy.asarray(candidate_topology.bond_orders.values)
    if reference_topology.aromatic_flags is None or candidate_topology.aromatic_flags is None:
        return False
    reference_aromatic = numpy.asarray(reference_topology.aromatic_flags.values)
    candidate_aromatic = numpy.asarray(candidate_topology.aromatic_flags.values)
    for (left, right), first_index in reference_edges.items():
        edge = tuple(sorted((mapping[left], mapping[right])))
        second_index = candidate_edges.get(edge)
        if second_index is None or (
            float(reference_orders[first_index]) != float(candidate_orders[second_index])
            or bool(reference_aromatic[first_index]) != bool(candidate_aromatic[second_index])
            or reference_topology.stereo_labels[first_index] != candidate_topology.stereo_labels[second_index]
        ):
            return False
    return True


def _pair_mapping(reference, candidate):
    reference_molecule, _reference_record, reference_structure, _reference_topology = reference
    candidate_molecule, _candidate_record, candidate_structure, _candidate_topology = candidate
    if reference_molecule.GetNumAtoms() != candidate_molecule.GetNumAtoms():
        return None
    if _complete_unique_atom_maps(reference_structure) and _complete_unique_atom_maps(candidate_structure):
        candidate_indices = {
            value: index
            for index, value in enumerate(_identity_values(candidate_structure.atomic_identity, "atom_map_numbers"))
        }
        mapping = tuple(
            candidate_indices.get(value, -1)
            for value in _identity_values(reference_structure.atomic_identity, "atom_map_numbers")
        )
        if -1 not in mapping and _exact_model_mapping(reference[1:], candidate[1:], mapping):
            return mapping, "complete_atom_maps", False
        return None

    from rdkit import Chem

    reference_ranks = tuple(
        Chem.CanonicalRankAtoms(
            reference_molecule,
            breakTies=True,
            includeChirality=True,
            includeIsotopes=True,
            includeAtomMaps=False,
        )
    )
    candidate_ranks = tuple(
        Chem.CanonicalRankAtoms(
            candidate_molecule,
            breakTies=True,
            includeChirality=True,
            includeIsotopes=True,
            includeAtomMaps=False,
        )
    )
    if set(reference_ranks) != set(candidate_ranks):
        return None
    by_rank = {rank: index for index, rank in enumerate(candidate_ranks)}
    ranked_mapping = tuple(by_rank[rank] for rank in reference_ranks)
    raw_matches = candidate_molecule.GetSubstructMatches(
        reference_molecule,
        uniquify=False,
        useChirality=True,
        maxMatches=_MAX_SYMMETRY_MATCHES + 1,
    )
    if len(raw_matches) > _MAX_SYMMETRY_MATCHES:
        return None
    matches = tuple(
        sorted(
            {
                tuple(match)
                for match in raw_matches
                if _exact_model_mapping(reference[1:], candidate[1:], tuple(match))
            }
        )
    )
    if not matches:
        return None
    mapping = ranked_mapping if ranked_mapping in matches else matches[0]
    ambiguous = len(matches) > 1
    return (
        mapping,
        "ambiguous_symmetric_isomorphism" if ambiguous else "canonical_ranks_isomorphism",
        ambiguous,
    )


def _array_snapshot(value):
    import numpy

    return numpy.asarray(value.values).tolist()


def _snapshot(batch, members):
    record_ids = {record.id for record, _structure, _topology in members}
    rows = []
    for record, structure, topology in members:
        identity = structure.atomic_identity
        rows.append(
            {
                "record": (str(record.id), record.revision, record.record_key),
                "structure": (
                    str(structure.id), structure.revision, structure.atomic_numbers,
                    _array_snapshot(structure.coordinates),
                    _identity_values(identity, "formal_charges"),
                    _identity_values(identity, "isotopes"),
                    _identity_values(identity, "atom_map_numbers"),
                    _identity_values(identity, "stereo_labels"),
                ),
                "topology": (
                    str(topology.id), topology.revision,
                    _array_snapshot(topology.bond_indices),
                    _array_snapshot(topology.bond_orders),
                    None if topology.aromatic_flags is None else _array_snapshot(topology.aromatic_flags),
                    topology.stereo_labels,
                ),
            }
        )
    columns = []
    for column in batch.datasets:
        if type(column) is not RecordPropertyColumn or not record_ids.intersection(column.record_ids):
            continue
        data = column.data.codes if isinstance(column.data, CategoricalData) else column.data
        columns.append(
            (
                str(column.id), column.revision, tuple(map(str, column.record_ids)),
                _array_snapshot(data),
                None if column.validity_mask is None else _array_snapshot(column.validity_mask),
            )
        )
    return _digest({"columns": tuple(columns), "members": tuple(rows)})


def suggest_conformer_groups(batch, *, is_cancelled=None):
    """Return immutable candidates; this function never creates project data."""
    entries = _ordered_records(batch)
    _check_cancel(is_cancelled)
    molecules = tuple((_rdkit_molecule(record), record, structure, topology) for record, structure, topology in entries)
    suggestions = []
    unmatched = list(molecules)
    while unmatched:
        _check_cancel(is_cancelled)
        reference, reference_record, reference_structure, reference_topology = unmatched.pop(0)
        members = [
            (
                reference_record,
                tuple(range(len(reference_structure.atomic_numbers))),
                "reference",
                False,
            )
        ]
        remaining = []
        for candidate, candidate_record, candidate_structure, candidate_topology in unmatched:
            _check_cancel(is_cancelled)
            if candidate_record.source_revision_id != reference_record.source_revision_id:
                remaining.append((candidate, candidate_record, candidate_structure, candidate_topology))
                continue
            result = _pair_mapping(
                (reference, reference_record, reference_structure, reference_topology),
                (candidate, candidate_record, candidate_structure, candidate_topology),
            )
            if result is None:
                remaining.append((candidate, candidate_record, candidate_structure, candidate_topology))
                continue
            mapping, kind, requires_review = result
            members.append((candidate_record, mapping, kind, requires_review))
        unmatched = remaining
        if len(members) < 2:
            continue
        suggestion_records = tuple(item[0] for item in members)
        member_entries = tuple(
            next(entry for entry in entries if entry[0].id == record.id)
            for record in suggestion_records
        )
        mappings = tuple(item[1] for item in members)
        evidence = tuple(
            ConformerGroupEvidence(record.id, kind, mapping, requires_review)
            for record, mapping, kind, requires_review in members
        )
        suggestions.append(
            ConformerGroupSuggestion(
                reference_record_id=reference_record.id,
                record_ids=tuple(record.id for record in suggestion_records),
                record_keys=tuple(record.record_key for record in suggestion_records),
                record_revisions=tuple(record.revision for record in suggestion_records),
                atom_mappings=mappings,
                evidence=evidence,
                snapshot=_snapshot(batch, member_entries),
            )
        )
    _check_cancel(is_cancelled)
    return tuple(sorted(suggestions, key=lambda suggestion: str(suggestion.id)))


def _coordinates(structure, mapping):
    import numpy

    coordinates = numpy.asarray(structure.coordinates.values, dtype=numpy.float64)
    if not numpy.all(numpy.isfinite(coordinates)):
        raise ValueError("structure has non-finite coordinates")
    return coordinates[list(mapping)]


def _reordered_column(column, row_indices, record_ids, provenance_id, suggestion_id):
    import numpy

    data = column.data
    if isinstance(data, CategoricalData):
        reordered_data = CategoricalData(
            ArrayData(
                numpy.asarray(data.codes.values)[list(row_indices)].copy(),
                data.codes.dims,
                data.codes.unit,
            ),
            data.categories,
            data.missing_code,
        )
    else:
        reordered_data = ArrayData(
            numpy.asarray(data.values)[list(row_indices)].copy(),
            data.dims,
            data.unit,
        )
    mask = (
        None
        if column.validity_mask is None
        else ArrayData(
            numpy.asarray(column.validity_mask.values)[list(row_indices)].copy(),
            column.validity_mask.dims,
            column.validity_mask.unit,
        )
    )
    revision = _digest(
        {
            "column_id": str(column.id),
            "column_revision": column.revision,
            "record_ids": tuple(map(str, record_ids)),
            "suggestion_id": str(suggestion_id),
        }
    )
    return RecordPropertyColumn(
        id=uuid5(suggestion_id, f"conformer-property-column:{column.id}"),
        revision=revision,
        semantic_role=column.semantic_role,
        domain="record",
        data=reordered_data,
        status=column.status,
        source_calculation=column.source_calculation,
        provenance_ids=tuple(dict.fromkeys((*column.provenance_ids, provenance_id))),
        record_ids=record_ids,
        validity_mask=mask,
    )


def accept_conformer_group(
    suggestion,
    batch,
    *,
    review_confirmed=False,
    is_cancelled=None,
):
    """Convert one current suggestion after explicit user confirmation."""
    if type(suggestion) is not ConformerGroupSuggestion:
        raise TypeError("suggestion must be a ConformerGroupSuggestion")
    if type(review_confirmed) is not bool:
        raise TypeError("review_confirmed must be a bool")
    if suggestion.requires_review and not review_confirmed:
        raise ValueError("ambiguous conformer grouping requires explicit review confirmation")
    entries = _ordered_records(batch)
    _check_cancel(is_cancelled)
    live = {item.id: item for item in suggest_conformer_groups(batch, is_cancelled=is_cancelled)}
    if live.get(suggestion.id) != suggestion:
        raise ValueError("conformer grouping suggestion is stale; refresh before accepting")
    by_id = {record.id: (record, structure, topology) for record, structure, topology in entries}
    selected = tuple(by_id[record_id] for record_id in suggestion.record_ids)
    parent_ids = tuple(
        dict.fromkeys(
            parent_id for record, _structure, _topology in selected for parent_id in record.provenance_ids
        )
    )
    evidence_kinds = tuple(
        sorted({item.kind for item in suggestion.evidence if item.kind != "reference"})
    )
    payload = {
        "atom_mappings": suggestion.atom_mappings,
        "evidence": evidence_kinds,
        "record_ids": tuple(map(str, suggestion.record_ids)),
        "suggestion_id": str(suggestion.id),
    }
    revision = _digest(payload)
    provenance = ProvenanceRecord(
        id=uuid5(suggestion.id, "conformer-grouping-provenance"),
        revision=revision,
        producer="ChemBlender SDF conformer grouping",
        producer_version=_VERSION,
        source="",
        source_hash=revision,
        parent_ids=parent_ids,
        operation="group_conformers",
        parameters=(
            ("suggestion_id", str(suggestion.id)),
            ("evidence", ",".join(evidence_kinds)),
            ("review_confirmed", review_confirmed),
        ),
    )
    _check_cancel(is_cancelled)
    import numpy

    coordinates = numpy.asarray(
        [
            _coordinates(structure, mapping)
            for (_record, structure, _topology), mapping in zip(selected, suggestion.atom_mappings, strict=True)
        ],
        dtype=numpy.float64,
    )
    if not all(isfinite(float(value)) for value in coordinates.flat):
        raise ValueError("conformer coordinates must be finite")
    columns = tuple(column for column in batch.datasets if type(column) is RecordPropertyColumn)
    reordered_columns = []
    selected_ids = set(suggestion.record_ids)
    for column in columns:
        _check_cancel(is_cancelled)
        overlap = selected_ids.intersection(column.record_ids)
        if not overlap:
            continue
        if overlap != selected_ids:
            raise ValueError("record property column does not cover the complete conformer group")
        positions = {record_id: index for index, record_id in enumerate(column.record_ids)}
        reordered_columns.append(
            _reordered_column(
                column,
                tuple(positions[record_id] for record_id in suggestion.record_ids),
                suggestion.record_ids,
                provenance.id,
                suggestion.id,
            )
        )
    _check_cancel(is_cancelled)
    conformer_set = ConformerSet(
        id=uuid5(suggestion.id, "conformer-set"),
        revision=revision,
        semantic_role="coordinates",
        domain="conformer",
        data=ArrayData(coordinates, ("conformer", "atom", "xyz"), "angstrom"),
        status=(DatasetStatus.AMBIGUOUS if suggestion.requires_review else DatasetStatus.COMPLETE),
        source_calculation=None,
        provenance_ids=(provenance.id,),
        reference_structure_id=selected[0][0].structure_id,
        reference_topology_id=selected[0][0].topology_id,
        record_ids=suggestion.record_ids,
        record_keys=suggestion.record_keys,
        atom_mappings=ArrayData(
            numpy.asarray(suggestion.atom_mappings, dtype=numpy.int64),
            ("conformer", "atom"),
            "dimensionless",
        ),
    )
    return ConformerGroupAcceptance(
        suggestion,
        conformer_set,
        tuple(reordered_columns),
        provenance,
    )


__all__ = [
    "ConformerGroupAcceptance",
    "ConformerGroupEvidence",
    "ConformerGroupSuggestion",
    "ConformerGroupingCancelled",
    "accept_conformer_group",
    "suggest_conformer_groups",
]
