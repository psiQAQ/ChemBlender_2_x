"""Global processor preference and non-blocking Worker Protocol controller."""

from dataclasses import dataclass
from enum import Enum
import json
from math import isfinite
import os
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic
from uuid import UUID, uuid4


class ProcessorError(RuntimeError):
    pass


class ProcessorState(str, Enum):
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    SUCCEEDED = "succeeded"


@dataclass(frozen=True, slots=True)
class ProcessorSnapshot:
    state: ProcessorState
    stage: str
    progress: float
    result: object | None
    error: str | None


_ACTIVE_TASKS = set()
_TERMINAL_STATES = {
    ProcessorState.CANCELLED,
    ProcessorState.FAILED,
    ProcessorState.SUCCEEDED,
}


def _processor_executable(path):
    path = Path(path)
    if not path.is_absolute():
        raise ProcessorError("processor executable path must be absolute")
    path = path.resolve()
    if not path.is_file():
        raise ProcessorError(f"processor executable does not exist: {path}")
    return path


def create_task_directory(workspace, request_id):
    if not isinstance(request_id, UUID):
        raise TypeError("request_id must be a UUID")
    workspace = Path(workspace).resolve(strict=True)
    task_directory = workspace / str(request_id)
    try:
        task_directory.mkdir()
    except FileExistsError as error:
        raise ProcessorError("processor task directory already exists") from error
    return task_directory


def _inside(path, root):
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_owned_project(task_directory, locator):
    path = Path(locator)
    if not path.is_absolute():
        raise ProcessorError("worker project locator must be absolute")
    task_root = task_directory.resolve(strict=True)
    project = path.resolve(strict=True)
    if not _inside(project, task_root) or project == task_root:
        raise ProcessorError("worker project must stay inside the task directory")
    current = project
    while current != task_root:
        if current.is_symlink() or current.is_junction():
            raise ProcessorError("worker project must not use links")
        current = current.parent
    return project


def _read_json(path):
    def reject_constant(value):
        raise ValueError(f"non-finite JSON value: {value}")

    try:
        return json.loads(Path(path).read_text(encoding="utf-8"),
                          parse_constant=reject_constant)
    except (OSError, UnicodeError, ValueError) as error:
        raise ProcessorError(f"cannot read processor output: {Path(path).name}") from error


def _capability_document(path):
    document = _read_json(path)
    fields = {
        "schema_name", "schema_version", "processor_version",
        "worker_protocol_version", "operations", "readers", "environments",
    }
    if not isinstance(document, dict) or set(document) != fields:
        raise ProcessorError("invalid processor capability fields")
    if (document["schema_name"] != "chemblender_prepare_capabilities"
            or document["schema_version"] != "1"
            or document["worker_protocol_version"] != "1"):
        raise ProcessorError("unsupported processor capability document")
    if not all(isinstance(document[name], list)
               for name in ("operations", "readers", "environments")):
        raise ProcessorError("invalid processor capability collections")
    for operation in document["operations"]:
        if (not isinstance(operation, dict)
                or set(operation) != {"operation_id", "operation_version",
                                      "environment", "available",
                                      "backend_versions", "reason"}
                or not isinstance(operation.get("operation_id"), str)
                or not isinstance(operation.get("operation_version"), str)
                or not isinstance(operation.get("environment"), str)
                or not isinstance(operation.get("available"), bool)
                or not isinstance(operation.get("backend_versions"), dict)
                or not all(isinstance(key, str) and isinstance(value, str)
                           for key, value in operation["backend_versions"].items())
                or (operation.get("reason") is not None
                    and not isinstance(operation.get("reason"), str))):
            raise ProcessorError("invalid processor operation capability")
    for environment in document["environments"]:
        if (not isinstance(environment, dict)
                or not isinstance(environment.get("name"), str)
                or not isinstance(environment.get("versions"), dict)
                or not all(isinstance(key, str) and isinstance(value, str)
                           for key, value in environment["versions"].items())):
            raise ProcessorError("invalid processor environment capability")
    return document


def _terminate_process_tree(process):
    if process.poll() is not None:
        return
    if platform.system() == "Windows":
        completed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            check=False,
        )
        if completed.returncode == 0:
            return
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


