from pathlib import Path
from uuid import uuid4


def short_sibling_temporary_path(destination, *, suffix=".tmp") -> Path:
    destination = Path(destination)
    if not isinstance(suffix, str):
        raise TypeError("suffix must be a string")
    if "\0" in suffix or "/" in suffix or "\\" in suffix:
        raise ValueError("suffix must not contain path separators or NUL")
    if len(suffix) > 15:
        raise ValueError("suffix is too long")
    return destination.with_name(f".{uuid4().hex}{suffix}")
