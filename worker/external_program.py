"""Safe subprocess boundary for explicitly registered analysis adapters."""

import hashlib
import math
import re
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*")


class ExternalRunStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    INVALID_OUTPUT = "invalid_output"


def _token(value, name):
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError(f"{name} must be a lower token")


def _strings(values, name, *, nonempty=True):
    values = tuple(values)
    if any(not isinstance(value, str) or (nonempty and not value) for value in values):
        raise ValueError(f"{name} must contain strings")
    return values


@dataclass(frozen=True, slots=True)
class ExternalAdapterDescriptor:
    program_id: str
    adapter_version: str
    recipe_ids: tuple[str, ...]
    executable_names: tuple[str, ...]
    version_arguments: tuple[str, ...]
    invocation_mode: str
    license_id: str
    homepage: str
    citations: tuple[str, ...]

    def __post_init__(self):
        _token(self.program_id, "program_id")
        if not isinstance(self.adapter_version, str) or not self.adapter_version:
            raise ValueError("adapter_version must be non-empty")
        recipe_ids = _strings(self.recipe_ids, "recipe_ids")
        for recipe_id in recipe_ids:
            _token(recipe_id, "recipe_id")
        executable_names = _strings(self.executable_names, "executable_names")
        version_arguments = _strings(
            self.version_arguments, "version_arguments", nonempty=False
        )
        if self.invocation_mode not in {"argv", "stdin_script"}:
            raise ValueError("invocation_mode is not supported")
        for value, name in (
            (self.license_id, "license_id"),
            (self.homepage, "homepage"),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be non-empty")
        citations = _strings(self.citations, "citations")
        if not recipe_ids or not executable_names or not citations:
            raise ValueError("descriptor requires recipes, executables and citations")
        object.__setattr__(self, "recipe_ids", recipe_ids)
        object.__setattr__(self, "executable_names", executable_names)
        object.__setattr__(self, "version_arguments", version_arguments)
        object.__setattr__(self, "citations", citations)


CRITIC2_ADAPTER = ExternalAdapterDescriptor(
    program_id="critic2",
    adapter_version="1",
    recipe_ids=("critic2_topology", "critic2_nci"),
    executable_names=("critic2", "critic2.exe"),
    version_arguments=("--version",),
    invocation_mode="argv",
    license_id="GPL-3.0",
    homepage="https://github.com/aoterodelaroza/critic2",
    citations=("10.1016/j.cpc.2014.10.026",),
)


MULTIWFN_ADAPTER = ExternalAdapterDescriptor(
    program_id="multiwfn",
    adapter_version="1",
    recipe_ids=("multiwfn_nci", "multiwfn_population", "multiwfn_hole_electron"),
    executable_names=("Multiwfn", "Multiwfn.exe"),
    version_arguments=("-help",),
    invocation_mode="stdin_script",
    license_id="unverified",
    homepage="http://sobereva.com/multiwfn/",
    citations=("10.1002/jcc.22885", "10.1063/5.0216272"),
)


@dataclass(frozen=True, slots=True)
class ExternalInvocation:
    program_id: str
    adapter_version: str
    executable: str
    arguments: tuple[str, ...]
    expected_artifacts: tuple[str, ...]
    timeout_seconds: float
    program_version: str
    stdin_artifact: str | None = None
    input_artifacts: tuple[str, ...] = ()

    def __post_init__(self):
        _token(self.program_id, "program_id")
        if not isinstance(self.adapter_version, str) or not self.adapter_version:
            raise ValueError("adapter_version must be non-empty")
        if not isinstance(self.executable, str) or not self.executable:
            raise ValueError("executable must be non-empty")
        object.__setattr__(self, "arguments", _strings(self.arguments, "arguments", nonempty=False))
        object.__setattr__(
            self,
            "expected_artifacts",
            _strings(self.expected_artifacts, "expected_artifacts"),
        )
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0.0
        ):
            raise ValueError("timeout_seconds must be positive and finite")
        if not isinstance(self.program_version, str) or not self.program_version:
            raise ValueError("program_version must be non-empty")
        if self.stdin_artifact is not None and (
            not isinstance(self.stdin_artifact, str) or not self.stdin_artifact
        ):
            raise ValueError("stdin_artifact must be a non-empty string")
        object.__setattr__(
            self, "input_artifacts", _strings(self.input_artifacts, "input_artifacts")
        )


@dataclass(frozen=True, slots=True)
class ExternalRunRecord:
    program_id: str
    adapter_version: str
    program_version: str
    argv: tuple[str, ...]
    status: ExternalRunStatus
    return_code: int | None
    elapsed_seconds: float
    stdout_artifact: str
    stderr_artifact: str
    stdout_hash: str
    stderr_hash: str
    expected_artifacts: tuple[str, ...]
    error_code: str | None = None


