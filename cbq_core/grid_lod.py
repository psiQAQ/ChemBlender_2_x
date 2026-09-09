import operator
from math import isfinite
from uuid import UUID, uuid5

from .cache_identity import derivation_cache_key
from .cache_identity import render_cache_key
from .model import ArrayData
from .model import Grid3D
from .model import ImportBatch
from .model import ProvenanceRecord






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
