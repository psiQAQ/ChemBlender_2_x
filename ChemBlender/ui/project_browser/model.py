"""Pure Project Browser flat-tree projection."""

from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
import re
from uuid import UUID


class BrowserMode(str, Enum):
    BY_SOURCE = "by_source"
    BY_DATA = "by_data"


@dataclass(frozen=True, slots=True)
class BrowserRow:
    id: str
    parent_id: str | None
    depth: int
    kind: str
    label: str
    quality: str
    view_count: int
    entity_id: UUID | None
    total_count: int = 0
    page: int = 0
    page_count: int = 0


@dataclass(frozen=True, slots=True)
class _EntityIndexEntry:
    registry: str
    group_label: str
    entity_id: UUID
    revision: str
    kind: str
    label: str
    quality: str
    normalized: str
    source_id: UUID | None
    source_label: str
    source_revision_id: UUID | None
    source_revision_label: str
    row_entity_id: UUID | None
    detail_count: int


@dataclass(frozen=True, slots=True)
class _ProjectionIndex:
    by_source: tuple[_EntityIndexEntry, ...]
    by_data: tuple[_EntityIndexEntry, ...]


@dataclass(frozen=True, slots=True)
class ViewRecord:
    object_name: str
    entity_id: UUID
    revision: str
    view_kind: str
    label: str
    quality: str = ""
    report_eligible: bool = True

    def __post_init__(self):
        if type(self.entity_id) is not UUID:
            raise TypeError("entity_id must be UUID")
        for name in ("object_name", "revision", "view_kind", "label"):
            value = getattr(self, name)
            if type(value) is not str:
                raise TypeError(f"{name} must be str")
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if type(self.quality) is not str:
            raise TypeError("quality must be str")
        if self.quality not in {"", "complete", "partial", "ambiguous"}:
            raise ValueError("quality is not supported")
        if type(self.report_eligible) is not bool:
            raise TypeError("report_eligible must be bool")
        if self.quality in {"partial", "ambiguous"} and self.report_eligible:
            raise ValueError("non-complete view must not be report eligible")


_REGISTRY_GROUPS = (
    ("molecular_records", "Molecular Records"),
    ("datasets", "Datasets"),
    ("structures", "Structures"),
    ("biological_hierarchies", "Biological Hierarchies"),
    ("topologies", "Topologies"),
    ("calculations", "Calculations"),
    ("symmetry_results", "Symmetry"),
    ("basis_sets", "Basis Sets"),
    ("orbital_sets", "Orbital Sets"),
    ("density_matrices", "Density Matrices"),
    ("cif_envelopes", "CIF Envelopes"),
    ("qcschema_envelopes", "QCSchema Envelopes"),
    ("cjson_envelopes", "CJSON Envelopes"),
    ("provenance", "Provenance"),
)
_CACHE = OrderedDict()
_INDEX_CACHE = OrderedDict()
_ROW_CACHE_LIMIT = 32
_INDEX_CACHE_LIMIT = 2
_DEFAULT_PAGE_SIZE = 998
_MAX_PAGE_SIZE = 998
_BROWSER_ROW_LIMIT = 1000
_REGISTRY_ORDER = {
    name: index for index, (name, _label_text) in enumerate(_REGISTRY_GROUPS)
}
_REGISTRY_ORDER["diagnostics"] = len(_REGISTRY_ORDER)


def clear_browser_session_cache(session):
    """Release cached projections owned by one UI session."""
    session_id = str(getattr(session, "id", session))
    for cache in (_CACHE, _INDEX_CACHE):
        for key in tuple(cache):
            if key[1] == session_id:
                del cache[key]


def clear_browser_caches():
    """Release all Project Browser projection state."""
    _CACHE.clear()
    _INDEX_CACHE.clear()


def _token(value):
    name = type(value).__name__.replace("3D", "3d")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _quality(value):
    status = getattr(value, "status", None)
    if status is None:
        status = getattr(value, "quality_status", None)
    return getattr(status, "value", "") if status is not None else ""


