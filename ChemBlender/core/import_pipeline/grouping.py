import json
import math
import ntpath
from collections import Counter
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import PureWindowsPath
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy

from ..model import CalculationGroup, ImportBatch, QCProject
from .conflicts import _staged_revisions
from .preview import ImportPreview
from .staging import StagedImportSession


_KIND_CONTRACT = {
    "explicit_internal_reference": (5, "high"),
    "exact_mapped_structure": (4, "high"),
    "kabsch_rmsd": (3, "medium"),
    "periodic_equivalence_conflict": (3, "review"),
    "metadata": (2, "low"),
    "filename_directory": (1, "low"),
}
_ENTITY_GROUPS = (
    "structures",
    "cif_envelopes",
    "qcschema_envelopes",
    "cjson_envelopes",
    "symmetry_results",
    "calculations",
    "datasets",
    "basis_sets",
    "orbital_sets",
    "density_matrices",
    "provenance",
)
_LENGTH_TO_ANGSTROM = {"angstrom": 1.0, "bohr": 0.529177210903}
_EXACT_TOLERANCE = 1e-8
_KABSCH_TOLERANCE_ANGSTROM = 0.15
_MAX_MAPPINGS = 4096


def _evidence_graph_connected(source_revision_ids, evidence):
    adjacency = {revision_id: set() for revision_id in source_revision_ids}
    for item in evidence:
        left, right = item.source_revision_ids
        adjacency[left].add(right)
        adjacency[right].add(left)
    seen = set()
    stack = [source_revision_ids[0]]
    while stack:
        revision_id = stack.pop()
        if revision_id in seen:
            continue
        seen.add(revision_id)
        stack.extend(adjacency[revision_id] - seen)
    return seen == set(source_revision_ids)


def _maximum_bottleneck_rank(source_revision_ids, evidence):
    parents = {revision_id: revision_id for revision_id in source_revision_ids}

    def root(revision_id):
        while parents[revision_id] != revision_id:
            parents[revision_id] = parents[parents[revision_id]]
            revision_id = parents[revision_id]
        return revision_id

    components = len(parents)
    for item in sorted(evidence, key=lambda value: -value.rank):
        left, right = map(root, item.source_revision_ids)
        if left == right:
            continue
        parents[right] = left
        components -= 1
        if components == 1:
            return item.rank
    raise ValueError("evidence does not connect all suggested sources")


def _uuid_tuple(values, name, *, minimum=0):
    if type(values) is not tuple:
        raise TypeError(f"{name} must be a tuple")
    if any(type(value) is not UUID for value in values):
        raise TypeError(f"{name} must contain UUID values")
    values = tuple(sorted(values, key=str))
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must contain unique UUID values")
    if len(values) < minimum:
        raise ValueError(f"{name} must contain at least {minimum} values")
    return values


