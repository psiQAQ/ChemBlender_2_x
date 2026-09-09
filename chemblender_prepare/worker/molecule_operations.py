"""RDKit-backed molecular operations exposed through Worker Protocol v1."""

import hashlib
import json
from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from cbq_core.model import ArrayData
from cbq_core.model import CalculationRecord
from cbq_core.model import CalculationStatus
from cbq_core.model import DatasetStatus
from cbq_core.model import ImportBatch
from cbq_core.model import MolecularRecord
from cbq_core.model import PropertyDataset
from cbq_core.model import ProvenanceRecord
from cbq_core.model import QualityStatus
from cbq_core.model import Structure
from cbq_core.model import TopologyRecord
from cbq_core.model import TopologySource

from .operation import OperationError
from .operation import OperationOutput
from .protocol import EntityReference
from .protocol import ProtocolError


_VERSION = "1"


def _parameters(request, allowed, defaults=()):
    values = dict(defaults)
    supplied = dict(request.parameters)
    if set(supplied) - set(allowed):
        raise ProtocolError(
            f"{request.operation_id} accepts only parameters {sorted(allowed)}"
        )
    values.update(supplied)
    return values


def _inputs(context, request, *, record=False, optional_record=False):
    expected = 3 if record else 2
    if len(request.inputs) not in ({2, 3} if optional_record else {expected}):
        raise ProtocolError(f"{request.operation_id} input count is invalid")
    try:
        structure = context.project.structures[request.inputs[0].entity_id]
        topology = context.project.topologies[request.inputs[1].entity_id]
        molecular_record = (
            context.project.molecular_records[request.inputs[2].entity_id]
            if len(request.inputs) == 3 else None
        )
    except KeyError as error:
        raise ProtocolError("molecular input type/order is invalid") from error
    if not isinstance(structure, Structure) or not isinstance(topology, TopologyRecord):
        raise ProtocolError("molecular input type/order is invalid")
    if topology.structure_id != structure.id or topology.id not in structure.topology_ids:
        raise ProtocolError("topology is not bound to the selected structure")
    if molecular_record is not None and (
        not isinstance(molecular_record, MolecularRecord)
        or molecular_record.structure_id != structure.id
        or molecular_record.topology_id not in {None, topology.id}
    ):
        raise ProtocolError("molecular record is not bound to the selected structure")
    return structure, topology, molecular_record


def _cache_key(request, *, rdkit_version):
    document = {
        "inputs": [
            {"id": str(item.entity_id), "revision": item.revision}
            for item in request.inputs
        ],
        "operation": f"{request.operation_id}@{request.operation_version}",
        "parameters": request.parameters,
        "rdkit_version": rdkit_version,
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"),
                   allow_nan=False).encode("utf-8")
    ).hexdigest()


def _identity(request, kind):
    return uuid5(request.request_id, f"chemblender:{request.operation_id}:{kind}")


def _provenance(request, cache_key, parents, parameters, rdkit_version):
    return ProvenanceRecord(
        id=_identity(request, "provenance"),
        revision=cache_key,
        producer="chemblender-prepare",
        producer_version=_VERSION,
        source="",
        source_hash=cache_key,
        parent_ids=tuple(parents),
        operation=request.operation_id,
        parameters=tuple(sorted((*parameters.items(),
                                 ("rdkit_version", rdkit_version)))),
    )


def _references(batch):
    groups = (
        batch.structures, batch.topologies, batch.molecular_records,
        batch.biological_hierarchies, batch.annotations,
        batch.external_references, batch.cif_envelopes,
        batch.qcschema_envelopes, batch.cjson_envelopes,
        batch.symmetry_results, batch.calculations, batch.datasets,
        batch.basis_sets, batch.orbital_sets, batch.density_matrices,
        batch.provenance,
    )
    return tuple(
        EntityReference(entity.id, entity.revision)
        for group in groups for entity in group
    )


def _output(batch, cache_key, metadata, *, artifacts=()):
    return OperationOutput(
        outputs=_references(batch), artifacts=tuple(artifacts),
        cache_key=cache_key, metadata=metadata, batch=batch,
    )


def _rdkit_molecule(structure, topology, record=None):
    from chemblender_prepare.core.exporters.rdkit_molecular import _molecule

    return _molecule(structure, topology, record=record)


def _force_field(molecule, name):
    from rdkit.Chem import AllChem

    if name == "MMFF94":
        properties = AllChem.MMFFGetMoleculeProperties(
            molecule, mmffVariant="MMFF94"
        )
        field = None if properties is None else AllChem.MMFFGetMoleculeForceField(
            molecule, properties
        )
    elif name == "UFF":
        field = AllChem.UFFGetMoleculeForceField(molecule)
    else:
        raise ProtocolError("force_field must be MMFF94 or UFF")
    if field is None:
        raise OperationError(
            "molecule_force_field_unavailable",
            f"{name} parameters are unavailable for the selected molecule",
        )
    return field


