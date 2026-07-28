import operator
import re
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from uuid import UUID, uuid5

from .cache_identity import derivation_cache_key
from .model import ArrayData, DatasetStatus, Grid3D, ImportBatch, ProvenanceRecord


_VERSION = "1"
_IDENTITY_NAMESPACE = UUID("f41ef862-f51b-4ed7-88d1-cbc0387371cf")
_TOKEN = re.compile(r"[a-z][a-z0-9_]*", re.ASCII)
_SURFACE_MODES = frozenset({"grid_volume", "signed_isosurface"})
_ISOVALUE_POLICIES = frozenset({"absolute", "fraction_of_max_abs"})


@dataclass(frozen=True, slots=True)
class GridSemanticPreset:
    preset_id: str
    semantic_role: str
    value_units: tuple[str, ...]
    signed: bool
    default_surface_mode: str
    isovalue_policy: str
    isovalue_parameter: float
    colormap_class: str

    def __post_init__(self):
        for name in ("preset_id", "semantic_role", "colormap_class"):
            value = getattr(self, name)
            if type(value) is not str or _TOKEN.fullmatch(value) is None:
                raise ValueError(f"{name} must be a lowercase token")
        units = tuple(self.value_units)
        if (
            not units
            or len(units) != len(set(units))
            or any(type(value) is not str or _TOKEN.fullmatch(value) is None for value in units)
        ):
            raise ValueError("value_units must contain unique lowercase tokens")
        if type(self.signed) is not bool:
            raise TypeError("signed must be a bool")
        if self.default_surface_mode not in _SURFACE_MODES:
            raise ValueError("default_surface_mode is unsupported")
        if self.isovalue_policy not in _ISOVALUE_POLICIES:
            raise ValueError("isovalue_policy is unsupported")
        if (
            isinstance(self.isovalue_parameter, bool)
            or not isinstance(self.isovalue_parameter, (int, float))
            or not isfinite(self.isovalue_parameter)
            or self.isovalue_parameter <= 0.0
        ):
            raise ValueError("isovalue_parameter must be finite and positive")
        object.__setattr__(self, "value_units", units)
        object.__setattr__(
            self, "isovalue_parameter", float(self.isovalue_parameter)
        )


GRID_SEMANTIC_PRESETS = MappingProxyType(
    {
        value.preset_id: value
        for value in (
            GridSemanticPreset(
                "generic_scalar",
                "scalar_field",
                (
                    "dimensionless",
                    "electron_per_cubic_bohr",
                    "electron_per_cubic_angstrom",
                    "hartree_per_elementary_charge",
                ),
                signed=True,
                default_surface_mode="grid_volume",
                isovalue_policy="fraction_of_max_abs",
                isovalue_parameter=0.1,
                colormap_class="diverging",
            ),
            GridSemanticPreset(
                "molecular_orbital",
                "molecular_orbital",
                ("inverse_bohr_to_three_halves",),
                signed=True,
                default_surface_mode="signed_isosurface",
                isovalue_policy="fraction_of_max_abs",
                isovalue_parameter=0.05,
                colormap_class="phase",
            ),
            GridSemanticPreset(
                "electron_density",
                "electron_density",
                ("electron_per_cubic_bohr", "electron_per_cubic_angstrom"),
                signed=False,
                default_surface_mode="grid_volume",
                isovalue_policy="absolute",
                isovalue_parameter=0.001,
                colormap_class="sequential",
            ),
            GridSemanticPreset(
                "spin_density",
                "spin_density",
                ("electron_per_cubic_bohr", "electron_per_cubic_angstrom"),
                signed=True,
                default_surface_mode="signed_isosurface",
                isovalue_policy="fraction_of_max_abs",
                isovalue_parameter=0.05,
                colormap_class="diverging",
            ),
            GridSemanticPreset(
                "electrostatic_potential",
                "electrostatic_potential",
                ("hartree_per_elementary_charge",),
                signed=True,
                default_surface_mode="signed_isosurface",
                isovalue_policy="fraction_of_max_abs",
                isovalue_parameter=0.05,
                colormap_class="diverging",
            ),
            GridSemanticPreset(
                "reduced_density_gradient",
                "reduced_density_gradient",
                ("dimensionless",),
                signed=False,
                default_surface_mode="grid_volume",
                isovalue_policy="absolute",
                isovalue_parameter=0.5,
                colormap_class="sequential",
            ),
            GridSemanticPreset(
                "sign_lambda2_rho",
                "sign_lambda2_rho",
                ("electron_per_cubic_bohr", "electron_per_cubic_angstrom"),
                signed=True,
                default_surface_mode="signed_isosurface",
                isovalue_policy="fraction_of_max_abs",
                isovalue_parameter=0.05,
                colormap_class="diverging",
            ),
        )
    }
)


