"""Recompute the analytic teaching density difference through public prepare CLI.

Download this script and generate_t07_density_pair.py into the same directory.
Uses only Python's standard library; the supplied prepare executable owns science.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', required=True, help='Installed chemblender-prepare executable')
    parser.add_argument('--source', required=True, type=Path, help='Fixed h2-lcao-1s-density-64.cube')
    parser.add_argument('--output', required=True, type=Path, help='New directory; existing directories are refused')
    args = parser.parse_args()
    source = args.source.resolve()
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    expected = '51fcb06343132c4b75f340aa5824434c9c622b51df7ea1ad3742920c78af66b4'
    if digest(source) != expected:
        parser.error('Source SHA-256 differs from the frozen teaching input')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    pair = root / 'h2-density-pair.cube'
    subprocess.run([sys.executable, str(Path(__file__).with_name('generate_t07_density_pair.py')),
                    str(pair), '--source', str(source)], check=True)
    assert digest(pair) == '8902b35f01edee818cd794793c152c7bfc766b8d0d08cb794077c9e0deef3b7c'

    def run(name, *arguments):
        command = [args.prepare, *map(str, arguments), '--json']
        completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        (root / (name + '.stdout.json')).write_text(completed.stdout, encoding='utf-8')
        (root / (name + '.stderr.txt')).write_text(completed.stderr, encoding='utf-8')
        (root / (name + '.argv.json')).write_text(json.dumps(command, indent=2), encoding='utf-8')
        completed.check_returncode()
        result = json.loads(completed.stdout)
        if result['status'] != 'success':
            raise RuntimeError(result)
        return result['metadata']

    first = root / 'pair-first.cbq'
    both = root / 'pair-both.cbq'
    difference = root / 'pair-difference.cbq'
    metadata = run('convert', 'convert', pair, '--reader', 'cube', '--preset', 'electron_density',
                   '--unit', 'electron_per_cubic_bohr', '--dataset-index', '0', '-o', first)
    grids = [e for e in metadata['entities'] if e['type'] == 'Grid3D']
    raw, = [e for e in grids if e['status'] == 'ambiguous' and e['shape'] == [2, 64, 64, 64]]
    left, = [e for e in grids if e['status'] == 'complete' and e['semantic_role'] == 'electron_density']
    metadata = run('resolve', 'derive', first, '--operation', 'grid.resolve_semantics', '--input', raw['id'],
                   '--parameters', json.dumps(dict(dataset_index=1, preset_id='electron_density',
                                                  value_unit='electron_per_cubic_bohr')), '-o', both)
    right, = [e for e in metadata['entities'] if e['type'] == 'Grid3D' and
              e['id'] in metadata['derived_outputs'] and e['semantic_role'] == 'electron_density']
    assert left['structure_id'] == right['structure_id']
    run('difference', 'derive', both, '--operation', 'grid.difference', '--input', left['id'],
        '--input', right['id'], '-o', difference)
    run('validate', 'validate', difference)
    assert digest(source) == expected
    print('Validated CBQ:', difference)
    print('Subtraction order: bonding density (dataset index 0) minus isolated atoms (index 1).')
    print('Import this CBQ, select Difference, and create a signed surface at 0.005.')


if __name__ == '__main__':
    main()
