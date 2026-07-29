import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from ..core.readers import CapabilitySupport
from . import READER_API_VERSION
from .conformance import ReaderConformanceCase, run_reader_conformance_v1
from .registry import ReaderPluginRegistry


def _is_link(path):
    return path.is_symlink() or path.is_junction()


def _directory(value, name):
    path = Path(value)
    if _is_link(path):
        raise ValueError(f"{name} must not be a symlink")
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError(f"{name} must be a directory")
    return path


def _plugin(path):
    source = path / "reader.py"
    if _is_link(source) or not source.is_file():
        raise ValueError("plugin path must contain a regular reader.py")
    spec = importlib.util.spec_from_file_location(
        f"_chemblender_conformance_{source.stat().st_size}",
        source,
    )
    if spec is None or spec.loader is None:
        raise ValueError("cannot load plugin reader.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "create_plugin", None)
    if not callable(factory):
        raise ValueError("reader.py must define create_plugin(api)")
    return factory(sys.modules["ChemBlender.reader_api"])


def _cases(plugin_path, fixture_root):
    plugin = _plugin(plugin_path)
    registry = ReaderPluginRegistry((plugin,))
    descriptor = plugin.descriptor
    capabilities = tuple(
        name
        for name, support in descriptor.capabilities.items()
        if support is CapabilitySupport.SUPPORTED
    )
    fixtures = tuple(
        path
        for path in sorted(fixture_root.rglob("*"))
        if path.is_file()
        and not _is_link(path)
        and path.suffix.lower() in descriptor.extensions
        and path.resolve().is_relative_to(fixture_root)
    )
    if not fixtures:
        raise ValueError("fixtures contain no files accepted by the reader")
    return tuple(
        ReaderConformanceCase(
            f"{descriptor.reader_id}:{path.relative_to(fixture_root).as_posix()}",
            registry,
            descriptor.reader_id,
            path,
            capabilities,
        )
        for path in fixtures
    )


def _json_bytes(document):
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_atomic(path, content):
    if _is_link(path):
        raise ValueError("output must not be a symlink")
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=".conformance-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _worker(plugin_path, fixtures):
    with redirect_stdout(sys.stderr):
        cases = _cases(
            _directory(plugin_path, "plugin path"),
            _directory(fixtures, "fixtures"),
        )
        document = run_reader_conformance_v1(
            cases,
            process_isolation="subprocess",
        )
    sys.stdout.buffer.write(_json_bytes(document))
    return 0


def _parser():
    parser = argparse.ArgumentParser(
        description=f"ChemBlender Reader API {READER_API_VERSION} conformance"
    )
    parser.add_argument("--plugin-path", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--output", required=False)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args._worker:
            return _worker(args.plugin_path, args.fixtures)
        if args.output is None:
            raise ValueError("--output is required")
        plugin_path = _directory(args.plugin_path, "plugin path")
        fixtures = _directory(args.fixtures, "fixtures")
        command = (
            sys.executable,
            "-m",
            "ChemBlender.reader_api.conformance_cli",
            "--_worker",
            "--plugin-path",
            str(plugin_path),
            "--fixtures",
            str(fixtures),
        )
        completed = subprocess.run(command, capture_output=True, check=False)
        if completed.returncode != 0:
            sys.stderr.buffer.write(completed.stderr)
            return 2
        document = json.loads(completed.stdout)
        content = _json_bytes(document)
        if content != completed.stdout:
            raise ValueError("conformance worker returned non-canonical JSON")
        _write_atomic(Path(args.output), content)
        return 0 if document["passed"] else 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"conformance failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
