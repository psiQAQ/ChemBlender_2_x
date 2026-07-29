"""Small Blender properties and in-memory state for Quick Import."""

from dataclasses import dataclass
import importlib.util

import bpy
from bpy.props import EnumProperty, FloatProperty, PointerProperty, StringProperty

from ..core import AtomicProperty, Structure, SymmetryResult
from ..core.import_pipeline.preview import ImportPreview
from ..core.import_pipeline.request import ValidationMode
from ..core.import_pipeline.staging import StagedImportSession
from ..core.session import ProjectSession
from ..core.spglib_adapter import SpglibDependencyError, derive_symmetry
from .session import (
    get_scene_session,
    register_session_cleanup,
    register_session_mutation,
    unregister_session_cleanup,
    unregister_session_mutation,
)


VALIDATION_MODE_ITEMS = tuple(
    (mode.value, mode.value.title(), "")
    for mode in ValidationMode
)
_QUICK_IMPORT_STATES = {}
_SCENE_PROPERTY_NAME = "chemblender_quick_import"
_OWNED_SCENE_PROPERTY = None


class CHEMBLENDER_PG_quick_import(bpy.types.PropertyGroup):
    validation_mode: EnumProperty(
        name="Validation",
        items=VALIDATION_MODE_ITEMS,
        default=ValidationMode.BALANCED.value,
    )
    recent_summary: StringProperty(name="Recent Preview", default="")


def spglib_action_availability():
    try:
        available = importlib.util.find_spec("spglib") is not None
    except (ImportError, AttributeError, ValueError) as error:
        return False, f"spglib availability check failed: {error}"
    return (
        (True, "")
        if available
        else (False, "spglib is not installed in the core/worker environment")
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
    available, reason = spglib_action_availability()
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
        "derive_available": available,
        "dependency_reason": reason,
    }


class CHEMBLENDER_OT_derive_crystal_symmetry(bpy.types.Operator):
    bl_idname = "chemblender.derive_crystal_symmetry"
    bl_label = "Derive Symmetry"
    bl_description = "Derive symmetry without changing the source Structure"

    symprec: FloatProperty(name="Symprec", default=1.0e-5, min=1.0e-12)
    angle_tolerance: FloatProperty(name="Angle Tolerance", default=-1.0, min=-1.0)

    def execute(self, context):
        session = get_scene_session(context.scene)
        structure = session.project.structures.get(session.active_entity_id)
        available, reason = spglib_action_availability()
        if not available:
            self.report({"ERROR"}, reason)
            return {"CANCELLED"}
        try:
            if not isinstance(structure, Structure) or structure.periodic is None:
                raise ValueError("select a periodic Structure")
            existing = next(
                (
                    result
                    for result in session.project.symmetry_results.values()
                    if (
                        result.structure_id == structure.id
                        and result.symprec == self.symprec
                        and result.angle_tolerance == self.angle_tolerance
                    )
                ),
                None,
            )
            if existing is None:
                session.project.commit(
                    derive_symmetry(
                        structure,
                        symprec=self.symprec,
                        angle_tolerance=self.angle_tolerance,
                    )
                )
                session.mark_dirty("symmetry")
        except (
            SpglibDependencyError,
            TypeError,
            ValueError,
        ) as error:
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
    dataset = _selective_dynamics(project, structure.id)
    if dataset is None:
        return
    constrained = int((~dataset.data.values).any(axis=1).sum())
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
    for title in ("declared", "derived"):
        box = layout.box()
        box.label(text=f"{title.title()} Symmetry")
        for name, value in sections[title]:
            box.label(text=f"{name}: {value}")
    row = layout.row()
    row.enabled = sections["derive_available"]
    row.operator(CHEMBLENDER_OT_derive_crystal_symmetry.bl_idname)
    if sections["dependency_reason"]:
        layout.label(text=sections["dependency_reason"], icon="INFO")


@dataclass(slots=True)
class QuickImportUIState:
    staging_session: StagedImportSession | None = None
    preview: ImportPreview | None = None
    active_job: object | None = None
    conflicts: tuple = ()
    grouping_suggestions: tuple = ()
    conformer_grouping_suggestions: tuple | None = None
    browser_revision: int = 0


def _require_session(session):
    if type(session) is not ProjectSession:
        raise TypeError("session must be a ProjectSession")


def get_quick_import_state(session):
    _require_session(session)
    return _QUICK_IMPORT_STATES.setdefault(session.id, QuickImportUIState())


def advance_browser_revision(session):
    """Invalidate presentation projections after a successful UI mutation."""
    state = get_quick_import_state(session)
    state.browser_revision += 1
    return state.browser_revision


def create_quick_import_staging(session):
    _require_session(session)
    state = get_quick_import_state(session)
    discard_quick_import_preview(session)
    staging = StagedImportSession.create(
        temp_parent=session.temporary_root.parent.parent
    )
    state.staging_session = staging
    return staging