@dataclass(frozen=True, slots=True)
class GroupingEvidence:
    kind: str
    source_revision_ids: tuple[UUID, ...]
    summary: str
    entity_ids: tuple[UUID, ...] = ()
    metric: float | None = None
    metric_unit: str | None = None
    id: UUID = field(init=False)

    def __post_init__(self):
        if self.kind not in _KIND_CONTRACT:
            raise ValueError("kind is not a supported grouping evidence kind")
        object.__setattr__(
            self,
            "source_revision_ids",
            _uuid_tuple(
                self.source_revision_ids,
                "source_revision_ids",
                minimum=2,
            ),
        )
        if len(self.source_revision_ids) != 2:
            raise ValueError("evidence must compare exactly two source revisions")
        object.__setattr__(
            self,
            "entity_ids",
            _uuid_tuple(self.entity_ids, "entity_ids"),
        )
        if type(self.summary) is not str or not self.summary:
            raise ValueError("summary must be a non-empty string")
        if self.metric is not None and (
            isinstance(self.metric, bool)
            or not isinstance(self.metric, (int, float))
            or not math.isfinite(self.metric)
            or self.metric < 0
        ):
            raise ValueError("metric must be a finite non-negative number or None")
        if (self.metric is None) != (self.metric_unit is None):
            raise ValueError("metric and metric_unit must be provided together")
        if self.metric_unit is not None and (
            type(self.metric_unit) is not str or not self.metric_unit
        ):
            raise ValueError("metric_unit must be a non-empty string or None")
        metric = None if self.metric is None else round(float(self.metric), 12)
        object.__setattr__(self, "metric", metric)
        object.__setattr__(
            self,
            "id",
            _stable_id(
                "grouping-evidence",
                {
                    "entity_ids": tuple(map(str, self.entity_ids)),
                    "kind": self.kind,
                    "metric": metric,
                    "metric_unit": self.metric_unit,
                    "source_revision_ids": tuple(
                        map(str, self.source_revision_ids)
                    ),
                    "summary": self.summary,
                },
            ),
        )

    @property
    def rank(self):
        return _KIND_CONTRACT[self.kind][0]

    @property
    def confidence(self):
        return _KIND_CONTRACT[self.kind][1]

    @property
    def is_conflict(self):
        return self.kind == "periodic_equivalence_conflict"

    @property
    def requires_review(self):
        return self.is_conflict


@dataclass(frozen=True, slots=True)
class SourceGroupSuggestion:
    source_revision_ids: tuple[UUID, ...]
    evidence: tuple[GroupingEvidence, ...]
    id: UUID = field(init=False)

    def __post_init__(self):
        object.__setattr__(
            self,
            "source_revision_ids",
            _uuid_tuple(
                self.source_revision_ids,
                "source_revision_ids",
                minimum=2,
            ),
        )
        if type(self.evidence) is not tuple or any(
            type(item) is not GroupingEvidence for item in self.evidence
        ):
            raise TypeError("evidence must contain GroupingEvidence values")
        if not self.evidence:
            raise ValueError("evidence must not be empty")
        if any(
            not set(item.source_revision_ids).issubset(
                self.source_revision_ids
            )
            for item in self.evidence
        ):
            raise ValueError("evidence references a source outside the suggestion")
        evidence = tuple(
            sorted(
                self.evidence,
                key=lambda item: (-item.rank, item.kind, str(item.id)),
            )
        )
        if len({item.id for item in evidence}) != len(evidence):
            raise ValueError("evidence ids must be unique")
        if not _evidence_graph_connected(self.source_revision_ids, evidence):
            raise ValueError("evidence must connect all suggested sources")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(
            self,
            "id",
            _stable_id(
                "source-group-suggestion",
                {
                    "evidence": tuple(
                        {
                            "entity_ids": tuple(map(str, item.entity_ids)),
                            "id": str(item.id),
                            "kind": item.kind,
                            "metric": item.metric,
                            "metric_unit": item.metric_unit,
                            "source_revision_ids": tuple(
                                map(str, item.source_revision_ids)
                            ),
                            "summary": item.summary,
                        }
                        for item in evidence
                    ),
                    "source_revision_ids": tuple(
                        map(str, self.source_revision_ids)
                    ),
                },
            ),
        )

    @property
    def evidence_ids(self):
        return tuple(item.id for item in self.evidence)

    @property
    def confidence(self):
        if self.requires_review:
            return "review"
        rank = _maximum_bottleneck_rank(
            self.source_revision_ids,
            self.evidence,
        )
        return "high" if rank >= 4 else "medium" if rank == 3 else "low"

    @property
    def requires_review(self):
        return any(item.requires_review for item in self.evidence)

    def confirm(self, evidence_ids):
        evidence_ids = _uuid_tuple(
            evidence_ids, "evidence_ids", minimum=1
        )
        if not set(evidence_ids).issubset(self.evidence_ids):
            raise ValueError("selected evidence does not belong to suggestion")
        selected = tuple(
            item for item in self.evidence if item.id in evidence_ids
        )
        if not _evidence_graph_connected(self.source_revision_ids, selected):
            raise ValueError("selected evidence must connect all suggested sources")
        return CalculationGroup(
            suggestion_id=self.id,
            source_revision_ids=self.source_revision_ids,
            evidence_ids=evidence_ids,
        )