def _derived_batch(context, request, molecule, parameters, status):
    from rdkit import Chem, rdBase
    from chemblender_prepare.core.formats.rdkit_common import RDKitMoleculeContext
    from chemblender_prepare.core.formats.rdkit_common import adapt_rdkit_molecule

    structure, topology, _record = _inputs(context, request, optional_record=True)
    cache_key = _cache_key(request, rdkit_version=rdBase.rdkitVersion)
    provenance = _provenance(
        request, cache_key, (structure.id, topology.id), parameters,
        rdBase.rdkitVersion,
    )
    adapted = adapt_rdkit_molecule(
        molecule, cache_key.encode("ascii"),
        RDKitMoleculeContext(
            source_revision_id=structure.id, source_hash=cache_key,
            record_key="derived", source_record_index=0,
            title=request.operation_id, block_version=None,
            writer_name="RDKit", writer_version=rdBase.rdkitVersion,
        ),
        is_cancelled=context.is_cancelled,
    )
    if adapted.structure is None or not adapted.topologies:
        raise OperationError(
            "molecule_result_invalid", "RDKit did not produce a finite conformer"
        )
    structure_id = _identity(request, "structure")
    topology_id = _identity(request, "topology")
    derived_topology = replace(
        adapted.topologies[0], id=topology_id, revision=cache_key,
        structure_id=structure_id, source_kind=TopologySource.RDKIT_SANITIZED,
        quality_status=QualityStatus.COMPLETE,
        inference_parameters=(), provenance_ids=(provenance.id,),
    )
    derived_structure = replace(
        adapted.structure, id=structure_id, revision=cache_key,
        topology_ids=(topology_id,), molecular_charge=Chem.GetFormalCharge(molecule),
        molecular_multiplicity=structure.molecular_multiplicity,
    )
    calculation = CalculationRecord(
        id=_identity(request, "calculation"), revision=cache_key,
        status=status, input_structure_ids=(structure.id,),
        result_structure_ids=(structure_id,), dataset_ids=(),
        provenance_ids=(provenance.id,),
    )
    batch = ImportBatch(
        structures=(derived_structure,), topologies=(derived_topology,),
        calculations=(calculation,), provenance=(provenance,),
    )
    return _output(batch, cache_key, {
        "operation": f"{request.operation_id}@1",
        "structure_id": str(structure_id),
        "topology_id": str(topology_id),
        "calculation_id": str(calculation.id),
        "status": status.value,
    })


def smiles_to_3d(context, request):
    from rdkit import rdBase
    from chemblender_prepare.core.derivations.smiles_3d import Smiles3DCancelled
    from chemblender_prepare.core.derivations.smiles_3d import derive_smiles_3d

    structure, topology, record = _inputs(context, request, record=True)
    try:
        source_revision = context.project.source_revisions[record.source_revision_id]
    except KeyError as error:
        raise ProtocolError("SMILES source revision is missing") from error
    parameters = _parameters(request, {
        "add_hydrogens", "force_field", "random_seed", "num_threads",
        "max_iterations",
    }, (
        ("add_hydrogens", True), ("force_field", "MMFF94"),
        ("random_seed", 0xC0FFEE), ("num_threads", 1),
        ("max_iterations", 200),
    ))
    try:
        batch = derive_smiles_3d(
            structure, topology, record, source_revision,
            is_cancelled=context.is_cancelled, **parameters,
        )
    except Smiles3DCancelled as error:
        raise CancelledError(str(error)) from error
    cache_key = batch.provenance[0].revision
    primary = batch.structures[0].id if batch.structures else batch.calculations[0].id
    return _output(batch, cache_key, {
        "operation": "molecule.smiles_to_3d@1",
        "primary_id": str(primary),
        "status": batch.calculations[0].status.value,
        "rdkit_version": rdBase.rdkitVersion,
    })


def kekulize(context, request):
    from rdkit import Chem

    structure, topology, _record = _inputs(context, request)
    _parameters(request, set())
    molecule = _rdkit_molecule(structure, topology)
    if context.is_cancelled():
        raise CancelledError("molecule kekulization cancelled")
    try:
        Chem.Kekulize(molecule, clearAromaticFlags=True)
    except (ValueError, RuntimeError) as error:
        raise OperationError(
            "molecule_kekulize_failed", "selected topology cannot be kekulized"
        ) from error
    return _derived_batch(
        context, request, molecule, {}, CalculationStatus.SUCCESS
    )


def optimize(context, request):
    from rdkit import Chem

    structure, topology, _record = _inputs(context, request)
    parameters = _parameters(request, {
        "force_field", "add_hydrogens", "max_iterations",
    }, (("force_field", "MMFF94"), ("add_hydrogens", False),
        ("max_iterations", 200)))
    if type(parameters["add_hydrogens"]) is not bool:
        raise ProtocolError("add_hydrogens must be bool")
    maximum = parameters["max_iterations"]
    if type(maximum) is not int or not 0 < maximum <= 2_147_483_647:
        raise ProtocolError("max_iterations must be a positive signed 32-bit integer")
    molecule = _rdkit_molecule(structure, topology)
    if parameters["add_hydrogens"]:
        molecule = Chem.AddHs(molecule, addCoords=True)
    field = _force_field(molecule, parameters["force_field"])
    status = 1
    completed = 0
    while completed < maximum and status:
        if context.is_cancelled():
            raise CancelledError("molecule optimization cancelled")
        step = min(10, maximum - completed)
        status = field.Minimize(maxIts=step)
        completed += step
    parameters["iterations_attempted"] = completed
    parameters["optimizer_status"] = int(status)
    return _derived_batch(
        context, request, molecule, parameters,
        CalculationStatus.SUCCESS if status == 0 else CalculationStatus.INCOMPLETE,
    )


