import os
from pathlib import Path

import bpy

from .core import Grid3D, volume_render_cache_key
from .core.grid_cache_service import (
    VolumeCacheRequest,
    _dataset_index as _cache_dataset_index,
    _selected_values,
    _transform_matrix,
    prepare_volume_cache,
    volume_cache_path as _volume_cache_path,
)


_ANGSTROM_SCALE = {
    "angstrom": 1.0,
    "bohr": 0.529177210903,
}


def _is_link_like(path):
    return path.is_symlink() or path.is_junction()


def _absolute_path(path):
    return Path(os.path.abspath(path))


def _safe_vdb_path(path):
    path = _absolute_path(path)
    if _is_link_like(path):
        raise OSError("cache_path must not be a filesystem link")
    return path


def volume_cache_path(cache_root, grid, *, dataset_index=None):
    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    cache_root = _safe_vdb_path(cache_root)
    return _safe_vdb_path(
        _volume_cache_path(
            cache_root,
            grid,
            dataset_index=dataset_index,
        )
    )


class _OpenVDBWriter:
    @staticmethod
    def populate(values, transform, _metadata):
        import openvdb

        vdb_grid = openvdb.FloatGrid()
        vdb_grid.name = "density"
        vdb_grid.copyFromArray(values)
        vdb_grid.transform = openvdb.createLinearTransform(transform)
        return vdb_grid

    @staticmethod
    def write(path, payload, metadata):
        import openvdb

        openvdb.write(str(path), payload, metadata=metadata)

    @staticmethod
    def validate(path, grid_names, render_key):
        import openvdb

        grids, metadata = openvdb.readAll(str(path))
        if {grid.name for grid in grids} != set(grid_names):
            raise RuntimeError(
                "VDB grid inventory does not match the cache contract"
            )
        if metadata.get("chemblender_render_cache_key") != render_key:
            raise RuntimeError("VDB render cache identity does not match")


_OPENVDB_WRITER = _OpenVDBWriter()


def ensure_grid_volume_cache(grid, cache_path, *, dataset_index=None):
    """Return a validated cache, rebuilding a missing or invalid VDB in place."""
    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    cache_path = _safe_vdb_path(cache_path)
    if cache_path.is_dir():
        cache_path = volume_cache_path(
            cache_path, grid, dataset_index=dataset_index
        )
        cache_path = _safe_vdb_path(cache_path)
    elif cache_path.suffix.lower() != ".vdb":
        raise ValueError("cache_path must use the .vdb suffix")
    result = prepare_volume_cache(
        grid,
        VolumeCacheRequest(cache_path, dataset_index=dataset_index),
        writer=_OPENVDB_WRITER,
        cancelled=lambda: False,
        progress=lambda _stage, _fraction: None,
    )
    return result.cache_path


def create_grid_volume(
    grid,
    cache_path,
    *,
    dataset_index=None,
    name="ChemBlender Grid",
    collection=None,
):
    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")
    dataset_index = _cache_dataset_index(grid, dataset_index)
    try:
        scale = _ANGSTROM_SCALE[grid.coordinate_unit]
    except KeyError as error:
        raise ValueError(
            f"unsupported Grid3D coordinate unit: {grid.coordinate_unit}"
        ) from error

    render_key = volume_render_cache_key(grid, dataset_index=dataset_index)
    cache_path = ensure_grid_volume_cache(
        grid, cache_path, dataset_index=dataset_index
    )
    if collection is None:
        collection = bpy.context.collection
    if collection is None:
        raise ValueError("a Blender collection is required")

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
