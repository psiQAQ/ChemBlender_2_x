from ChemBlender.core import BasisSet, OrbitalSet, Structure

from .protocol import EntityReference, ProtocolError
from .operation import OperationOutput


_GRID_FIELDS = {"origin", "step_vectors", "shape"}


def _entities(context, request):
    if len(request.inputs) != 3:
        raise ProtocolError(
            "wavefunction operations require structure, basis set and orbital set inputs"
        )
    structure_ref, basis_ref, orbital_ref = request.inputs
    try:
        structure = context.project.structures[structure_ref.entity_id]
        basis = context.project.basis_sets[basis_ref.entity_id]
        orbitals = context.project.orbital_sets[orbital_ref.entity_id]
    except KeyError as error:
        raise ProtocolError("wavefunction operation input type/order is invalid") from error
    if not isinstance(structure, Structure) or not isinstance(basis, BasisSet) or not isinstance(
        orbitals, OrbitalSet
    ):
        raise ProtocolError("wavefunction operation input type/order is invalid")
    return structure, basis, orbitals


def _output(batch):
    groups = (
        batch.structures,
        batch.cif_envelopes,
        batch.symmetry_results,
        batch.calculations,
        batch.datasets,
        batch.basis_sets,
        batch.orbital_sets,
        batch.density_matrices,
        batch.provenance,
    )
    references = tuple(
        EntityReference(entity.id, entity.revision)
        for group in groups
        for entity in group
    )
    dataset = batch.datasets[0]
    return OperationOutput(
        outputs=references,
        cache_key=dataset.revision,
        metadata={"dataset_id": str(dataset.id)},
        batch=batch,
    )


def _mo_grid(context, request):
    from ChemBlender.core import evaluate_molecular_orbital_grid

    required = _GRID_FIELDS | {"channel", "orbital_index"}
    if set(request.parameters) != required:
        raise ProtocolError(f"molecular-orbital parameters must be {sorted(required)}")
    structure, basis, orbitals = _entities(context, request)
    batch = evaluate_molecular_orbital_grid(
        structure,
        basis,
        orbitals,
        channel=request.parameters["channel"],
        orbital_index=request.parameters["orbital_index"],
        origin=request.parameters["origin"],
        step_vectors=request.parameters["step_vectors"],
        shape=request.parameters["shape"],
    )
    return _output(batch)


def _electron_density_grid(context, request):
    from ChemBlender.core import evaluate_electron_density_grid

    if set(request.parameters) != _GRID_FIELDS:
        raise ProtocolError(
            f"electron-density parameters must be {sorted(_GRID_FIELDS)}"
        )
    structure, basis, orbitals = _entities(context, request)
    batch = evaluate_electron_density_grid(
        structure,
        basis,
        orbitals,
        origin=request.parameters["origin"],
        step_vectors=request.parameters["step_vectors"],
        shape=request.parameters["shape"],
    )
    return _output(batch)


def register_wavefunction_operations(registry):
    registry.register("wavefunction.mo_grid", "1", _mo_grid)
    registry.register(
        "wavefunction.electron_density_grid", "1", _electron_density_grid
    )