def energy(context, request):
    import numpy
    from rdkit import rdBase

    structure, topology, _record = _inputs(context, request)
    parameters = _parameters(
        request, {"force_field"}, (("force_field", "MMFF94"),)
    )
    molecule = _rdkit_molecule(structure, topology)
    if context.is_cancelled():
        raise CancelledError("molecule energy calculation cancelled")
    value = float(_force_field(molecule, parameters["force_field"]).CalcEnergy())
    if not numpy.isfinite(value):
        raise OperationError(
            "molecule_energy_invalid", "force field returned non-finite energy"
        )
    cache_key = _cache_key(request, rdkit_version=rdBase.rdkitVersion)
    provenance = _provenance(
        request, cache_key, (structure.id, topology.id), parameters,
        rdBase.rdkitVersion,
    )
    calculation_id = _identity(request, "calculation")
    dataset = PropertyDataset(
        id=_identity(request, "dataset"), revision=cache_key,
        semantic_role="potential_energy", domain="structure",
        data=ArrayData(numpy.asarray(value), (), "kilocalorie_per_mole"),
        status=DatasetStatus.COMPLETE, source_calculation=calculation_id,
        provenance_ids=(provenance.id,),
    )
    calculation = CalculationRecord(
        id=calculation_id, revision=cache_key,
        status=CalculationStatus.SUCCESS,
        input_structure_ids=(structure.id,), result_structure_ids=(),
        dataset_ids=(dataset.id,), provenance_ids=(provenance.id,),
    )
    batch = ImportBatch(
        calculations=(calculation,), datasets=(dataset,),
        provenance=(provenance,),
    )
    return _output(batch, cache_key, {
        "operation": "molecule.energy@1", "dataset_id": str(dataset.id),
        "calculation_id": str(calculation.id), "value": value,
        "unit": dataset.data.unit,
    })


def export(context, request):
    from rdkit import rdBase
    from chemblender_prepare.core.exporters.rdkit_molecular import export_mol
    from chemblender_prepare.core.exporters.rdkit_molecular import export_sdf
    from chemblender_prepare.core.exporters.rdkit_molecular import export_smiles

    structure, topology, record = _inputs(
        context, request, optional_record=True
    )
    parameters = _parameters(
        request, {"format", "confirm_loss", "isomeric"},
        (("confirm_loss", False), ("isomeric", True)),
    )
    format_name = parameters.get("format")
    if format_name not in {"mol", "sdf", "smiles"}:
        raise ProtocolError("format must be mol, sdf or smiles")
    if type(parameters["confirm_loss"]) is not bool or type(parameters["isomeric"]) is not bool:
        raise ProtocolError("confirm_loss and isomeric must be bool")
    cache_key = _cache_key(request, rdkit_version=rdBase.rdkitVersion)
    root = context.project_path.resolve()
    export_root = root / "exports"
    if export_root.exists() and (
        export_root.is_symlink() or export_root.is_junction()
        or not export_root.is_dir()
    ):
        raise OperationError(
            "molecule_export_path_invalid", "CBQ export path is not a regular directory"
        )
    export_root.mkdir(exist_ok=True)
    destination = export_root / f"molecule-{request.request_id}.{format_name}"
    options = {
        "record": record, "confirm_loss": parameters["confirm_loss"],
        "destination": destination, "is_cancelled": context.is_cancelled,
    }
    if format_name == "mol":
        result = export_mol(structure, topology, **options)
    elif format_name == "sdf":
        result = export_sdf(structure, topology, **options)
    else:
        result = export_smiles(
            structure, topology, isomeric=parameters["isomeric"], **options
        )
    if result.report.requires_confirmation and not result.report.written:
        raise OperationError(
            "molecule_export_confirmation_required",
            "molecular export requires explicit loss confirmation",
        )
    relative = destination.relative_to(root).as_posix()
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    provenance = _provenance(
        request, cache_key, (structure.id, topology.id), parameters,
        rdBase.rdkitVersion,
    )
    batch = ImportBatch(provenance=(provenance,))
    return _output(batch, cache_key, {
        "operation": "molecule.export@1", "format": format_name,
        "artifact": relative, "artifact_sha256": digest,
        "requires_confirmation": result.report.requires_confirmation,
    }, artifacts=(relative,))


def register_molecule_operations(registry):
    registry.register("molecule.smiles_to_3d", "1", smiles_to_3d)
    registry.register("molecule.kekulize", "1", kekulize)
    registry.register("molecule.optimize", "1", optimize)
    registry.register("molecule.energy", "1", energy)
    registry.register("molecule.export", "1", export)


__all__ = ("register_molecule_operations",)
