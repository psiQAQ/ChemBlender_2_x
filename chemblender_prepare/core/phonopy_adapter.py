import hashlib
import io
import json
from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from cbq_core.model import ArrayData
from cbq_core.model import DatasetStatus
from cbq_core.model import ImportBatch
from cbq_core.model import IssueKind
from cbq_core.model import ParserIssue
from cbq_core.model import ParserReport
from cbq_core.model import PeriodicSiteData
from cbq_core.model import PhononModeSet
from cbq_core.model import ProvenanceRecord
from cbq_core.model import Structure

from chemblender_prepare.core.readers import CapabilitySupport
from chemblender_prepare.core.readers import ReaderDescriptor
from chemblender_prepare.core.readers import SniffMatch
from chemblender_prepare.core.readers import SniffResult


ADAPTER_VERSION = "2"


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


def _qpoint_parameters(qpoints, nac_q_direction, with_group_velocities):
    import numpy

    points = numpy.asarray(qpoints)
    if numpy.iscomplexobj(points):
        raise ValueError("qpoints must be real")
    points = numpy.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (3,) or not len(points) or not numpy.isfinite(points).all():
        raise ValueError("qpoints must be a non-empty finite (qpoint, 3) array")
    direction = None
    if nac_q_direction is not None:
        direction = numpy.asarray(nac_q_direction)
        if numpy.iscomplexobj(direction):
            raise ValueError("nac_q_direction must be real")
        direction = numpy.asarray(direction, dtype=float)
        if direction.shape != (3,) or not numpy.isfinite(direction).all() or not numpy.any(direction):
            raise ValueError("nac_q_direction must be a finite nonzero vector")
    if not isinstance(with_group_velocities, bool):
        raise TypeError("with_group_velocities must be bool")
    return points, direction


