"""Versioned, pure-data publication scene presets."""

import math
import re
from dataclasses import dataclass

from .cache_identity import derivation_cache_key, render_cache_key
from .model import (
    BandStructure,
    DatasetStatus,
    DensityOfStates,
    ExcitedStateSet,
    Grid3D,
    QCProject,
    Spectrum,
    SpectrumKind,
    SpectrumProfile,
    Structure,
    VibrationalModeSet,
)
from .recipe import RecipeBinding, RecipeDefinition


_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*")
_ENTITY_TYPES = {
    "Structure": Structure,
    "Grid3D": Grid3D,
    "VibrationalModeSet": VibrationalModeSet,
    "ExcitedStateSet": ExcitedStateSet,
    "Spectrum": Spectrum,
    "BandStructure": BandStructure,
    "DensityOfStates": DensityOfStates,
}


class ScenePresetError(ValueError):
    pass


def _token(value, name):
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ScenePresetError(f"{name} must be a lower token")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value:
        raise ScenePresetError(f"{name} must be non-empty text")
    return value


def _tokens(values, name):
    values = tuple(values)
    for value in values:
        _token(value, name)
    if len(set(values)) != len(values):
        raise ScenePresetError(f"{name} must not contain duplicates")
    return values


def _json_value(value, name="setting"):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ScenePresetError(f"{name} must be finite")
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_json_value(item, name) for item in value)
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ScenePresetError(f"{name} keys must be strings")
        return {key: _json_value(value[key], name) for key in sorted(value)}
    raise ScenePresetError(f"{name} must be JSON-compatible")


@dataclass(frozen=True, slots=True)
class SceneBindingSpec:
    name: str
    entity_kind: str
    entity_types: tuple[str, ...]
    semantic_roles: tuple[str, ...] = ()

    def __post_init__(self):
        _token(self.name, "binding name")
        if self.entity_kind not in {"structure", "dataset"}:
            raise ScenePresetError("scene binding kind must be structure or dataset")
        entity_types = tuple(self.entity_types)
        if not entity_types or any(value not in _ENTITY_TYPES for value in entity_types):
            raise ScenePresetError("scene binding has an unknown entity type")
        object.__setattr__(self, "entity_types", entity_types)
        object.__setattr__(
            self, "semantic_roles", _tokens(self.semantic_roles, "semantic role")
        )


@dataclass(frozen=True, slots=True)
class ScenePresetDefinition:
    preset_id: str
    version: str
    title: str
    view_kind: str
    bindings: tuple[SceneBindingSpec, ...]
    adapter_contracts: tuple[str, ...]
    default_settings: tuple[tuple[str, object], ...]

    def __post_init__(self):
        _token(self.preset_id, "preset_id")
        _text(self.version, "preset version")
        _text(self.title, "preset title")
        _token(self.view_kind, "view_kind")
        bindings = tuple(self.bindings)
        if not bindings or any(not isinstance(value, SceneBindingSpec) for value in bindings):
            raise ScenePresetError("preset requires binding specs")
        if len({value.name for value in bindings}) != len(bindings):
            raise ScenePresetError("preset binding names must be unique")
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(
            self, "adapter_contracts", _tokens(self.adapter_contracts, "adapter contract")
        )
        settings = tuple(self.default_settings)
        if any(
            not isinstance(value, tuple)
            or len(value) != 2
            or not isinstance(value[0], str)
            for value in settings
        ):
            raise ScenePresetError("default settings must contain name/value pairs")
        if len({value[0] for value in settings}) != len(settings):
            raise ScenePresetError("default setting names must be unique")
        object.__setattr__(
            self,
            "default_settings",
            tuple(
                (name, _json_value(value, name))
                for name, value in sorted(settings, key=lambda item: item[0])
            ),
        )


@dataclass(frozen=True, slots=True)
class ScenePresetPlan:
    preset_id: str
    preset_version: str
    view_kind: str
    bindings: tuple[RecipeBinding, ...]
    adapter_contracts: tuple[str, ...]
    settings: tuple[tuple[str, object], ...]
    render_identity: str


def _spec(name, kind, *types, semantic_roles=()):
    return SceneBindingSpec(name, kind, types, semantic_roles)


