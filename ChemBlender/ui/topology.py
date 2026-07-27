"""Topology proposal decisions and Blender controls."""

from dataclasses import dataclass, replace
import json
from uuid import UUID

from ..core import ProjectSession, QualityStatus, TopologySource
from ..core.topology.infer import (
    TopologyInferenceSettings,
    infer_distance_topology,
)
from ..core.topology.periodic import infer_periodic_topology


_SOURCE_ORDER = {
    TopologySource.EXPLICIT_FILE.value: 0,
    TopologySource.RDKIT_SANITIZED.value: 1,
    TopologySource.USER_EDITED.value: 2,
    TopologySource.DISTANCE_INFERRED.value: 3,
}
_SCENE_PROPERTY_NAME = "chemblender_topology"


@dataclass(frozen=True, slots=True)
class TopologyChoice:
    topology_id: UUID
    revision: str
    source: str
    quality: str
    edge_count: int
    parameters: tuple[tuple[str, object], ...]
    view_count: int
    accepted: bool
    rejected: bool


def _uuid_text(value, name):
    if type(value) is not str or not value:
        raise TypeError(f"{name} must be a non-empty UUID string")
    try:
        return UUID(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a UUID string") from error


def _decode_decisions(encoded):
    if type(encoded) is not str:
        raise TypeError("decisions_json must be str")
    try:
        document = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise ValueError("decisions_json must contain valid JSON") from error
    if type(document) is not dict:
        raise TypeError("topology decisions must be an object")
    decisions = {}
    for structure_text, entry in document.items():
        structure_id = _uuid_text(structure_text, "decision structure id")
        if type(entry) is not dict or set(entry) != {"accepted", "rejected"}:
            raise ValueError(
                "each topology decision must contain accepted and rejected"
            )
        accepted = entry["accepted"]
        if accepted is not None:
            accepted = _uuid_text(accepted, "accepted topology id")
        rejected_values = entry["rejected"]
        if type(rejected_values) is not list:
            raise TypeError("rejected topology ids must be a list")
        rejected = tuple(
            _uuid_text(value, "rejected topology id")
            for value in rejected_values
        )
        if len(set(rejected)) != len(rejected):
            raise ValueError("rejected topology ids must not repeat")
        if accepted in rejected:
            raise ValueError("accepted topology cannot also be rejected")
        decisions[structure_id] = (accepted, rejected)
    return decisions


def _encode_decisions(decisions):
    return json.dumps(
        {
            str(structure_id): {
                "accepted": (
                    None if accepted is None else str(accepted)
                ),
                "rejected": [
                    str(topology_id)
                    for topology_id in sorted(rejected, key=str)
                ],
            }
            for structure_id, (accepted, rejected) in sorted(
                decisions.items(), key=lambda item: str(item[0])
            )
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _require_structure(project, structure_id):
    if type(structure_id) is not UUID:
        raise TypeError("structure_id must be UUID")
    try:
        return project.structures[structure_id]
    except KeyError as error:
        raise ValueError("structure_id is not in the project") from error


def _validate_decisions(project, decisions):
    for structure_id, (accepted, rejected) in decisions.items():
        _require_structure(project, structure_id)
        for topology_id in (
            *((accepted,) if accepted is not None else ()),
            *rejected,
        ):
            topology = project.topologies.get(topology_id)
            if topology is None:
                raise ValueError("topology decision is not in the project")
            if topology.structure_id != structure_id:
                raise ValueError(
                    "topology decision belongs to another structure"
                )


def topology_choices(
    project,
    structure_id,
    decisions_json="{}",
    view_usage=None,
):
    _require_structure(project, structure_id)
    decisions = _decode_decisions(decisions_json)
    _validate_decisions(project, decisions)
    accepted, rejected = decisions.get(structure_id, (None, ()))
    usage = {} if view_usage is None else dict(view_usage)
    if any(
        type(topology_id) is not UUID
        or type(count) is not int
        or isinstance(count, bool)
        or count < 0
        for topology_id, count in usage.items()
    ):
        raise ValueError("view_usage must map topology UUIDs to counts")
    choices = tuple(
        TopologyChoice(
            topology.id,
            topology.revision,
            topology.source_kind.value,
            topology.quality_status.value,
            topology.bond_indices.shape[0],
            topology.inference_parameters,
            usage.get(topology.id, 0),
            topology.id == accepted,
            topology.id in rejected,
        )
        for topology in project.topologies.values()
        if topology.structure_id == structure_id
    )
    known = {choice.topology_id for choice in choices}
    if accepted is not None and accepted not in known:
        raise ValueError("accepted topology is not in the project")
    if not set(rejected).issubset(known):
        raise ValueError("rejected topology is not in the project")
    return tuple(
        sorted(
            choices,
            key=lambda choice: (
                not choice.accepted,
                _SOURCE_ORDER[choice.source],
                choice.quality,
                str(choice.topology_id),
            ),
        )
    )


def suggested_topology_id(choices):
    choices = tuple(choices)
    if any(type(choice) is not TopologyChoice for choice in choices):
        raise TypeError("choices must contain TopologyChoice values")
    accepted = next((choice for choice in choices if choice.accepted), None)
    if accepted is not None:
        return accepted.topology_id
    return next(
        (
            choice.topology_id
            for choice in choices
            if (
                not choice.rejected
                and choice.quality != QualityStatus.INVALID.value
            )
        ),
        None,
    )


def record_topology_decision(
    project,
    decisions_json,
    structure_id,
    topology_id,
    *,
    accept,
):
    _require_structure(project, structure_id)
    if type(topology_id) is not UUID:
        raise TypeError("topology_id must be UUID")
    if type(accept) is not bool:
        raise TypeError("accept must be bool")
    try:
        topology = project.topologies[topology_id]
    except KeyError as error:
        raise ValueError("topology_id is not in the project") from error
    if topology.structure_id != structure_id:
        raise ValueError("topology does not belong to the selected structure")
    decisions = _decode_decisions(decisions_json)
    _validate_decisions(project, decisions)
    accepted, rejected = decisions.get(structure_id, (None, ()))
    rejected = set(rejected)
    if accept:
        accepted = topology_id
        rejected.discard(topology_id)
    else:
        if accepted == topology_id:
            accepted = None
        rejected.add(topology_id)
    decisions[structure_id] = (accepted, tuple(rejected))
    return _encode_decisions(decisions)


def compute_topology_proposal(session, structure_id, settings=None):
    if not isinstance(session, ProjectSession):
        raise TypeError("session must be a ProjectSession")
    reference = _require_structure(session.project, structure_id)
    if settings is None:
        settings = TopologyInferenceSettings()
    if not isinstance(settings, TopologyInferenceSettings):
        raise TypeError("settings must be TopologyInferenceSettings")
    periodic = (
        reference.periodic is not None
        and any(reference.periodic.pbc)
    )
    settings = replace(settings, periodic=periodic)
    batch = (
        infer_periodic_topology(reference, settings)
        if periodic
        else infer_distance_topology(reference, settings)
    )
    proposal = batch.topologies[0]
    existing = session.project.topologies.get(proposal.id)
    if existing is not None:
        if (
            existing.revision != proposal.revision
            or existing.structure_id != proposal.structure_id
        ):
            raise RuntimeError("deterministic topology identity collision")
        return existing, False
    session.project.commit(batch)
    session.mark_dirty("topology")
    return proposal, True


try:
    import bpy
    from bpy.props import (
        EnumProperty,
        FloatProperty,
        IntProperty,
        StringProperty,
    )
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    class CHEMBLENDER_PG_topology_settings(bpy.types.PropertyGroup):
        covalent_scale: FloatProperty(
            name="Covalent Scale",
            default=1.15,
            min=0.01,
        )
        tolerance_angstrom: FloatProperty(
            name="Tolerance (Å)",
            default=0.20,
            min=0.0,
        )
        minimum_distance_angstrom: FloatProperty(
            name="Minimum Distance (Å)",
            default=0.25,
            min=0.001,
        )
        max_coordination_default: IntProperty(
            name="Maximum Coordination",
            default=8,
            min=1,
        )
        metal_mode: EnumProperty(
            name="Metal Mode",
            items=(("coordination", "Coordination", ""),),
            default="coordination",
        )
        proposal_topology_id: StringProperty(
            options={"HIDDEN", "SKIP_SAVE"}
        )
        decisions_json: StringProperty(default="{}", options={"HIDDEN"})


    def _selected_structure(project, entity_id):
        if entity_id in project.structures:
            return project.structures[entity_id]
        topology = project.topologies.get(entity_id)
        return (
            None
            if topology is None
            else project.structures.get(topology.structure_id)
        )


    def _operator_context(context):
        from .session import get_scene_session

        session = get_scene_session(context.scene)
        reference = _selected_structure(
            session.project,
            session.active_entity_id,
        )
        if reference is None:
            raise ValueError("select a Structure or topology in Project Browser")
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        return session, reference, settings


    def _inference_settings(settings):
        return TopologyInferenceSettings(
            covalent_scale=settings.covalent_scale,
            tolerance_angstrom=settings.tolerance_angstrom,
            minimum_distance_angstrom=settings.minimum_distance_angstrom,
            max_coordination_default=settings.max_coordination_default,
            metal_mode=settings.metal_mode,
        )


    def topology_view_usage(scene):
        usage = {}
        for obj in scene.objects:
            value = obj.get("cb_topology_id")
            if type(value) is not str:
                continue
            try:
                topology_id = UUID(value)
            except ValueError:
                continue
            usage[topology_id] = usage.get(topology_id, 0) + 1
        return usage


    def _find_structure_view(context, session, structure_id):
        active = context.active_object
        candidates = (
            active,
            context.scene.objects.get(session.active_view_object_name)
            if session.active_view_object_name
            else None,
            *context.scene.objects,
        )
        for obj in candidates:
            if (
                obj is not None
                and obj.get("cb_structure_contract") == "structure_view_v1"
                and obj.get("cb_structure_id") == str(structure_id)
            ):
                return obj
        return None


    def _switch_view(context, session, reference, topology, decision):
        from ..views import update_structure_view_topology

        obj = _find_structure_view(context, session, reference.id)
        if obj is None:
            return None
        update_structure_view_topology(obj, reference, topology)
        obj["cb_topology_decision"] = decision
        session.active_view_object_name = obj.name
        return obj


    def _topology_id(value):
        try:
            return UUID(value)
        except (TypeError, ValueError) as error:
            raise ValueError("topology_id must be a UUID") from error


    def _report_failure(operator, error):
        operator.report({"ERROR"}, str(error))
        return {"CANCELLED"}


    class CHEMBLENDER_OT_compute_topology(bpy.types.Operator):
        bl_idname = "chemblender.compute_topology"
        bl_label = "Compute Topology"
        bl_description = "Create a distance-inferred topology proposal"

        def execute(self, context):
            try:
                session, reference, settings = _operator_context(context)
                proposal, created = compute_topology_proposal(
                    session,
                    reference.id,
                    _inference_settings(settings),
                )
                settings.proposal_topology_id = str(proposal.id)
                if created:
                    from .properties import advance_browser_revision

                    advance_browser_revision(session)
                self.report(
                    {"INFO"},
                    "Topology proposal created"
                    if created
                    else "Matching topology proposal already exists",
                )
                return {"FINISHED"}
            except Exception as error:
                return _report_failure(self, error)


    class _TopologyOperator:
        topology_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

        def _values(self, context):
            session, reference, settings = _operator_context(context)
            topology_id = _topology_id(self.topology_id)
            try:
                topology = session.project.topologies[topology_id]
            except KeyError as error:
                raise ValueError("topology is no longer in the project") from error
            if topology.structure_id != reference.id:
                raise ValueError("topology does not belong to selected Structure")
            return session, reference, settings, topology


    class CHEMBLENDER_OT_accept_topology(
        _TopologyOperator,
        bpy.types.Operator,
    ):
        bl_idname = "chemblender.accept_topology"
        bl_label = "Accept Topology"
        bl_description = "Accept this topology for the selected Structure view"

        def execute(self, context):
            try:
                session, reference, settings, topology = self._values(context)
                encoded = record_topology_decision(
                    session.project,
                    settings.decisions_json,
                    reference.id,
                    topology.id,
                    accept=True,
                )
                _switch_view(
                    context,
                    session,
                    reference,
                    topology,
                    "accepted",
                )
                settings.decisions_json = encoded
                settings.proposal_topology_id = ""
                from .properties import advance_browser_revision

                advance_browser_revision(session)
                return {"FINISHED"}
            except Exception as error:
                return _report_failure(self, error)


    class CHEMBLENDER_OT_reject_topology(
        _TopologyOperator,
        bpy.types.Operator,
    ):
        bl_idname = "chemblender.reject_topology"
        bl_label = "Reject Topology"
        bl_description = "Keep this proposal but remove it from suggestions"

        def execute(self, context):
            try:
                session, reference, settings, topology = self._values(context)
                encoded = record_topology_decision(
                    session.project,
                    settings.decisions_json,
                    reference.id,
                    topology.id,
                    accept=False,
                )
                obj = _find_structure_view(context, session, reference.id)
                if (
                    obj is not None
                    and obj.get("cb_topology_id") == str(topology.id)
                ):
                    _switch_view(
                        context,
                        session,
                        reference,
                        None,
                        "rejected",
                    )
                settings.decisions_json = encoded
                if settings.proposal_topology_id == str(topology.id):
                    settings.proposal_topology_id = ""
                from .properties import advance_browser_revision

                advance_browser_revision(session)
                return {"FINISHED"}
            except Exception as error:
                return _report_failure(self, error)


    class CHEMBLENDER_OT_switch_topology(
        _TopologyOperator,
        bpy.types.Operator,
    ):
        bl_idname = "chemblender.switch_topology"
        bl_label = "Switch Topology"
        bl_description = "Change only the active Structure view topology"

        atoms_only: bpy.props.BoolProperty(
            options={"HIDDEN", "SKIP_SAVE"}
        )

        def execute(self, context):
            try:
                session, reference, _settings = _operator_context(context)
                topology = None
                if not self.atoms_only:
                    topology_id = _topology_id(self.topology_id)
                    topology = session.project.topologies.get(topology_id)
                    if topology is None:
                        raise ValueError("topology is no longer in the project")
                    if topology.structure_id != reference.id:
                        raise ValueError(
                            "topology does not belong to selected Structure"
                        )
                obj = _switch_view(
                    context,
                    session,
                    reference,
                    topology,
                    "atoms_only" if topology is None else "preview",
                )
                if obj is None:
                    raise ValueError("selected Structure has no active view")
                from .properties import advance_browser_revision

                advance_browser_revision(session)
                return {"FINISHED"}
            except Exception as error:
                return _report_failure(self, error)


    def draw_topology_controls(layout, context, session):
        reference = _selected_structure(
            session.project,
            session.active_entity_id,
        )
        if reference is None:
            return
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        choices = topology_choices(
            session.project,
            reference.id,
            settings.decisions_json,
            topology_view_usage(context.scene),
        )
        layout.separator()
        layout.label(text="Topology", icon="MOD_WIREFRAME")
        layout.prop(settings, "covalent_scale")
        layout.prop(settings, "tolerance_angstrom")
        layout.prop(settings, "minimum_distance_angstrom")
        layout.prop(settings, "max_coordination_default")
        layout.prop(settings, "metal_mode")
        layout.operator(
            CHEMBLENDER_OT_compute_topology.bl_idname,
            text=(
                "Recompute Proposal"
                if settings.proposal_topology_id
                else "Compute Proposal"
            ),
        )
        for choice in choices:
            box = layout.box()
            box.label(
                text=(
                    f"{choice.source.replace('_', ' ').title()} · "
                    f"{choice.quality.title()} · {choice.edge_count} bonds · "
                    f"{choice.view_count} views"
                ),
                icon="CHECKMARK" if choice.accepted else "MOD_WIREFRAME",
            )
            if choice.parameters:
                box.label(
                    text=", ".join(
                        f"{name}={value}"
                        for name, value in choice.parameters
                    )
                )
            row = box.row(align=True)
            switch = row.operator(
                CHEMBLENDER_OT_switch_topology.bl_idname,
                text="Show",
            )
            switch.topology_id = str(choice.topology_id)
            accept = row.operator(
                CHEMBLENDER_OT_accept_topology.bl_idname,
                text="Accept",
            )
            accept.topology_id = str(choice.topology_id)
            reject = row.operator(
                CHEMBLENDER_OT_reject_topology.bl_idname,
                text="Reject",
            )
            reject.topology_id = str(choice.topology_id)
        atoms_only = layout.operator(
            CHEMBLENDER_OT_switch_topology.bl_idname,
            text="Show Atoms Only",
        )
        atoms_only.atoms_only = True


__all__ = (
    "TopologyChoice",
    "compute_topology_proposal",
    "record_topology_decision",
    "suggested_topology_id",
    "topology_choices",
)
if bpy is not None:
    __all__ += (
        "CHEMBLENDER_OT_accept_topology",
        "CHEMBLENDER_OT_compute_topology",
        "CHEMBLENDER_OT_reject_topology",
        "CHEMBLENDER_OT_switch_topology",
        "CHEMBLENDER_PG_topology_settings",
        "draw_topology_controls",
        "topology_view_usage",
    )
