import hashlib
from math import isfinite
from uuid import uuid4

from .model import (
    ArrayData,
    ImportBatch,
    PeriodicSiteData,
    ProvenanceRecord,
    Structure,
    SymmetryResult,
)


ADAPTER_VERSION = "1"
_ANGSTROM_SCALE = {"angstrom": 1.0, "bohr": 0.529177210903}


class SpglibDependencyError(RuntimeError):
    pass


def _spglib():
    try:
        import spglib
    except ModuleNotFoundError as error:
        if error.name == "spglib":
            raise SpglibDependencyError(
                "spglib is required in the ChemBlender core/worker environment"
            ) from error
        raise
    return spglib


def _tolerances(symprec, angle_tolerance):
    for value, name in (
        (symprec, "symprec"),
        (angle_tolerance, "angle_tolerance"),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
        ):
            raise ValueError(f"{name} must be finite")
    if symprec <= 0.0:
        raise ValueError("symprec must be positive")
    if angle_tolerance < 0.0 and angle_tolerance != -1.0:
        raise ValueError("angle_tolerance must be -1 or non-negative")
    return float(symprec), float(angle_tolerance)


def derive_symmetry(
    structure,
    *,
    symprec=1.0e-5,
    angle_tolerance=-1.0,
    hall_number=0,
):
    import numpy

    spglib = _spglib()
    if not isinstance(structure, Structure) or structure.periodic is None:
        raise TypeError("structure must be a periodic Structure")
    symprec, angle_tolerance = _tolerances(symprec, angle_tolerance)
    if (
        isinstance(hall_number, bool)
        or not isinstance(hall_number, int)
        or not 0 <= hall_number <= 530
    ):
        raise ValueError("hall_number must be from 0 to 530")
    occupancies = numpy.asarray(structure.periodic.occupancies.values)
    if not numpy.allclose(occupancies, 1.0, rtol=0.0, atol=1.0e-12):
        raise ValueError("spglib symmetry does not accept partial occupancy")
    if any(structure.periodic.disorder_groups):
        raise ValueError("spglib symmetry does not accept disorder groups")
    try:
        scale = _ANGSTROM_SCALE[structure.cell.unit]
    except KeyError as error:
        raise ValueError(
            "spglib adapter requires angstrom or bohr cell units"
        ) from error
    lattice = numpy.asarray(structure.cell.values, dtype=float) * scale
    positions = numpy.asarray(
        structure.periodic.fractional_coordinates.values, dtype=float
    )
    numbers = numpy.asarray(structure.atomic_numbers, dtype=int)
    try:
        dataset = spglib.get_symmetry_dataset(
            (lattice, positions, numbers),
            symprec=symprec,
            angle_tolerance=angle_tolerance,
            hall_number=hall_number,
            _throw=True,
        )
    except Exception as error:
        raise ValueError(f"spglib symmetry search failed: {error}") from error
    if dataset is None:
        raise ValueError("spglib symmetry search returned no result")

    revision_source = "|".join(
        (
            structure.revision,
            spglib.__version__,
            repr(symprec),
            repr(angle_tolerance),
            str(hall_number),
        )
    ).encode("utf-8")
    revision = hashlib.sha256(revision_source).hexdigest()
    provenance_id = uuid4()
    standard_id = uuid4()
    result_id = uuid4()
    standard_lattice = numpy.asarray(dataset.std_lattice, dtype=float)
    standard_fractional = numpy.asarray(dataset.std_positions, dtype=float)
    standard_numbers = tuple(int(value) for value in dataset.std_types)
    standard_periodic = PeriodicSiteData(
        fractional_coordinates=ArrayData(
            standard_fractional,
            ("atom", "xyz"),
            "dimensionless",
        ),
        site_labels=tuple(
            f"standard_site_{index}" for index in range(len(standard_numbers))
        ),
        occupancies=ArrayData(
            numpy.ones(len(standard_numbers)),
            ("atom",),
            "dimensionless",
        ),
        isotropic_displacements=None,
        anisotropic_displacements=None,
        adp_types=("none",) * len(standard_numbers),
        disorder_groups=(0,) * len(standard_numbers),
        declared_space_group_name=dataset.international,
        declared_space_group_number=int(dataset.number),
        symmetry_operations=(),
        cif_envelope_id=structure.periodic.cif_envelope_id,
    )
    standard_structure = Structure(
        id=standard_id,
        revision=revision,
        atomic_numbers=standard_numbers,
        coordinates=ArrayData(
            standard_fractional @ standard_lattice,
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=ArrayData(
            standard_lattice,
            ("cell_vector", "xyz"),
            "angstrom",
        ),
        periodic=standard_periodic,
    )
    result = SymmetryResult(
        id=result_id,
        revision=revision,
        structure_id=structure.id,
        standardized_structure_id=standard_id,
        hall_number=int(dataset.hall_number),
        international_number=int(dataset.number),
        international_symbol=dataset.international,
        hall_symbol=dataset.hall,
        choice=dataset.choice,
        pointgroup=dataset.pointgroup,
        rotations=ArrayData(
            numpy.asarray(dataset.rotations),
            ("operation", "output_axis", "input_axis"),
            "dimensionless",
        ),
        translations=ArrayData(
            numpy.asarray(dataset.translations),
            ("operation", "axis"),
            "dimensionless",
        ),
        wyckoffs=tuple(dataset.wyckoffs),
        site_symmetry_symbols=tuple(dataset.site_symmetry_symbols),
        equivalent_atoms=ArrayData(
            numpy.asarray(dataset.equivalent_atoms),
            ("atom",),
            "dimensionless",
        ),
        crystallographic_orbits=ArrayData(
            numpy.asarray(dataset.crystallographic_orbits),
            ("atom",),
            "dimensionless",
        ),
        transformation_matrix=ArrayData(
            numpy.asarray(dataset.transformation_matrix),
            ("standard_axis", "input_axis"),
            "dimensionless",
        ),
        origin_shift=ArrayData(
            numpy.asarray(dataset.origin_shift),
            ("axis",),
            "dimensionless",
        ),
        mapping_to_primitive=ArrayData(
            numpy.asarray(dataset.mapping_to_primitive),
            ("atom",),
            "dimensionless",
        ),
        std_mapping_to_primitive=ArrayData(
            numpy.asarray(dataset.std_mapping_to_primitive),
            ("standard_atom",),
            "dimensionless",
        ),
        std_rotation_matrix=ArrayData(
            numpy.asarray(dataset.std_rotation_matrix),
            ("cartesian_output_axis", "cartesian_input_axis"),
            "dimensionless",
        ),
        symprec=symprec,
        angle_tolerance=angle_tolerance,
        provenance_ids=(provenance_id,),
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="spglib symmetry adapter",
        producer_version=f"{ADAPTER_VERSION}/spglib-{spglib.__version__}",
        source="",
        source_hash="",
        parent_ids=(structure.id,),
        operation="symmetry_standardization",
        parameters=(
            ("symprec_angstrom", symprec),
            ("angle_tolerance_degree", angle_tolerance),
            ("requested_hall_number", hall_number),
        ),
    )
    return ImportBatch(
        structures=(standard_structure,),
        symmetry_results=(result,),
        provenance=(provenance,),
    )
