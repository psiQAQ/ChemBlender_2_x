"""Blender Import Preview projection and transaction confirmation."""

import shutil
from dataclasses import dataclass, fields, is_dataclass, replace
from hashlib import sha256
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread
from uuid import UUID, uuid4

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)

from ..core import (
    DiagnosticSeverity,
    QualityStatus,
    RecordPropertyColumn,
    builtin_scene_presets,
    plan_scene_preset,
    unit_cell_parameters,
)
from ..core.import_pipeline.conflicts import (
    ConflictDecision,
    DuplicateAction,
    detect_import_conflicts,
)
from ..core.import_pipeline.conformer_grouping import (
    suggest_staged_conformer_groups,
)
from ..core.import_pipeline.grouping import suggest_source_groups
from ..core.import_pipeline.preflight import ImportCancelled
from ..core.import_pipeline.preview import ImportPreview
from ..core.import_pipeline.request import (
    ImportRequest,
    ImportSource,
    ReaderOverride,
    ValidationMode,
)
from ..core.import_pipeline.transaction import (
    ConformerGroupingDecision,
    GroupingDecision,
    ImportCommitDecisions,
    commit_import_preview,
)
from ..reader_api.import_pipeline_bridge import preflight_reader_plugins
from ..scene_preset_view import (
    _remove_objects as _remove_scene_preset_objects,
    apply_scene_preset,
)
from ..runtime.reader_api_bridge import get_reader_plugin_registry
from .default_views import describe_default_view, plan_default_view
from .extxyz_preview import extxyz_preview_summary
from .grid import grid_preview_summary
from .properties import (
    discard_quick_import_preview,
    finish_quick_import_job,
    get_quick_import_state,
    store_quick_import_job,
)
from .session import get_scene_session


_ACTION_ITEMS = tuple(
    (action.value, action.value.replace("_", " ").title(), "")
    for action in DuplicateAction
)
_ACTION_ITEMS_BY_VALUE = {
    identifier: (identifier, label, description)
    for identifier, label, description in _ACTION_ITEMS
}
_GROUPING_ACTION_ITEMS = (
    (
        "keep_independent",
        "Keep Independent",
        "Do not create a Calculation Group",
    ),
    (
        "accept_group",
        "Accept Group",
        "Create the suggested Calculation Group",
    ),
)
_CONFORMER_GROUPING_ACTION_ITEMS = (
    (
        "keep_independent",
        "Keep Independent",
        "Keep each molecular record as an independent Structure",
    ),
    (
        "accept_group",
        "Accept Group",
        "Create the suggested ConformerSet",
    ),
)
_TARGET_ACTIONS = frozenset(
    {
        DuplicateAction.REUSE_EXISTING,
        DuplicateAction.LOCATE_EXISTING,
        DuplicateAction.LINK_EXISTING,
    }
)
_SKIP_ACTIONS = frozenset(
    {
        DuplicateAction.REUSE_EXISTING,
        DuplicateAction.LOCATE_EXISTING,
        DuplicateAction.LINK_EXISTING,
        DuplicateAction.IGNORE,
    }
)
_CONFORMER_EVIDENCE_PREVIEW_LIMIT = 20
_RNA_TEXT_PREVIEW_LIMIT = 256
_FATAL_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    MemoryError,
)


def _merge_cleanup_failure(failure, error, label):
    if failure is None:
        return error
    if isinstance(error, _FATAL_EXCEPTIONS) and not isinstance(
        failure,
        _FATAL_EXCEPTIONS,
    ):
        error.add_note(f"earlier cleanup failed: {failure}")
        return error
    failure.add_note(f"{label}: {error}")
    return failure


def _rna_preview_text(value):
    text = str(value)
    if len(text) <= _RNA_TEXT_PREVIEW_LIMIT:
        return text
    return text[: _RNA_TEXT_PREVIEW_LIMIT - 1] + "…"


def _new_preflight_job(*args, **kwargs):
    from .quick_import import _PreflightJob

    return _PreflightJob(*args, **kwargs)


def _conflict_action_items(row, _context):
    values = tuple(
        value
        for value in getattr(row, "allowed_actions", "").split(",")
        if value in _ACTION_ITEMS_BY_VALUE
    )
    if not values:
        values = (DuplicateAction.INDEPENDENT_COPY.value,)
    return tuple(_ACTION_ITEMS_BY_VALUE[value] for value in values)


class CHEMBLENDER_PG_import_conflict_candidate(bpy.types.PropertyGroup):
    revision_id: StringProperty()
    source_id: StringProperty()
    display_label: StringProperty()
    created_entity_count: IntProperty()
    selected: BoolProperty(default=False)


class CHEMBLENDER_PG_import_grouping_evidence(bpy.types.PropertyGroup):
    evidence_id: StringProperty()
    source_revision_ids: StringProperty()
    kind: StringProperty()
    summary: StringProperty()
    metric: StringProperty()
    metric_unit: StringProperty()
    selected: BoolProperty(default=True)


class CHEMBLENDER_PG_import_grouping_suggestion(bpy.types.PropertyGroup):
    suggestion_id: StringProperty()
    source_count: IntProperty()
    confidence: StringProperty()
    requires_review: BoolProperty()
    grouping_action: EnumProperty(items=_GROUPING_ACTION_ITEMS)
    review_confirmed: BoolProperty(default=False)
    evidence: CollectionProperty(
        type=CHEMBLENDER_PG_import_grouping_evidence
    )


class CHEMBLENDER_PG_import_conformer_evidence(bpy.types.PropertyGroup):
    record_id: StringProperty()
    record_key: StringProperty()
    kind: StringProperty()
    atom_mapping: StringProperty()
    requires_review: BoolProperty()


class CHEMBLENDER_PG_import_conformer_suggestion(bpy.types.PropertyGroup):
    suggestion_id: StringProperty()
    record_count: IntProperty()
    requires_review: BoolProperty()
    hidden_review_count: IntProperty(default=0)
    grouping_action: EnumProperty(items=_CONFORMER_GROUPING_ACTION_ITEMS)
    review_confirmed: BoolProperty(default=False)
    evidence: CollectionProperty(
        type=CHEMBLENDER_PG_import_conformer_evidence
    )


class CHEMBLENDER_PG_import_preview_row(bpy.types.PropertyGroup):
    source_id: StringProperty()
    source_name: StringProperty()
    reader_id: StringProperty()
    reader_availability: StringProperty()
    capability_summary: StringProperty()
    frame_count: IntProperty()
    atom_property_summary: StringProperty()
    frame_property_summary: StringProperty()
    lattice_pbc_summary: StringProperty()
    assumed_unit_summary: StringProperty()
    molecular_record_count: IntProperty()
    molecular_version_summary: StringProperty()
    molecular_recovery_summary: StringProperty()
    molecular_topology_summary: StringProperty()
    molecular_property_summary: StringProperty()
    grid_dataset_count: IntProperty()
    grid_source_ids: StringProperty()
    grid_sample_range: StringProperty()
    grid_shape: StringProperty()
    grid_coordinate_unit: StringProperty()
    grid_value_unit: StringProperty()
    grid_quality: StringProperty()
    cif_block_count: IntProperty()
    cif_valid_block_count: IntProperty()
    cif_block_summary: StringProperty()
    cif_site_summary: StringProperty()
    cif_cell_summary: StringProperty()
    cif_occupancy_adp_summary: StringProperty()
    cif_declared_symmetry_summary: StringProperty()
    cif_default_block_confirmed: BoolProperty(default=False)
    poscar_comment: StringProperty()
    poscar_scale_summary: StringProperty()
    poscar_cell_summary: StringProperty()
    poscar_species_summary: StringProperty()
    poscar_coordinate_mode: StringProperty()
    poscar_selective_summary: StringProperty()
    poscar_velocity_summary: StringProperty()
    poscar_species_assignment: StringProperty()
    poscar_requires_species_assignment: BoolProperty(default=False)
    conformer_suggestion_count: IntProperty()
    quality: StringProperty()
    conflict_id: StringProperty()
    conflict_action: EnumProperty(items=_conflict_action_items)
    conflict_candidates: CollectionProperty(
        type=CHEMBLENDER_PG_import_conflict_candidate
    )
    allowed_actions: StringProperty()
    default_view: BoolProperty(default=True)
    default_view_label: StringProperty()
    blocking: BoolProperty(default=False)
    blocking_reason: StringProperty()


@dataclass(slots=True)
class ConflictCandidateProjection:
    revision_id: str
    source_id: str
    display_label: str
    created_entity_count: int
    selected: bool = False


