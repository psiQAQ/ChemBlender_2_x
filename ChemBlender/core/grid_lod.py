import operator
from math import isfinite
from uuid import UUID, uuid5

from .cache_identity import derivation_cache_key, render_cache_key
from .model import ArrayData, Grid3D, ImportBatch, ProvenanceRecord


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


def _dataset_index(grid, dataset_index):
    if grid.data.dims == ("x", "y", "z"):
        if dataset_index is None:
            return 0
        if isinstance(dataset_index, bool):
            raise TypeError("dataset_index must be an integer")
        try:
            dataset_index = operator.index(dataset_index)
        except TypeError as error:
            raise TypeError("dataset_index must be an integer") from error
        if dataset_index != 0:
            raise IndexError("scalar Grid3D only has dataset index 0")
        return 0
    if grid.data.dims != ("dataset", "x", "y", "z"):
        raise ValueError("Grid LOD requires xyz or dataset-xyz dimensions")
    if dataset_index is None:
        raise ValueError("multi-dataset Grid3D requires an explicit dataset_index")
    if isinstance(dataset_index, bool):
        raise TypeError("dataset_index must be an integer")
    try:
        dataset_index = operator.index(dataset_index)
    except TypeError as error:
        raise TypeError("dataset_index must be an integer") from error
    if not 0 <= dataset_index < grid.data.shape[0]:
        raise IndexError("dataset_index is outside the Grid3D dataset axis")
    return dataset_index


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


def volume_render_cache_key(grid, *, dataset_index=None, adapter_version="1"):
    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    dataset_index = _dataset_index(grid, dataset_index)
    selected = derivation_cache_key(
        ((grid.id, grid.revision),),
        "select_grid_dataset",
        "1",
        {"dataset_index": dataset_index},
    )
    return render_cache_key(
        grid.id,
        grid.revision,
        selected,
        "openvdb_volume",
        adapter_version,
        {"dataset_index": dataset_index},
    )


def surface_render_cache_key(
    grid,
    *,
    dataset_index=None,
    isovalue,
    adapter_version="1",
    volume_adapter_version="1",
):
    if (
        isinstance(isovalue, bool)
        or not isinstance(isovalue, (int, float))
        or not isfinite(isovalue)
    ):
        raise ValueError("isovalue must be finite")
    dataset_index = _dataset_index(grid, dataset_index)
    volume_key = volume_render_cache_key(
        grid,
        dataset_index=dataset_index,
        adapter_version=volume_adapter_version,
    )
    return render_cache_key(
        grid.id,
        grid.revision,
        volume_key,
        "volume_to_mesh",
        adapter_version,
        {"dataset_index": dataset_index, "isovalue": float(isovalue)},
    )
