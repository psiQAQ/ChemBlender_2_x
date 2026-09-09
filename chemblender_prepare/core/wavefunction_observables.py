import hashlib
import json
from math import isfinite
from uuid import uuid4

from cbq_core.model import ArrayData
from cbq_core.model import AtomicProperty
from cbq_core.model import BasisSet
from cbq_core.model import DatasetStatus
from cbq_core.model import DensityMatrix
from cbq_core.model import DensityMatrixLevel
from cbq_core.model import DensityMatrixSpin
from cbq_core.model import Grid3D
from cbq_core.model import ImportBatch
from cbq_core.model import ProvenanceRecord
from cbq_core.model import Structure
from chemblender_prepare.core.wavefunction_grid import BACKEND_NAME
from chemblender_prepare.core.wavefunction_grid import BACKEND_VERSION
from chemblender_prepare.core.wavefunction_grid import DEFAULT_CHUNK_SIZE
from chemblender_prepare.core.wavefunction_grid import _basis_function_signs
from chemblender_prepare.core.wavefunction_grid import _check_cancel
from chemblender_prepare.core.wavefunction_grid import _evaluate_grid
from chemblender_prepare.core.wavefunction_grid import _gbasis_shells
from chemblender_prepare.core.wavefunction_grid import _occupations
from chemblender_prepare.core.wavefunction_grid import _require_gbasis_version
from chemblender_prepare.core.wavefunction_grid import _validate_entities


DERIVATION_VERSION = "2"


def _validate_density_entities(structure, basis_set, density_matrix):
    import numpy

    if not isinstance(structure, Structure):
        raise TypeError("structure must be a Structure")
    if not isinstance(basis_set, BasisSet):
        raise TypeError("basis_set must be a BasisSet")
    if not isinstance(density_matrix, DensityMatrix):
        raise TypeError("density_matrix must be a DensityMatrix")
    if basis_set.structure_id != structure.id:
        raise ValueError("basis_set does not reference structure")
    if density_matrix.structure_id != structure.id:
        raise ValueError("density_matrix does not reference structure")
    if density_matrix.basis_set_id != basis_set.id:
        raise ValueError("density_matrix does not reference basis_set")
    if structure.coordinates.unit != "bohr":
        raise ValueError("wavefunction evaluation requires coordinates in bohr")
    if basis_set.primitive_normalization != "l2":
        raise ValueError("GBasis evaluation requires L2 primitive normalization")
    expected = basis_set.basis_function_count
    if density_matrix.data.shape != (expected, expected):
        raise ValueError("density-matrix width must match basis_set")
    matrix = numpy.asarray(density_matrix.data.values)
    if (
        numpy.iscomplexobj(matrix)
        or not numpy.all(numpy.isfinite(matrix))
        or not numpy.allclose(matrix, matrix.T)
    ):
        raise ValueError("density_matrix must contain a finite real symmetric matrix")


def _evaluate_stored_basis(structure, basis_set, points):
    from chemblender_prepare.core.wavefunction_grid import _evaluate_channel

    return _evaluate_channel(structure, basis_set, None, points)


def _contract_density(density_matrix, basis_values):
    import numpy

    matrix = numpy.asarray(density_matrix.data.values, dtype=float)
    values = numpy.asarray(basis_values)
    if numpy.iscomplexobj(values):
        raise NotImplementedError("complex basis values are not supported")
    values = numpy.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[0] != matrix.shape[0]:
        raise ValueError("evaluated basis width does not match density matrix")
    if not numpy.all(numpy.isfinite(values)):
        raise ValueError("GBasis returned non-finite basis values")
    result = numpy.einsum("ij,ip,jp->p", matrix, values, values)
    if not numpy.all(numpy.isfinite(result)):
        raise ValueError("density contraction returned non-finite values")
    if density_matrix.spin_role is DensityMatrixSpin.TOTAL:
        minimum = float(result.min())
        if minimum < -1.0e-8:
            raise ValueError(f"total density is negative beyond tolerance: {minimum}")
        result = result.clip(min=0.0)
    return result


def _evaluate_esp(structure, basis_set, density_matrix, nuclear_charges, points):
    import numpy

    try:
        from gbasis.contractions import GeneralizedContractionShell
        from gbasis.evals.electrostatic_potential import electrostatic_potential
    except ImportError as error:
        from chemblender_prepare.core.wavefunction_grid import GBasisDependencyError

        raise GBasisDependencyError(
            "ESP evaluation requires the optional qc-gbasis==0.1.0 dependency"
        ) from error
    _require_gbasis_version()
    shells = _gbasis_shells(structure, basis_set, GeneralizedContractionShell)
    signs = numpy.asarray(_basis_function_signs(basis_set), dtype=float)
    matrix = numpy.asarray(density_matrix.data.values, dtype=float)
    matrix = signs[:, None] * matrix * signs[None, :]
    return electrostatic_potential(
        shells,
        matrix,
        points,
        numpy.asarray(structure.coordinates.values, dtype=float),
        numpy.asarray(nuclear_charges, dtype=float),
        threshold_dist=0.0,
    )