@dataclass(slots=True)
class PreviewProjection:
    source_id: str
    source_name: str
    reader_id: str
    reader_availability: str
    capability_summary: str
    quality: str
    frame_count: int = 0
    atom_property_summary: str = ""
    frame_property_summary: str = ""
    lattice_pbc_summary: str = ""
    assumed_unit_summary: str = ""
    molecular_record_count: int = 0
    molecular_version_summary: str = ""
    molecular_recovery_summary: str = ""
    molecular_topology_summary: str = ""
    molecular_property_summary: str = ""
    grid_dataset_count: int = 0
    grid_source_ids: str = ""
    grid_sample_range: str = ""
    grid_shape: str = ""
    grid_coordinate_unit: str = ""
    grid_value_unit: str = ""
    grid_quality: str = ""
    cif_block_count: int = 0
    cif_valid_block_count: int = 0
    cif_block_summary: str = ""
    cif_site_summary: str = ""
    cif_cell_summary: str = ""
    cif_occupancy_adp_summary: str = ""
    cif_declared_symmetry_summary: str = ""
    cif_default_block_confirmed: bool = False
    poscar_comment: str = ""
    poscar_scale_summary: str = ""
    poscar_cell_summary: str = ""
    poscar_species_summary: str = ""
    poscar_coordinate_mode: str = ""
    poscar_selective_summary: str = ""
    poscar_velocity_summary: str = ""
    poscar_species_assignment: str = ""
    poscar_requires_species_assignment: bool = False
    conformer_suggestion_count: int = 0
    conflict_id: str = ""
    allowed_actions: str = ""
    conflict_action: str = DuplicateAction.INDEPENDENT_COPY.value
    conflict_candidates: tuple[ConflictCandidateProjection, ...] = ()
    default_view: bool = True
    default_view_label: str = ""
    blocking: bool = False
    blocking_reason: str = ""


@dataclass(slots=True)
class GroupingEvidenceProjection:
    evidence_id: str
    source_revision_ids: str
    kind: str
    summary: str
    metric: str
    metric_unit: str
    selected: bool = True


@dataclass(slots=True)
class GroupingSuggestionProjection:
    suggestion_id: str
    source_count: int
    confidence: str
    requires_review: bool
    grouping_action: str = "keep_independent"
    review_confirmed: bool = False
    evidence: tuple[GroupingEvidenceProjection, ...] = ()


@dataclass(slots=True)
class ConformerEvidenceProjection:
    record_id: str
    record_key: str
    kind: str
    atom_mapping: str
    requires_review: bool


@dataclass(slots=True)
class ConformerSuggestionProjection:
    suggestion_id: str
    record_count: int
    requires_review: bool
    hidden_review_count: int = 0
    grouping_action: str = "keep_independent"
    review_confirmed: bool = False
    evidence: tuple[ConformerEvidenceProjection, ...] = ()


@dataclass(frozen=True, slots=True)
class ImportUICommitResult:
    status: str
    commit_result: object
    created_view_count: int


class ImportCommitCancelled(RuntimeError):
    pass


def _owned_temporary_generation(project_session, path):
    if path is None:
        return False
    candidate = Path(path)
    try:
        root = Path(project_session.temporary_root).resolve(strict=True)
        resolved = candidate.resolve(strict=False)
    except OSError:
        return False
    is_link_like = candidate.is_symlink() or (
        hasattr(candidate, "is_junction") and candidate.is_junction()
    )
    return (
        not is_link_like
        and resolved.parent == root
        and resolved.suffix.lower() == ".cbq"
    )


def _remove_owned_temporary_generation(project_session, path):
    if not _owned_temporary_generation(project_session, path):
        return
    candidate = Path(path)
    if candidate.exists():
        shutil.rmtree(candidate)


def _restore_dirty_reasons(project_session, dirty_reasons):
    current = project_session.dirty_reasons
    for reason in current - dirty_reasons:
        project_session.clear_dirty(reason)
    for reason in dirty_reasons - current:
        project_session.mark_dirty(reason)


def _new_temporary_generation(project_session):
    root = Path(project_session.temporary_root)
    while True:
        candidate = root / f"g{uuid4().hex[:8]}.cbq"
        if not candidate.exists():
            return candidate


def _commit_to_fresh_generation(
    project_session,
    staged_session,
    preview,
    decisions,
    *,
    progress=lambda _stage, _completed, _total: None,
    is_cancelled=lambda: False,
):
    previous_path = project_session.sidecar_path
    previous_project = project_session.project
    previous_dirty = project_session.dirty_reasons
    generation = _new_temporary_generation(project_session)
    project_session.sidecar_path = generation
    try:
        result = commit_import_preview(
            project_session,
            staged_session,
            preview,
            decisions,
            progress=progress,
            is_cancelled=is_cancelled,
        )
    except BaseException as error:
        project_session.sidecar_path = previous_path
        _restore_dirty_reasons(project_session, previous_dirty)
        if project_session.project is not previous_project:
            error.add_note(
                "project changed during a failed import publication"
            )
        try:
            _remove_owned_temporary_generation(project_session, generation)
        except OSError as cleanup_error:
            error.add_note(
                f"failed import generation cleanup failed: {cleanup_error}"
            )
        raise

    if previous_path is not None and previous_path != result.sidecar_path:
        try:
            _remove_owned_temporary_generation(
                project_session,
                previous_path,
            )
        except OSError as error:
            result = replace(
                result,
                cleanup_warnings=(
                    *result.cleanup_warnings,
                    f"previous import generation cleanup failed: {error}",
                ),
            )
    return result


def _diagnostics(staging, source_preview):
    values = {}
    for batch_id in source_preview.staged_batch_ids:
        batch = staging.result(batch_id)
        values.update((value.id, value) for value in batch.diagnostics)
    return tuple(
        values[diagnostic_id]
        for diagnostic_id in source_preview.diagnostic_ids
        if diagnostic_id in values
    )


def _is_isolated_sdf_record_failure(diagnostic, valid_record_keys):
    return (
        diagnostic.code == "sdf.record_parse_failed"
        and diagnostic.field_path.startswith("record.")
        and diagnostic.recovery_action == "other SDF records were retained"
        and diagnostic.entity_id is None
        and valid_record_keys
        and diagnostic.record_key
        and diagnostic.record_key not in valid_record_keys
    )


def _quality_and_blocking(staging, source_preview):
    if len(source_preview.staged_batch_ids) != 1:
        return (
            QualityStatus.INCOMPLETE.value,
            "source has no single staged batch",
        )
    batch = staging.result(source_preview.staged_batch_ids[0])
    diagnostics = _diagnostics(staging, source_preview)
    valid_record_keys = frozenset(
        record.record_key for record in batch.molecular_records
    )
    quality = max(
        (item.quality_status for item in diagnostics),
        key=lambda item: item.summary_order,
        default=QualityStatus.COMPLETE,
    )
    blocking = next(
        (
            item
            for item in diagnostics
            if (
                item.severity is DiagnosticSeverity.ERROR
                or item.quality_status is QualityStatus.INVALID
            )
            and not _is_isolated_sdf_record_failure(
                item, valid_record_keys
            )
        ),
        None,
    )
    return (
        quality.value,
        (
            f"{blocking.code}: {blocking.message}"
            if blocking is not None
            else ""
        ),
    )


def _candidate_projection(project, candidate, *, selected):
    source = project.sources[candidate.source_id]
    revision = project.source_revisions[candidate.revision_id]
    return ConflictCandidateProjection(
        revision_id=str(candidate.revision_id),
        source_id=str(candidate.source_id),
        display_label=(
            f"{source.display_name} · {revision.original_filename} · "
            f"{str(candidate.revision_id)[:8]}"
        ),
        created_entity_count=len(candidate.created_entity_ids),
        selected=selected,
    )


def _molecular_summary(batch, conformer_count):
    records = batch.molecular_records
    if not records:
        return (0, "", "", "", "", 0)
    versions = {}
    for record in records:
        name = record.block_version or "SMILES"
        versions[name] = versions.get(name, 0) + 1
    version_summary = ", ".join(
        f"{name}: {versions[name]}" for name in sorted(versions)
    )
    recoveries = sum(
        diagnostic.code == "sdf.record_parse_failed"
        for diagnostic in batch.diagnostics
    )
    sanitized = sum(
        getattr(topology.source_kind, "value", "") == "rdkit_sanitized"
        for topology in batch.topologies
    )
    raw_fields = sum(
        len(record.ordered_raw_properties) for record in records
    )
    typed_columns = sum(
        isinstance(dataset, RecordPropertyColumn)
        for dataset in batch.datasets
    )
    return (
        len(records),
        version_summary,
        "none" if not recoveries else f"{recoveries} recovered record(s)",
        f"{sanitized} sanitized topology record(s)",
        f"{raw_fields} raw fields · {typed_columns} typed columns",
        conformer_count,
    )


