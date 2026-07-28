"""Atomic Blender application of validated scene preset plans."""

import json

import bpy

from .core import EnergyReference, validate_scene_plan
from .dataset_view import link_stick_spectrum_selection
from .electronic_plot import create_band_structure_plot, create_dos_plot
from .grid_volume import create_grid_volume
from .spectrum_plot import create_spectrum_plot
from .surface_view import (
    create_property_surface,
    create_signed_isosurfaces,
    remove_surface_object,
)
from .vibration_view import create_vibration_view
from .views.structure import create_structure_view, remove_structure_view


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


def _write_plan_metadata(obj, plan):
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


def _remove_objects(objects):
    data_blocks = []
    for obj in reversed(objects):
        getter = getattr(obj, "get", None)
        if (
            getter is not None
            and getter("cb_structure_contract") == "structure_view_v1"
        ):
            remove_structure_view(obj)
            continue
        if getattr(obj, "type", None) == "VOLUME" and any(
            modifier.get("cbq_contract") in {"isosurface_v1", "property_surface_v1"}
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


def apply_scene_preset(plan, project, *, collection=None, cache_root=None):
    """Apply a current plan, removing every created object if an adapter fails."""
    plan = validate_scene_plan(plan, project)
    if plan.view_kind in {
        "grid_volume",
        "signed_isosurface",
        "property_on_surface",
    } and cache_root is None:
        raise ScenePresetApplicationError("grid scene preset requires cache_root")
    target = collection or bpy.context.collection
    if target is None:
        raise ScenePresetApplicationError("a Blender collection is required")
    entities = _entities(plan, project)
    settings = dict(plan.settings)
    created = []
    try:
        if plan.view_kind == "grid_volume":
            created.append(
                create_grid_volume(
                    entities["grid"],
                    cache_root,
                    dataset_index=settings["dataset_index"],
                    name="Grid Volume",
                    collection=target,
                )
            )
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
                )
            )
        elif plan.view_kind == "property_on_surface":
            created.append(
                create_property_surface(
                    entities["surface_grid"], entities["property_grid"], cache_root,
                    isovalue=settings["surface_isovalue"],
                    color_min=settings["color_min"], color_max=settings["color_max"],
                    colormap=settings["colormap"], render_identity=plan.render_identity,
                    surface_dataset_index=settings["surface_dataset_index"],
                    property_dataset_index=settings["property_dataset_index"],
                    collection=target,
                )
            )
        elif plan.view_kind == "structure":
            created.append(create_structure_view(entities["structure"], collection=target))
        elif plan.view_kind == "vibration_spectrum_linked":
            structure = create_structure_view(entities["structure"], collection=target)
            created.append(structure)
            create_vibration_view(
                structure,
                entities["modes"],
                mode_index=settings["selection_index"],
                arrow_scale=settings["arrow_scale"],
            )
            structure["cb_vibration_amplitude_scale"] = settings["amplitude_scale"]
            link_stick_spectrum_selection(
                structure,
                entities["spectrum"],
                entities["modes"],
                settings["selection_index"],
            )
            created.append(create_spectrum_plot(entities["spectrum"], collection=target))
        elif plan.view_kind == "electronic_spectrum_linked":
            structure = create_structure_view(entities["structure"], collection=target)
            created.append(structure)
            link_stick_spectrum_selection(
                structure,
                entities["spectrum"],
                entities["states"],
                settings["selection_index"],
            )
            created.append(create_spectrum_plot(entities["spectrum"], collection=target))
        elif plan.view_kind == "band_dos_linked":
            reference = EnergyReference(settings["energy_reference"])
            created.append(
                create_band_structure_plot(
                    entities["band"], collection=target, energy_reference=reference
                )
            )
            created.append(
                create_dos_plot(
                    entities["dos"],
                    collection=target,
                    energy_reference=reference,
                    mirror_beta=settings["mirror_beta"],
                )
            )
        else:
            raise ScenePresetApplicationError(
                f"unknown scene preset view: {plan.view_kind}"
            )
        for obj in created:
            _write_plan_metadata(obj, plan)
        return tuple(created)
    except BaseException as error:
        try:
            _remove_objects(created)
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
