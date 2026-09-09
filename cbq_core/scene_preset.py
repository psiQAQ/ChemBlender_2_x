"""Versioned, pure-data publication scene presets."""

import math
import re
from dataclasses import dataclass, replace

from .cache_identity import derivation_cache_key
from .cache_identity import render_cache_key
from .model import BandStructure
from .model import AtomicProperty
from .model import AtomFrameProperty
from .model import DatasetStatus
from .model import DensityOfStates
from .model import ExcitedStateSet
from .model import Grid3D
from .model import FermiSurfaceMesh
from .model import FrameSet
from .model import PhononModeSet
from .model import QCProject
from .model import Spectrum
from .model import SpectrumKind
from .model import SpectrumProfile
from .model import Structure
from .model import TopologyGraph
from .model import VibrationalModeSet
from .recipe import RecipeBinding
from .recipe import RecipeDefinition


_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*")
GRID_AFFINE_ABS_TOLERANCE = 1.0e-9
# Blender owns a complete Mesh/Curve even though scientific interpolation chunks.
GRID_SAMPLE_POINT_LIMIT = 1_000_000
_ENTITY_TYPES = {
    "Structure": Structure,
    "Grid3D": Grid3D,
    "VibrationalModeSet": VibrationalModeSet,
    "ExcitedStateSet": ExcitedStateSet,
    "Spectrum": Spectrum,
    "BandStructure": BandStructure,
    "DensityOfStates": DensityOfStates,
    "AtomicProperty": AtomicProperty,
    "FermiSurfaceMesh": FermiSurfaceMesh,
    "PhononModeSet": PhononModeSet,
    "TopologyGraph": TopologyGraph,
    "FrameSet": FrameSet,
    "AtomFrameProperty": AtomFrameProperty,
}


def grids_share_affine(left, right):
    """Return whether two grids share one index-to-space mapping."""
    if not isinstance(left, Grid3D) or not isinstance(right, Grid3D):
        return False
    if (
        left.grid_shape != right.grid_shape
        or left.coordinate_unit != right.coordinate_unit
        or left.structure_id != right.structure_id
    ):
        return False
    return all(
        math.isclose(
            left_value,
            right_value,
            rel_tol=0.0,
            abs_tol=GRID_AFFINE_ABS_TOLERANCE,
        )
        for left_value, right_value in zip(
            (*left.origin, *(value for row in left.step_vectors for value in row)),
            (*right.origin, *(value for row in right.step_vectors for value in row)),
            strict=True,
        )
    )


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


