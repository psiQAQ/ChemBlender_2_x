"""Existing grid derivations exposed through the existing Worker v1 contract."""

from cbq_core.model import Grid3D
from .protocol import ProtocolError
from .wavefunction_operations import _output, _parameters


def _grids(context, request, count):
    if len(request.inputs) != count:
        raise ProtocolError(f"{request.operation_id} requires {count} Grid3D inputs")
    values = tuple(context.project.datasets[value.entity_id] for value in request.inputs)
    if any(not isinstance(value, Grid3D) for value in values):
        raise ProtocolError("Grid operation requires Grid3D inputs")
    return values


def _difference(context, request):
    from ..core.grid_difference import derive_grid_difference
    parameters = _parameters(request, set(), {"left_dataset_index", "right_dataset_index"})
    return _output(derive_grid_difference(*_grids(context, request, 2),
        cancel_check=context.is_cancelled, **parameters))


def _semantics(context, request):
    from ..core.grid_semantics import resolve_grid_semantics
    parameters = _parameters(request, {"dataset_index", "preset_id", "value_unit"})
    if "chunk_size" in parameters:
        raise ProtocolError("Semantic assignment does not accept chunk_size")
    return _output(resolve_grid_semantics(_grids(context, request, 1)[0], **parameters))


def register_grid_operations(registry):
    registry.register("grid.difference", "1", _difference)
    registry.register("grid.resolve_semantics", "1", _semantics)
