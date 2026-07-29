"""Biological hierarchy projection and view-only atom filters."""

import json
from math import isclose, isfinite

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)

from ..core import (
    AtomicProperty,
    BiologicalHierarchy,
    FrameSet,
    Structure,
    TopologyRecord,
)
from ..dataset_view import apply_atom_selection
from .. import trajectory_view
from ..views.structure import (
    BIOLOGICAL_NUMERIC_ROLE_SPECS,
    StructureViewSettings,
    _write_attribute,
    biological_point_data,
    default_altloc_mask,
)
from .properties import active_session_view
from .session import get_scene_session


_BALL_STICK_ATOM_LIMIT = 50_000


def biological_numeric_role_items():
    return tuple(
        (role, spec["label"], "")
        for role, spec in BIOLOGICAL_NUMERIC_ROLE_SPECS.items()
    )


def _values(categorical):
    codes = categorical.codes.values
    return tuple(
        None if int(code) == categorical.missing_code
        else categorical.categories[int(code)]
        for code in codes
    )


def biological_selection_indices(
    structure,
    hierarchy,
    datasets=(),
    *,
    chain_id=None,
    residue_start=None,
    residue_end=None,
    residue_name=None,
    atom_name=None,
    altloc=None,
    property_role=None,
    comparison=None,
    threshold=None,
):
    """Return source atom indexes matching the requested hierarchy predicate."""
    projection = biological_point_data(structure, hierarchy, datasets)
    for name, value in (
        ("chain_id", chain_id),
        ("residue_name", residue_name),
        ("atom_name", atom_name),
        ("altloc", altloc),
    ):
        if value is not None and type(value) is not str:
            raise TypeError(f"{name} must be a string or None")
    for name, value in (
        ("residue_start", residue_start),
        ("residue_end", residue_end),
    ):
        if value is not None and type(value) is not int:
            raise TypeError(f"{name} must be an integer or None")
    if (
        residue_start is not None
        and residue_end is not None
        and residue_start > residue_end
    ):
        raise ValueError("residue_start must not exceed residue_end")
    property_filter = any(
        value is not None
        for value in (property_role, comparison, threshold)
    )
    if property_filter:
        if property_role not in BIOLOGICAL_NUMERIC_ROLE_SPECS:
            raise ValueError("property_role is not supported")
        if comparison not in {"greater_equal", "less_equal"}:
            raise ValueError("comparison is not supported")
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not isfinite(threshold)
        ):
            raise ValueError("threshold must be finite")
    residue_indices = tuple(
        int(value) for value in hierarchy.atom_sites.residue_indices.values
    )
    atom_names = _values(structure.atomic_identity.atom_names)
    alternate_locations = _values(hierarchy.atom_sites.alternate_locations)
    selected = []
    property_values = (
        projection[
            BIOLOGICAL_NUMERIC_ROLE_SPECS[property_role]["attribute"]
        ]
        if property_filter
        else None
    )
    property_valid = (
        projection[
            f"{BIOLOGICAL_NUMERIC_ROLE_SPECS[property_role]['attribute']}_valid"
        ]
        if property_filter
        else None
    )
    compare = (
        (lambda value: value >= threshold)
        if comparison == "greater_equal"
        else (lambda value: value <= threshold)
    )
    for index, residue_index in enumerate(residue_indices):
        residue = hierarchy.residues[residue_index]
        chain = hierarchy.chains[residue.chain_index]
        if chain_id is not None and chain.chain_id != chain_id:
            continue
        if (
            residue_start is not None
            and residue.sequence_number < residue_start
        ):
            continue
        if residue_end is not None and residue.sequence_number > residue_end:
            continue
        if residue_name is not None and residue.residue_name != residue_name:
            continue
        if atom_name is not None and atom_names[index] != atom_name:
            continue
        if altloc is not None and (alternate_locations[index] or "") != altloc:
            continue
        if property_filter and (
            not property_valid[index]
            or not compare(property_values[index])
        ):
            continue
        selected.append(index)
    return tuple(
        selected
    )