def _cif_summary(batch):
    if not batch.cif_envelopes:
        return None
    envelope = batch.cif_envelopes[0]
    structures = tuple(
        structure
        for structure in batch.structures
        if (
            structure.periodic is not None
            and structure.periodic.cif_envelope_id == envelope.id
        )
    )
    sites = sum(len(structure.atomic_numbers) for structure in structures)
    cells = []
    declared = []
    missing_occupancy = 0
    partial_occupancy = 0
    u_iso = 0
    u_aniso = 0
    disorder = 0
    for structure in structures:
        import numpy

        periodic = structure.periodic
        parameters = unit_cell_parameters(structure.cell)
        cells.append(
            f"{periodic.cif_block_key}: "
            + " × ".join(format(value, ".6g") for value in parameters[:3])
            + f" {structure.cell.unit}"
        )
        occupancies = numpy.asarray(periodic.occupancies.values)
        missing_occupancy += int(numpy.count_nonzero(numpy.isnan(occupancies)))
        partial_occupancy += int(
            numpy.count_nonzero(
                numpy.isfinite(occupancies) & (occupancies < 1.0)
            )
        )
        u_iso += periodic.isotropic_displacements is not None
        u_aniso += periodic.anisotropic_displacements is not None
        disorder += sum(value != 0 for value in periodic.disorder_groups)
        source_symmetry = periodic.declared_symmetry
        if any(
            (
                source_symmetry.name,
                source_symmetry.international_number,
                source_symmetry.hall_symbol,
                source_symmetry.operations,
            )
        ):
            declared.append(
                (
                    f"{periodic.cif_block_key}: "
                    f"{source_symmetry.name or 'unnamed'}"
                    + (
                        ""
                        if source_symmetry.international_number is None
                        else f" (No. {source_symmetry.international_number})"
                    )
                )
            )
    default_key = (
        structures[0].periodic.cif_block_key if structures else "none"
    )
    return {
        "block_count": len(envelope.block_names),
        "valid_block_count": len(structures),
        "block_summary": (
            ", ".join(envelope.block_keys) + f" · default {default_key}"
        ),
        "site_summary": (
            f"{sites} sites across {len(structures)} structure(s)"
        ),
        "cell_summary": "; ".join(cells),
        "occupancy_adp_summary": (
            f"Occupancy: {missing_occupancy} missing, "
            f"{partial_occupancy} partial · "
            f"ADP: Uiso {u_iso}, Uij {u_aniso} · "
            f"Disorder: {disorder} site(s)"
        ),
        "declared_symmetry_summary": (
            "; ".join(declared) if declared else "No declared symmetry"
        ),
    }


def _poscar_summary(batch):
    import numpy

    provenance = next(
        (
            value
            for value in batch.provenance
            if value.producer == "ChemBlender POSCAR adapter"
        ),
        None,
    )
    if provenance is None:
        return None
    parameters = dict(provenance.parameters)
    species = (
        parameters.get("species_order")
        or parameters.get("species_assignment")
    )
    counts = parameters.get("counts") or ()
    assignment = parameters.get("species_assignment")
    structure = batch.structures[0] if len(batch.structures) == 1 else None
    volume = (
        None
        if structure is None
        else abs(float(numpy.linalg.det(structure.cell.values)))
    )
    velocities = []
    if parameters.get("velocity_mode") is not None:
        velocities.append("Ion velocities")
    if parameters.get("lattice_velocity_initialization_state") is not None:
        velocities.append("lattice velocities")
    scale = parameters.get("scale")
    scale_kind = (
        "target volume"
        if isinstance(scale, (int, float)) and scale < 0.0
        else "factor"
    )
    return {
        "comment": str(parameters.get("comment") or ""),
        "scale_summary": (
            ""
            if not isinstance(scale, (int, float))
            else f"{scale:g} ({scale_kind})"
        ),
        "cell_summary": (
            "Unavailable until species assignment"
            if volume is None
            else f"{volume:g} angstrom^3"
        ),
        "species_summary": (
            f"{' '.join(species) if species else 'Unassigned'}"
            f" · {' '.join(map(str, counts))}"
        ),
        "group_count": len(counts),
        "coordinate_mode": str(
            parameters.get("coordinate_mode") or ""
        ).title(),
        "selective_summary": (
            "Selective Dynamics"
            if parameters.get("selective_dynamics")
            else "No Selective Dynamics"
        ),
        "velocity_summary": (
            " · ".join(velocities) if velocities else "No velocities"
        ),
        "species_assignment": (
            "" if assignment is None else ",".join(assignment)
        ),
        "requires_species_assignment": (
            parameters.get("species_order") is None and structure is None
        ),
    }


def _prepare_poscar_species_restage(
    state,
    source_id,
    species,
    validation_mode,
):
    if type(source_id) is not UUID:
        raise TypeError("source_id must be UUID")
    if type(species) is not str:
        raise TypeError("species must be comma-separated text")
    if type(validation_mode) is not ValidationMode:
        raise TypeError("validation_mode must be ValidationMode")
    if state.active_job is not None:
        raise RuntimeError("cannot restage while an import job is active")
    preview = state.preview
    old_staging = state.staging_session
    if preview is None or old_staging is None:
        raise RuntimeError("no staged Import Preview")
    target = next(
        (
            value
            for value in preview.source_previews
            if value.source_id == source_id
        ),
        None,
    )
    if target is None or target.selected_reader_id != "poscar":
        raise ValueError("source is not a staged POSCAR")
    normalized = ",".join(
        value.strip() for value in species.split(",") if value.strip()
    )
    if not normalized:
        raise ValueError("enter ordered POSCAR species")
    current_batch = old_staging.result(target.staged_batch_ids[0])
    summary = _poscar_summary(current_batch)
    if (
        summary is None
        or len(normalized.split(",")) != summary["group_count"]
    ):
        raise ValueError(
            "species assignment must match the POSCAR count groups"
        )

    request = ImportRequest(
        sources=(ImportSource(path=target.source_path, id=source_id),),
        validation_mode=validation_mode,
        reader_overrides=(ReaderOverride(source_id, "poscar"),),
    )
    return (
        request,
        {source_id: {"species": normalized}},
    )


def _apply_poscar_species_restage(state, source_id, target_result):
    preview = state.preview
    staging = state.staging_session
    if preview is None or staging is None:
        raise RuntimeError("no staged Import Preview")
    target_preview, = target_result.source_previews
    if target_preview.source_id != source_id:
        raise ValueError("POSCAR restage returned the wrong source")
    batch = staging.result(target_preview.staged_batch_ids[0])
    if len(batch.structures) != 1:
        message = next(
            (
                diagnostic.message
                for diagnostic in batch.diagnostics
                if diagnostic.source_revision_id
                in {
                    value.id for value in batch.source_revisions
                }
            ),
            "POSCAR species assignment did not produce a Structure",
        )
        raise ValueError(message)
    source_previews = tuple(
        target_preview if value.source_id == source_id else value
        for value in preview.source_previews
    )
    refreshed = ImportPreview(
        session_id=staging.id,
        source_previews=source_previews,
        staged_batch_ids=tuple(
            result_id
            for value in source_previews
            for result_id in value.staged_batch_ids
        ),
        diagnostic_ids=tuple(
            diagnostic_id
            for value in source_previews
            for diagnostic_id in value.diagnostic_ids
        ),
    )
    state.preview = refreshed
    state.conflicts = ()
    state.grouping_suggestions = ()
    return refreshed


def restage_poscar_species_assignment(
    project_session,
    state,
    source_id,
    species,
    registry,
    validation_mode,
    *,
    progress=None,
    is_cancelled=None,
):
    request, canonical_parameters = _prepare_poscar_species_restage(
        state,
        source_id,
        species,
        validation_mode,
    )
    target_result = preflight_reader_plugins(
        request,
        registry,
        state.staging_session,
        canonical_parameters_by_source=canonical_parameters,
        progress=progress,
        is_cancelled=is_cancelled,
    )
    return _apply_poscar_species_restage(state, source_id, target_result)