def _stable_id(kind, payload):
    document = json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return uuid5(NAMESPACE_URL, f"chemblender:{kind}:v1:{document}")


def _evidence(kind, revision_ids, entity_ids, summary, *, metric=None, unit=None):
    revision_ids = tuple(sorted(revision_ids, key=str))
    entity_ids = tuple(sorted(set(entity_ids), key=str))
    metric = None if metric is None else round(float(metric), 12)
    return GroupingEvidence(
        kind=kind,
        source_revision_ids=revision_ids,
        entity_ids=entity_ids,
        metric=metric,
        metric_unit=unit,
        summary=summary,
    )


def _batch_entity_ids(batch):
    return tuple(
        entity.id
        for name in _ENTITY_GROUPS
        for entity in getattr(batch, name)
    )


def _validate_staged_entities(entries):
    merged = ImportBatch(
        **{
            name: tuple(
                entity
                for _, _, batch in entries
                for entity in getattr(batch, name)
            )
            for name in (
                "sources",
                "source_revisions",
                *_ENTITY_GROUPS,
                "diagnostics",
            )
        }
    )
    project = QCProject(
        id=uuid5(NAMESPACE_URL, "chemblender:grouping-validation-project:v1"),
        schema_version="0.2",
    )
    project.commit(merged)


def _staged_entries(preview, session):
    entries = []
    revisions = _staged_revisions(preview, session)
    for source_preview, revision in revisions:
        batch = session.result(source_preview.staged_batch_ids[0])
        if type(batch) is not ImportBatch:
            raise ValueError("staged result must be an ImportBatch")
        entity_ids = _batch_entity_ids(batch)
        if (
            len(revision.created_entity_ids)
            != len(set(revision.created_entity_ids))
            or len(entity_ids) != len(set(entity_ids))
            or set(revision.created_entity_ids) != set(entity_ids)
        ):
            raise ValueError(
                "source revision created entities do not match staged batch"
            )
        entries.append((source_preview, revision, batch))
    if len({entry[1].id for entry in entries}) != len(entries):
        raise ValueError("staged source revision ids must be unique")
    return tuple(sorted(entries, key=lambda item: str(item[1].id)))


def _coordinates_angstrom(structure):
    scale = _LENGTH_TO_ANGSTROM.get(structure.coordinates.unit)
    if scale is None:
        return None
    return numpy.asarray(structure.coordinates.values, dtype=float) * scale


def _cell_angstrom(structure):
    if structure.cell is None:
        return None
    scale = _LENGTH_TO_ANGSTROM.get(structure.cell.unit)
    if scale is None:
        return None
    return numpy.asarray(structure.cell.values, dtype=float) * scale


def _composition(structure):
    return tuple(sorted(Counter(structure.atomic_numbers).items()))


def _topology_labels(structure):
    labels = [[] for _ in structure.atomic_numbers]
    if structure.topology is None:
        return None
    indices = numpy.asarray(structure.topology.bond_indices.values, dtype=int)
    orders = numpy.asarray(structure.topology.bond_orders.values, dtype=float)
    for (left, right), order in zip(indices, orders, strict=True):
        labels[left].append(
            (structure.atomic_numbers[right], round(float(order), 8))
        )
        labels[right].append(
            (structure.atomic_numbers[left], round(float(order), 8))
        )
    return tuple(tuple(sorted(neighbors)) for neighbors in labels)


