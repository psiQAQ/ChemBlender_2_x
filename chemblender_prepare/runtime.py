"""Live processor capabilities, diagnostics, and worker environment routing."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory

from cbq_core.worker_protocol import (
    PROTOCOL_VERSION,
    WORKER_VERSION,
    WorkerError,
    WorkerResult,
    WorkerStatus,
    read_request,
    read_result,
    write_result,
)


CAPABILITY_SCHEMA_VERSION = "1"
CONFIGURATION_ENVIRONMENT = "CHEMBLENDER_PREPARE_CONFIG"
_ENVIRONMENTS = frozenset({"wavefunction", "scientific", "fermi"})
_SCIENTIFIC_READERS = frozenset({
    "ase-structure",
    "cclib_output",
    "phonopy-file",
    "pymatgen-vasp-grid",
    "pymatgen-vasprun-electronic",
})
_PROBED_DISTRIBUTIONS = (
    "numpy",
    "rdkit",
    "gemmi",
    "qc-gbasis",
    "qc-iodata",
    "pyprocar",
    "pymatgen-core",
    "phonopy",
    "ase",
    "cclib",
    "qcengine",
    "pyscf",
)
_MODULE_DISTRIBUTIONS = {
    "iodata": "qc-iodata",
    "pymatgen": "pymatgen-core",
}


def load_configuration(path=None):
    if path is None:
        path = os.environ.get(CONFIGURATION_ENVIRONMENT)
        if not path:
            adjacent = Path(sys.argv[0]).resolve().with_name(
                "chemblender-prepare.json"
            )
            path = adjacent if adjacent.is_file() else None
    if not path:
        return {"schema_version": "1", "python": {}, "critic2": None}
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read processor configuration: {path}") from error
    if not isinstance(document, dict) or set(document) != {
        "schema_version", "python", "critic2"
    }:
        raise ValueError("processor configuration fields are invalid")
    if document["schema_version"] != "1":
        raise ValueError("unsupported processor configuration version")
    routes = document["python"]
    if not isinstance(routes, dict) or set(routes) - _ENVIRONMENTS:
        raise ValueError("processor Python routes are invalid")
    for name, value in routes.items():
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError(f"processor Python route must be absolute: {name}")
    critic2 = document["critic2"]
    if critic2 is not None and (
        not isinstance(critic2, str) or not Path(critic2).is_absolute()
    ):
        raise ValueError("critic2 path must be absolute")
    return document


def _reader_environment(reader_id):
    if reader_id == "iodata_wavefunction":
        return "wavefunction"
    if reader_id in _SCIENTIFIC_READERS:
        return "scientific"
    return "current"


def request_environment(request):
    if request.operation_id.startswith("wavefunction."):
        return "wavefunction"
    if request.operation_id == "periodic.phonon":
        return "scientific"
    if request.operation_id == "periodic.fermi_surface":
        return "fermi"
    if request.operation_id == "reader.parse":
        return _reader_environment(request.parameters.get("reader_id"))
    return "current"


def _route_executable(configuration, environment):
    if environment == "current":
        return Path(sys.executable)
    executable = configuration["python"].get(environment)
    return Path(executable) if executable else None


def _probe_python(executable):
    executable = Path(executable)
    if not executable.is_file():
        return {"available": False, "python_version": None,
                "executable": str(executable), "versions": {},
                "error": "Python executable does not exist"}
    # Distribution lookup needs individual exception handling; keep the child
    # independent of this package and any scientific imports.
    script = """
