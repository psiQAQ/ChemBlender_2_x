from uuid import UUID, uuid5
import operator
from cbq_core.model import ArrayData, Grid3D, ImportBatch, ProvenanceRecord
from cbq_core.cache_identity import derivation_cache_key
from cbq_core.grid_lod import _dataset_index


DERIVATION_VERSION = "1"


_IDENTITY_NAMESPACE = UUID("cb513d7c-a51d-4f3f-987a-e491ff1f10d0")


def _strides(values):
    values = tuple(values)
    if len(values) != 3:
        raise ValueError("strides must contain three positive integers")
    result = []
    for value in values:
        if isinstance(value, bool):
            raise TypeError("strides must contain integers")
        try:
            value = operator.index(value)
        except TypeError as error:
            raise TypeError("strides must contain integers") from error
        if value <= 0:
            raise ValueError("strides must contain positive integers")
        result.append(value)
    result = tuple(result)
    if result == (1, 1, 1):
        raise ValueError("at least one stride must be greater than one")
    return result


def _identity(grid, strides, dataset_index):
    return derivation_cache_key(
        ((grid.id, grid.revision),),
        "grid_lod",
        DERIVATION_VERSION,
        {"dataset_index": dataset_index, "strides": strides},
    )


def derive_grid_lod(grid, *, strides, dataset_index=None):
    import numpy

    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    strides = _strides(strides)
    dataset_index = _dataset_index(grid, dataset_index)
    spatial_slice = tuple(slice(None, None, stride) for stride in strides)
    key = (
        spatial_slice
        if grid.data.dims == ("x", "y", "z")
        else (dataset_index, *spatial_slice)
    )
    try:
        selected = grid.data.values[key]
    except (TypeError, NotImplementedError):
        selected = numpy.asarray(grid.data.values)[key]
    values = numpy.array(selected, copy=True, order="C")
    revision = _identity(grid, strides, dataset_index)
    dataset_id = uuid5(
        _IDENTITY_NAMESPACE, f"grid-lod:{grid.id}:{revision}:dataset"
    )
    provenance_id = uuid5(
        _IDENTITY_NAMESPACE, f"grid-lod:{grid.id}:{revision}:provenance"
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="ChemBlender Grid LOD",
        producer_version=DERIVATION_VERSION,
        source="",
        source_hash=revision,
        parent_ids=(grid.id,),
        operation="grid_lod",
        parameters=(
            ("dataset_index", dataset_index),
            ("strides", strides),
        ),
    )
    lod = Grid3D(
        id=dataset_id,
        revision=revision,
        semantic_role=grid.semantic_role,
        domain="grid",
        data=ArrayData(values, ("x", "y", "z"), grid.data.unit),
        status=grid.status,
        source_calculation=grid.source_calculation,
        provenance_ids=(provenance_id,),
        origin=grid.origin,
        step_vectors=tuple(
            tuple(component * stride for component in vector)
            for vector, stride in zip(grid.step_vectors, strides)
        ),
        coordinate_unit=grid.coordinate_unit,
        structure_id=grid.structure_id,
    )
    return ImportBatch(datasets=(lod,), provenance=(provenance,))