def builtin_scene_presets():
    presets = (
        ScenePresetDefinition(
            "structure_publication",
            "1",
            "Publication structure",
            "structure",
            (_spec("structure", "structure", "Structure"),),
            ("structure_view_v1",),
            (("display_coordinate_unit", "angstrom"),),
        ),
        ScenePresetDefinition(
            "signed_isosurface",
            "1",
            "Signed scalar isosurface",
            "signed_isosurface",
            (_spec("grid", "dataset", "Grid3D"),),
            ("openvdb_volume_v1", "volume_to_mesh_v1"),
            (
                ("isovalue", 0.05),
                ("opacity", 1.0),
                ("positive_color", (0.15, 0.35, 0.95, 1.0)),
                ("negative_color", (0.95, 0.20, 0.15, 1.0)),
            ),
        ),
        ScenePresetDefinition(
            "property_on_surface",
            "1",
            "Property mapped on surface",
            "property_on_surface",
            (
                _spec("surface_grid", "dataset", "Grid3D"),
                _spec("property_grid", "dataset", "Grid3D"),
            ),
            ("openvdb_volume_v1", "volume_to_mesh_v1", "surface_property_plan_v1"),
            (
                ("surface_isovalue", 0.001),
                ("color_min", -0.1),
                ("color_max", 0.1),
                ("symmetric", True),
                ("colormap", "coolwarm"),
            ),
        ),
        ScenePresetDefinition(
            "vibration_spectrum_linked",
            "1",
            "Vibration and spectrum linked view",
            "vibration_spectrum_linked",
            (
                _spec("structure", "structure", "Structure"),
                _spec(
                    "modes",
                    "dataset",
                    "VibrationalModeSet",
                    semantic_roles=("vibrational_modes",),
                ),
                _spec("spectrum", "dataset", "Spectrum"),
            ),
            ("structure_view_v1", "vibration_view_v1", "stick_spectrum_selection_v1"),
            (("selection_index", 0), ("arrow_scale", 1.0), ("amplitude_scale", 1.0)),
        ),
        ScenePresetDefinition(
            "electronic_spectrum_linked",
            "1",
            "Electronic state and spectrum linked view",
            "electronic_spectrum_linked",
            (
                _spec("structure", "structure", "Structure"),
                _spec(
                    "states",
                    "dataset",
                    "ExcitedStateSet",
                    semantic_roles=("excited_states",),
                ),
                _spec("spectrum", "dataset", "Spectrum"),
            ),
            ("structure_view_v1", "stick_spectrum_selection_v1"),
            (("selection_index", 0),),
        ),
        ScenePresetDefinition(
            "band_dos_linked",
            "1",
            "Band structure and DOS linked view",
            "band_dos_linked",
            (
                _spec("band", "dataset", "BandStructure", semantic_roles=("band_structure",)),
                _spec(
                    "dos",
                    "dataset",
                    "DensityOfStates",
                    semantic_roles=("density_of_states",),
                ),
            ),
            ("band_structure_curve_v1", "density_of_states_curve_v1"),
            (("energy_reference", "fermi_shifted"), ("mirror_beta", True)),
        ),
    )
    return {value.preset_id: value for value in presets}


def _entity(project, spec, identity):
    registry = project.structures if spec.entity_kind == "structure" else project.datasets
    entity = registry.get(identity)
    if entity is None:
        raise ScenePresetError(f"scene binding is missing: {spec.name}")
    if not isinstance(entity, tuple(_ENTITY_TYPES[value] for value in spec.entity_types)):
        raise ScenePresetError(f"scene binding has wrong type: {spec.name}")
    if spec.semantic_roles and entity.semantic_role not in spec.semantic_roles:
        raise ScenePresetError(f"scene binding has wrong semantic role: {spec.name}")
    if spec.entity_kind == "dataset" and entity.status is not DatasetStatus.COMPLETE:
        raise ScenePresetError(f"publication scene requires complete dataset: {spec.name}")
    return entity


def _number(value, name, *, positive=False, minimum=None, maximum=None):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (positive and value <= 0.0)
        or (minimum is not None and value < minimum)
        or (maximum is not None and value > maximum)
    ):
        raise ScenePresetError(f"{name} is outside the supported range")
    return float(value)


def _index(value, size, name):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < size:
        raise ScenePresetError(f"{name} is outside the dataset")
    return value


def _color(value, name):
    value = tuple(value) if isinstance(value, (list, tuple)) else ()
    if len(value) != 4:
        raise ScenePresetError(f"{name} must be RGBA")
    return tuple(_number(item, name, minimum=0.0, maximum=1.0) for item in value)


