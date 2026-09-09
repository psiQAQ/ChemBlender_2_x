"""Frozen, hash-checked VASP text input for the optional periodic worker."""

import hashlib
import re
from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from chemblender_prepare.core.pyprocar_file import OPTIONAL_FILES
from chemblender_prepare.core.pyprocar_file import REQUIRED_FILES
from chemblender_prepare.core.pyprocar_file import parse_vasp_fermi
from chemblender_prepare.reader_api.worker_bridge import WorkerReaderIntegrityError
from chemblender_prepare.reader_api.worker_bridge import _task_file

from chemblender_prepare.worker.operation import OperationError
from chemblender_prepare.worker.wavefunction_operations import _output
from chemblender_prepare.worker.wavefunction_operations import _progress


def _fermi_surface(context, request):
    parameters = request.parameters
    allowed = {"source_artifacts", "spin_index", "interpolation_factor"}
    if request.inputs or not isinstance(parameters, dict) or set(parameters) - allowed:
        raise OperationError("fermi_request_invalid", "Fermi worker accepts only frozen text artifacts and display-independent numeric parameters")
    artifacts = parameters.get("source_artifacts")
    if not isinstance(artifacts, dict) or not REQUIRED_FILES <= set(artifacts) or set(artifacts) - REQUIRED_FILES - OPTIONAL_FILES:
        raise OperationError("fermi_request_invalid", "source_artifacts requires INCAR/KPOINTS/POSCAR/OUTCAR/PROCAR and optional IBZKPT only")
    if context.task_directory is None:
        raise OperationError("fermi_request_invalid", "Fermi operation requires a task directory")
    # PyProcar sees only the explicitly accepted filenames, including no gz
    # siblings. Its directory parser / pickle cache helpers are never invoked.
    try:
        with TemporaryDirectory(prefix="fermi-text-", dir=context.task_directory) as directory:
            for name, document in sorted(artifacts.items()):
                if not isinstance(document, dict) or set(document) != {"path", "sha256"} or not isinstance(document["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", document["sha256"]):
                    raise OperationError("fermi_request_invalid", "each artifact requires exactly path and SHA-256")
                source = _task_file(context.task_directory, document["path"])
                digest = hashlib.sha256()
                with source.open("rb") as reader, (Path(directory) / name).open("xb") as writer:
                    while data := reader.read(1024 * 1024):
                        if context.is_cancelled():
                            raise CancelledError("Fermi input staging cancelled")
                        digest.update(data)
                        writer.write(data)
                if digest.hexdigest() != document["sha256"]:
                    raise OperationError("fermi_source_invalid", f"{name} source artifact hash mismatch")
            batch = parse_vasp_fermi(
                directory, spin_index=parameters.get("spin_index", 0),
                interpolation_factor=parameters.get("interpolation_factor", 1),
                is_cancelled=context.is_cancelled, progress=_progress(context),
            )
            # The temporary directory is not a durable source locator. Keep the
            # task-relative file identities together with each file's real hash.
            batch = replace(batch, provenance=tuple(
                replace(item, source="VASP text bundle", parameters=(
                    *item.parameters, ("source_artifacts", artifacts),
                )) for item in batch.provenance
            ))
    except WorkerReaderIntegrityError as error:
        raise OperationError("fermi_source_invalid", str(error)) from error
    if context.is_cancelled():
        raise CancelledError("Fermi evaluation cancelled before publication")
    output = _output(batch)
    return replace(output, metadata={
        "operation": "periodic.fermi_surface@1",
        "band_structure_id": str(batch.datasets[0].id),
        "fermi_surface_id": str(batch.datasets[1].id),
        "structure_id": str(batch.structures[0].id),
    })


def register_fermi_surface_operation(registry):
    registry.register("periodic.fermi_surface", "1", _fermi_surface)
