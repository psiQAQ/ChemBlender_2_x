import hashlib
import json
import operator
import re
import sys
from concurrent.futures import CancelledError
from math import isfinite, prod
from uuid import uuid4

from .model import (
    ArrayData,
    BasisFunctionKind,
    BasisSet,
    DatasetStatus,
    Grid3D,
    ImportBatch,
    OrbitalKind,
    OrbitalSet,
    ProvenanceRecord,
    Structure,
)


BACKEND_NAME = "qc-gbasis"
BACKEND_VERSION = "0.1.0"
DERIVATION_VERSION = "2"
DEFAULT_CHUNK_SIZE = 8192
_WORKING_BYTES = 64 * 1024 * 1024
_NTO_MARKER = re.compile(
    r"(?<![a-z0-9])ntos?(?![a-z0-9])|natural[\s_-]+transition[\s_-]+orbitals?",
    re.IGNORECASE,
)


class GBasisDependencyError(RuntimeError):
    pass


def _require_gbasis_version():
    try:
        from importlib.metadata import PackageNotFoundError, version

        actual_version = version(BACKEND_NAME)
    except PackageNotFoundError as error:
        raise GBasisDependencyError(
            f"cannot determine installed {BACKEND_NAME} version"
        ) from error
    if actual_version != BACKEND_VERSION:
        raise GBasisDependencyError(
            f"wavefunction evaluation requires {BACKEND_NAME}=={BACKEND_VERSION}; "
            f"found {actual_version}"
        )


def _validate_entities(structure, basis_set, orbital_set):
    import numpy

    if not isinstance(structure, Structure):
        raise TypeError("structure must be a Structure")
    if not isinstance(basis_set, BasisSet):
        raise TypeError("basis_set must be a BasisSet")
    if not isinstance(orbital_set, OrbitalSet):
        raise TypeError("orbital_set must be an OrbitalSet")
    if basis_set.structure_id != structure.id:
        raise ValueError("basis_set does not reference structure")
    if orbital_set.structure_id != structure.id:
        raise ValueError("orbital_set does not reference structure")
    if orbital_set.basis_set_id != basis_set.id:
        raise ValueError("orbital_set does not reference basis_set")
    if structure.coordinates.unit != "bohr":
        raise ValueError(
            "wavefunction evaluation requires structure coordinates in bohr"
        )
    if basis_set.primitive_normalization != "l2":
        raise ValueError("GBasis evaluation requires L2 primitive normalization")
    if orbital_set.kind is OrbitalKind.GENERALIZED:
        raise NotImplementedError("generalized spinor evaluation is not supported")
    for channel in orbital_set.channels:
        coefficients = numpy.asarray(channel.coefficients.values)
        if numpy.iscomplexobj(coefficients):
            raise NotImplementedError("complex orbital coefficients are not supported")
        if coefficients.shape[1] != basis_set.basis_function_count:
            raise ValueError("orbital coefficient width must match basis_set")
        if not numpy.all(numpy.isfinite(coefficients)):
            raise ValueError("orbital coefficients must be finite")