def _candidate_labels(first, second):
    first_topology = _topology_labels(first)
    second_topology = _topology_labels(second)
    use_topology = first_topology is not None and second_topology is not None
    first_labels = tuple(
        (
            atomic_number,
            first_topology[index] if use_topology else (),
        )
        for index, atomic_number in enumerate(first.atomic_numbers)
    )
    second_labels = tuple(
        (
            atomic_number,
            second_topology[index] if use_topology else (),
        )
        for index, atomic_number in enumerate(second.atomic_numbers)
    )
    return first_labels, second_labels


def _centered_distance_signature(structure, coordinates):
    centered = coordinates - coordinates.mean(axis=0)
    return tuple(
        sorted(
            (
                atomic_number,
                round(float(numpy.linalg.norm(centered[index])), 8),
            )
            for index, atomic_number in enumerate(structure.atomic_numbers)
        )
    )


def _mapped_topology_equal(first, second, mapping):
    if first.topology is None or second.topology is None:
        return first.topology is second.topology

    def edges(structure, atom_mapping):
        indices = numpy.asarray(
            structure.topology.bond_indices.values,
            dtype=int,
        )
        orders = numpy.asarray(
            structure.topology.bond_orders.values,
            dtype=float,
        )
        return tuple(
            sorted(
                (
                    *sorted(
                        (
                            atom_mapping[int(left)],
                            atom_mapping[int(right)],
                        )
                    ),
                    round(float(order), 8),
                )
                for (left, right), order in zip(indices, orders, strict=True)
            )
        )

    return edges(first, mapping) == edges(
        second,
        tuple(range(len(second.atomic_numbers))),
    )


def _atom_mappings(first, second, first_coordinates, second_coordinates, tolerance):
    first_labels, second_labels = _candidate_labels(first, second)
    candidates = tuple(
        tuple(
            index
            for index, second_label in enumerate(second_labels)
            if second_label == first_label
        )
        for first_label in first_labels
    )
    if any(not values for values in candidates):
        return
    first_distances = numpy.linalg.norm(
        first_coordinates[:, None, :] - first_coordinates[None, :, :],
        axis=2,
    )
    second_distances = numpy.linalg.norm(
        second_coordinates[:, None, :] - second_coordinates[None, :, :],
        axis=2,
    )
    order = tuple(
        sorted(
            range(len(candidates)),
            key=lambda index: (len(candidates[index]), index),
        )
    )
    mapping = [-1] * len(candidates)
    used = set()
    produced = [0]

    def visit(depth):
        if produced[0] >= _MAX_MAPPINGS:
            return
        if depth == len(order):
            produced[0] += 1
            yield tuple(mapping)
            return
        first_index = order[depth]
        for second_index in candidates[first_index]:
            if second_index in used:
                continue
            if any(
                not _within_numeric_tolerance(
                    abs(
                        first_distances[first_index, assigned_first]
                        - second_distances[second_index, assigned_second]
                    ),
                    tolerance,
                )
                for assigned_first, assigned_second in enumerate(mapping)
                if assigned_second >= 0
            ):
                continue
            mapping[first_index] = second_index
            used.add(second_index)
            yield from visit(depth + 1)
            used.remove(second_index)
            mapping[first_index] = -1

    # ponytail: bounded fail-closed search; add a graph matcher only if large
    # symmetric structures measurably need cross-source grouping.
    yield from visit(0)


def _kabsch_rmsd(first, second):
    first = first - first.mean(axis=0)
    second = second - second.mean(axis=0)
    left, _, right = numpy.linalg.svd(first.T @ second)
    if numpy.linalg.det(left @ right) < 0:
        left[:, -1] *= -1
    rotation = left @ right
    delta = first @ rotation - second
    return float(numpy.sqrt(numpy.mean(numpy.sum(delta * delta, axis=1))))


def _is_kabsch_match(rmsd):
    return _within_numeric_tolerance(rmsd, _KABSCH_TOLERANCE_ANGSTROM)


def _within_numeric_tolerance(value, tolerance):
    return value <= tolerance + math.ulp(tolerance)