def resolve_biological_context(project, entity_id):
    """Resolve the current project snapshot from a real selected entity."""
    entity = (
        project.structures.get(entity_id)
        or project.biological_hierarchies.get(entity_id)
        or project.datasets.get(entity_id)
        or project.topologies.get(entity_id)
    )
    if isinstance(entity, Structure):
        structure = entity
    elif isinstance(entity, BiologicalHierarchy):
        structure = project.structures.get(entity.structure_id)
    elif isinstance(entity, (AtomicProperty, FrameSet, TopologyRecord)):
        structure = project.structures.get(entity.structure_id)
    else:
        raise ValueError("selected entity has no biological Structure")
    if not isinstance(structure, Structure):
        raise ValueError("selected entity has no current Structure")
    hierarchies = tuple(
        value
        for value in project.biological_hierarchies.values()
        if value.structure_id == structure.id
    )
    if len(hierarchies) != 1:
        raise ValueError("Structure must have exactly one biological hierarchy")
    hierarchy = hierarchies[0]
    properties = tuple(
        sorted(
            (
                value
                for value in project.datasets.values()
                if (
                    isinstance(value, AtomicProperty)
                    and value.structure_id == structure.id
                    and value.semantic_role in BIOLOGICAL_NUMERIC_ROLE_SPECS
                )
            ),
            key=lambda value: (value.semantic_role, str(value.id)),
        )
    )
    frame_sets = tuple(
        value
        for value in project.datasets.values()
        if isinstance(value, FrameSet) and value.structure_id == structure.id
    )
    if isinstance(entity, FrameSet):
        frame_set = entity
    elif len(frame_sets) > 1:
        raise ValueError("Structure has multiple FrameSets; select one explicitly")
    else:
        frame_set = frame_sets[0] if frame_sets else None
    if isinstance(entity, TopologyRecord):
        topology = entity
    else:
        topologies = tuple(
            project.topologies[value]
            for value in structure.topology_ids
            if value in project.topologies
        )
        topology = topologies[0] if len(topologies) == 1 else None
    return structure, hierarchy, properties, frame_set, topology


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _point_attribute_values(mesh, name, data_type, atom_count):
    attributes = getattr(mesh, "attributes", None)
    attribute = None if attributes is None else attributes.get(name)
    if (
        attribute is None
        or getattr(attribute, "domain", None) != "POINT"
        or getattr(attribute, "data_type", None) != data_type
        or len(getattr(attribute, "data", ())) != atom_count
    ):
        raise ValueError(f"biological attribute {name} is missing or stale")
    default = (
        0.0
        if data_type == "FLOAT"
        else False
        if data_type == "BOOLEAN"
        else 0
    )
    values = [default] * atom_count
    try:
        attribute.data.foreach_get("value", values)
    except (AttributeError, RuntimeError, TypeError, ValueError) as error:
        raise ValueError(f"biological attribute {name} is unreadable") from error
    return tuple(values)


def _require_projected_attribute(mesh, name, data_type, expected, atom_count):
    actual = _point_attribute_values(mesh, name, data_type, atom_count)
    if data_type == "FLOAT":
        matches = all(
            isfinite(value)
            and isclose(value, target, rel_tol=1.0e-6, abs_tol=1.0e-6)
            for value, target in zip(actual, expected, strict=True)
        )
    else:
        matches = actual == tuple(expected)
    if not matches:
        raise ValueError(f"biological attribute {name} is stale")
    return actual


