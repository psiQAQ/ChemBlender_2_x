"""Fetch or verify the reviewed input manifest using Python's standard library.

Run without flags to prepare redistributable fixtures. --fermi prepares only
the reviewed text members in the ignored project cache; --verify is read-only.
"""

import argparse
import hashlib
import io
import json
import os
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


BASE = Path(__file__).resolve().parent
ROOT = BASE.parent.parent
FERMI_TEXT_MEMBERS = frozenset({"INCAR", "KPOINTS", "POSCAR", "OUTCAR", "PROCAR", "IBZKPT"})


def checked_path(base, relative):
    """Keep manifest-controlled writes within their explicitly selected root."""
    relative = PurePosixPath(relative)
    if relative.is_absolute() or ".." in relative.parts or ":" in str(relative) or "\\" in str(relative):
        raise ValueError(f"invalid relative manifest path: {relative}")
    target = base.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(base.resolve()):
        raise ValueError(f"manifest path escapes its root: {relative}")
    return target


def validate(data, record):
    if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ValueError(f"byte count / SHA-256 mismatch: {record.get('path', record.get('url'))}")
    return data


def fetch(record):
    if not record["url"].startswith("https://"):
        raise ValueError("source URL must use HTTPS")
    request = urllib.request.Request(record["url"], headers={"User-Agent": "ChemBlender-scientific-fixtures/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return validate(response.read(record["bytes"] + 1), record)


def publish(target, data):
    """Publish exact bytes without replacing a conflicting user file."""
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError(f"existing file differs; preserving it: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".input-", delete=False) as handle:
            staging = Path(handle.name)
            handle.write(data)
        os.replace(staging, target)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


def prepare_file(record, *, verify):
    target = checked_path(BASE, record["path"])
    if target.exists() or verify:
        validate(target.read_bytes(), record)
        return
    submodule = record.get("submodule")
    checkout = checked_path(ROOT, submodule) if submodule else None
    if checkout is not None and (checkout / ".git").is_file():
        data = subprocess.check_output(["git", "-C", str(checkout), "show", f"{record['commit']}:{record['upstream_path']}"])
        validate(data, record)
    else:
        data = fetch(record)
    publish(target, data)


def prepare_fermi(record, *, verify):
    cache = checked_path(ROOT, record["cache_directory"])
    if cache != ROOT / ".agents/cache/scientific-visualization/fermi":
        raise ValueError("Fermi data must remain in the reviewed project cache")
    archive = checked_path(cache, record["archive_name"])
    data = validate(archive.read_bytes(), record) if archive.exists() or verify else fetch(record)
    if not verify:
        publish(archive, data)
    members = record["members"]
    if {member["path"] for member in members} != FERMI_TEXT_MEMBERS or len(members) != len(FERMI_TEXT_MEMBERS):
        raise ValueError("Fermi member selection differs from the reviewed text allowlist")
    with zipfile.ZipFile(io.BytesIO(data)) as container:
        for member in members:
            path = checked_path(cache, member["path"])
            info = container.getinfo(member["path"])
            if info.file_size != member["bytes"] or info.file_size > 4_000_000:
                raise ValueError("unexpected Fermi member size")
            payload = validate(container.read(info), member)
            payload.decode("utf-8")
            if verify:
                validate(path.read_bytes(), member)
            else:
                publish(path, payload)
    card = record["dataset_card"]
    target = checked_path(cache, card["path"])
    if target.exists() or verify:
        validate(target.read_bytes(), card)
    else:
        publish(target, fetch(card))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="verify existing bytes without writes or network")
    parser.add_argument("--fermi", action="store_true", help="include the private cache-only Fermi input")
    arguments = parser.parse_args()
    manifest = json.loads((BASE / "input-manifest.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] != 1:
        raise ValueError("unsupported fixture manifest version")
    for record in manifest["files"]:
        prepare_file(record, verify=arguments.verify)
    if arguments.fermi:
        prepare_fermi(manifest["fermi_cache"], verify=arguments.verify)
    print(f"Verified {len(manifest['files'])} fixture/license files" + (" and cache-only Fermi input" if arguments.fermi else ""))


if __name__ == "__main__":
    main()
