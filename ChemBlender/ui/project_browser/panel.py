"""Blender Project Browser UIList and small RNA projection."""

import importlib
import json
import operator
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
    get_quick_import_state,
)
from ..session import get_scene_session
from ...core import (
    AtomFrameProperty,
    ConformerSet,
    FrameSet,
    MolecularRecord,
    Structure,
)
from ...dataset_view import write_vector_view
from .model import (
    BrowserMode,
    ViewRecord,
    _browser_entity_ids,
    build_browser_rows,
)

_scientific_edit = importlib.import_module("..scientific_edit", __package__)
_topology = importlib.import_module("..topology", __package__)
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
    "record_property_column": "PROPERTIES",
    "structure": "MESH_DATA",
    "topology_record": "MOD_WIREFRAME",
    "view": "HIDE_OFF",
}
_SCENE_PROPERTY_NAME = "chemblender_project_browser"
_TOPOLOGY_SCENE_PROPERTY_NAME = "chemblender_topology"
_OWNED_SCENE_PROPERTY = None
_OWNED_TOPOLOGY_SCENE_PROPERTY = None


def _selection_changed(state, context):
    synchronize_browser_selection(get_scene_session(context.scene), state)


def _projection_changed(_state, context):
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
    selected_index: IntProperty(default=0, update=_selection_changed)
    active_entity_id: StringProperty()
    total_row_count: IntProperty(default=0)
    rows: CollectionProperty(type=CHEMBLENDER_PG_project_browser_row)


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
                )
            )
    return tuple(records)


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
    )
    selected = _project_entity_id(
        session.project,
        settings.active_entity_id,
    )
    selected_id = str(selected) if selected is not None else ""
    settings.total_row_count = len(rows)
    _copy_rows(settings.rows, rows[:_BROWSER_RNA_ROW_LIMIT])
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
            row.label(text=item.quality.title())


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
        layout.template_list(
            "CHEMBLENDER_UL_project_rows",
            "",
            settings,
            "rows",
            settings,
            "selected_index",
        )
        if settings.total_row_count > len(settings.rows):
            layout.label(
                text=(
                    f"Showing {len(settings.rows)} of "
                    f"{settings.total_row_count} rows; refine Search or Filter"
                ),
                icon="INFO",
            )
        if settings.active_entity_id:
            layout.label(text=f"Selected: {settings.active_entity_id}")
            selected = session.project.datasets.get(session.active_entity_id)
            selected_record = session.project.molecular_records.get(
                session.active_entity_id
            )
            if (
                isinstance(selected, AtomFrameProperty)
                and selected.semantic_role == "atomic_force"
            ):
                layout.operator(
                    CHEMBLENDER_OT_apply_frame_force.bl_idname,
                    icon="FORCE_FORCE",
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
        if _same_scene_property(current, _OWNED_SCENE_PROPERTY):
            topology_current = _scene_property_identity(
                _TOPOLOGY_SCENE_PROPERTY_NAME
            )
            if not _same_scene_property(
                topology_current,
                _OWNED_TOPOLOGY_SCENE_PROPERTY,
            ):
                raise RuntimeError(
                    f"Scene.{_TOPOLOGY_SCENE_PROPERTY_NAME} is no longer "
                    "owned by ChemBlender"
                )
            return
        raise RuntimeError(
            f"Scene.{_SCENE_PROPERTY_NAME} is no longer owned by ChemBlender"
        )
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
                "property replaced before rollback; foreign property preserved"
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


def unregister():
    global _OWNED_SCENE_PROPERTY
    global _OWNED_TOPOLOGY_SCENE_PROPERTY
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
    if owned is None:
        return
    if _same_scene_property(
        _scene_property_identity(_SCENE_PROPERTY_NAME),
        owned,
    ):
        delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
    _OWNED_SCENE_PROPERTY = None


__all__ = (
    "CHEMBLENDER_OT_apply_frame_force",
    "CHEMBLENDER_PG_project_browser",
    "CHEMBLENDER_PG_project_browser_row",
    "CHEMBLENDER_PT_project_browser",
    "CHEMBLENDER_UL_project_rows",
    "presentation_view_records",
    "refresh_project_browser",
    "synchronize_browser_selection",
)