def _label(value):
    record_key = getattr(value, "record_key", None)
    title = getattr(value, "title", None)
    if type(record_key) is str and type(title) is str:
        version = getattr(value, "block_version", None) or "SMILES"
        return f"{title or record_key} · {version}"
    source = getattr(getattr(value, "source_kind", None), "value", None)
    bonds = getattr(getattr(value, "bond_indices", None), "shape", ())
    if type(source) is str and len(bonds) == 2:
        parameters = getattr(value, "inference_parameters", ())
        suffix = (
            ""
            if not parameters
            else " (" + ", ".join(
                f"{name}={setting}" for name, setting in parameters
            ) + ")"
        )
        return (
            f"{source.replace('_', ' ').title()}: {bonds[0]} bonds"
            f"{suffix}"
        )
    for name in ("display_name", "semantic_role", "original_filename"):
        text = getattr(value, name, None)
        if type(text) is str and text:
            return text.replace("_", " ").title()
    return type(value).__name__.replace("_", " ")


def _view_row(view, parent_id, depth):
    return BrowserRow(
        id=(
            f"{parent_id}/view:{view.object_name}:"
            f"{view.entity_id}:{view.revision}"
        ),
        parent_id=parent_id,
        depth=depth,
        kind="view",
        label=view.label,
        quality=view.quality,
        view_count=0,
        entity_id=None,
    )


def _entity_views(entity, views):
    candidates = sorted(
        (
            view
            for view in views
            if (
                view.entity_id == entity.id
                and view.revision == entity.revision
            )
        ),
        key=lambda view: (
            view.object_name,
            str(view.entity_id),
            view.revision,
            view.view_kind,
            view.label,
        ),
    )
    unique = {}
    for view in candidates:
        unique.setdefault(
            (view.object_name, view.entity_id, view.revision),
            view,
        )
    return tuple(
        sorted(
            unique.values(),
            key=lambda view: (
                view.label.casefold(),
                view.object_name,
                view.view_kind,
            ),
        )
    )


def _entity_row(entity, parent_id, depth, views):
    entity_views = _entity_views(entity, views)
    row_id = f"{parent_id}/entity:{entity.id}"
    details = (
        *_periodic_detail_rows(entity, row_id, depth + 1),
        *_biological_detail_rows(entity, row_id, depth + 1),
    )
    return (
        BrowserRow(
            id=row_id,
            parent_id=parent_id,
            depth=depth,
            kind=_token(entity),
            label=_label(entity),
            quality=_quality(entity),
            view_count=len(entity_views),
            entity_id=entity.id,
        ),
        *details,
        *(_view_row(view, row_id, depth + 1) for view in entity_views),
    )


def _periodic_detail_rows(entity, parent_id, depth):
    periodic = getattr(entity, "periodic", None)
    if periodic is None:
        return ()
    atom_count = len(entity.atomic_numbers)
    disorder_count = sum(
        value != 0 for value in periodic.disorder_groups
    )
    return (
        BrowserRow(
            f"{parent_id}/crystal-sites",
            parent_id,
            depth,
            "crystal_sites",
            (
                f"Sites: {atom_count} · Occupancy: per-site · "
                f"Disorder: {disorder_count} grouped"
            ),
            "",
            0,
            None,
        ),
        BrowserRow(
            f"{parent_id}/crystal-adp",
            parent_id,
            depth,
            "crystal_adp",
            (
                "ADP: Uiso "
                f"{'available' if periodic.isotropic_displacements is not None else 'missing'}"
                " · Uij "
                f"{'available' if periodic.anisotropic_displacements is not None else 'missing'}"
            ),
            "",
            0,
            None,
        ),
    )


def _biological_detail_rows(entity, parent_id, depth):
    chains = getattr(entity, "chains", None)
    residues = getattr(entity, "residues", None)
    atom_sites = getattr(entity, "atom_sites", None)
    if chains is None or residues is None or atom_sites is None:
        return ()
    residues_by_chain = [[] for _chain in chains]
    for residue_index, residue in enumerate(residues):
        residues_by_chain[residue.chain_index].append((residue_index, residue))
    atom_counts = [0] * len(chains)
    for residue_index in atom_sites.residue_indices.values:
        atom_counts[residues[int(residue_index)].chain_index] += 1
    rows = []
    for chain_index, chain in enumerate(chains):
        chain_id = f"{parent_id}/chain:{chain_index}"
        chain_residues = residues_by_chain[chain_index]
        label = chain.chain_id or "[blank]"
        rows.append(
            BrowserRow(
                chain_id,
                parent_id,
                depth,
                "biological_chain",
                (
                    f"Chain {label} · Segment {chain.segment_index} · "
                    f"{len(chain_residues)} residues · "
                    f"{atom_counts[chain_index]} atoms"
                ),
                "",
                0,
                entity.id,
            )
        )
        rows.extend(
            BrowserRow(
                f"{chain_id}/residue:{residue_index}",
                chain_id,
                depth + 1,
                "biological_residue",
                (
                    f"{residue.residue_name} {residue.sequence_number}"
                    f"{residue.insertion_code}"
                ),
                "",
                0,
                entity.id,
            )
            for residue_index, residue in chain_residues
        )
    return tuple(rows)