def legacy_scene_presets():
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
                ("dataset_index", 0),
                ("isovalue", 0.05),
                ("opacity", 1.0),
                ("positive_color", (0.15, 0.35, 0.95, 1.0)),
                ("negative_color", (0.95, 0.20, 0.15, 1.0)),
            ),
        ),
        ScenePresetDefinition(
            "grid_volume",
            "1",
            "Grid volume",
            "grid_volume",
            (_spec("grid", "dataset", "Grid3D"),),
            ("openvdb_volume_v1",),
            (("dataset_index", 0),),
        ),
        ScenePresetDefinition(
            "property_on_surface",
            "2",
            "Property mapped on surface",
            "property_on_surface",
            (
                _spec("surface_grid", "dataset", "Grid3D"),
                _spec("property_grid", "dataset", "Grid3D"),
            ),
            ("openvdb_volume_v1", "grid_to_mesh_v1", "property_surface_v2"),
            (
                ("surface_dataset_index", 0),
                ("property_dataset_index", 0),
                ("surface_isovalue", 0.001),
                ("color_min", -0.1),
                ("color_max", 0.1),
                ("symmetric", True),
                ("colormap", "coolwarm"),
            ),
        ),
        ScenePresetDefinition(
            "grid_slice", "1", "Scientific plane slice", "grid_slice",
            (_spec("grid", "dataset", "Grid3D"),), ("grid_sample_view_v1",),
            (("dataset_index", 0), ("origin", (-1., -1., 0.)),
             ("u_vector", (2., 0., 0.)), ("v_vector", (0., 2., 0.)),
             ("counts", (65, 65)), ("color_min", -.1), ("color_max", .1),
             ("symmetric", True), ("colormap", "coolwarm")),
        ),
        ScenePresetDefinition(
            "grid_profile", "1", "Scientific line profile", "grid_profile",
            (_spec("grid", "dataset", "Grid3D"),), ("grid_sample_view_v1",),
            (("dataset_index", 0), ("start", (-1., 0., 0.)),
             ("end", (1., 0., 0.)), ("sample_count", 129), ("radius", .015)),
        ),
        ScenePresetDefinition(
            "grid_colorbar", "1", "Scientific colorbar", "grid_colorbar",
            (_spec("grid", "dataset", "Grid3D"),), ("grid_sample_view_v1",),
            (("dataset_index", 0), ("color_min", -.1), ("color_max", .1),
             ("symmetric", True), ("colormap", "coolwarm"),
             ("width", 2.), ("height", .2)),
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
            (
                "structure_view_v1",
                "vibration_view_v1",
                "spectrum_curve_v1",
                "stick_spectrum_selection_v1",
            ),
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
            ("structure_view_v1", "spectrum_curve_v1", "stick_spectrum_selection_v1"),
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


def builtin_scene_presets():
    """Current definitions; legacy definitions remain available for explicit rebuild."""
    old = legacy_scene_presets()
    common = (("template", "research"), ("shaded", False), ("material_opacity", 1.))
    result = {}
    for name, preset in old.items():
        extra = common
        if name == "grid_volume":
            extra += (("density_scale", 10.), ("signed", False),
                      ("positive_color", (.04, .45, .80, 1.)),
                      ("negative_color", (1., .30, .04, 1.)))
        if name == "vibration_spectrum_linked":
            extra += (("phase", 0.), ("frame_start", 1), ("frames_per_cycle", 48))
        result[name] = replace(preset, version=str(int(preset.version) + 1),
                               default_settings=preset.default_settings + extra)
    scalar = (("color_min", -1.), ("color_max", 1.), ("symmetric", True),
              ("colormap", "coolwarm"))
    plot = (("line_radius", .01), ("axes", True))
    energy = (("energy_reference", "fermi_shifted"),)
    trajectory = (("frame_index", 0), ("frame_start", 1), ("frame_step", 1))
    definitions = (
        ("nci_surface", "NCI: RDG surface colored by sign(lambda2) rho",
         (_spec("surface_grid", "dataset", "Grid3D", semantic_roles=("reduced_density_gradient",)),
          _spec("property_grid", "dataset", "Grid3D", semantic_roles=("sign_lambda2_rho",))),
         (("surface_dataset_index", 0), ("property_dataset_index", 0),
          ("surface_isovalue", .5), ("color_min", -.05), ("color_max", .05),
          ("symmetric", True), ("colormap", "nci"), ("pairing_confirmed", False))),
        ("trajectory", "Trajectory frame", (_spec("structure", "structure", "Structure"),
         _spec("frames", "dataset", "FrameSet")), trajectory),
        ("trajectory_force", "Trajectory with forces", (_spec("structure", "structure", "Structure"),
         _spec("frames", "dataset", "FrameSet"),
         _spec("force", "dataset", "AtomFrameProperty", semantic_roles=("atomic_force",))),
         trajectory + (("vector_scale", 1.),)),
        ("atomic_scalar", "Atomic scalar", (_spec("structure", "structure", "Structure"),
         _spec("property", "dataset", "AtomicProperty")), scalar),
        ("atomic_vector", "Atomic vectors", (_spec("structure", "structure", "Structure"),
         _spec("property", "dataset", "AtomicProperty")), (("vector_scale", 1.), ("as_force", False))),
        ("vibration_mode", "Vibrational mode", (_spec("structure", "structure", "Structure"),
         _spec("modes", "dataset", "VibrationalModeSet")),
         (("selection_index", 0), ("arrow_scale", 1.), ("amplitude_scale", .4), ("phase", 0.))),
        ("spectrum_plot", "Spectrum", (_spec("spectrum", "dataset", "Spectrum"),), plot),
        ("band_structure", "Band structure", (_spec("band", "dataset", "BandStructure"),), plot + energy),
        ("density_of_states", "DOS / PDOS", (_spec("dos", "dataset", "DensityOfStates"),),
         plot + energy + (("mirror_beta", True), ("atom_indices", None),
                          ("orbital_labels", None), ("spin_indices", None))),
        ("fermi_surface", "Fermi surface", (_spec("surface", "dataset", "FermiSurfaceMesh"),),
         (("color_property", ""), ("color_min", 0.), ("color_max", 1.),
          ("colormap", "viridis"), ("vector_property", ""), ("vector_scale", 1.),
          ("vector_stride", 1))),
        ("topology_graph", "QTAIM critical points and paths", (_spec("graph", "dataset", "TopologyGraph"),),
         (("point_radius", .10), ("path_radius", .025), ("color_property", "kind"),
          ("color_min", 0.), ("color_max", 1.), ("colormap", "viridis"))),
        ("phonon_mode", "Phonon mode", (_spec("structure", "structure", "Structure"),
         _spec("modes", "dataset", "PhononModeSet")),
         (("qpoint_index", 0), ("selection_index", 0), ("amplitude_scale", .4),
          ("phase", 0.), ("repetitions", (1, 1, 1)))),
    )
    for name, title, bindings, settings in definitions:
        if name in {"vibration_mode", "phonon_mode"}:
            settings += (("frame_start", 1), ("frames_per_cycle", 48))
        result[name] = ScenePresetDefinition(name, "1", title, name, bindings,
                        ("scientific_view_v1",), settings + common)
    return result


def _entity(project, spec, identity, *, require_complete=True):
    registry = project.structures if spec.entity_kind == "structure" else project.datasets
    entity = registry.get(identity)
    if entity is None:
        raise ScenePresetError(f"scene binding is missing: {spec.name}")
    if not isinstance(entity, tuple(_ENTITY_TYPES[value] for value in spec.entity_types)):
        raise ScenePresetError(f"scene binding has wrong type: {spec.name}")
    if spec.semantic_roles and entity.semantic_role not in spec.semantic_roles:
        raise ScenePresetError(f"scene binding has wrong semantic role: {spec.name}")
    if (
        require_complete
        and spec.entity_kind == "dataset"
        and entity.status is not DatasetStatus.COMPLETE
    ):
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


def _color_range(result):
    result["color_min"] = _number(result["color_min"], "color_min")
    result["color_max"] = _number(result["color_max"], "color_max")
    if result["color_min"] >= result["color_max"]:
        raise ScenePresetError("color range must be increasing")
    if not isinstance(result["symmetric"], bool):
        raise ScenePresetError("symmetric must be a boolean")
    if result["symmetric"] and result["color_min"] != -result["color_max"]:
        raise ScenePresetError("symmetric color range must be centered on zero")
    from .color_mapping import COLORMAPS
    if result["colormap"] not in COLORMAPS:
        raise ScenePresetError("unsupported property surface colormap")


def _settings(preset, supplied, entities):
    if not isinstance(supplied, dict):
        raise TypeError("scene settings must be a mapping")
    result = dict(preset.default_settings)
    if set(supplied) - set(result):
        raise ScenePresetError("scene settings contain unknown names")
    result.update(supplied)
    if "template" in result:
        if result["template"] not in {"research", "teaching"}:
            raise ScenePresetError("unsupported presentation template")
        if type(result["shaded"]) is not bool:
            raise ScenePresetError("shaded must be boolean")
        result["material_opacity"] = _number(result["material_opacity"],
                                             "material_opacity", minimum=0., maximum=1.)
    kind = preset.view_kind
    if kind in {"band_structure", "band_dos_linked"} and not entities["band"].branches:
        raise ScenePresetError("band-line plots require a high-symmetry path; uniform k-mesh data is for Fermi surfaces")
    if "frames_per_cycle" in result:
        if type(result["frame_start"]) is not int or type(result["frames_per_cycle"]) is not int or result["frames_per_cycle"] < 2:
            raise ScenePresetError("animation requires integer start and at least two frames per cycle")
        result["phase"] = _number(result["phase"], "phase")
    if kind == "structure":
        if result["display_coordinate_unit"] != "angstrom":
            raise ScenePresetError("structure display unit must be angstrom")
    elif kind in {"grid_volume", "signed_isosurface"}:
        grid = entities["grid"]
        if (
            kind == "signed_isosurface"
            and grid.status
            not in {DatasetStatus.COMPLETE, DatasetStatus.AMBIGUOUS}
        ):
            raise ScenePresetError(
                "surface preview requires complete or ambiguous grid"
            )
        dataset_count = grid.data.shape[0] if grid.data.dims[0] == "dataset" else 1
        result["dataset_index"] = _index(
            result["dataset_index"], dataset_count, "dataset_index"
        )
        if kind == "grid_volume":
            if "density_scale" in result:
                result["density_scale"] = _number(result["density_scale"], "density_scale", positive=True)
                if type(result["signed"]) is not bool:
                    raise ScenePresetError("signed must be boolean")
                for name in ("positive_color", "negative_color"):
                    result[name] = _color(result[name], name)
            return tuple(
                (name, _json_value(result[name], name))
                for name in sorted(result)
            )
        result["isovalue"] = _number(result["isovalue"], "isovalue", positive=True)
        result["negative_isovalue"] = -result["isovalue"]
        result["opacity"] = _number(result["opacity"], "opacity", minimum=0.0, maximum=1.0)
        result["positive_color"] = _color(result["positive_color"], "positive_color")
        result["negative_color"] = _color(result["negative_color"], "negative_color")
    elif kind in {"property_on_surface", "nci_surface"}:
        surface, prop = entities["surface_grid"], entities["property_grid"]
        surface_count = surface.data.shape[0] if surface.data.dims[0] == "dataset" else 1
        property_count = prop.data.shape[0] if prop.data.dims[0] == "dataset" else 1
        result["surface_dataset_index"] = _index(
            result["surface_dataset_index"], surface_count, "surface_dataset_index"
        )
        result["property_dataset_index"] = _index(
            result["property_dataset_index"], property_count, "property_dataset_index"
        )
        result["surface_isovalue"] = _number(
            result["surface_isovalue"], "surface_isovalue", positive=True
        )
        _color_range(result)
        if not grids_share_affine(surface, prop):
            raise ScenePresetError("surface and property grids must share one affine grid")
        if kind == "nci_surface":
            from .grid_semantics import validate_nci_pair

            validate_nci_pair(surface, prop,
                surface_dataset_index=result["surface_dataset_index"],
                property_dataset_index=result["property_dataset_index"],
                pairing_confirmed=result["pairing_confirmed"])
    elif kind in {"grid_slice", "grid_profile", "grid_colorbar"}:
        from .grid_lod import _dataset_index
        from .grid_sampling import validate_plane
        from .grid_sampling import validate_profile

        grid = entities["grid"]
        if grid.coordinate_unit not in {"angstrom", "bohr"}:
            raise ScenePresetError("scientific grid views require angstrom or bohr coordinates")
        result["dataset_index"] = _dataset_index(grid, result["dataset_index"])
        if kind == "grid_slice":
            result.update(validate_plane(**{name: result[name] for name in (
                "origin", "u_vector", "v_vector", "counts", "dataset_index")}))
        elif kind == "grid_profile":
            result.update(validate_profile(**{name: result[name] for name in (
                "start", "end", "sample_count", "dataset_index")}))
            result["radius"] = _number(result["radius"], "radius", positive=True)
        else:
            for name in ("width", "height"):
                result[name] = _number(result[name], name, positive=True)
        if kind != "grid_profile":
            _color_range(result)
        count = (math.prod(result["counts"]) if kind == "grid_slice"
                 else result["sample_count"] if kind == "grid_profile" else 0)
        if count > GRID_SAMPLE_POINT_LIMIT:
            raise ScenePresetError(f"grid view exceeds {GRID_SAMPLE_POINT_LIMIT:,} sample points")
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
    elif kind in {"atomic_scalar", "atomic_vector"}:
        dataset = entities["property"]
        if dataset.structure_id != entities["structure"].id:
            raise ScenePresetError("atomic property and structure must be linked")
        expected = ("atom",) if kind == "atomic_scalar" else ("atom", "xyz")
        if dataset.data.dims != expected:
            raise ScenePresetError(f"{kind} requires {expected} data")
        if kind == "atomic_scalar":
            _color_range(result)
        else:
            result["vector_scale"] = _number(result["vector_scale"], "vector_scale", positive=True)
            if type(result["as_force"]) is not bool:
                raise ScenePresetError("as_force must be boolean")
            if result["as_force"] and dataset.semantic_role != "gradient":
                raise ScenePresetError("only an energy gradient can be converted to force")
    elif kind in {"trajectory", "trajectory_force"}:
        frames = entities["frames"]
        if frames.structure_id != entities["structure"].id:
            raise ScenePresetError("trajectory and structure must be linked")
        if frames.data.unit not in {"angstrom", "bohr"}:
            raise ScenePresetError("trajectory coordinates require angstrom or bohr")
        result["frame_index"] = _index(result["frame_index"], frames.data.shape[0], "frame_index")
        if type(result["frame_start"]) is not int or type(result["frame_step"]) is not int or result["frame_step"] < 1:
            raise ScenePresetError("trajectory timeline requires integer start and positive frame step")
        if kind == "trajectory_force":
            force = entities["force"]
            if (force.frame_set_id != frames.id or force.data.dims != ("frame", "atom", "xyz")
                    or force.data.shape != frames.data.shape
                    or force.status not in {DatasetStatus.COMPLETE, DatasetStatus.PARTIAL}):
                raise ScenePresetError("force dataset must match the complete trajectory axes")
            result["vector_scale"] = _number(result["vector_scale"], "vector_scale", positive=True)
    elif kind in {"vibration_mode", "phonon_mode"}:
        modes = entities["modes"]
        if modes.structure_id != entities["structure"].id:
            raise ScenePresetError("modes and structure must be linked")
        if kind == "phonon_mode":
            result["qpoint_index"] = _index(result["qpoint_index"], modes.data.shape[0], "qpoint_index")
            repeats = tuple(result["repetitions"])
            if len(repeats) != 3 or any(type(v) is not int or not 1 <= v <= 12 for v in repeats):
                raise ScenePresetError("repetitions require three integers between 1 and 12")
            result["repetitions"] = repeats
        else:
            result["arrow_scale"] = _number(result["arrow_scale"], "arrow_scale", positive=True)
        result["selection_index"] = _index(result["selection_index"], modes.data.shape[-1], "selection_index")
        for name in ("amplitude_scale", "phase"):
            result[name] = _number(result[name], name)
    elif kind in {"spectrum_plot", "band_structure", "density_of_states"}:
        result["line_radius"] = _number(result["line_radius"], "line_radius", positive=True)
        if type(result["axes"]) is not bool:
            raise ScenePresetError("axes must be boolean")
        if kind != "spectrum_plot" and result["energy_reference"] not in {"absolute", "fermi_shifted"}:
            raise ScenePresetError("unsupported energy reference")
        if kind == "density_of_states":
            if type(result["mirror_beta"]) is not bool:
                raise ScenePresetError("mirror_beta must be boolean")
            for name in ("atom_indices", "orbital_labels", "spin_indices"):
                if result[name] is not None:
                    if not isinstance(result[name], (tuple, list)) or not result[name]:
                        raise ScenePresetError(f"{name} must be a nonempty selection or null")
                    if name != "orbital_labels" and any(type(v) is not int or v < 0 for v in result[name]):
                        raise ScenePresetError(f"{name} must contain nonnegative integer indices")
                    result[name] = tuple(result[name])
    elif kind in {"fermi_surface", "topology_graph"}:
        from .color_mapping import color_stops
        color_stops(result["color_min"], result["color_max"], result["colormap"])
        if kind == "fermi_surface":
            result["vector_scale"] = _number(result["vector_scale"], "vector_scale", positive=True)
            if type(result["vector_stride"]) is not int or result["vector_stride"] < 1:
                raise ScenePresetError("vector_stride must be a positive integer")
        else:
            if result["color_property"] not in {"kind", "field_value", "laplacian"}:
                raise ScenePresetError("unsupported critical-point color property")
            for name in ("point_radius", "path_radius"):
                result[name] = _number(result[name], name, positive=True)
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
        entity = _entity(
            project,
            spec,
            identity,
            require_complete=(preset.view_kind not in {"grid_volume", "signed_isosurface"}
                              and not (preset.view_kind == "trajectory_force" and spec.name == "force")),
        )
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


def validate_scene_plan(plan, project):
    """Rebuild a plan against current project revisions before side effects."""
    if not isinstance(plan, ScenePresetPlan):
        raise TypeError("plan must be a ScenePresetPlan")
    try:
        preset = builtin_scene_presets()[plan.preset_id]
    except KeyError as error:
        raise ScenePresetError("scene plan references an unknown preset") from error
    if preset.version != plan.preset_version:
        raise ScenePresetError("scene plan preset version is stale")
    bindings = {value.name: value.entity_id for value in plan.bindings}
    settings = dict(plan.settings)
    supplied = {name: settings[name] for name, _ in preset.default_settings}
    current = plan_scene_preset(preset, project, bindings, supplied)
    if current != plan:
        raise ScenePresetError("scene plan is stale or has been modified")
    return current


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