def _biological_view_snapshot(obj, structure, hierarchy, properties=()):
    """Validate and capture one live biological Mesh snapshot."""
    projection = biological_point_data(structure, hierarchy, properties)
    if (
        obj is None
        or obj.get("cb_structure_contract") != "structure_view_v1"
        or obj.get("cb_structure_id") != str(structure.id)
        or obj.get("cb_structure_revision") != structure.revision
        or obj.get("cb_biological_hierarchy_id") != str(hierarchy.id)
        or obj.get("cb_biological_hierarchy_revision") != hierarchy.revision
    ):
        raise ValueError("active object is not the current biological Structure view")
    mesh = getattr(obj, "data", None)
    vertices = getattr(mesh, "vertices", None)
    if vertices is None or len(vertices) != hierarchy.atom_count:
        raise ValueError("biological Structure view atom count is stale")
    expected = {
        "cb_biological_categories": projection["categories"],
        "cb_biological_category_hashes": projection["category_hashes"],
        "cb_biological_dataset_bindings": projection["dataset_bindings"],
    }
    for name, value in expected.items():
        stored = obj.get(name)
        try:
            actual = _canonical_json(json.loads(stored))
        except (TypeError, ValueError):
            raise ValueError("biological attribute mapping is stale") from None
        if actual != _canonical_json(value):
            raise ValueError("biological attribute mapping is stale")
    atom_count = hierarchy.atom_count
    for name in projection["categories"]:
        _require_projected_attribute(
            mesh,
            name,
            "INT",
            projection[name],
            atom_count,
        )
        _require_projected_attribute(
            mesh,
            f"{name}_valid",
            "BOOLEAN",
            projection[f"{name}_valid"],
            atom_count,
        )
    _require_projected_attribute(
        mesh,
        "cbq_residue_number",
        "INT",
        projection["cbq_residue_number"],
        atom_count,
    )
    for spec in BIOLOGICAL_NUMERIC_ROLE_SPECS.values():
        name = spec["attribute"]
        _require_projected_attribute(
            mesh,
            name,
            "FLOAT",
            projection[name],
            atom_count,
        )
        _require_projected_attribute(
            mesh,
            f"{name}_valid",
            "BOOLEAN",
            projection[f"{name}_valid"],
            atom_count,
        )
    return {
        "selected": _point_attribute_values(
            mesh,
            "cbq_selected",
            "BOOLEAN",
            atom_count,
        ),
        "visible": _point_attribute_values(
            mesh,
            "cbq_visible",
            "BOOLEAN",
            atom_count,
        ),
        "altloc_filter_present": "cb_altloc_filter" in obj,
        "altloc_filter": obj.get("cb_altloc_filter"),
        "selection_name_present": "cb_selection_name" in obj,
        "selection_name": obj.get("cb_selection_name"),
        "selection_domain_present": "cb_selection_domain" in obj,
        "selection_domain": obj.get("cb_selection_domain"),
    }


def require_live_biological_view(obj, structure, hierarchy, properties=()):
    """Fail closed for foreign, stale or remapped Blender objects."""
    _biological_view_snapshot(obj, structure, hierarchy, properties)
    return obj


def _restore_custom_property(obj, name, present, value):
    if present:
        obj[name] = value
    elif name in obj:
        del obj[name]


def _apply_altloc_view_mutation(obj, indices, mask, name, filter_value, snapshot):
    try:
        _write_attribute(
            obj.data,
            "cbq_visible",
            "BOOLEAN",
            "value",
            mask,
        )
        obj["cb_altloc_filter"] = filter_value
        apply_atom_selection(obj, indices, name=name)
    except BaseException as error:
        cleanup = (
            (
                "selected mask",
                lambda: _write_attribute(
                    obj.data,
                    "cbq_selected",
                    "BOOLEAN",
                    "value",
                    snapshot["selected"],
                ),
            ),
            (
                "visible mask",
                lambda: _write_attribute(
                    obj.data,
                    "cbq_visible",
                    "BOOLEAN",
                    "value",
                    snapshot["visible"],
                ),
            ),
            (
                "altloc filter",
                lambda: _restore_custom_property(
                    obj,
                    "cb_altloc_filter",
                    snapshot["altloc_filter_present"],
                    snapshot["altloc_filter"],
                ),
            ),
            (
                "selection name",
                lambda: _restore_custom_property(
                    obj,
                    "cb_selection_name",
                    snapshot["selection_name_present"],
                    snapshot["selection_name"],
                ),
            ),
            (
                "selection domain",
                lambda: _restore_custom_property(
                    obj,
                    "cb_selection_domain",
                    snapshot["selection_domain_present"],
                    snapshot["selection_domain"],
                ),
            ),
        )
        for label, restore in cleanup:
            try:
                restore()
            except BaseException as cleanup_error:
                error.add_note(f"failed to restore {label}: {cleanup_error}")
        update = getattr(obj.data, "update", None)
        if update is not None:
            try:
                update()
            except BaseException as cleanup_error:
                error.add_note(
                    f"failed to update restored biological view: {cleanup_error}"
                )
        raise


