"""Small Blender properties and in-memory state for Project Browser."""

from dataclasses import dataclass
from uuid import UUID

import bpy
from bpy.props import StringProperty
from cbq_core.symmetry_comparison import compare_symmetry

from cbq_core.model import AtomicProperty
from cbq_core.model import Structure
from cbq_core.model import SymmetryResult
from cbq_core.session import ProjectSession
from .session import (
    get_scene_session,
    register_session_cleanup,
    register_session_mutation,
    unregister_session_cleanup,
    unregister_session_mutation,
)


_PROJECT_UI_STATES = {}
_SCENE_PROPERTY_NAME = "chemblender_project_browser"
_FATAL_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    MemoryError,
)


def active_session_view(context, session):
    obj = context.active_object
    if obj is None and session.active_view_object_name:
        obj = context.scene.objects.get(session.active_view_object_name)
    return obj


def symmetry_comparison_rows(structure, derived=None):
    if not isinstance(structure, Structure) or structure.periodic is None:
        raise TypeError("structure must be a periodic Structure")
    if derived is None:
        return (
            ("Status", "Not included in CBQ"),
            ("Symprec", "Not included in CBQ"),
            ("Angle tolerance", "Not included in CBQ"),
            ("Standardized Structure", "Not included in CBQ"),
        )
    if (
        not isinstance(derived, SymmetryResult)
        or derived.structure_id != structure.id
    ):
        raise ValueError("derived symmetry must belong to structure")
    comparison = compare_symmetry(
        structure.periodic.declared_symmetry,
        derived,
        setting_transformation=derived.transformation_matrix,
    )
    angle = (
        "automatic"
        if derived.angle_tolerance == -1.0
        else f"{derived.angle_tolerance:g}°"
    )
    return (
        ("Status", comparison.status.replace("_", " ").title()),
        ("Symprec", f"{derived.symprec:g} Å"),
        ("Angle tolerance", angle),
        ("Standardized Structure", str(derived.standardized_structure_id)),
        ("Details", "; ".join(comparison.details)),
    )


def crystal_symmetry_property_sections(structure, derived=None):
    if not isinstance(structure, Structure) or structure.periodic is None:
        raise TypeError("structure must be a periodic Structure")
    if derived is not None and (
        not isinstance(derived, SymmetryResult)
        or derived.structure_id != structure.id
    ):
        raise ValueError("derived symmetry must belong to structure")
    declared = structure.periodic.declared_symmetry
    return {
        "declared": (
            ("Name", declared.name or "Not declared"),
            (
                "International number",
                (
                    str(declared.international_number)
                    if declared.international_number is not None
                    else "Not declared"
                ),
            ),
            ("Hall symbol", declared.hall_symbol or "Not declared"),
            ("Operations", str(len(declared.operations))),
        ),
        "derived": (
            (
                "International",
                (
                    f"{derived.international_symbol} "
                    f"(No. {derived.international_number})"
                    if derived is not None
                    else "Not derived"
                ),
            ),
            (
                "Hall symbol",
                derived.hall_symbol if derived is not None else "Not derived",
            ),
        ),
        "comparison": symmetry_comparison_rows(structure, derived),
    }


class CHEMBLENDER_OT_view_standardized_structure(bpy.types.Operator):
    bl_idname = "chemblender.view_standardized_structure"
    bl_label = "View Standardized Structure"
    bl_description = "Create a view without replacing the source Structure"

    symmetry_result_id: StringProperty()

    def execute(self, context):
        session = None
        view = None
        remove_view = None
        previous_entity_id = None
        previous_view_name = ""
        previous_active = context.active_object
        active_selected = (
            previous_active.select_get()
            if previous_active is not None
            else False
        )
        browser = getattr(
            context.scene,
            "chemblender_project_browser",
            None,
        )
        previous_browser_entity_id = (
            browser.active_entity_id if browser is not None else None
        )
        try:
            session = get_scene_session(context.scene)
            previous_entity_id = session.active_entity_id
            previous_view_name = session.active_view_object_name
            result_id = UUID(self.symmetry_result_id)
            result = session.project.symmetry_results.get(result_id)
            if not isinstance(result, SymmetryResult):
                raise ValueError("symmetry result is no longer available")
            structure = session.project.structures.get(
                result.standardized_structure_id
            )
            if not isinstance(structure, Structure):
                raise ValueError("standardized Structure is no longer available")
            topology = next(
                (
                    session.project.topologies[topology_id]
                    for topology_id in structure.topology_ids
                    if topology_id in session.project.topologies
                ),
                None,
            )
            from ..views import (
                create_periodic_structure_view,
                remove_structure_view,
            )

            remove_view = remove_structure_view
            view = create_periodic_structure_view(
                structure,
                topology,
                name=f"Standardized {str(structure.id)[:8]}",
                collection=context.collection,
            )
            if previous_active is not None and previous_active is not view:
                previous_active.select_set(False)
            view.select_set(True)
            context.view_layer.objects.active = view
            session.active_entity_id = structure.id
            session.active_view_object_name = view.name
            if browser is not None:
                browser.active_entity_id = str(structure.id)
            advance_browser_revision(session)
        except BaseException as error:
            if view is not None and remove_view is not None:
                try:
                    remove_view(view)
                except BaseException as cleanup_error:
                    error.add_note(
                        f"standardized View cleanup failed: {cleanup_error}"
                    )
            if session is not None:
                session.active_entity_id = previous_entity_id
                session.active_view_object_name = previous_view_name
            if browser is not None:
                browser.active_entity_id = previous_browser_entity_id
            try:
                if previous_active is not None:
                    previous_active.select_set(active_selected)
                context.view_layer.objects.active = previous_active
            except BaseException as rollback_error:
                error.add_note(
                    f"source View rollback failed: {rollback_error}"
                )
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