def store_quick_import_preview(
    session,
    staging_session,
    preview,
    *,
    conformer_grouping_suggestions=None,
):
    _require_session(session)
    if type(staging_session) is not StagedImportSession:
        raise TypeError("staging_session must be a StagedImportSession")
    if type(preview) is not ImportPreview:
        raise TypeError("preview must be an ImportPreview")
    if (
        conformer_grouping_suggestions is not None
        and type(conformer_grouping_suggestions) is not tuple
    ):
        raise TypeError("conformer_grouping_suggestions must be a tuple")
    if preview.session_id != staging_session.id:
        raise ValueError("preview must belong to staging_session")
    state = get_quick_import_state(session)
    if state.staging_session is not staging_session:
        raise ValueError("staging_session is not owned by session")
    state.preview = preview
    state.conflicts = ()
    state.grouping_suggestions = ()
    state.conformer_grouping_suggestions = conformer_grouping_suggestions


def store_quick_import_job(session, staging_session, job):
    _require_session(session)
    state = get_quick_import_state(session)
    if state.staging_session is not staging_session:
        raise ValueError("staging_session is not owned by session")
    if state.active_job is not None:
        raise RuntimeError("session already has an active Quick Import job")
    state.active_job = job


def finish_quick_import_job(session, job):
    _require_session(session)
    state = _QUICK_IMPORT_STATES.get(session.id)
    if state is None or state.active_job is not job:
        raise RuntimeError("Quick Import job is not owned by session")
    state.active_job = None


def _add_failure(failure, error, label):
    if failure is None:
        return error
    failure.add_note(f"{label}: {error}")
    return failure


def _clear_owned_state(session_id, state):
    failure = None
    worker_stopped = True
    job = state.active_job
    if job is not None:
        try:
            job.cancel()
        except BaseException as error:
            failure = _add_failure(failure, error, "job cancellation failed")
        try:
            worker_stopped = job.join(timeout=0.5)
            if not worker_stopped:
                raise RuntimeError("Quick Import job did not stop")
        except BaseException as error:
            worker_stopped = False
            failure = _add_failure(failure, error, "job join failed")
        if worker_stopped:
            try:
                job.release_ui()
            except BaseException as error:
                failure = _add_failure(failure, error, "job UI cleanup failed")
            else:
                state.active_job = None
    if worker_stopped and state.staging_session is not None:
        try:
            state.staging_session.discard()
        except BaseException as error:
            failure = _add_failure(failure, error, "staging cleanup failed")
    if failure is None:
        _QUICK_IMPORT_STATES.pop(session_id, None)
    else:
        raise failure


def clear_quick_import_state(session):
    _require_session(session)
    state = _QUICK_IMPORT_STATES.get(session.id)
    if state is not None:
        _clear_owned_state(session.id, state)


def discard_quick_import_preview(session):
    """Discard only staged import data while preserving UI revision state."""
    _require_session(session)
    state = _QUICK_IMPORT_STATES.get(session.id)
    if state is None:
        return
    if state.active_job is not None:
        raise RuntimeError("cannot discard while an import job is active")
    if state.staging_session is not None:
        state.staging_session.discard()
    state.staging_session = None
    state.preview = None
    state.conflicts = ()
    state.grouping_suggestions = ()
    state.conformer_grouping_suggestions = None


def _clear_all_states():
    failure = None
    for session_id, state in tuple(_QUICK_IMPORT_STATES.items()):
        try:
            _clear_owned_state(session_id, state)
        except BaseException as error:
            failure = _add_failure(failure, error, "Quick Import cleanup failed")
    if failure is not None:
        raise failure


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


def _register_scene_property():
    global _OWNED_SCENE_PROPERTY
    current = _scene_property_identity()
    if _OWNED_SCENE_PROPERTY is not None:
        if _same_scene_property(current, _OWNED_SCENE_PROPERTY):
            return
        raise RuntimeError(
            f"Scene.{_SCENE_PROPERTY_NAME} is no longer owned by ChemBlender"
        )
    if current is not None:
        raise RuntimeError(
            f"Scene.{_SCENE_PROPERTY_NAME} is already owned"
        )
    setattr(
        bpy.types.Scene,
        _SCENE_PROPERTY_NAME,
        PointerProperty(type=CHEMBLENDER_PG_quick_import),
    )
    identity = _scene_property_identity()
    if identity is None:
        failure = RuntimeError(
            "Quick Import Scene property registration failed"
        )
        try:
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
        except BaseException as error:
            failure.add_note(f"property rollback failed: {error}")
        raise failure
    _OWNED_SCENE_PROPERTY = identity


def _unregister_scene_property():
    global _OWNED_SCENE_PROPERTY
    owned = _OWNED_SCENE_PROPERTY
    if owned is None:
        return
    if _same_scene_property(_scene_property_identity(), owned):
        delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
    _OWNED_SCENE_PROPERTY = None


def register():
    _register_scene_property()
    bpy.app.handlers.persistent(_load_pre_handler)
    _register_handler(bpy.app.handlers.load_pre, _load_pre_handler)
    register_session_cleanup(clear_quick_import_state)
    register_session_mutation(advance_browser_revision)


def unregister():
    _remove_handler(bpy.app.handlers.load_pre, _load_pre_handler)
    _clear_all_states()
    unregister_session_cleanup(clear_quick_import_state)
    unregister_session_mutation(advance_browser_revision)
    _unregister_scene_property()
