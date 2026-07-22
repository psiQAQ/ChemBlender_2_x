import hashlib
import operator
import re
import warnings
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from .model import (
    ArrayData,
    BasisConvention,
    BasisFunctionKind,
    BasisSet,
    BasisShell,
    ImportBatch,
    IssueKind,
    OrbitalChannel,
    OrbitalKind,
    OrbitalSet,
    ParserIssue,
    ParserReport,
    ProvenanceRecord,
    Structure,
)
from .readers import (
    CapabilitySupport,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
)


ADAPTER_VERSION = "1"
_MAPPED_ATTRIBUTES = {"atcoords", "atnums", "mo", "obasis", "obasis_name", "title"}
_KNOWN_IODATA_ATTRIBUTES = (
    "atcharges",
    "atcoords",
    "atcorenums",
    "atffparams",
    "atfrozen",
    "atgradient",
    "athessian",
    "atmasses",
    "atnums",
    "basisdef",
    "bonds",
    "cellvecs",
    "charge",
    "core_energy",
    "cube",
    "energy",
    "extcharges",
    "extra",
    "g_rot",
    "lot",
    "mo",
    "moments",
    "nelec",
    "obasis",
    "obasis_name",
    "one_ints",
    "one_rdms",
    "run_type",
    "spinpol",
    "title",
    "two_ints",
    "two_rdms",
)


class IODataDependencyError(ImportError):
    pass


def sniff_iodata_wavefunction(source: Path, prefix: bytes) -> SniffResult:
    del source
    if re.search(rb"\[\s*Molden\s+Format\s*\]", prefix, re.IGNORECASE):
        return SniffResult(SniffMatch.EXACT, "Molden format marker")
    if re.search(rb"(?m)^Number of atoms\s+I\s+\d+\s*$", prefix):
        return SniffResult(SniffMatch.EXACT, "Gaussian formatted-checkpoint record")
    return SniffResult(SniffMatch.NONE, "no supported IOData wavefunction marker")


def _source_identity(source):
    source = Path(source)
    try:
        content = source.read_bytes()
    except FileNotFoundError:
        return source, "", "in_memory"
    source_hash = hashlib.sha256(content).hexdigest()
    return source, source_hash, source_hash


def _array(value, name, rank, *, shape=None, integer=False, positive=False):
    import numpy

    values = numpy.asarray(value)
    if values.ndim != rank or (shape is not None and values.shape != shape):
        expected = f"rank {rank}" if shape is None else f"shape {shape}"
        raise ValueError(f"IOData {name} must have {expected}")
    if integer and not numpy.issubdtype(values.dtype, numpy.integer):
        raise ValueError(f"IOData {name} must contain integers")
    if not numpy.isfinite(values).all() or (positive and not (values > 0).all()):
        raise ValueError(f"IOData {name} contains invalid values")
    return values


def _present(value):
    if value is None:
        return False
    if isinstance(value, (dict, list, tuple, str)):
        return bool(value)
    return True


def _unmapped_attributes(data):
    present = set()
    for name in _KNOWN_IODATA_ATTRIBUTES:
        try:
            value = getattr(data, name)
        except (AttributeError, NotImplementedError):
            continue
        if _present(value):
            present.add(name)
    return tuple(sorted(present - _MAPPED_ATTRIBUTES))


def _basis_kind(value):
    if value == "c":
        return BasisFunctionKind.CARTESIAN
    if value == "p":
        return BasisFunctionKind.PURE
    raise ValueError(f"unsupported IOData basis function kind: {value}")


