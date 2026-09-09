from time import monotonic

from cbq_core.model import AtomicProperty
from cbq_core.model import BasisSet
from cbq_core.model import DensityMatrix
from cbq_core.model import DensityMatrixLevel
from cbq_core.model import ImportBatch
from cbq_core.model import OrbitalSet
from cbq_core.model import Structure

from chemblender_prepare.worker.protocol import EntityReference
from chemblender_prepare.worker.protocol import ProtocolError
from chemblender_prepare.worker.operation import OperationOutput
from cbq_core.worker_protocol import _atomic_document


_GRID_FIELDS = {"origin", "step_vectors", "shape"}


def _progress(context):
    if context.task_directory is None:
        return None
    last_write = 0.0

    def report(completed, total):
        nonlocal last_write
        now = monotonic()
        if 0 < completed < total and now - last_write < 0.1:
            return
        try:
            _atomic_document(
                context.task_directory / "progress.json",
                {"completed": int(completed), "total": int(total)},
            )
        except PermissionError:
            # Windows readers can briefly deny replacement. Progress is optional;
            # leave last_write unchanged so a later block can retry the update.
            return
        last_write = now

    return report


def _entities(context, request, *, density_matrix=False, nuclear_charge=False):
    if len(request.inputs) != (4 if nuclear_charge else 3):
        raise ProtocolError(
            "wavefunction operation input count is invalid"
        )
    structure_ref, basis_ref, wavefunction_ref = request.inputs[:3]
    try:
        structure = context.project.structures[structure_ref.entity_id]
        basis = context.project.basis_sets[basis_ref.entity_id]
        registry = (context.project.density_matrices if density_matrix
                    else context.project.orbital_sets)
        wavefunction = registry[wavefunction_ref.entity_id]
        charges = (context.project.datasets[request.inputs[3].entity_id]
                   if nuclear_charge else None)
    except KeyError as error:
        raise ProtocolError("wavefunction operation input type/order is invalid") from error
    if not isinstance(structure, Structure) or not isinstance(basis, BasisSet) or not isinstance(
        wavefunction, DensityMatrix if density_matrix else OrbitalSet
    ):
        raise ProtocolError("wavefunction operation input type/order is invalid")
    if nuclear_charge and not isinstance(charges, AtomicProperty):
        raise ProtocolError("ESP requires a nuclear-charge AtomicProperty input")
    values = (structure, basis, wavefunction)
    return (*values, charges) if nuclear_charge else values


def _parameters(request, required, optional=()):
    fields = set(request.parameters)
    if not required <= fields or fields - required - set(optional) - {"chunk_size"}:
        raise ProtocolError(
            f"{request.operation_id} requires parameters {sorted(required)}"
        )
    return dict(request.parameters)


def _output(batch):
    groups = (
        batch.structures,
        batch.topologies,
        batch.molecular_records,
        batch.biological_hierarchies,
        batch.annotations,
        batch.external_references,
        batch.cif_envelopes,
        batch.qcschema_envelopes,
        batch.cjson_envelopes,
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
    metadata = {"dataset_id": str(dataset.id)}
    if batch.density_matrices:
        metadata["derived_density_matrix_id"] = str(batch.density_matrices[0].id)
    return OperationOutput(
        outputs=references,
        cache_key=dataset.revision,
        metadata=metadata,
        batch=batch,
    )


def _mo_grid(context, request):
    from chemblender_prepare.core.wavefunction_grid import evaluate_molecular_orbital_grid

    required = _GRID_FIELDS | {"channel", "orbital_index"}
    parameters = _parameters(request, required)
    structure, basis, orbitals = _entities(context, request)
    batch = evaluate_molecular_orbital_grid(
        structure,
        basis,
        orbitals,
        cancel_check=context.is_cancelled,
        progress=_progress(context),
        **parameters,
    )
    return _output(batch)


def _electron_density_grid(context, request):
    from chemblender_prepare.core.wavefunction_grid import evaluate_electron_density_grid

    parameters = _parameters(request, _GRID_FIELDS)
    structure, basis, orbitals = _entities(context, request)
    batch = evaluate_electron_density_grid(
        structure,
        basis,
        orbitals,
        source_provenance=context.project.provenance.values(),
        cancel_check=context.is_cancelled,
        progress=_progress(context),
        **parameters,
    )
    return _output(batch)


def _density_matrix_grid(context, request):
    from chemblender_prepare.core.wavefunction_observables import evaluate_density_matrix_grid

    parameters = _parameters(request, _GRID_FIELDS)
    entities = _entities(context, request, density_matrix=True)
    return _output(evaluate_density_matrix_grid(
        *entities, cancel_check=context.is_cancelled,
        progress=_progress(context), **parameters,
    ))


def _esp_grid(context, request):
    from chemblender_prepare.core.wavefunction_observables import evaluate_electrostatic_potential_grid

    parameters = _parameters(request, _GRID_FIELDS, {"nuclear_exclusion_radius"})
    entities = _entities(context, request, density_matrix=True, nuclear_charge=True)
    return _output(evaluate_electrostatic_potential_grid(
        *entities, cancel_check=context.is_cancelled,
        progress=_progress(context), **parameters,
    ))


def _esp_from_orbitals_grid(context, request):
    from chemblender_prepare.core.wavefunction_observables import derive_density_matrix_from_orbitals
    from chemblender_prepare.core.wavefunction_observables import evaluate_electrostatic_potential_grid

    parameters = _parameters(request, _GRID_FIELDS | {"density_level"},
                             {"nuclear_exclusion_radius"})
    try:
        level = DensityMatrixLevel(parameters.pop("density_level"))
    except (TypeError, ValueError) as error:
        raise ProtocolError("density_level must explicitly be scf or post_scf") from error
    structure, basis, orbitals, charges = _entities(context, request, nuclear_charge=True)
    density = derive_density_matrix_from_orbitals(
        structure, basis, orbitals, level=level,
        source_provenance=context.project.provenance.values(),
        cancel_check=context.is_cancelled,
    )
    grid = evaluate_electrostatic_potential_grid(
        structure, basis, density.density_matrices[0], charges,
        cancel_check=context.is_cancelled, progress=_progress(context), **parameters,
    )
    return _output(ImportBatch(
        datasets=grid.datasets, density_matrices=density.density_matrices,
        provenance=(*density.provenance, *grid.provenance),
    ))


def register_wavefunction_operations(registry):
    registry.register("wavefunction.mo_grid", "1", _mo_grid)
    registry.register(
        "wavefunction.electron_density_grid", "1", _electron_density_grid
    )
    registry.register("wavefunction.density_matrix_grid", "1", _density_matrix_grid)
    registry.register("wavefunction.esp_grid", "1", _esp_grid)
    registry.register("wavefunction.esp_from_orbitals_grid", "1", _esp_from_orbitals_grid)