@dataclass(slots=True, eq=False)
class ProcessorTask:
    process: subprocess.Popen
    task_directory: Path
    kind: str
    request_id: UUID | None
    state: ProcessorState = ProcessorState.RUNNING
    stage: str = "starting"
    progress: float = 0.0
    result: object | None = None
    error: str | None = None
    cancel_requested_at: float | None = None

    @property
    def result_path(self):
        name = "capabilities.json" if self.kind == "capabilities" else "result.json"
        return self.task_directory / name

    @property
    def cancel_path(self):
        return self.task_directory / "cancel"

    def snapshot(self):
        return ProcessorSnapshot(
            self.state, self.stage, self.progress, self.result, self.error
        )

    def request_cancel(self):
        if self.state in _TERMINAL_STATES:
            return self.snapshot()
        self.cancel_path.touch(exist_ok=True)
        if self.cancel_requested_at is None:
            self.cancel_requested_at = monotonic()
        self.state = ProcessorState.CANCELLING
        self.stage = "cancelling"
        return self.snapshot()

    def _read_progress(self):
        path = self.task_directory / "progress.json"
        if not path.is_file():
            return
        try:
            document = _read_json(path)
            fields = set(document) if isinstance(document, dict) else set()
            if fields not in ({"completed", "total"},
                               {"stage", "completed", "total"}):
                return
            completed, total = document["completed"], document["total"]
            if (isinstance(completed, bool) or isinstance(total, bool)
                    or not isinstance(completed, (int, float))
                    or not isinstance(total, (int, float))
                    or not isfinite(completed) or not isfinite(total)
                    or total <= 0):
                return
            self.progress = max(self.progress, min(1., max(0., completed / total)))
            stage = document.get("stage")
            if isinstance(stage, str) and stage:
                self.stage = stage
        except ProcessorError:
            pass  # Progress is optional; result validation remains strict.

    def _finish(self, state, *, result=None, error=None):
        self.state = state
        self.stage = state.value
        self.progress = 1. if state is ProcessorState.SUCCEEDED else self.progress
        self.result = result
        self.error = error
        _ACTIVE_TASKS.discard(self)
        return self.snapshot()

    def poll(self):
        if self.state in _TERMINAL_STATES:
            return self.snapshot()
        self._read_progress()
        return_code = self.process.poll()
        if return_code is None:
            if (self.cancel_requested_at is not None
                    and monotonic() - self.cancel_requested_at >= 2.):
                _terminate_process_tree(self.process)
                return self._finish(ProcessorState.CANCELLED)
            if self.state is ProcessorState.RUNNING:
                self.stage = "running"
            return self.snapshot()
        if self.state is ProcessorState.CANCELLING:
            return self._finish(ProcessorState.CANCELLED)
        if self.kind == "capabilities":
            if return_code:
                message = (self.task_directory / "stderr.log").read_text(
                    encoding="utf-8", errors="replace"
                ).strip()
                return self._finish(
                    ProcessorState.FAILED,
                    error=message or f"processor exited with code {return_code}",
                )
            try:
                document = _capability_document(self.result_path)
            except ProcessorError as error:
                return self._finish(ProcessorState.FAILED, error=str(error))
            return self._finish(ProcessorState.SUCCEEDED, result=document)
        from cbq_core.worker_protocol import read_result, WorkerStatus
        if not self.result_path.is_file():
            return self._finish(
                ProcessorState.FAILED,
                error=f"processor exited with code {return_code} without a result",
            )
        try:
            result = read_result(self.result_path)
        except ValueError as error:
            return self._finish(ProcessorState.FAILED, error=str(error))
        if result.request_id != self.request_id:
            return self._finish(
                ProcessorState.FAILED,
                error="processor result request identity does not match",
            )
        if result.status is WorkerStatus.SUCCESS:
            if return_code:
                return self._finish(
                    ProcessorState.FAILED,
                    result=result,
                    error=f"processor exited with code {return_code}",
                )
            return self._finish(ProcessorState.SUCCEEDED, result=result)
        if result.status is WorkerStatus.CANCELLED:
            return self._finish(ProcessorState.CANCELLED)
        return self._finish(
            ProcessorState.FAILED,
            result=result,
            error=result.error.message,
        )

    def shutdown(self):
        if self.state not in _TERMINAL_STATES:
            self.request_cancel()
            _terminate_process_tree(self.process)
            self._finish(ProcessorState.CANCELLED)


def _launch(command, task_directory, kind, request_id=None):
    stdout_name = "capabilities.json" if kind == "capabilities" else "stdout.log"
    stdout_path = task_directory / stdout_name
    stderr_path = task_directory / "stderr.log"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=str(task_directory),
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
                shell=False,
            )
    except (OSError, ValueError) as error:
        raise ProcessorError(f"cannot start processor: {error}") from error
    task = ProcessorTask(process, task_directory, kind, request_id)
    _ACTIVE_TASKS.add(task)
    return task


def start_capability_test(executable, workspace):
    executable = _processor_executable(executable)
    workspace = Path(workspace).resolve(strict=True)
    task_directory = workspace / f"capability-{uuid4()}"
    task_directory.mkdir()
    return _launch(
        [str(executable), "capabilities", "--json"],
        task_directory,
        "capabilities",
    )


