from math import isfinite
from .wavefunction_grid import DEFAULT_CHUNK_SIZE, grid_evaluation_memory


def suggest_grid(structure, *, spacing=0.25, padding=6.0):
    """Suggest an axis-aligned Bohr grid enclosing the molecule and padding."""
    import numpy

    if structure.coordinates.unit != "bohr":
        raise ValueError("wavefunction grid coordinates must use bohr")
    if (isinstance(spacing, bool) or not isfinite(spacing) or spacing <= 0
            or isinstance(padding, bool) or not isfinite(padding) or padding < 0):
        raise ValueError("spacing must be positive and padding non-negative finite numbers")
    coordinates = numpy.asarray(structure.coordinates.values)
    if not coordinates.size or not numpy.isfinite(coordinates).all():
        raise ValueError("structure must have finite atomic coordinates")
    lower = numpy.floor((coordinates.min(axis=0) - padding) / spacing) * spacing
    upper = numpy.ceil((coordinates.max(axis=0) + padding) / spacing) * spacing
    shape = tuple(int(round((high - low) / spacing)) + 1 for low, high in zip(lower, upper))
    return {"origin": tuple(float(value) for value in lower),
            "step_vectors": ((spacing, 0., 0.), (0., spacing, 0.), (0., 0., spacing)),
            "shape": shape}


def estimate_grid_memory(shape, basis_count, *, block_size=DEFAULT_CHUNK_SIZE,
                         operation="mo", orbital_count=None):
    """Use the evaluator's actual block limit and common-array memory estimate."""
    return grid_evaluation_memory(shape, basis_count, chunk_size=block_size,
                                  operation=operation, orbital_count=orbital_count)
