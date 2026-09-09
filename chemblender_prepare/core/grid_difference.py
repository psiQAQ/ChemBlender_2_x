"""Explicit density subtraction on one shared scientific grid, without resampling."""

import operator
from concurrent.futures import CancelledError
from uuid import UUID, uuid5

from cbq_core.cache_identity import derivation_cache_key
from cbq_core.grid_semantics import GRID_SEMANTIC_PRESETS
from cbq_core.grid_semantics import _selected_values
from cbq_core.model import ArrayData
from cbq_core.model import DatasetStatus
from cbq_core.model import Grid3D
from cbq_core.model import ImportBatch
from cbq_core.model import ProvenanceRecord


DERIVATION_VERSION = "1"
_NAMESPACE = UUID("ff5a4cf8-1b03-49ee-a496-b897b7d88658")


def derive_grid_difference(
    left, right, *, left_dataset_index=0, right_dataset_index=0,
    cancel_check=None, chunk_size=65536,
):
    """Return left minus right as one owned Grid3D and its two-input provenance.

    Inputs must be complete electron densities with identical affine coordinates,
    units and a shared non-null structure ID. Chunk size only bounds temporary
    arithmetic arrays; the complete float64 output is retained in the result.
    """
    import numpy

    if not isinstance(left, Grid3D) or not isinstance(right, Grid3D):
        raise TypeError("density difference inputs must be Grid3D")
    if cancel_check is not None and not callable(cancel_check):
        raise TypeError("cancel_check must be callable or None")
    if isinstance(chunk_size, bool):
        raise TypeError("chunk_size must be an integer")
    chunk_size = operator.index(chunk_size)
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if left.structure_id is None or left.structure_id != right.structure_id:
        raise ValueError("density difference requires the same non-null structure_id")
    if any(grid.status is not DatasetStatus.COMPLETE for grid in (left, right)):
        raise ValueError("density difference requires complete inputs")
    if any(grid.semantic_role != "electron_density" for grid in (left, right)):
        raise ValueError("density difference requires electron_density inputs")
    units = GRID_SEMANTIC_PRESETS["electron_density"].value_units
    if left.data.unit not in units or left.data.unit != right.data.unit:
        raise ValueError("density difference requires the same supported density unit")
    if (
        left.coordinate_unit not in {"angstrom", "bohr"}
        or left.coordinate_unit != right.coordinate_unit
        or left.grid_shape != right.grid_shape
        or left.origin != right.origin
        or left.step_vectors != right.step_vectors
    ):
        raise ValueError("density difference requires identical affine grids and coordinate units")

    def check():
        if cancel_check is not None and cancel_check():
            raise CancelledError("density difference was cancelled")

    check()
    left_values, left_dataset_index = _selected_values(left, left_dataset_index)
    right_values, right_dataset_index = _selected_values(right, right_dataset_index)
    left_values, right_values = numpy.asarray(left_values), numpy.asarray(right_values)
    if any(array.dtype.kind not in "iuf" for array in (left_values, right_values)):
        raise ValueError("density values must be real numeric arrays")
    check()
    values = numpy.empty(left.grid_shape, dtype=numpy.float64)
    flattened = values.reshape(-1)
    for start in range(0, values.size, chunk_size):
        check()
        stop = min(values.size, start + chunk_size)
        first = numpy.asarray(left_values.flat[start:stop], dtype=numpy.float64)
        second = numpy.asarray(right_values.flat[start:stop], dtype=numpy.float64)
        if not numpy.all(numpy.isfinite(first)) or not numpy.all(numpy.isfinite(second)):
            raise ValueError("density difference inputs must contain finite values")
        with numpy.errstate(over="ignore", invalid="ignore"):
            numpy.subtract(first, second, out=flattened[start:stop])
        if not numpy.all(numpy.isfinite(flattened[start:stop])):
            raise ValueError("density difference produced non-finite values")
    check()
    parameters = {
        "left_dataset_index": left_dataset_index,
        "right_dataset_index": right_dataset_index,
        "operation": "left_minus_right",
        "value_unit": left.data.unit,
    }
    revision = derivation_cache_key(
        ((left.id, left.revision), (right.id, right.revision)),
        "grid_difference", DERIVATION_VERSION, parameters,
    )
    provenance_id = uuid5(_NAMESPACE, f"{revision}:provenance")
    provenance = ProvenanceRecord(
        id=provenance_id, revision=revision, producer="ChemBlender density difference",
        producer_version=DERIVATION_VERSION, source="", source_hash=revision,
        parent_ids=tuple(dict.fromkeys((left.id, right.id, *left.provenance_ids, *right.provenance_ids))),
        operation="grid_difference", parameters=tuple(parameters.items()),
    )
    result = Grid3D(
        id=uuid5(_NAMESPACE, f"{revision}:dataset"), revision=revision,
        semantic_role="difference_density", domain="grid",
        data=ArrayData(values, ("x", "y", "z"), left.data.unit),
        status=DatasetStatus.COMPLETE,
        source_calculation=left.source_calculation if left.source_calculation == right.source_calculation else None,
        provenance_ids=(provenance_id,), origin=left.origin, step_vectors=left.step_vectors,
        coordinate_unit=left.coordinate_unit, structure_id=left.structure_id,
    )
    return ImportBatch(datasets=(result,), provenance=(provenance,))
