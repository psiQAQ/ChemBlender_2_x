"""Atomic Blender application of validated scene preset plans."""

import json
from uuid import uuid4

import bpy

from cbq_core.model import AtomicProperty
from cbq_core.model import BiologicalHierarchy
from cbq_core.model import DatasetStatus
from cbq_core.model import EnergyReference
from cbq_core.scene_preset import validate_scene_plan
from .dataset_view import (
    apply_atomic_scalar, apply_atomic_vector, link_stick_spectrum_selection,
    write_vector_view,
)
from .electronic_plot import create_band_structure_plot, create_dos_plot
from .grid_volume import create_grid_volume
from .spectrum_plot import create_spectrum_plot
from .surface_view import (
    create_property_surface,
    create_signed_isosurfaces,
    remove_surface_object,
)
from .vibration_view import apply_vibration_phase, create_vibration_view
from .views.structure import (
    BIOLOGICAL_NUMERIC_ROLE_SPECS,
    create_structure_view,
    remove_structure_view,
)
from .views.periodic import create_periodic_structure_view


class ScenePresetApplicationError(RuntimeError):
    pass


_FATAL_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    MemoryError,
)


def _entities(plan, project):
    entities = {}
    for binding in plan.bindings:
        registry = (
            project.structures
            if binding.entity_kind == "structure"
            else project.datasets
        )
        entities[binding.name] = registry[binding.entity_id]
    return entities