def _entity_lookup(project):
    lookup = {}
    for name, _label_text in _REGISTRY_GROUPS:
        lookup.update(getattr(project, name, {}))
    return lookup


def _browser_entity_ids(project):
    return frozenset(_entity_lookup(project))


def _unique_ids(values):
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            yield value


def _by_source(project, views):
    rows = []
    entities = _entity_lookup(project)
    sources = sorted(
        project.sources.values(),
        key=lambda value: (value.display_name.casefold(), str(value.id)),
    )
    for source in sources:
        source_id = f"source:{source.id}"
        rows.append(
            BrowserRow(
                source_id,
                None,
                0,
                "source",
                source.display_name,
                "",
                0,
                None,
            )
        )
        revisions = sorted(
            (
                revision
                for revision in project.source_revisions.values()
                if revision.source_id == source.id
            ),
            key=lambda value: (value.original_filename.casefold(), str(value.id)),
        )
        for revision in revisions:
            revision_id = f"{source_id}/revision:{revision.id}"
            rows.append(
                BrowserRow(
                    revision_id,
                    source_id,
                    1,
                    "source_revision",
                    revision.original_filename,
                    "",
                    0,
                    None,
                )
            )
            created = tuple(
                entities[entity_id]
                for entity_id in _unique_ids(revision.created_entity_ids)
                if entity_id in entities
            )
            for entity in created:
                rows.extend(_entity_row(entity, revision_id, 2, views))
            diagnostics = sorted(
                (
                    project.diagnostics[diagnostic_id]
                    for diagnostic_id in _unique_ids(
                        revision.diagnostic_ids
                    )
                ),
                key=lambda value: (
                    value.severity.summary_order,
                    value.message.casefold(),
                    str(value.id),
                ),
            )
            for diagnostic in diagnostics:
                rows.append(
                    BrowserRow(
                        f"{revision_id}/diagnostic:{diagnostic.id}",
                        revision_id,
                        2,
                        "diagnostic",
                        diagnostic.message,
                        diagnostic.quality_status.value,
                        0,
                        diagnostic.entity_id,
                    )
                )
    return tuple(rows)


def _by_data(project, views):
    rows = []
    for name, label in _REGISTRY_GROUPS:
        entities = tuple(
            sorted(
                getattr(project, name, {}).values(),
                key=lambda value: (_label(value).casefold(), str(value.id)),
            )
        )
        if not entities:
            continue
        group_id = f"group:{name}"
        rows.append(BrowserRow(group_id, None, 0, "group", label, "", 0, None))
        if name == "datasets":
            frame_sets = tuple(
                entity for entity in entities if _token(entity) == "frame_set"
            )
            conformer_sets = tuple(
                entity
                for entity in entities
                if _token(entity) == "conformer_set"
            )
            parents = (*frame_sets, *conformer_sets)
            frame_set_ids = {frame_set.id for frame_set in frame_sets}
            conformer_record_ids = {
                conformer_set.id: conformer_set.record_ids
                for conformer_set in conformer_sets
            }

            def parent_for(entity, parent):
                if _token(parent) == "frame_set":
                    return getattr(entity, "frame_set_id", None) == parent.id
                return (
                    entity is not parent
                    and getattr(entity, "record_ids", None)
                    == conformer_record_ids[parent.id]
                )

            grouped_ids = {
                entity.id
                for entity in entities
                if (
                    getattr(entity, "frame_set_id", None) in frame_set_ids
                    or any(
                        parent_for(entity, conformer_set)
                        for conformer_set in conformer_sets
                    )
                )
            }
            for parent in parents:
                parent_rows = _entity_row(parent, group_id, 1, views)
                rows.extend(parent_rows)
                parent_row_id = parent_rows[0].id
                for entity in entities:
                    if parent_for(entity, parent):
                        rows.extend(
                            _entity_row(entity, parent_row_id, 2, views)
                        )
            for entity in entities:
                if (
                    entity.id not in grouped_ids
                    and entity not in parents
                ):
                    rows.extend(_entity_row(entity, group_id, 1, views))
            continue
        for entity in entities:
            rows.extend(_entity_row(entity, group_id, 1, views))
    diagnostics = tuple(
        sorted(
            project.diagnostics.values(),
            key=lambda value: (
                value.severity.summary_order,
                value.message.casefold(),
                str(value.id),
            ),
        )
    )
    if diagnostics:
        group_id = "group:diagnostics"
        rows.append(
            BrowserRow(group_id, None, 0, "group", "Diagnostics", "", 0, None)
        )
        rows.extend(
            BrowserRow(
                f"{group_id}/diagnostic:{value.id}",
                group_id,
                1,
                "diagnostic",
                value.message,
                value.quality_status.value,
                0,
                value.entity_id,
            )
            for value in diagnostics
        )
    return tuple(rows)