def _molecular_evidence(first, second, revision_ids):
    if (
        not first.atomic_numbers
        or not second.atomic_numbers
        or _composition(first) != _composition(second)
    ):
        return None
    if (first.topology is None) != (second.topology is None):
        return None
    first_coordinates = _coordinates_angstrom(first)
    second_coordinates = _coordinates_angstrom(second)
    if first_coordinates is None or second_coordinates is None:
        return None
    if _centered_distance_signature(
        first, first_coordinates
    ) == _centered_distance_signature(second, second_coordinates):
        for mapping in _atom_mappings(
            first,
            second,
            first_coordinates,
            second_coordinates,
            _EXACT_TOLERANCE,
        ):
            if not _mapped_topology_equal(first, second, mapping):
                continue
            centered_first = first_coordinates - first_coordinates.mean(axis=0)
            mapped_second = second_coordinates[list(mapping)]
            centered_second = mapped_second - mapped_second.mean(axis=0)
            if numpy.allclose(
                centered_first,
                centered_second,
                atol=_EXACT_TOLERANCE,
                rtol=0,
            ):
                return _evidence(
                    "exact_mapped_structure",
                    revision_ids,
                    (first.id, second.id),
                    "atomic-number and topology mapping gives identical centered coordinates",
                )

    best_rmsd = None
    for mapping in _atom_mappings(
        first,
        second,
        first_coordinates,
        second_coordinates,
        _KABSCH_TOLERANCE_ANGSTROM * 2,
    ):
        if not _mapped_topology_equal(first, second, mapping):
            continue
        rmsd = _kabsch_rmsd(
            first_coordinates,
            second_coordinates[list(mapping)],
        )
        best_rmsd = rmsd if best_rmsd is None else min(best_rmsd, rmsd)
    if best_rmsd is not None and _is_kabsch_match(best_rmsd):
        return _evidence(
            "kabsch_rmsd",
            revision_ids,
            (first.id, second.id),
            "atomic-number and topology mapping has a low Kabsch RMSD",
            metric=best_rmsd,
            unit="angstrom",
        )
    return None


def _periodic_coordinates_match(first, second):
    first_fractional = numpy.asarray(
        first.periodic.fractional_coordinates.values,
        dtype=float,
    )
    second_fractional = numpy.asarray(
        second.periodic.fractional_coordinates.values,
        dtype=float,
    )
    first_labels = first.atomic_numbers
    second_labels = second.atomic_numbers
    candidates = tuple(
        tuple(
            index
            for index, atomic_number in enumerate(second_labels)
            if atomic_number == first_atomic_number
        )
        for first_atomic_number in first_labels
    )
    order = tuple(
        sorted(
            range(len(candidates)),
            key=lambda index: (len(candidates[index]), index),
        )
    )

    def matches_shift(shift):
        used = set()

        def visit(depth):
            if depth == len(order):
                return True
            first_index = order[depth]
            for second_index in candidates[first_index]:
                if second_index in used:
                    continue
                delta = (
                    first_fractional[first_index]
                    - second_fractional[second_index]
                    - shift
                )
                for axis, periodic in enumerate(first.periodic.pbc):
                    if periodic:
                        delta[axis] -= numpy.rint(delta[axis])
                if numpy.allclose(
                    delta,
                    0,
                    atol=_EXACT_TOLERANCE,
                    rtol=0,
                ):
                    used.add(second_index)
                    if visit(depth + 1):
                        return True
                    used.remove(second_index)
            return False

        return visit(0)

    first_anchor = order[0]
    for second_anchor in candidates[first_anchor]:
        shift = first_fractional[first_anchor] - second_fractional[second_anchor]
        if any(
            not periodic and abs(float(shift[axis])) > _EXACT_TOLERANCE
            for axis, periodic in enumerate(first.periodic.pbc)
        ):
            continue
        shift = numpy.asarray(
            tuple(
                shift[axis] if periodic else 0.0
                for axis, periodic in enumerate(first.periodic.pbc)
            )
        )
        if matches_shift(shift):
            return True
    return False


