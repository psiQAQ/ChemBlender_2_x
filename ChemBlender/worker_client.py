import subprocess
from dataclasses import dataclass
from pathlib import Path

class WorkerProcessError(RuntimeError):
    pass


@dataclass(slots=True)
class WorkerHandle:
    process: subprocess.Popen
    request_path: Path
    result_path: Path
    cancel_path: Path
    stdout_path: Path
    stderr_path: Path
    _stdout: object
    _stderr: object

    def request_cancel(self):
        self.cancel_path.touch(exist_ok=True)

    def poll(self):
        from .core.worker_protocol import read_result

        return_code = self.process.poll()
        if self.result_path.is_file():
            self._close_logs()
            return read_result(self.result_path)
        if return_code is None:
            return None
        self._close_logs()
        raise WorkerProcessError(
            f"worker exited with code {return_code} without a result; "
            f"see {self.stderr_path}"
        )

    def wait(self, timeout=None):
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise WorkerProcessError("worker did not finish before timeout") from error
        return self.poll()

    def terminate(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait()
        self._close_logs()

    def _close_logs(self):
        if not self._stdout.closed:
            self._stdout.close()
        if not self._stderr.closed:
            self._stderr.close()


def start_worker(
    request,
    workspace,
    *,
    python_executable,
    module="worker.runner",
    working_directory=None,
):
    from .core.worker_protocol import WorkerRequest, write_request

    if not isinstance(request, WorkerRequest):
        raise TypeError("request must be a WorkerRequest")
    executable = Path(python_executable)
    if not executable.is_file():
        raise WorkerProcessError(f"worker Python does not exist: {executable}")
    task_directory = Path(workspace) / str(request.request_id)
    try:
        task_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise WorkerProcessError("worker request directory already exists") from error
    request_path = task_directory / "request.json"
    result_path = task_directory / "result.json"
    cancel_path = task_directory / "cancel"
    stdout_path = task_directory / "stdout.log"
    stderr_path = task_directory / "stderr.log"
    write_request(request_path, request)
    stdout = stdout_path.open("wb")
    stderr = stderr_path.open("wb")
    command = [
        str(executable),
        "-m",
        module,
        str(request_path),
        str(result_path),
        "--cancel-file",
        str(cancel_path),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(
            command,
            cwd=None if working_directory is None else str(working_directory),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )
    except Exception:
        stdout.close()
        stderr.close()
        raise
    return WorkerHandle(
        process,
        request_path,
        result_path,
        cancel_path,
        stdout_path,
        stderr_path,
        stdout,
        stderr,
    )
