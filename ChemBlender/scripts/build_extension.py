#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _script_dir() -> Path:
    return Path(__file__).resolve().parent


def _extension_root() -> Path:
    return _script_dir().parent


def _manifest_path() -> Path:
    return _extension_root() / "blender_manifest.toml"


def _parse_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def _normalize_os_name(value: str) -> str:
    v = value.strip().lower()
    if v in {"windows", "win32", "cygwin", "msys"}:
        return "windows"
    if v in {"linux", "gnu/linux"}:
        return "linux"
    if v in {"darwin", "macos", "mac", "osx"}:
        return "darwin"
    return v


def _agent_system() -> str:
    return _normalize_os_name(platform.system())


def _is_wsl() -> bool:
    release = platform.release().lower()
    return "microsoft" in release or "wsl" in release


def _to_shared_windows_path(path_value: str) -> str:
    p = path_value.strip()
    if not p.startswith("/mnt/"):
        return p

    parts = p.split("/")
    if len(parts) < 4 or len(parts[2]) != 1:
        return p

    drive = parts[2].upper()
    rest = "\\".join([x for x in parts[3:] if x])
    return f"{drive}:\\{rest}" if rest else f"{drive}:\\"


def _to_wsl_path(path_value: str) -> str:
    p = path_value.strip()
    if len(p) < 3 or p[1:3] != ":\\":
        return p

    drive = p[0].lower()
    rest = p[3:].replace("\\", "/")
    return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}/"


def _normalize_local_path(path_value: str) -> Path:
    value = path_value.strip()

    if _is_wsl():
        value = _to_wsl_path(value)

    if os.name == "nt":
        value = _to_shared_windows_path(value)

    return Path(value).expanduser().resolve()


