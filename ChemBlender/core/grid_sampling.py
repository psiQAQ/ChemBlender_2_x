"""Affine grid sampling, scientific slices/profiles and reproducible CSV export."""

from dataclasses import dataclass
import operator

from .grid_cache_service import _ANGSTROM_SCALE
from .grid_lod import _dataset_index
from .model import Grid3D


_SAMPLE_BLOCK_SIZE = 16384


@dataclass(frozen=True, slots=True)
class GridSample:
    points: object
    values: object
    valid_mask: object
    distance: object | None = None


def _integer(value, name, minimum):
    import numpy

    if isinstance(value, (bool, numpy.bool_)):
        raise ValueError(f"{name} must be an integer >= {minimum}")
    try:
        value = operator.index(value)
    except TypeError as error:
        raise ValueError(f"{name} must be an integer >= {minimum}") from error
    if value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def validate_plane(*, origin, u_vector, v_vector, counts, dataset_index=0):
    """Normalize a plane's full spans and endpoint-inclusive counts; read no grid."""
    import numpy

    origin = Grid3D._vector(origin, "origin")
    u_vector = Grid3D._vector(u_vector, "u_vector")
    v_vector = Grid3D._vector(v_vector, "v_vector")
    with numpy.errstate(over="ignore", invalid="ignore"):
        area = numpy.linalg.norm(numpy.cross(u_vector, v_vector))
    if not numpy.isfinite(area) or area == 0:
        raise ValueError("plane span vectors must be finite and linearly independent")
    counts = tuple(counts)
    if len(counts) != 2:
        raise ValueError("counts must contain two integers >= 2")
    return {
        "origin": origin, "u_vector": u_vector, "v_vector": v_vector,
        "counts": tuple(_integer(value, "counts", 2) for value in counts),
        "dataset_index": _integer(dataset_index, "dataset_index", 0),
    }


def validate_profile(*, start, end, sample_count, dataset_index=0):
    """Normalize a segment and its endpoint-inclusive count; read no grid."""
    import numpy

    start = Grid3D._vector(start, "start")
    end = Grid3D._vector(end, "end")
    with numpy.errstate(over="ignore", invalid="ignore"):
        length = numpy.linalg.norm(numpy.asarray(end) - start)
    if not numpy.isfinite(length) or length == 0:
        raise ValueError("profile endpoints must define a finite nonzero segment")
    return {
        "start": start, "end": end,
        "sample_count": _integer(sample_count, "sample_count", 2),
        "dataset_index": _integer(dataset_index, "dataset_index", 0),
    }


def _check_cancel(is_cancelled):
    if is_cancelled is not None:
        from .exporters.xyz import ExportCancelled, _cancelled
        if _cancelled(is_cancelled):
            raise ExportCancelled("grid sample export cancelled")


def _sample_points(grid, points, *, dataset_index, coordinate_unit, is_cancelled=None):
    import numpy

    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    if isinstance(dataset_index, numpy.bool_):
        raise TypeError("dataset_index must be an integer")
    dataset_index = _dataset_index(grid, dataset_index)
    coordinate_unit = grid.coordinate_unit if coordinate_unit is None else coordinate_unit
    if grid.coordinate_unit not in _ANGSTROM_SCALE or coordinate_unit not in _ANGSTROM_SCALE:
        raise ValueError("grid sampling requires bohr or angstrom coordinates")
    if numpy.dtype(grid.data.dtype).kind not in "iuf":
        raise ValueError("grid sampling requires real numeric data")
    points = numpy.asarray(points)
    if points.ndim == 0 or points.shape[-1] != 3 or points.dtype.kind not in "iuf":
        raise ValueError("points must contain real coordinates with shape (..., 3)")
    if not numpy.isfinite(points).all():
        raise ValueError("query coordinates must be finite")
    result_shape = points.shape[:-1]
    points = numpy.asarray(points, dtype=numpy.float64).reshape(-1, 3)
    values = numpy.full(len(points), numpy.nan, dtype=numpy.float64)
    valid_mask = numpy.zeros(len(points), dtype=bool)
    shape = numpy.asarray(grid.grid_shape, dtype=numpy.int64)
    steps = numpy.asarray(grid.step_vectors, dtype=numpy.float64)
    scale = _ANGSTROM_SCALE[coordinate_unit] / _ANGSTROM_SCALE[grid.coordinate_unit]
    # Only inverse-roundoff at cell boundaries is snapped, never a full voxel.
    tolerance = 64 * numpy.finfo(numpy.float64).eps * numpy.maximum(shape, 1)
    _check_cancel(is_cancelled)
    for offset in range(0, len(points), _SAMPLE_BLOCK_SIZE):
        _check_cancel(is_cancelled)
        block = points[offset:offset + _SAMPLE_BLOCK_SIZE]
        with numpy.errstate(over="ignore", invalid="ignore"):
            fractional = numpy.linalg.solve(steps.T, (block * scale - grid.origin).T).T
        inside = numpy.isfinite(fractional).all(axis=1) & (
            (fractional >= -tolerance) & (fractional <= shape - 1 + tolerance)
        ).all(axis=1)
        selected = numpy.flatnonzero(inside)
        if not len(selected):
            continue
        fractional = numpy.clip(fractional[selected], 0, shape - 1)
        lower = numpy.floor(fractional).astype(numpy.int64)
        lower = numpy.minimum(lower, numpy.maximum(shape - 2, 0))
        upper = numpy.minimum(lower + 1, shape - 1)
        weight = fractional - lower
        sampled = numpy.zeros(len(selected), dtype=numpy.float64)
        valid = numpy.ones(len(selected), dtype=bool)
        for x in (0, 1):
            for y in (0, 1):
                for z in (0, 1):
                    corner = numpy.asarray((x, y, z), dtype=bool)
                    weights = numpy.prod(numpy.where(corner, weight, 1 - weight), axis=1)
                    contributing = weights != 0
                    if not contributing.any():
                        continue
                    indices = numpy.where(corner, upper, lower)[contributing]
                    key = tuple(indices.T)
                    if grid.data.dims[0] == "dataset":
                        key = (dataset_index, *key)
                    try:
                        raw = grid.data.values[key]
                    except (TypeError, NotImplementedError):
                        raw = numpy.asarray(grid.data.values)[key]
                    raw = numpy.asarray(raw, dtype=numpy.float64)
                    finite = numpy.isfinite(raw)
                    valid[contributing] &= finite
                    sampled[contributing] += weights[contributing] * numpy.where(finite, raw, 0)
        valid &= numpy.isfinite(sampled)
        output_indices = offset + selected[valid]
        values[output_indices] = sampled[valid]
        valid_mask[output_indices] = True
    _check_cancel(is_cancelled)
    return values.reshape(result_shape), valid_mask.reshape(result_shape)