def project_import_preview(project_session, state, registry):
    """Refresh live conflicts and return a small RNA-safe row projection."""
    preview = state.preview
    staging = state.staging_session
    if preview is None or staging is None:
        raise RuntimeError("no staged Import Preview")
    ready = all(
        len(source.staged_batch_ids) == 1
        for source in preview.source_previews
    )
    conflicts = (
        detect_import_conflicts(project_session.project, preview, staging)
        if ready
        else ()
    )
    grouping_suggestions = (
        suggest_source_groups(preview, staging) if ready else ()
    )
    conformer_suggestions = state.conformer_grouping_suggestions
    if not ready or conformer_suggestions is None:
        conformer_suggestions = ()
    preview = replace(
        preview,
        conflict_ids=tuple(conflict.id for conflict in conflicts),
        grouping_suggestion_ids=tuple(
            suggestion.id for suggestion in grouping_suggestions
        ),
    )
    state.preview = preview
    state.conflicts = conflicts
    state.grouping_suggestions = grouping_suggestions
    state.conformer_grouping_suggestions = conformer_suggestions
    conflicts_by_source = {
        conflict.staged_source_id: conflict for conflict in conflicts
    }
    descriptors = {
        descriptor.reader_id: descriptor
        for descriptor in registry.descriptors
    }
    rows = []
    for source in preview.source_previews:
        descriptor = descriptors.get(source.selected_reader_id)
        availability = (
            descriptor.availability.reason_code
            if descriptor is not None
            else "reader unavailable"
        )
        quality, blocking_reason = _quality_and_blocking(staging, source)
        conflict = conflicts_by_source.get(source.source_id)
        default_view_plan = None
        extxyz_summary = None
        grid_summary = None
        cif_summary = None
        poscar_summary = None
        molecular_summary = (0, "", "", "", "", 0)
        if len(source.staged_batch_ids) == 1:
            batch = staging.result(source.staged_batch_ids[0])
            grid_summary = grid_preview_summary(batch)
            if source.selected_reader_id == "cif":
                cif_summary = _cif_summary(batch)
            if source.selected_reader_id == "poscar":
                poscar_summary = _poscar_summary(batch)
                if (
                    poscar_summary is not None
                    and poscar_summary["requires_species_assignment"]
                ):
                    blocking_reason = (
                        "VASP 4 count groups require an ordered species "
                        "assignment"
                    )
            if source.selected_reader_id == "extxyz":
                extxyz_summary = extxyz_preview_summary(batch)
            batch_record_ids = {
                record.id for record in batch.molecular_records
            }
            source_suggestion_count = sum(
                set(suggestion.record_ids).issubset(
                    batch_record_ids
                )
                for suggestion in conformer_suggestions
            )
            molecular_summary = _molecular_summary(
                batch,
                source_suggestion_count,
            )
            revision = next(
                (
                    value
                    for value in batch.source_revisions
                    if value.source_id == source.source_id
                ),
                None,
            )
            if revision is not None:
                default_view_plan = plan_default_view(
                    revision,
                    {value.id: value for value in batch.structures},
                    {value.id: value for value in batch.datasets},
                )
        rows.append(
            PreviewProjection(
                source_id=str(source.source_id),
                source_name=source.source_path.name,
                reader_id=source.selected_reader_id or "unresolved",
                reader_availability=availability,
                capability_summary=", ".join(source.capabilities) or "none",
                quality=quality,
                frame_count=(
                    0 if extxyz_summary is None else extxyz_summary.frame_count
                ),
                atom_property_summary=(
                    ""
                    if extxyz_summary is None
                    else ", ".join(extxyz_summary.atom_properties) or "none"
                ),
                frame_property_summary=(
                    ""
                    if extxyz_summary is None
                    else ", ".join(extxyz_summary.frame_properties) or "none"
                ),
                lattice_pbc_summary=(
                    ""
                    if extxyz_summary is None
                    else (
                        f"Lattice: {'yes' if extxyz_summary.has_lattice else 'no'}"
                        " · PBC: "
                        + (
                            "none"
                            if extxyz_summary.pbc is None
                            else " ".join(
                                "T" if value else "F"
                                for value in extxyz_summary.pbc
                            )
                            + (
                                " (varies)"
                                if extxyz_summary.pbc_changes
                                else ""
                            )
                        )
                    )
                ),
                assumed_unit_summary=(
                    ""
                    if extxyz_summary is None
                    else "; ".join(extxyz_summary.assumed_units)
                ),
                molecular_record_count=molecular_summary[0],
                molecular_version_summary=molecular_summary[1],
                molecular_recovery_summary=molecular_summary[2],
                molecular_topology_summary=molecular_summary[3],
                molecular_property_summary=molecular_summary[4],
                grid_dataset_count=(
                    0 if grid_summary is None else grid_summary.dataset_count
                ),
                grid_source_ids=(
                    ""
                    if grid_summary is None
                    else ", ".join(grid_summary.source_dataset_ids)
                ),
                grid_sample_range=(
                    ""
                    if grid_summary is None
                    else "; ".join(
                        f"{low:g}..{high:g}"
                        for low, high in grid_summary.sample_ranges
                    )
                ),
                grid_shape=(
                    ""
                    if grid_summary is None
                    else " × ".join(map(str, grid_summary.grid_shape))
                ),
                grid_coordinate_unit=(
                    ""
                    if grid_summary is None
                    else grid_summary.coordinate_unit
                ),
                grid_value_unit=(
                    "" if grid_summary is None else grid_summary.value_unit
                ),
                grid_quality=(
                    "" if grid_summary is None else grid_summary.quality
                ),
                cif_block_count=(
                    0 if cif_summary is None else cif_summary["block_count"]
                ),
                cif_valid_block_count=(
                    0
                    if cif_summary is None
                    else cif_summary["valid_block_count"]
                ),
                cif_block_summary=(
                    "" if cif_summary is None else cif_summary["block_summary"]
                ),
                cif_site_summary=(
                    "" if cif_summary is None else cif_summary["site_summary"]
                ),
                cif_cell_summary=(
                    "" if cif_summary is None else cif_summary["cell_summary"]
                ),
                cif_occupancy_adp_summary=(
                    ""
                    if cif_summary is None
                    else cif_summary["occupancy_adp_summary"]
                ),
                cif_declared_symmetry_summary=(
                    ""
                    if cif_summary is None
                    else cif_summary["declared_symmetry_summary"]
                ),
                poscar_comment=(
                    ""
                    if poscar_summary is None
                    else _rna_preview_text(poscar_summary["comment"])
                ),
                poscar_scale_summary=(
                    ""
                    if poscar_summary is None
                    else _rna_preview_text(poscar_summary["scale_summary"])
                ),
                poscar_cell_summary=(
                    ""
                    if poscar_summary is None
                    else _rna_preview_text(poscar_summary["cell_summary"])
                ),
                poscar_species_summary=(
                    ""
                    if poscar_summary is None
                    else _rna_preview_text(poscar_summary["species_summary"])
                ),
                poscar_coordinate_mode=(
                    ""
                    if poscar_summary is None
                    else _rna_preview_text(poscar_summary["coordinate_mode"])
                ),
                poscar_selective_summary=(
                    ""
                    if poscar_summary is None
                    else _rna_preview_text(poscar_summary["selective_summary"])
                ),
                poscar_velocity_summary=(
                    ""
                    if poscar_summary is None
                    else _rna_preview_text(poscar_summary["velocity_summary"])
                ),
                poscar_species_assignment=(
                    ""
                    if poscar_summary is None
                    else _rna_preview_text(
                        poscar_summary["species_assignment"]
                    )
                ),
                poscar_requires_species_assignment=(
                    False
                    if poscar_summary is None
                    else poscar_summary["requires_species_assignment"]
                ),
                conformer_suggestion_count=molecular_summary[5],
                conflict_id=str(conflict.id) if conflict else "",
                conflict_action=(
                    conflict.default_action.value
                    if conflict
                    else DuplicateAction.INDEPENDENT_COPY.value
                ),
                conflict_candidates=(
                    tuple(
                        _candidate_projection(
                            project_session.project,
                            candidate,
                            selected=(
                                len(conflict.candidates) == 1
                                and conflict.default_action in _TARGET_ACTIONS
                            ),
                        )
                        for candidate in conflict.candidates
                    )
                    if conflict
                    else ()
                ),
                allowed_actions=(
                    ",".join(action.value for action in conflict.allowed_actions)
                    if conflict
                    else ""
                ),
                default_view=True,
                default_view_label=describe_default_view(
                    default_view_plan
                ),
                blocking=bool(blocking_reason),
                blocking_reason=blocking_reason,
            )
        )
    return tuple(rows)


def project_grouping_suggestions(state):
    return tuple(
        GroupingSuggestionProjection(
            suggestion_id=str(suggestion.id),
            source_count=len(suggestion.source_revision_ids),
            confidence=suggestion.confidence,
            requires_review=suggestion.requires_review,
            evidence=tuple(
                GroupingEvidenceProjection(
                    evidence_id=str(item.id),
                    source_revision_ids=",".join(
                        map(str, item.source_revision_ids)
                    ),
                    kind=item.kind,
                    summary=item.summary,
                    metric=(
                        ""
                        if item.metric is None
                        else format(item.metric, ".12g")
                    ),
                    metric_unit=item.metric_unit or "",
                )
                for item in suggestion.evidence
            ),
        )
        for suggestion in state.grouping_suggestions
    )


def _conformer_projection(suggestion):
    if len(suggestion.evidence) != len(suggestion.record_keys):
        raise ValueError("conformer evidence and record keys must align")
    review_evidence = []
    other_evidence = []
    review_count = 0
    for index, item in enumerate(suggestion.evidence):
        pair = (item, suggestion.record_keys[index])
        if item.requires_review:
            review_count += 1
            if len(review_evidence) < _CONFORMER_EVIDENCE_PREVIEW_LIMIT:
                review_evidence.append(pair)
        elif len(other_evidence) < _CONFORMER_EVIDENCE_PREVIEW_LIMIT:
            other_evidence.append(pair)
    visible_evidence = (
        review_evidence + other_evidence
    )[:_CONFORMER_EVIDENCE_PREVIEW_LIMIT]
    return ConformerSuggestionProjection(
        suggestion_id=str(suggestion.id),
        record_count=len(suggestion.record_ids),
        requires_review=suggestion.requires_review,
        hidden_review_count=review_count - len(review_evidence),
        evidence=tuple(
            ConformerEvidenceProjection(
                record_id=str(item.record_id),
                record_key=record_key,
                kind=item.kind,
                atom_mapping=_atom_mapping_summary(item.atom_mapping),
                requires_review=item.requires_review,
            )
            for item, record_key in visible_evidence
        ),
    )


def _atom_mapping_summary(atom_mapping):
    visible = ",".join(map(str, atom_mapping[:12]))
    if len(atom_mapping) <= 12:
        return visible
    digest = sha256()
    for value in atom_mapping:
        digest.update(str(value).encode("ascii"))
        digest.update(b",")
    return (
        f"{visible},... ({len(atom_mapping)} atoms; "
        f"sha256:{digest.hexdigest()[:12]})"
    )


def project_conformer_suggestions(state):
    return tuple(
        _conformer_projection(suggestion)
        for suggestion in (state.conformer_grouping_suggestions or ())
    )