import importlib.metadata as metadata
import json
import sys
versions = {}
for name in json.loads(sys.argv[1]):
    try:
        versions[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        pass
print(json.dumps({"python_version": sys.version.split()[0],
                  "executable": sys.executable, "versions": versions}))
"""
    try:
        completed = subprocess.run(
            [str(executable), "-I", "-c", script,
             json.dumps(_PROBED_DISTRIBUTIONS)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            shell=False,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Python probe failed")
        result = json.loads(completed.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError,
            RuntimeError) as error:
        return {"available": False, "python_version": None,
                "executable": str(executable), "versions": {},
                "error": str(error) or type(error).__name__}
    return {"available": True, **result, "error": None}


def _operation_capability(operation_id, operation_version, probes, critic2):
    environment = "current"
    required = ()
    any_required = ()
    if operation_id.startswith("wavefunction."):
        environment, required = "wavefunction", ("qc-gbasis",)
    elif operation_id == "periodic.phonon":
        environment, required = "scientific", ("phonopy",)
    elif operation_id == "periodic.fermi_surface":
        environment, required = "fermi", ("pyprocar",)
    elif operation_id == "qcschema.compute":
        any_required = ("qcengine", "pyscf")
    elif operation_id.startswith("molecule."):
        required = ("rdkit",)
    elif operation_id in {"topology.qtaim", "grid.nci_fields"}:
        return {
            "operation_id": operation_id,
            "operation_version": operation_version,
            "environment": "current",
            "available": critic2["available"],
            "backend_versions": ({"critic2": critic2["version"]}
                                 if critic2["available"] else {}),
            "reason": critic2["error"],
        }
    probe = probes[environment]
    versions = probe["versions"]
    missing = [name for name in required if name not in versions]
    if any_required and not any(name in versions for name in any_required):
        missing = ["qcengine or pyscf"]
    available = probe["available"] and not missing
    backends = required or tuple(name for name in any_required if name in versions)
    reason = probe["error"] if not probe["available"] else None
    if missing and probe["available"]:
        reason = "missing " + ", ".join(missing)
    return {
        "operation_id": operation_id,
        "operation_version": operation_version,
        "environment": environment,
        "available": available,
        "backend_versions": {name: versions[name] for name in backends
                             if name in versions},
        "reason": reason,
    }


def _reader_capabilities(probes):
    from .core.reader_catalog import reader_capability_document

    readers = []
    for reader in reader_capability_document()["readers"]:
        reader = dict(reader)
        environment = _reader_environment(reader["reader_id"])
        probe = probes[environment]
        contract = reader["availability_contract"]
        distribution = None
        if contract["kind"] == "python_module":
            distribution = _MODULE_DISTRIBUTIONS.get(
                contract["module"], contract["module"]
            )
        available = probe["available"] and (
            distribution is None or distribution in probe["versions"]
        )
        reason = probe["error"] if not probe["available"] else None
        if (probe["available"] and distribution is not None
                and distribution not in probe["versions"]):
            reason = "missing " + distribution
        reader.update({
            "environment": environment,
            "available": available,
            "backend_versions": ({distribution: probe["versions"][distribution]}
                                 if distribution in probe["versions"] else {}),
            "reason": reason,
        })
        readers.append(reader)
    return readers


def capability_document(configuration=None):
    configuration = configuration or load_configuration()
    probes_by_path = {}
    probes = {}
    for environment in ("current", "wavefunction", "scientific", "fermi"):
        executable = _route_executable(configuration, environment)
        if executable is None:
            probes[environment] = {
                "available": False,
                "python_version": None,
                "executable": None,
                "versions": {},
                "error": "not configured",
            }
            continue
        key = os.path.normcase(str(executable.resolve()))
        if key not in probes_by_path:
            probes_by_path[key] = _probe_python(executable)
        probes[environment] = probes_by_path[key]
    from .worker.runner import default_registry

    critic2 = _probe_critic2(configuration["critic2"])
    operations = [
        _operation_capability(operation_id, operation_version, probes, critic2)
        for operation_id, operation_version in sorted(default_registry()._operations)
    ]
    environments = []
    for name in ("current", "wavefunction", "scientific", "fermi"):
        probe = probes[name]
        environments.append({
            "name": name,
            "configured": name == "current" or name in configuration["python"],
            **probe,
        })
    return {
        "schema_name": "chemblender_prepare_capabilities",
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "processor_version": WORKER_VERSION,
        "worker_protocol_version": PROTOCOL_VERSION,
        "operations": operations,
        "readers": _reader_capabilities(probes),
        "environments": environments,
    }


def _wsl_path(path):
    path = Path(path).resolve()
    value = path.as_posix()
    if len(value) < 3 or value[1:3] != ":/" or not value[0].isalpha():
        raise ValueError("WSL critic2 paths must use a Windows drive")
    return f"/mnt/{value[0].lower()}/{value[3:]}"


def critic2_command(executable, arguments=(), *, cwd=None):
    executable = Path(executable).resolve(strict=True)
    with executable.open("rb") as stream:
        is_elf = stream.read(4) == b"\x7fELF"
    if os.name == "nt" and is_elf:
        command = ["wsl.exe"]
        if cwd is not None:
            command.extend(("--cd", _wsl_path(cwd)))
        command.extend(("--exec", _wsl_path(executable)))
        command.extend(arguments)
        return command
    return [str(executable), *arguments]


def _probe_critic2(executable):
    if not executable:
        return {"available": False, "version": None, "error": "not configured"}
    executable = Path(executable)
    if not executable.is_file():
        return {"available": False, "version": None,
                "error": "executable does not exist"}
    try:
        completed = subprocess.run(
            critic2_command(executable, ("--version",)),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "version": None,
                "error": str(error) or type(error).__name__}
    output = "\n".join(value for value in (
        completed.stdout.strip(), completed.stderr.strip()
    ) if value)
    match = re.search(r"critic2.*?version\s+([^\s]+)", output, re.IGNORECASE)
    if completed.returncode or match is None:
        return {"available": False, "version": None,
                "error": output or f"exit code {completed.returncode}"}
    return {"available": True, "version": match.group(1), "error": None}


def doctor_document(configuration=None, task_directory=None):
    configuration = configuration or load_configuration()
    capabilities = capability_document(configuration)
    checks = [{
        "id": "processor_executable",
        "status": "passed" if Path(sys.executable).is_file() else "failed",
        "message": sys.executable,
        "fix": "Reinstall the chemblender-prepare environment." if not Path(sys.executable).is_file() else None,
    }]
    for environment in capabilities["environments"]:
        if environment["name"] != "current" and not environment["configured"]:
            status = "warning"
        else:
            status = "passed" if environment["available"] else "failed"
        checks.append({
            "id": "python_" + environment["name"],
            "status": status,
            "message": environment["error"] or environment["executable"],
            "fix": (f"Configure python.{environment['name']} in the file named by "
                    f"{CONFIGURATION_ENVIRONMENT}." if status != "passed" else None),
        })
    probes = {item["name"]: item for item in capabilities["environments"]}
    dependency_groups = (
        ("current", ("numpy",), True),
        ("wavefunction", ("qc-gbasis", "qc-iodata"), True),
        ("scientific", ("ase", "cclib", "pymatgen-core", "phonopy"), True),
        ("fermi", ("pyprocar",), True),
        ("current", ("rdkit", "gemmi"), False),
    )
    for environment, required, routed in dependency_groups:
        versions = probes[environment]["versions"]
        missing = [name for name in required if name not in versions]
        configured = environment == "current" or environment in configuration["python"]
        if missing and routed and configured:
            status = "failed"
        elif missing:
            status = "warning"
        else:
            status = "passed"
        name = "formats" if not routed else environment
        checks.append({
            "id": "dependencies_" + name,
            "status": status,
            "message": ("missing " + ", ".join(missing) if missing else
                        ", ".join(f"{item}={versions[item]}" for item in required)),
            "fix": (f"Install the documented {name} dependencies in the configured environment."
                    if missing else None),
        })
    owned = None
    try:
        if task_directory is None:
            owned = TemporaryDirectory(prefix="chemblender-doctor-")
            directory = Path(owned.name)
        else:
            directory = Path(task_directory).resolve(strict=True)
        with NamedTemporaryFile(prefix="write-probe-", dir=directory, delete=True):
            pass
        task_check = {"id": "task_directory", "status": "passed",
                      "message": str(directory), "fix": None}
    except OSError as error:
        task_check = {"id": "task_directory", "status": "failed",
                      "message": str(error) or type(error).__name__,
                      "fix": "Choose an existing writable task directory."}
    finally:
        if owned is not None:
            owned.cleanup()
    checks.append(task_check)
    critic2 = _probe_critic2(configuration["critic2"])
    checks.append({
        "id": "critic2",
        "status": "passed" if critic2["available"] else "warning",
        "message": critic2["version"] or critic2["error"],
        "fix": (None if critic2["available"] else
                f"Configure an absolute critic2 path in {CONFIGURATION_ENVIRONMENT}."),
    })
    return {
        "schema_name": "chemblender_prepare_doctor",
        "schema_version": "1",
        "status": "failed" if any(item["status"] == "failed" for item in checks) else "passed",
        "checks": checks,
    }


def run_worker(request_path, result_path, cancel_path=None, configuration=None):
    configuration = configuration or load_configuration()
    request = read_request(request_path)
    environment = request_environment(request)
    executable = _route_executable(configuration, environment)
    result_path = Path(result_path)
    if executable is None:
        result = WorkerResult(
            request.request_id,
            WorkerStatus.ERROR,
            error=WorkerError("environment_unavailable",
                              f"{environment} Python is not configured"),
        )
        write_result(result_path, result)
        return result
    if os.path.normcase(str(executable.resolve())) == os.path.normcase(
        str(Path(sys.executable).resolve())
    ):
        from .worker.runner import default_registry, run_request
        return run_request(request_path, result_path, default_registry(),
                           cancel_path=cancel_path)
    if not executable.is_file():
        result = WorkerResult(
            request.request_id,
            WorkerStatus.ERROR,
            error=WorkerError("environment_unavailable",
                              f"configured {environment} Python does not exist"),
        )
        write_result(result_path, result)
        return result
    command = [str(executable), "-I", "-m",
               "chemblender_prepare.worker.runner",
               str(request_path), str(result_path)]
    if cancel_path is not None:
        command.extend(("--cancel-file", str(cancel_path)))
    try:
        completed = subprocess.run(command, stdin=subprocess.DEVNULL,
                                   shell=False, check=False)
    except OSError as error:
        result = WorkerResult(request.request_id, WorkerStatus.ERROR,
                              error=WorkerError("environment_unavailable",
                                                str(error) or type(error).__name__))
        write_result(result_path, result)
        return result
    if result_path.is_file():
        result = read_result(result_path)
        if result.request_id == request.request_id:
            return result
        result = WorkerResult(
            request.request_id,
            WorkerStatus.ERROR,
            error=WorkerError("result_identity_mismatch",
                              "worker result request identity does not match"),
        )
        write_result(result_path, result)
        return result
    result = WorkerResult(
        request.request_id,
        WorkerStatus.ERROR,
        error=WorkerError("environment_unavailable",
                          f"{environment} worker exited with code {completed.returncode} without a result"),
    )
    write_result(result_path, result)
    return result
