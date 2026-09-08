"""Strict VASP text bundle to a neutral, provenance-backed Fermi surface."""

import hashlib
import json
import re
from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from .model import (
    ArrayData, BandStructure, DatasetStatus, EnergyReference, ImportBatch,
    IssueKind, ParserIssue, ParserReport, PeriodicSiteData, ProvenanceRecord, Structure,
)
from .pyprocar_adapter import _faces, _package_version, adapt_pyprocar_fermi_surface


ADAPTER_VERSION = "1"
REQUIRED_FILES = frozenset({"INCAR", "KPOINTS", "POSCAR", "OUTCAR", "PROCAR"})
OPTIONAL_FILES = frozenset({"IBZKPT"})
PYPROCAR_SOURCE_COMMIT = "4a2ec9049af78fdd35b6214eef68fe40e5f356ed"


def _check_cancel(is_cancelled):
    if is_cancelled is not None and is_cancelled():
        raise CancelledError("Fermi-surface evaluation cancelled")


def _real(values, name):
    import numpy

    values = numpy.asarray(values)
    if numpy.iscomplexobj(values) or not numpy.all(numpy.isfinite(values)):
        raise ValueError(f"{name} must contain finite real values")
    return values.astype(float)


def _mesh_spec(text):
    import numpy

    lines = text.splitlines()
    if len(lines) < 4 or lines[1].strip() != "0" or not lines[2].strip().lower().startswith(("g", "m")):
        raise ValueError("Fermi surfaces require automatic 3D Gamma/Monkhorst mesh KPOINTS, not a line path")
    shape = tuple(int(value) for value in lines[3].split())
    if len(shape) != 3 or min(shape) < 3:
        raise ValueError("Fermi mesh requires at least three points on every reciprocal axis")
    shift = _real([float(value) for value in lines[4].split()] if len(lines) > 4 and lines[4].strip() else [0., 0., 0.], "mesh shift")
    if shift.shape != (3,):
        raise ValueError("KPOINTS mesh shift must contain three values")
    offset = shift
    if lines[2].strip().lower().startswith("m"):
        offset = offset + (1 - numpy.asarray(shape)) / 2
    return shape, offset % 1


def _incar_options(text):
    options = {}
    for line in text.splitlines():
        for item in re.split(r"[;]", re.split(r"[!#]", line, maxsplit=1)[0]):
            if "=" in item:
                key, value = item.split("=", 1)
                options[key.strip().upper()] = value.strip()
    return options


def _preflight(texts):
    shape, offset = _mesh_spec(texts["KPOINTS"])
    lines = texts["POSCAR"].splitlines()
    if len(lines) < 8 or len(lines[1].split()) != 1 or float(lines[1]) <= 0:
        raise ValueError("POSCAR requires one positive scale and explicit element symbols")
    from ..Chem_data import ELEMENTS_DEFAULT

    if not lines[5].split() or any(symbol not in ELEMENTS_DEFAULT for symbol in lines[5].split()):
        raise ValueError("POSCAR requires explicit element symbols; POTCAR lookup is disabled")
    mode = 8 if lines[7].strip().lower().startswith("s") else 7
    if len(lines) <= mode or not lines[mode].strip().lower().startswith("d"):
        raise ValueError("the pinned PyProcar POSCAR adapter currently requires Direct coordinates")
    body = texts["PROCAR"].split("\n", 2)[-1]
    if re.search(r"\*+|(\d)-(\d)|(\.\d{8})(\d{2}\.)", body):
        raise ValueError("PROCAR needs upstream repair; silent repair and placeholder energies are disabled")
    options = _incar_options(texts["INCAR"])
    for name in ("LNONCOLLINEAR", "LSORBIT"):
        if options.get(name, "F").strip(".").upper().startswith("T") or re.search(rf"\b{name}\s*=\s*\.?T", texts["OUTCAR"], re.I):
            raise ValueError("noncollinear/spinor Fermi calculations are not supported")
    return shape, offset, options


def _readers():
    from pyprocar.io.vasp import Outcar, Poscar, Procar

    return Outcar, Poscar, Procar