def _write_plan_metadata(obj, plan, entities):
    obj["cb_scene_preset_id"] = plan.preset_id
    obj["cb_scene_preset_version"] = plan.preset_version
    obj["cb_scene_view_kind"] = plan.view_kind
    obj["cb_scene_render_identity"] = plan.render_identity
    obj["cb_scene_settings_json"] = json.dumps(
        dict(plan.settings), sort_keys=True, separators=(",", ":")
    )
    obj["cb_scene_bindings_json"] = json.dumps(
        {
            value.name: {
                "entity_id": str(value.entity_id),
                "revision": value.revision,
            }
            for value in plan.bindings
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    complete = all(getattr(value, "status", DatasetStatus.COMPLETE) is DatasetStatus.COMPLETE
                   for value in entities.values())
    obj["cb_view_quality"] = "complete" if complete else "ambiguous"
    obj["cb_report_eligible"] = complete


def scene_view_objects(root):
    """Return only this instance's owned hierarchy, never attached user objects."""
    result = [root]
    instance_id = root.get("cb_view_instance_id")
    for parent in result:
        for child in parent.children:
            if ((instance_id and child.get("cb_view_instance_id") == instance_id)
                    or (not instance_id and (child.get("cb_scientific_component")
                                             or child.get("cb_grid_sample_component")))):
                result.append(child)
    return tuple(result)


def _owned_components(objects):
    result = list(objects)
    for obj in result:
        for child in obj.children:
            if child not in result and (
                child.get("cb_scientific_component") or child.get("cb_grid_sample_component")
                or child.name in {obj.get(key) for key in (
                    "cb_periodic_display_object", "cb_selective_marker_object",
                    "cbq_periodic_site_display_object", "cbq_periodic_cell_object",
                    "cbq_periodic_adp_object", "cbq_periodic_occupancy_object")}
                or child.get("cb_view_instance_id") == obj.get("cb_view_instance_id")
                and obj.get("cb_view_instance_id")
            ):
                result.append(child)
    return result


def _remove_objects(objects):
    objects = _owned_components(objects)
    # Preserve unrelated annotations attached by a user, including their pose.
    for obj in objects:
        for child in tuple(obj.children):
            if child not in objects:
                matrix = child.matrix_world.copy()
                child.parent = None
                child.matrix_world = matrix
    owned_resources = set()
    for obj in objects:
        if obj.data is not None:
            owned_resources.update(material for material in getattr(obj.data, "materials", ())
                                   if material and material.get("cb_scientific_owned"))
        owned_resources.update(mod.node_group for mod in obj.modifiers
                               if getattr(mod, "node_group", None)
                               and mod.node_group.get("cb_scientific_owned"))
    owned_resources = sorted(owned_resources, key=lambda value: value.bl_rna.identifier != "GeometryNodeTree")
    sample_roots = [obj for obj in objects
                    if getattr(obj, "get", lambda *_: None)("cb_grid_sample_root")]
    for obj in sample_roots:
        from .grid_sample_view import remove_grid_sample_view

        remove_grid_sample_view(obj)
    data_blocks = []
    for obj in reversed(objects):
        try:
            getter = getattr(obj, "get", None)
            if getter is not None:
                getter("cb_grid_sample_root")
        except ReferenceError:
            # The sample root removed its owned annotations and materials.
            continue
        if (
            getter is not None
            and getter("cb_structure_contract") == "structure_view_v1"
        ):
            from .trajectory_view import clear_trajectory_view

            clear_trajectory_view(obj)
            remove_structure_view(obj)
            continue
        if getattr(obj, "type", None) == "VOLUME" and any(
            getattr(modifier, "node_group", None) is not None
            and modifier.node_group.get("cbq_contract")
            in {"isosurface_v1", "property_surface_v1", "property_surface_v2"}
            for modifier in obj.modifiers
        ):
            remove_surface_object(obj)
            continue
        data = getattr(obj, "data", None)
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None:
            data_blocks.append(data)
    for data in data_blocks:
        if data.users == 0:
            bpy.data.batch_remove(ids=(data,))
    # Removing node groups can release their materials; check both in that order.
    for resource in owned_resources:
        try:
            if resource.users == 0:
                bpy.data.batch_remove(ids=(resource,))
        except ReferenceError:
            pass  # A specialized surface/sample cleanup already removed it.


def _selected_or_unique_topology(project, structure):
    topologies = tuple(
        project.topologies[topology_id]
        for topology_id in structure.topology_ids
        if topology_id in project.topologies
    )
    scene = getattr(bpy.context, "scene", None)
    settings = getattr(scene, "chemblender_topology", None)
    if settings is not None:
        from .ui.topology import _decode_decisions

        decision = _decode_decisions(settings.decisions_json).get(
            structure.id
        )
        if decision is not None:
            accepted, rejected = decision
            for topology_id in (
                *((accepted,) if accepted is not None else ()),
                *rejected,
            ):
                topology = project.topologies.get(topology_id)
                if topology is None or topology.structure_id != structure.id:
                    raise ScenePresetApplicationError(
                        "current Structure topology decision is stale"
                    )
            if accepted is not None:
                return project.topologies[accepted]
            topologies = tuple(
                topology
                for topology in topologies
                if topology.id not in rejected
            )
    return topologies[0] if len(topologies) == 1 else None


def _plot_settings(settings):
    from .scientific_materials import flat_material

    teaching = settings["template"] == "teaching"
    return {
        "axes": settings.get("axes", True), "line_radius": settings.get("line_radius", .01),
        "axis_material": flat_material("Scientific axes", (.78, .84, .92, 1.) if teaching else (.045, .06, .08, 1.)),
        "material": flat_material("Scientific curve", (.1, .6, 1., 1.) if teaching else (.015, .21, .48, 1.)),
    }


def _place_linked_plot(first, plot):
    """Move only the plot, reserving space for evaluated glyphs, axes and labels."""
    from mathutils import Vector

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()

    def bounds(root):
        points = []
        for obj in _owned_components((root,)):
            if obj.type not in {"MESH", "CURVE", "FONT"}:
                continue
            evaluated = obj.evaluated_get(depsgraph)
            points.extend(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
        if not points:
            raise ScenePresetApplicationError("linked View has no display geometry")
        return (Vector(tuple(min(point[i] for point in points) for i in range(3))),
                Vector(tuple(max(point[i] for point in points) for i in range(3))))

    left_min, left_max = bounds(first)
    right_min, right_max = bounds(plot)
    # Band/DOS share an energy axis: align frame origins, not text bounds.
    vertical = (first.location.y - plot.location.y if first.get("cb_plot_height")
                else (left_min.y + left_max.y - right_min.y - right_max.y) / 2.)
    plot.location += Vector((left_max.x - right_min.x + 1.,
                             vertical, 0.))
    bpy.context.view_layer.update()


def apply_scene_preset(plan, project, *, collection=None, cache_root=None):
    """Apply a current plan, removing every created object if an adapter fails."""
    plan = validate_scene_plan(plan, project)
    if plan.view_kind in {
        "grid_volume",
        "signed_isosurface",
        "property_on_surface",
        "nci_surface",
    } and cache_root is None:
        raise ScenePresetApplicationError("grid scene preset requires cache_root")
    target = collection or bpy.context.collection
    if target is None:
        raise ScenePresetApplicationError("a Blender collection is required")
    entities = _entities(plan, project)
    settings = dict(plan.settings)
    created = []
    materials_before = set(bpy.data.materials)
    try:
        if plan.view_kind in {"grid_slice", "grid_profile", "grid_colorbar"}:
            from .grid_sample_view import create_grid_sample_view

            created.extend(create_grid_sample_view(
                entities["grid"], plan.view_kind, settings, collection=target))
        elif plan.view_kind == "grid_volume":
            created.append(
                create_grid_volume(
                    entities["grid"],
                    cache_root,
                    dataset_index=settings["dataset_index"],
                    name="Grid Volume",
                    collection=target,
                )
            )
            from .scientific_materials import volume_material

            created[0].data.materials.append(volume_material(
                "Scientific volume", density_scale=settings["density_scale"],
                signed=settings["signed"], positive_color=settings["positive_color"],
                negative_color=settings["negative_color"]))
        elif plan.view_kind == "signed_isosurface":
            created.extend(
                create_signed_isosurfaces(
                    entities["grid"], cache_root,
                    isovalue=settings["isovalue"],
                    positive_color=settings["positive_color"],
                    negative_color=settings["negative_color"],
                    opacity=settings["opacity"],
                    dataset_index=settings["dataset_index"],
                    render_identity=plan.render_identity,
                    collection=target,
                    shaded=settings["shaded"],
                )
            )
        elif plan.view_kind in {"property_on_surface", "nci_surface"}:
            created.append(
                create_property_surface(
                    entities["surface_grid"], entities["property_grid"], cache_root,
                    isovalue=settings["surface_isovalue"],
                    color_min=settings["color_min"], color_max=settings["color_max"],
                    colormap=settings["colormap"], render_identity=plan.render_identity,
                    surface_dataset_index=settings["surface_dataset_index"],
                    property_dataset_index=settings["property_dataset_index"],
                    collection=target,
                    shaded=settings["shaded"], opacity=settings["material_opacity"],
                )
            )
        elif plan.view_kind == "phonon_mode":
            from .phonon_view import create_phonon_view

            created.append(create_phonon_view(entities["structure"], entities["modes"],
                qpoint_index=settings["qpoint_index"], mode_index=settings["selection_index"],
                repetitions=settings["repetitions"], amplitude_scale=settings["amplitude_scale"],
                phase=settings["phase"], collection=target))
        elif plan.view_kind in {"trajectory", "trajectory_force"}:
            from .trajectory_view import apply_trajectory_frame

            obj = create_structure_view(entities["structure"],
                _selected_or_unique_topology(project, entities["structure"]), collection=target)
            created.append(obj)
            obj["cb_vector_display_scale"] = settings.get("vector_scale", 1.)
            apply_trajectory_frame(obj, entities["frames"], settings["frame_index"],
                frame_force=entities.get("force"), frame_start=settings["frame_start"],
                frame_step=settings["frame_step"])
            _trajectory_metadata(obj, entities["frames"], project, settings["frame_index"])
        elif plan.view_kind in {"atomic_scalar", "atomic_vector", "vibration_mode"}:
            obj = create_structure_view(entities["structure"],
                _selected_or_unique_topology(project, entities["structure"]), collection=target)
            created.append(obj)
            if plan.view_kind == "atomic_scalar":
                apply_atomic_scalar(obj, entities["property"],
                                    display_min=settings["color_min"], display_max=settings["color_max"],
                                    symmetric=settings["symmetric"], colormap=settings["colormap"])
            elif plan.view_kind == "atomic_vector":
                prop = entities["property"]
                if settings["as_force"]:
                    import numpy

                    write_vector_view(obj, -numpy.asarray(prop.data.values), dataset_id=prop.id,
                                      revision=prop.revision, semantic_role="atomic_force",
                                      unit=prop.data.unit, display_scale=settings["vector_scale"])
                    obj["cb_vector_display_operation"] = "negative_gradient"
                else:
                    apply_atomic_vector(obj, prop, display_scale=settings["vector_scale"])
            else:
                create_vibration_view(obj, entities["modes"], mode_index=settings["selection_index"],
                                      arrow_scale=settings["arrow_scale"])
                apply_vibration_phase(obj, settings["phase"], amplitude_scale=settings["amplitude_scale"])
        elif plan.view_kind in {"spectrum_plot", "band_structure", "density_of_states"}:
            plot_settings = _plot_settings(settings)
            if plan.view_kind == "spectrum_plot":
                obj = create_spectrum_plot(entities["spectrum"], collection=target, **plot_settings)
            elif plan.view_kind == "band_structure":
                obj = create_band_structure_plot(entities["band"], collection=target,
                                                energy_reference=EnergyReference(settings["energy_reference"]), **plot_settings)
            else:
                obj = create_dos_plot(entities["dos"], collection=target,
                                     energy_reference=EnergyReference(settings["energy_reference"]),
                                     mirror_beta=settings["mirror_beta"],
                                     **{key: settings[key] for key in ("atom_indices", "orbital_labels", "spin_indices")},
                                     **plot_settings)
            created.append(obj)
        elif plan.view_kind in {"fermi_surface", "topology_graph"}:
            from .scientific_materials import scalar_material

            prop = settings["color_property"]
            scalar = bool(prop and prop != "kind")
            kwargs = {"collection": target}
            if scalar:
                kwargs.update(color_min=settings["color_min"], color_max=settings["color_max"])
                attribute = "cbq_color_value" if plan.view_kind == "fermi_surface" else "cbq_" + prop
                kwargs["material"] = scalar_material("Scientific property", settings["color_min"],
                    settings["color_max"], attribute_name=attribute, colormap=settings["colormap"],
                    shaded=settings["shaded"], opacity=settings["material_opacity"])
            if plan.view_kind == "fermi_surface":
                from .fermi_surface_view import create_fermi_surface_view

                created.append(create_fermi_surface_view(entities["surface"], color_property=prop or None,
                    vector_property=settings["vector_property"] or None, vector_scale=settings["vector_scale"],
                    vector_stride=settings["vector_stride"], **kwargs))
            else:
                from .topology_view import create_topology_view

                created.extend(obj for obj in create_topology_view(entities["graph"], color_property=prop,
                    point_radius=settings["point_radius"], path_radius=settings["path_radius"], **kwargs) if obj is not None)
        elif plan.view_kind == "structure":
            structure = entities["structure"]
            selective = next(
                (
                    value
                    for value in project.datasets.values()
                    if (
                        isinstance(value, AtomicProperty)
                        and value.structure_id == structure.id
                        and value.semantic_role == "selective_dynamics"
                    )
                ),
                None,
            )
            hierarchies = tuple(
                value
                for value in project.biological_hierarchies.values()
                if (
                    isinstance(value, BiologicalHierarchy)
                    and value.structure_id == structure.id
                )
            )
            if len(hierarchies) > 1:
                raise ScenePresetApplicationError(
                    "Structure has multiple biological hierarchies"
                )
            if hierarchies:
                from .ui.biological import plan_biological_view

                properties = tuple(
                    sorted(
                        (
                            value
                            for value in project.datasets.values()
                            if (
                                isinstance(value, AtomicProperty)
                                and value.structure_id == structure.id
                                and value.semantic_role
                                in BIOLOGICAL_NUMERIC_ROLE_SPECS
                            )
                        ),
                        key=lambda value: (
                            value.semantic_role,
                            str(value.id),
                        ),
                    )
                )
                topology = _selected_or_unique_topology(project, structure)
                view_settings, reason = plan_biological_view(
                    structure,
                    topology,
                )
                view = create_structure_view(
                    structure,
                    topology,
                    view_settings,
                    selective_dynamics=selective,
                    biological_hierarchy=hierarchies[0],
                    atomic_properties=properties,
                    collection=target,
                )
                view["cb_biological_default_reason"] = reason
                created.append(view)
            else:
                # Source-site occupancy and cell displays belong to periodic Views.
                create_view = (create_periodic_structure_view
                               if structure.periodic is not None else create_structure_view)
                created.append(
                    create_view(
                        structure,
                        _selected_or_unique_topology(project, structure),
                        selective_dynamics=selective,
                        collection=target,
                    )
                )
        elif plan.view_kind == "vibration_spectrum_linked":
            structure = create_structure_view(entities["structure"],
                _selected_or_unique_topology(project, entities["structure"]), collection=target)
            created.append(structure)
            create_vibration_view(
                structure,
                entities["modes"],
                mode_index=settings["selection_index"],
                arrow_scale=settings["arrow_scale"],
            )
            apply_vibration_phase(structure, settings["phase"], amplitude_scale=settings["amplitude_scale"])
            link_stick_spectrum_selection(
                structure,
                entities["spectrum"],
                entities["modes"],
                settings["selection_index"],
            )
            created.append(create_spectrum_plot(entities["spectrum"], collection=target, **_plot_settings(settings)))
        elif plan.view_kind == "electronic_spectrum_linked":
            structure = create_structure_view(entities["structure"],
                _selected_or_unique_topology(project, entities["structure"]), collection=target)
            created.append(structure)
            link_stick_spectrum_selection(
                structure,
                entities["spectrum"],
                entities["states"],
                settings["selection_index"],
            )
            created.append(create_spectrum_plot(entities["spectrum"], collection=target, **_plot_settings(settings)))
        elif plan.view_kind == "band_dos_linked":
            reference = EnergyReference(settings["energy_reference"])
            plot_settings = _plot_settings(settings)
            from .electronic_plot import _energy_shift

            band, dos = entities["band"], entities["dos"]
            band_shift, dos_shift = _energy_shift(band, reference), _energy_shift(dos, reference)
            plot_settings["energy_limits"] = (
                min(float(band.data.values.min()) - band_shift, float(dos.energies.values.min()) - dos_shift),
                max(float(band.data.values.max()) - band_shift, float(dos.energies.values.max()) - dos_shift),
            )
            created.append(
                create_band_structure_plot(
                    entities["band"], collection=target, energy_reference=reference, **plot_settings
                )
            )
            created.append(
                create_dos_plot(
                    entities["dos"],
                    collection=target,
                    energy_reference=reference,
                    mirror_beta=settings["mirror_beta"],
                    **plot_settings,
                )
            )
        else:
            raise ScenePresetApplicationError(
                f"unknown scene preset view: {plan.view_kind}"
            )
        from .scientific_materials import apply_structure_materials

        for obj in created:
            if obj.get("cb_structure_contract") == "structure_view_v1":
                apply_structure_materials(obj, quantitative=plan.view_kind == "atomic_scalar",
                                          shaded=settings["shaded"] if plan.view_kind == "atomic_scalar" else True,
                                          opacity=settings["material_opacity"])
        if plan.view_kind in {"vibration_spectrum_linked", "electronic_spectrum_linked", "band_dos_linked"}:
            _place_linked_plot(created[0], created[1])
        components = _owned_components(created)
        root = created[0]
        instance_id = str(uuid4())
        for obj in components:
            if obj != root and obj.parent not in components:
                matrix = obj.matrix_world.copy()
                obj.parent = root
                obj.matrix_world = matrix
            obj["cb_view_instance_id"] = instance_id
            obj["cb_view_root"] = obj == root
            _write_plan_metadata(obj, plan, entities)
            obj["cb_scene_project_id"] = str(project.id)
        return tuple(created)
    except BaseException as error:
        try:
            _remove_objects(created)
            for material in set(bpy.data.materials) - materials_before:
                if material.users == 0 and material.get("cb_scientific_owned"):
                    bpy.data.materials.remove(material)
        except BaseException as cleanup_error:
            if (
                isinstance(cleanup_error, _FATAL_EXCEPTIONS)
                and not isinstance(error, _FATAL_EXCEPTIONS)
            ):
                cleanup_error.add_note(
                    f"scene preset application failed: {error}"
                )
                raise cleanup_error
            error.add_note(
                f"scene preset cleanup failed: {cleanup_error}"
            )
        raise


def apply_scientific_phase(root, project, phase):
    """Set a molecular mode phase in scientific space, independent of root pose."""
    from .ui.view_cache import scene_plan_from_view

    plan = scene_plan_from_view(root, project)
    if plan.view_kind == "phonon_mode":
        from .phonon_view import apply_phonon_phase

        entities = _entities(plan, project)
        return apply_phonon_phase(root, entities["structure"], entities["modes"], phase,
                                  amplitude_scale=dict(plan.settings)["amplitude_scale"])
    if plan.view_kind not in {"vibration_mode", "vibration_spectrum_linked"}:
        raise ScenePresetApplicationError("selected view has no supported phase animation")
    apply_vibration_phase(root, phase, amplitude_scale=dict(plan.settings)["amplitude_scale"])


def _trajectory_metadata(root, frames, project, index):
    """Preserve source labels and a unique explicit time channel, never animation time."""
    import math
    import numpy
    from cbq_core.model import ArrayData
    from cbq_core.model import FrameProperty

    result = {"frame_index": int(index), "frame_label": frames.comments[index]}
    for key in ("cb_trajectory_time", "cb_trajectory_time_unit", "cb_trajectory_time_dataset_id",
                "cb_trajectory_time_dataset_revision"):
        if key in root:
            del root[key]
    candidates = [value for value in project.datasets.values()
                  if isinstance(value, FrameProperty) and value.frame_set_id == frames.id
                  and value.semantic_role == "time" and isinstance(value.data, ArrayData)
                  and value.status in {DatasetStatus.COMPLETE, DatasetStatus.PARTIAL}
                  and value.data.dims == ("frame",) and numpy.dtype(value.data.dtype).kind in "iuf"
                  and value.data.unit != "unknown"]
    if len(candidates) == 1:
        time = candidates[0]
        if time.validity_mask is None or bool(time.validity_mask.values[index]):
            value = float(time.data.values[index])
            if math.isfinite(value):
                result.update(time=value, time_unit=time.data.unit, time_dataset_id=str(time.id),
                              time_dataset_revision=time.revision)
                for key in ("time", "time_unit", "time_dataset_id", "time_dataset_revision"):
                    root["cb_trajectory_" + key] = result[key]
    return result


def apply_scientific_frame(root, project, index):
    """Apply one source trajectory frame without changing its saved static-frame plan."""
    from .trajectory_view import apply_trajectory_frame
    from .ui.view_cache import scene_plan_from_view

    plan = scene_plan_from_view(root, project)
    if plan.view_kind not in {"trajectory", "trajectory_force"}:
        raise ScenePresetApplicationError("selected View is not a trajectory")
    entities, settings = _entities(plan, project), dict(plan.settings)
    apply_trajectory_frame(root, entities["frames"], index, frame_force=entities.get("force"),
        frame_start=settings["frame_start"], frame_step=settings["frame_step"])
    return _trajectory_metadata(root, entities["frames"], project, index)