def plan_biological_view(structure, topology):
    if not isinstance(structure, Structure):
        raise TypeError("structure must be a Structure")
    if topology is not None and (
        not isinstance(topology, TopologyRecord)
        or topology.structure_id != structure.id
    ):
        raise ValueError("topology must match Structure")
    if topology is None:
        return (
            StructureViewSettings(attach_ball_and_stick=False),
            "Atoms/points: no selected topology.",
        )
    if len(structure.atomic_numbers) > _BALL_STICK_ATOM_LIMIT:
        return (
            StructureViewSettings(attach_ball_and_stick=False),
            "Atoms/points: size-aware atom limit exceeded.",
        )
    return (
        StructureViewSettings(),
        "Ball-and-stick: selected topology is available.",
    )


def altloc_filter_mask(structure, hierarchy, datasets, altloc):
    if altloc is None:
        return default_altloc_mask(structure, hierarchy, datasets)
    if type(altloc) is not str:
        raise TypeError("altloc must be a string or None")
    biological_point_data(structure, hierarchy, datasets)
    residue_indices = tuple(
        int(value) for value in hierarchy.atom_sites.residue_indices.values
    )
    atom_names = _values(structure.atomic_identity.atom_names)
    record_kinds = _values(hierarchy.atom_sites.record_kinds)
    alternate_locations = tuple(
        value or "" for value in _values(hierarchy.atom_sites.alternate_locations)
    )
    groups = {}
    for index, identity in enumerate(
        zip(residue_indices, atom_names, record_kinds)
    ):
        groups.setdefault(identity, []).append(index)
    selected = list(default_altloc_mask(structure, hierarchy, datasets))
    for indices in groups.values():
        candidate = next(
            (
                index
                for index in indices
                if alternate_locations[index] == altloc
            ),
            None,
        )
        if candidate is None:
            continue
        for index in indices:
            selected[index] = index == candidate
    return tuple(selected)