def _validate_run_identity(text, poscar, procar):
    """Match the separate text files before assigning a structure to the mesh."""
    import numpy

    counts = re.findall(r"ions per type\s*=\s*([\d\s]+)", text)
    species = re.findall(r"VRHFIN\s*=\s*([A-Z][a-z]?)\s*:", text)
    if not counts or not species:
        raise ValueError("OUTCAR must declare element identities and ions per type")
    counts = [int(value) for value in counts[-1].split()]
    if len(species) != len(counts) or tuple(symbol for symbol, count in zip(species, counts) for _ in range(count)) != tuple(poscar.atoms):
        raise ValueError("POSCAR and OUTCAR element identities do not match")
    dimensions = re.findall(r"NKPTS\s*=\s*(\d+)[^\n]*NBANDS\s*=\s*(\d+)", text)
    if not dimensions or tuple(map(int, dimensions[-1])) != tuple(procar.bands.shape[:2]):
        raise ValueError("OUTCAR and PROCAR kpoint/band dimensions do not match")
    spins = re.findall(r"\bISPIN\s*=\s*(\d+)", text)
    if not spins or int(spins[-1]) != procar.bands.shape[-1]:
        raise ValueError("OUTCAR and PROCAR spin dimensions do not match")
    matches = list(re.finditer(r"position of ions in fractional coordinates \(direct lattice\)[ \t]*\r?\n", text, re.I))
    if not matches:
        raise ValueError("OUTCAR must declare fractional atom positions")
    for match in matches:
        rows = text[match.end():].splitlines()[:len(poscar.atoms)]
        positions = _real([[float(value) for value in row.split()[:3]] for row in rows], "OUTCAR positions")
        if positions.shape != poscar.coordinates.shape:
            raise ValueError("OUTCAR fractional atom positions are incomplete")
        difference = positions - poscar.coordinates
        if not numpy.allclose(difference - numpy.rint(difference), 0, atol=2e-6, rtol=0):
            raise ValueError("POSCAR and OUTCAR atom positions do not match; use a static run")


def _full_mesh(kpoints, energies, shape, offset, rotations, reciprocal, is_cancelled=None):
    """Expand only declared run symmetries; retain signed k coordinates and band IDs."""
    import numpy

    kpoints, energies = _real(kpoints, "kpoints"), _real(energies, "band energies")
    if kpoints.ndim != 2 or kpoints.shape[1] != 3 or energies.ndim != 3 or energies.shape[0] != len(kpoints) or energies.shape[2] not in (1, 2):
        raise ValueError("PROCAR must contain matching (kpoint, 3) and (kpoint, band, spin) arrays")
    count = int(numpy.prod(shape))
    if count > 2_000_000 or count * energies.shape[1] * energies.shape[2] > 100_000_000:
        raise ValueError("Fermi mesh exceeds the worker's explicit array limit")
    size = numpy.asarray(shape)

    def indices(points):
        scaled = points * size - offset
        rounded = numpy.rint(scaled)
        if not numpy.allclose(scaled, rounded, atol=2e-6, rtol=0):
            raise ValueError("PROCAR points do not lie on the declared uniform KPOINTS mesh")
        return numpy.ravel_multi_index((rounded.astype(int) % size).T, shape)

    original = indices(kpoints)
    if len(numpy.unique(original)) != len(original):
        raise ValueError("PROCAR has duplicate periodic kpoints")
    expanded = numpy.empty((count, *energies.shape[1:]), dtype=float)
    seen = numpy.zeros(count, dtype=bool)
    expanded[original], seen[original] = energies, True
    used = 0
    if not numpy.all(seen):
        if rotations is None:
            raise ValueError("incomplete 3D mesh; OUTCAR symmetry operations are required")
        rotations = _real(rotations, "OUTCAR rotations")
        metric = reciprocal @ reciprocal.T
        if rotations.ndim != 3 or rotations.shape[1:] != (3, 3):
            raise ValueError("OUTCAR rotations must be 3x3 matrices")
        for rotation in rotations:
            _check_cancel(is_cancelled)
            if not numpy.isclose(abs(numpy.linalg.det(rotation)), 1., atol=1e-6) or not numpy.allclose(rotation.T @ metric @ rotation, metric, atol=1e-6, rtol=1e-5):
                raise ValueError("OUTCAR rotation does not preserve the reciprocal lattice")
            target = indices(kpoints @ rotation.T)
            if len(numpy.unique(target)) != len(target):
                raise ValueError("OUTCAR rotation collapses distinct mesh points")
            overlap = seen[target]
            if not numpy.allclose(expanded[target[overlap]], energies[overlap], atol=2e-5, rtol=0):
                raise ValueError("symmetry-related band energies disagree; cannot expand this calculation")
            expanded[target], seen[target] = energies, True
            used += 1
    if not numpy.all(seen):
        raise ValueError(f"incomplete 3D mesh after symmetry: {int(seen.sum())}/{count} points")
    nodes = numpy.indices(shape).reshape(3, -1).T
    points = ((nodes + offset) / size + .5) % 1 - .5
    order = numpy.lexsort((points[:, 2], points[:, 1], points[:, 0]))
    return points[order], expanded[order], used