def _cache_scope(project, session_id, browser_revision):
    if (
        session_id is None
        or not str(session_id).strip()
        or type(browser_revision) is not int
        or browser_revision < 0
    ):
        return None
    return (
        str(getattr(project, "id", "")),
        str(session_id),
        browser_revision,
    )


def _index_scope(project, session_id, browser_revision):
    if _cache_scope(project, session_id, browser_revision) is None:
        return None
    return (
        str(getattr(project, "id", "")),
        str(session_id),
        id(project),
        tuple(
            len(getattr(project, name, {}))
            for name, _label_text in _REGISTRY_GROUPS
        ),
        len(getattr(project, "sources", {})),
        len(getattr(project, "source_revisions", {})),
        len(getattr(project, "diagnostics", {})),
    )


def _remember(cache, key, value, limit):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > limit:
        cache.popitem(last=False)
    return value


def _remember_rows(key, rows):
    if key is None:
        return rows
    for stale in tuple(_CACHE):
        if (
            stale[0] == key[0]
            and stale[1] == key[1]
            and stale[3] == key[3]
            and stale[2] != key[2]
        ):
            del _CACHE[stale]
    return _remember(_CACHE, key, rows, _ROW_CACHE_LIMIT)


def _source_sort_key(entry):
    return (
        entry.source_label.casefold(),
        str(entry.source_id),
        entry.source_revision_label.casefold(),
        str(entry.source_revision_id),
        _REGISTRY_ORDER.get(entry.registry, -1),
        entry.label.casefold(),
        str(entry.entity_id),
    )


def _data_sort_key(entry):
    return (
        _REGISTRY_ORDER[entry.registry],
        entry.label.casefold(),
        str(entry.entity_id),
    )


def _index_detail_count(entity):
    count = 2 if getattr(entity, "periodic", None) is not None else 0
    chains = getattr(entity, "chains", None)
    residues = getattr(entity, "residues", None)
    atom_sites = getattr(entity, "atom_sites", None)
    if chains is not None and residues is not None and atom_sites is not None:
        count += len(chains) + len(residues)
    return count


