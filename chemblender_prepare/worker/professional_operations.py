"""QTAIM, phonon, and NCI operations over frozen scientific inputs."""

from concurrent.futures import CancelledError
from dataclasses import replace
import hashlib
from pathlib import Path
from uuid import uuid4

from cbq_core.grid_semantics import validate_nci_pair
from cbq_core.model import ArrayData, DatasetStatus, Grid3D, ImportBatch, ProvenanceRecord, Structure
from chemblender_prepare.core.cube import parse_cube
from chemblender_prepare.core.phonopy_adapter import parse_phonopy_file
from chemblender_prepare.reader_api.worker_bridge import _task_file
from chemblender_prepare.runtime import _probe_critic2, critic2_command, load_configuration
from chemblender_prepare.topology_service import load_topology_batch
from chemblender_prepare.worker.external_program import (
    CRITIC2_ADAPTER, ExternalInvocation, ExternalRunStatus,
    external_run_metadata, run_external_program,
)
from chemblender_prepare.worker.operation import OperationError, OperationOutput
from chemblender_prepare.worker.protocol import EntityReference, ProtocolError


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifacts(context, request, names, optional=()):
    allowed = {"source_artifacts", *optional}
    if not isinstance(request.parameters, dict) or set(request.parameters) - allowed:
        raise ProtocolError(f"{request.operation_id} parameters are invalid")
    documents = request.parameters.get("source_artifacts")
    if not isinstance(documents, dict) or set(documents) != set(names):
        raise ProtocolError(f"{request.operation_id} requires artifacts {sorted(names)}")
    result = {}
    for name, document in documents.items():
        if (not isinstance(document, dict) or set(document) != {"path", "sha256"}
                or not isinstance(document["sha256"], str)
                or len(document["sha256"]) != 64
                or any(character not in "0123456789abcdef" for character in document["sha256"])):
            raise ProtocolError("scientific artifacts require path and SHA-256")
        path = _task_file(context.task_directory, document["path"])
        if _sha256(path) != document["sha256"]:
            raise OperationError("scientific_source_invalid", f"{name} artifact hash mismatch")
        result[name] = path
    return result


def _critic2_run(context, script, expected):
    if context.task_directory is None:
        raise ProtocolError("critic2 operation requires a task directory")
    configuration = load_configuration()
    probe = _probe_critic2(configuration["critic2"])
    if not probe["available"]:
        raise OperationError("critic2_unavailable", probe["error"] or "critic2 is unavailable")
    script_path = context.task_directory / "analysis.cri"
    script_path.write_text(script, encoding="utf-8", newline="\n")
    command = critic2_command(
        configuration["critic2"], ("-q", "-t", "-l", "analysis.cri", "analysis.cro"),
        cwd=context.task_directory,
    )
    record = run_external_program(ExternalInvocation(
        "critic2", CRITIC2_ADAPTER.adapter_version, command[0], tuple(command[1:]),
        tuple(expected), 300.0, probe["version"], input_artifacts=("analysis.cri",),
    ), context.task_directory, cancel_path=context.cancel_path)
    if record.status is ExternalRunStatus.CANCELLED:
        raise CancelledError("critic2 calculation cancelled")
    if record.status is not ExternalRunStatus.SUCCESS:
        raise OperationError("critic2_failed", f"critic2 failed: {record.error_code}")
    return record


def _qtaim(context, request):
    if len(request.inputs) != 1:
        raise ProtocolError("topology.qtaim requires one Structure input")
    structure = context.project.structures.get(request.inputs[0].entity_id)
    if not isinstance(structure, Structure):
        raise ProtocolError("topology.qtaim input must be a Structure")
    source = _artifacts(context, request, ("wavefunction",))["wavefunction"]
    relative = source.relative_to(context.task_directory).as_posix()
    record = _critic2_run(context, "\n".join((
        f"molecule {relative}", f"load {relative}", "auto",
        "cpreport qtaim.json", "fluxprint", " graph 2", " text", "end", "",
    )), ("qtaim.json", "analysis_flux.txt"))
    batch = load_topology_batch(
        context.task_directory / "qtaim.json", structure=structure,
        field_kind="ELECTRON_DENSITY_AU",
        fluxprint_path=context.task_directory / "analysis_flux.txt",
        endpoint_tolerance_bohr=.25,
        temp_parent=context.task_directory, is_cancelled=context.is_cancelled,
    )
    run_id = uuid4()
    run = ProvenanceRecord(
        run_id, _sha256(context.task_directory / "qtaim.json"), "critic2",
        record.program_version, str(source), _sha256(source), (), "qtaim",
        (("external_run", external_run_metadata(record)),
         ("source_artifacts", request.parameters["source_artifacts"])),
    )
    graphs = tuple(replace(value, provenance_ids=(*value.provenance_ids, run_id))
                   for value in batch.datasets)
    provenance = (*batch.provenance, run)
    batch = replace(
        batch, datasets=graphs, provenance=provenance,
        report=replace(batch.report, created_entity_ids=tuple(
            value.id for value in (*graphs, *provenance)
        )),
    )
    outputs = tuple(EntityReference(value.id, value.revision)
                    for value in (*graphs, *batch.provenance))
    return OperationOutput(outputs, cache_key=graphs[-1].revision, batch=batch, metadata={
        "operation": "topology.qtaim@1", "topology_id": str(graphs[-1].id),
        "critic2_version": record.program_version,
    })


