import hashlib
from uuid import uuid4

from .model import (
    ArrayData,
    DatasetStatus,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    PeriodicSiteData,
    PhononModeSet,
    ProvenanceRecord,
    Structure,
)


ADAPTER_VERSION = "1"


class PhonopyDependencyError(RuntimeError):
    pass


def _phonopy():
    try:
        import phonopy
        from phonopy import Phonopy
    except ModuleNotFoundError as error:
        if error.name == "phonopy" or (
            error.name and error.name.startswith("phonopy.")
        ):
            raise PhonopyDependencyError(
                "phonopy is required in the ChemBlender core/worker environment"
            ) from error
        raise
    return phonopy, Phonopy


def _site_labels(symbols):
    counts = {}
    labels = []
    for symbol in symbols:
        counts[symbol] = counts.get(symbol, 0) + 1
        labels.append(f"{symbol}{counts[symbol]}")
    return tuple(labels)


def _revision(phonon):
    import numpy

    digest = hashlib.sha256()
    primitive = phonon.primitive
    result = phonon.qpoints
    for values in (
        primitive.cell,
        primitive.scaled_positions,
        primitive.numbers,
        primitive.masses,
        result.qpoints,
        result.frequencies,
        result.eigenvectors,
    ):
        array = numpy.asarray(values)
        digest.update(str(array.dtype).encode("ascii"))
        digest.update(numpy.asarray(array.shape, dtype="<i8").tobytes())
        digest.update(numpy.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def _structure(primitive, revision):
    import numpy

    lattice = numpy.asarray(primitive.cell, dtype=float)
    fractional = numpy.asarray(primitive.scaled_positions, dtype=float)
    cartesian = numpy.asarray(primitive.positions, dtype=float)
    symbols = tuple(primitive.symbols)
    return Structure(
        id=uuid4(),
        revision=revision,
        atomic_numbers=tuple(int(number) for number in primitive.numbers),
        coordinates=ArrayData(cartesian, ("atom", "xyz"), "angstrom"),
        cell=ArrayData(lattice, ("cell_vector", "xyz"), "angstrom"),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(
                fractional, ("atom", "xyz"), "dimensionless"
            ),
            site_labels=_site_labels(symbols),
            occupancies=ArrayData(
                numpy.ones(len(symbols)), ("atom",), "dimensionless"
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",) * len(symbols),
            disorder_groups=(0,) * len(symbols),
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=(),
            cif_envelope_id=None,
            pbc=(True, True, True),
        ),
    )


def adapt_phonopy_qpoints(phonon, *, source=""):
    import numpy

    phonopy_package, phonopy_type = _phonopy()
    if not isinstance(phonon, phonopy_type):
        raise TypeError("phonon must be a phonopy.Phonopy object")
    result = phonon.qpoints
    if result is None:
        raise ValueError("phonon.run_qpoints must be called before adaptation")
    if result.eigenvectors is None:
        raise ValueError("run_qpoints must use with_eigenvectors=True")
    primitive = phonon.primitive
    if primitive is None or primitive.masses is None:
        raise ValueError("phonopy primitive structure and masses are required")
    revision = _revision(phonon)
    structure = _structure(primitive, revision)
    qpoints = numpy.asarray(result.qpoints, dtype=float)
    frequencies = numpy.asarray(result.frequencies, dtype=float)
    raw_eigenvectors = numpy.asarray(result.eigenvectors, dtype=complex)
    atom_count = len(primitive)
    mode_count = atom_count * 3
    if raw_eigenvectors.shape != (len(qpoints), mode_count, mode_count):
        raise ValueError("phonopy eigenvector shape does not match primitive atoms")
    eigenvectors = raw_eigenvectors.transpose(0, 2, 1).reshape(
        (len(qpoints), mode_count, atom_count, 3)
    )
    group_velocities = getattr(result, "group_velocities", None)
    velocity_data = None
    issues = []
    if group_velocities is None:
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "phonon.group_velocities",
                "run_qpoints did not calculate group velocities",
            )
        )
    else:
        velocity_data = ArrayData(
            numpy.asarray(group_velocities, dtype=float),
            ("qpoint", "mode", "xyz"),
            "terahertz_angstrom",
        )
    weights = getattr(result, "weights", None)
    weight_data = None
    if weights is None:
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "phonon.qpoint_weights",
                "explicit q-point results do not provide integration weights",
            )
        )
    else:
        weight_data = ArrayData(
            numpy.asarray(weights, dtype=float), ("qpoint",), "dimensionless"
        )
    provenance_id = uuid4()
    modes = PhononModeSet(
        id=uuid4(),
        revision=revision,
        semantic_role="phonon_modes",
        domain="mode",
        data=ArrayData(frequencies, ("qpoint", "mode"), "terahertz"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        structure_id=structure.id,
        qpoints=ArrayData(
            qpoints, ("qpoint", "reciprocal_axis"), "dimensionless"
        ),
        eigenvectors=ArrayData(
            eigenvectors,
            ("qpoint", "mode", "atom", "xyz"),
            "dimensionless",
        ),
        masses=ArrayData(
            numpy.asarray(primitive.masses, dtype=float),
            ("atom",),
            "atomic_mass_unit",
        ),
        group_velocities=velocity_data,
        weights=weight_data,
        eigenvector_convention="phonopy_mass_weighted_dynamical_matrix",
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="phonopy q-point adapter",
        producer_version=f"{ADAPTER_VERSION}/phonopy-{phonopy_package.__version__}",
        source=str(source),
        source_hash=revision,
        parent_ids=(),
        operation="normalize_qpoint_modes",
        parameters=(
            ("frequency_unit", "terahertz"),
            ("eigenvector_convention", modes.eigenvector_convention),
        ),
    )
    return ImportBatch(
        structures=(structure,),
        datasets=(modes,),
        provenance=(provenance,),
        report=ParserReport(
            reader_id="phonopy-qpoints",
            reader_version=ADAPTER_VERSION,
            created_entity_ids=(structure.id, modes.id, provenance.id),
            parsed_capabilities=("structure", "phonon_mode"),
            issues=tuple(issues),
        ),
    )