def sample_grid_points(grid, points, *, dataset_index=None, coordinate_unit=None):
    """Trilinearly sample an affine grid; finite out-of-bounds points are NaN/False."""
    return _sample_points(grid, points, dataset_index=dataset_index,
                          coordinate_unit=coordinate_unit)


def _plane_points(settings):
    import numpy

    u = numpy.linspace(0., 1., settings["counts"][0])
    v = numpy.linspace(0., 1., settings["counts"][1])
    return (numpy.asarray(settings["origin"])
            + u[:, None, None] * numpy.asarray(settings["u_vector"])
            + v[None, :, None] * numpy.asarray(settings["v_vector"]))


def _profile_points(settings):
    import numpy

    return numpy.linspace(settings["start"], settings["end"], settings["sample_count"])


def _make_sample(grid, kind, settings, *, is_cancelled=None):
    import numpy

    _check_cancel(is_cancelled)
    points = _plane_points(settings) if kind == "plane" else _profile_points(settings)
    values, valid_mask = _sample_points(
        grid, points, dataset_index=settings["dataset_index"],
        coordinate_unit=None, is_cancelled=is_cancelled,
    )
    distance = (numpy.linalg.norm(points - settings["start"], axis=1)
                if kind == "profile" else None)
    return GridSample(points, values, valid_mask, distance)


def plane_slice(grid, *, origin, u_vector, v_vector, counts, dataset_index=0):
    """Sample full plane spans, including all edges, in grid coordinate units."""
    settings = validate_plane(origin=origin, u_vector=u_vector, v_vector=v_vector,
                              counts=counts, dataset_index=dataset_index)
    return _make_sample(grid, "plane", settings)


def line_profile(grid, *, start, end, sample_count, dataset_index=0):
    """Sample a finite segment including both endpoints, in grid coordinate units."""
    settings = validate_profile(start=start, end=end, sample_count=sample_count,
                                dataset_index=dataset_index)
    return _make_sample(grid, "profile", settings)


def export_grid_sample(destination, grid, *, kind, settings, is_cancelled=None):
    """Recompute scientific coordinates and atomically export CSV plus metadata."""
    import csv
    import io
    import json

    from .exporters.xyz import ExportReport, atomic_write_chunks

    fields = {
        "plane": ("origin", "u_vector", "v_vector", "counts"),
        "profile": ("start", "end", "sample_count"),
    }
    if kind not in fields:
        raise ValueError("kind must be plane or profile")
    settings = dict(settings)
    parameters = {name: settings[name] for name in fields[kind]}
    parameters["dataset_index"] = settings.get("dataset_index", 0)
    parameters = (validate_plane(**parameters) if kind == "plane"
                  else validate_profile(**parameters))
    sample = _make_sample(grid, kind, parameters, is_cancelled=is_cancelled)
    metadata = {
        "format": "chemblender_grid_sample", "version": 1, "kind": kind,
        "grid_id": str(grid.id), "grid_revision": grid.revision,
        "structure_id": str(grid.structure_id) if grid.structure_id else None,
        "source_calculation": str(grid.source_calculation) if grid.source_calculation else None,
        "provenance_ids": [str(value) for value in grid.provenance_ids],
        "semantic_role": grid.semantic_role, "value_unit": grid.data.unit,
        "coordinate_unit": grid.coordinate_unit,
        "grid_origin": grid.origin, "grid_step_vectors": grid.step_vectors,
        "grid_shape": grid.grid_shape, "sampling": parameters,
    }

    def chunks():
        yield "# " + json.dumps(metadata, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("x", "y", "z", "distance", "value", "valid_mask",
                         "coordinate_unit", "value_unit"))
        for index, (point, value, valid) in enumerate(zip(
            sample.points.reshape(-1, 3), sample.values.flat, sample.valid_mask.flat,
        )):
            _check_cancel(is_cancelled)
            writer.writerow((*(format(number, ".17g") for number in point),
                "" if sample.distance is None else format(sample.distance[index], ".17g"),
                format(value, ".17g") if valid else "", int(valid),
                grid.coordinate_unit, grid.data.unit))
            if index % 256 == 255:
                yield stream.getvalue()
                stream.seek(0)
                stream.truncate()
        yield stream.getvalue()

    atomic_write_chunks(destination, chunks(), is_cancelled=is_cancelled)
    return ExportReport("csv", True, 1, False)
