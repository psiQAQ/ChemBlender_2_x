import hashlib
import operator
from math import isfinite
from uuid import uuid4

from .model import (
    ArrayData,
    DatasetStatus,
    FrameSet,
    ImportBatch,
    ParserReport,
    PhononModeSet,
    ProvenanceRecord,
    Structure,
)


DERIVATION_VERSION = "1"


def _index(value, size, name):
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    try:
        value = operator.index(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an integer") from error
    if not 0 <= value < size:
        raise IndexError(f"{name} is outside the phonon dataset")
    return int(value)


def derive_phonon_frames(
    modes,
    supercell_structure,
    *,
    primitive_atom_indices,
    translations,
    qpoint_index,
    mode_index,
    phases,
    amplitude=1.0,
    user_phase=0.0,
):
    import numpy

    if not isinstance(modes, PhononModeSet):
        raise TypeError("modes must be a PhononModeSet")
    if not isinstance(supercell_structure, Structure) or supercell_structure.periodic is None:
        raise TypeError("supercell_structure must be a periodic Structure")
    atom_count = len(supercell_structure.atomic_numbers)
    primitive_indices = numpy.asarray(primitive_atom_indices)
    if (
        primitive_indices.shape != (atom_count,)
        or not numpy.issubdtype(primitive_indices.dtype, numpy.integer)
        or numpy.any(primitive_indices < 0)
        or numpy.any(primitive_indices >= modes.eigenvectors.shape[2])
    ):
        raise ValueError("primitive_atom_indices must map every supercell atom")
    translations = numpy.asarray(translations, dtype=float)
    if translations.shape != (atom_count, 3) or not numpy.all(numpy.isfinite(translations)):
        raise ValueError("translations must contain one finite lattice translation per atom")
    phases = numpy.asarray(phases, dtype=float)
    if phases.ndim != 1 or not len(phases) or not numpy.all(numpy.isfinite(phases)):
        raise ValueError("phases must be a non-empty finite one-dimensional array")
    if (
        isinstance(amplitude, bool)
        or not isinstance(amplitude, (int, float))
        or not isfinite(amplitude)
        or amplitude <= 0.0
    ):
        raise ValueError("amplitude must be positive and finite")
    if (
        isinstance(user_phase, bool)
        or not isinstance(user_phase, (int, float))
        or not isfinite(user_phase)
    ):
        raise ValueError("user_phase must be finite")
    qpoint_index = _index(qpoint_index, modes.data.shape[0], "qpoint_index")
    mode_index = _index(mode_index, modes.data.shape[1], "mode_index")

    qpoint = numpy.asarray(modes.qpoints.values[qpoint_index], dtype=float)
    eigenvector = numpy.asarray(
        modes.eigenvectors.values[qpoint_index, mode_index], dtype=complex
    )[primitive_indices]
    masses = numpy.asarray(modes.masses.values, dtype=float)[primitive_indices]
    spatial_phase = 2.0 * numpy.pi * numpy.dot(translations, qpoint)
    phase_factors = numpy.exp(
        1j * (spatial_phase[numpy.newaxis, :] - phases[:, numpy.newaxis] + user_phase)
    )
    displacements = (
        amplitude
        * numpy.real(eigenvector[numpy.newaxis, :, :] * phase_factors[:, :, numpy.newaxis])
        / numpy.sqrt(masses)[numpy.newaxis, :, numpy.newaxis]
    )
    coordinates = numpy.asarray(supercell_structure.coordinates.values, dtype=float)
    frame_values = coordinates[numpy.newaxis, :, :] + displacements
    digest = hashlib.sha256()
    digest.update(modes.revision.encode("utf-8"))
    digest.update(supercell_structure.revision.encode("utf-8"))
    for values in (primitive_indices, translations, phases):
        digest.update(numpy.ascontiguousarray(values).tobytes())
    digest.update(repr((qpoint_index, mode_index, amplitude, user_phase)).encode("ascii"))
    revision = digest.hexdigest()
    provenance_id = uuid4()
    frames = FrameSet(
        id=uuid4(),
        revision=revision,
        semantic_role="coordinates",
        domain="frame",
        data=ArrayData(
            frame_values,
            ("frame", "atom", "xyz"),
            supercell_structure.coordinates.unit,
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=modes.source_calculation,
        provenance_ids=(provenance_id,),
        structure_id=supercell_structure.id,
        comments=tuple(f"phase={phase:.12g}" for phase in phases),
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="ChemBlender phonon frame derivation",
        producer_version=DERIVATION_VERSION,
        source="",
        source_hash=revision,
        parent_ids=(modes.id, supercell_structure.id),
        operation="derive_periodic_phonon_frames",
        parameters=(
            ("qpoint_index", qpoint_index),
            ("mode_index", mode_index),
            ("frequency_terahertz", float(modes.data.values[qpoint_index, mode_index])),
            ("amplitude", float(amplitude)),
            ("user_phase", float(user_phase)),
            ("phase_convention", "exp_i_2pi_qR_minus_phase"),
        ),
    )
    return ImportBatch(
        datasets=(frames,),
        provenance=(provenance,),
        report=ParserReport(
            reader_id="chemblender-phonon-frames",
            reader_version=DERIVATION_VERSION,
            created_entity_ids=(frames.id, provenance.id),
            parsed_capabilities=("trajectory", "phonon_mode"),
            issues=(),
        ),
    )