def parse_phonopy_file(
    source, *, force_sets_filename=None, born_filename=None,
    qpoints=((0.0, 0.0, 0.0),), nac_q_direction=None,
    with_group_velocities=False, cancel_check=None,
):
    """Read VASP-unit displacement YAML + FORCE_SETS without ambient file reads.

    BORN is opt-in. At Gamma its longitudinal direction must be explicit.
    Cancellation is checked between native phonopy stages, not inside a solve.
    """
    import numpy

    points, direction = _qpoint_parameters(qpoints, nac_q_direction, with_group_velocities)
    if direction is not None and born_filename is None:
        raise ValueError("nac_q_direction requires an explicit BORN file")
    if born_filename is not None and direction is None and numpy.any(numpy.all(points == 0, axis=1)):
        raise ValueError("Gamma with BORN requires an explicit nac_q_direction")

    def check():
        if cancel_check is not None and cancel_check():
            raise CancelledError("phonopy file calculation cancelled")

    check()
    package, phonopy_type = _phonopy()
    import yaml
    from phonopy.file_IO import parse_BORN_from_strings, parse_FORCE_SETS_from_strings
    from phonopy.interface.calculator import get_calculator_physical_units
    from phonopy.interface.phonopy_yaml import PhonopyYaml

    source = Path(source).resolve(strict=True)
    force_path = Path(force_sets_filename).resolve(strict=True) if force_sets_filename is not None else source.parent / "FORCE_SETS"
    paths = [("displacement_yaml", source), ("force_sets", force_path)]
    if born_filename is not None:
        paths.append(("born", Path(born_filename).resolve(strict=True)))
    inputs = [(role, path, path.read_bytes()) for role, path in paths]
    document = yaml.safe_load(inputs[0][2].decode("utf-8-sig"))
    units = document.get("physical_unit", {}) if isinstance(document, dict) else {}
    expected = {"length": "angstrom", "force_constants": "eV/angstrom^2", "atomic_mass": "AMU"}
    if any(units.get(key) != value for key, value in expected.items()):
        raise ValueError("phonopy file reader requires explicit VASP angstrom/eV/AMU units")
    parsed = PhonopyYaml().read(io.StringIO(inputs[0][2].decode("utf-8-sig")))
    if parsed.calculator not in (None, "vasp"):
        raise ValueError("phonopy file reader currently supports VASP units only")
    if parsed.unitcell is None or parsed.supercell_matrix is None:
        raise ValueError("phonopy YAML requires unit_cell and supercell_matrix")
    if parsed.force_constants is not None:
        raise ValueError("use displacement YAML without embedded force_constants")
    phonon = phonopy_type(
        parsed.unitcell, parsed.supercell_matrix,
        primitive_matrix=parsed.primitive_matrix if parsed.primitive_matrix is not None else "auto",
        calculator="vasp", symprec=1e-5, log_level=0,
    )
    factor = parsed.frequency_unit_conversion_factor
    if factor is not None:
        if not numpy.isfinite(factor) or factor <= 0:
            raise ValueError("frequency conversion factor must be positive and finite")
        phonon.unit_conversion_factor = float(factor)
    dataset = parse_FORCE_SETS_from_strings(inputs[1][2].decode("utf-8-sig"))
    if "first_atoms" not in dataset or dataset.get("natom") != len(phonon.supercell):
        raise ValueError("FORCE_SETS must contain matching type-1 supercell displacements")
    for displacement in dataset["first_atoms"]:
        forces = numpy.asarray(displacement["forces"])
        vector = numpy.asarray(displacement["displacement"])
        if forces.shape != (len(phonon.supercell), 3) or vector.shape != (3,) or not numpy.isfinite(forces).all() or not numpy.isfinite(vector).all():
            raise ValueError("FORCE_SETS displacements and forces must be finite and match atoms")
    phonon.dataset = dataset
    check()
    phonon.produce_force_constants(fc_calculator="traditional", show_drift=False)
    if not numpy.isfinite(phonon.force_constants).all():
        raise ValueError("phonopy produced non-finite force constants")
    if born_filename is not None:
        nac = parse_BORN_from_strings(inputs[2][2].decode("utf-8-sig"), phonon.primitive)
        if nac.get("factor") is None:
            nac["factor"] = get_calculator_physical_units("vasp").nac_factor
        if any(not numpy.isfinite(numpy.asarray(nac[key])).all() for key in ("born", "dielectric", "factor")):
            raise ValueError("BORN parameters must be finite")
        phonon.nac_params = nac
    check()
    phonon.run_qpoints(points, with_eigenvectors=True,
        with_group_velocities=with_group_velocities, nac_q_direction=direction)
    check()
    batch = adapt_phonopy_qpoints(phonon, source=str(source))
    parameters = (
        ("qpoints", tuple(tuple(float(value) for value in point) for point in points)),
        ("nac_q_direction", tuple(float(value) for value in direction) if direction is not None else None),
        ("with_group_velocities", with_group_velocities),
        ("fc_calculator", "traditional"), ("symmetrize_force_constants", False),
        ("symmetry_tolerance", 1e-5),
        ("frequency_conversion_factor", float(phonon.unit_conversion_factor)),
    )
    sources = tuple(ProvenanceRecord(
        id=uuid4(), revision=hashlib.sha256(content).hexdigest(),
        producer="phonopy file input", producer_version=ADAPTER_VERSION,
        source=str(path), source_hash=hashlib.sha256(content).hexdigest(),
        parent_ids=(), operation="read_" + role, parameters=(),
    ) for role, path, content in inputs)
    revision = hashlib.sha256(json.dumps(
        (ADAPTER_VERSION, package.__version__, tuple(item.source_hash for item in sources), parameters),
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    provenance = replace(batch.provenance[0], revision=revision,
        source_hash=sources[0].source_hash, parent_ids=tuple(item.id for item in sources),
        operation="force_sets_qpoint_modes", parameters=batch.provenance[0].parameters + parameters)
    check()
    return replace(batch,
        structures=tuple(replace(item, revision=revision) for item in batch.structures),
        datasets=tuple(replace(item, revision=revision) for item in batch.datasets),
        provenance=sources + (provenance,),
        report=replace(batch.report, reader_id="phonopy-file", created_entity_ids=(
            *(item.id for item in batch.structures),
            *(item.id for item in batch.datasets),
            *(item.id for item in sources), provenance.id)),
    )


def parse_phonopy_request(request):
    """Adapt canonical string parameters; read only explicit staged companions."""
    parameters = dict(request.canonical_parameters)
    allowed = {"force_sets_artifact", "force_sets_sha256", "born_artifact", "born_sha256",
               "qpoints", "nac_q_direction", "with_group_velocities"}
    if set(parameters) - allowed:
        raise ValueError("unsupported phonopy canonical parameter")

    def companion(role, required=False):
        artifact = parameters.get(role + "_artifact")
        digest = parameters.get(role + "_sha256")
        if artifact is None and digest is None and not required:
            return None
        if artifact != {"force_sets": "FORCE_SETS", "born": "BORN"}[role] or digest is None:
            raise ValueError("phonopy companion requires its staged filename and SHA256")
        path = request.staging_root / artifact
        if path.is_symlink() or path.resolve(strict=True).parent != request.staging_root:
            raise ValueError("phonopy companion must stay in the staging directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("phonopy companion SHA256 mismatch")
        return path

    velocities = parameters.get("with_group_velocities", "false")
    if velocities not in {"true", "false"}:
        raise ValueError("with_group_velocities must be true or false")
    return parse_phonopy_file(
        request.source_path, force_sets_filename=companion("force_sets", required=True),
        born_filename=companion("born"),
        qpoints=json.loads(parameters.get("qpoints", "[[0,0,0]]")),
        nac_q_direction=json.loads(parameters.get("nac_q_direction", "null")),
        with_group_velocities=velocities == "true", cancel_check=request.is_cancelled,
    )


def sniff_phonopy_file(source: Path, prefix: bytes) -> SniffResult:
    if Path(source).name.lower() not in ("phonopy.yaml", "phonopy_disp.yaml"):
        return SniffResult(SniffMatch.NONE, "not a canonical phonopy YAML filename")
    if b"phonopy:" in prefix and b"supercell_matrix:" in prefix:
        return SniffResult(SniffMatch.EXACT, "phonopy cell and displacement YAML")
    return SniffResult(SniffMatch.POSSIBLE, "canonical phonopy YAML filename")


PHONOPY_FILE_READER = ReaderDescriptor(
    reader_id="phonopy-file", reader_version=ADAPTER_VERSION,
    extensions=(".yaml", ".yml"),
    capabilities={"structure": CapabilitySupport.SUPPORTED, "phonon_mode": CapabilitySupport.SUPPORTED},
    priority=125, sniff=sniff_phonopy_file, parse=parse_phonopy_file,
    parse_request=parse_phonopy_request,
)