def _positive_index(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        value = operator.index(value)
    except TypeError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def grid_evaluation_memory(
    shape, basis_count, *, chunk_size=DEFAULT_CHUNK_SIZE,
    orbital_count=None, operation="mo",
):
    """Bound point blocks; estimate float64 arrays, excluding backend overhead."""
    shape = tuple(_positive_index(value, "shape") for value in shape)
    if len(shape) != 3:
        raise ValueError("shape must contain three positive integers")
    basis_count = _positive_index(basis_count, "basis_count")
    chunk_size = _positive_index(chunk_size, "chunk_size")
    if operation not in {"mo", "density", "spin", "esp"}:
        raise ValueError("unknown wavefunction operation")
    if orbital_count is None:
        orbital_count = 1 if operation == "mo" else basis_count
    orbital_count = _positive_index(orbital_count, "orbital_count")
    point_count = prod(shape)
    if point_count > sys.maxsize // 8:
        raise ValueError("grid output exceeds the addressable array size")
    # ESP materializes AO-pair integrals. Keep their point axis bounded too.
    components = (4 * basis_count**2 + 16 if operation == "esp"
                  else 4 * basis_count + 2 * orbital_count + 16)
    chunk_size = min(point_count, chunk_size, DEFAULT_CHUNK_SIZE,
                     max(1, _WORKING_BYTES // (8 * components)))
    fixed = 8 * (basis_count**2 if operation == "esp"
                 else basis_count * orbital_count)
    working = 8 * chunk_size * components + fixed
    output = 8 * point_count
    return {"point_count": point_count, "output_bytes": output,
            "working_bytes": working, "estimated_bytes": output + working,
            "chunk_size": chunk_size}


def _check_cancel(cancel_check):
    if cancel_check is not None and cancel_check():
        raise CancelledError("wavefunction evaluation was cancelled")


def _occupations(orbital_set, source_provenance=()):
    import numpy

    for record in source_provenance:
        if record.id in orbital_set.provenance_ids and _NTO_MARKER.search(
            " ".join((record.operation, record.source, str(record.parameters)))
        ):
            raise ValueError("NTO weights cannot be used as electron occupations")
    result = []
    for channel in orbital_set.channels:
        if channel.occupations is None:
            raise ValueError(
                f"orbital occupations are required for density channel {channel.label}"
            )
        values = numpy.asarray(channel.occupations.values)
        if (numpy.iscomplexobj(values) or not numpy.all(numpy.isfinite(values))
                or numpy.any(values < 0.0)
                or numpy.any(values > (2.0 if channel.label == "restricted" else 1.0))):
            raise ValueError("orbital occupations must be finite real values in the spin range")
        result.append(values)
    return tuple(result)


def _grid_geometry(origin, step_vectors, shape):
    import numpy

    origin = tuple(origin)
    step_vectors = tuple(tuple(vector) for vector in step_vectors)
    shape = tuple(shape)
    if len(origin) != 3 or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        for value in origin
    ):
        raise ValueError("origin must contain three finite numbers")
    if len(step_vectors) != 3 or any(len(vector) != 3 for vector in step_vectors):
        raise ValueError("step_vectors must contain three 3D vectors")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        for vector in step_vectors
        for value in vector
    ):
        raise ValueError("step_vectors must contain finite numbers")
    shape = tuple(_positive_index(value, "shape") for value in shape)
    if len(shape) != 3:
        raise ValueError("shape must contain three positive integers")
    steps = numpy.asarray(step_vectors, dtype=float)
    if numpy.linalg.det(steps) == 0.0:
        raise ValueError("step_vectors must be linearly independent")
    return (
        tuple(float(value) for value in origin),
        tuple(tuple(float(value) for value in vector) for vector in step_vectors),
        shape,
    )


def _evaluate_grid(
    origin, step_vectors, shape, evaluate, *, basis_count, operation,
    orbital_count=None, chunk_size=DEFAULT_CHUNK_SIZE, cancel_check=None,
    progress=None,
):
    """Allocate one output and publish it only after every point block succeeds."""
    import numpy

    for callback in (cancel_check, progress):
        if callback is not None and not callable(callback):
            raise TypeError("cancel_check and progress must be callable or None")
    origin, step_vectors, shape = _grid_geometry(origin, step_vectors, shape)
    estimate = grid_evaluation_memory(
        shape, basis_count, orbital_count=orbital_count,
        chunk_size=chunk_size, operation=operation,
    )
    count, chunk_size = estimate["point_count"], estimate["chunk_size"]
    _check_cancel(cancel_check)
    if progress is not None:
        progress(0, count)
    _check_cancel(cancel_check)
    output = numpy.empty(count, dtype=float)
    steps = numpy.asarray(step_vectors, dtype=float)
    for start in range(0, count, chunk_size):
        _check_cancel(cancel_check)
        stop = min(start + chunk_size, count)
        flat = numpy.arange(start, stop, dtype=numpy.intp)
        indices = numpy.column_stack(
            (flat // (shape[1] * shape[2]), (flat // shape[2]) % shape[1],
             flat % shape[2])
        )
        points = numpy.asarray(origin) + indices @ steps
        if not numpy.all(numpy.isfinite(points)):
            raise ValueError("grid coordinates must be finite")
        values = numpy.asarray(evaluate(points))
        _check_cancel(cancel_check)
        if values.shape != (stop - start,):
            raise ValueError("wavefunction backend returned an unexpected value shape")
        if numpy.iscomplexobj(values):
            raise NotImplementedError("complex wavefunction values are not supported")
        if not numpy.all(numpy.isfinite(values)):
            raise ValueError("wavefunction backend returned non-finite values")
        output[start:stop] = values
        if progress is not None:
            progress(stop, count)
    _check_cancel(cancel_check)
    return origin, step_vectors, shape, output


def _gbasis_shells(structure, basis_set, shell_type):
    import numpy

    conventions = {
        (item.angular_momentum, item.kind): item.functions
        for item in basis_set.conventions
    }

    class ChemBlenderShell(shell_type):
        def assign_norm_cont(self):
            component_count = (self.angmom + 1) * (self.angmom + 2) // 2
            self.norm_cont = numpy.ones((component_count, self.coeffs.shape[1]))

        @property
        def angmom_components_cart(self):
            functions = conventions.get((self.angmom, BasisFunctionKind.CARTESIAN))
            if functions is None:
                return super().angmom_components_cart
            return numpy.asarray(
                [
                    (
                        name.lower().count("x"),
                        name.lower().count("y"),
                        name.lower().count("z"),
                    )
                    for name in functions
                ],
                dtype=int,
            )

        @property
        def angmom_components_sph(self):
            functions = conventions.get((self.angmom, BasisFunctionKind.PURE))
            if functions is None:
                raise ValueError(
                    f"missing pure convention for angular momentum {self.angmom}"
                )
            return tuple(functions)

    coordinates = structure.coordinates.values
    result = []
    for shell in basis_set.shells:
        exponents = numpy.asarray(shell.exponents.values, dtype=float)
        coefficients = numpy.asarray(shell.coefficients.values, dtype=float)
        for column, (angular_momentum, kind) in enumerate(
            zip(shell.angular_momenta, shell.kinds)
        ):
            if (angular_momentum, kind) not in conventions:
                raise ValueError(
                    "basis convention is missing for "
                    f"angular momentum {angular_momentum} and kind {kind.value}"
                )
            result.append(
                ChemBlenderShell(
                    angular_momentum,
                    numpy.asarray(coordinates[shell.center_atom], dtype=float),
                    coefficients[:, column : column + 1],
                    exponents,
                    "cartesian" if kind is BasisFunctionKind.CARTESIAN else "spherical",
                    icenter=shell.center_atom,
                )
            )
    return tuple(result)


def _basis_function_signs(basis_set):
    conventions = {
        (item.angular_momentum, item.kind): item.functions
        for item in basis_set.conventions
    }
    signs = []
    for shell in basis_set.shells:
        for angular_momentum, kind in zip(shell.angular_momenta, shell.kinds):
            functions = conventions[(angular_momentum, kind)]
            signs.extend(
                -1.0
                if kind is BasisFunctionKind.CARTESIAN and name.startswith("-")
                else 1.0
                for name in functions
            )
    return tuple(signs)


def _evaluate_channel(structure, basis_set, coefficients, points):
    try:
        import numpy
        from gbasis.contractions import GeneralizedContractionShell
        from gbasis.evals.eval import evaluate_basis
    except ImportError as error:
        raise GBasisDependencyError(
            "wavefunction evaluation requires the optional qc-gbasis==0.1.0 dependency"
        ) from error
    _require_gbasis_version()
    shells = _gbasis_shells(structure, basis_set, GeneralizedContractionShell)
    signs = numpy.asarray(_basis_function_signs(basis_set), dtype=float)
    if coefficients is None:
        return evaluate_basis(shells, points) * signs[:, numpy.newaxis]
    if numpy.iscomplexobj(coefficients):
        raise NotImplementedError("complex orbital coefficients are not supported")
    transform = numpy.asarray(coefficients, dtype=float) * signs[numpy.newaxis, :]
    return evaluate_basis(shells, points, transform=transform)


def _channel(orbital_set, label):
    for channel in orbital_set.channels:
        if channel.label == label:
            return channel
    raise ValueError(f"orbital channel is unavailable: {label}")


def _checked_values(values, orbital_count, point_count):
    import numpy

    values = numpy.asarray(values)
    if numpy.iscomplexobj(values):
        raise NotImplementedError("complex orbital values are not supported")
    if values.shape != (orbital_count, point_count):
        raise ValueError("GBasis returned an unexpected orbital array shape")
    values = numpy.asarray(values, dtype=float)
    if not numpy.all(numpy.isfinite(values)):
        raise ValueError("GBasis returned non-finite orbital values")
    return values


def _derivation_identity(structure, basis_set, orbital_set, operation, parameters):
    payload = {
        "structure": [str(structure.id), structure.revision],
        "basis_set": [str(basis_set.id), basis_set.revision],
        "orbital_set": [str(orbital_set.id), orbital_set.revision],
        "operation": operation,
        "operation_version": DERIVATION_VERSION,
        "backend": [BACKEND_NAME, BACKEND_VERSION],
        "parameters": parameters,
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _batch(
    structure,
    basis_set,
    orbital_set,
    *,
    semantic_role,
    unit,
    values,
    origin,
    step_vectors,
    shape,
    parameters,
):
    operation = f"evaluate_{semantic_role}_grid"
    identity_parameters = {
        "origin": origin,
        "step_vectors": step_vectors,
        "shape": shape,
        **parameters,
    }
    revision = _derivation_identity(
        structure, basis_set, orbital_set, operation, identity_parameters
    )
    provenance_id = uuid4()
    provenance_parameters = (
        ("backend", BACKEND_NAME),
        ("backend_version", BACKEND_VERSION),
        ("structure_revision", structure.revision),
        ("basis_revision", basis_set.revision),
        ("orbital_revision", orbital_set.revision),
        ("origin", origin),
        ("step_vectors", step_vectors),
        ("shape", shape),
        *tuple(parameters.items()),
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer=BACKEND_NAME,
        producer_version=BACKEND_VERSION,
        source="",
        source_hash=revision,
        parent_ids=(structure.id, basis_set.id, orbital_set.id),
        operation=operation,
        parameters=provenance_parameters,
    )
    grid = Grid3D(
        id=uuid4(),
        revision=revision,
        semantic_role=semantic_role,
        domain="grid",
        data=ArrayData(values.reshape(shape), ("x", "y", "z"), unit),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        origin=origin,
        step_vectors=step_vectors,
        coordinate_unit="bohr",
        structure_id=structure.id,
    )
    return ImportBatch(datasets=(grid,), provenance=(provenance,))


def evaluate_molecular_orbital_grid(
    structure,
    basis_set,
    orbital_set,
    *,
    channel,
    orbital_index,
    origin,
    step_vectors,
    shape,
    chunk_size=DEFAULT_CHUNK_SIZE,
    cancel_check=None,
    progress=None,
):
    _validate_entities(structure, basis_set, orbital_set)
    selected = _channel(orbital_set, channel)
    if isinstance(orbital_index, bool):
        raise IndexError("orbital_index must be a valid zero-based orbital index")
    try:
        orbital_index = operator.index(orbital_index)
    except TypeError as error:
        raise IndexError(
            "orbital_index must be a valid zero-based orbital index"
        ) from error
    orbital_count = selected.coefficients.shape[0]
    if not 0 <= orbital_index < orbital_count:
        raise IndexError("orbital_index is outside the selected channel")
    coefficients = selected.coefficients.values[orbital_index : orbital_index + 1]
    origin, step_vectors, shape, values = _evaluate_grid(
        origin, step_vectors, shape,
        lambda points: _checked_values(
            _evaluate_channel(structure, basis_set, coefficients, points),
            1, points.shape[0],
        )[0],
        basis_count=basis_set.basis_function_count, operation="mo",
        chunk_size=chunk_size, cancel_check=cancel_check, progress=progress,
    )
    return _batch(
        structure,
        basis_set,
        orbital_set,
        semantic_role="molecular_orbital",
        unit="inverse_bohr_to_three_halves",
        values=values,
        origin=origin,
        step_vectors=step_vectors,
        shape=shape,
        parameters={"channel": channel, "orbital_index": orbital_index},
    )


def evaluate_electron_density_grid(
    structure,
    basis_set,
    orbital_set,
    *,
    origin,
    step_vectors,
    shape,
    chunk_size=DEFAULT_CHUNK_SIZE,
    cancel_check=None,
    progress=None,
    source_provenance=(),
):
    import numpy

    _validate_entities(structure, basis_set, orbital_set)
    occupations = _occupations(orbital_set, source_provenance)

    def evaluate(points):
        density = numpy.zeros(points.shape[0], dtype=float)
        for channel, occupation in zip(orbital_set.channels, occupations):
            _check_cancel(cancel_check)
            values = _checked_values(
                _evaluate_channel(
                    structure, basis_set, channel.coefficients.values, points
                ), channel.coefficients.shape[0], points.shape[0],
            )
            density += numpy.einsum("i,ip,ip->p", occupation, values, values)
        return density

    origin, step_vectors, shape, density = _evaluate_grid(
        origin, step_vectors, shape, evaluate,
        basis_count=basis_set.basis_function_count, operation="density",
        orbital_count=max(item.coefficients.shape[0] for item in orbital_set.channels),
        chunk_size=chunk_size, cancel_check=cancel_check, progress=progress,
    )
    return _batch(
        structure,
        basis_set,
        orbital_set,
        semantic_role="electron_density",
        unit="electron_per_cubic_bohr",
        values=density,
        origin=origin,
        step_vectors=step_vectors,
        shape=shape,
        parameters={
            "channels": tuple(channel.label for channel in orbital_set.channels)
        },
    )
