"""Optional QCEngine and PySCF execution behind the local worker boundary."""

import copy
import hashlib
import json
import math
import os
import re
from pathlib import Path
from uuid import uuid4

from ChemBlender.core import parse_qcschema_atomic_result

from .operation import OperationError, OperationOutput
from .protocol import EntityReference


_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*")
_REQUEST_FIELDS = {"backend", "input_data", "program", "return_version", "task_config"}
_TASK_FIELDS = {"ncores", "memory", "retries", "scratch_messy"}
_RESULT_IDENTITIES = {("qcschema_output", 1), ("qcschema_atomic_result", 2)}


class QCSchemaExecutionError(OperationError):
    pass


def _invalid(message):
    raise QCSchemaExecutionError("invalid_input", message)


def _load_qcengine_compute():
    from qcengine import compute

    return compute


def _load_pyscf():
    import pyscf

    return pyscf


def _has_local_override(value):
    if isinstance(value, dict):
        return "_qcengine_local_config" in value or any(
            _has_local_override(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_has_local_override(item) for item in value)
    return False


def _positive_number(value, name, *, integral=False, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _invalid(f"{name} must be numeric")
    outside_range = value < 0 if allow_zero else value <= 0
    if not math.isfinite(value) or outside_range:
        _invalid(f"{name} is outside the supported range")
    if integral and int(value) != value:
        _invalid(f"{name} must be an integer")
    return int(value) if integral else value


def _validate_task_config(value):
    if not isinstance(value, dict) or set(value) - _TASK_FIELDS:
        _invalid(f"task_config supports only {sorted(_TASK_FIELDS)}")
    result = {}
    for key in sorted(value):
        item = value[key]
        if key == "ncores":
            item = _positive_number(item, key, integral=True)
        elif key == "memory":
            item = _positive_number(item, key)
        elif key == "retries":
            item = _positive_number(item, key, integral=True, allow_zero=True)
        elif not isinstance(item, bool):
            _invalid("scratch_messy must be a boolean")
        result[key] = item
    return result


def _validate_request(parameters):
    if not isinstance(parameters, dict) or set(parameters) != _REQUEST_FIELDS:
        _invalid(f"parameters must contain exactly {sorted(_REQUEST_FIELDS)}")
    backend = parameters["backend"]
    if backend not in {"qcengine", "pyscf"}:
        _invalid("backend must be qcengine or pyscf")
    program = parameters["program"]
    if not isinstance(program, str) or not _TOKEN.fullmatch(program):
        _invalid("program must be a lower token")
    if backend == "pyscf" and program != "pyscf":
        _invalid("the PySCF backend requires program=pyscf")
    return_version = parameters["return_version"]
    if isinstance(return_version, bool) or return_version not in {1, 2}:
        _invalid("return_version must be 1 or 2")
    document = parameters["input_data"]
    if not isinstance(document, dict):
        _invalid("input_data must be a JSON object")
    identity = (document.get("schema_name"), document.get("schema_version"))
    if identity not in {("qcschema_input", 1), ("qcschema_atomic_input", 2)}:
        _invalid("input_data must be a supported QCSchema AtomicInput")
    if _has_local_override(document):
        _invalid("input_data must not override local QCEngine configuration")
    task_config = _validate_task_config(parameters["task_config"])
    if backend == "pyscf" and (return_version != 2 or set(task_config) - {"ncores"}):
        _invalid("PySCF supports return_version=2 and task_config.ncores only")
    return backend, copy.deepcopy(document), program, return_version, task_config


def _validate_result(document):
    if not isinstance(document, dict):
        raise QCSchemaExecutionError("invalid_result", "backend returned a non-object result")
    if document.get("success") is False:
        error = document.get("error")
        message = "calculation failed"
        if isinstance(error, dict) and isinstance(error.get("error_message"), str):
            message = error["error_message"] or message
        raise QCSchemaExecutionError("calculation_failed", message)
    identity = (document.get("schema_name"), document.get("schema_version"))
    if document.get("success") is not True or identity not in _RESULT_IDENTITIES:
        raise QCSchemaExecutionError(
            "invalid_result", "backend did not return a supported successful AtomicResult"
        )
    return document


def _v2_specification(document):
    specification = document.get("specification")
    molecule = document.get("molecule")
    if not isinstance(specification, dict) or not isinstance(molecule, dict):
        _invalid("QCSchema v2 input requires specification and molecule objects")
    return specification, molecule


def _pyscf_result(input_data, pyscf_module, task_config):
    if (input_data.get("schema_name"), input_data.get("schema_version")) != (
        "qcschema_atomic_input",
        2,
    ):
        _invalid("PySCF initially supports QCSchema v2 AtomicInput only")
    specification, molecule = _v2_specification(input_data)
    if specification.get("driver") != "energy":
        _invalid("PySCF initially supports the energy driver only")
    model = specification.get("model")
    if not isinstance(model, dict):
        _invalid("specification.model must be an object")
    method = model.get("method")
    basis = model.get("basis")
    if not isinstance(method, str) or method.lower() not in {"hf", "rhf", "uhf"}:
        _invalid("PySCF initially supports HF, RHF and UHF only")
    if not isinstance(basis, str) or not basis:
        _invalid("PySCF requires a string basis name")
    if specification.get("keywords") not in (None, {}):
        _invalid("PySCF keywords are not supported by the initial adapter")
    symbols = molecule.get("symbols")
    geometry = molecule.get("geometry")
    if not isinstance(symbols, list) or not symbols or not all(
        isinstance(symbol, str) and symbol for symbol in symbols
    ):
        _invalid("molecule.symbols must contain element symbols")
    if not isinstance(geometry, list) or len(geometry) != 3 * len(symbols) or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in geometry
    ):
        _invalid("molecule.geometry must contain three finite values per atom")
    charge = molecule.get("molecular_charge", 0)
    multiplicity = molecule.get("molecular_multiplicity", 1)
    if isinstance(charge, bool) or not isinstance(charge, (int, float)) or int(charge) != charge:
        _invalid("molecular_charge must be an integer")
    if (
        isinstance(multiplicity, bool)
        or not isinstance(multiplicity, (int, float))
        or int(multiplicity) != multiplicity
        or multiplicity < 1
    ):
        _invalid("molecular_multiplicity must be a positive integer")
    atoms = [
        (symbols[index], tuple(geometry[3 * index : 3 * index + 3]))
        for index in range(len(symbols))
    ]
    if "ncores" in task_config and hasattr(pyscf_module, "lib"):
        pyscf_module.lib.num_threads(task_config["ncores"])
    mol = pyscf_module.gto.M(
        atom=atoms,
        unit="Bohr",
        charge=int(charge),
        spin=int(multiplicity) - 1,
        basis=basis,
        verbose=0,
    )
    unrestricted = method.lower() == "uhf" or int(multiplicity) != 1
    calculation = (pyscf_module.scf.UHF if unrestricted else pyscf_module.scf.RHF)(mol)
    energy = float(calculation.kernel())
    if not math.isfinite(energy) or not calculation.converged:
        raise QCSchemaExecutionError("calculation_failed", "PySCF SCF did not converge")
    normalized_input = copy.deepcopy(input_data)
    normalized_input["specification"]["program"] = "pyscf"
    nalpha, nbeta = mol.nelec
    return {
        "schema_name": "qcschema_atomic_result",
        "schema_version": 2,
        "input_data": normalized_input,
        "molecule": copy.deepcopy(molecule),
        "properties": {
            "return_energy": energy,
            "calcinfo_nalpha": int(nalpha),
            "calcinfo_nbeta": int(nbeta),
        },
        "return_result": energy,
        "success": True,
        "provenance": {
            "creator": "PySCF",
            "version": str(getattr(pyscf_module, "__version__", "unknown")),
            "routine": type(calculation).__name__,
        },
        "native_files": {},
        "extras": {},
    }


def execute_qcschema(parameters, *, qcengine_compute=None, pyscf_module=None):
    backend, input_data, program, return_version, task_config = _validate_request(parameters)
    if backend == "qcengine":
        if qcengine_compute is None:
            try:
                qcengine_compute = _load_qcengine_compute()
            except ImportError as error:
                raise QCSchemaExecutionError(
                    "dependency_missing", "QCEngine is not installed in the worker environment"
                ) from error
        try:
            result = qcengine_compute(
                input_data,
                program,
                raise_error=False,
                return_dict=True,
                return_version=return_version,
                task_config=task_config,
            )
        except Exception as error:
            raise QCSchemaExecutionError(
                "calculation_failed", str(error) or type(error).__name__
            ) from error
    else:
        if pyscf_module is None:
            try:
                pyscf_module = _load_pyscf()
            except ImportError as error:
                raise QCSchemaExecutionError(
                    "dependency_missing", "PySCF is not installed in the worker environment"
                ) from error
        try:
            result = _pyscf_result(input_data, pyscf_module, task_config)
        except QCSchemaExecutionError:
            raise
        except Exception as error:
            raise QCSchemaExecutionError(
                "calculation_failed", str(error) or type(error).__name__
            ) from error
    return _validate_result(result)


def _write_json(path, document):
    data = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return hashlib.sha256(data).hexdigest()


def _batch_references(batch):
    groups = (
        batch.structures,
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
    return tuple(
        EntityReference(entity.id, entity.revision)
        for group in groups
        for entity in group
    )


def qcschema_compute_operation(context, request):
    document = execute_qcschema(request.parameters)
    canonical = json.dumps(
        document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    identity = hashlib.sha256(canonical).hexdigest()
    relative = Path("cache") / "qcschema-compute" / identity / "result.json"
    result_path = context.project_path / relative
    result_hash = _write_json(result_path, document)
    batch = parse_qcschema_atomic_result(result_path)
    return OperationOutput(
        outputs=_batch_references(batch),
        artifacts=(relative.as_posix(),),
        cache_key=result_hash,
        metadata={
            "backend": request.parameters["backend"],
            "program": request.parameters["program"],
            "return_version": request.parameters["return_version"],
        },
        batch=batch,
    )


def register_qcschema_compute_operation(registry):
    registry.register("qcschema.compute", "1", qcschema_compute_operation)