def _identity(parents, operation, parameters, *, backend=(BACKEND_NAME, BACKEND_VERSION)):
    payload = {
        "parents": [(str(entity.id), entity.revision) for entity in parents],
        "operation": operation,
        "operation_version": DERIVATION_VERSION,
        "backend": list(backend),
        "parameters": parameters,
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_density_matrix_from_orbitals(
    structure, basis_set, orbital_set, *, level, source_provenance=(),
    cancel_check=None,
):
    """Reconstruct a total AO matrix from occupations with an explicit level."""
    import numpy

    _validate_entities(structure, basis_set, orbital_set)
    if not isinstance(level, DensityMatrixLevel):
        raise TypeError("level must explicitly be a DensityMatrixLevel")
    if cancel_check is not None and not callable(cancel_check):
        raise TypeError("cancel_check must be callable or None")
    records = {record.id: record for record in source_provenance}
    for record_id in orbital_set.provenance_ids:
        if record_id not in records:
            raise ValueError("orbital source provenance is required for density reconstruction")
    occupations = _occupations(orbital_set, records.values())
    _check_cancel(cancel_check)
    width = basis_set.basis_function_count
    matrix = numpy.zeros((width, width), dtype=float)
    block = max(1, min(DEFAULT_CHUNK_SIZE, (64 * 1024 * 1024) // (16 * width)))
    for channel, occupation in zip(orbital_set.channels, occupations):
        coefficients = numpy.asarray(channel.coefficients.values)
        for start in range(0, coefficients.shape[0], block):
            _check_cancel(cancel_check)
            current = coefficients[start:start + block]
            matrix += current.T @ (occupation[start:start + block, None] * current)
    _check_cancel(cancel_check)
    if not numpy.all(numpy.isfinite(matrix)):
        raise ValueError("orbital density reconstruction returned non-finite values")
    parents = (structure, basis_set, orbital_set)
    parameters = {"backend": "numpy", "backend_version": numpy.__version__,
                  "density_level": level.value, "spin_role": "total",
                  "density_source": "orbital_occupations",
                  "channels": tuple(channel.label for channel in orbital_set.channels)}
    operation = "derive_density_matrix_from_orbitals"
    revision = _identity(parents, operation, parameters,
                         backend=("numpy", numpy.__version__))
    provenance_id = uuid4()
    provenance = ProvenanceRecord(
        id=provenance_id, revision=revision, producer="ChemBlender",
        producer_version=DERIVATION_VERSION, source="", source_hash=revision,
        parent_ids=tuple(entity.id for entity in parents), operation=operation,
        parameters=tuple(parameters.items()),
    )
    density = DensityMatrix(
        id=uuid4(), revision=revision, structure_id=structure.id,
        basis_set_id=basis_set.id, level=level, spin_role=DensityMatrixSpin.TOTAL,
        data=ArrayData(matrix, ("basis_function_row", "basis_function_column"),
                       "dimensionless"), source_calculation=None,
        provenance_ids=(provenance_id,),
    )
    return ImportBatch(density_matrices=(density,), provenance=(provenance,))


def _batch(
    parents,
    density_matrix,
    *,
    semantic_role,
    unit,
    values,
    origin,
    step_vectors,
    shape,
    parameters,
):
    import numpy

    operation = f"evaluate_{semantic_role}_grid"
    identity_parameters = {
        "origin": origin,
        "step_vectors": step_vectors,
        "shape": shape,
        **parameters,
    }
    revision = _identity(parents, operation, identity_parameters)
    values = numpy.asarray(values)
    if values.shape != (shape[0] * shape[1] * shape[2],):
        raise ValueError("observable backend returned an unexpected value shape")
    if numpy.iscomplexobj(values) or not numpy.all(numpy.isfinite(values)):
        raise ValueError("observable backend returned invalid values")
    provenance_id = uuid4()
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer=BACKEND_NAME,
        producer_version=BACKEND_VERSION,
        source="",
        source_hash=revision,
        parent_ids=tuple(entity.id for entity in parents),
        operation=operation,
        parameters=(
            ("backend", BACKEND_NAME),
            ("backend_version", BACKEND_VERSION),
            ("origin", origin),
            ("step_vectors", step_vectors),
            ("shape", shape),
            *tuple(parameters.items()),
        ),
    )
    grid = Grid3D(
        id=uuid4(),
        revision=revision,
        semantic_role=semantic_role,
        domain="grid",
        data=ArrayData(
            numpy.asarray(values, dtype=float).reshape(shape),
            ("x", "y", "z"),
            unit,
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=density_matrix.source_calculation,
        provenance_ids=(provenance_id,),
        origin=origin,
        step_vectors=step_vectors,
        coordinate_unit="bohr",
        structure_id=density_matrix.structure_id,
    )
    return ImportBatch(datasets=(grid,), provenance=(provenance,))


def evaluate_density_matrix_grid(
    structure,
    basis_set,
    density_matrix,
    *,
    origin,
    step_vectors,
    shape,
    chunk_size=DEFAULT_CHUNK_SIZE,
    cancel_check=None,
    progress=None,
):
    _validate_density_entities(structure, basis_set, density_matrix)
    role = (
        "electron_density"
        if density_matrix.spin_role is DensityMatrixSpin.TOTAL
        else "spin_density"
    )
    origin, step_vectors, shape, values = _evaluate_grid(
        origin, step_vectors, shape,
        lambda points: _contract_density(
            density_matrix, _evaluate_stored_basis(structure, basis_set, points)
        ),
        basis_count=basis_set.basis_function_count,
        operation="density" if role == "electron_density" else "spin",
        chunk_size=chunk_size, cancel_check=cancel_check, progress=progress,
    )
    return _batch(
        (structure, basis_set, density_matrix),
        density_matrix,
        semantic_role=role,
        unit="electron_per_cubic_bohr",
        values=values,
        origin=origin,
        step_vectors=step_vectors,
        shape=shape,
        parameters={
            "density_level": density_matrix.level.value,
            "spin_role": density_matrix.spin_role.value,
        },
    )


def evaluate_electrostatic_potential_grid(
    structure,
    basis_set,
    density_matrix,
    nuclear_charges,
    *,
    origin,
    step_vectors,
    shape,
    nuclear_exclusion_radius=1.0e-8,
    chunk_size=DEFAULT_CHUNK_SIZE,
    cancel_check=None,
    progress=None,
):
    import numpy

    _validate_density_entities(structure, basis_set, density_matrix)
    if density_matrix.spin_role is not DensityMatrixSpin.TOTAL:
        raise ValueError("ESP requires a total density matrix")
    if not isinstance(nuclear_charges, AtomicProperty):
        raise TypeError("nuclear_charges must be an AtomicProperty")
    if (
        nuclear_charges.structure_id != structure.id
        or nuclear_charges.semantic_role != "nuclear_charge"
        or nuclear_charges.domain != "atom"
        or nuclear_charges.data.dims != ("atom",)
        or nuclear_charges.data.shape != (len(structure.atomic_numbers),)
        or nuclear_charges.data.unit != "elementary_charge"
    ):
        raise ValueError("nuclear_charges does not match the structure")
    charge_values = numpy.asarray(nuclear_charges.data.values)
    if (
        numpy.iscomplexobj(charge_values)
        or not numpy.all(numpy.isfinite(charge_values))
        or numpy.any(charge_values < 0.0)
    ):
        raise ValueError("nuclear_charges must contain finite non-negative values")
    if (
        isinstance(nuclear_exclusion_radius, bool)
        or not isinstance(nuclear_exclusion_radius, (int, float))
        or not isfinite(nuclear_exclusion_radius)
        or nuclear_exclusion_radius < 0.0
    ):
        raise ValueError(
            "nuclear_exclusion_radius must be a finite non-negative number"
        )
    coordinates = numpy.asarray(structure.coordinates.values, dtype=float)

    def evaluate(points):
        for coordinate in coordinates:
            _check_cancel(cancel_check)
            if numpy.any(numpy.linalg.norm(points - coordinate, axis=1)
                         <= nuclear_exclusion_radius):
                raise ValueError(
                    "ESP grid contains a point inside the nuclear exclusion radius"
                )
        return _evaluate_esp(
            structure, basis_set, density_matrix, charge_values, points,
        )

    origin, step_vectors, shape, values = _evaluate_grid(
        origin, step_vectors, shape, evaluate,
        basis_count=basis_set.basis_function_count, operation="esp",
        chunk_size=chunk_size, cancel_check=cancel_check, progress=progress,
    )
    return _batch(
        (structure, basis_set, density_matrix, nuclear_charges),
        density_matrix,
        semantic_role="electrostatic_potential",
        unit="hartree_per_elementary_charge",
        values=values,
        origin=origin,
        step_vectors=step_vectors,
        shape=shape,
        parameters={
            "density_level": density_matrix.level.value,
            "nuclear_exclusion_radius": float(nuclear_exclusion_radius),
        },
    )
