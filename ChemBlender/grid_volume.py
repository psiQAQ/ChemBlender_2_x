import operator
import os
from pathlib import Path
from uuid import uuid4

import bpy

from .core import Grid3D, volume_render_cache_key


_ANGSTROM_SCALE = {
    "angstrom": 1.0,
    "bohr": 0.529177210903,
}


def _selected_values(grid, dataset_index):
    import numpy as np

    if isinstance(dataset_index, bool):
        raise TypeError("dataset_index must be an integer")
    try:
        dataset_index = operator.index(dataset_index)
    except TypeError as error:
        raise TypeError("dataset_index must be an integer") from error
    if grid.data.dims == ("x", "y", "z"):
        if dataset_index != 0:
            raise IndexError("three-dimensional Grid3D only has dataset index 0")
        return np.asarray(grid.data.values, dtype=np.float32, order="C")
    if grid.data.dims == ("dataset", "x", "y", "z"):
        if not 0 <= dataset_index < grid.data.shape[0]:
            raise IndexError("dataset_index is outside the Grid3D dataset axis")
        return np.asarray(
            grid.data.values[dataset_index], dtype=np.float32, order="C"
        )
    raise ValueError("Volume adapter requires xyz or dataset-xyz Grid3D dimensions")


def _dataset_index(grid, dataset_index):
    if dataset_index is None:
        if grid.data.dims == ("x", "y", "z"):
            return 0
        raise ValueError("multi-dataset Grid3D requires an explicit dataset_index")
    if isinstance(dataset_index, bool):
        raise TypeError("dataset_index must be an integer")
    try:
        return operator.index(dataset_index)
    except TypeError as error:
        raise TypeError("dataset_index must be an integer") from error


def _transform_matrix(grid, scale):
    steps = tuple(
        tuple(component * scale for component in vector) + (0.0,)
        for vector in grid.step_vectors
    )
    origin = tuple(component * scale for component in grid.origin) + (1.0,)
    return (*steps, origin)


def volume_cache_path(cache_root, grid, *, dataset_index=None):
    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    dataset_index = _dataset_index(grid, dataset_index)
    cache_root = Path(cache_root).resolve()
    key = volume_render_cache_key(grid, dataset_index=dataset_index)
    return cache_root / "volume" / f"{key}.vdb"


def create_grid_volume(
    grid,
    cache_path,
    *,
    dataset_index=None,
    name="ChemBlender Grid",
    collection=None,
):
    import openvdb

    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")
    dataset_index = _dataset_index(grid, dataset_index)
    try:
        scale = _ANGSTROM_SCALE[grid.coordinate_unit]
    except KeyError as error:
        raise ValueError(
            f"unsupported Grid3D coordinate unit: {grid.coordinate_unit}"
        ) from error

    cache_path = Path(cache_path).resolve()
    render_key = volume_render_cache_key(grid, dataset_index=dataset_index)
    if cache_path.is_dir():
        cache_path = volume_cache_path(
            cache_path, grid, dataset_index=dataset_index
        )
        cache_path.parent.mkdir(exist_ok=True)
    elif cache_path.suffix.lower() != ".vdb":
        raise ValueError("cache_path must use the .vdb suffix")
    if not cache_path.parent.is_dir():
        raise ValueError("cache_path parent directory must exist")
    if collection is None:
        collection = bpy.context.collection
    if collection is None:
        raise ValueError("a Blender collection is required")

    values = _selected_values(grid, dataset_index)
    vdb_grid = openvdb.FloatGrid()
    vdb_grid.name = "density"
    vdb_grid.copyFromArray(values)
    vdb_grid.transform = openvdb.createLinearTransform(
        _transform_matrix(grid, scale)
    )
    metadata = {
        "chemblender_dataset_id": str(grid.id),
        "chemblender_dataset_revision": grid.revision,
        "chemblender_dataset_index": int(dataset_index),
        "chemblender_semantic_role": grid.semantic_role,
        "chemblender_value_unit": grid.data.unit,
        "chemblender_source_coordinate_unit": grid.coordinate_unit,
        "chemblender_display_coordinate_unit": "angstrom",
        "chemblender_coordinate_scale": scale,
        "chemblender_cache_format_version": 1,
        "chemblender_render_cache_key": render_key,
    }
    if grid.structure_id is not None:
        metadata["chemblender_structure_id"] = str(grid.structure_id)
    temporary = cache_path.with_name(
        f".{cache_path.name}.{uuid4().hex}.tmp"
    )
    try:
        openvdb.write(str(temporary), vdb_grid, metadata=metadata)
        os.replace(temporary, cache_path)
    finally:
        temporary.unlink(missing_ok=True)

    volume = bpy.data.volumes.new(name)
    obj = None
    try:
        volume.filepath = str(cache_path)
        volume.grids.load()
        if volume.grids["density"] is None:
            raise RuntimeError("written VDB does not contain the density grid")
        volume.display.interpolation_method = "LINEAR"
        obj = bpy.data.objects.new(name, volume)
        collection.objects.link(obj)
        obj["cb_dataset_id"] = str(grid.id)
        obj["cb_dataset_revision"] = grid.revision
        obj["cb_dataset_index"] = int(dataset_index)
        obj["cb_semantic_role"] = grid.semantic_role
        obj["cb_value_unit"] = grid.data.unit
        obj["cb_source_coordinate_unit"] = grid.coordinate_unit
        obj["cb_display_coordinate_unit"] = "angstrom"
        obj["cb_coordinate_scale"] = scale
        obj["cb_cache_path"] = str(cache_path)
        obj["cb_cache_format_version"] = 1
        obj["cb_render_cache_key"] = render_key
        if grid.structure_id is not None:
            obj["cb_structure_id"] = str(grid.structure_id)
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if volume.name in bpy.data.volumes:
            bpy.data.volumes.remove(volume)
        raise