def builtin_grid_semantic_presets():
    return GRID_SEMANTIC_PRESETS


def _selected_values(grid, dataset_index):
    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    if isinstance(dataset_index, bool):
        raise TypeError("dataset_index must be an integer")
    try:
        dataset_index = operator.index(dataset_index)
    except TypeError as error:
        raise TypeError("dataset_index must be an integer") from error
    if grid.data.dims == ("x", "y", "z"):
        if dataset_index != 0:
            raise IndexError("scalar Grid3D only has dataset index 0")
        return grid.data.values, 0
    if grid.data.dims != ("dataset", "x", "y", "z"):
        raise ValueError("grid must use xyz or dataset-xyz dimensions")
    if not 0 <= dataset_index < grid.data.shape[0]:
        raise IndexError("dataset_index is outside the Grid3D dataset axis")
    try:
        return grid.data.values[dataset_index], dataset_index
    except (TypeError, NotImplementedError):
        import numpy

        return numpy.asarray(grid.data.values)[dataset_index], dataset_index


def _require_preset(preset_id):
    if type(preset_id) is not str:
        raise TypeError("preset_id must be a string")
    try:
        return GRID_SEMANTIC_PRESETS[preset_id]
    except KeyError as error:
        raise ValueError(f"unknown grid semantic preset: {preset_id}") from error


def default_grid_isovalue(grid, *, dataset_index, preset_id):
    import numpy

    preset = _require_preset(preset_id)
    values, _ = _selected_values(grid, dataset_index)
    values = numpy.asarray(values, dtype=float)
    if not numpy.all(numpy.isfinite(values)):
        raise ValueError("grid values must be finite")
    if preset.isovalue_policy == "absolute":
        return preset.isovalue_parameter
    maximum = float(numpy.max(numpy.abs(values)))
    if maximum == 0.0:
        raise ValueError("relative isovalue requires nonzero grid values")
    return maximum * preset.isovalue_parameter


def resolve_grid_semantics(grid, *, dataset_index, preset_id, value_unit):
    import numpy

    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    if grid.status is not DatasetStatus.AMBIGUOUS:
        raise ValueError("grid semantic resolution requires an ambiguous Grid3D")
    preset = _require_preset(preset_id)
    if type(value_unit) is not str or value_unit not in preset.value_units:
        raise ValueError(
            f"value_unit is unsupported for preset {preset.preset_id}"
        )
    selected, dataset_index = _selected_values(grid, dataset_index)
    values = numpy.array(selected, copy=True, order="C")
    if not numpy.all(numpy.isfinite(values)):
        raise ValueError("grid values must be finite")
    parameters = {
        "dataset_index": dataset_index,
        "preset_id": preset.preset_id,
        "semantic_role": preset.semantic_role,
        "value_unit": value_unit,
        "isovalue_policy": preset.isovalue_policy,
        "isovalue_parameter": preset.isovalue_parameter,
    }
    revision = derivation_cache_key(
        ((grid.id, grid.revision),),
        "resolve_grid_semantics",
        _VERSION,
        parameters,
    )
    dataset_id = uuid5(
        _IDENTITY_NAMESPACE,
        f"grid-semantics:{grid.id}:{revision}:dataset",
    )
    provenance_id = uuid5(
        _IDENTITY_NAMESPACE,
        f"grid-semantics:{grid.id}:{revision}:provenance",
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="ChemBlender Grid Semantics",
        producer_version=_VERSION,
        source="",
        source_hash=revision,
        parent_ids=(grid.id, *grid.provenance_ids),
        operation="resolve_grid_semantics",
        parameters=(
            ("dataset_index", dataset_index),
            ("isovalue_parameter", preset.isovalue_parameter),
            ("isovalue_policy", preset.isovalue_policy),
            ("preset_id", preset.preset_id),
            ("semantic_role", preset.semantic_role),
            ("source_revision", grid.revision),
            ("value_unit", value_unit),
        ),
    )
    resolved = Grid3D(
        id=dataset_id,
        revision=revision,
        semantic_role=preset.semantic_role,
        domain="grid",
        data=ArrayData(values, ("x", "y", "z"), value_unit),
        status=DatasetStatus.COMPLETE,
        source_calculation=grid.source_calculation,
        provenance_ids=(provenance_id,),
        origin=grid.origin,
        step_vectors=grid.step_vectors,
        coordinate_unit=grid.coordinate_unit,
        structure_id=grid.structure_id,
    )
    return ImportBatch(datasets=(resolved,), provenance=(provenance,))