def _projection_index(project, scope):
    if scope is not None:
        cached = _INDEX_CACHE.get(scope)
        if cached is not None:
            _INDEX_CACHE.move_to_end(scope)
            return cached
    revisions = getattr(project, "source_revisions", {})
    sources = getattr(project, "sources", {})
    revision_locations = {}
    entity_locations = {}
    for source_revision in revisions.values():
        source = sources.get(source_revision.source_id)
        location = (
            getattr(source, "id", None),
            getattr(source, "display_name", ""),
            source_revision.id,
            source_revision.original_filename,
        )
        revision_locations[source_revision.id] = location
        for entity_id in _unique_ids(
            (
                *source_revision.created_entity_ids,
                *source_revision.diagnostic_ids,
            )
        ):
            entity_locations.setdefault(entity_id, location)
    entries = []
    for registry, group_label in _REGISTRY_GROUPS:
        for entity in getattr(project, registry, {}).values():
            location = entity_locations.get(entity.id, (None, "", None, ""))
            label = _label(entity)
            quality = _quality(entity)
            kind = _token(entity)
            revision = getattr(entity, "revision", "")
            entries.append(
                _EntityIndexEntry(
                    registry,
                    group_label,
                    entity.id,
                    revision,
                    kind,
                    label,
                    quality,
                    " ".join(
                        value
                        for value in (
                            label,
                            kind,
                            group_label,
                            quality,
                            str(entity.id),
                            revision,
                            location[1],
                            location[3],
                        )
                        if value
                    ).casefold(),
                    location[0],
                    location[1],
                    location[2],
                    location[3],
                    entity.id,
                    _index_detail_count(entity),
                )
            )
    for diagnostic in getattr(project, "diagnostics", {}).values():
        location = revision_locations.get(
            diagnostic.source_revision_id,
            (None, "", diagnostic.source_revision_id, ""),
        )
        quality = diagnostic.quality_status.value
        entries.append(
            _EntityIndexEntry(
                "diagnostics",
                "Diagnostics",
                diagnostic.id,
                "",
                "diagnostic",
                diagnostic.message,
                quality,
                " ".join(
                    value
                    for value in (
                        diagnostic.message,
                        "diagnostic",
                        "Diagnostics",
                        quality,
                        diagnostic.code,
                        diagnostic.field_path,
                        str(diagnostic.id),
                        location[1],
                        location[3],
                    )
                    if value
                ).casefold(),
                location[0],
                location[1],
                location[2],
                location[3],
                diagnostic.entity_id,
                0,
            )
        )
    covered_revision_ids = {
        entry.source_revision_id
        for entry in entries
        if entry.source_revision_id is not None
    }
    revisions_by_source = {}
    for source_revision in revisions.values():
        revisions_by_source.setdefault(
            source_revision.source_id,
            [],
        ).append(source_revision)
    source_branches = []
    for source in sources.values():
        source_revisions = revisions_by_source.get(source.id, ())
        if not source_revisions:
            source_branches.append(
                _EntityIndexEntry(
                    "",
                    "",
                    source.id,
                    "",
                    "source",
                    source.display_name,
                    "",
                    " ".join(
                        (
                            source.display_name,
                            "source",
                            str(source.id),
                        )
                    ).casefold(),
                    source.id,
                    source.display_name,
                    None,
                    "",
                    None,
                    0,
                )
            )
            continue
        for source_revision in source_revisions:
            if source_revision.id in covered_revision_ids:
                continue
            source_branches.append(
                _EntityIndexEntry(
                    "",
                    "",
                    source_revision.id,
                    "",
                    "source_revision",
                    source_revision.original_filename,
                    "",
                    " ".join(
                        (
                            source.display_name,
                            source_revision.original_filename,
                            "source revision",
                            str(source.id),
                            str(source_revision.id),
                        )
                    ).casefold(),
                    source.id,
                    source.display_name,
                    source_revision.id,
                    source_revision.original_filename,
                    None,
                    0,
                )
            )
    result = _ProjectionIndex(
        tuple(
            sorted(
                (*entries, *source_branches),
                key=_source_sort_key,
            )
        ),
        tuple(sorted(entries, key=_data_sort_key)),
    )
    if scope is None:
        return result
    for stale in tuple(_INDEX_CACHE):
        if stale[:2] == scope[:2] and stale != scope:
            del _INDEX_CACHE[stale]
    return _remember(
        _INDEX_CACHE,
        scope,
        result,
        _INDEX_CACHE_LIMIT,
    )


def _record_views(views):
    grouped = {}
    for view in views:
        grouped.setdefault((view.entity_id, view.revision), {}).setdefault(
            (view.object_name, view.entity_id, view.revision),
            view,
        )
    return {
        key: tuple(
            sorted(
                unique.values(),
                key=lambda view: (
                    view.label.casefold(),
                    view.object_name,
                    view.view_kind,
                ),
            )
        )
        for key, unique in grouped.items()
    }


def _matches_projection(search, filters, normalized, kind, quality):
    return (
        (not search or search in normalized)
        and (
            not filters
            or kind.casefold() in filters
            or quality.casefold() in filters
        )
    )


def _matching_entries(entries, search, filters, views, visible_views):
    for entry in entries:
        if _matches_projection(
            search,
            filters,
            entry.normalized,
            entry.kind,
            entry.quality,
        ):
            if views and entry.registry:
                key = (entry.entity_id, entry.revision)
                entity_views = views.get(key, ())
                if entity_views:
                    visible_views[key] = entity_views
            yield entry
            continue
        if not views or not entry.registry:
            continue
        key = (entry.entity_id, entry.revision)
        entity_views = views.get(key, ())
        matching_views = tuple(
            view
            for view in entity_views
            if _matches_projection(
                search,
                filters,
                " ".join(
                    (view.label, view.view_kind, view.quality)
                ).casefold(),
                view.view_kind,
                view.quality,
            )
        )
        if matching_views:
            visible_views[key] = matching_views
            yield entry


