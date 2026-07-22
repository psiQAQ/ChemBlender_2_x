"""Atomic Blender application of validated scene preset plans."""

import json

import bpy

from .core import EnergyReference, validate_scene_plan
from .dataset_view import create_structure_view, link_stick_spectrum_selection
from .electronic_plot import create_band_structure_plot, create_dos_plot
from .spectrum_plot import create_spectrum_plot
from .vibration_view import create_vibration_view


class ScenePresetApplicationError(RuntimeError):
    pass


_UNSUPPORTED = {"signed_isosurface", "property_on_surface"}


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
        data = getattr(obj, "data", None)
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None:
            data_blocks.append(data)
    for data in data_blocks:
        if data.users == 0:
            bpy.data.batch_remove(ids=(data,))


def apply_scene_preset(plan, project, *, collection=None):
    """Apply a current plan, removing every created object if an adapter fails."""
    plan = validate_scene_plan(plan, project)
    if plan.view_kind in _UNSUPPORTED:
        raise ScenePresetApplicationError(
            f"scene preset view is not implemented: {plan.view_kind}"
        )
    target = collection or bpy.context.collection
    if target is None:
        raise ScenePresetApplicationError("a Blender collection is required")
    entities = _entities(plan, project)
    settings = dict(plan.settings)
    created = []
    try:
        if plan.view_kind == "structure":
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
    except Exception:
        _remove_objects(created)
        raise
