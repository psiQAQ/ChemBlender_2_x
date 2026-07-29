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
_CACHE_LIMIT = 32


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
    rows = []
    for chain_index, chain in enumerate(chains):
        chain_id = f"{parent_id}/chain:{chain_index}"
        chain_residues = tuple(
            (index, residue)
            for index, residue in enumerate(residues)
            if residue.chain_index == chain_index
        )
        residue_ids = {index for index, _residue in chain_residues}
        atom_count = sum(
            int(value) in residue_ids
            for value in atom_sites.residue_indices.values
        )
        label = chain.chain_id or "[blank]"
        rows.append(
            BrowserRow(
                chain_id,
                parent_id,
                depth,
                "biological_chain",
                (
                    f"Chain {label} · Segment {chain.segment_index} · "
                    f"{len(chain_residues)} residues · {atom_count} atoms"
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
    browser_revision=0,
    search="",
    filters=(),
    views=(),
):
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
    if search or filters:
        rows = build_browser_rows(
            project,
            mode=mode,
            session_id=session_id,
            browser_revision=browser_revision,
            views=views,
        )
        return (
            rows
            if len(rows) == 1 and rows[0].kind == "empty"
            else _filtered(rows, search, filters, mode)
        )
    key = (
        id(project),
        getattr(project, "id", None),
        session_id,
        browser_revision,
        mode,
        search,
        filters,
        view_fingerprint,
    )
    cached = _CACHE.get(key)
    if cached is not None:
        _CACHE.move_to_end(key)
        return cached
    rows = (
        _by_source(project, views)
        if mode is BrowserMode.BY_SOURCE
        else _by_data(project, views)
    )
    result = (
        rows
        if len(rows) == 1 and rows[0].kind == "empty"
        else (
            _filtered(rows, "", (), mode)
            if rows
            else _empty_rows(mode)
        )
    )
    scope = (key[0], key[1], key[2], key[4])
    for stale in tuple(_CACHE):
        if (stale[0], stale[1], stale[2], stale[4]) == scope:
            del _CACHE[stale]
    _CACHE[key] = result
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_LIMIT:
        _CACHE.popitem(last=False)
    return result


__all__ = ("BrowserMode", "BrowserRow", "ViewRecord", "build_browser_rows")
