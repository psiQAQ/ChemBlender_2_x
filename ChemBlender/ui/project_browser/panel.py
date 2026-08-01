"""Blender Project Browser UIList and small RNA projection."""

import importlib
import json
import operator
import os
from pathlib import Path
from uuid import UUID

import bpy
from bpy.props import (
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from ..properties import (
    _same_scene_property,
    _scene_property_identity,
    draw_crystal_symmetry_properties,
    draw_selective_dynamics_properties,
    advance_browser_revision,
    get_quick_import_state,
)
from ..session import (
    get_scene_session,
    get_scene_session_status,
    register_session_cleanup,
    unregister_session_cleanup,
)
from ...core import (
    AtomFrameProperty,
    AtomicProperty,
    CategoricalData,
    ConformerSet,
    FrameSet,
    MolecularRecord,
    Structure,
    builtin_scene_presets,
    plan_scene_preset,
)
from ...core.project_service import (
    relink_project_session_for_scenes,
    verify_project_session_for_scenes,
)
from ...core.storage.atomic_paths import short_sibling_temporary_path
from ...dataset_view import (
    apply_atom_selection,
    apply_atomic_scalar,
    write_vector_view,
)
from ...project_link import ProjectLinkStatus
from ...scene_preset_view import (
    _remove_objects as _remove_scene_preset_objects,
    apply_scene_preset,
)
from .model import (
    BrowserMode,
    ViewRecord,
    _browser_entity_ids,
    build_browser_rows,
    clear_browser_caches,
    clear_browser_session_cache,
)

_scientific_edit = importlib.import_module("..scientific_edit", __package__)
_topology = importlib.import_module("..topology", __package__)
_biological = importlib.import_module("..biological", __package__)
_diagnostics = importlib.import_module("..diagnostics", __package__)
_grid = importlib.import_module("..grid", __package__)


_MODE_ITEMS = tuple(
    (mode.value, mode.value.replace("_", " ").title(), "") for mode in BrowserMode
)
_QUALITY_ITEMS = (
    ("all", "All Quality", ""),
    ("complete", "Complete", ""),
    ("partial", "Partial", ""),
    ("ambiguous", "Ambiguous", ""),
    ("incomplete", "Incomplete", ""),
    ("invalid", "Invalid", ""),
)
_BROWSER_RNA_ROW_LIMIT = 1000
_ROW_ICONS = {
    "diagnostic": "ERROR",
    "empty": "INFO",
    "grid3d": "VOLUME_DATA",
    "conformer_set": "MOD_ARRAY",
    "group": "OUTLINER_COLLECTION",
    "source": "FILE",
    "source_revision": "FILE",
    "molecular_record": "FILE_TEXT",
    "projection_summary": "INFO",
    "record_page": "LINENUMBERS_ON",
    "result_page": "LINENUMBERS_ON",
    "record_property_column": "PROPERTIES",
    "structure": "MESH_DATA",
    "topology_record": "MOD_WIREFRAME",
    "view": "HIDE_OFF",
}
_SCENE_PROPERTY_NAME = "chemblender_project_browser"
_TOPOLOGY_SCENE_PROPERTY_NAME = "chemblender_topology"
_OWNED_SCENE_PROPERTY = None
_OWNED_TOPOLOGY_SCENE_PROPERTY = None
_FATAL_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    MemoryError,
)


def _diagnostics_report(session):
    return get_quick_import_state(session).diagnostics_report


def _current_diagnostic(state):
    document = state.diagnostics_report
    diagnostics = () if document is None else document["diagnostics"]
    total = len(diagnostics)
    if not total:
        state.diagnostic_index = 0
        return 0, 0, None
    index = max(
        0,
        min(int(getattr(state, "diagnostic_index", 0)), total - 1),
    )
    state.diagnostic_index = index
    return index + 1, total, diagnostics[index]


class CHEMBLENDER_OT_diagnostic_page(bpy.types.Operator):
    bl_idname = "chemblender.diagnostic_page"
    bl_label = "Navigate Diagnostics"

    direction: EnumProperty(
        items=(
            ("previous", "Previous", ""),
            ("next", "Next", ""),
        )
    )

    def execute(self, context):
        try:
            session = get_scene_session(context.scene)
            state = get_quick_import_state(session)
            _index, total, _item = _current_diagnostic(state)
            if total:
                delta = -1 if self.direction == "previous" else 1
                state.diagnostic_index = max(
                    0,
                    min(state.diagnostic_index + delta, total - 1),
                )
        except BaseException as error:
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class CHEMBLENDER_OT_copy_diagnostics(bpy.types.Operator):
    bl_idname = "chemblender.copy_diagnostics"
    bl_label = "Copy Diagnostics"

    format_name: EnumProperty(
        items=(
            ("markdown", "Markdown", ""),
            ("json", "JSON", ""),
        ),
        default="markdown",
    )

    def execute(self, context):
        try:
            session = get_scene_session(context.scene)
            document = _diagnostics_report(session)
            if document is None:
                raise ValueError("no import diagnostics are available")
            context.window_manager.clipboard = (
                _diagnostics.canonical_report_text(
                    document,
                    self.format_name,
                )
            )
        except BaseException as error:
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class CHEMBLENDER_OT_export_diagnostics(bpy.types.Operator):
    bl_idname = "chemblender.export_diagnostics"
    bl_label = "Export Diagnostics"

    filepath: StringProperty(subtype="FILE_PATH")
    format_name: EnumProperty(
        items=(
            ("markdown", "Markdown", ""),
            ("json", "JSON", ""),
        ),
        default="markdown",
    )

    def invoke(self, context, _event):
        if not self.filepath:
            extension = ".md" if self.format_name == "markdown" else ".json"
            self.filepath = f"chemblender-diagnostics{extension}"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        temporary = None
        try:
            session = get_scene_session(context.scene)
            document = _diagnostics_report(session)
            if document is None:
                raise ValueError("no import diagnostics are available")
            destination = Path(self.filepath).resolve()
            if not destination.parent.is_dir():
                raise ValueError(
                    "diagnostics destination directory does not exist"
                )
            text = _diagnostics.canonical_report_text(
                document,
                self.format_name,
            )
            temporary = short_sibling_temporary_path(destination)
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            temporary = None
        except BaseException as error:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    error.add_note(
                        f"diagnostics temporary cleanup failed: {cleanup_error}"
                    )
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


