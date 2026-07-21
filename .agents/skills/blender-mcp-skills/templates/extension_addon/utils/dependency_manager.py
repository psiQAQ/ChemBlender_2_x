from __future__ import annotations

import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


TSINGHUA_PYPI_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
ADDON_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DEPS_PATH = ADDON_ROOT / "deps" / "site-packages"


@dataclass(frozen=True)
class DependencySpec:
    import_name: str
    pip_requirement: str
    display_name: str


@dataclass(frozen=True)
class DependencyStatus:
    spec: DependencySpec
    installed: bool
    origin: str | None


DEPENDENCIES = (
    DependencySpec("requests", "requests==2.32.3", "Requests"),
    DependencySpec("yaml", "PyYAML==6.0.2", "PyYAML"),
)


def _private_deps_path_string() -> str:
    return str(PRIVATE_DEPS_PATH)


def add_private_deps_path() -> None:
    path = _private_deps_path_string()
    if path not in sys.path:
        sys.path.insert(0, path)


def remove_private_deps_path() -> None:
    path = _private_deps_path_string()
    sys.path[:] = [entry for entry in sys.path if entry != path]


def private_deps_path_enabled() -> bool:
    return _private_deps_path_string() in sys.path


def _find_import_origin(import_name: str) -> str | None:
    spec = importlib.util.find_spec(import_name)
    return spec.origin if spec is not None else None


def get_dependency_status() -> list[DependencyStatus]:
    statuses: list[DependencyStatus] = []
    for spec in DEPENDENCIES:
        origin = _find_import_origin(spec.import_name)
        statuses.append(DependencyStatus(spec=spec, installed=origin is not None, origin=origin))
    return statuses


def get_missing_requirements() -> list[str]:
    return [status.spec.pip_requirement for status in get_dependency_status() if not status.installed]


def all_dependencies_ready() -> bool:
    return not get_missing_requirements()


def install_missing_dependencies(
    *,
    use_tsinghua_mirror: bool = True,
    no_cache_dir: bool = False,
) -> subprocess.CompletedProcess[str] | None:
    missing_requirements = get_missing_requirements()
    if not missing_requirements:
        return None

    add_private_deps_path()
    PRIVATE_DEPS_PATH.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--target",
        _private_deps_path_string(),
    ]
    if no_cache_dir:
        cmd.append("--no-cache-dir")
    if use_tsinghua_mirror:
        cmd.extend(["-i", TSINGHUA_PYPI_INDEX_URL])
    cmd.extend(missing_requirements)

    if "--target" not in cmd:
        raise RuntimeError("Refusing to run pip install without --target.")

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    importlib.invalidate_caches()
    return result


def assert_dependencies_ready() -> None:
    missing_requirements = get_missing_requirements()
    if missing_requirements:
        raise RuntimeError("Missing Python dependencies: " + ", ".join(missing_requirements))