def _selective_dynamics(project, structure_id):
    return next(
        (
            value
            for value in project.datasets.values()
            if (
                isinstance(value, AtomicProperty)
                and value.structure_id == structure_id
                and value.semantic_role == "selective_dynamics"
            )
        ),
        None,
    )


class CHEMBLENDER_OT_toggle_selective_constraints(bpy.types.Operator):
    bl_idname = "chemblender.toggle_selective_constraints"
    bl_label = "Toggle Selective Constraints"
    bl_description = "Show or hide the active Structure constraint markers"

    def execute(self, context):
        session = get_scene_session(context.scene)
        obj = context.active_object
        if obj is None and session.active_view_object_name:
            obj = context.scene.objects.get(session.active_view_object_name)
        try:
            structure = session.project.structures.get(
                session.active_entity_id
            )
            if not isinstance(structure, Structure):
                raise ValueError("select a Structure")
            if _selective_dynamics(session.project, structure.id) is None:
                raise ValueError("selected Structure has no Selective Dynamics")
            if (
                obj is None
                or obj.get("cb_structure_id") != str(structure.id)
            ):
                raise ValueError("activate the matching Structure view")
            marker_name = obj.get("cb_selective_marker_object")
            marker = (
                bpy.data.objects.get(marker_name)
                if isinstance(marker_name, str)
                else None
            )
            if marker is None:
                raise ValueError("Structure view has no constraint marker")
            visible = marker.hide_get()
            marker.hide_set(not visible)
            obj["cb_selective_constraints_visible"] = visible
        except (AttributeError, TypeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        session.active_view_object_name = obj.name
        return {"FINISHED"}


def draw_selective_dynamics_properties(layout, project, structure):
    import numpy

    dataset = _selective_dynamics(project, structure.id)
    if dataset is None:
        return
    constrained = int((~numpy.asarray(dataset.data.values)).any(axis=1).sum())
    box = layout.box()
    box.label(
        text=f"Selective Dynamics: {constrained} constrained atom(s)"
    )
    box.operator(
        CHEMBLENDER_OT_toggle_selective_constraints.bl_idname,
        icon="HIDE_OFF",
    )


def draw_crystal_symmetry_properties(layout, structure, derived=None):
    sections = crystal_symmetry_property_sections(structure, derived)
    for title in ("declared", "derived", "comparison"):
        box = layout.box()
        box.label(text=f"{title.title()} Symmetry")
        for name, value in sections[title]:
            box.label(text=f"{name}: {value}")
    if derived is not None:
        button = layout.operator(
            CHEMBLENDER_OT_view_standardized_structure.bl_idname,
            icon="MESH_DATA",
        )
        button.symmetry_result_id = str(derived.id)


@dataclass(slots=True)
class ProjectUIState:
    revision_prompts: tuple = ()
    diagnostics_report: dict | None = None
    diagnostic_index: int = 0
    project_link_inspection_only: bool = False
    show_project_link_diagnostics: bool = False
    browser_revision: int = 0


def _require_session(session):
    if type(session) is not ProjectSession:
        raise TypeError("session must be a ProjectSession")


def get_project_ui_state(session):
    _require_session(session)
    return _PROJECT_UI_STATES.setdefault(session.id, ProjectUIState())


def advance_browser_revision(session):
    """Invalidate presentation projections after a successful UI mutation."""
    state = get_project_ui_state(session)
    state.browser_revision += 1
    return state.browser_revision


def clear_project_ui_state(session):
    _require_session(session)
    _PROJECT_UI_STATES.pop(session.id, None)


def _clear_all_states():
    _PROJECT_UI_STATES.clear()


def _load_pre_handler(_dummy):
    _clear_all_states()


def _register_handler(callbacks, handler):
    while handler in callbacks:
        callbacks.remove(handler)
    callbacks.append(handler)


def _remove_handler(callbacks, handler):
    while handler in callbacks:
        callbacks.remove(handler)


def _scene_property_identity(name=_SCENE_PROPERTY_NAME):
    scene_type = bpy.types.Scene
    rna = getattr(scene_type, "bl_rna", None)
    properties = getattr(rna, "properties", None)
    rna_property = None
    if properties is not None:
        try:
            rna_property = properties.get(name)
        except (AttributeError, KeyError, TypeError):
            try:
                rna_property = properties[name]
            except (KeyError, TypeError):
                pass
    if rna_property is not None:
        as_pointer = getattr(rna_property, "as_pointer", None)
        if callable(as_pointer):
            pointer = as_pointer()
            if type(pointer) is int and pointer:
                return ("rna", pointer)
    if hasattr(scene_type, name):
        return (
            "python",
            getattr(scene_type, name),
        )
    return None


def _same_scene_property(left, right):
    if left is None or right is None or left[0] != right[0]:
        return False
    if left[0] == "rna":
        return left[1] == right[1]
    return left[1] is right[1]


def register():
    bpy.app.handlers.persistent(_load_pre_handler)
    _register_handler(bpy.app.handlers.load_pre, _load_pre_handler)
    register_session_cleanup(clear_project_ui_state)
    register_session_mutation(advance_browser_revision)


def unregister():
    _remove_handler(bpy.app.handlers.load_pre, _load_pre_handler)
    _clear_all_states()
    unregister_session_cleanup(clear_project_ui_state)
    unregister_session_mutation(advance_browser_revision)