def _source_rows(preview, rows):
    rows = tuple(rows)
    by_source = {}
    for row in rows:
        source_id = UUID(row.source_id)
        if source_id in by_source:
            raise ValueError("preview rows must have unique source IDs")
        by_source[source_id] = row
    expected = {source.source_id for source in preview.source_previews}
    if set(by_source) != expected:
        raise ValueError("preview rows do not match staged sources")
    return by_source


def _grouping_decisions(
    state,
    grouping_rows,
    *,
    project_session,
):
    preview = state.preview
    staging = state.staging_session
    suggestions = state.grouping_suggestions
    if preview.grouping_suggestion_ids != tuple(
        suggestion.id for suggestion in suggestions
    ):
        raise ValueError("grouping suggestions do not match Import Preview")
    if project_session is not None:
        live = suggest_source_groups(preview, staging)
        if live != suggestions:
            raise ValueError(
                "grouping suggestions changed; refresh Import Preview"
            )
    if grouping_rows is None:
        grouping_rows = project_grouping_suggestions(state)
    grouping_rows = tuple(grouping_rows)
    by_id = {}
    for row in grouping_rows:
        suggestion_id = UUID(row.suggestion_id)
        if suggestion_id in by_id:
            raise ValueError("grouping suggestion rows must be unique")
        by_id[suggestion_id] = row
    live_by_id = {
        suggestion.id: suggestion for suggestion in suggestions
    }
    if set(by_id) != set(live_by_id):
        raise ValueError(
            "grouping suggestion rows do not match Import Preview"
        )
    decisions = []
    for suggestion_id, row in by_id.items():
        suggestion = live_by_id[suggestion_id]
        if row.grouping_action == "keep_independent":
            continue
        if row.grouping_action != "accept_group":
            raise ValueError("Split/Edit grouping is unavailable in alpha.1")
        if suggestion.requires_review and not row.review_confirmed:
            raise ValueError("grouping review requires explicit confirmation")
        evidence_rows = tuple(row.evidence)
        evidence_ids = tuple(UUID(item.evidence_id) for item in evidence_rows)
        if len(evidence_ids) != len(set(evidence_ids)) or set(
            evidence_ids
        ) != set(suggestion.evidence_ids):
            raise ValueError(
                "grouping evidence does not match Import Preview"
            )
        selected_ids = tuple(
            UUID(item.evidence_id)
            for item in evidence_rows
            if item.selected
        )
        suggestion.confirm(selected_ids)
        decisions.append(
            GroupingDecision(
                suggestion=suggestion,
                evidence_ids=selected_ids,
            )
        )
    return tuple(decisions)


def _conformer_grouping_decisions(
    state,
    conformer_rows,
):
    suggestions = state.conformer_grouping_suggestions or ()
    if conformer_rows is None:
        conformer_rows = project_conformer_suggestions(state)
    conformer_rows = tuple(conformer_rows)
    by_id = {}
    for row in conformer_rows:
        suggestion_id = UUID(row.suggestion_id)
        if suggestion_id in by_id:
            raise ValueError("conformer grouping suggestion rows must be unique")
        by_id[suggestion_id] = row
    live_by_id = {
        suggestion.id: suggestion for suggestion in suggestions
    }
    if set(by_id) != set(live_by_id):
        raise ValueError(
            "conformer grouping rows do not match Import Preview"
        )
    decisions = []
    for suggestion_id, row in by_id.items():
        suggestion = live_by_id[suggestion_id]
        expected = _conformer_projection(suggestion)
        evidence = tuple(row.evidence)
        if tuple(
            (
                item.record_id,
                item.record_key,
                item.kind,
                item.atom_mapping,
                item.requires_review,
            )
            for item in evidence
        ) != tuple(
            (
                item.record_id,
                item.record_key,
                item.kind,
                item.atom_mapping,
                item.requires_review,
            )
            for item in expected.evidence
        ):
            raise ValueError(
                "conformer grouping evidence does not match Import Preview"
            )
        if row.hidden_review_count != expected.hidden_review_count:
            raise ValueError(
                "conformer grouping review count does not match Import Preview"
            )
        if row.grouping_action == "keep_independent":
            continue
        if row.grouping_action != "accept_group":
            raise ValueError("unsupported conformer grouping action")
        if expected.hidden_review_count:
            raise ValueError(
                "conformer grouping has hidden review evidence; "
                "keep records independent"
            )
        if suggestion.requires_review and not row.review_confirmed:
            raise ValueError(
                "conformer grouping review requires explicit confirmation"
            )
        decisions.append(
            ConformerGroupingDecision(
                suggestion,
                review_confirmed=row.review_confirmed,
            )
        )
    return tuple(decisions)


def import_commit_decisions(
    state,
    rows,
    *,
    grouping_rows=None,
    conformer_rows=None,
    project_session=None,
):
    preview = state.preview
    staging = state.staging_session
    if preview is None or staging is None:
        raise RuntimeError("no staged Import Preview")
    by_source = _source_rows(preview, rows)
    for source in preview.source_previews:
        _quality, blocking_reason = _quality_and_blocking(staging, source)
        if blocking_reason:
            raise ValueError(blocking_reason)
        if source.selected_reader_id == "cif":
            batch = staging.result(source.staged_batch_ids[0])
            summary = _cif_summary(batch)
            row = by_source[source.source_id]
            expected = (
                summary["block_count"],
                summary["valid_block_count"],
            )
            if (
                row.cif_block_count,
                row.cif_valid_block_count,
            ) != expected:
                raise ValueError(
                    "CIF block summary changed; refresh Import Preview"
                )
            if (
                summary["valid_block_count"] > 1
                and not row.cif_default_block_confirmed
            ):
                raise ValueError(
                    "CIF default block requires explicit confirmation"
                )
    conflicts = state.conflicts
    if project_session is not None:
        live = detect_import_conflicts(
            project_session.project,
            preview,
            staging,
        )
        if live != conflicts:
            raise ValueError("conflicts changed; refresh Import Preview")
    decisions = {}
    conflicts_by_source = {
        conflict.staged_source_id: conflict for conflict in conflicts
    }
    for source_id, row in by_source.items():
        conflict = conflicts_by_source.get(source_id)
        if conflict is None:
            if row.conflict_id:
                raise ValueError("unexpected conflict ID")
            continue
        if row.conflict_id != str(conflict.id):
            raise ValueError("conflict ID does not match the live conflict")
        action = DuplicateAction(row.conflict_action)
        if action not in conflict.allowed_actions:
            raise ValueError("conflict action is not allowed")
        if action in _TARGET_ACTIONS:
            selected = tuple(
                candidate
                for candidate in row.conflict_candidates
                if candidate.selected
            )
            if len(selected) != 1:
                raise ValueError("select exactly one conflict target")
            try:
                target_id = UUID(selected[0].revision_id)
            except (AttributeError, TypeError, ValueError) as error:
                raise ValueError(
                    "conflict target is not allowed"
                ) from error
            if target_id not in conflict.existing_revision_ids:
                raise ValueError("conflict target is not allowed")
            decisions[conflict.id] = ConflictDecision(action, target_id)
        else:
            decisions[conflict.id] = action
    return ImportCommitDecisions(
        conflicts=conflicts,
        conflict_decisions=decisions,
        grouping_decisions=_grouping_decisions(
            state,
            grouping_rows,
            project_session=project_session,
        ),
        conformer_grouping_decisions=_conformer_grouping_decisions(
            state,
            conformer_rows,
        ),
    )


def _committed_default_view_plans(commit_result, rows):
    committing_rows = tuple(
        row
        for row in rows
        if not row.conflict_id
        or DuplicateAction(row.conflict_action) not in _SKIP_ACTIONS
    )
    if len(committing_rows) != len(
        commit_result.committed_source_revision_ids
    ):
        raise RuntimeError("committed source revisions do not match preview")
    selected = []
    project = commit_result.project
    for row, revision_id in zip(
        committing_rows,
        commit_result.committed_source_revision_ids,
        strict=True,
    ):
        if not row.default_view:
            continue
        revision = project.source_revisions[revision_id]
        plan = plan_default_view(
            revision,
            project.structures,
            project.datasets,
        )
        if plan is not None:
            selected.append(plan)
    return tuple(selected)