def _artifact(root, value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("artifact paths must stay inside job root")
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("artifact paths must stay inside job root") from error
    return candidate


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stop(process):
    process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_external_program(invocation, job_root, *, cancel_path=None):
    if not isinstance(invocation, ExternalInvocation):
        raise TypeError("invocation must be an ExternalInvocation")
    root = Path(job_root).resolve()
    if not root.is_dir():
        raise ValueError("job_root must be an existing directory")
    expected = tuple(_artifact(root, value) for value in invocation.expected_artifacts)
    inputs = tuple(_artifact(root, value) for value in invocation.input_artifacts)
    if any(not path.is_file() for path in inputs):
        raise ValueError("input artifact is missing")
    if any(path.exists() for path in expected):
        raise ValueError("expected output already exists")
    stdin_path = (
        None if invocation.stdin_artifact is None else _artifact(root, invocation.stdin_artifact)
    )
    if stdin_path is not None and not stdin_path.is_file():
        raise ValueError("stdin artifact is missing")
    cancel_path = None if cancel_path is None else Path(cancel_path).resolve()

    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    stdout_path = logs / f"{invocation.program_id}.stdout.log"
    stderr_path = logs / f"{invocation.program_id}.stderr.log"
    started = time.monotonic()
    process = None
    status = ExternalRunStatus.ERROR
    error_code = "program_not_found"
    return_code = None
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        if cancel_path is not None and cancel_path.exists():
            status = ExternalRunStatus.CANCELLED
            error_code = "cancelled"
        else:
            stdin = None if stdin_path is None else stdin_path.open("rb")
            try:
                try:
                    process = subprocess.Popen(
                        [invocation.executable, *invocation.arguments],
                        cwd=root,
                        stdin=stdin,
                        stdout=stdout,
                        stderr=stderr,
                        shell=False,
                    )
                except OSError:
                    process = None
                if process is not None:
                    deadline = started + float(invocation.timeout_seconds)
                    while process.poll() is None:
                        if cancel_path is not None and cancel_path.exists():
                            _stop(process)
                            status = ExternalRunStatus.CANCELLED
                            error_code = "cancelled"
                            break
                        if time.monotonic() >= deadline:
                            _stop(process)
                            status = ExternalRunStatus.TIMEOUT
                            error_code = "timeout"
                            break
                        time.sleep(0.02)
                    return_code = process.returncode
                    if status not in {ExternalRunStatus.CANCELLED, ExternalRunStatus.TIMEOUT}:
                        if return_code != 0:
                            status = ExternalRunStatus.ERROR
                            error_code = "nonzero_exit"
                        elif any(not path.is_file() for path in expected):
                            status = ExternalRunStatus.INVALID_OUTPUT
                            error_code = "missing_output"
                        else:
                            status = ExternalRunStatus.SUCCESS
                            error_code = None
            finally:
                if stdin is not None:
                    stdin.close()
    elapsed = time.monotonic() - started
    return ExternalRunRecord(
        program_id=invocation.program_id,
        adapter_version=invocation.adapter_version,
        program_version=invocation.program_version,
        argv=(invocation.executable, *invocation.arguments),
        status=status,
        return_code=return_code,
        elapsed_seconds=elapsed,
        stdout_artifact=str(stdout_path.relative_to(root)).replace("\\", "/"),
        stderr_artifact=str(stderr_path.relative_to(root)).replace("\\", "/"),
        stdout_hash=_hash(stdout_path),
        stderr_hash=_hash(stderr_path),
        expected_artifacts=invocation.expected_artifacts,
        error_code=error_code,
    )


def probe_program_version(executable, arguments, *, timeout_seconds=5.0):
    arguments = _strings(arguments, "version arguments", nonempty=False)
    try:
        result = subprocess.run(
            [executable, *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("program version probe failed") from error
    output = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0 or not output:
        raise RuntimeError("program version probe failed")
    return output.splitlines()[0].strip()


def external_run_metadata(record):
    if not isinstance(record, ExternalRunRecord):
        raise TypeError("record must be an ExternalRunRecord")
    return {
        "program_id": record.program_id,
        "adapter_version": record.adapter_version,
        "program_version": record.program_version,
        "argv": list(record.argv),
        "status": record.status.value,
        "return_code": record.return_code,
        "elapsed_seconds": record.elapsed_seconds,
        "stdout_artifact": record.stdout_artifact,
        "stderr_artifact": record.stderr_artifact,
        "stdout_hash": record.stdout_hash,
        "stderr_hash": record.stderr_hash,
        "expected_artifacts": list(record.expected_artifacts),
        "error_code": record.error_code,
    }


def critic2_invocation(
    input_artifact,
    output_artifact,
    *,
    executable="critic2",
    program_version="unprobed",
    timeout_seconds=300.0,
):
    return ExternalInvocation(
        "critic2",
        CRITIC2_ADAPTER.adapter_version,
        executable,
        ("-q", "-t", "-l", input_artifact, output_artifact),
        (output_artifact,),
        timeout_seconds,
        program_version,
        None,
        (input_artifact,),
    )


def multiwfn_invocation(
    wavefunction_artifact,
    command_script_artifact,
    *,
    expected_artifacts=(),
    executable="Multiwfn",
    program_version="unprobed",
    timeout_seconds=300.0,
):
    return ExternalInvocation(
        "multiwfn",
        MULTIWFN_ADAPTER.adapter_version,
        executable,
        (wavefunction_artifact,),
        tuple(expected_artifacts),
        timeout_seconds,
        program_version,
        command_script_artifact,
        (wavefunction_artifact, command_script_artifact),
    )