def _marching_coordinates(matrix, origin, spacing, padding, isovalue, marching_cubes):
    """Marching-cubes index coordinates use the grid origin, never the surface bbox."""
    import numpy

    padded = numpy.pad(matrix, [(int(n), int(n)) for n in padding], mode="wrap")
    vertices, faces, normals, values = marching_cubes(padded, isovalue)
    vertices = (numpy.asarray(vertices, dtype=float) - padding) * spacing + origin
    return vertices, faces, normals, values


def _surface_backend():
    from pyprocar.core.brillouin_zone import BrillouinZone
    from pyprocar.core.isosurface import Isosurface, measure

    class LocatedIsosurface(Isosurface):
        def _get_isosurface(self, interp_factor=1):
            # The pinned upstream implementation recenters the extracted bbox.
            # Override only that step and allow numeric failures to propagate.
            return _marching_coordinates(
                self.V_matrix, [self.X[0], self.Y[0], self.Z[0]], self.dxyz,
                self.padding, self.isovalue, measure.marching_cubes,
            )

    return LocatedIsosurface, BrillouinZone


def parse_vasp_fermi(source_directory, *, spin_index=0, interpolation_factor=1,
                     is_cancelled=None, progress=None):
    """Read canonical VASP text files; no cache pickle, POTCAR or implicit energy shift.

    Progress reports completed/total bands. Cancellation is checked at parser,
    symmetry and band boundaries. No project state is changed by this function.
    """
    import numpy

    if type(spin_index) is not int or spin_index not in (0, 1):
        raise ValueError("spin_index must be 0 or 1")
    if type(interpolation_factor) is not int or interpolation_factor != 1:
        raise ValueError("interpolation_factor must be 1 until FFT coordinates are validated")
    root = Path(source_directory).resolve(strict=True)
    texts, hashes = {}, {}
    for name in sorted(REQUIRED_FILES | OPTIONAL_FILES):
        path = root / name
        if name in OPTIONAL_FILES and not path.exists():
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{name} must be a regular text file")
        if (root / (name + ".gz")).exists():
            raise ValueError(f"ambiguous {name}.gz sibling; canonical plain text is required")
        _check_cancel(is_cancelled)
        raw = path.read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        texts[name] = raw.decode("utf-8-sig")
    shape, offset, options = _preflight(texts)
    Outcar, Poscar, Procar = _readers()
    outcar = Outcar(root / "OUTCAR")
    poscar = Poscar(root / "POSCAR")
    _check_cancel(is_cancelled)
    procar = Procar(root / "PROCAR")
    _check_cancel(is_cancelled)
    lattice = _real(poscar.lattice, "POSCAR lattice")
    fractional = _real(poscar.coordinates, "POSCAR positions")
    reciprocal = 2 * numpy.pi * numpy.linalg.inv(lattice).T
    if not numpy.allclose(_real(outcar.reciprocal_lattice, "OUTCAR reciprocal lattice") * (2 * numpy.pi), reciprocal, atol=2e-5, rtol=1e-5):
        raise ValueError("POSCAR and OUTCAR lattices do not match")
    if len(poscar.atoms) != procar.ionsCount:
        raise ValueError("POSCAR and PROCAR atom counts do not match")
    _validate_run_identity(texts["OUTCAR"], poscar, procar)
    energies = _real(procar.bands, "PROCAR absolute energies")
    if energies.ndim != 3 or energies.shape[-1] != int(options.get("ISPIN", "1")):
        raise ValueError("INCAR and PROCAR spin channels do not match")
    if spin_index >= energies.shape[-1]:
        raise ValueError("requested spin channel is absent")
    efermi = float(outcar.efermi)
    if not numpy.isfinite(efermi):
        raise ValueError("OUTCAR Fermi energy must be finite")
    points, energies, rotation_count = _full_mesh(
        procar.kpoints, energies, shape, offset, outcar.rotations, reciprocal, is_cancelled,
    )
    source_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    parameters = {
        "source_files": hashes, "mesh_shape": list(shape), "mesh_offset": offset.tolist(),
        "adapter_version": ADAPTER_VERSION, "pyprocar_version": _package_version(),
        "original_kpoint_count": len(procar.kpoints), "full_kpoint_count": len(points),
        "symmetry_rotation_count": rotation_count, "spin_index": spin_index,
        "interpolation_factor": interpolation_factor, "energy_reference": "absolute",
        "fermi_energy_ev": efermi, "vasp_version": str(outcar.version),
        "incar": options, "pyprocar_source_commit": PYPROCAR_SOURCE_COMMIT,
        "coordinate_convention": "cartesian_reciprocal_2pi",
        "mesh_path": False, "isosurface_origin": "sample_grid_origin",
    }
    revision = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
    provenance_id = uuid4()
    from ..Chem_data import ELEMENTS_DEFAULT
    from .ase_adapter import _site_labels

    structure = Structure(
        id=uuid4(), revision=source_hash,
        atomic_numbers=tuple(ELEMENTS_DEFAULT[symbol][0] for symbol in poscar.atoms),
        coordinates=ArrayData(fractional @ lattice, ("atom", "xyz"), "angstrom"),
        cell=ArrayData(lattice, ("cell_vector", "xyz"), "angstrom"),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(fractional, ("atom", "xyz"), "dimensionless"),
            site_labels=_site_labels(poscar.atoms),
            occupancies=ArrayData(numpy.ones(len(poscar.atoms)), ("atom",), "dimensionless"),
            isotropic_displacements=None, anisotropic_displacements=None,
            adp_types=("none",) * len(poscar.atoms), disorder_groups=(0,) * len(poscar.atoms),
            declared_space_group_name=None, declared_space_group_number=None,
            symmetry_operations=(), cif_envelope_id=None,
        ),
    )
    band = BandStructure(
        id=uuid4(), revision=revision, semantic_role="band_structure", domain="band",
        data=ArrayData(energies.transpose(2, 0, 1), ("spin", "kpoint", "band"), "electron_volt"),
        status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(provenance_id,),
        structure_id=structure.id, occupations=None,
        kpoints=ArrayData(points, ("kpoint", "reciprocal_axis"), "dimensionless"),
        reciprocal_lattice=ArrayData(reciprocal, ("reciprocal_vector", "cartesian_axis"), "inverse_angstrom"),
        # This is a mesh, so no invented high-symmetry distance or branch.
        distances=ArrayData(numpy.zeros(len(points)), ("kpoint",), "inverse_angstrom"),
        spin_channels=("alpha",) if energies.shape[-1] == 1 else ("alpha", "beta"),
        labels=(None,) * len(points), branches=(), projections=None, orbital_labels=(),
        fermi_energy=efermi, energy_reference=EnergyReference.ABSOLUTE,
    )
    selected = energies[:, :, spin_index]
    crossing = numpy.flatnonzero((selected.min(axis=0) < efermi) & (selected.max(axis=0) > efermi))
    if not len(crossing):
        raise ValueError("no band brackets E_F on this mesh; no Fermi surface can be extracted")
    Isosurface, BrillouinZone = _surface_backend()
    boundary = BrillouinZone(reciprocal, [1, 1, 1])
    vertices, triangles, local_bands = [], [], []
    vertex_count = 0
    if progress is not None:
        progress(0, len(crossing))
    for completed, index in enumerate(crossing, 1):
        _check_cancel(is_cancelled)
        surface = Isosurface(
            XYZ=points, V_matrix=selected[:, index].reshape(shape), isovalue=efermi,
            algorithm="lewiner", interpolation_factor=1, padding=[1, 1, 1],
            transform_matrix=reciprocal, boundaries=boundary,
        )
        verts = _real(surface.points, "Fermi vertices")
        faces = _faces(surface.faces)
        vertices.append(verts)
        triangles.append(faces + vertex_count)
        local_bands.extend([completed - 1] * len(faces))
        vertex_count += len(verts)
        if progress is not None:
            progress(completed, len(crossing))
    _check_cancel(is_cancelled)
    mesh = SimpleNamespace(
        points=numpy.concatenate(vertices),
        faces=numpy.column_stack((numpy.full(sum(len(v) for v in triangles), 3), numpy.concatenate(triangles))).ravel(),
        point_data={}, cell_data={"band_index": numpy.asarray(local_bands, dtype=int)},
        band_isosurface_index_map={int(index): local for local, index in enumerate(crossing)},
    )
    adapted = adapt_pyprocar_fermi_surface(mesh, band, spin_index=spin_index, fermi_energy=efermi, source=str(root))
    provenance = ProvenanceRecord(
        id=provenance_id, revision=revision, producer="VASP text / PyProcar Fermi adapter",
        producer_version=f"{ADAPTER_VERSION}/PyProcar-{_package_version()}",
        source=str(root), source_hash=source_hash, parent_ids=(),
        operation="parse_uniform_vasp_mesh", parameters=tuple(parameters.items()),
    )
    surface_provenance = replace(adapted.provenance[0], source_hash=source_hash)
    entities = (structure, band, *adapted.datasets, provenance, surface_provenance)
    return ImportBatch(
        structures=(structure,), datasets=(band, *adapted.datasets),
        provenance=(provenance, surface_provenance),
        report=ParserReport(
            reader_id="pyprocar-vasp-fermi", reader_version=ADAPTER_VERSION,
            created_entity_ids=tuple(item.id for item in entities),
            parsed_capabilities=("structure", "band_structure", "fermi_surface"),
            issues=(ParserIssue(IssueKind.UNSUPPORTED, "pyprocar.projections",
                                "symmetry-resolved projections, occupations, velocity and effective mass are not derived"),),
        ),
    )
