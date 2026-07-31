"""Deterministic benchmark fixtures that never materialize a large Python tuple."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path


BENCHMARK_SEED = 230


@dataclass(frozen=True, slots=True)
class BenchmarkScale:
    name: str
    structure_atoms: int
    trajectory_frames: int
    grid_shape: tuple[int, int, int]
    sdf_records: int
    seed: int = BENCHMARK_SEED


@dataclass(frozen=True, slots=True)
class GeneratedFixture:
    path: Path
    sha256: str
    record_count: int | None = None
    shape: tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True)
class TrajectoryFixture:
    path: Path
    sha256: str
    shape: tuple[int, int, int]
    array: object


BENCHMARK_SCALES = {
    "interactive": BenchmarkScale(
        "interactive", 50_000, 1_000, (128, 128, 128), 10_000
    ),
    "lazy": BenchmarkScale(
        "lazy", 250_000, 100_000, (256, 256, 256), 100_000
    ),
}


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def generate_structure_xyz(path, *, atom_count):
    """Write a deterministic XYZ structure without constructing atom tuples."""
    atom_count = _positive(atom_count, "atom_count")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{atom_count}\nChemBlender benchmark seed {BENCHMARK_SEED}\n")
        for atom in range(atom_count):
            stream.write(
                f"C {atom % 251 * 0.01:.4f} "
                f"{(atom // 251) % 251 * 0.01:.4f} "
                f"{atom // (251 * 251) * 0.01:.4f}\n"
            )
        stream.flush()
        os.fsync(stream.fileno())
    return GeneratedFixture(path, _sha256(path), record_count=atom_count)


def generate_trajectory_npy(path, *, frames, atoms=1):
    """Write frame slices through an NPY memmap and return a lazy sidecar reader."""
    frames = _positive(frames, "frames")
    atoms = _positive(atoms, "atoms")
    import numpy

    from ChemBlender.core.sidecar import LazyNpyArray, _array_content_hash

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    values = numpy.lib.format.open_memmap(
        path, mode="w+", dtype=numpy.float32, shape=(frames, atoms, 3)
    )
    atom_index = numpy.arange(atoms, dtype=numpy.float32)
    for frame in range(frames):
        values[frame, :, 0] = atom_index + frame * 0.001
        values[frame, :, 1] = atom_index % 17
        values[frame, :, 2] = frame % 19
    values.flush()
    del values
    mapped = numpy.load(path, mmap_mode="r", allow_pickle=False)
    try:
        content_hash, _contiguous = _array_content_hash(mapped)
    finally:
        mapped._mmap.close()
    shape = (frames, atoms, 3)
    return TrajectoryFixture(
        path,
        _sha256(path),
        shape,
        LazyNpyArray(path, shape, "float32", content_hash),
    )


def generate_grid_npy(path, *, shape):
    """Write a deterministic scalar grid one slab at a time."""
    shape = tuple(shape)
    if len(shape) != 3 or any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in shape
    ):
        raise ValueError("shape must contain three positive integers")
    import numpy

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    values = numpy.lib.format.open_memmap(
        path, mode="w+", dtype=numpy.float32, shape=shape
    )
    y = numpy.arange(shape[1], dtype=numpy.float32)[:, None]
    z = numpy.arange(shape[2], dtype=numpy.float32)[None, :]
    for x in range(shape[0]):
        values[x] = ((x + y + z + BENCHMARK_SEED) % 97) / 96.0
    values.flush()
    del values
    return GeneratedFixture(path, _sha256(path), shape=shape)


def generate_sdf_fixture(path, *, record_count):
    """Write valid one-atom SDF records as a stream for the existing indexer."""
    record_count = _positive(record_count, "record_count")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as stream:
        for index in range(record_count):
            stream.write(
                f"benchmark-{index}\nChemBlender\n\n"
                "  1  0  0  0  0  0  0  0  0  0  0  0 V2000\n"
                f"    {index % 101 * 0.01:6.4f}    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "M  END\n$$$$\n"
            )
        stream.flush()
        os.fsync(stream.fileno())
    return GeneratedFixture(path, _sha256(path), record_count=record_count)