def _large_projection_required(entries, views, mode, page_size):
    if len(entries) > page_size:
        return True
    if mode is BrowserMode.BY_DATA:
        ancestor_count = len({entry.registry for entry in entries})
    else:
        ancestor_count = (
            len({
                entry.source_id
                for entry in entries
                if entry.registry or entry.kind == "source_revision"
            })
            + len({
                entry.source_revision_id
                for entry in entries
                if entry.registry
            })
        )
    return (
        1
        + len(entries)
        + ancestor_count
        + sum(
            entry.detail_count
            for entry in entries
            if entry.registry
        )
        + sum(len(values) for values in views.values())
        > _BROWSER_ROW_LIMIT
    )


def _page_slice(
    entries,
    views,
    page,
    page_size,
    mode,
    row_limit,
    *,
    base_row_count=1,
    initial_registries=(),
):
    current = []
    current_start = 0
    selected = None
    selected_start = 0
    last = ()
    last_start = 0
    page_count = 0
    total_count = 0
    row_count = base_row_count
    registry_ids = set(initial_registries)
    source_ids = set()
    revision_ids = set()

    def finish_page():
        nonlocal current
        nonlocal last
        nonlocal last_start
        nonlocal page_count
        nonlocal selected
        nonlocal selected_start
        values = tuple(current)
        if page_count == page:
            selected = values
            selected_start = current_start
        last = values
        last_start = current_start
        page_count += 1
        current = []

    for entry in entries:
        ancestor_count = 0
        if mode is BrowserMode.BY_DATA:
            if entry.registry not in registry_ids:
                ancestor_count = 1
        elif not entry.registry:
            if (
                entry.kind == "source_revision"
                and entry.source_id not in source_ids
            ):
                ancestor_count = 1
        else:
            if entry.source_id not in source_ids:
                ancestor_count += 1
            if entry.source_revision_id not in revision_ids:
                ancestor_count += 1
        entry_count = 1
        if entry.registry:
            entry_count += (
                len(views.get((entry.entity_id, entry.revision), ()))
                + (entry.detail_count > 0)
            )
        if current and (
            len(current) >= page_size
            or row_count + ancestor_count + entry_count > row_limit
        ):
            finish_page()
            current_start = total_count
            row_count = base_row_count
            registry_ids = set(initial_registries)
            source_ids = set()
            revision_ids = set()
            if mode is BrowserMode.BY_DATA:
                ancestor_count = entry.registry not in registry_ids
            elif not entry.registry:
                ancestor_count = entry.kind == "source_revision"
            else:
                ancestor_count = 2
        if row_count + ancestor_count + entry_count > row_limit:
            raise ValueError(
                "one project entity has too many Project Browser views"
            )
        current.append(entry)
        total_count += 1
        row_count += ancestor_count + entry_count
        registry_ids.add(entry.registry)
        source_ids.add(entry.source_id)
        if entry.registry or entry.source_revision_id is not None:
            revision_ids.add(entry.source_revision_id)
    if current:
        finish_page()
    if not page_count:
        return (), 0, 0, 0, 0
    if selected is None:
        return last, last_start, page_count - 1, page_count, total_count
    return selected, selected_start, page, page_count, total_count


def _indexed_entity_rows(entry, parent_id, depth, views):
    entity_views = views.get((entry.entity_id, entry.revision), ())
    row_id = f"{parent_id}/entity:{entry.entity_id}"
    rows = [
        BrowserRow(
            row_id,
            parent_id,
            depth,
            entry.kind,
            entry.label,
            entry.quality,
            len(entity_views),
            entry.row_entity_id,
        )
    ]
    if entry.detail_count:
        rows.append(
            BrowserRow(
                f"{row_id}/details",
                row_id,
                depth + 1,
                "projection_summary",
                (
                    f"{entry.detail_count} detail rows hidden in the "
                    "large-project projection; refine Search or Filter"
                ),
                "",
                0,
                None,
                entry.detail_count,
            )
        )
    rows.extend(
        _view_row(view, row_id, depth + 1)
        for view in entity_views
    )
    return tuple(rows)


