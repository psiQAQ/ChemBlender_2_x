"""Stage, validate, and publish external operations through one processor."""

from dataclasses import dataclass, fields, replace
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import time
from uuid import UUID, uuid4

from cbq_core.model import (
    AtomicProperty, BandStructure, DensityMatrix, DensityMatrixSpin,
    FermiSurfaceMesh, Grid3D, PhononModeSet, PropertyDataset, QCProject,
    Structure, TopologyGraph,
)
from cbq_core.grid_semantics import validate_nci_pair
from cbq_core.package_import import import_package
from cbq_core.sidecar import close_project, open_project, save_project
from cbq_core.worker_protocol import EntityReference, WorkerRequest, WORKER_VERSION

from .processor import (
    ProcessorError, ProcessorState, create_task_directory, start_worker,
)


_FERMI_REQUIRED = frozenset({"INCAR", "KPOINTS", "POSCAR", "OUTCAR", "PROCAR"})
_FERMI_OPTIONAL = frozenset({"IBZKPT"})
_READER_ID = re.compile(r"[a-z][a-z0-9_.-]*", re.ASCII)
_WAVEFUNCTION_OPERATIONS = {
    "wavefunction.mo_grid": ("molecular_orbital", "inverse_bohr_to_three_halves"),
    "wavefunction.electron_density_grid": ("electron_density", "electron_per_cubic_bohr"),
    "wavefunction.density_matrix_grid": (None, "electron_per_cubic_bohr"),
    "wavefunction.esp_grid": ("electrostatic_potential", "hartree_per_elementary_charge"),
    "wavefunction.esp_from_orbitals_grid": ("electrostatic_potential", "hartree_per_elementary_charge"),
}
_MOLECULE_OPERATIONS = {
    "molecule.smiles_to_3d", "molecule.kekulize", "molecule.optimize",
    "molecule.energy", "molecule.export",
}
_PROFESSIONAL_OPERATIONS = {
    "topology.qtaim", "periodic.phonon", "grid.nci_fields",
}
_SCENE_PROPERTY_NAME = "chemblender_processor_operation"
_OWNED_SCENE_PROPERTY = None
_ACTIVE_OPERATIONS = {}
_OPERATION_TERMINAL_STATES = {
    ProcessorState.CANCELLED, ProcessorState.FAILED, ProcessorState.SUCCEEDED,
}


def _entity_map(project):
    return {
        identity: entity
        for field in fields(project)
        if isinstance(registry := getattr(project, field.name), dict)
        for identity, entity in registry.items()
    }


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_file(path):
    path = Path(path).expanduser().resolve(strict=True)
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise ProcessorError(f"processor input must be a regular file: {path}")
    return path


def _copy_input(source, destination):
    source = _source_file(source)
    before = _sha256(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer, 1024 * 1024)
    if _sha256(source) != before or _sha256(destination) != before:
        raise ProcessorError("processor input changed while it was copied")
    return source, before


