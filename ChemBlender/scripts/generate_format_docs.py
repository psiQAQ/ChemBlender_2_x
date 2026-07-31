#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from ChemBlender.core.reader_catalog import reader_capability_document
from ChemBlender.scripts.dependency_inventory import _validate_schema


BEGIN_MARKER = "<!-- BEGIN GENERATED FORMAT CAPABILITIES -->"
END_MARKER = "<!-- END GENERATED FORMAT CAPABILITIES -->"


def _json_bytes(document):
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _dependency_document(repository_root, capability_document):
    inventory_path = repository_root / "ChemBlender" / "dependencies.toml"
    with inventory_path.open("rb") as handle:
        dependencies = _validate_schema(tomllib.load(handle))
    readers_by_module = {}
    for reader in capability_document["readers"]:
        availability = reader["availability_contract"]
        module = availability.get("module")
        if module is not None:
            readers_by_module.setdefault(module, []).append(reader["reader_id"])

    rows = []
    for dependency in sorted(
        dependencies,
        key=lambda item: item["distribution"],
    ):
        reader_ids = sorted(
            readers_by_module.get(dependency["distribution"], ())
        )
        rows.append(
            {
                "availability": {
                    "kind": (
                        "bundled_wheel"
                        if dependency["required"]
                        else "optional_wheel"
                    ),
                    "required": dependency["required"],
                    "runtime_probe": {
                        "kind": "python_module",
                        "module": dependency["distribution"],
                    },
                },
                "distribution": dependency["distribution"],
                "filename": dependency["filename"],
                "license_source": dependency["license_source"],
                "max_compressed_bytes": dependency["max_compressed_bytes"],
                "max_unpacked_bytes": dependency["max_unpacked_bytes"],
                "platform": dependency["platform"],
                "python_abi": dependency["python_abi"],
                "role": {
                    "kind": (
                        "reader_backend"
                        if reader_ids
                        else "extension_runtime"
                    ),
                    "reader_ids": reader_ids,
                },
                "sha256": dependency["sha256"],
                "source": dependency["url"],
                "spdx_license": dependency["spdx_license"],
                "version": dependency["version"],
            }
        )
    return {
        "dependencies": rows,
        "schema_name": "chemblender_dependency_capabilities",
        "schema_version": 1,
    }


def _format_table(document):
    lines = [
        "## Generated format capability reference",
        "",
        (
            f"Reader API `{document['reader_api_version']}`. Runtime availability "
            "is evaluated when a reader is selected; this table records the probe "
            "contract, not the current machine state."
        ),
        "",
        "| Reader | Import | Export | Runtime | Fixtures |",
        "| --- | --- | --- | --- | --- |",
    ]
    for reader in document["readers"]:
        names = [*reader["extensions"], *reader["basenames"]]
        source_names = ", ".join(f"`{name}`" for name in names) or "content"
        imports = ", ".join(
            f"{name}={support}"
            for name, support in reader["capabilities"].items()
        )
        export = reader["export"]
        export_text = (
            f"{export['maturity']} / {export['execution_mode']} / "
            f"{export['loss_policy']}"
        )
        availability = reader["availability_contract"]
        runtime = (
            "built-in"
            if availability["kind"] == "always"
            else f"runtime module `{availability['module']}`"
        )
        fixtures = ", ".join(reader["fixture_families"])
        lines.append(
            f"| `{reader['reader_id']}` ({source_names}) | {imports} | "
            f"{export_text} | {runtime} | {fixtures} |"
        )
    return "\n".join(lines)


def _replace_marked_section(source, generated, newline):
    block = f"{BEGIN_MARKER}{newline}{generated}{newline}{END_MARKER}"
    begin_count = source.count(BEGIN_MARKER)
    end_count = source.count(END_MARKER)
    if begin_count == end_count == 0:
        return source.rstrip() + newline * 2 + block + newline
    if begin_count != 1 or end_count != 1:
        raise ValueError("formats.md must contain one generated marker pair")
    start = source.index(BEGIN_MARKER)
    end = source.index(END_MARKER, start) + len(END_MARKER)
    return source[:start] + block + source[end:]


def render_documents(repository_root):
    repository_root = Path(repository_root)
    capabilities = reader_capability_document()
    capability_bytes = _json_bytes(capabilities)
    dependency_bytes = _json_bytes(
        _dependency_document(repository_root, capabilities)
    )
    formats_path = repository_root / "docs" / "user" / "formats.md"
    formats_source = formats_path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in formats_source else "\n"
    formats = _replace_marked_section(
        formats_source,
        _format_table(capabilities).replace("\n", newline),
        newline,
    ).encode("utf-8")
    return {
        "docs/quantum-visualization/reader-capability-matrix.json": (
            capability_bytes
        ),
        "docs/user/dependencies.json": dependency_bytes,
        "docs/user/format-capabilities.json": capability_bytes,
        "docs/user/formats.md": formats,
    }


def _write_documents(repository_root, documents):
    for relative_path, contents in documents.items():
        path = repository_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate deterministic ChemBlender format documentation."
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    try:
        documents = render_documents(args.repository_root)
        stale = [
            relative_path
            for relative_path, contents in documents.items()
            if not (args.repository_root / relative_path).is_file()
            or (args.repository_root / relative_path).read_bytes() != contents
        ]
        if args.check:
            if stale:
                print("ERROR: stale generated documentation: " + ", ".join(stale))
                return 1
        else:
            _write_documents(args.repository_root, documents)
    except (OSError, UnicodeError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("OK: generated documentation is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