def _page_rows(
    entries,
    entity_views,
    page,
    page_size,
    mode,
    row_limit,
    *,
    summary_kind,
    summary_noun,
    data_group=None,
):
    selected, start, page, page_count, total_count = _page_slice(
        entries,
        entity_views,
        page,
        page_size,
        mode,
        row_limit,
        base_row_count=1 + (data_group is not None),
        initial_registries=(
            (data_group[0],) if data_group is not None else ()
        ),
    )
    if not selected:
        return ()
    page_id = f"page:{summary_kind}:{mode.value}:{page}"
    parent_id = None
    summary_depth = 0
    rows = []
    if data_group is not None:
        parent_id = f"group:{data_group[0]}"
        summary_depth = 1
        rows.append(
            BrowserRow(
                parent_id,
                None,
                0,
                "group",
                data_group[1],
                "",
                0,
                None,
            )
        )
    rows.append(
        BrowserRow(
            page_id,
            parent_id,
            summary_depth,
            summary_kind,
            (
                f"{summary_noun} {start + 1}-{start + len(selected)} "
                f"of {total_count}"
            ),
            "",
            0,
            None,
            total_count,
            page,
            page_count,
        )
    )
    if data_group is not None:
        rows.extend(
            row
            for entry in selected
            for row in _indexed_entity_rows(
                entry,
                page_id,
                2,
                entity_views,
            )
        )
        return tuple(rows)
    if mode is BrowserMode.BY_DATA:
        group_paths = {}
        for entry in selected:
            group_path = group_paths.get(entry.registry)
            if group_path is None:
                group_path = f"{page_id}/group:{entry.registry}"
                group_paths[entry.registry] = group_path
                rows.append(
                    BrowserRow(
                        group_path,
                        page_id,
                        1,
                        "group",
                        entry.group_label,
                        "",
                        0,
                        None,
                    )
                )
            rows.extend(
                _indexed_entity_rows(entry, group_path, 2, entity_views)
            )
        return tuple(rows)
    source_paths = {}
    revision_paths = {}
    for entry in selected:
        source_key = entry.source_id
        source_path = source_paths.get(source_key)
        if source_path is None:
            source_path = f"{page_id}/source:{source_key}"
            source_paths[source_key] = source_path
            rows.append(
                BrowserRow(
                    source_path,
                    page_id,
                    1,
                    "source",
                    entry.source_label or "Unattributed project data",
                    "",
                    0,
                    None,
                )
            )
        if not entry.registry and entry.kind == "source":
            continue
        revision_key = (source_key, entry.source_revision_id)
        revision_path = revision_paths.get(revision_key)
        if revision_path is None:
            revision_path = (
                f"{source_path}/revision:{entry.source_revision_id}"
            )
            revision_paths[revision_key] = revision_path
            rows.append(
                BrowserRow(
                    revision_path,
                    source_path,
                    2,
                    "source_revision",
                    entry.source_revision_label or "No source revision",
                    "",
                    0,
                    None,
                )
            )
        if not entry.registry:
            continue
        rows.extend(
            _indexed_entity_rows(entry, revision_path, 3, entity_views)
        )
    return tuple(rows)


def _additional_summary(index, mode):
    entries = tuple(
        entry
        for entry in index
        if entry.registry != "molecular_records"
    )
    if not entries:
        return ()
    if mode is BrowserMode.BY_SOURCE:
        source_count = len({
            entry.source_id for entry in entries if entry.source_id is not None
        })
        revision_count = len({
            entry.source_revision_id
            for entry in entries
            if entry.source_revision_id is not None
        })
        details = f"{source_count} source / {revision_count} revision"
        branch_count = sum(not entry.registry for entry in entries)
        if branch_count:
            details = f"{details}; {branch_count} empty source branches"
    else:
        counts = {}
        labels = {}
        for entry in entries:
            counts[entry.registry] = counts.get(entry.registry, 0) + 1
            labels[entry.registry] = entry.group_label
        details = "; ".join(
            f"{labels[name]} {counts[name]:,}"
            for name, _label_text in (*_REGISTRY_GROUPS, ("diagnostics", "Diagnostics"))
            if name in counts
        )
    return (
        BrowserRow(
            f"summary:additional:{mode.value}",
            None,
            0,
            "projection_summary",
            (
                f"{len(entries):,} additional entries hidden ({details}); "
                "use Search or Filter to page them"
            ),
            "",
            0,
            None,
            len(entries),
        ),
    )


def _filtered(rows, search, filters, mode):
    if not search and not filters:
        return rows
    matching = {
        row.id
        for row in rows
        if (
            not search
            or search
            in " ".join((row.label, row.kind, row.quality)).casefold()
        )
        and (
            not filters
            or row.kind in filters
            or row.quality in filters
        )
    }
    parents = {row.id: row.parent_id for row in rows}
    matching.update(
        row.id
        for row in rows
        if row.kind == "view" and row.parent_id in matching
    )
    for row_id in tuple(matching):
        parent_id = parents[row_id]
        while parent_id is not None:
            matching.add(parent_id)
            parent_id = parents[parent_id]
    filtered = tuple(row for row in rows if row.id in matching)
    if filtered:
        return filtered
    return (
        BrowserRow(
            f"empty:{mode.value}",
            None,
            0,
            "empty",
            "No matching project data",
            "",
            0,
            None,
        ),
    )


