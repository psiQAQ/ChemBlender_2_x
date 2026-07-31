"""Small Blender-independent state for cancellable UI work."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from threading import Event, RLock, Thread


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    SUCCEEDED = "succeeded"


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    state: TaskState
    progress: float
    stage: str
    error: BaseException | None
    result: object | None


class Task:
    """Thread-safe state machine; callers keep Blender mutations outside it."""

    def __init__(self):
        self._lock = RLock()
        self._state = TaskState.PENDING
        self._progress = 0.0
        self._stage = "pending"
        self._error = None
        self._result = None

    def snapshot(self):
        with self._lock:
            return TaskSnapshot(
                self._state,
                self._progress,
                self._stage,
                self._error,
                self._result,
            )

    def _require(self, *states):
        if self._state not in states:
            expected = ", ".join(state.value for state in states)
            raise RuntimeError(
                f"task is {self._state.value}; expected {expected}"
            )

    @staticmethod
    def _stage_text(stage):
        if not isinstance(stage, str) or not stage:
            raise ValueError("stage must be a non-empty string")
        return stage

    @staticmethod
    def _progress_value(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("progress must be a number")
        value = float(value)
        if not isfinite(value):
            raise ValueError("progress must be finite")
        if not 0.0 <= value <= 1.0:
            raise ValueError("progress must be within 0..1")
        return value

    def start(self, stage):
        with self._lock:
            self._require(TaskState.PENDING)
            self._state = TaskState.RUNNING
            self._stage = self._stage_text(stage)
            return self.snapshot()

    def progress(self, stage, value):
        with self._lock:
            if self._state is TaskState.CANCELLING:
                return self.snapshot()
            self._require(TaskState.RUNNING)
            value = self._progress_value(value)
            if value < self._progress:
                raise ValueError("progress must be monotonic")
            self._progress = value
            self._stage = self._stage_text(stage)
            return self.snapshot()

    def progress_event(self, stage, completed, total):
        if isinstance(total, bool) or not isinstance(total, (int, float)):
            raise TypeError("progress total must be a number")
        if not isfinite(total) or total <= 0:
            raise ValueError("progress total must be positive and finite")
        return self.progress(stage, completed / total)

    def request_cancel(self, stage="cancelling"):
        with self._lock:
            if self._state is TaskState.PENDING:
                self._state = TaskState.CANCELLED
                self._stage = "cancelled"
            elif self._state is TaskState.RUNNING:
                self._state = TaskState.CANCELLING
                self._stage = self._stage_text(stage)
            elif self._state not in (TaskState.CANCELLING, TaskState.CANCELLED):
                self._require(TaskState.RUNNING)
            return self.snapshot()

    def cancel(self, stage="cancelled"):
        with self._lock:
            if self._state is TaskState.PENDING:
                self._state = TaskState.CANCELLED
            else:
                self._require(TaskState.CANCELLING)
                self._state = TaskState.CANCELLED
            self._stage = self._stage_text(stage)
            return self.snapshot()

    def succeed(self, stage):
        with self._lock:
            self._require(TaskState.RUNNING)
            self._state = TaskState.SUCCEEDED
            self._progress = 1.0
            self._stage = self._stage_text(stage)
            return self.snapshot()

    def complete(self, result, stage="complete"):
        """Atomically publish a result, or discard it if cancellation won.

        Repeated completion after a completed/cancelled task is idempotent;
        completion after a failed task remains an invalid transition.
        """
        with self._lock:
            if self._state is TaskState.RUNNING:
                self._state = TaskState.SUCCEEDED
                self._progress = 1.0
                self._stage = self._stage_text(stage)
                self._result = result
            elif self._state is TaskState.CANCELLING:
                self._state = TaskState.CANCELLED
                self._stage = "cancelled"
                self._result = None
            elif self._state not in (
                TaskState.CANCELLED,
                TaskState.SUCCEEDED,
            ):
                self._require(TaskState.RUNNING, TaskState.CANCELLING)
            return self.snapshot()

    def fail(self, error, stage="failed"):
        if not isinstance(error, BaseException):
            raise TypeError("error must be a BaseException")
        with self._lock:
            self._require(TaskState.RUNNING, TaskState.CANCELLING)
            self._state = TaskState.FAILED
            self._stage = self._stage_text(stage)
            self._error = error
            return self.snapshot()

    def is_cancelled(self):
        with self._lock:
            return self._state in (TaskState.CANCELLING, TaskState.CANCELLED)


class TaskProgressAdapter:
    """Map nested ``stage, completed, total`` events to Task progress."""

    def __init__(self, task):
        if type(task) is not Task:
            raise TypeError("task must be a Task")
        self._task = task
        self._lock = RLock()
        self._stage = None
        self._base = 0.0
        self._span = 0.5

    def __call__(self, stage, completed, total):
        if isinstance(completed, bool) or not isinstance(
            completed, (int, float)
        ):
            raise TypeError("progress completed must be a number")
        if isinstance(total, bool) or not isinstance(total, (int, float)):
            raise TypeError("progress total must be a number")
        if not isfinite(total) or total <= 0:
            raise ValueError("progress total must be positive and finite")
        fraction = Task._progress_value(completed / total)
        with self._lock:
            snapshot = self._task.snapshot()
            if snapshot.state in (TaskState.CANCELLING, TaskState.CANCELLED):
                return snapshot
            if stage != self._stage:
                self._stage = Task._stage_text(stage)
                self._base = snapshot.progress
                self._span = (1.0 - self._base) / 2
            return self._task.progress(
                stage,
                self._base + self._span * fraction,
            )


class TaskWorker:
    """Run a pure callback off the UI thread and expose its Task state."""

    def __init__(self, task, work):
        if type(task) is not Task:
            raise TypeError("task must be a Task")
        if not callable(work):
            raise TypeError("work must be callable")
        self.task = task
        self._work = work
        self._done = Event()
        self._thread = Thread(target=self._run, daemon=True)
        self._started = False
        self.result = None
        self.error = None

    @property
    def done(self):
        return self._done.is_set()

    def start(self, stage):
        if self._started:
            raise RuntimeError("task worker has already started")
        self.task.start(stage)
        self._thread.start()
        self._started = True

    def _run(self):
        try:
            result = self._work(self.task.is_cancelled, self.task.progress)
        except BaseException as error:
            self.error = error
            self.task.fail(error)
        else:
            snapshot = self.task.complete(result)
            self.result = (
                snapshot.result
                if snapshot.state is TaskState.SUCCEEDED
                else None
            )
        finally:
            self._done.set()

    def join(self, timeout=None):
        if not self._started:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def request_cancel(self):
        try:
            return self.task.request_cancel()
        except RuntimeError:
            return self.task.snapshot()

    def raise_if_failed(self):
        if self.error is not None:
            raise self.error


__all__ = (
    "Task",
    "TaskProgressAdapter",
    "TaskSnapshot",
    "TaskState",
    "TaskWorker",
)
