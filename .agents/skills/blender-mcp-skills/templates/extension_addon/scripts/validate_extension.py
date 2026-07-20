#!/usr/bin/env python3
"""Validate Blender extension metadata and run Blender extension validate."""

from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    print("ERROR: Python 3.11+ is required (tomllib unavailable).")
    sys.exit(2)


REQUIRED_MANIFEST_KEYS = (
    "id",
    "version",
    "name",
    "tagline",
    "maintainer",
    "type",
    "blender_version_min",
    "license",
)

EXTENSION_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
EXCLUDED_SCAN_DIRS = {"deps", "wheels", "scripts", ".venv", "venv", "__pycache__"}
COMMON_TOP_LEVEL_THIRD_PARTY_IMPORTS = {"requests", "yaml", "numpy", "cv2", "PIL", "scipy", "torch", "open3d"}


def _parse_version_tuple(value: str) -> tuple[int, ...] | None:
    parts = value.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def _normalize_os_name(value: str) -> str:
    v = value.strip().lower()
    if v in {"windows", "win32", "cygwin", "msys"}:
        return "windows"
    if v in {"linux", "gnu/linux"}:
        return "linux"
    if v in {"darwin", "macos", "mac", "osx"}:
        return "darwin"
    return v


def _is_wsl() -> bool:
    import platform

    release = platform.release().lower()
    return "microsoft" in release or "wsl" in release


def _to_wsl_path(path_value: str) -> str:
    p = path_value.strip()
    if len(p) < 3 or p[1:3] != ":\\":
        return p

    drive = p[0].lower()
    rest = p[3:].replace("\\", "/")
    return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}/"


def _resolve_blender_binary(user_blender: str | None) -> str:
    candidates: list[str] = []

    if user_blender:
        candidates.append(user_blender)

    env_blender = os.environ.get("BLENDER_BIN", "").strip() or os.environ.get("BLENDER", "").strip()
    if env_blender:
        candidates.append(env_blender)

    if shutil.which("blender"):
        candidates.append("blender")

    for candidate in candidates:
        if candidate == "blender":
            return candidate

        if _is_wsl():
            wsl_candidate = _to_wsl_path(candidate)
            if wsl_candidate != candidate and Path(wsl_candidate).exists():
                return wsl_candidate

        if Path(candidate).exists():
            return candidate

    raise RuntimeError(
        "Unable to locate Blender executable for extension validate. Provide --blender, set BLENDER_BIN/BLENDER, or add blender to PATH."
    )


def _discover_extension_root(source_path: str | None) -> Path:
    if source_path:
        return Path(source_path).resolve()
    return Path(__file__).resolve().parent.parent


def _read_manifest(manifest_path: Path) -> dict:
    with manifest_path.open("rb") as f:
        data = tomllib.load(f)
    if not isinstance(data, dict):
        raise ValueError("Manifest root must be a TOML table.")
    return data


def _collect_project_modules(extension_root: Path) -> set[str]:
    modules: set[str] = set()

    for path in _iter_addon_python_files(extension_root):
        rel_parts = path.relative_to(extension_root).parts
        if rel_parts[-1] == "__init__.py":
            if len(rel_parts) >= 2:
                modules.add(rel_parts[-2])
            continue
        modules.add(path.stem)

    for path in extension_root.iterdir():
        if path.is_dir() and (path / "__init__.py").exists() and path.name not in EXCLUDED_SCAN_DIRS:
            modules.add(path.name)

    return modules


def _iter_addon_python_files(extension_root: Path):
    for path in extension_root.rglob("*.py"):
        rel = path.relative_to(extension_root)
        if any(part in EXCLUDED_SCAN_DIRS for part in rel.parts):
            continue
        yield path


def _scan_absolute_import_warnings(extension_root: Path, project_modules: set[str]) -> list[str]:
    warnings: list[str] = []

    for path in _iter_addon_python_files(extension_root):
        rel = path.relative_to(extension_root)
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            warnings.append(f"{rel}: skipped import scan due to syntax error ({exc.msg}).")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if "." not in name:
                        continue
                    top = name.split(".", 1)[0]
                    if top in project_modules:
                        warnings.append(
                            f"{rel}:{node.lineno} uses project absolute import '{name}' (prefer relative imports)."
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level != 0 or not node.module:
                    continue
                top = node.module.split(".", 1)[0]
                if top in project_modules:
                    warnings.append(
                        f"{rel}:{node.lineno} uses project absolute import '{node.module}' (prefer relative imports)."
                    )

    return warnings


def _source_has_pip_install(source: str) -> bool:
    if re.search(r"\bpip\s+install\b", source):
        return True

    tokens = re.findall(r"[A-Za-z0-9_./:\\-]+", source)
    return any(token == "pip" and idx + 1 < len(tokens) and tokens[idx + 1] == "install" for idx, token in enumerate(tokens))


def _manifest_has_network_permission(manifest: dict) -> bool:
    permissions = manifest.get("permissions")
    return isinstance(permissions, dict) and bool(permissions.get("network"))


def _scan_dependency_policy_warnings(extension_root: Path, manifest: dict) -> list[str]:
    warnings: list[str] = []
    pip_install_files: list[Path] = []

    private_deps_path = extension_root / "deps" / "site-packages"
    if private_deps_path.exists():
        warnings.append("deps/site-packages exists; release builds should exclude it or use manifest wheels instead.")

    for path in _iter_addon_python_files(extension_root):
        rel = path.relative_to(extension_root)
        source = path.read_text(encoding="utf-8")

        if _source_has_pip_install(source):
            pip_install_files.append(rel)
            if "--target" not in source:
                warnings.append(f"{rel}: pip install command appears to be missing --target; use deps/site-packages.")

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            warnings.append(f"{rel}: skipped dependency policy scan due to syntax error ({exc.msg}).")
            continue

        seen_imports: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".", 1)[0]]
            else:
                continue

            for name in names:
                if name in COMMON_TOP_LEVEL_THIRD_PARTY_IMPORTS and name not in seen_imports:
                    warnings.append(
                        f"{rel}:{node.lineno} uses top-level third-party import '{name}' "
                        "(delay optional dependency imports until operator execute or business logic)."
                    )
                    seen_imports.add(name)

    if pip_install_files and not _manifest_has_network_permission(manifest):
        files = ", ".join(str(path) for path in pip_install_files)
        warnings.append(f"online pip install logic found but manifest has no network permission: {files}")

    return warnings


