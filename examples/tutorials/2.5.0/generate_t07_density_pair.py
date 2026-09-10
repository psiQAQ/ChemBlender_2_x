"""Write a teaching Cube pair; neither density is an HF/DFT result."""
import argparse
import hashlib
import math
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2] / 'user-workflows/inputs/cube/h2-lcao-1s-density-64.cube'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == '51fcb06343132c4b75f340aa5824434c9c622b51df7ea1ad3742920c78af66b4'
    lines = source.read_text(encoding='utf-8').splitlines()
    bonding = [float(x) for line in lines[8:] for x in line.split()]
    assert len(bonding) == 64 ** 3
    step = float(lines[3].split()[1])
    header = ['Analytic H2 teaching density pair: bonding and isolated atoms',
              'Not HF/DFT; bohr and electron_per_cubic_bohr; dataset IDs 1,2',
              lines[2].replace('    2 ', '   -2 ', 1), *lines[3:8], '    2    1    2']
    with args.output.open('x', encoding='ascii', newline='\n') as stream:
        stream.write('\n'.join(header) + '\n')
        row = []
        for i, rho in enumerate(bonding):
            x, y, z = (-6 + step * k for k in (i // 4096, (i // 64) % 64, i % 64))
            isolated = sum(math.exp(-2 * math.sqrt(x*x + y*y + (z-center)**2)) / math.pi
                           for center in (-0.7, 0.7))
            row.extend((format(rho, '.12e'), format(isolated, '.12e')))
            if len(row) == 6:
                stream.write(' '.join(row) + '\n')
                row.clear()
        if row:
            stream.write(' '.join(row) + '\n')
    print(hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