def _same_structure(left, right):
    import numpy
    return (left.atomic_numbers == right.atomic_numbers
            and left.coordinates.unit == right.coordinates.unit
            and numpy.array_equal(left.coordinates.values, right.coordinates.values))


def _nci(context, request):
    if request.inputs:
        raise ProtocolError("grid.nci_fields accepts frozen WFX input only")
    source = _artifacts(context, request, ("wavefunction",), ("grid_points",))["wavefunction"]
    relative = source.relative_to(context.task_directory).as_posix()
    points = request.parameters.get("grid_points", (40, 40, 40))
    if (not isinstance(points, (list, tuple)) or len(points) != 3
            or any(type(value) is not int or not 8 <= value <= 256 for value in points)):
        raise ProtocolError("grid_points must contain three integers from 8 to 256")
    record = _critic2_run(context, "\n".join((
        f"molecule {relative}", f"load {relative}", "nciplot", " oname nci",
        " nochk", f" nstep {points[0]} {points[1]} {points[2]}", "end", "",
    )), ("nci-grad.cube", "nci-dens.cube"))
    rdg_batch = parse_cube(context.task_directory / "nci-grad.cube")
    signed_batch = parse_cube(context.task_directory / "nci-dens.cube")
    structure = rdg_batch.structures[0]
    if not _same_structure(structure, signed_batch.structures[0]):
        raise OperationError("critic2_output_invalid", "NCI Cubes contain different structures")
    run_id = uuid4()
    run_hash = hashlib.sha256(
        (_sha256(source) + _sha256(context.task_directory / "nci-grad.cube")
         + _sha256(context.task_directory / "nci-dens.cube")).encode("ascii")
    ).hexdigest()
    run = ProvenanceRecord(
        run_id, run_hash, "critic2", record.program_version, str(source), _sha256(source),
        (), "nci_fields", (("external_run", external_run_metadata(record)),
                           ("grid_points", tuple(points)),
                           ("source_artifacts", request.parameters["source_artifacts"])),
    )
    grids = []
    provenances = [run]
    for parsed, role, unit in (
        (rdg_batch, "reduced_density_gradient", "dimensionless"),
        (signed_batch, "sign_lambda2_rho", "electron_per_cubic_bohr"),
    ):
        provenance = replace(parsed.provenance[0], parent_ids=(run_id,))
        provenances.append(provenance)
        base = parsed.datasets[0]
        grids.append(replace(
            base, semantic_role=role,
            data=ArrayData(base.data.values, base.data.dims, unit),
            status=DatasetStatus.COMPLETE, structure_id=structure.id,
            provenance_ids=(run_id, provenance.id),
        ))
    rdg, signed = grids
    validate_nci_pair(rdg, signed)
    batch = ImportBatch(structures=(structure,), datasets=(rdg, signed),
                        provenance=tuple(provenances))
    values = (structure, rdg, signed, *provenances)
    outputs = tuple(EntityReference(value.id, value.revision) for value in values)
    return OperationOutput(outputs, cache_key=run_hash, batch=batch, metadata={
        "operation": "grid.nci_fields@1", "structure_id": str(structure.id),
        "rdg_id": str(rdg.id), "signed_density_id": str(signed.id),
        "critic2_version": record.program_version,
    })


def _phonon(context, request):
    if request.inputs:
        raise ProtocolError("periodic.phonon accepts frozen phonopy inputs only")
    artifacts = _artifacts(
        context, request,
        tuple(request.parameters.get("source_artifacts", {})),
        ("qpoints", "nac_q_direction", "with_group_velocities"),
    )
    if set(artifacts) not in ({"displacement_yaml", "force_sets"},
                              {"displacement_yaml", "force_sets", "born"}):
        raise ProtocolError("periodic.phonon requires displacement_yaml/FORCE_SETS and optional BORN")
    batch = parse_phonopy_file(
        artifacts["displacement_yaml"], force_sets_filename=artifacts["force_sets"],
        born_filename=artifacts.get("born"),
        qpoints=request.parameters.get("qpoints", ((0.0, 0.0, 0.0),)),
        nac_q_direction=request.parameters.get("nac_q_direction"),
        with_group_velocities=request.parameters.get("with_group_velocities", False),
        cancel_check=context.is_cancelled,
    )
    provenance = tuple(replace(
        value,
        parameters=(*value.parameters,
                    ("source_artifacts", request.parameters["source_artifacts"])),
    ) for value in batch.provenance)
    batch = replace(batch, provenance=provenance)
    structure, modes = batch.structures[0], batch.datasets[0]
    values = (structure, modes, *provenance)
    return OperationOutput(
        tuple(EntityReference(value.id, value.revision) for value in values),
        cache_key=modes.revision, batch=batch, metadata={
            "operation": "periodic.phonon@1", "structure_id": str(structure.id),
            "phonon_mode_id": str(modes.id),
        },
    )


def register_professional_operations(registry):
    registry.register("topology.qtaim", "1", _qtaim)
    registry.register("periodic.phonon", "1", _phonon)
    registry.register("grid.nci_fields", "1", _nci)