def _resolve_python_runner(user_python: str | None, project_root: Path, blender_python: str | None) -> str:
    candidates: list[str] = []

    if user_python:
        candidates.append(user_python)

    venv_python = project_root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv_python.exists():
        candidates.append(str(venv_python))

    if blender_python:
        candidates.append(blender_python)

    if shutil.which("python3"):
        candidates.append("python3")
    if shutil.which("python"):
        candidates.append("python")

    for candidate in candidates:
        normalized_candidate = candidate

        if _is_wsl():
            normalized_candidate = _to_wsl_path(normalized_candidate)

        if os.name == "nt":
            normalized_candidate = _to_shared_windows_path(normalized_candidate)

        try:
            proc = subprocess.run(
                [normalized_candidate, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        except OSError:
            continue

        if proc.returncode == 0:
            return normalized_candidate

    raise RuntimeError(
        "No usable Python interpreter found. Priority is: user specified > project .venv > Blender Python > system PATH python."
    )


def _resolve_blender_binary(
    user_blender: str | None,
    env_blender: str | None,
    mcp_binary: str | None,
    allow_path_lookup: bool,
) -> str:
    candidates: list[str] = []

    if user_blender:
        candidates.append(user_blender)
    if env_blender:
        candidates.append(env_blender)
    if mcp_binary:
        candidates.append(mcp_binary)
    if allow_path_lookup and shutil.which("blender"):
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

        if os.name == "nt":
            windows_candidate = _to_shared_windows_path(candidate)
            if windows_candidate != candidate and Path(windows_candidate).exists():
                return windows_candidate

    raise RuntimeError(
        "Unable to locate Blender executable. Provide --blender, set BLENDER_BIN, or pass MCP info JSON with binary_path."
    )


def _run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd), check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def _load_mcp_info(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = _parse_json_file(Path(path))
    return payload


def _check_system_compatibility(agent_system: str, blender_system_raw: str | None, allow_cross_system: bool) -> None:
    if not blender_system_raw:
        return

    blender_system = _normalize_os_name(blender_system_raw)
    if blender_system == agent_system:
        return

    if agent_system == "linux" and blender_system == "windows" and _is_wsl():
        if allow_cross_system:
            print("INFO: Detected WSL-to-Windows cross-system mode.")
            return
        raise RuntimeError(
            "Detected WSL-to-Windows cross-system mode. Re-run with --allow-cross-system after confirming shared-path mapping."
        )

    if allow_cross_system:
        print(f"INFO: Cross-system mode enabled ({agent_system} -> {blender_system}).")
        return

    raise RuntimeError(
        f"Build aborted: agent system is '{agent_system}' but Blender system is '{blender_system}'."
        " Re-run with --allow-cross-system after confirming path mapping."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and build Blender extension with one Python entrypoint.")
    parser.add_argument("--blender", help="Blender executable path. Highest priority for Blender binary resolution.")
    parser.add_argument("--python", dest="user_python", help="Python interpreter for validate/build orchestration.")
    parser.add_argument(
        "--mcp-info-json",
        help="JSON file from Blender MCP info. Supported keys: blender_system, binary_path, binary_path_python, extension_root.",
    )
    parser.add_argument(
        "--allow-cross-system",
        action="store_true",
        help="Allow cross-system build mode after explicit confirmation of shared-path mapping.",
    )
    parser.add_argument(
        "--no-path-lookup",
        action="store_true",
        help="Do not fallback to PATH lookup for blender command.",
    )
    parser.add_argument(
        "--valid-tags",
        help="Optional JSON file for Blender valid-tags validation.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only validate runtime compatibility and path resolution; skip build execution.",
    )

    args = parser.parse_args()

    extension_root = _extension_root()
    manifest_path = _manifest_path()
    script_dir = _script_dir()
    validate_script = script_dir / "validate_extension.py"

    if not manifest_path.exists():
        print(f"ERROR: blender_manifest.toml not found: {manifest_path}", file=sys.stderr)
        return 1

    mcp_info = _load_mcp_info(args.mcp_info_json)

    mcp_extension_root = mcp_info.get("extension_root")
    if isinstance(mcp_extension_root, str) and mcp_extension_root.strip():
        expected = _normalize_local_path(mcp_extension_root)
        if expected != extension_root:
            print(
                "ERROR: extension_root from MCP info does not match local template root.\n"
                f"- MCP extension_root: {expected}\n"
                f"- Local extension_root: {extension_root}",
                file=sys.stderr,
            )
            return 1

    agent_system = _agent_system()
    blender_system = mcp_info.get("blender_system") if isinstance(mcp_info.get("blender_system"), str) else None

    try:
        _check_system_compatibility(agent_system, blender_system, args.allow_cross_system)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    blender_python = mcp_info.get("binary_path_python") if isinstance(mcp_info.get("binary_path_python"), str) else None
    if not blender_python:
        env_blender_python = os.environ.get("BLENDER_PYTHON", "").strip()
        blender_python = env_blender_python or None

    env_blender = os.environ.get("BLENDER_BIN", "").strip() or os.environ.get("BLENDER", "").strip() or None
    mcp_binary = mcp_info.get("binary_path") if isinstance(mcp_info.get("binary_path"), str) else None

    try:
        python_runner = _resolve_python_runner(args.user_python, extension_root, blender_python)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        blender_bin = _resolve_blender_binary(
            user_blender=args.blender,
            env_blender=env_blender,
            mcp_binary=mcp_binary,
            allow_path_lookup=not args.no_path_lookup,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"INFO: extension_root={extension_root}")
    print(f"INFO: manifest={manifest_path}")
    print(f"INFO: agent_system={agent_system}")
    if blender_system:
        print(f"INFO: blender_system={_normalize_os_name(blender_system)}")
    print(f"INFO: python_runner={python_runner}")
    print(f"INFO: blender_binary={blender_bin}")

    if args.check_only:
        print("OK: compatibility and path checks passed (check-only mode)")
        return 0

    validate_cmd = [
        python_runner,
        str(validate_script),
        "--source-path",
        str(extension_root),
        "--blender",
        blender_bin,
    ]
    if args.valid_tags:
        validate_cmd.extend(["--valid-tags", args.valid_tags])

    try:
        _run(validate_cmd, cwd=extension_root)
        _run([blender_bin, "--command", "extension", "build"], cwd=extension_root)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(
            "HINT: If this is cross-system mode, provide --allow-cross-system and ensure extension_root maps to Blender host paths "
            "(for example WSL /mnt/c/... to Windows paths).",
            file=sys.stderr,
        )
        return 1

    print("OK: extension build completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