def _adapt_basis(obasis, structure_id, provenance_id, revision, name):
    import numpy

    shells = []
    for index, shell in enumerate(obasis.shells):
        try:
            center_atom = operator.index(shell.icenter)
        except TypeError as error:
            raise ValueError(f"IOData shell {index} has an invalid center") from error
        angular_momenta = _array(
            shell.angmoms, f"shells[{index}].angmoms", 1, integer=True
        )
        kinds = numpy.asarray(shell.kinds)
        if kinds.shape != angular_momenta.shape:
            raise ValueError(f"IOData shell {index} kinds must match contractions")
        exponents = _array(
            shell.exponents, f"shells[{index}].exponents", 1, positive=True
        )
        coefficients = _array(
            shell.coeffs,
            f"shells[{index}].coeffs",
            2,
            shape=(len(exponents), len(angular_momenta)),
        )
        shells.append(
            BasisShell(
                center_atom=center_atom,
                angular_momenta=tuple(int(value) for value in angular_momenta),
                kinds=tuple(_basis_kind(str(value)) for value in kinds),
                exponents=ArrayData(
                    numpy.array(exponents, dtype=float, copy=True),
                    ("primitive",),
                    "inverse_square_bohr",
                ),
                coefficients=ArrayData(
                    numpy.array(coefficients, dtype=float, copy=True),
                    ("primitive", "contraction"),
                    "dimensionless",
                ),
            )
        )
    if not shells:
        raise ValueError("IOData orbital basis contains no shells")

    conventions = []
    for key in sorted(obasis.conventions, key=lambda item: (item[0], item[1])):
        if not isinstance(key, tuple) or len(key) != 2:
            raise ValueError("IOData basis convention key must contain angular momentum and kind")
        angular_momentum, kind = key
        try:
            angular_momentum = operator.index(angular_momentum)
        except TypeError as error:
            raise ValueError("IOData convention angular momentum must be an integer") from error
        conventions.append(
            BasisConvention(
                angular_momentum=angular_momentum,
                kind=_basis_kind(str(kind)),
                functions=tuple(str(value) for value in obasis.conventions[key]),
            )
        )
    return BasisSet(
        id=uuid4(),
        revision=revision,
        structure_id=structure_id,
        name=str(name or "unknown"),
        shells=tuple(shells),
        conventions=tuple(conventions),
        primitive_normalization=str(obasis.primitive_normalization).lower(),
        provenance_ids=(provenance_id,),
    )


def _optional_orbital_array(mo, name, count, issues):
    import numpy

    value = getattr(mo, name, None)
    if value is None:
        semantic_name = "occupations" if name == "occs" else name
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                f"orbital.{semantic_name}",
                f"IOData molecular orbitals do not contain {name}",
            )
        )
        return None
    values = _array(value, f"mo.{name}", 1, shape=(count,))
    return numpy.array(values, copy=True)


def _channel(label, coefficients, energies, occupations, irreps):
    import numpy

    orbital_count = coefficients.shape[1]
    dims = (
        ("orbital", "spin_basis_function")
        if label == "generalized"
        else ("orbital", "basis_function")
    )
    return OrbitalChannel(
        label=label,
        coefficients=ArrayData(
            numpy.array(coefficients.T, dtype=float, copy=True),
            dims,
            "dimensionless",
        ),
        energies=None
        if energies is None
        else ArrayData(
            numpy.array(energies, dtype=float, copy=True), ("orbital",), "hartree"
        ),
        occupations=None
        if occupations is None
        else ArrayData(
            numpy.array(occupations, dtype=float, copy=True),
            ("orbital",),
            "dimensionless",
        ),
        irreps=() if irreps is None else tuple(str(value) for value in irreps),
    )


def _adapt_orbitals(mo, basis, structure_id, provenance_id, revision, issues):
    coefficients = _array(mo.coeffs, "mo.coeffs", 2)
    kind_value = getattr(mo, "kind", None)
    try:
        kind = OrbitalKind(kind_value)
    except ValueError as error:
        raise ValueError(f"unsupported IOData orbital kind: {kind_value}") from error

    if kind is OrbitalKind.RESTRICTED:
        try:
            norba = operator.index(mo.norba)
            norbb = operator.index(mo.norbb)
        except TypeError as error:
            raise ValueError("restricted IOData orbitals require integer counts") from error
        if norba <= 0 or norba != norbb or coefficients.shape != (
            basis.basis_function_count,
            norba,
        ):
            raise ValueError("restricted IOData orbital coefficient shape is invalid")
        count = norba
    elif kind is OrbitalKind.UNRESTRICTED:
        try:
            norba = operator.index(mo.norba)
            norbb = operator.index(mo.norbb)
        except TypeError as error:
            raise ValueError("unrestricted IOData orbitals require integer counts") from error
        if norba <= 0 or norbb <= 0 or coefficients.shape != (
            basis.basis_function_count,
            norba + norbb,
        ):
            raise ValueError("unrestricted IOData orbital coefficient shape is invalid")
        count = norba + norbb
    else:
        if coefficients.shape[0] != 2 * basis.basis_function_count or coefficients.shape[1] <= 0:
            raise ValueError("generalized IOData coefficients require a spin-basis dimension")
        norba = norbb = None
        count = coefficients.shape[1]

    energies = _optional_orbital_array(mo, "energies", count, issues)
    occupations = _optional_orbital_array(mo, "occs", count, issues)
    irreps = getattr(mo, "irreps", None)
    if irreps is None:
        issues.append(
            ParserIssue(
                IssueKind.MISSING,
                "orbital.irreps",
                "IOData molecular orbitals do not contain irreps",
            )
        )
    elif len(irreps) != count:
        raise ValueError("IOData mo.irreps must match the orbital count")

    if kind is OrbitalKind.RESTRICTED:
        channels = (_channel("restricted", coefficients, energies, occupations, irreps),)
    elif kind is OrbitalKind.UNRESTRICTED:
        channels = (
            _channel(
                "alpha",
                coefficients[:, :norba],
                None if energies is None else energies[:norba],
                None if occupations is None else occupations[:norba],
                None if irreps is None else irreps[:norba],
            ),
            _channel(
                "beta",
                coefficients[:, norba:],
                None if energies is None else energies[norba:],
                None if occupations is None else occupations[norba:],
                None if irreps is None else irreps[norba:],
            ),
        )
    else:
        channels = (_channel("generalized", coefficients, energies, occupations, irreps),)
    return OrbitalSet(
        id=uuid4(),
        revision=revision,
        structure_id=structure_id,
        basis_set_id=basis.id,
        kind=kind,
        channels=channels,
        provenance_ids=(provenance_id,),
    )