class CHEMBLENDER_OT_select_biological_atoms(bpy.types.Operator):
    bl_idname = "chemblender.select_biological_atoms"
    bl_label = "Select Biological Atoms"
    bl_description = "Write a view-only biological atom selection"

    selector: EnumProperty(
        items=(
            ("chain", "Chain", ""),
            ("residue_range", "Residue Range", ""),
            ("residue_name", "Residue Name", ""),
            ("atom_name", "Atom Name", ""),
            ("altloc", "Alternate Location", ""),
            ("property", "Property Threshold", ""),
        ),
        default="chain",
    )
    chain_id: StringProperty(name="Chain")
    residue_start: IntProperty(name="First Residue")
    residue_end: IntProperty(name="Last Residue")
    residue_name: StringProperty(name="Residue Name")
    atom_name: StringProperty(name="Atom Name")
    altloc: StringProperty(name="Alternate Location")
    use_default_altloc: BoolProperty(name="Default Alternate Location")
    property_role: EnumProperty(
        items=biological_numeric_role_items(),
        default="occupancy",
    )
    comparison: EnumProperty(
        items=(
            ("greater_equal", "At Least", ""),
            ("less_equal", "At Most", ""),
        ),
        default="greater_equal",
    )
    threshold: FloatProperty(name="Threshold")

    def execute(self, context):
        session = get_scene_session(context.scene)
        obj = active_session_view(context, session)
        try:
            structure, hierarchy, properties, _frames, _topology = (
                resolve_biological_context(
                    session.project,
                    session.active_entity_id,
                )
            )
            snapshot = _biological_view_snapshot(
                obj,
                structure,
                hierarchy,
                properties,
            )
            if self.selector == "altloc":
                requested = None if self.use_default_altloc else self.altloc
                mask = altloc_filter_mask(
                    structure,
                    hierarchy,
                    properties,
                    requested,
                )
                indices = tuple(
                    index for index, selected in enumerate(mask) if selected
                )
                name = (
                    "altloc:default"
                    if requested is None
                    else f"altloc:{requested or '[blank]'}"
                )
                filter_value = (
                    "[default]" if requested is None else requested
                )
            else:
                if self.selector == "chain":
                    keywords = {"chain_id": self.chain_id}
                elif self.selector == "residue_range":
                    keywords = {
                        "residue_start": self.residue_start,
                        "residue_end": self.residue_end,
                    }
                elif self.selector == "residue_name":
                    keywords = {"residue_name": self.residue_name}
                elif self.selector == "atom_name":
                    keywords = {"atom_name": self.atom_name}
                else:
                    keywords = {
                        "property_role": self.property_role,
                        "comparison": self.comparison,
                        "threshold": self.threshold,
                    }
                indices = biological_selection_indices(
                    structure,
                    hierarchy,
                    properties,
                    **keywords,
                )
                label = next(iter(keywords.values()))
                name = f"{self.selector}:{label}"
            if self.selector == "altloc":
                _apply_altloc_view_mutation(
                    obj,
                    indices,
                    mask,
                    name,
                    filter_value,
                    snapshot,
                )
            else:
                apply_atom_selection(obj, indices, name=name)
        except (
            AttributeError,
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        session.active_view_object_name = obj.name
        return {"FINISHED"}


class CHEMBLENDER_OT_play_biological_models(bpy.types.Operator):
    bl_idname = "chemblender.play_biological_models"
    bl_label = "Configure MODEL Playback"
    bl_description = "Use the existing trajectory manager for compatible MODEL frames"

    frame_start: IntProperty(name="Start Frame", default=1)
    frame_step: IntProperty(name="Frame Step", default=1, min=1)

    def execute(self, context):
        session = get_scene_session(context.scene)
        obj = active_session_view(context, session)
        try:
            structure, hierarchy, properties, frame_set, _topology = (
                resolve_biological_context(
                    session.project,
                    session.active_entity_id,
                )
            )
            require_live_biological_view(
                obj,
                structure,
                hierarchy,
                properties,
            )
            if not isinstance(frame_set, FrameSet):
                raise ValueError(
                    "selected biological Structure has no compatible MODEL FrameSet"
                )
            handlers = getattr(
                getattr(getattr(bpy, "app", None), "handlers", None),
                "frame_change_post",
                None,
            )
            if handlers is not None and not any(
                getattr(handler, "__module__", None)
                == trajectory_view.__name__
                and getattr(handler, "__name__", None)
                == "_frame_change_handler"
                for handler in handlers
            ):
                trajectory_view.register()
            trajectory_view.configure_trajectory_view(
                obj,
                frame_set,
                frame_start=self.frame_start,
                frame_step=self.frame_step,
            )
            context.scene.frame_end = self.frame_start + (
                frame_set.data.shape[0] - 1
            ) * self.frame_step
        except (AttributeError, RuntimeError, TypeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        session.active_view_object_name = obj.name
        return {"FINISHED"}


class CHEMBLENDER_OT_create_biological_view(bpy.types.Operator):
    bl_idname = "chemblender.create_biological_view"
    bl_label = "Create Biological Default View"
    bl_description = "Create a size-aware atom or ball-and-stick view"

    def execute(self, context):
        session = get_scene_session(context.scene)
        view = None
        try:
            structure, hierarchy, properties, _frames, topology = (
                resolve_biological_context(
                    session.project,
                    session.active_entity_id,
                )
            )
            settings, reason = plan_biological_view(structure, topology)
            from ..views import create_structure_view

            view = create_structure_view(
                structure,
                topology,
                settings,
                biological_hierarchy=hierarchy,
                atomic_properties=properties,
                name=f"Biological {str(structure.id)[:8]}",
                collection=(
                    getattr(context, "collection", None)
                    or context.scene.collection
                ),
            )
            view["cb_biological_default_reason"] = reason
            previous = context.active_object
            if previous is not None and previous is not view:
                previous.select_set(False)
            view.select_set(True)
            context.view_layer.objects.active = view
        except (AttributeError, RuntimeError, TypeError, ValueError) as error:
            if view is not None:
                from ..views import remove_structure_view

                try:
                    remove_structure_view(view)
                except (AttributeError, ReferenceError, RuntimeError) as cleanup:
                    error.add_note(f"view cleanup failed: {cleanup}")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        session.active_view_object_name = view.name
        self.report({"INFO"}, reason)
        return {"FINISHED"}


def _selection_action(layout, selector, text, **values):
    action = layout.operator(
        CHEMBLENDER_OT_select_biological_atoms.bl_idname,
        text=text,
        icon="RESTRICT_SELECT_OFF",
    )
    action.selector = selector
    for name, value in values.items():
        setattr(action, name, value)


def draw_biological_controls(layout, project, entity_id, settings):
    try:
        structure, hierarchy, properties, frame_set, _topology = (
            resolve_biological_context(project, entity_id)
        )
    except ValueError:
        return
    box = layout.box()
    model = (
        str(hierarchy.model.number)
        if hierarchy.model.number is not None
        else "unspecified"
    )
    box.label(
        text=(
            f"Biological hierarchy: model {model} · "
            f"{len(hierarchy.chains)} chains · "
            f"{len(hierarchy.residues)} residues · "
            f"{hierarchy.atom_count} atoms"
        )
    )
    for dataset in properties:
        box.label(
            text=(
                f"{dataset.semantic_role.replace('_', ' ').title()}: "
                f"{dataset.data.unit} ({dataset.status.value})"
            )
        )
    box.operator(
        CHEMBLENDER_OT_create_biological_view.bl_idname,
        text="Create Size-Aware Default View",
        icon="MESH_DATA",
    )
    box.prop(settings, "biological_chain")
    _selection_action(
        box,
        "chain",
        "Select Chain",
        chain_id=settings.biological_chain,
    )
    box.prop(settings, "biological_residue_start")
    box.prop(settings, "biological_residue_end")
    _selection_action(
        box,
        "residue_range",
        "Select Residue Range",
        residue_start=settings.biological_residue_start,
        residue_end=settings.biological_residue_end,
    )
    box.prop(settings, "biological_residue_name")
    _selection_action(
        box,
        "residue_name",
        "Select Residue Name",
        residue_name=settings.biological_residue_name,
    )
    box.prop(settings, "biological_atom_name")
    _selection_action(
        box,
        "atom_name",
        "Select Atom Name",
        atom_name=settings.biological_atom_name,
    )
    box.prop(settings, "biological_altloc")
    _selection_action(
        box,
        "altloc",
        "Apply Alternate Location",
        altloc=settings.biological_altloc,
        use_default_altloc=False,
    )
    _selection_action(
        box,
        "altloc",
        "Restore Default Alternate Locations",
        use_default_altloc=True,
    )
    box.prop(settings, "biological_property_role")
    box.prop(settings, "biological_comparison")
    box.prop(settings, "biological_threshold")
    try:
        threshold = float(settings.biological_threshold)
    except (TypeError, ValueError):
        threshold = float("nan")
    if isfinite(threshold):
        _selection_action(
            box,
            "property",
            "Select Property Threshold",
            property_role=settings.biological_property_role,
            comparison=settings.biological_comparison,
            threshold=threshold,
        )
    else:
        box.label(text="Property threshold must be finite", icon="ERROR")
    if frame_set is not None:
        box.operator(
            CHEMBLENDER_OT_play_biological_models.bl_idname,
            text=f"Configure {frame_set.data.shape[0]} MODEL Frames",
            icon="PLAY",
        )