def _reduced_composition(structure):
    counts = Counter(structure.atomic_numbers)
    divisor = math.gcd(*counts.values())
    return tuple(
        sorted(
            (atomic_number, value // divisor)
            for atomic_number, value in counts.items()
        )
    )


def _periodic_evidence(first, second, revision_ids):
    if not first.atomic_numbers or not second.atomic_numbers:
        return None
    first_cell = _cell_angstrom(first)
    second_cell = _cell_angstrom(second)
    if first_cell is None or second_cell is None:
        return None
    if first.periodic.pbc != second.periodic.pbc:
        return None
    first_metric = first_cell @ first_cell.T
    second_metric = second_cell @ second_cell.T
    if (
        _composition(first) == _composition(second)
        and numpy.allclose(
            first_metric,
            second_metric,
            atol=_EXACT_TOLERANCE,
            rtol=0,
        )
        and _periodic_coordinates_match(first, second)
    ):
        return _evidence(
            "exact_mapped_structure",
            revision_ids,
            (first.id, second.id),
            "cell metric, composition and fractional coordinates modulo periodicity match",
        )

    first_volume = abs(float(numpy.linalg.det(first_cell)))
    second_volume = abs(float(numpy.linalg.det(second_cell)))
    atom_ratio = len(second.atomic_numbers) / len(first.atomic_numbers)
    volume_ratio = second_volume / first_volume if first_volume else 0.0
    if (
        all(first.periodic.pbc)
        and _reduced_composition(first) == _reduced_composition(second)
        and not math.isclose(atom_ratio, 1.0, abs_tol=_EXACT_TOLERANCE)
        and math.isclose(
            volume_ratio,
            atom_ratio,
            rel_tol=1e-6,
            abs_tol=_EXACT_TOLERANCE,
        )
    ):
        return _evidence(
            "periodic_equivalence_conflict",
            revision_ids,
            (first.id, second.id),
            "cell volume and reduced composition suggest "
            "primitive/conventional equivalence; symmetry review is required",
            metric=max(volume_ratio, 1 / volume_ratio),
            unit="cell_volume_ratio",
        )
    return None


def _structure_evidence(first_entry, second_entry):
    first_revision, first_batch = first_entry[1], first_entry[2]
    second_revision, second_batch = second_entry[1], second_entry[2]
    revision_ids = (first_revision.id, second_revision.id)
    evidence = []
    for first in first_batch.structures:
        for second in second_batch.structures:
            first_periodic = first.periodic is not None
            second_periodic = second.periodic is not None
            if first_periodic != second_periodic:
                continue
            item = (
                _periodic_evidence(first, second, revision_ids)
                if first_periodic
                else _molecular_evidence(first, second, revision_ids)
            )
            if item is not None:
                evidence.append(item)
    return tuple(evidence)


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


def _explicit_evidence(entries):
    owners = {}
    for _, revision, _ in entries:
        for entity_id in revision.created_entity_ids:
            if entity_id in owners:
                raise ValueError(
                    "created entity belongs to more than one source revision"
                )
            owners[entity_id] = revision.id
    by_pair = {}
    for _, revision, batch in entries:
        for name in _ENTITY_GROUPS:
            for entity in getattr(batch, name):
                for reference_id in _semantic_uuid_references(entity):
                    target_revision_id = owners.get(reference_id)
                    if (
                        target_revision_id is None
                        or target_revision_id == revision.id
                    ):
                        continue
                    pair = tuple(
                        sorted((revision.id, target_revision_id), key=str)
                    )
                    by_pair.setdefault(pair, set()).update(
                        (entity.id, reference_id)
                    )
    return {
        pair: (
            _evidence(
                "explicit_internal_reference",
                pair,
                entity_ids,
                "a staged entity directly references another entity "
                "created by another source revision",
            ),
        )
        for pair, entity_ids in by_pair.items()
    }


def _metadata_key(metadata):
    return (
        metadata.driver,
        metadata.method,
        metadata.basis,
        metadata.molecular_charge,
        metadata.molecular_multiplicity,
        metadata.program,
        metadata.program_version,
    )


def _metadata_evidence(first_entry, second_entry):
    first_revision, first_batch = first_entry[1], first_entry[2]
    second_revision, second_batch = second_entry[1], second_entry[2]
    for first in first_batch.calculations:
        if first.metadata is None:
            continue
        for second in second_batch.calculations:
            if (
                second.metadata is not None
                and _metadata_key(first.metadata) == _metadata_key(second.metadata)
            ):
                return (
                    _evidence(
                        "metadata",
                        (first_revision.id, second_revision.id),
                        (first.id, second.id),
                        "calculation metadata matches",
                    ),
                )
    return ()


def _filename_evidence(first_entry, second_entry):
    first_revision = first_entry[1]
    second_revision = second_entry[1]
    first_stem = PureWindowsPath(first_revision.original_filename).stem.casefold()
    second_stem = PureWindowsPath(second_revision.original_filename).stem.casefold()
    first_directory = ntpath.normcase(
        ntpath.normpath(ntpath.dirname(first_revision.locator))
    )
    second_directory = ntpath.normcase(
        ntpath.normpath(ntpath.dirname(second_revision.locator))
    )
    if first_stem != second_stem and first_directory != second_directory:
        return ()
    return (
        _evidence(
            "filename_directory",
            (first_revision.id, second_revision.id),
            (),
            "source filename stem or directory matches",
        ),
    )


def _components(revision_ids, evidence_by_pair):
    adjacency = {revision_id: set() for revision_id in revision_ids}
    for pair in evidence_by_pair:
        left, right = pair
        adjacency[left].add(right)
        adjacency[right].add(left)
    components = []
    unseen = set(revision_ids)
    while unseen:
        start = min(unseen, key=str)
        stack = [start]
        component = set()
        while stack:
            revision_id = stack.pop()
            if revision_id in component:
                continue
            component.add(revision_id)
            unseen.discard(revision_id)
            stack.extend(adjacency[revision_id] - component)
        if len(component) >= 2:
            components.append(tuple(sorted(component, key=str)))
    return tuple(components)


def suggest_source_groups(preview, session):
    if type(preview) is not ImportPreview:
        raise TypeError("preview must be an ImportPreview")
    if type(session) is not StagedImportSession:
        raise TypeError("session must be a StagedImportSession")

    entries = _staged_entries(preview, session)
    _validate_staged_entities(entries)
    if len(entries) < 2:
        return ()
    evidence_by_pair = _explicit_evidence(entries)
    for first_index, first_entry in enumerate(entries):
        for second_entry in entries[first_index + 1 :]:
            pair = tuple(
                sorted(
                    (first_entry[1].id, second_entry[1].id),
                    key=str,
                )
            )
            evidence = list(evidence_by_pair.get(pair, ()))
            evidence.extend(_structure_evidence(first_entry, second_entry))
            evidence.extend(_metadata_evidence(first_entry, second_entry))
            evidence.extend(_filename_evidence(first_entry, second_entry))
            if evidence:
                evidence_by_pair[pair] = tuple(evidence)

    suggestions = []
    revision_ids = tuple(entry[1].id for entry in entries)
    for component in _components(revision_ids, evidence_by_pair):
        evidence = tuple(
            item
            for pair, pair_evidence in evidence_by_pair.items()
            if set(pair).issubset(component)
            for item in pair_evidence
        )
        suggestions.append(
            SourceGroupSuggestion(
                source_revision_ids=component,
                evidence=evidence,
            )
        )
    return tuple(sorted(suggestions, key=lambda item: str(item.id)))