def _run_blender_validate(blender_bin: str, source_path: Path, valid_tags_json: str | None) -> None:
    cmd = [blender_bin, "--command", "extension", "validate"]
    if valid_tags_json:
        cmd.extend(["--valid-tags", valid_tags_json])
    cmd.append(str(source_path))

    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Blender extension validate failed with exit code {proc.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run preflight checks and Blender extension validate.")
    parser.add_argument("--source-path", help="Extension source path (default: template root).")
    parser.add_argument("--blender", help="Blender executable path.")
    parser.add_argument("--valid-tags", help="Optional JSON file for Blender valid-tags validation.")
    parser.add_argument(
        "--skip-blender-validate",
        action="store_true",
        help="Run local preflight only and skip Blender extension validate.",
    )

    args = parser.parse_args()

    extension_root = _discover_extension_root(args.source_path)
    manifest_path = extension_root / "blender_manifest.toml"

    errors: list[str] = []
    warns: list[str] = []
    manifest: dict = {}

    if not manifest_path.exists():
        errors.append("blender_manifest.toml not found in extension root.")
    else:
        try:
            manifest = _read_manifest(manifest_path)
        except Exception as exc:
            errors.append(f"failed to parse blender_manifest.toml: {exc}")
            manifest = {}

        missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in manifest]
        for key in missing:
            errors.append(f"missing required manifest key: {key}")

        extension_id = manifest.get("id")
        if isinstance(extension_id, str):
            if not EXTENSION_ID_PATTERN.fullmatch(extension_id):
                errors.append("manifest id should use lowercase letters, digits, and underscores only.")
        else:
            errors.append("manifest id must be a string.")

        extension_type = manifest.get("type")
        if extension_type != "add-on":
            errors.append("this template is add-on only; manifest type must be 'add-on'.")

        version = manifest.get("version")
        if isinstance(version, str):
            if not SEMVER_PATTERN.fullmatch(version):
                warns.append("manifest version should look like semantic version, for example 1.0.0.")
        else:
            errors.append("manifest version must be a string.")

        blender_version_min = manifest.get("blender_version_min")
        if isinstance(blender_version_min, str):
            parsed = _parse_version_tuple(blender_version_min)
            if parsed is None:
                errors.append("blender_version_min must be a dot-separated numeric string, for example 4.2.0.")
            elif parsed < (4, 2, 0):
                errors.append("default extension template requires blender_version_min >= 4.2.0.")
        else:
            errors.append("blender_version_min must be a string.")

        wheels = manifest.get("wheels")
        if wheels is not None:
            if not isinstance(wheels, list):
                errors.append("manifest key 'wheels' must be a list when present.")
            else:
                for idx, wheel in enumerate(wheels):
                    if not isinstance(wheel, str):
                        errors.append(f"wheels[{idx}] must be a string path.")
                        continue
                    wheel_path = (extension_root / wheel).resolve()
                    try:
                        wheel_path.relative_to(extension_root)
                    except ValueError:
                        errors.append(f"wheel path must stay within extension root: {wheel}")
                        continue
                    if not wheel_path.exists():
                        errors.append(f"wheel path does not exist: {wheel}")

    project_modules = _collect_project_modules(extension_root)
    warns.extend(_scan_absolute_import_warnings(extension_root, project_modules))
    warns.extend(_scan_dependency_policy_warnings(extension_root, manifest))

    print(f"OK: extension root = {extension_root}")

    if errors:
        for msg in errors:
            print(f"ERROR: {msg}")
        return 1

    print("OK: local preflight checks passed")

    if warns:
        for msg in warns:
            print(f"WARN: {msg}")
    else:
        print("OK: no local warnings")

    if args.skip_blender_validate:
        print("OK: skipped blender extension validate")
        return 0

    try:
        blender_bin = _resolve_blender_binary(args.blender)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"INFO: blender_binary={blender_bin}")

    try:
        _run_blender_validate(blender_bin, extension_root, args.valid_tags)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("OK: blender extension validate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
