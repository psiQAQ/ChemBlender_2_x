"""Pure staging transaction for derived Grid3D OpenVDB volume caches."""

import operator
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .grid_lod import volume_render_cache_key
from .model import Grid3D
from .storage.atomic_paths import short_sibling_temporary_path


_ANGSTROM_SCALE = {
    "angstrom": 1.0,
    "bohr": 0.529177210903,
}


@dataclass(frozen=True, slots=True)
class VolumeCacheRequest:
    cache_path: Path
    dataset_index: int | None = None

    def __post_init__(self):
        path = Path(os.path.abspath(self.cache_path))
        if path.suffix.lower() != ".vdb":
            raise ValueError("cache_path must use the .vdb suffix")
        if path.is_symlink() or path.is_junction():
            raise OSError("cache_path must not be a filesystem link")
        object.__setattr__(self, "cache_path", path)


@dataclass(frozen=True, slots=True)
class CacheResult:
    status: str
    cache_path: Path
    render_key: str
    dataset_index: int
    progress: float


def _dataset_index(grid, dataset_index):
    if dataset_index is None:
        if grid.data.dims == ("x", "y", "z"):
            return 0
        raise ValueError("multi-dataset Grid3D requires an explicit dataset_index")
    if isinstance(dataset_index, bool):
        raise TypeError("dataset_index must be an integer")
    try:
        dataset_index = operator.index(dataset_index)
    except TypeError as error:
        raise TypeError("dataset_index must be an integer") from error
    count = grid.data.shape[0] if grid.data.dims[0] == "dataset" else 1
    if not 0 <= dataset_index < count:
        raise IndexError("dataset_index is outside the Grid3D dataset axis")
    return dataset_index


def _selected_values(grid, dataset_index):
    import numpy

    values = numpy.asarray(grid.data.values)
    if grid.data.dims == ("dataset", "x", "y", "z"):
        values = values[dataset_index]
    elif grid.data.dims != ("x", "y", "z"):
        raise ValueError(
            "Volume adapter requires xyz or dataset-xyz Grid3D dimensions"
        )
    return numpy.asarray(values, dtype=numpy.float32, order="C")


def _transform_matrix(grid, scale):
    steps = tuple(
        tuple(component * scale for component in vector) + (0.0,)
        for vector in grid.step_vectors
    )
    origin = tuple(component * scale for component in grid.origin) + (1.0,)
    return (*steps, origin)


def _metadata(grid, dataset_index, scale, render_key):
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
    return metadata


def volume_cache_path(cache_root, grid, *, dataset_index=None):
    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    dataset_index = _dataset_index(grid, dataset_index)
    return (
        Path(cache_root)
        / "volume"
        / f"{volume_render_cache_key(grid, dataset_index=dataset_index)}.vdb"
    )


def _checkpoint(stage, fraction, *, cancelled, progress):
    progress(stage, fraction)
    return cancelled()


def prepare_volume_cache(
    grid,
    request,
    *,
    writer,
    cancelled,
    progress,
):
    """Stage, verify and atomically publish one derived volume cache."""
    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    if not isinstance(request, VolumeCacheRequest):
        raise TypeError("request must be a VolumeCacheRequest")
    if not callable(cancelled) or not callable(progress):
        raise TypeError("cancelled and progress must be callable")
    if any(
        not callable(getattr(writer, name, None))
        for name in ("populate", "write", "validate")
    ):
        raise TypeError("writer must provide populate(), write() and validate()")
    dataset_index = _dataset_index(grid, request.dataset_index)
    try:
        scale = _ANGSTROM_SCALE[grid.coordinate_unit]
    except KeyError as error:
        raise ValueError(
            f"unsupported Grid3D coordinate unit: {grid.coordinate_unit}"
        ) from error
    cache_path = request.cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    render_key = volume_render_cache_key(grid, dataset_index=dataset_index)
    if cache_path.is_file():
        try:
            writer.validate(cache_path, ("density",), render_key)
        except MemoryError:
            raise
        except Exception:
            pass
        else:
            progress("cache_hit", 1.0)
            return CacheResult(
                "cache_hit", cache_path, render_key, dataset_index, 1.0
            )

    stages = (
        ("before_array_load", 0.1),
        ("after_dataset_slice", 0.35),
        ("after_vdb_population", 0.7),
        ("before_publish", 0.9),
    )
    if _checkpoint(*stages[0], cancelled=cancelled, progress=progress):
        return CacheResult(
            "cancelled", cache_path, render_key, dataset_index, stages[0][1]
        )
    values = _selected_values(grid, dataset_index)
    if _checkpoint(*stages[1], cancelled=cancelled, progress=progress):
        return CacheResult(
            "cancelled", cache_path, render_key, dataset_index, stages[1][1]
        )

    temporary = short_sibling_temporary_path(cache_path)
    try:
        metadata = _metadata(grid, dataset_index, scale, render_key)
        payload = writer.populate(
            values,
            _transform_matrix(grid, scale),
            metadata,
        )
        if _checkpoint(*stages[2], cancelled=cancelled, progress=progress):
            return CacheResult(
                "cancelled",
                cache_path,
                render_key,
                dataset_index,
                stages[2][1],
            )
        writer.write(
            temporary,
            payload,
            metadata,
        )
        writer.validate(temporary, ("density",), render_key)
        if _checkpoint(*stages[3], cancelled=cancelled, progress=progress):
            return CacheResult(
                "cancelled",
                cache_path,
                render_key,
                dataset_index,
                stages[3][1],
            )
        os.replace(temporary, cache_path)
    finally:
        active_error = sys.exception()
        try:
            temporary.unlink(missing_ok=True)
        except OSError as cleanup_error:
            if active_error is None:
                raise
            active_error.add_note(f"cache staging cleanup failed: {cleanup_error}")
    progress("published", 1.0)
    return CacheResult(
        "published", cache_path, render_key, dataset_index, 1.0
    )


__all__ = (
    "CacheResult",
    "VolumeCacheRequest",
    "prepare_volume_cache",
    "volume_cache_path",
)