def _empty_rows(mode):
    return (
        BrowserRow(
            f"empty:{mode.value}",
            None,
            0,
            "empty",
            "No project data",
            "",
            0,
            None,
        ),
    )


def build_browser_rows(
    project,
    *,
    mode=BrowserMode.BY_SOURCE,
    session_id=None,
    browser_revision=None,
    search="",
    filters=(),
    views=(),
    page=0,
    page_size=_DEFAULT_PAGE_SIZE,
):
    if type(page) is not int:
        raise TypeError("page must be int")
    if page < 0:
        raise ValueError("page must not be negative")
    if type(page_size) is not int:
        raise TypeError("page_size must be int")
    if not 1 <= page_size <= _MAX_PAGE_SIZE:
        raise ValueError(
            f"page_size must be between 1 and {_MAX_PAGE_SIZE}"
        )
    mode = BrowserMode(mode)
    search = str(search).strip().casefold()
    filters = tuple(
        sorted(
            {
                str(value).strip().casefold()
                for value in filters
                if str(value).strip()
            }
        )
    )
    views = tuple(views)
    if any(type(view) is not ViewRecord for view in views):
        raise TypeError("views must contain ViewRecord values")
    views = tuple(
        sorted(
            views,
            key=lambda view: (
                str(view.entity_id),
                view.revision,
                view.label.casefold(),
                view.object_name,
                view.view_kind,
            ),
        )
    )
    view_fingerprint = tuple(
        (
            view.object_name,
            str(view.entity_id),
            view.revision,
            view.view_kind,
            view.label,
            view.quality,
            view.report_eligible,
        )
        for view in views
    )
    scope = _cache_scope(project, session_id, browser_revision)
    key = (
        *scope,
        mode,
        page,
        page_size,
        view_fingerprint,
    ) if scope is not None and not search and not filters else None
    if key is not None:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key)
            return cached

    projection = _projection_index(
        project,
        _index_scope(project, session_id, browser_revision),
    )
    index = (
        projection.by_source
        if mode is BrowserMode.BY_SOURCE
        else projection.by_data
    )
    entity_views = _record_views(views)
    records = getattr(project, "molecular_records", {})
    if _large_projection_required(
        index,
        entity_views,
        mode,
        page_size,
    ):
        if search or filters or not records:
            visible_views = {}
            entries = (
                _matching_entries(
                    index,
                    search,
                    filters,
                    entity_views,
                    visible_views,
                )
                if search or filters
                else index
            )
            rows = _page_rows(
                entries,
                (
                    visible_views
                    if search or filters
                    else entity_views
                ),
                page,
                page_size,
                mode,
                _BROWSER_ROW_LIMIT,
                summary_kind="result_page",
                summary_noun=(
                    "Matches" if search or filters else "Entries"
                ),
            )
            if rows:
                return _remember_rows(key, rows)
            return (
                BrowserRow(
                    f"empty:{mode.value}",
                    None,
                    0,
                    "empty",
                    "No matching project data",
                    "",
                    0,
                    None,
                ),
            )
        summary_rows = _additional_summary(index, mode)
        record_rows = _page_rows(
            (
                entry
                for entry in index
                if entry.registry == "molecular_records"
            ),
            entity_views,
            page,
            page_size,
            mode,
            _BROWSER_ROW_LIMIT - len(summary_rows),
            summary_kind="record_page",
            summary_noun="Records",
            data_group=(
                ("molecular_records", "Molecular Records")
                if mode is BrowserMode.BY_DATA
                else None
            ),
        )
        rows = (*record_rows, *summary_rows)
        return _remember_rows(
            key,
            tuple(rows),
        )

    if search or filters:
        rows = build_browser_rows(
            project,
            mode=mode,
            session_id=session_id,
            browser_revision=browser_revision,
            views=views,
            page=page,
            page_size=page_size,
        )
        return (
            rows
            if len(rows) == 1 and rows[0].kind == "empty"
            else _filtered(rows, search, filters, mode)
        )
    rows = (
        _by_source(project, views)
        if mode is BrowserMode.BY_SOURCE
        else _by_data(project, views)
    )
    return _remember_rows(key, rows if rows else _empty_rows(mode))


__all__ = (
    "BrowserMode",
    "BrowserRow",
    "ViewRecord",
    "build_browser_rows",
    "clear_browser_caches",
    "clear_browser_session_cache",
)
