from uuid import UUID, uuid5
from cbq_core.model import ArrayData, DatasetStatus, Grid3D, ImportBatch, ProvenanceRecord
from cbq_core.cache_identity import derivation_cache_key
from cbq_core.grid_semantics import _require_preset, _selected_values


_VERSION = "1"


_IDENTITY_NAMESPACE = UUID("f41ef862-f51b-4ed7-88d1-cbc0387371cf")


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
    if numpy.iscomplexobj(values):
        raise ValueError("grid values must be real")
    if not numpy.all(numpy.isfinite(values)):
        raise ValueError("grid values must be finite")
    if preset.preset_id == "reduced_density_gradient" and numpy.any(values < 0.0):
        raise ValueError("reduced_density_gradient must be nonnegative")
    if preset.preset_id in {"elf", "lol"} and (
        numpy.any(values < 0.0) or numpy.any(values > 1.0)
    ):
        raise ValueError("ELF and LOL values must lie between zero and one")
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