def start_worker(executable, task_directory, request):
    from cbq_core.worker_protocol import WorkerRequest, write_request
    if not isinstance(request, WorkerRequest):
        raise TypeError("request must be a WorkerRequest")
    executable = _processor_executable(executable)
    task_directory = Path(task_directory).resolve(strict=True)
    if task_directory.name != str(request.request_id):
        raise ProcessorError("task directory must match the request identity")
    _validate_owned_project(task_directory, request.project_locator)
    reserved = ("request.json", "result.json", "progress.json", "cancel",
                "stdout.log", "stderr.log")
    if any((task_directory / name).exists() for name in reserved):
        raise ProcessorError("processor task contains a reserved file")
    request_path = task_directory / "request.json"
    result_path = task_directory / "result.json"
    cancel_path = task_directory / "cancel"
    write_request(request_path, request)
    return _launch(
        [str(executable), "worker", str(request_path), str(result_path),
         "--cancel-file", str(cancel_path)],
        task_directory,
        "worker",
        request.request_id,
    )


def shutdown_processor_tasks():
    for task in tuple(_ACTIVE_TASKS):
        task.shutdown()


_PACKAGE_ROOT = __package__.rsplit(".ui", 1)[0]
_CAPABILITY_STATE = {"status": "Not tested", "detail": "", "document": None}

try:
    import bpy
    from bpy.props import StringProperty
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    def get_processor_preferences(context):
        addon = context.preferences.addons.get(_PACKAGE_ROOT)
        if addon is None:
            raise ProcessorError("ChemBlender preferences are unavailable")
        return addon.preferences


    class CHEMBLENDER_Preferences(bpy.types.AddonPreferences):
        bl_idname = _PACKAGE_ROOT

        processor_executable: StringProperty(
            name="Processor Executable",
            subtype="FILE_PATH",
            description="Absolute path to the local chemblender-prepare executable",
        )

        def draw(self, _context):
            self.layout.prop(self, "processor_executable")
            self.layout.operator("chemblender.test_processor", icon="PLAY")
            self.layout.label(text=_CAPABILITY_STATE["status"])
            if _CAPABILITY_STATE["detail"]:
                self.layout.label(text=_CAPABILITY_STATE["detail"])
            document = _CAPABILITY_STATE["document"]
            if document:
                versions = next((item["versions"] for item in document["environments"]
                                 if item["name"] == "current"), {})
                self.layout.label(text=f"RDKit: {versions.get('rdkit', 'unavailable')}")
                box = self.layout.box()
                for operation in document["operations"]:
                    state = "Ready" if operation["available"] else operation["reason"]
                    box.label(text=f"{operation['operation_id']} {operation['operation_version']}: {state}")


    class CHEMBLENDER_OT_test_processor(bpy.types.Operator):
        bl_idname = "chemblender.test_processor"
        bl_label = "Test Processor"
        bl_description = "Check the configured processor without installing anything"

        _task = None
        _temporary = None
        _timer = None

        def invoke(self, context, _event):
            try:
                preferences = get_processor_preferences(context)
                self._temporary = TemporaryDirectory(prefix="chemblender-processor-")
                self._task = start_capability_test(
                    preferences.processor_executable,
                    self._temporary.name,
                )
                self._timer = context.window_manager.event_timer_add(
                    .1, window=context.window
                )
                context.window_manager.modal_handler_add(self)
                _CAPABILITY_STATE.update(
                    status="Processor running", detail="", document=None
                )
                return {"RUNNING_MODAL"}
            except (OSError, ProcessorError) as error:
                if self._temporary is not None:
                    self._temporary.cleanup()
                    self._temporary = None
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}

        def _cleanup(self, context):
            if self._timer is not None:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            if self._temporary is not None:
                self._temporary.cleanup()
                self._temporary = None

        def modal(self, context, event):
            if event.type == "ESC":
                self._task.request_cancel()
                _CAPABILITY_STATE.update(status="Cancelling processor", detail="")
                return {"RUNNING_MODAL"}
            if event.type != "TIMER":
                return {"PASS_THROUGH"}
            snapshot = self._task.poll()
            if snapshot.state not in _TERMINAL_STATES:
                return {"RUNNING_MODAL"}
            self._cleanup(context)
            if snapshot.state is ProcessorState.SUCCEEDED:
                document = snapshot.result
                available = sum(item["available"] for item in document["operations"])
                _CAPABILITY_STATE.update(
                    status=f"Processor {document['processor_version']} ready",
                    detail=f"{available}/{len(document['operations'])} operations available",
                    document=document,
                )
                return {"FINISHED"}
            _CAPABILITY_STATE.update(
                status="Processor cancelled" if snapshot.state is ProcessorState.CANCELLED
                else "Processor check failed",
                detail=snapshot.error or "",
                document=None,
            )
            if snapshot.error:
                self.report({"ERROR"}, snapshot.error)
            return {"CANCELLED"}

        def cancel(self, context):
            if self._task is not None:
                self._task.shutdown()
            self._cleanup(context)


    def unregister():
        shutdown_processor_tasks()


__all__ = (
    "ProcessorError", "ProcessorSnapshot", "ProcessorState",
    "ProcessorTask", "create_task_directory", "shutdown_processor_tasks",
    "start_capability_test", "start_worker",
)
if bpy is not None:
    __all__ += (
        "CHEMBLENDER_Preferences", "CHEMBLENDER_OT_test_processor",
        "get_processor_preferences",
    )
