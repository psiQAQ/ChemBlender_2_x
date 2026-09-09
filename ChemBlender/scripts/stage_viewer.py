"""Stage the Viewer and the one shared core source for Blender Extensions."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil


_EXCLUDE = {"__pycache__", "scripts", "tests", "wheels", "deps"}
_FORBIDDEN_IMPORTS = {
    "chemblender_prepare", "rdkit", "gemmi", "gbasis", "iodata", "cclib",
    "scipy", "ase", "pymatgen", "phonopy", "pyprocar", "qcengine", "qcelemental",
}
_CORE_FROM = re.compile(rb"(?m)^(\s*from )cbq_core(?=[.\s])")


def _audit(path, data):
    for node in ast.walk(ast.parse(data, filename=str(path))):
        names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                 else [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level
                 else [])
        if any(name.split('.')[0] in _FORBIDDEN_IMPORTS for name in names):
            raise ValueError(f"External scientific import in Viewer: {path}:{node.lineno}")
        if isinstance(node, ast.Import) and any(name.startswith('cbq_core') for name in names):
            raise ValueError(f"Use an explicit from cbq_core import in Viewer: {path}:{node.lineno}")


def stage_viewer(source, destination, *, core_source=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    core_source = Path(core_source or source.parent / 'cbq_core').resolve()
    if not (core_source / '__init__.py').is_file():
        raise ValueError(f"Shared core source not found: {core_source}")
    if destination == source or destination.is_relative_to(source):
        raise ValueError("Viewer stage must be outside the source tree")
    destination.mkdir(parents=True, exist_ok=False)
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if any(part in _EXCLUDE for part in relative.parts) or not path.is_file():
            continue
        if path.suffix.lower() in {'.pyc', '.pyo', '.zip', '.whl', '.sha256'}:
            continue
        if path.is_symlink():
            raise ValueError(f"Linked Viewer source is not supported: {path}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        if path.suffix == '.py':
            _audit(relative, data)
            prefix = b'.' * len(relative.parts) + b'_cbq_core'
            data = _CORE_FROM.sub(lambda match: match[1] + prefix, data)
        target.write_bytes(data)
    hashes = {}
    for path in sorted(core_source.rglob('*.py')):
        if '__pycache__' in path.parts or path.is_symlink():
            continue
        relative = path.relative_to(core_source)
        target = destination / '_cbq_core' / relative
        data = path.read_bytes()
        _audit(relative, data)
        for node in ast.walk(ast.parse(data)):
            if (isinstance(node, ast.ImportFrom) and not node.level
                    and (node.module or "").split(".")[0] == "cbq_core"):
                raise ValueError(f"Shared core must use relative imports: {relative}:{node.lineno}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        digest = hashlib.sha256(data).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Shared core hash mismatch: {relative}")
        hashes[relative.as_posix()] = digest
    (destination / '_cbq_core_source.json').write_bytes(
        (json.dumps({'schema': 1, 'files': hashes}, indent=2, sort_keys=True) + '\n').encode())
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--core-source')
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    print(stage_viewer(args.source, args.destination, core_source=args.core_source))


if __name__ == '__main__':
    main()
