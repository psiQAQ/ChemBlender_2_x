import math
from pathlib import Path

from ..Chem_data import ELEMENTS_DEFAULT
from .readers import SniffMatch, SniffResult


_ELEMENT_SYMBOLS = {
    symbol for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
}
_XYZ_SYMBOLS = _ELEMENT_SYMBOLS | {"D", "T"}


def _normalize_symbol(symbol):
    symbol = symbol.strip()
    if symbol.upper() in {"D", "T"}:
        return symbol.upper()
    return symbol[:1].upper() + symbol[1:].lower()


def _valid_atom_line(line):
    fields = line.split()
    if len(fields) < 4 or _normalize_symbol(fields[0]) not in _XYZ_SYMBOLS:
        return False
    try:
        coordinates = (float(fields[1]), float(fields[2]), float(fields[3]))
    except ValueError:
        return False
    return all(math.isfinite(value) for value in coordinates)


def sniff_xyz(source: Path, prefix: bytes) -> SniffResult:
    try:
        text = prefix.decode("utf-8-sig")
    except UnicodeDecodeError:
        return SniffResult(SniffMatch.NONE, "content is not UTF-8 XYZ text")

    lines = text.splitlines()
    if not lines:
        return SniffResult(SniffMatch.NONE, "missing atom count")
    try:
        atom_count = int(lines[0].strip())
    except ValueError:
        return SniffResult(SniffMatch.NONE, "atom count is not an integer")
    if atom_count <= 0 or len(lines) < 2:
        return SniffResult(SniffMatch.NONE, "invalid atom count or comment line")

    atom_lines = lines[2 : 2 + atom_count]
    try:
        truncated = source.stat().st_size > len(prefix)
    except OSError:
        truncated = False
    if truncated and atom_lines and not prefix.endswith((b"\n", b"\r")):
        atom_lines = atom_lines[:-1]
    if any(not _valid_atom_line(line) for line in atom_lines):
        return SniffResult(SniffMatch.NONE, "invalid XYZ atom line")
    if len(atom_lines) == atom_count:
        return SniffResult(SniffMatch.EXACT, "complete XYZ frame")
    if truncated and atom_lines:
        return SniffResult(SniffMatch.PROBABLE, "valid XYZ atom prefix")
    if not atom_lines:
        return SniffResult(SniffMatch.POSSIBLE, "XYZ count and comment prefix")
    return SniffResult(SniffMatch.NONE, "incomplete XYZ frame")