def _finish_committed_import(
    project_session,
    state,
    rows,
    commit_result,
    *,
    collection,
    apply_view,
    discard_staging=True,
):
    state.browser_revision += 1
    created = []
    cleanup_pending = bool(commit_result.cleanup_warnings)
    view_failed = False
    try:
        presets = builtin_scene_presets()
        for default_view in _committed_default_view_plans(
            commit_result,
            rows,
        ):
            preset = presets[default_view.preset_id]
            plan = plan_scene_preset(
                preset,
                commit_result.project,
                dict(default_view.bindings),
                dict(default_view.settings),
            )
            apply_keywords = {"collection": collection}
            if default_view.preset_id != "structure_publication":
                cache_root = (
                    Path(project_session.temporary_root) / "view-cache"
                )
                cache_root.mkdir(exist_ok=True)
                apply_keywords["cache_root"] = cache_root
            created.extend(
                apply_view(
                    plan,
                    commit_result.project,
                    **apply_keywords,
                )
            )
    except BaseException as error:
        try:
            _remove_scene_preset_objects(created)
        except BaseException as cleanup_error:
            error = _merge_cleanup_failure(
                error,
                cleanup_error,
                "default view cleanup failed",
            )
        created.clear()
        if isinstance(error, _FATAL_EXCEPTIONS):
            raise error
        view_failed = True
    if discard_staging:
        try:
            discard_quick_import_preview(project_session)
        except BaseException as error:
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise error
            cleanup_pending = True
    else:
        state.preview = None
        state.conflicts = ()
        state.grouping_suggestions = ()
        state.conformer_grouping_suggestions = ()
    status_parts = []
    if view_failed:
        status_parts.append("view failed")
    if cleanup_pending:
        status_parts.append("cleanup pending")
    status = (
        f"data committed; {'; '.join(status_parts)}"
        if status_parts
        else "committed"
    )
    return ImportUICommitResult(status, commit_result, len(created))


def commit_project_import(
    project_session,
    state,
    rows,
    *,
    grouping_rows=None,
    conformer_rows=None,
    collection,
    apply_view=None,
):
    """Synchronous background/smoke boundary; Blender views stay on caller."""
    if apply_view is None:
        apply_view = apply_scene_preset
    rows = tuple(rows)
    decisions = import_commit_decisions(
        state,
        rows,
        grouping_rows=grouping_rows,
        conformer_rows=conformer_rows,
        project_session=project_session,
    )
    result = _commit_to_fresh_generation(
        project_session,
        state.staging_session,
        state.preview,
        decisions,
    )
    return _finish_committed_import(
        project_session,
        state,
        rows,
        result,
        collection=collection,
        apply_view=apply_view,
    )


def cancel_project_import(project_session):
    discard_quick_import_preview(project_session)


def _commit_report_level(status):
    return {"WARNING"} if status.startswith("data committed;") else {"INFO"}


def _with_cleanup_pending(result):
    if "cleanup pending" in result.status:
        return result
    status = (
        "data committed; cleanup pending"
        if result.status == "committed"
        else f"{result.status}; cleanup pending"
    )
    return replace(result, status=status)


def _add_cleanup_note(error, label, cleanup_error):
    error.add_note(f"{label}: {cleanup_error}")
    for note in getattr(cleanup_error, "__notes__", ()):
        error.add_note(f"{label}: {note}")


def _error_report(error):
    return "\n".join((str(error), *getattr(error, "__notes__", ())))


class _CommitJob:
    """Own a pure commit until completion so session teardown cannot race it."""

    def __init__(self, project_session, staging, preview, decisions):
        self.project_session = project_session
        self.staging = staging
        self.preview = preview
        self.decisions = decisions
        self.result = None
        self.error = None
        self.progress_events = SimpleQueue()
        self._cancelled = Event()
        self._commit_started = Event()
        self._done = Event()
        self._started = False
        self._thread = Thread(target=self._run, daemon=True)
        self._window_manager = None
        self._timer = None
        self._progress_started = False

    @property
    def done(self):
        return self._done.is_set()

    @property
    def commit_started(self):
        return self._commit_started.is_set()

    @property
    def timer_pending(self):
        return self._timer is not None

    def _run(self):
        try:
            if self._cancelled.is_set():
                raise ImportCommitCancelled("import commit cancelled")
            self._commit_started.set()
            if self._cancelled.is_set():
                raise ImportCommitCancelled("import commit cancelled")
            self.result = _commit_to_fresh_generation(
                self.project_session,
                self.staging,
                self.preview,
                self.decisions,
                progress=self._progress,
                is_cancelled=self._cancelled.is_set,
            )
        except BaseException as error:
            self.error = error
        finally:
            self._done.set()

    def start(self):
        self._thread.start()
        self._started = True

    def cancel(self):
        self._cancelled.set()

    def _progress(self, stage, completed, total):
        self.progress_events.put((stage, completed, total))

    def drain_progress(self):
        latest = None
        while True:
            try:
                latest = self.progress_events.get_nowait()
            except Empty:
                return latest

    def join(self, timeout):
        if not self._started:
            return True
        self._thread.join(timeout)
        if self._thread.is_alive() and self._commit_started.is_set():
            self._thread.join()
        return not self._thread.is_alive()

    def attach_ui(self, manager, timer):
        self._window_manager = manager
        self._timer = timer

    def mark_progress_started(self):
        self._progress_started = True

    def release_ui(self):
        manager = self._window_manager
        if manager is None:
            return
        failure = None
        if self._progress_started:
            try:
                manager.progress_end()
            except BaseException as error:
                failure = error
            else:
                self._progress_started = False
        if self._timer is not None:
            try:
                manager.event_timer_remove(self._timer)
            except BaseException as error:
                failure = _merge_cleanup_failure(
                    failure,
                    error,
                    "timer cleanup failed",
                )
            else:
                self._timer = None
        if self._timer is None and not self._progress_started:
            self._window_manager = None
        if failure is not None:
            raise failure

    def abandon_ui(self):
        self._timer = None
        self._progress_started = False
        self._window_manager = None


def _copy_projections(collection, projected):
    if collection is None:
        return projected
    collection.clear()
    for projection in projected:
        item = collection.add()
        for field in fields(projection):
            value = getattr(projection, field.name)
            if type(value) is tuple and (
                not value or all(is_dataclass(member) for member in value)
            ):
                nested = getattr(item, field.name, None)
                copied = _copy_projections(nested, value)
                if nested is None:
                    setattr(item, field.name, copied)
            else:
                setattr(item, field.name, value)
    return collection


def _projection_value(cls, value, nested=()):
    nested = dict(nested)
    return cls(
        **{
            field.name: (
                tuple(
                    _projection_value(nested[field.name], member)
                    for member in getattr(value, field.name)
                )
                if field.name in nested
                else getattr(value, field.name)
            )
            for field in fields(cls)
        }
    )


def _row_values(rows):
    return tuple(
        _projection_value(
            PreviewProjection,
            row,
            (("conflict_candidates", ConflictCandidateProjection),),
        )
        for row in rows
    )


def _grouping_values(rows):
    return tuple(
        _projection_value(
            GroupingSuggestionProjection,
            row,
            (("evidence", GroupingEvidenceProjection),),
        )
        for row in rows
    )


def _conformer_values(rows):
    return tuple(
        _projection_value(
            ConformerSuggestionProjection,
            row,
            (("evidence", ConformerEvidenceProjection),),
        )
        for row in rows
    )


class CHEMBLENDER_OT_apply_poscar_species(bpy.types.Operator):
    bl_idname = "chemblender.apply_poscar_species"
    bl_label = "Apply POSCAR Species"
    bl_description = "Reparse a VASP 4 file with the ordered element assignment"

    source_id: StringProperty(options={"HIDDEN"})
    species: StringProperty(name="Species")

    def execute(self, context):
        job = None
        try:
            session = get_scene_session(context.scene)
            state = get_quick_import_state(session)
            source_id = UUID(self.source_id)
            validation_mode = ValidationMode(
                context.scene.chemblender_quick_import.validation_mode
            )
            registry = get_reader_plugin_registry()
            if getattr(bpy.app, "background", False):
                restage_poscar_species_assignment(
                    session,
                    state,
                    source_id,
                    self.species,
                    registry,
                    validation_mode,
                )
                self.report({"INFO"}, "POSCAR species applied; reopen Review")
                return {"FINISHED"}
            request, canonical_parameters = _prepare_poscar_species_restage(
                state,
                source_id,
                self.species,
                validation_mode,
            )
            job = _new_preflight_job(
                request,
                registry,
                state.staging_session,
                canonical_parameters_by_source=canonical_parameters,
                prepare_conformers=False,
            )
            store_quick_import_job(session, state.staging_session, job)
            manager = context.window_manager
            timer = manager.event_timer_add(0.1, window=context.window)
            job.attach_ui(manager, timer)
            manager.progress_begin(0, 100)
            job.mark_progress_started()
            manager.modal_handler_add(self)
            self._session = session
            self._state = state
            self._source_id = source_id
            self._job = job
            job.start()
        except BaseException as error:
            if job is not None:
                try:
                    job.release_ui()
                except BaseException as cleanup_error:
                    error = _merge_cleanup_failure(
                        error,
                        cleanup_error,
                        "POSCAR restage UI cleanup failed",
                    )
                if state.active_job is job:
                    try:
                        finish_quick_import_job(session, job)
                    except BaseException as cleanup_error:
                        error = _merge_cleanup_failure(
                            error,
                            cleanup_error,
                            "POSCAR restage ownership cleanup failed",
                        )
            return self._report_error(error)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        job = getattr(self, "_job", None)
        if job is None:
            return {"CANCELLED"}
        if event.type == "ESC":
            job.cancel()
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}
        if not getattr(job, "_completion_checked", False):
            completion_error = None
            try:
                progress = job.drain_progress()
                if progress is not None:
                    _stage, completed, total = progress
                    context.window_manager.progress_update(
                        100 * completed / total if total else 0
                    )
                if not job.done:
                    return {"RUNNING_MODAL"}
                job.join(0)
            except BaseException as error:
                completion_error = error
                job.cancel()
                try:
                    job.join(None)
                except BaseException as cleanup_error:
                    completion_error = _merge_cleanup_failure(
                        completion_error,
                        cleanup_error,
                        "POSCAR restage job cleanup failed",
                    )
            job._completion_error = completion_error
            job._completion_checked = True
        failure = job._completion_error
        if failure is None:
            failure = job.error
        try:
            job.release_ui()
        except BaseException as error:
            if (
                not isinstance(error, _FATAL_EXCEPTIONS)
                and job.timer_pending
            ):
                self.report(
                    {"WARNING"},
                    f"POSCAR restage cleanup retry pending: {error}",
                )
                return {"RUNNING_MODAL"}
            job.abandon_ui()
            failure = (
                error
                if failure is None
                else _merge_cleanup_failure(
                    failure,
                    error,
                    "POSCAR restage UI cleanup failed",
                )
            )
        try:
            finish_quick_import_job(self._session, job)
        except BaseException as error:
            failure = (
                error
                if failure is None
                else _merge_cleanup_failure(
                    failure,
                    error,
                    "POSCAR restage ownership cleanup failed",
                )
            )
        self._job = None
        if failure is not None:
            return self._report_error(failure)
        try:
            _apply_poscar_species_restage(
                self._state,
                self._source_id,
                job.preview,
            )
        except BaseException as error:
            return self._report_error(error)
        self.report({"INFO"}, "POSCAR species applied; reopen Review")
        return {"FINISHED"}

    def cancel(self, _context):
        job = getattr(self, "_job", None)
        if job is not None:
            job.cancel()

    def _report_error(self, error):
        if isinstance(error, _FATAL_EXCEPTIONS):
            raise error
        self.report({"ERROR"}, str(error))
        return {"CANCELLED"}