def _settings(preset, supplied, entities):
    if not isinstance(supplied, dict):
        raise TypeError("scene settings must be a mapping")
    result = dict(preset.default_settings)
    if set(supplied) - set(result):
        raise ScenePresetError("scene settings contain unknown names")
    result.update(supplied)
    kind = preset.view_kind
    if kind == "structure":
        if result["display_coordinate_unit"] != "angstrom":
            raise ScenePresetError("structure display unit must be angstrom")
    elif kind == "signed_isosurface":
        result["isovalue"] = _number(result["isovalue"], "isovalue", positive=True)
        result["negative_isovalue"] = -result["isovalue"]
        result["opacity"] = _number(result["opacity"], "opacity", minimum=0.0, maximum=1.0)
        result["positive_color"] = _color(result["positive_color"], "positive_color")
        result["negative_color"] = _color(result["negative_color"], "negative_color")
    elif kind == "property_on_surface":
        result["surface_isovalue"] = _number(
            result["surface_isovalue"], "surface_isovalue", positive=True
        )
        result["color_min"] = _number(result["color_min"], "color_min")
        result["color_max"] = _number(result["color_max"], "color_max")
        if result["color_min"] >= result["color_max"]:
            raise ScenePresetError("color range must be increasing")
        if not isinstance(result["symmetric"], bool):
            raise ScenePresetError("symmetric must be a boolean")
        if result["symmetric"] and result["color_min"] != -result["color_max"]:
            raise ScenePresetError("symmetric color range must be centered on zero")
        _token(result["colormap"], "colormap")
        surface, prop = entities["surface_grid"], entities["property_grid"]
        if (
            surface.grid_shape != prop.grid_shape
            or surface.origin != prop.origin
            or surface.step_vectors != prop.step_vectors
            or surface.coordinate_unit != prop.coordinate_unit
            or surface.structure_id != prop.structure_id
        ):
            raise ScenePresetError("surface and property grids must share one affine grid")
    elif kind in {"vibration_spectrum_linked", "electronic_spectrum_linked"}:
        source_name = "modes" if kind.startswith("vibration") else "states"
        source = entities[source_name]
        spectrum = entities["spectrum"]
        if spectrum.profile is not SpectrumProfile.STICK:
            raise ScenePresetError("linked spectrum scene requires a stick spectrum")
        if spectrum.source_dataset_id != source.id or source.structure_id != entities[
            "structure"
        ].id:
            raise ScenePresetError("spectrum scene datasets are not linked")
        if kind.startswith("vibration") and spectrum.kind not in {
            SpectrumKind.IR,
            SpectrumKind.RAMAN,
        }:
            raise ScenePresetError("vibration scene requires IR or Raman spectrum")
        if kind.startswith("electronic") and spectrum.kind not in {
            SpectrumKind.UV_VIS,
            SpectrumKind.ECD,
        }:
            raise ScenePresetError("electronic scene requires UV-Vis or ECD spectrum")
        result["selection_index"] = _index(
            result["selection_index"], spectrum.data.shape[0], "selection_index"
        )
        if kind.startswith("vibration"):
            result["arrow_scale"] = _number(
                result["arrow_scale"], "arrow_scale", positive=True
            )
            result["amplitude_scale"] = _number(
                result["amplitude_scale"], "amplitude_scale"
            )
    elif kind == "band_dos_linked":
        if entities["band"].structure_id != entities["dos"].structure_id:
            raise ScenePresetError("band and DOS must reference one structure")
        if result["energy_reference"] not in {"absolute", "fermi_shifted"}:
            raise ScenePresetError("unsupported energy reference")
        if not isinstance(result["mirror_beta"], bool):
            raise ScenePresetError("mirror_beta must be a boolean")
    return tuple((name, _json_value(result[name], name)) for name in sorted(result))


def plan_scene_preset(preset, project, bindings, settings):
    if not isinstance(preset, ScenePresetDefinition):
        raise TypeError("preset must be a ScenePresetDefinition")
    if not isinstance(project, QCProject):
        raise TypeError("project must be a QCProject")
    if not isinstance(bindings, dict) or set(bindings) != {
        value.name for value in preset.bindings
    }:
        raise ScenePresetError("scene binding names must exactly match the preset")
    entities = {}
    normalized_bindings = []
    identities = []
    for spec in preset.bindings:
        identity = bindings[spec.name]
        entity = _entity(project, spec, identity)
        entities[spec.name] = entity
        normalized_bindings.append(
            RecipeBinding(spec.name, spec.entity_kind, entity.id, entity.revision)
        )
        identities.append((entity.id, entity.revision))
    normalized_settings = _settings(preset, settings, entities)
    derivation = derivation_cache_key(
        identities,
        f"scene_preset.{preset.preset_id}",
        preset.version,
        dict(normalized_settings),
    )
    anchor = normalized_bindings[0]
    render_identity = render_cache_key(
        anchor.entity_id,
        anchor.revision,
        derivation,
        f"scene_preset.{preset.view_kind}",
        preset.version,
        dict(normalized_settings),
    )
    return ScenePresetPlan(
        preset.preset_id,
        preset.version,
        preset.view_kind,
        tuple(normalized_bindings),
        preset.adapter_contracts,
        normalized_settings,
        render_identity,
    )


