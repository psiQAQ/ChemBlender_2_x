import hashlib
import json
import operator
from math import isfinite
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
DERIVATION_VERSION = "1"


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


def _grid_points(origin, step_vectors, shape):
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
    try:
        shape = tuple(operator.index(value) for value in shape)
    except TypeError as error:
        raise ValueError("shape must contain three positive integers") from error
    if len(shape) != 3 or any(value <= 0 for value in shape):
        raise ValueError("shape must contain three positive integers")
    steps = numpy.asarray(step_vectors, dtype=float)
    if numpy.linalg.det(steps) == 0.0:
        raise ValueError("step_vectors must be linearly independent")
    indices = numpy.indices(shape, dtype=float).reshape(3, -1).T
    points = numpy.asarray(origin, dtype=float) + indices @ steps
    return (
        tuple(float(value) for value in origin),
        tuple(tuple(float(value) for value in vector) for vector in step_vectors),
        shape,
        points,
    )


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
    origin, step_vectors, shape, points = _grid_points(origin, step_vectors, shape)
    coefficients = selected.coefficients.values[orbital_index : orbital_index + 1]
    values = _checked_values(
        _evaluate_channel(structure, basis_set, coefficients, points),
        1,
        points.shape[0],
    )[0]
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
):
    import numpy

    _validate_entities(structure, basis_set, orbital_set)
    for channel in orbital_set.channels:
        if channel.occupations is None:
            raise ValueError(
                f"orbital occupations are required for density channel {channel.label}"
            )
    origin, step_vectors, shape, points = _grid_points(origin, step_vectors, shape)
    density = numpy.zeros(points.shape[0], dtype=float)
    for channel in orbital_set.channels:
        orbital_count = channel.coefficients.shape[0]
        values = _checked_values(
            _evaluate_channel(
                structure, basis_set, channel.coefficients.values, points
            ),
            orbital_count,
            points.shape[0],
        )
        density += numpy.einsum(
            "i,ip,ip->p", channel.occupations.values, values, values
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