class CHEMBLENDER_OT_confirm_import(bpy.types.Operator):
    bl_idname = "chemblender.confirm_import"
    bl_label = "Import Preview"
    bl_description = "Review and commit staged scientific files"

    rows: CollectionProperty(type=CHEMBLENDER_PG_import_preview_row)
    grouping_suggestions: CollectionProperty(
        type=CHEMBLENDER_PG_import_grouping_suggestion
    )
    conformer_grouping_suggestions: CollectionProperty(
        type=CHEMBLENDER_PG_import_conformer_suggestion
    )
    blocking_reason: StringProperty()

    def _project(self, context):
        session = get_scene_session(context.scene)
        state = get_quick_import_state(session)
        projected = project_import_preview(
            session,
            state,
            get_reader_plugin_registry(),
        )
        _copy_projections(self.rows, projected)
        grouping_suggestions = project_grouping_suggestions(state)
        collection = getattr(self, "grouping_suggestions", None)
        copied = _copy_projections(collection, grouping_suggestions)
        if collection is None:
            self.grouping_suggestions = copied
        conformer_suggestions = project_conformer_suggestions(state)
        collection = getattr(
            self,
            "conformer_grouping_suggestions",
            None,
        )
        copied = _copy_projections(collection, conformer_suggestions)
        if collection is None:
            self.conformer_grouping_suggestions = copied
        self.blocking_reason = next(
            (row.blocking_reason for row in projected if row.blocking),
            "",
        )
        self._project_session = session
        return session, state

    def invoke(self, context, _event):
        try:
            self._project(context)
        except BaseException as error:
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=720)

    def draw(self, _context):
        layout = self.layout
        if self.blocking_reason:
            layout.label(text=self.blocking_reason, icon="ERROR")
        for row in self.rows:
            box = layout.box()
            box.label(text=row.source_name)
            box.label(
                text=f"{row.reader_id}: {row.reader_availability}"
            )
            box.label(text=f"Capabilities: {row.capability_summary}")
            box.label(text=f"Quality: {row.quality}")
            if row.frame_count:
                box.label(text=f"Frames: {row.frame_count}")
                box.label(
                    text=f"Atom properties: {row.atom_property_summary}"
                )
                box.label(
                    text=f"Frame properties: {row.frame_property_summary}"
                )
                box.label(text=row.lattice_pbc_summary)
                if row.assumed_unit_summary:
                    box.label(
                        text=f"Assumed units: {row.assumed_unit_summary}",
                        icon="ERROR",
                    )
            if row.molecular_record_count:
                box.label(
                    text=f"Records: {row.molecular_record_count} · "
                    f"{row.molecular_version_summary}"
                )
                box.label(text=f"Recovery: {row.molecular_recovery_summary}")
                box.label(text=row.molecular_topology_summary)
                box.label(text=row.molecular_property_summary)
                box.label(
                    text=(
                        f"Conformer suggestions: "
                        f"{row.conformer_suggestion_count}"
                    )
                )
            if row.grid_dataset_count:
                box.label(
                    text=(
                        f"Grid: {row.grid_shape} {row.grid_coordinate_unit} · "
                        f"{row.grid_dataset_count} dataset(s)"
                    )
                )
                box.label(text=f"Dataset IDs: {row.grid_source_ids}")
                box.label(text=f"Sample range: {row.grid_sample_range}")
                box.label(
                    text=(
                        f"Value unit: {row.grid_value_unit} · "
                        f"{row.grid_quality}"
                    ),
                    icon="ERROR" if row.grid_quality == "ambiguous" else "INFO",
                )
            if row.cif_block_count:
                box.label(
                    text=(
                        f"CIF blocks: {row.cif_block_count} · "
                        f"importable: {row.cif_valid_block_count}"
                    )
                )
                box.label(text=row.cif_block_summary)
                box.label(text=row.cif_site_summary)
                box.label(text=row.cif_cell_summary)
                box.label(text=row.cif_occupancy_adp_summary)
                box.label(text=row.cif_declared_symmetry_summary)
                if row.cif_valid_block_count > 1:
                    box.prop(
                        row,
                        "cif_default_block_confirmed",
                        text="Use the displayed default CIF block for the view",
                    )
            if row.reader_id == "poscar":
                box.label(text=f"Comment: {row.poscar_comment}")
                box.label(text=f"Scale: {row.poscar_scale_summary}")
                box.label(text=f"Cell: {row.poscar_cell_summary}")
                box.label(text=f"Species: {row.poscar_species_summary}")
                box.label(text=f"Coordinates: {row.poscar_coordinate_mode}")
                box.label(text=row.poscar_selective_summary)
                box.label(text=row.poscar_velocity_summary)
                if row.poscar_requires_species_assignment:
                    box.prop(
                        row,
                        "poscar_species_assignment",
                        text="Ordered species",
                    )
                    apply_species = box.operator(
                        CHEMBLENDER_OT_apply_poscar_species.bl_idname,
                        text="Apply Species and Refresh",
                    )
                    apply_species.source_id = row.source_id
                    apply_species.species = row.poscar_species_assignment
            if row.conflict_id:
                box.prop(row, "conflict_action")
                if DuplicateAction(row.conflict_action) in _TARGET_ACTIONS:
                    box.label(text="Select exactly one target:")
                    for candidate in row.conflict_candidates:
                        candidate_row = box.row(align=True)
                        candidate_row.prop(
                            candidate,
                            "selected",
                            text=candidate.display_label,
                        )
                        candidate_row.label(
                            text=(
                                f"{candidate.created_entity_count} "
                                "created entities"
                            )
                        )
            box.prop(row, "default_view")
            box.label(text=row.default_view_label)
        for suggestion in self.grouping_suggestions:
            box = layout.box()
            box.label(
                text=(
                    f"Suggested source group: {suggestion.source_count} "
                    f"sources · {suggestion.confidence} confidence"
                )
            )
            box.prop(suggestion, "grouping_action", expand=True)
            if suggestion.grouping_action == "accept_group":
                for evidence in suggestion.evidence:
                    evidence_row = box.row(align=True)
                    evidence_row.prop(
                        evidence,
                        "selected",
                        text=evidence.summary,
                    )
                    detail = evidence.kind
                    if evidence.metric:
                        detail += (
                            f": {evidence.metric} {evidence.metric_unit}"
                        )
                    evidence_row.label(text=detail)
                if suggestion.requires_review:
                    box.prop(
                        suggestion,
                        "review_confirmed",
                        text="I reviewed this grouping conflict",
                    )
            unavailable = box.row()
            unavailable.enabled = False
            unavailable.label(text="Split / Edit unavailable in alpha.1")
        for suggestion in self.conformer_grouping_suggestions:
            box = layout.box()
            box.label(
                text=(
                    f"Suggested conformer group: "
                    f"{suggestion.record_count} records"
                )
            )
            action = box.row()
            action.enabled = not suggestion.hidden_review_count
            action.prop(suggestion, "grouping_action", expand=True)
            for evidence in suggestion.evidence:
                box.label(
                    text=(
                        f"{evidence.record_key}: {evidence.kind} · "
                        f"map {evidence.atom_mapping}"
                    ),
                    icon="ERROR" if evidence.requires_review else "INFO",
                )
            if len(suggestion.evidence) < suggestion.record_count:
                box.label(
                    text=(
                        f"Showing {len(suggestion.evidence)} "
                        f"of {suggestion.record_count} records"
                    )
                )
            if suggestion.hidden_review_count:
                box.label(
                    text=(
                        f"{suggestion.hidden_review_count} review mappings "
                        "are hidden; keep records independent"
                    ),
                    icon="ERROR",
                )
            if (
                suggestion.grouping_action == "accept_group"
                and suggestion.requires_review
            ):
                box.prop(
                    suggestion,
                    "review_confirmed",
                    text="I reviewed this atom mapping",
                )

    def _abort_setup(self, session, job, error):
        fatal_cleanup = None
        for label, cleanup in (
            ("job cancellation failed", job.cancel),
            ("job join failed", lambda: job.join(0)),
        ):
            try:
                cleanup()
            except BaseException as cleanup_error:
                _add_cleanup_note(error, label, cleanup_error)
                if (
                    fatal_cleanup is None
                    and isinstance(cleanup_error, _FATAL_EXCEPTIONS)
                ):
                    fatal_cleanup = cleanup_error
        try:
            job.release_ui()
        except BaseException as cleanup_error:
            _add_cleanup_note(
                error,
                "job UI cleanup failed",
                cleanup_error,
            )
            if (
                fatal_cleanup is None
                and isinstance(cleanup_error, _FATAL_EXCEPTIONS)
            ):
                fatal_cleanup = cleanup_error
        else:
            for label, cleanup in (
                (
                    "job ownership cleanup failed",
                    lambda: finish_quick_import_job(session, job),
                ),
                (
                    "staging cleanup failed",
                    lambda: discard_quick_import_preview(session),
                ),
            ):
                try:
                    cleanup()
                except BaseException as cleanup_error:
                    _add_cleanup_note(error, label, cleanup_error)
                    if (
                        fatal_cleanup is None
                        and isinstance(cleanup_error, _FATAL_EXCEPTIONS)
                    ):
                        fatal_cleanup = cleanup_error
        self._job = None
        self._rows = None
        if fatal_cleanup is not None:
            fatal_cleanup.add_note(f"setup failed: {error}")
            raise fatal_cleanup

    def _finalize_committed_job(self, context, job, state):
        result = getattr(self, "_completion_result", None)
        if result is not None:
            return result
        progress_failed = False
        try:
            context.window_manager.progress_update(80)
        except BaseException as error:
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            progress_failed = True
        result = _finish_committed_import(
            job.project_session,
            state,
            self._rows,
            job.result,
            collection=context.scene.collection,
            apply_view=apply_scene_preset,
            discard_staging=False,
        )
        try:
            context.window_manager.progress_update(100)
        except BaseException as error:
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            progress_failed = True
        if progress_failed:
            result = _with_cleanup_pending(result)
        self._completion_result = result
        return result

    def _finish_modal_ownership(self, job, result, cleanup_error=None):
        state = get_quick_import_state(job.project_session)
        cleanup_errors = [] if cleanup_error is None else [cleanup_error]
        try:
            finish_quick_import_job(job.project_session, job)
        except BaseException as error:
            cleanup_errors.append(error)
        try:
            discard_quick_import_preview(job.project_session)
        except BaseException as error:
            cleanup_errors.append(error)
        fatal_error = next(
            (
                error
                for error in cleanup_errors
                if isinstance(error, _FATAL_EXCEPTIONS)
            ),
            None,
        )
        if fatal_error is not None:
            raise fatal_error
        cleanup_error = cleanup_errors[0] if cleanup_errors else None
        if cleanup_error is not None and result is not None:
            result = _with_cleanup_pending(result)
        return state, result

    def execute(self, context):
        try:
            session = getattr(self, "_project_session", None)
            if session is None:
                session, state = self._project(context)
            else:
                state = get_quick_import_state(session)
            rows = _row_values(self.rows)
            grouping_rows = _grouping_values(
                self.grouping_suggestions
            )
            conformer_rows = _conformer_values(
                self.conformer_grouping_suggestions
            )
            decisions = import_commit_decisions(
                state,
                rows,
                grouping_rows=grouping_rows,
                conformer_rows=conformer_rows,
                project_session=session,
            )
        except BaseException as error:
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if getattr(bpy.app, "background", False):
            try:
                result = commit_project_import(
                    session,
                    state,
                    rows,
                    grouping_rows=grouping_rows,
                    conformer_rows=conformer_rows,
                    collection=context.scene.collection,
                )
            except BaseException as error:
                if isinstance(error, _FATAL_EXCEPTIONS):
                    raise
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            self.report(
                _commit_report_level(result.status),
                result.status,
            )
            context.scene.chemblender_quick_import.recent_summary = (
                result.status
            )
            return {"FINISHED"}
        job = _CommitJob(
            session,
            state.staging_session,
            state.preview,
            decisions,
        )
        try:
            store_quick_import_job(
                session,
                state.staging_session,
                job,
            )
            manager = context.window_manager
            timer = manager.event_timer_add(0.1, window=context.window)
            job.attach_ui(manager, timer)
            manager.progress_begin(0, 100)
            job.mark_progress_started()
            manager.progress_update(10)
            manager.modal_handler_add(self)
            self._job = job
            self._rows = rows
            job.start()
        except BaseException as error:
            self._abort_setup(session, job, error)
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, _error_report(error))
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        job = getattr(self, "_job", None)
        if job is None:
            return {"CANCELLED"}
        if event.type == "ESC":
            job.cancel()
            if job.commit_started:
                self.report(
                    {"WARNING"},
                    "cancellation requested; cannot undo published data",
                )
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}
        progress = getattr(job, "drain_progress", lambda: None)()
        if progress is not None:
            _stage, completed, total = progress
            context.window_manager.progress_update(
                10 + 60 * completed / total if total else 10
            )
        if not job.done:
            return {"RUNNING_MODAL"}
        if not getattr(job, "_completion_checked", False):
            completion_error = None
            result = None
            try:
                job.join(0)
                state = get_quick_import_state(job.project_session)
                if job.error is None:
                    result = self._finalize_committed_job(
                        context,
                        job,
                        state,
                    )
            except BaseException as error:
                completion_error = error
            job._completion_error = completion_error
            job._completion_result = result
            job._completion_checked = True
        completion_error = job._completion_error
        result = job._completion_result
        release_error = None
        try:
            job.release_ui()
        except BaseException as error:
            release_error = error
            if (
                not isinstance(error, _FATAL_EXCEPTIONS)
                and job.timer_pending
            ):
                self.report(
                    {"WARNING"},
                    f"Import Preview cleanup retry pending: {error}",
                )
                return {"RUNNING_MODAL"}
            job.abandon_ui()
        try:
            state, result = self._finish_modal_ownership(
                job,
                result,
                release_error,
            )
        except BaseException as ownership_error:
            if completion_error is not None:
                raise _merge_cleanup_failure(
                    completion_error,
                    ownership_error,
                    "import ownership cleanup failed",
                )
            raise
        if completion_error is not None:
            if release_error is not None:
                completion_error = _merge_cleanup_failure(
                    completion_error,
                    release_error,
                    "Import Preview UI cleanup failed",
                )
            if isinstance(completion_error, _FATAL_EXCEPTIONS):
                raise completion_error
            self.report({"ERROR"}, str(completion_error))
            return {"CANCELLED"}
        if job.error is not None:
            if release_error is not None:
                _add_cleanup_note(
                    job.error,
                    "Import Preview UI cleanup failed",
                    release_error,
                )
            if isinstance(job.error, (ImportCommitCancelled, ImportCancelled)):
                self.report({"INFO"}, str(job.error))
            elif isinstance(job.error, _FATAL_EXCEPTIONS):
                raise job.error
            else:
                self.report({"ERROR"}, str(job.error))
            return {"CANCELLED"}
        self.report(
            _commit_report_level(result.status),
            result.status,
        )
        context.scene.chemblender_quick_import.recent_summary = result.status
        return {"FINISHED"}

    def cancel(self, context):
        job = getattr(self, "_job", None)
        if job is not None:
            job.cancel()
            return
        session = getattr(self, "_project_session", None)
        if session is None:
            session = get_scene_session(context.scene)
        cancel_project_import(session)


class CHEMBLENDER_OT_cancel_import(bpy.types.Operator):
    bl_idname = "chemblender.cancel_import"
    bl_label = "Cancel Import"

    def execute(self, context):
        session = get_scene_session(context.scene)
        state = get_quick_import_state(session)
        if state.active_job is not None:
            state.active_job.cancel()
            self.report(
                {"WARNING"},
                "cancellation requested; published data cannot be undone",
            )
        else:
            cancel_project_import(session)
        return {"FINISHED"}


__all__ = (
    "CHEMBLENDER_OT_apply_poscar_species",
    "CHEMBLENDER_OT_cancel_import",
    "CHEMBLENDER_OT_confirm_import",
    "CHEMBLENDER_PG_import_conformer_evidence",
    "CHEMBLENDER_PG_import_conformer_suggestion",
    "CHEMBLENDER_PG_import_conflict_candidate",
    "CHEMBLENDER_PG_import_grouping_evidence",
    "CHEMBLENDER_PG_import_grouping_suggestion",
    "CHEMBLENDER_PG_import_preview_row",
    "restage_poscar_species_assignment",
)
