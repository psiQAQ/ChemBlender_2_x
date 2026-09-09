"""Atomic UTF-8 output shared by scientific and sampled display exports."""
from dataclasses import dataclass
import os
from pathlib import Path
from .atomic_paths import short_sibling_temporary_path


@dataclass(frozen=True, slots=True)
class ExportReportEntry:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ExportReport:
    format: str
    written: bool
    frame_count: int
    requires_confirmation: bool
    entries: tuple[ExportReportEntry, ...] = ()
    missing_value_token: str | None = None


class ExportCancelled(RuntimeError):
    pass


def _cancelled(is_cancelled):
    if is_cancelled is None:
        return False
    if not callable(is_cancelled):
        raise TypeError("is_cancelled must be callable")
    value = is_cancelled()
    if type(value) is not bool:
        raise TypeError("is_cancelled must return bool")
    return value


def atomic_write_chunks(destination, chunks, *, is_cancelled=None):
    """Write UTF-8 chunks atomically with cooperative cancellation."""
    destination = Path(destination)
    if _cancelled(is_cancelled):
        raise ExportCancelled("export cancelled")
    temporary = short_sibling_temporary_path(destination)
    try:
        with temporary.open("xb") as stream:
            for chunk in chunks:
                if _cancelled(is_cancelled):
                    raise ExportCancelled("export cancelled")
                stream.write(chunk.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
            if _cancelled(is_cancelled):
                raise ExportCancelled("export cancelled")
        os.replace(temporary, destination)
    except BaseException as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as cleanup_error:
            error.add_note(f"temporary export cleanup failed: {cleanup_error}")
        raise