def _safe_artifact(task_directory, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ProcessorError("processor artifact path is invalid")
    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if posix.is_absolute() or windows.drive or any(
        part in {"", ".", ".."} or ":" in part or part.endswith((".", " "))
        for part in relative.split("/")
    ):
        raise ProcessorError("processor artifact path is invalid")
    root = Path(task_directory).resolve(strict=True)
    candidate = root
    for part in posix.parts:
        candidate /= part
        if candidate.is_symlink() or candidate.is_junction():
            raise ProcessorError("processor artifact must not use links")
    try:
        candidate = candidate.resolve(strict=True)
        candidate.relative_to(root)
    except (OSError, ValueError) as error:
        raise ProcessorError("processor artifact is missing") from error
    if not candidate.is_file():
        raise ProcessorError("processor artifact must be a regular file")
    return candidate


@dataclass(slots=True)
class PreparedOperation:
    task: object
    request: WorkerRequest
    workspace_root: Path
    baseline_ids: frozenset
    source_files: tuple
    result_project: Path
    export_destination: Path | None = None
    closed: bool = False

    def request_cancel(self):
        return self.task.request_cancel()

    def poll(self):
        return self.task.poll()

    def cleanup(self):
        if self.closed:
            return
        self.task.shutdown()
        task_root = self.task.task_directory.resolve(strict=True)
        workspace = self.workspace_root.resolve(strict=True)
        if task_root.parent != workspace or task_root.name != str(self.request.request_id):
            raise ProcessorError("refusing to remove an unowned processor task")
        if task_root.is_symlink() or task_root.is_junction():
            raise ProcessorError("refusing to remove a linked processor task")
        shutil.rmtree(task_root)
        self.closed = True


def _start_operation(executable, workspace, project, operation_id, inputs,
                     parameters, *, staged_files=(), source_artifacts=()):
    if not isinstance(project, QCProject):
        raise TypeError("project must be a QCProject")
    request_id = uuid4()
    workspace = Path(workspace).resolve(strict=True)
    task_directory = create_task_directory(workspace, request_id)
    try:
        copied = []
        artifact_documents = {}
        staged = tuple((None, *value) for value in staged_files) + tuple(source_artifacts)
        for role, relative, source in staged:
            copied_source, digest = _copy_input(
                source, task_directory / Path(*PurePosixPath(relative).parts)
            )
            copied.append((copied_source, digest, relative))
            if role is not None:
                artifact_documents[role] = {"path": relative, "sha256": digest}
        parameters = dict(parameters)
        if artifact_documents:
            if "source_artifacts" in parameters:
                raise ProcessorError("source_artifacts are generated from selected files")
            parameters["source_artifacts"] = artifact_documents
        project_path = task_directory / "project.cbq"
        save_project(project_path, project)
        request = WorkerRequest(
            request_id=request_id,
            project_locator=str(project_path),
            project_id=project.id,
            project_schema_version=project.schema_version,
            operation_id=operation_id,
            operation_version="0.1" if operation_id == "reader.parse" else "1",
            inputs=tuple(EntityReference(value.id, value.revision) for value in inputs),
            parameters=parameters,
        )
        task = start_worker(executable, task_directory, request)
        return PreparedOperation(
            task, request, workspace, frozenset(_entity_map(project)),
            tuple(copied),
            task_directory / "project.cbq",
        )
    except BaseException:
        if task_directory.exists() and not task_directory.is_symlink():
            shutil.rmtree(task_directory)
        raise


def start_reader_operation(executable, workspace, project, source, reader_id,
                           *, canonical_parameters=None, companions=None,
                           validation_mode="balanced"):
    if not isinstance(reader_id, str) or not _READER_ID.fullmatch(reader_id):
        raise ProcessorError("invalid scientific reader ID")
    source = _source_file(source)
    artifact = (
        "source.molden" if reader_id == "iodata_wavefunction"
        and source.suffix.lower() in {".molden", ".input"}
        else "source" + source.suffix.lower()
    )
    parameters = dict(canonical_parameters or {})
    staged = [(artifact, source)]
    companion_names = {
        "pymatgen-vasprun-electronic": {"kpoints": "KPOINTS"},
        "phonopy-file": {"force_sets": "FORCE_SETS", "born": "BORN"},
    }.get(reader_id, {})
    companions = dict(companions or {})
    if set(companions) - set(companion_names):
        raise ProcessorError("unsupported scientific reader companion")
    if reader_id == "phonopy-file" and "force_sets" not in companions:
        raise ProcessorError("phonopy reader requires FORCE_SETS")
    for role, value in companions.items():
        staged.append((companion_names[role], value))
    # Hashes are generated before launch, so construct the task in one pass here.
    request_id = uuid4()
    workspace = Path(workspace).resolve(strict=True)
    task_directory = create_task_directory(workspace, request_id)
    try:
        copied = []
        hashes = {}
        for relative, value in staged:
            original, digest = _copy_input(
                value, task_directory / Path(*PurePosixPath(relative).parts)
            )
            copied.append((original, digest, relative))
            hashes[relative] = digest
        for role, relative in companion_names.items():
            if relative in hashes:
                parameters[role + "_artifact"] = relative
                parameters[role + "_sha256"] = hashes[relative]
        project_path = task_directory / "project.cbq"
        save_project(project_path, QCProject(project.id, project.schema_version))
        request = WorkerRequest(
            request_id, str(project_path), project.id, project.schema_version,
            "reader.parse", "0.1", (), {
                "reader_id": reader_id,
                "source_artifact": artifact,
                "source_sha256": hashes[artifact],
                "validation_mode": validation_mode,
                "canonical_parameters": parameters,
            },
        )
        task = start_worker(executable, task_directory, request)
        return PreparedOperation(
            task, request, workspace, frozenset(_entity_map(project)),
            tuple(copied), task_directory / "reader-result.cbq",
        )
    except BaseException:
        if task_directory.exists() and not task_directory.is_symlink():
            shutil.rmtree(task_directory)
        raise


def start_fermi_operation(executable, workspace, project, directory, *, spin_index=0):
    root = Path(directory).expanduser().resolve(strict=True)
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        raise ProcessorError("select a regular VASP Fermi input directory")
    files = {name: root / name for name in sorted(_FERMI_REQUIRED | _FERMI_OPTIONAL)
             if name in _FERMI_REQUIRED or (root / name).is_file()}
    if any(not path.is_file() for path in files.values()):
        raise ProcessorError("Fermi input requires INCAR/KPOINTS/POSCAR/OUTCAR/PROCAR")
    request_id = uuid4()
    workspace = Path(workspace).resolve(strict=True)
    task_directory = create_task_directory(workspace, request_id)
    try:
        copied = []
        artifacts = {}
        for name, source in files.items():
            original, digest = _copy_input(source, task_directory / name)
            copied.append((original, digest, name))
            artifacts[name] = {"path": name, "sha256": digest}
        project_path = task_directory / "project.cbq"
        save_project(project_path, QCProject(project.id, project.schema_version))
        request = WorkerRequest(
            request_id, str(project_path), project.id, project.schema_version,
            "periodic.fermi_surface", "1", (), {
                "source_artifacts": artifacts,
                "spin_index": int(spin_index),
                "interpolation_factor": 1,
            },
        )
        task = start_worker(executable, task_directory, request)
        return PreparedOperation(
            task, request, workspace, frozenset(_entity_map(project)),
            tuple(copied), project_path,
        )
    except BaseException:
        if task_directory.exists() and not task_directory.is_symlink():
            shutil.rmtree(task_directory)
        raise


def start_wavefunction_operation(executable, workspace, project, operation_id,
                                 inputs, parameters):
    if operation_id not in _WAVEFUNCTION_OPERATIONS:
        raise ProcessorError("unsupported wavefunction operation")
    return _start_operation(
        executable, workspace, project, operation_id, tuple(inputs),
        dict(parameters),
    )


def start_professional_operation(executable, workspace, project, operation_id,
                                 inputs, parameters, artifacts):
    if operation_id not in _PROFESSIONAL_OPERATIONS:
        raise ProcessorError("unsupported professional operation")
    inputs = tuple(inputs)
    parameters = dict(parameters)
    if "grid_points" in parameters:
        parameters["grid_points"] = list(parameters["grid_points"])
    if "qpoints" in parameters:
        parameters["qpoints"] = [list(value) for value in parameters["qpoints"]]
    if "nac_q_direction" in parameters:
        parameters["nac_q_direction"] = list(parameters["nac_q_direction"])
    if operation_id == "topology.qtaim":
        if len(inputs) != 1 or not isinstance(inputs[0], Structure):
            raise ProcessorError("QTAIM requires the matching Structure")
        source = _source_file(artifacts.get("wavefunction", ""))
        staged = (("wavefunction", "inputs/wavefunction" + source.suffix.lower(), source),)
    elif operation_id == "grid.nci_fields":
        if inputs:
            raise ProcessorError("NCI fields use the selected wavefunction file")
        source = _source_file(artifacts.get("wavefunction", ""))
        staged = (("wavefunction", "inputs/wavefunction" + source.suffix.lower(), source),)
    else:
        if inputs:
            raise ProcessorError("phonons use frozen phonopy files")
        required = {"displacement_yaml", "force_sets"}
        if set(artifacts) not in (required, required | {"born"}):
            raise ProcessorError("phonons require phonopy YAML/FORCE_SETS and optional BORN")
        names = {"displacement_yaml": "inputs/phonopy_disp.yaml",
                 "force_sets": "inputs/FORCE_SETS", "born": "inputs/BORN"}
        staged = tuple((role, names[role], value) for role, value in artifacts.items())
    return _start_operation(
        executable, workspace, project, operation_id, inputs, parameters,
        source_artifacts=staged,
    )


def molecule_inputs(project, operation_id, structure_id, topology_id):
    if operation_id not in _MOLECULE_OPERATIONS:
        raise ProcessorError("unsupported molecular operation")
    try:
        structure = project.structures[structure_id]
        topology = project.topologies[topology_id]
    except KeyError as error:
        raise ProcessorError("select a current molecular Structure and Topology") from error
    if (not isinstance(structure, Structure)
            or topology.structure_id != structure.id
            or topology.id not in structure.topology_ids
            or structure.coordinates.unit != "angstrom"
            or structure.atomic_identity is None):
        raise ProcessorError("molecular operations require a bound angstrom Structure and Topology")
    inputs = (structure, topology)
    if operation_id in {"molecule.smiles_to_3d", "molecule.export"}:
        record = next((
            value for value in project.molecular_records.values()
            if value.structure_id == structure.id
            and value.topology_id in {None, topology.id}
        ), None)
        if operation_id == "molecule.smiles_to_3d" and record is None:
            raise ProcessorError("Generate 3D requires the bound SMILES record")
        if record is not None:
            inputs += (record,)
    return inputs


def start_molecule_operation(executable, workspace, project, operation_id,
                             inputs, parameters, *, export_destination=None):
    if operation_id not in _MOLECULE_OPERATIONS:
        raise ProcessorError("unsupported molecular operation")
    destination = None
    if operation_id == "molecule.export":
        if export_destination is None or not str(export_destination).strip():
            raise ProcessorError("select an export destination")
        destination = Path(export_destination).expanduser().resolve()
    operation = _start_operation(
        executable, workspace, project, operation_id, tuple(inputs),
        dict(parameters),
    )
    operation.export_destination = destination
    return operation


def wavefunction_inputs(project, operation_id, source_id, *, nuclear_charge_id=None):
    if operation_id not in _WAVEFUNCTION_OPERATIONS:
        raise ProcessorError("unsupported wavefunction operation")
    registry = (project.density_matrices if operation_id in {
        "wavefunction.density_matrix_grid", "wavefunction.esp_grid"
    } else project.orbital_sets)
    source = registry.get(source_id)
    if source is None:
        raise ProcessorError("select a compatible orbital set or density matrix")
    structure = project.structures[source.structure_id]
    basis = project.basis_sets[source.basis_set_id]
    if structure.coordinates.unit != "bohr":
        raise ProcessorError("wavefunction inputs must use bohr coordinates")
    inputs = (structure, basis, source)
    if operation_id in {"wavefunction.esp_grid", "wavefunction.esp_from_orbitals_grid"}:
        if isinstance(source, DensityMatrix) and source.spin_role is not DensityMatrixSpin.TOTAL:
            raise ProcessorError("ESP requires a total density matrix")
        charges = project.datasets.get(nuclear_charge_id)
        if (not isinstance(charges, AtomicProperty)
                or charges.structure_id != structure.id
                or charges.semantic_role != "nuclear_charge"
                or charges.data.unit != "elementary_charge"
                or charges.status.value != "complete"):
            raise ProcessorError("select an explicit effective nuclear-charge dataset")
        inputs += (charges,)
    return inputs


def reader_options(settings):
    """Freeze the existing scientific-reader controls into string parameters."""
    reader = settings.reader_id
    companions, parameters = {}, {}
    if reader == "pymatgen-vasprun-electronic":
        if settings.line_mode not in {"auto", "true", "false"}:
            raise ProcessorError("invalid VASP calculation mode")
        parameters["line_mode"] = settings.line_mode
        if settings.kpoints_file.strip():
            companions["kpoints"] = settings.kpoints_file
        elif settings.line_mode == "true":
            raise ProcessorError("line-mode bands require the matching KPOINTS file")
    elif reader == "phonopy-file":
        points, native, companions = phonon_options(settings)
        parameters["qpoints"] = json.dumps(points, allow_nan=False, separators=(",", ":"))
        parameters["with_group_velocities"] = (
            "true" if native["with_group_velocities"] else "false"
        )
        if "nac_q_direction" in native:
            parameters["nac_q_direction"] = json.dumps(
                native["nac_q_direction"], allow_nan=False, separators=(",", ":")
            )
    return parameters, companions


def phonon_options(settings):
    if not settings.force_sets_file.strip():
        raise ProcessorError("select the matching FORCE_SETS file")
    points = []
    for row in settings.qpoints.split(";"):
        try:
            point = tuple(float(item.strip()) for item in row.split(","))
        except ValueError as error:
            raise ProcessorError("q-points require finite fractional triples") from error
        if len(point) != 3 or not all(map(math.isfinite, point)):
            raise ProcessorError("q-points require finite fractional triples")
        points.append(point)
    parameters = {
        "qpoints": points,
        "with_group_velocities": bool(settings.with_group_velocities),
    }
    companions = {"force_sets": settings.force_sets_file}
    if settings.born_file.strip():
        companions["born"] = settings.born_file
        if settings.use_nac_direction:
            direction = tuple(settings.nac_direction)
            if not all(map(math.isfinite, direction)) or not any(direction):
                raise ProcessorError("NAC direction must be finite and nonzero")
            parameters["nac_q_direction"] = direction
        elif any(not any(point) for point in points):
            raise ProcessorError("Gamma with BORN requires an explicit NAC direction")
    elif settings.use_nac_direction:
        raise ProcessorError("NAC direction requires an explicit BORN file")
    return points, parameters, companions


def _validate_sources(operation):
    for original, expected, relative in operation.source_files:
        if _sha256(original) != expected:
            raise ProcessorError("processor source changed while the task was running")
        if _sha256(_safe_artifact(operation.task.task_directory, relative)) != expected:
            raise ProcessorError("staged processor source changed")


def _validate_reader(operation, project, result):
    metadata = result.metadata
    expected_fields = {
        "operation", "schema_version", "document_path",
        "document_sha256", "artifact_sha256",
    }
    if (set(metadata) != expected_fields
            or metadata["operation"] != "reader.parse@0.1"
            or metadata["schema_version"] != "0.1"):
        raise ProcessorError("reader result metadata is invalid")
    hashes = metadata["artifact_sha256"]
    if not isinstance(hashes, dict):
        raise ProcessorError("reader artifact hashes are invalid")
    expected_artifacts = {metadata["document_path"], *hashes}
    if set(result.artifacts) != expected_artifacts:
        raise ProcessorError("reader artifact inventory is invalid")
    if _sha256(_safe_artifact(operation.task.task_directory,
                              metadata["document_path"])) != metadata["document_sha256"]:
        raise ProcessorError("reader document hash mismatch")
    for relative, expected in hashes.items():
        if _sha256(_safe_artifact(operation.task.task_directory, relative)) != expected:
            raise ProcessorError("reader array hash mismatch")
    revision = project.source_revisions.get(operation.request.request_id)
    if (revision is None
            or revision.content_hash != operation.request.parameters["source_sha256"]
            or set(revision.created_entity_ids) != {
                reference.entity_id for reference in result.outputs
            }):
        raise ProcessorError("reader source revision is invalid")
    priority = (project.orbital_sets, project.datasets, project.structures)
    return next((identity for registry in priority
                 for identity in revision.created_entity_ids if identity in registry),
                revision.created_entity_ids[0] if revision.created_entity_ids else None)


def _normalize_reader_sources(operation, project):
    revision = project.source_revisions[operation.request.request_id]
    original = operation.source_files[0][0]
    project.source_revisions[revision.id] = replace(
        revision, locator=str(original), original_filename=original.name,
    )
    source = project.sources[revision.source_id]
    project.sources[source.id] = replace(source, display_name=original.name)
    staged = {
        str((operation.task.task_directory / relative).resolve()): str(path)
        for path, _digest, relative in operation.source_files
    }
    for identity, record in tuple(project.provenance.items()):
        if record.source in staged:
            project.provenance[identity] = replace(record, source=staged[record.source])
    published = operation.task.task_directory / "reader-published.cbq"
    save_project(published, project)
    return published


def _validate_wavefunction(operation, project, result):
    entities = _entity_map(project)
    outputs = [entities[reference.entity_id] for reference in result.outputs]
    grids = tuple(value for value in outputs if isinstance(value, Grid3D))
    matrices = tuple(value for value in outputs if isinstance(value, DensityMatrix))
    provenance = tuple(value for value in outputs if value.id in project.provenance)
    derived = operation.request.operation_id == "wavefunction.esp_from_orbitals_grid"
    if (len(grids) != 1 or len(matrices) != int(derived)
            or len(provenance) != 1 + int(derived)
            or len(outputs) != len(grids) + len(matrices) + len(provenance)):
        raise ProcessorError("wavefunction output inventory is invalid")
    grid = grids[0]
    role, unit = _WAVEFUNCTION_OPERATIONS[operation.request.operation_id]
    if role is None:
        source = project.density_matrices[operation.request.inputs[2].entity_id]
        role = "spin_density" if source.spin_role is DensityMatrixSpin.SPIN else "electron_density"
    if (grid.semantic_role != role or grid.data.unit != unit
            or grid.structure_id != operation.request.inputs[0].entity_id
            or grid.coordinate_unit != "bohr" or grid.status.value != "complete"
            or result.metadata.get("dataset_id") != str(grid.id)
            or result.cache_key != grid.revision):
        raise ProcessorError("wavefunction grid semantics are invalid")
    import numpy
    for name, actual in (("origin", grid.origin), ("step_vectors", grid.step_vectors),
                         ("shape", grid.grid_shape)):
        if not numpy.array_equal(actual, operation.request.parameters[name]):
            raise ProcessorError("wavefunction grid geometry changed")
    if numpy.iscomplexobj(grid.data.values) or not numpy.isfinite(grid.data.values).all():
        raise ProcessorError("wavefunction grid must contain finite real values")
    return grid.id


def _validate_fermi(operation, project, result):
    bands = tuple(value for value in project.datasets.values()
                  if isinstance(value, BandStructure))
    surfaces = tuple(value for value in project.datasets.values()
                     if isinstance(value, FermiSurfaceMesh))
    if (len(project.structures) != 1 or len(bands) != 1 or len(surfaces) != 1
            or len(project.datasets) != 2 or len(project.provenance) != 2):
        raise ProcessorError("Fermi output inventory is invalid")
    structure = next(iter(project.structures.values()))
    band, surface = bands[0], surfaces[0]
    if (result.metadata != {
            "operation": "periodic.fermi_surface@1",
            "structure_id": str(structure.id),
            "band_structure_id": str(band.id),
            "fermi_surface_id": str(surface.id),
        } or result.cache_key != band.revision
            or surface.band_structure_id != band.id
            or band.structure_id != structure.id
            or surface.spin_index != operation.request.parameters["spin_index"]
            or band.branches or band.status.value != "complete"
            or surface.status.value != "complete"):
        raise ProcessorError("Fermi output semantics are invalid")
    expected = operation.request.parameters["source_artifacts"]
    if any(dict(record.parameters).get("source_artifacts") != expected
           for record in project.provenance.values()):
        raise ProcessorError("Fermi provenance is incomplete")
    return surface.id


def _normalize_fermi_sources(operation, project):
    originals = {
        relative: {"path": str(path), "sha256": digest}
        for path, digest, relative in operation.source_files
    }
    for identity, record in tuple(project.provenance.items()):
        parameters = dict(record.parameters)
        parameters["source_artifacts"] = originals
        project.provenance[identity] = replace(
            record, source=str(operation.source_files[0][0].parent),
            parameters=tuple(parameters.items()),
        )
    published = operation.task.task_directory / "fermi-published.cbq"
    save_project(published, project)
    return published


def _copy_export_artifact(source, destination):
    from cbq_core.storage.atomic_paths import short_sibling_temporary_path

    destination = Path(destination)
    if destination.exists() and destination.is_dir():
        destination /= source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = short_sibling_temporary_path(destination)
    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _validate_molecule(operation, project, result):
    entities = _entity_map(project)
    outputs = tuple(entities[item.entity_id] for item in result.outputs)
    operation_id = operation.request.operation_id
    expected_operation = f"{operation_id}@1"
    if result.cache_key is None or result.metadata.get("operation") != expected_operation:
        raise ProcessorError("molecular result metadata is invalid")
    provenance = tuple(
        value for value in outputs if value.id in project.provenance
    )
    expected_provenance_operation = (
        "derive_smiles_3d"
        if operation_id == "molecule.smiles_to_3d" else operation_id
    )
    if (len(provenance) != 1
            or provenance[0].operation != expected_provenance_operation):
        raise ProcessorError("molecular provenance is invalid")
    source_structure_id = operation.request.inputs[0].entity_id
    source_topology_id = operation.request.inputs[1].entity_id
    expected_parents = (
        (operation.request.inputs[2].entity_id,
         source_structure_id, source_topology_id)
        if operation_id == "molecule.smiles_to_3d"
        else (source_structure_id, source_topology_id)
    )
    if provenance[0].parent_ids != expected_parents:
        raise ProcessorError("molecular provenance inputs are invalid")

    if operation_id == "molecule.export":
        if len(outputs) != 1 or len(result.artifacts) != 1:
            raise ProcessorError("molecular export inventory is invalid")
        relative = result.artifacts[0]
        if result.metadata.get("artifact") != relative:
            raise ProcessorError("molecular export artifact metadata is invalid")
        artifact = _safe_artifact(operation.result_project, relative)
        if _sha256(artifact) != result.metadata.get("artifact_sha256"):
            raise ProcessorError("molecular export artifact hash mismatch")
        if operation.export_destination is None:
            raise ProcessorError("molecular export destination is missing")
        _copy_export_artifact(artifact, operation.export_destination)
        return source_structure_id

    if result.artifacts:
        raise ProcessorError("molecular operation returned unexpected artifacts")
    calculations = tuple(
        value for value in outputs if value.id in project.calculations
    )
    if len(calculations) != 1:
        raise ProcessorError("molecular calculation inventory is invalid")
    calculation = calculations[0]
    if (calculation.input_structure_ids != (source_structure_id,)
            or calculation.provenance_ids != (provenance[0].id,)):
        raise ProcessorError("molecular calculation bindings are invalid")

    if operation_id == "molecule.energy":
        datasets = tuple(
            value for value in outputs if isinstance(value, PropertyDataset)
        )
        if (len(outputs) != 3 or len(datasets) != 1
                or calculation.dataset_ids != (datasets[0].id,)):
            raise ProcessorError("molecular energy inventory is invalid")
        dataset = datasets[0]
        import numpy
        if (dataset.semantic_role != "potential_energy"
                or dataset.domain != "structure"
                or dataset.data.unit != "kilocalorie_per_mole"
                or dataset.data.shape != ()
                or dataset.source_calculation != calculation.id
                or not numpy.isfinite(numpy.asarray(dataset.data.values)).all()
                or result.metadata.get("dataset_id") != str(dataset.id)):
            raise ProcessorError("molecular energy semantics are invalid")
        return dataset.id

    structures = tuple(value for value in outputs if isinstance(value, Structure))
    topologies = tuple(
        value for value in outputs if value.id in project.topologies
    )
    failed_smiles = (
        operation_id == "molecule.smiles_to_3d"
        and calculation.status.value == "failed"
    )
    if failed_smiles:
        if len(outputs) != 2 or structures or topologies:
            raise ProcessorError("failed SMILES 3D inventory is invalid")
        return calculation.id
    if (len(outputs) != 4 or len(structures) != 1 or len(topologies) != 1):
        raise ProcessorError("molecular structure inventory is invalid")
    structure, topology = structures[0], topologies[0]
    if (topology.structure_id != structure.id
            or structure.topology_ids != (topology.id,)
            or calculation.result_structure_ids != (structure.id,)
            or result.metadata.get("status") != calculation.status.value
            or result.cache_key != structure.revision):
        raise ProcessorError("molecular structure result is invalid")
    return structure.id


def _validate_professional(operation, project, result):
    outputs = tuple(_entity_map(project)[item.entity_id] for item in result.outputs)
    operation_id = operation.request.operation_id
    expected_artifacts = operation.request.parameters["source_artifacts"]
    provenance = tuple(value for value in outputs if value.id in project.provenance)
    if (result.artifacts or not provenance
            or not any(dict(value.parameters).get("source_artifacts") == expected_artifacts
                       for value in provenance)):
        raise ProcessorError("professional result provenance is incomplete")
    if operation_id == "topology.qtaim":
        graphs = tuple(value for value in outputs if isinstance(value, TopologyGraph))
        structure_id = operation.request.inputs[0].entity_id
        if (len(graphs) != 2 or len(outputs) != len(graphs) + len(provenance)
                or any(value.structure_id != structure_id for value in graphs)
                or result.metadata.get("operation") != "topology.qtaim@1"
                or result.metadata.get("topology_id") != str(graphs[-1].id)
                or result.cache_key != graphs[-1].revision):
            raise ProcessorError("QTAIM result semantics are invalid")
        return graphs[-1].id
    if operation_id == "grid.nci_fields":
        structures = tuple(value for value in outputs if isinstance(value, Structure))
        grids = tuple(value for value in outputs if isinstance(value, Grid3D))
        if (len(structures) != 1 or len(grids) != 2
                or len(outputs) != 3 + len(provenance)
                or result.metadata.get("operation") != "grid.nci_fields@1"):
            raise ProcessorError("NCI result inventory is invalid")
        by_role = {value.semantic_role: value for value in grids}
        if set(by_role) != {"reduced_density_gradient", "sign_lambda2_rho"}:
            raise ProcessorError("NCI result semantics are invalid")
        rdg, signed = by_role["reduced_density_gradient"], by_role["sign_lambda2_rho"]
        validate_nci_pair(rdg, signed)
        if (result.metadata.get("structure_id") != str(structures[0].id)
                or result.metadata.get("rdg_id") != str(rdg.id)
                or result.metadata.get("signed_density_id") != str(signed.id)
                or result.cache_key is None):
            raise ProcessorError("NCI result metadata is invalid")
        return rdg.id
    structures = tuple(value for value in outputs if isinstance(value, Structure))
    modes = tuple(value for value in outputs if isinstance(value, PhononModeSet))
    if (len(structures) != 1 or len(modes) != 1
            or len(outputs) != 2 + len(provenance)
            or modes[0].structure_id != structures[0].id
            or modes[0].status.value != "complete"
            or result.metadata != {
                "operation": "periodic.phonon@1",
                "structure_id": str(structures[0].id),
                "phonon_mode_id": str(modes[0].id),
            }
            or result.cache_key != modes[0].revision):
        raise ProcessorError("phonon result semantics are invalid")
    return modes[0].id


def _normalize_professional_sources(operation, project):
    originals = {
        role: {"path": str(path), "sha256": digest}
        for role, document in operation.request.parameters["source_artifacts"].items()
        for path, digest, relative in operation.source_files
        if relative == document["path"]
    }
    staged = {
        str((operation.task.task_directory / relative).resolve()): str(path)
        for path, _digest, relative in operation.source_files
    }
    for identity, record in tuple(project.provenance.items()):
        parameters = dict(record.parameters)
        if parameters.get("source_artifacts") == operation.request.parameters[
                "source_artifacts"]:
            parameters["source_artifacts"] = originals
        project.provenance[identity] = replace(
            record, source=staged.get(record.source, record.source),
            parameters=tuple(parameters.items()),
        )
    published = operation.task.task_directory / "professional-published.cbq"
    save_project(published, project)
    return published


def publish_operation(operation, session):
    snapshot = operation.poll()
    if snapshot.state is not ProcessorState.SUCCEEDED or snapshot.result is None:
        raise ProcessorError(snapshot.error or "processor result is not ready")
    result = snapshot.result
    if result.worker_version != WORKER_VERSION:
        raise ProcessorError("processor worker version does not match the client")
    if session.project.id != operation.request.project_id:
        raise ProcessorError("active project changed while the processor was running")
    current = _entity_map(session.project)
    if any(current.get(reference.entity_id) is None
           or current[reference.entity_id].revision != reference.revision
           for reference in operation.request.inputs):
        raise ProcessorError("processor inputs changed while the task was running")
    _validate_sources(operation)
    project = open_project(
        operation.result_project,
        expected_project_id=operation.request.project_id,
        expected_schema_version=operation.request.project_schema_version,
        verify_arrays=True,
    )
    published = operation.result_project
    try:
        entities = _entity_map(project)
        if (not result.outputs or len(result.outputs) != len(set(result.outputs))
                or any(reference.entity_id in operation.baseline_ids
                       or entities.get(reference.entity_id) is None
                       or entities[reference.entity_id].revision != reference.revision
                       for reference in result.outputs)):
            raise ProcessorError("processor output identity is invalid")
        if operation.request.operation_id == "reader.parse":
            primary = _validate_reader(operation, project, result)
            published = _normalize_reader_sources(operation, project)
        elif operation.request.operation_id == "periodic.fermi_surface":
            primary = _validate_fermi(operation, project, result)
            published = _normalize_fermi_sources(operation, project)
        elif operation.request.operation_id.startswith("molecule."):
            primary = _validate_molecule(operation, project, result)
        elif operation.request.operation_id in _PROFESSIONAL_OPERATIONS:
            primary = _validate_professional(operation, project, result)
            published = _normalize_professional_sources(operation, project)
        else:
            primary = _validate_wavefunction(operation, project, result)
    finally:
        close_project(project)
    import_package(session, published)
    if primary is None or primary not in _entity_map(session.project):
        raise ProcessorError("processor result has no selectable entity")
    session.active_entity_id = primary
    return primary


try:
    import bpy
    from bpy.props import (
        BoolProperty, EnumProperty, FloatVectorProperty, IntProperty, IntVectorProperty,
        PointerProperty, StringProperty,
    )
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    class CHEMBLENDER_PG_processor_operation(bpy.types.PropertyGroup):
        reader_id: EnumProperty(name="Input", items=(
            ("iodata_wavefunction", "Molden / WFN / FCHK", "Basis and orbitals"),
            ("cclib_output", "Gaussian / ORCA Output", "Vibrations and excitations"),
            ("pymatgen-vasprun-electronic", "VASP Bands / DOS", "vasprun.xml"),
            ("phonopy-file", "Phonopy Displacements", "phonopy YAML"),
        ))
        source_file: StringProperty(name="Scientific File", subtype="FILE_PATH")
        kpoints_file: StringProperty(name="KPOINTS", subtype="FILE_PATH")
        line_mode: EnumProperty(name="Calculation", default="auto", items=(
            ("auto", "From KPOINTS", "Use the declared calculation"),
            ("true", "Band Path", "Require matching line-mode KPOINTS"),
            ("false", "Uniform DOS Mesh", "Keep DOS and band path separate"),
        ))
        force_sets_file: StringProperty(name="FORCE_SETS", subtype="FILE_PATH")
        born_file: StringProperty(name="BORN (optional)", subtype="FILE_PATH")
        qpoints: StringProperty(name="Fractional q-points", default="0,0,0")
        with_group_velocities: BoolProperty(name="Group Velocities", default=False)
        use_nac_direction: BoolProperty(name="Explicit NAC Direction", default=False)
        nac_direction: FloatVectorProperty(
            name="NAC Direction", size=3, default=(1., 0., 0.)
        )
        fermi_directory: StringProperty(name="Fermi Input Directory", subtype="DIR_PATH")
        fermi_spin: IntProperty(name="Fermi Spin Index", default=0, min=0, max=1)
        nci_grid_points: IntVectorProperty(
            name="NCI Grid", size=3, default=(40, 40, 40), min=8, max=256,
        )
        molecule_force_field: EnumProperty(name="Force Field", items=(
            ("MMFF94", "MMFF94", "Merck Molecular Force Field"),
            ("UFF", "UFF", "Universal Force Field"),
        ))
        molecule_add_hydrogens: BoolProperty(name="Add Hydrogens", default=True)
        molecule_max_iterations: IntProperty(
            name="Maximum Iterations", default=200, min=1, max=100000,
        )
        molecule_export_format: EnumProperty(name="Format", items=(
            ("mol", "MOL", "MDL molfile"),
            ("sdf", "SDF", "Structure-data file"),
            ("smiles", "SMILES", "Canonical isomeric SMILES"),
        ))
        molecule_export_path: StringProperty(
            name="Export File", default="//molecule.sdf", subtype="FILE_PATH",
        )


    class CHEMBLENDER_OT_processor_operation(bpy.types.Operator):
        bl_idname = "chemblender.processor_operation"
        bl_label = "Run Local Processor"
        bl_description = "Run one verified operation through the configured local processor"

        action: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        operation_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        source_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        topology_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

        _session = None
        _operation = None
        _timer = None
        _window_manager = None

        def _begin(self, context):
            from .processor import get_processor_preferences
            from .session import get_scene_session

            session = self._session or get_scene_session(context.scene)
            settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
            executable = get_processor_preferences(context).processor_executable
            if self.action == "READER":
                parameters, companions = reader_options(settings)
                self._operation = start_reader_operation(
                    executable, session.temporary_root, session.project,
                    bpy.path.abspath(settings.source_file), settings.reader_id,
                    canonical_parameters=parameters,
                    companions={key: bpy.path.abspath(value)
                                for key, value in companions.items()},
                )
            elif self.action == "FERMI":
                self._operation = start_fermi_operation(
                    executable, session.temporary_root, session.project,
                    bpy.path.abspath(settings.fermi_directory),
                    spin_index=settings.fermi_spin,
                )
            elif self.action == "WAVEFUNCTION":
                from .wavefunction import prepare_wavefunction_request
                inputs, parameters = prepare_wavefunction_request(
                    session, context.scene.chemblender_wavefunction,
                    self.operation_id, UUID(self.source_id),
                )
                self._operation = start_wavefunction_operation(
                    executable, session.temporary_root, session.project,
                    self.operation_id, inputs, parameters,
                )
            elif self.action == "MOLECULE":
                inputs = molecule_inputs(
                    session.project, self.operation_id,
                    UUID(self.source_id), UUID(self.topology_id),
                )
                if self.operation_id == "molecule.smiles_to_3d":
                    parameters = {
                        "add_hydrogens": settings.molecule_add_hydrogens,
                        "force_field": settings.molecule_force_field,
                        "random_seed": 0xC0FFEE,
                        "num_threads": 1,
                        "max_iterations": settings.molecule_max_iterations,
                    }
                elif self.operation_id == "molecule.optimize":
                    parameters = {
                        "add_hydrogens": settings.molecule_add_hydrogens,
                        "force_field": settings.molecule_force_field,
                        "max_iterations": settings.molecule_max_iterations,
                    }
                elif self.operation_id == "molecule.energy":
                    parameters = {"force_field": settings.molecule_force_field}
                elif self.operation_id == "molecule.export":
                    parameters = {
                        "format": settings.molecule_export_format,
                        "confirm_loss": True,
                        "isomeric": True,
                    }
                else:
                    parameters = {}
                destination = None
                if self.operation_id == "molecule.export":
                    destination = settings.molecule_export_path
                    if destination.strip():
                        destination = Path(bpy.path.abspath(destination))
                        expected = "." + settings.molecule_export_format
                        if destination.suffix.lower() != expected:
                            destination = destination.with_suffix(expected)
                self._operation = start_molecule_operation(
                    executable, session.temporary_root, session.project,
                    self.operation_id, inputs, parameters,
                    export_destination=destination,
                )
            elif self.action == "PROFESSIONAL":
                if self.operation_id == "periodic.phonon":
                    _points, parameters, companions = phonon_options(settings)
                    artifacts = {
                        "displacement_yaml": bpy.path.abspath(settings.source_file),
                        **{role: bpy.path.abspath(value)
                           for role, value in companions.items()},
                    }
                    inputs = ()
                else:
                    parameters = ({"grid_points": tuple(settings.nci_grid_points)}
                                  if self.operation_id == "grid.nci_fields" else {})
                    artifacts = {"wavefunction": bpy.path.abspath(settings.source_file)}
                    inputs = ()
                    if self.operation_id == "topology.qtaim":
                        entity = _entity_map(session.project).get(session.active_entity_id)
                        structure = (entity if isinstance(entity, Structure) else
                                     session.project.structures.get(
                                         getattr(entity, "structure_id", None)
                                     ))
                        if structure is None:
                            raise ProcessorError("select the Structure imported from this wavefunction")
                        inputs = (structure,)
                self._operation = start_professional_operation(
                    executable, session.temporary_root, session.project,
                    self.operation_id, inputs, parameters, artifacts,
                )
            else:
                raise ProcessorError("unsupported processor action")

        def _release(self, context):
            manager = context.window_manager if context is not None else self._window_manager
            if self._timer is not None and manager is not None:
                try:
                    manager.event_timer_remove(self._timer)
                except RuntimeError:
                    pass
                self._timer = None
            try:
                if self._operation is not None:
                    try:
                        self._operation.cleanup()
                    except (OSError, ProcessorError) as error:
                        self.report({"WARNING"}, f"Processor cleanup failed: {error}")
            finally:
                if self._session is not None:
                    _ACTIVE_OPERATIONS.pop(self._session.id, None)
                # Redraw after releasing the active job, including energy-only results.
                area = getattr(context, "area", None)
                if area is not None:
                    area.tag_redraw()

        def _complete(self, context, snapshot):
            from .session import _notify_session_mutation
            try:
                if snapshot.state is ProcessorState.SUCCEEDED:
                    primary = publish_operation(self._operation, self._session)
                    context.scene.chemblender_project_browser.active_entity_id = str(primary)
                    view_settings = context.scene.chemblender_scientific_view
                    view_settings.preset_id = "AUTO"
                    if self._operation.request.operation_id == "grid.nci_fields":
                        view_settings.preset_id = "nci_surface"
                        view_settings.secondary_source_uuid = snapshot.result.metadata[
                            "signed_density_id"
                        ]
                        view_settings.pairing_confirmed = True
                    _notify_session_mutation(self._session)
                    entity = _entity_map(self._session.project)[primary]
                    if (primary not in self._operation.baseline_ids
                            and isinstance(entity, (
                                Structure, Grid3D, FermiSurfaceMesh,
                                TopologyGraph, PhononModeSet,
                            ))):
                        try:
                            view_result = bpy.ops.chemblender.scientific_view(action="CREATE")
                        except RuntimeError:
                            view_result = {"CANCELLED"}
                        if view_result != {"FINISHED"}:
                            self.report({"WARNING"}, "Result added; create its View manually")
                    if self._operation.request.operation_id == "molecule.export":
                        self.report({"INFO"}, "Molecule exported to " + str(
                            self._operation.export_destination
                        ))
                    elif self._operation.request.operation_id == "molecule.energy":
                        self.report({"INFO"}, "Potential energy added to the project")
                    else:
                        self.report({"INFO"}, "Processor result added to the project")
                    return {"FINISHED"}
                if snapshot.state is ProcessorState.CANCELLED:
                    self.report({"INFO"}, "Processor operation cancelled")
                elif snapshot.error:
                    self.report({"ERROR"}, snapshot.error)
                return {"CANCELLED"}
            except (KeyError, OSError, ProcessorError, TypeError, ValueError) as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            finally:
                self._release(context)

        def invoke(self, context, _event):
            from .session import get_scene_session
            self._session = get_scene_session(context.scene)
            if self._session.id in _ACTIVE_OPERATIONS:
                self.report({"ERROR"}, "Wait for the current processor operation")
                return {"CANCELLED"}
            _ACTIVE_OPERATIONS[self._session.id] = self
            self._window_manager = context.window_manager
            self._timer = context.window_manager.event_timer_add(.1, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}

        def modal(self, context, event):
            if event.type == "ESC":
                if self._operation is None:
                    self._release(context)
                    return {"CANCELLED"}
                self._operation.request_cancel()
                return {"RUNNING_MODAL"}
            if event.type != "TIMER":
                return {"PASS_THROUGH"}
            try:
                if self._operation is None:
                    self._begin(context)
                snapshot = self._operation.poll()
            except (KeyError, OSError, ProcessorError, TypeError, ValueError) as error:
                self.report({"ERROR"}, str(error))
                self._release(context)
                return {"CANCELLED"}
            if snapshot.state in _OPERATION_TERMINAL_STATES:
                return self._complete(context, snapshot)
            return {"RUNNING_MODAL"}

        def execute(self, context):
            from .session import get_scene_session
            self._session = get_scene_session(context.scene)
            if self._session.id in _ACTIVE_OPERATIONS:
                self.report({"ERROR"}, "Wait for the current processor operation")
                return {"CANCELLED"}
            _ACTIVE_OPERATIONS[self._session.id] = self
            try:
                self._begin(context)
                while True:
                    snapshot = self._operation.poll()
                    if snapshot.state in _OPERATION_TERMINAL_STATES:
                        return self._complete(context, snapshot)
                    time.sleep(.02)
            except (KeyError, OSError, ProcessorError, TypeError, ValueError) as error:
                self.report({"ERROR"}, str(error))
                self._release(context)
                return {"CANCELLED"}

        def cancel(self, context):
            if self._operation is not None:
                self._operation.task.shutdown()
            self._release(context)


    def _cancel_session_operation(session):
        operator = _ACTIVE_OPERATIONS.get(session.id)
        if operator is not None:
            operator.cancel(None)


    def draw_processor_inputs(layout, context, session):
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        header, body = layout.panel("chemblender_processor_inputs", default_closed=True)
        header.label(text="Local Processor · Scientific Input")
        if body is None:
            return
        body.prop(settings, "reader_id")
        body.prop(settings, "source_file")
        if settings.reader_id == "pymatgen-vasprun-electronic":
            body.prop(settings, "line_mode")
            body.prop(settings, "kpoints_file")
        elif settings.reader_id == "phonopy-file":
            for name in ("force_sets_file", "born_file", "qpoints",
                         "with_group_velocities", "use_nac_direction"):
                body.prop(settings, name)
            if settings.use_nac_direction:
                body.prop(settings, "nac_direction")
        active = _ACTIVE_OPERATIONS.get(session.id)
        row = body.row()
        row.enabled = active is None
        button = row.operator(CHEMBLENDER_OT_processor_operation.bl_idname,
                              text="Read Scientific File", icon="IMPORT")
        button.action = "READER"
        body.separator()
        body.prop(settings, "fermi_directory")
        body.prop(settings, "fermi_spin")
        row = body.row()
        row.enabled = active is None
        button = row.operator(CHEMBLENDER_OT_processor_operation.bl_idname,
                              text="Extract Fermi Surface", icon="IMPORT")
        button.action = "FERMI"
        body.separator()
        body.label(text="Professional Analysis")
        body.prop(settings, "nci_grid_points")
        row = body.row(align=True)
        row.enabled = active is None
        for operation_id, label in (
            ("topology.qtaim", "QTAIM"),
            ("grid.nci_fields", "NCI"),
            ("periodic.phonon", "Phonons"),
        ):
            button = row.operator(
                CHEMBLENDER_OT_processor_operation.bl_idname,
                text=label, icon="PLAY",
            )
            button.action = "PROFESSIONAL"
            button.operation_id = operation_id
        if active is not None:
            snapshot = (active._operation.task.snapshot()
                        if active._operation is not None else None)
            body.label(text=(f"{snapshot.stage}: {snapshot.progress:.0%} · Esc to cancel"
                             if snapshot is not None else "Starting processor · Esc to cancel"))


    def draw_molecule_controls(layout, context, session, obj):
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        try:
            structure_id = UUID(obj.get("cb_structure_id"))
            topology_id = UUID(obj.get("cb_topology_id"))
            structure = session.project.structures[structure_id]
            topology = session.project.topologies[topology_id]
        except (KeyError, TypeError, ValueError):
            layout.label(text="A current molecular Topology is required")
            return
        if (obj.get("cb_structure_revision") != structure.revision
                or obj.get("cb_topology_revision") != topology.revision
                or topology.structure_id != structure.id):
            layout.label(text="Refresh the stale molecular View first")
            return
        box = layout.box()
        box.label(text="Local Processor · Molecular Operations")
        box.prop(settings, "molecule_force_field")
        box.prop(settings, "molecule_add_hydrogens")
        box.prop(settings, "molecule_max_iterations")
        controls = box.column()
        active = _ACTIVE_OPERATIONS.get(session.id)
        controls.enabled = active is None and not obj.get("cbq_mesh_edit_pending", False)

        def add_button(target, text, operation_id, icon="NONE"):
            value = target.operator(
                CHEMBLENDER_OT_processor_operation.bl_idname,
                text=text, icon=icon,
            )
            value.action = "MOLECULE"
            value.operation_id = operation_id
            value.source_id = str(structure.id)
            value.topology_id = str(topology.id)

        record = next((
            value for value in session.project.molecular_records.values()
            if value.structure_id == structure.id
            and value.topology_id in {None, topology.id}
            and (revision := session.project.source_revisions.get(
                value.source_revision_id
            )) is not None
            and revision.reader_id == "smiles"
        ), None)
        if record is not None:
            add_button(controls, "Generate 3D (ETKDG)",
                       "molecule.smiles_to_3d")
        row = controls.row(align=True)
        for text, operation_id in (
            ("Kekulize", "molecule.kekulize"),
            ("Optimize", "molecule.optimize"),
            ("Energy", "molecule.energy"),
        ):
            add_button(row, text, operation_id)
        controls.prop(settings, "molecule_export_format")
        controls.prop(settings, "molecule_export_path")
        add_button(controls, "Export Molecule", "molecule.export", "EXPORT")
        if obj.get("cbq_mesh_edit_pending", False):
            box.label(text="Apply Mesh edits before running molecular operations")
        elif active is not None:
            snapshot = (
                active._operation.task.snapshot()
                if active._operation is not None else None
            )
            box.label(text=(
                f"{snapshot.state.value}: {snapshot.progress:.0%} · Esc to cancel"
                if snapshot is not None else "Starting processor · Esc to cancel"
            ))


    def register():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        from .session import register_session_cleanup
        current = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if _OWNED_SCENE_PROPERTY is not None:
            if not _same_scene_property(current, _OWNED_SCENE_PROPERTY):
                raise RuntimeError("processor operation Scene property is no longer owned")
        elif current is not None:
            raise RuntimeError("processor operation Scene property is already owned")
        else:
            setattr(bpy.types.Scene, _SCENE_PROPERTY_NAME,
                    PointerProperty(type=CHEMBLENDER_PG_processor_operation))
            _OWNED_SCENE_PROPERTY = _scene_property_identity(_SCENE_PROPERTY_NAME)
        register_session_cleanup(_cancel_session_operation)


    def unregister():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        from .session import unregister_session_cleanup
        unregister_session_cleanup(_cancel_session_operation)
        for operator in tuple(_ACTIVE_OPERATIONS.values()):
            operator.cancel(None)
        if (_OWNED_SCENE_PROPERTY is not None
                and _same_scene_property(_scene_property_identity(_SCENE_PROPERTY_NAME),
                                         _OWNED_SCENE_PROPERTY)):
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
        _OWNED_SCENE_PROPERTY = None


__all__ = (
    "PreparedOperation", "molecule_inputs", "publish_operation", "reader_options",
    "start_fermi_operation", "start_molecule_operation", "start_reader_operation",
    "start_wavefunction_operation", "wavefunction_inputs",
)
if bpy is not None:
    __all__ += (
        "CHEMBLENDER_OT_processor_operation", "CHEMBLENDER_PG_processor_operation",
        "draw_molecule_controls", "draw_processor_inputs",
    )