def scene_preset_document(preset):
    if not isinstance(preset, ScenePresetDefinition):
        raise TypeError("preset must be a ScenePresetDefinition")
    return {
        "preset_id": preset.preset_id,
        "version": preset.version,
        "title": preset.title,
        "view_kind": preset.view_kind,
        "bindings": [
            {
                "name": value.name,
                "entity_kind": value.entity_kind,
                "entity_types": list(value.entity_types),
                "semantic_roles": list(value.semantic_roles),
            }
            for value in preset.bindings
        ],
        "adapter_contracts": list(preset.adapter_contracts),
        "default_settings": {
            name: list(value) if isinstance(value, tuple) else value
            for name, value in preset.default_settings
        },
    }


def scene_preset_from_document(document):
    fields = {
        "preset_id",
        "version",
        "title",
        "view_kind",
        "bindings",
        "adapter_contracts",
        "default_settings",
    }
    if not isinstance(document, dict) or set(document) != fields:
        raise ScenePresetError("invalid scene preset fields")
    if not isinstance(document["bindings"], list):
        raise ScenePresetError("scene preset bindings must be a list")
    bindings = []
    for value in document["bindings"]:
        if not isinstance(value, dict) or set(value) != {
            "name",
            "entity_kind",
            "entity_types",
            "semantic_roles",
        }:
            raise ScenePresetError("invalid scene binding fields")
        if not isinstance(value["entity_types"], list) or not isinstance(
            value["semantic_roles"], list
        ):
            raise ScenePresetError("scene binding type and role fields must be lists")
        bindings.append(
            SceneBindingSpec(
                value["name"],
                value["entity_kind"],
                tuple(value["entity_types"]),
                tuple(value["semantic_roles"]),
            )
        )
    if not isinstance(document["adapter_contracts"], list) or not isinstance(
        document["default_settings"], dict
    ):
        raise ScenePresetError("invalid scene preset contracts or settings")
    return ScenePresetDefinition(
        document["preset_id"],
        document["version"],
        document["title"],
        document["view_kind"],
        tuple(bindings),
        tuple(document["adapter_contracts"]),
        tuple(
            (name, _json_value(document["default_settings"][name], name))
            for name in sorted(document["default_settings"])
        ),
    )


def scene_plan_document(plan):
    if not isinstance(plan, ScenePresetPlan):
        raise TypeError("plan must be a ScenePresetPlan")
    return {
        "preset_id": plan.preset_id,
        "preset_version": plan.preset_version,
        "view_kind": plan.view_kind,
        "bindings": [
            {
                "name": value.name,
                "entity_kind": value.entity_kind,
                "entity_id": str(value.entity_id),
                "revision": value.revision,
            }
            for value in plan.bindings
        ],
        "adapter_contracts": list(plan.adapter_contracts),
        "settings": {
            name: list(value) if isinstance(value, tuple) else value
            for name, value in plan.settings
        },
        "render_identity": plan.render_identity,
    }


def scene_preset_for_recipe_view(recipe, view_index=0):
    if not isinstance(recipe, RecipeDefinition):
        raise TypeError("recipe must be a RecipeDefinition")
    if isinstance(view_index, bool) or not isinstance(view_index, int) or not 0 <= view_index < len(
        recipe.views
    ):
        raise ScenePresetError("view_index is outside the recipe")
    mapping = {
        ("wavefunction_molecular_orbital_grid", "signed_isosurface"): "signed_isosurface",
        ("vibrational_ir_spectrum", "spectrum_plot"): "vibration_spectrum_linked",
        ("tddft_uvvis", "spectrum_plot"): "electronic_spectrum_linked",
    }
    try:
        return mapping[(recipe.recipe_id, recipe.views[view_index].kind)]
    except KeyError as error:
        raise ScenePresetError("recipe view has no publication scene preset") from error