def adapt_iodata(data, source, *, iodata_version="unknown") -> ImportBatch:
    import numpy

    source, source_hash, revision = _source_identity(source)
    for name in ("atnums", "atcoords", "obasis", "mo"):
        if getattr(data, name, None) is None:
            raise ValueError(f"IOData wavefunction requires {name}")
    atnums = _array(data.atnums, "atnums", 1, integer=True)
    if atnums.size == 0:
        raise ValueError("IOData atnums must not be empty")
    atomic_numbers = tuple(int(value) for value in atnums)
    if any(not 0 <= value <= 118 for value in atomic_numbers):
        raise ValueError("IOData atomic numbers must be from 0 to 118")
    atcoords = _array(data.atcoords, "atcoords", 2, shape=(len(atnums), 3))

    structure_id = uuid4()
    provenance_id = uuid4()
    structure = Structure(
        id=structure_id,
        revision=revision,
        atomic_numbers=atomic_numbers,
        coordinates=ArrayData(
            numpy.array(atcoords, dtype=float, copy=True), ("atom", "xyz"), "bohr"
        ),
    )
    basis = _adapt_basis(
        data.obasis,
        structure_id,
        provenance_id,
        revision,
        getattr(data, "obasis_name", None),
    )
    issues = []
    orbitals = _adapt_orbitals(
        data.mo, basis, structure_id, provenance_id, revision, issues
    )

    unmapped = _unmapped_attributes(data)
    if unmapped:
        issues.append(
            ParserIssue(
                IssueKind.UNSUPPORTED,
                "iodata.attributes",
                "adapter did not map: " + ", ".join(unmapped),
            )
        )
    suffix = source.suffix.lower()
    source_format = "molden" if suffix in {".molden", ".input"} else "fchk"
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="ChemBlender IOData adapter",
        producer_version=ADAPTER_VERSION,
        source=str(source.resolve()),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=(
            ("format", source_format),
            ("iodata_version", str(iodata_version)),
            ("title", str(getattr(data, "title", "") or "")),
            ("basis_name", basis.name),
            ("orbital_kind", orbitals.kind.value),
            ("unmapped_attributes", unmapped),
        ),
    )
    report = ParserReport(
        reader_id="iodata_wavefunction",
        reader_version=ADAPTER_VERSION,
        created_entity_ids=(structure.id, basis.id, orbitals.id, provenance.id),
        parsed_capabilities=("structure", "basis_set", "orbital"),
        issues=tuple(issues),
    )
    return ImportBatch(
        structures=(structure,),
        basis_sets=(basis,),
        orbital_sets=(orbitals,),
        provenance=(provenance,),
        report=report,
    )


def parse_iodata_wavefunction(source) -> ImportBatch:
    try:
        import iodata
        from iodata import load_one
    except ImportError as error:
        raise IODataDependencyError(
            "wavefunction parsing requires the optional qc-iodata dependency"
        ) from error
    source = Path(source)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data = load_one(str(source))
    batch = adapt_iodata(data, source, iodata_version=iodata.__version__)
    if not caught:
        return batch
    warning_issues = tuple(
        ParserIssue(IssueKind.WARNING, "iodata.load", str(item.message))
        for item in caught
    )
    return replace(
        batch,
        report=replace(
            batch.report,
            issues=batch.report.issues + warning_issues,
        ),
    )


IODATA_WAVEFUNCTION_READER = ReaderDescriptor(
    reader_id="iodata_wavefunction",
    reader_version=ADAPTER_VERSION,
    extensions=(".fchk", ".fch", ".molden", ".input"),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "basis_set": CapabilitySupport.SUPPORTED,
        "orbital": CapabilitySupport.SUPPORTED,
    },
    priority=90,
    sniff=sniff_iodata_wavefunction,
    parse=parse_iodata_wavefunction,
)