def _logical_view_metadata(obj):
    try:
        preset_id = obj["cb_scene_preset_id"]
        preset_version = obj["cb_scene_preset_version"]
        view_kind = obj["cb_scene_view_kind"]
        render_identity = obj["cb_scene_render_identity"]
        encoded_bindings = json.loads(obj["cb_scene_bindings_json"])
        settings = json.loads(obj["cb_scene_settings_json"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "current View has invalid revision metadata"
        ) from error
    if (
        any(
            type(value) is not str or not value
            for value in (
                preset_id,
                preset_version,
                view_kind,
                render_identity,
            )
        )
        or type(encoded_bindings) is not dict
        or type(settings) is not dict
    ):
        raise ValueError("current View has invalid revision metadata")
    return (
        render_identity,
        preset_id,
        preset_version,
        view_kind,
        encoded_bindings,
        settings,
    )


def _logical_view_groups(objects):
    grouped = {}
    order = []
    for obj in objects:
        if obj.get("cb_scene_preset_id") is None:
            continue
        metadata = _logical_view_metadata(obj)
        render_identity = metadata[0]
        if render_identity not in grouped:
            grouped[render_identity] = [metadata[1:], [obj]]
            order.append(render_identity)
            continue
        expected, components = grouped[render_identity]
        if expected != metadata[1:]:
            raise ValueError(
                "logical View components have conflicting metadata"
            )
        components.append(obj)
    return tuple(
        (tuple(grouped[identity][1]), grouped[identity][0])
        for identity in order
    )


def _mapped_revision_bindings(
    project,
    preset,
    encoded_bindings,
    current_revision,
    new_revision,
):
    if set(encoded_bindings) != {
        spec.name for spec in preset.bindings
    }:
        raise ValueError("current View has invalid revision metadata")
    current = {}
    mapped = {}
    changed = False
    for spec in preset.bindings:
        value = encoded_bindings[spec.name]
        if (
            type(value) is not dict
            or set(value) != {"entity_id", "revision"}
            or type(value["entity_id"]) is not str
            or type(value["revision"]) is not str
            or not value["revision"]
        ):
            raise ValueError("current View has invalid revision metadata")
        try:
            current_id = UUID(value["entity_id"])
        except ValueError as error:
            raise ValueError(
                "current View has invalid revision metadata"
            ) from error
        registry = (
            project.structures
            if spec.entity_kind == "structure"
            else project.datasets
        )
        current_entity = registry.get(current_id)
        if (
            current_entity is None
            or current_entity.revision != value["revision"]
        ):
            raise ValueError("current View binding is stale")
        current[spec.name] = current_id
        if current_id not in current_revision.created_entity_ids:
            mapped[spec.name] = current_id
            continue
        candidates = tuple(
            candidate
            for candidate_id in new_revision.created_entity_ids
            if (
                (candidate := registry.get(candidate_id)) is not None
                and type(candidate) is type(current_entity)
                and getattr(candidate, "semantic_role", None)
                == getattr(current_entity, "semantic_role", None)
            )
        )
        if len(candidates) != 1:
            qualifier = "no" if not candidates else "ambiguous"
            raise ValueError(
                f"{qualifier} new revision entity matches "
                f"View binding {spec.name!r}"
            )
        mapped[spec.name] = candidates[0].id
        changed = True
    return current, mapped if changed else None


def _revision_view_targets(context, prompt, *, selected_only):
    presets = builtin_scene_presets()
    session = get_scene_session(context.scene)
    project = session.project
    try:
        current_revision = project.source_revisions[
            prompt.current_revision_id
        ]
        new_revision = project.source_revisions[prompt.new_revision_id]
    except KeyError as error:
        raise ValueError("revision prompt is stale") from error
    targets = []
    for components, metadata in _logical_view_groups(
        context.scene.objects
    ):
        if selected_only and not any(
            component.select_get() for component in components
        ):
            continue
        (
            preset_id,
            preset_version,
            view_kind,
            encoded_bindings,
            settings,
        ) = metadata
        preset = presets.get(preset_id)
        if preset is None:
            raise ValueError("current View references an unknown preset")
        if (
            preset.version != preset_version
            or preset.view_kind != view_kind
        ):
            raise ValueError("current View references a stale preset")
        current_bindings, bindings = _mapped_revision_bindings(
            project,
            preset,
            encoded_bindings,
            current_revision,
            new_revision,
        )
        if bindings is None:
            continue
        try:
            supplied_settings = {
                name: settings[name]
                for name, _default in preset.default_settings
            }
        except KeyError as error:
            raise ValueError(
                "current View has invalid revision metadata"
            ) from error
        current_plan = plan_scene_preset(
            preset,
            project,
            current_bindings,
            supplied_settings,
        )
        normalized_settings = json.loads(
            json.dumps(
                dict(current_plan.settings),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        if normalized_settings != settings:
            raise ValueError(
                "current View has invalid revision metadata"
            )
        plan = plan_scene_preset(
            preset,
            project,
            bindings,
            supplied_settings,
        )
        targets.append((components, plan))
    return tuple(targets)


def _remove_revision_prompt(state, prompt):
    state.revision_prompts = tuple(
        value
        for value in state.revision_prompts
        if not (
            value.current_revision_id == prompt.current_revision_id
            and value.new_revision_id == prompt.new_revision_id
        )
    )


class CHEMBLENDER_OT_revision_view_action(bpy.types.Operator):
    bl_idname = "chemblender.revision_view_action"
    bl_label = "Resolve Revision Views"

    current_revision_id: StringProperty()
    new_revision_id: StringProperty()
    action: EnumProperty(items=_diagnostics.revision_action_items())

    def execute(self, context):
        created = []
        hidden = []
        try:
            session = get_scene_session(context.scene)
            state = get_quick_import_state(session)
            current_id = UUID(self.current_revision_id)
            new_id = UUID(self.new_revision_id)
            prompt = next(
                (
                    value
                    for value in state.revision_prompts
                    if (
                        value.current_revision_id == current_id
                        and value.new_revision_id == new_id
                    )
                ),
                None,
            )
            if prompt is None:
                raise ValueError("revision prompt is no longer available")
            if self.action == "keep_current":
                _remove_revision_prompt(state, prompt)
                return {"FINISHED"}
            targets = _revision_view_targets(
                context,
                prompt,
                selected_only=self.action == "update_selected_views",
            )
            if not targets:
                raise ValueError("no matching current Views are selected")
            cache_root = Path(session.temporary_root) / "view-cache"
            cache_root.mkdir(exist_ok=True)
            for old_views, plan in targets:
                created.extend(
                    apply_scene_preset(
                        plan,
                        session.project,
                        collection=context.collection,
                        cache_root=cache_root,
                    )
                )
                if self.action == "update_selected_views":
                    for old_view in old_views:
                        previous = (
                            old_view.hide_get(),
                            old_view.hide_render,
                        )
                        hidden.append((old_view, previous))
                        old_view.hide_set(True)
                        old_view.hide_render = True
            _remove_revision_prompt(state, prompt)
            advance_browser_revision(session)
        except BaseException as error:
            for old_view, previous in reversed(hidden):
                try:
                    old_view.hide_set(previous[0])
                    old_view.hide_render = previous[1]
                except BaseException as cleanup_error:
                    error.add_note(
                        f"revision View visibility rollback failed: "
                        f"{cleanup_error}"
                    )
            if created:
                try:
                    _remove_scene_preset_objects(created)
                except BaseException as cleanup_error:
                    error.add_note(
                        f"revision View cleanup failed: {cleanup_error}"
                    )
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class CHEMBLENDER_OT_project_link_recovery(bpy.types.Operator):
    bl_idname = "chemblender.project_link_recovery"
    bl_label = "Recover Project Link"

    action: EnumProperty(
        items=(
            ("relink", "Relink", ""),
            ("verify", "Verify", ""),
            ("inspect_existing", "Inspect Existing Objects", ""),
            ("open_diagnostics", "Open Diagnostics", ""),
            ("detach", "Detach", ""),
        )
    )
    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, _event):
        if self.action == "relink":
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}
        return self.execute(context)

    def execute(self, context):
        try:
            session = get_scene_session(context.scene)
            scenes = tuple(bpy.data.scenes)
            blend_path = bpy.data.filepath
            try:
                live_status = ProjectLinkStatus(session.link_status)
            except ValueError as error:
                raise ValueError(
                    "project link state does not allow recovery actions"
                ) from error
            if self.action not in _diagnostics.project_recovery_actions(
                live_status
            ):
                raise ValueError(
                    "recovery action is not allowed for the current link state"
                )
            state = get_quick_import_state(session)
            if self.action == "relink":
                if not self.filepath:
                    raise ValueError("select a ChemBlender .cbq sidecar")
                result = relink_project_session_for_scenes(
                    session=session,
                    scenes=scenes,
                    sidecar_path=self.filepath,
                    blend_path=blend_path,
                )
                if result.status.value != "connected":
                    raise ValueError(result.message or result.status.value)
                state.project_link_inspection_only = False
                state.show_project_link_diagnostics = False
            elif self.action == "verify":
                result = verify_project_session_for_scenes(
                    session=session,
                    scenes=scenes,
                    blend_path=blend_path,
                )
                if result.status.value != "connected":
                    raise ValueError(result.message or result.status.value)
                state.project_link_inspection_only = False
                state.show_project_link_diagnostics = False
            elif self.action == "inspect_existing":
                state.project_link_inspection_only = True
            elif self.action == "open_diagnostics":
                state.show_project_link_diagnostics = True
            elif self.action == "detach":
                _diagnostics.detach_project_links_for_scenes(scenes)
                session.sidecar_path = None
                session.link_status = "unlinked"
                for reason in ("project_link", "view_cache"):
                    if reason in session.dirty_reasons:
                        session.clear_dirty(reason)
                state.project_link_inspection_only = False
                state.show_project_link_diagnostics = False
            else:
                raise ValueError("unknown project recovery action")
        except BaseException as error:
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


def _selection_changed(state, context):
    synchronize_browser_selection(get_scene_session(context.scene), state)


def _projection_changed(_state, context):
    _state.page = 0
    _state.page_jump = 1
    refresh_project_browser(context.scene)


class CHEMBLENDER_PG_project_browser_row(bpy.types.PropertyGroup):
    row_id: StringProperty()
    parent_id: StringProperty()
    entity_id: StringProperty()
    kind: StringProperty()
    label: StringProperty()
    quality: StringProperty()
    depth: IntProperty()
    view_count: IntProperty()


class CHEMBLENDER_PG_project_browser(bpy.types.PropertyGroup):
    mode: EnumProperty(items=_MODE_ITEMS, default=BrowserMode.BY_SOURCE.value, update=_projection_changed)
    search: StringProperty(name="Search", update=_projection_changed)
    quality_filter: EnumProperty(
        items=_QUALITY_ITEMS,
        default="all",
        update=_projection_changed,
    )
    substructure_code: IntProperty(
        name="Substructure Code",
        default=0,
        min=0,
    )
    biological_chain: StringProperty(name="Chain")
    biological_residue_start: IntProperty(name="First Residue")
    biological_residue_end: IntProperty(name="Last Residue")
    biological_residue_name: StringProperty(name="Residue Name")
    biological_atom_name: StringProperty(name="Atom Name")
    biological_altloc: StringProperty(name="Alternate Location")
    biological_property_role: EnumProperty(
        items=_biological.biological_numeric_role_items(),
        default="occupancy",
    )
    biological_comparison: EnumProperty(
        items=(
            ("greater_equal", "At Least", ""),
            ("less_equal", "At Most", ""),
        ),
        default="greater_equal",
    )
    biological_threshold: StringProperty(name="Threshold", default="0.0")
    selected_index: IntProperty(default=0, update=_selection_changed)
    active_entity_id: StringProperty()
    total_row_count: IntProperty(default=0)
    record_count: IntProperty(default=0, min=0)
    page: IntProperty(default=0, min=0)
    page_size: IntProperty(
        name="Entries per Page",
        default=998,
        min=1,
        max=998,
        update=_projection_changed,
    )
    page_jump: IntProperty(name="Jump to Page", default=1, min=1)
    page_count: IntProperty(default=1, min=1)
    page_kind: StringProperty()
    rows: CollectionProperty(type=CHEMBLENDER_PG_project_browser_row)


class CHEMBLENDER_OT_project_browser_page(bpy.types.Operator):
    bl_idname = "chemblender.project_browser_page"
    bl_label = "Change Project Browser Page"

    action: EnumProperty(
        items=(
            ("previous", "Previous", ""),
            ("next", "Next", ""),
            ("jump", "Jump", ""),
        )
    )

    def execute(self, context):
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        last_page = max(settings.page_count - 1, 0)
        target = {
            "previous": settings.page - 1,
            "next": settings.page + 1,
            "jump": settings.page_jump - 1,
        }[self.action]
        settings.page = max(0, min(target, last_page))
        settings.page_jump = settings.page + 1
        refresh_project_browser(context.scene)
        return {"FINISHED"}


def _project_entity_id(project, value):
    if type(value) is not str or not value:
        return None
    try:
        entity_id = UUID(value)
    except ValueError:
        return None
    return (
        entity_id
        if entity_id in _browser_entity_ids(project)
        else None
    )


def synchronize_browser_selection(session, state):
    index = state.selected_index
    entity_id = ""
    if type(index) is int and 0 <= index < len(state.rows):
        entity_id = state.rows[index].entity_id
    selected = _project_entity_id(session.project, entity_id)
    session.active_entity_id = selected
    state.active_entity_id = str(selected) if selected is not None else ""


def atom_frame_vector(project, entity_id, frame_index):
    if type(entity_id) is not UUID:
        raise TypeError("entity_id must be UUID")
    dataset = project.datasets.get(entity_id)
    if (
        not isinstance(dataset, AtomFrameProperty)
        or dataset.semantic_role != "atomic_force"
        or dataset.data.dims != ("frame", "atom", "xyz")
    ):
        raise ValueError("selected entity is not an atomic force trajectory")
    frame_set = project.datasets.get(dataset.frame_set_id)
    if not isinstance(frame_set, FrameSet):
        raise ValueError("atomic force trajectory has no FrameSet")
    structure = project.structures.get(frame_set.structure_id)
    if not isinstance(structure, Structure):
        raise ValueError("atomic force trajectory has no current Structure")
    if isinstance(frame_index, bool):
        raise TypeError("frame_index must be an integer")
    try:
        frame_index = operator.index(frame_index)
    except TypeError as error:
        raise TypeError("frame_index must be an integer") from error
    if not 0 <= frame_index < dataset.data.shape[0]:
        raise IndexError("frame_index is outside the trajectory")
    if dataset.validity_mask is not None:
        import numpy

        if not numpy.all(dataset.validity_mask.values[frame_index]):
            raise ValueError("atomic force frame contains missing values")
    return (
        structure,
        dataset,
        dataset.data.values[frame_index],
    )


def substructure_category(project, entity_id, category_code):
    if type(entity_id) is not UUID:
        raise TypeError("entity_id must be UUID")
    dataset = project.datasets.get(entity_id)
    if (
        not isinstance(dataset, AtomicProperty)
        or dataset.semantic_role != "substructure_name"
        or not isinstance(dataset.data, CategoricalData)
        or dataset.data.dims != ("atom",)
    ):
        raise ValueError(
            "selected entity is not a categorical substructure dataset"
        )
    structure = project.structures.get(dataset.structure_id)
    if (
        not isinstance(structure, Structure)
        or len(structure.atomic_numbers) != dataset.data.shape[0]
    ):
        raise ValueError("substructure dataset has no matching Structure")
    if isinstance(category_code, bool):
        raise TypeError("category_code must be an integer")
    try:
        category_code = operator.index(category_code)
    except TypeError as error:
        raise TypeError("category_code must be an integer") from error
    if not 0 <= category_code < len(dataset.data.categories):
        raise IndexError("category_code is outside the substructure categories")
    import numpy

    indices = tuple(
        int(index)
        for index in numpy.flatnonzero(
            numpy.asarray(dataset.data.codes.values) == category_code
        )
    )
    return (
        structure,
        dataset,
        dataset.data.categories[category_code],
        indices,
    )


class CHEMBLENDER_OT_apply_substructure_category(bpy.types.Operator):
    bl_idname = "chemblender.apply_substructure_category"
    bl_label = "Color and Select Substructure"
    bl_description = (
        "Color MOL2 substructures and select atoms with the chosen category code"
    )

    category_code: IntProperty(name="Category Code", default=0, min=0)

    def execute(self, context):
        session = get_scene_session(context.scene)
        obj = context.active_object
        if obj is None and session.active_view_object_name:
            obj = context.scene.objects.get(session.active_view_object_name)
        try:
            structure, dataset, label, indices = substructure_category(
                session.project,
                session.active_entity_id,
                self.category_code,
            )
            if (
                obj.get("cb_structure_contract") != "structure_view_v1"
                or obj.get("cb_structure_id") != str(structure.id)
                or obj.get("cb_structure_revision") != structure.revision
            ):
                raise ValueError(
                    "active object is not the current matching Structure view"
                )
            apply_atomic_scalar(
                obj,
                dataset,
                presentation_only=True,
            )
            apply_atom_selection(
                obj,
                indices,
                name=f"substructure:{label}",
            )
            obj["cb_categorical_dataset_id"] = str(dataset.id)
            obj["cb_categorical_dataset_revision"] = dataset.revision
            obj["cb_categorical_code"] = int(self.category_code)
            obj["cb_categorical_label"] = label
        except (AttributeError, TypeError, ValueError, IndexError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        session.active_view_object_name = obj.name
        return {"FINISHED"}


class CHEMBLENDER_OT_apply_frame_force(bpy.types.Operator):
    bl_idname = "chemblender.apply_frame_force"
    bl_label = "Show Force Vectors"
    bl_description = "Apply the selected trajectory force to the active Structure view"

    display_scale: FloatProperty(name="Scale", default=1.0, min=1.0e-9)

    def execute(self, context):
        session = get_scene_session(context.scene)
        obj = context.active_object
        if obj is None and session.active_view_object_name:
            obj = context.scene.objects.get(session.active_view_object_name)
        try:
            frame_index = int(obj.get("cb_trajectory_frame_index", 0))
            structure, dataset, values = atom_frame_vector(
                session.project,
                session.active_entity_id,
                frame_index,
            )
            if (
                obj.get("cb_structure_contract") != "structure_view_v1"
                or obj.get("cb_structure_id") != str(structure.id)
                or obj.get("cb_structure_revision") != structure.revision
            ):
                raise ValueError(
                    "active object is not the current matching Structure view"
                )
            write_vector_view(
                obj,
                values,
                dataset_id=dataset.id,
                revision=dataset.revision,
                semantic_role=dataset.semantic_role,
                unit=dataset.data.unit,
                display_scale=self.display_scale,
            )
        except (AttributeError, TypeError, ValueError, IndexError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        session.active_view_object_name = obj.name
        return {"FINISHED"}


def presentation_view_records(scene):
    records = []
    seen = set()
    for obj in sorted(scene.objects, key=lambda value: value.name):
        topology_text = obj.get("cb_topology_id")
        topology_revision = obj.get("cb_topology_revision")
        if (
            type(topology_text) is str
            and topology_text.strip()
            and type(topology_revision) is str
            and topology_revision.strip()
        ):
            try:
                topology_id = UUID(topology_text)
            except ValueError:
                pass
            else:
                identity = (obj.name, topology_id, topology_revision)
                seen.add(identity)
                records.append(
                    ViewRecord(
                        object_name=obj.name,
                        entity_id=topology_id,
                        revision=topology_revision,
                        view_kind="structure_topology",
                        label=obj.name,
                    )
                )
        view_kind = obj.get("cb_scene_view_kind")
        encoded = obj.get("cb_scene_bindings_json")
        if (
            type(view_kind) is not str
            or not view_kind.strip()
            or type(encoded) is not str
            or not encoded.strip()
        ):
            continue
        try:
            bindings = json.loads(encoded)
        except (TypeError, ValueError):
            continue
        if type(bindings) is not dict:
            continue
        quality = obj.get("cb_view_quality", "")
        if (
            type(quality) is not str
            or quality not in {"", "complete", "partial", "ambiguous"}
        ):
            quality = ""
        report_eligible = obj.get(
            "cb_report_eligible",
            view_kind not in {"signed_isosurface", "property_on_surface"},
        )
        if type(report_eligible) is not bool:
            report_eligible = False
        if quality in {"partial", "ambiguous"}:
            report_eligible = False
        for binding_name in sorted(bindings):
            binding = bindings[binding_name]
            if (
                type(binding) is not dict
                or set(binding) != {"entity_id", "revision"}
            ):
                continue
            entity_text = binding["entity_id"]
            revision = binding["revision"]
            if (
                type(entity_text) is not str
                or not entity_text.strip()
                or type(revision) is not str
                or not revision.strip()
            ):
                continue
            try:
                entity_id = UUID(entity_text)
            except ValueError:
                continue
            identity = (obj.name, entity_id, revision)
            if identity in seen:
                continue
            seen.add(identity)
            records.append(
                ViewRecord(
                    object_name=obj.name,
                    entity_id=entity_id,
                    revision=revision,
                    view_kind=view_kind,
                    label=obj.name,
                    quality=quality,
                    report_eligible=report_eligible,
                )
            )
    return tuple(records)


def draw_substructure_controls(layout, dataset, settings):
    if (
        not isinstance(dataset, AtomicProperty)
        or dataset.semantic_role != "substructure_name"
        or not isinstance(dataset.data, CategoricalData)
    ):
        return
    categories = dataset.data.categories
    layout.label(text=f"Substructures: {len(categories)} categories")
    layout.prop(settings, "substructure_code")
    code = settings.substructure_code
    if not 0 <= code < len(categories):
        layout.label(text="Substructure code is outside the dataset", icon="ERROR")
        return
    layout.label(text=f"Code {code}: {categories[code]}")
    action = layout.operator(
        CHEMBLENDER_OT_apply_substructure_category.bl_idname,
        icon="RESTRICT_SELECT_OFF",
    )
    action.category_code = code


def _copy_rows(collection, rows):
    collection.clear()
    for row in rows:
        projected = collection.add()
        projected.row_id = row.id
        projected.parent_id = row.parent_id or ""
        projected.entity_id = str(row.entity_id) if row.entity_id is not None else ""
        projected.kind = row.kind
        projected.label = row.label
        projected.quality = row.quality
        projected.depth = row.depth
        projected.view_count = row.view_count


def refresh_project_browser(scene):
    session = get_scene_session(scene)
    state = get_quick_import_state(session)
    settings = getattr(scene, _SCENE_PROPERTY_NAME)
    filters = (
        ()
        if settings.quality_filter == "all"
        else (settings.quality_filter,)
    )
    rows = build_browser_rows(
        session.project,
        mode=settings.mode,
        session_id=session.id,
        browser_revision=state.browser_revision,
        search=settings.search,
        filters=filters,
        views=presentation_view_records(scene),
        page=getattr(settings, "page", 0),
        page_size=getattr(settings, "page_size", 998),
    )
    if len(rows) > _BROWSER_RNA_ROW_LIMIT:
        raise RuntimeError(
            "Project Browser model must return a bounded RNA projection"
        )
    summary = next(
        (
            row
            for row in rows
            if row.kind in {"record_page", "result_page"}
        ),
        None,
    )
    settings.record_count = (
        summary.total_count
        if summary is not None
        else sum(row.kind == "molecular_record" for row in rows)
    )
    settings.page_kind = summary.kind if summary is not None else ""
    settings.page = summary.page if summary is not None else 0
    settings.page_count = summary.page_count if summary is not None else 1
    settings.page_jump = settings.page + 1
    selected = _project_entity_id(
        session.project,
        settings.active_entity_id,
    )
    selected_id = str(selected) if selected is not None else ""
    settings.total_row_count = len(rows)
    _copy_rows(settings.rows, rows)
    selected_index = next(
        (
            index
            for index, row in enumerate(settings.rows)
            if row.entity_id == selected_id
        ),
        None,
    )
    settings.selected_index = selected_index if selected_index is not None else 0
    if selected_index is not None:
        synchronize_browser_selection(session, settings)
    elif selected is not None:
        session.active_entity_id = selected
        settings.active_entity_id = selected_id
    else:
        session.active_entity_id = None
        settings.active_entity_id = ""
    return rows


def _page_subject(settings):
    if (
        settings.search.strip()
        or settings.quality_filter != "all"
    ):
        return "matching entries"
    if settings.page_kind == "record_page":
        return "molecular records"
    return "project entries"


def _draw_import_diagnostics(layout, session):
    state = get_quick_import_state(session)
    document = state.diagnostics_report
    if document is None:
        return
    box = layout.box()
    index, total, item = _current_diagnostic(state)
    box.label(
        text=f"Import Diagnostics ({total})",
        icon="INFO",
    )
    actions = box.row(align=True)
    copy_action = actions.operator(
        CHEMBLENDER_OT_copy_diagnostics.bl_idname,
        text="Copy",
        icon="COPYDOWN",
    )
    copy_action.format_name = "markdown"
    export_action = actions.operator(
        CHEMBLENDER_OT_export_diagnostics.bl_idname,
        text="Export",
        icon="EXPORT",
    )
    export_action.format_name = "markdown"
    if item is not None:
        navigation = box.row(align=True)
        previous = navigation.operator(
            CHEMBLENDER_OT_diagnostic_page.bl_idname,
            text="Previous",
            icon="TRIA_LEFT",
        )
        previous.direction = "previous"
        navigation.label(text=f"{index} / {total}")
        following = navigation.operator(
            CHEMBLENDER_OT_diagnostic_page.bl_idname,
            text="Next",
            icon="TRIA_RIGHT",
        )
        following.direction = "next"
        _diagnostics.draw_quality_badge(
            box,
            item["quality_status"],
        )
        for label, value in _diagnostics.diagnostic_detail_rows(item):
            box.label(text=f"{label}: {value}")


def _draw_revision_prompts(layout, session):
    state = get_quick_import_state(session)
    for prompt in state.revision_prompts:
        box = layout.box()
        box.label(text="Revision Available", icon="FILE_REFRESH")
        box.label(
            text=f"Current: {prompt.current_revision_id}"
        )
        box.label(text=f"New: {prompt.new_revision_id}")
        actions = box.row(align=True)
        for identifier, label, _description in (
            _diagnostics.revision_action_items()
        ):
            action = actions.operator(
                CHEMBLENDER_OT_revision_view_action.bl_idname,
                text=label,
            )
            action.current_revision_id = str(prompt.current_revision_id)
            action.new_revision_id = str(prompt.new_revision_id)
            action.action = identifier


def _draw_project_link_recovery(layout, context, session):
    status_text = session.link_status
    try:
        status = ProjectLinkStatus(status_text)
    except ValueError:
        return
    actions = _diagnostics.project_recovery_actions(status)
    if not actions:
        return
    state = get_quick_import_state(session)
    box = layout.box()
    box.alert = status in {
        ProjectLinkStatus.INCOMPATIBLE,
        ProjectLinkStatus.INVALID,
    }
    box.label(
        text=f"Project link: {status.value.title()}",
        icon="ERROR",
    )
    _reported_status, message = get_scene_session_status(context.scene)
    if message and (
        state.show_project_link_diagnostics
        or status in {
            ProjectLinkStatus.INCOMPATIBLE,
            ProjectLinkStatus.INVALID,
        }
    ):
        box.label(text=message)
    if state.project_link_inspection_only:
        box.label(
            text=(
                "Inspection mode does not lock Blender editing or saving; "
                "no candidate is adopted or written"
            ),
            icon="INFO",
        )
    row = box.row(align=True)
    labels = {
        "relink": "Relink",
        "verify": "Verify",
        "inspect_existing": "Inspect Existing",
        "open_diagnostics": "Diagnostics",
        "detach": "Detach",
    }
    for identifier in actions:
        action = row.operator(
            CHEMBLENDER_OT_project_link_recovery.bl_idname,
            text=labels[identifier],
        )
        action.action = identifier


class CHEMBLENDER_UL_project_rows(bpy.types.UIList):
    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        _icon,
        _active_data,
        _active_property,
        _index=0,
    ):
        text = f"{'  ' * item.depth}{item.label}"
        if item.view_count:
            text = f"{text} ({item.view_count})"
        row = layout.row(align=True)
        row.label(text=text, icon=_ROW_ICONS.get(item.kind, "DOT"))
        if item.quality:
            _diagnostics.draw_quality_badge(
                row,
                item.quality,
                prefix="",
            )


class CHEMBLENDER_PT_project_browser(bpy.types.Panel):
    bl_label = "Project Browser"
    bl_idname = "CHEMBLENDER_PT_PROJECT_BROWSER"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ChemBlender"

    def draw(self, context):
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        refresh_project_browser(context.scene)
        session = get_scene_session(context.scene)
        layout = self.layout
        layout.prop(settings, "mode", expand=True)
        layout.prop(settings, "search", icon="VIEWZOOM")
        layout.prop(settings, "quality_filter")
        if settings.record_count:
            layout.label(
                text=(
                    f"{settings.record_count} {_page_subject(settings)} · "
                    f"Page {settings.page + 1} of {settings.page_count}"
                ),
                icon="LINENUMBERS_ON",
            )
            layout.prop(settings, "page_size")
            navigation = layout.row(align=True)
            previous = navigation.operator(
                CHEMBLENDER_OT_project_browser_page.bl_idname,
                text="Prev",
                icon="TRIA_LEFT",
            )
            previous.action = "previous"
            navigation.label(
                text=f"{settings.page + 1}/{settings.page_count}"
            )
            following = navigation.operator(
                CHEMBLENDER_OT_project_browser_page.bl_idname,
                text="Next",
                icon="TRIA_RIGHT",
            )
            following.action = "next"
            jump = layout.row(align=True)
            jump.prop(settings, "page_jump")
            action = jump.operator(
                CHEMBLENDER_OT_project_browser_page.bl_idname,
                text="Jump",
            )
            action.action = "jump"
        layout.template_list(
            "CHEMBLENDER_UL_project_rows",
            "",
            settings,
            "rows",
            settings,
            "selected_index",
        )
        _draw_import_diagnostics(layout, session)
        _draw_revision_prompts(layout, session)
        _draw_project_link_recovery(layout, context, session)
        if settings.active_entity_id:
            layout.label(text=f"Selected: {settings.active_entity_id}")
            selected = session.project.datasets.get(session.active_entity_id)
            selected_record = session.project.molecular_records.get(
                session.active_entity_id
            )
            selected_structure = session.project.structures.get(
                session.active_entity_id
            )
            if (
                isinstance(selected_structure, Structure)
                and selected_structure.periodic is not None
            ):
                derived = next(
                    (
                        result
                        for result in reversed(
                            tuple(
                                session.project.symmetry_results.values()
                            )
                        )
                        if result.structure_id == selected_structure.id
                    ),
                    None,
                )
                draw_crystal_symmetry_properties(
                    layout,
                    selected_structure,
                    derived,
                )
                draw_selective_dynamics_properties(
                    layout,
                    session.project,
                    selected_structure,
                )
            if (
                isinstance(selected, AtomFrameProperty)
                and selected.semantic_role == "atomic_force"
            ):
                layout.operator(
                    CHEMBLENDER_OT_apply_frame_force.bl_idname,
                    icon="FORCE_FORCE",
                )
            draw_substructure_controls(layout, selected, settings)
            _biological.draw_biological_controls(
                layout,
                session.project,
                session.active_entity_id,
                settings,
            )
            if (
                session.active_entity_id in session.project.structures
                or isinstance(selected, (FrameSet, ConformerSet))
                or isinstance(selected_record, MolecularRecord)
            ):
                layout.operator(
                    "chemblender.export_project_entity",
                    icon="EXPORT",
                )
        _scientific_edit.draw_scientific_edit_controls(
            layout,
            context,
            session,
        )
        _topology.draw_topology_controls(
            layout,
            context,
            session,
        )
        _grid.draw_grid_controls(
            layout,
            context,
            session,
        )


def register():
    global _OWNED_SCENE_PROPERTY
    global _OWNED_TOPOLOGY_SCENE_PROPERTY
    current = _scene_property_identity(_SCENE_PROPERTY_NAME)
    if _OWNED_SCENE_PROPERTY is not None:
        if not _same_scene_property(current, _OWNED_SCENE_PROPERTY):
            raise RuntimeError(
                f"Scene.{_SCENE_PROPERTY_NAME} is no longer owned by "
                "ChemBlender"
            )
    else:
        if current is not None:
            raise RuntimeError(f"Scene.{_SCENE_PROPERTY_NAME} is already owned")
        created_property = PointerProperty(
            type=CHEMBLENDER_PG_project_browser
        )
        setattr(
            bpy.types.Scene,
            _SCENE_PROPERTY_NAME,
            created_property,
        )
        identity = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if identity is None:
            failure = RuntimeError(
                "Project Browser Scene property registration failed"
            )
            current_property = getattr(
                bpy.types.Scene,
                _SCENE_PROPERTY_NAME,
                None,
            )
            if current_property is not created_property:
                failure.add_note(
                    "property replaced before rollback; foreign property "
                    "preserved"
                )
                raise failure
            try:
                delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
            except BaseException as error:
                if (
                    getattr(
                        bpy.types.Scene,
                        _SCENE_PROPERTY_NAME,
                        None,
                    )
                    is created_property
                ):
                    _OWNED_SCENE_PROPERTY = (
                        "python",
                        created_property,
                    )
                failure.add_note(f"property rollback failed: {error}")
            raise failure
        _OWNED_SCENE_PROPERTY = identity
    topology_current = _scene_property_identity(
        _TOPOLOGY_SCENE_PROPERTY_NAME
    )
    if _OWNED_TOPOLOGY_SCENE_PROPERTY is not None:
        if _same_scene_property(
            topology_current,
            _OWNED_TOPOLOGY_SCENE_PROPERTY,
        ):
            register_session_cleanup(clear_browser_session_cache)
            return
        raise RuntimeError(
            f"Scene.{_TOPOLOGY_SCENE_PROPERTY_NAME} is no longer owned "
            "by ChemBlender"
        )
    if topology_current is not None:
        raise RuntimeError(
            f"Scene.{_TOPOLOGY_SCENE_PROPERTY_NAME} is already owned"
        )
    created_topology_property = PointerProperty(
        type=_topology.CHEMBLENDER_PG_topology_settings
    )
    setattr(
        bpy.types.Scene,
        _TOPOLOGY_SCENE_PROPERTY_NAME,
        created_topology_property,
    )
    topology_identity = _scene_property_identity(
        _TOPOLOGY_SCENE_PROPERTY_NAME
    )
    if topology_identity is None:
        failure = RuntimeError(
            "Topology Scene property registration failed"
        )
        try:
            delattr(bpy.types.Scene, _TOPOLOGY_SCENE_PROPERTY_NAME)
        except BaseException as error:
            failure.add_note(f"property rollback failed: {error}")
        raise failure
    _OWNED_TOPOLOGY_SCENE_PROPERTY = topology_identity
    register_session_cleanup(clear_browser_session_cache)


def unregister():
    global _OWNED_SCENE_PROPERTY
    global _OWNED_TOPOLOGY_SCENE_PROPERTY
    clear_browser_caches()
    topology_owned = _OWNED_TOPOLOGY_SCENE_PROPERTY
    if (
        topology_owned is not None
        and _same_scene_property(
            _scene_property_identity(_TOPOLOGY_SCENE_PROPERTY_NAME),
            topology_owned,
        )
    ):
        delattr(bpy.types.Scene, _TOPOLOGY_SCENE_PROPERTY_NAME)
    _OWNED_TOPOLOGY_SCENE_PROPERTY = None
    owned = _OWNED_SCENE_PROPERTY
    if owned is not None:
        if _same_scene_property(
            _scene_property_identity(_SCENE_PROPERTY_NAME),
            owned,
        ):
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
        _OWNED_SCENE_PROPERTY = None
    unregister_session_cleanup(clear_browser_session_cache)


__all__ = (
    "CHEMBLENDER_OT_apply_frame_force",
    "CHEMBLENDER_OT_apply_substructure_category",
    "CHEMBLENDER_OT_project_browser_page",
    "CHEMBLENDER_PG_project_browser",
    "CHEMBLENDER_PG_project_browser_row",
    "CHEMBLENDER_PT_project_browser",
    "CHEMBLENDER_UL_project_rows",
    "presentation_view_records",
    "refresh_project_browser",
    "draw_substructure_controls",
    "substructure_category",
    "synchronize_browser_selection",
)
