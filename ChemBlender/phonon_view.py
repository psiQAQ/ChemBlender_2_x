"""Display-only phonon supercells built from authoritative primitive modes."""

from itertools import product
import operator
from uuid import uuid4

from cbq_core.model import ArrayData
from cbq_core.model import DatasetStatus
from cbq_core.model import PeriodicSiteData
from cbq_core.model import PhononModeSet
from cbq_core.model import Structure
from cbq_core.phonon_frames import _index
from cbq_core.phonon_frames import derive_phonon_frames
from .views.structure import (
    StructureViewSettings, _coordinate_scale, create_structure_view, remove_structure_view,
)


_REFERENCE = "cbq_phonon_reference_position"
_PRIMITIVE = "cbq_phonon_primitive_atom"
_TRANSLATION = "cbq_phonon_translation"
_CONTRACT = "phonon_view_v1"


def _repetitions(values):
    try:
        values = tuple(values)
        if len(values) != 3 or any(isinstance(value, bool) for value in values):
            raise ValueError
        counts = tuple(operator.index(value) for value in values)
        if any(value <= 0 for value in counts):
            raise ValueError
    except (TypeError, ValueError) as error:
        raise ValueError("repetitions must contain three positive integers") from error
    return counts


def _reference_supercell(structure, repetitions):
    import numpy

    if not isinstance(structure, Structure) or structure.periodic is None or not all(structure.periodic.pbc):
        raise ValueError("phonon view requires a fully periodic primitive Structure")
    repetitions = _repetitions(repetitions)
    cells = numpy.asarray(tuple(product(*(range(value) for value in repetitions))), dtype=int)
    primitive_count = len(structure.atomic_numbers)
    indices = numpy.tile(numpy.arange(primitive_count), len(cells))
    translations = numpy.repeat(cells, primitive_count, axis=0)
    positions = numpy.asarray(structure.coordinates.values)[indices] + translations @ numpy.asarray(structure.cell.values)
    fractional = (numpy.asarray(structure.periodic.fractional_coordinates.values)[indices] + translations) / repetitions
    count = len(indices)
    reference = Structure(
        id=uuid4(), revision=structure.revision + repr(repetitions),
        atomic_numbers=tuple(structure.atomic_numbers[index] for index in indices),
        coordinates=ArrayData(positions, ("atom", "xyz"), structure.coordinates.unit),
        cell=ArrayData(numpy.diag(repetitions) @ numpy.asarray(structure.cell.values),
            ("cell_vector", "xyz"), structure.cell.unit),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(fractional, ("atom", "xyz"), "dimensionless"),
            site_labels=tuple(f"{structure.periodic.site_labels[index]}_{offset}" for offset, index in enumerate(indices)),
            occupancies=ArrayData(numpy.asarray(structure.periodic.occupancies.values)[indices], ("atom",), "dimensionless"),
            isotropic_displacements=None, anisotropic_displacements=None,
            adp_types=("none",) * count, disorder_groups=(0,) * count,
            declared_space_group_name=None, declared_space_group_number=None,
            symmetry_operations=(), cif_envelope_id=None,
        ),
    )
    return reference, indices, translations


def _display_frame(structure, modes, repetitions, qpoint_index, mode_index, phase, amplitude):
    import numpy

    if not isinstance(modes, PhononModeSet) or modes.structure_id != structure.id:
        raise ValueError("phonon modes must bind the provided primitive Structure")
    if modes.status is not DatasetStatus.COMPLETE:
        raise ValueError("phonon view requires complete modes")
    qpoint_index = _index(qpoint_index, modes.data.shape[0], "qpoint_index")
    mode_index = _index(mode_index, modes.data.shape[1], "mode_index")
    if modes.eigenvectors.shape[2] != len(structure.atomic_numbers):
        raise ValueError("phonon eigenvector atom count does not match primitive Structure")
    vector = numpy.asarray(modes.eigenvectors.values[qpoint_index, mode_index])
    if not numpy.isfinite(vector).all() or not numpy.isclose(numpy.sum(abs(vector) ** 2), 1.0, rtol=1e-6, atol=1e-8):
        raise ValueError("selected phonon eigenvector must be normalized; no implicit normalization")
    if modes.masses is None:
        raise ValueError("phonon view requires atomic masses")
    masses = numpy.asarray(modes.masses.values)
    if masses.shape != (len(structure.atomic_numbers),) or not numpy.isfinite(masses).all() or numpy.any(masses <= 0):
        raise ValueError("phonon view requires positive finite atomic masses")
    reference, indices, translations = _reference_supercell(structure, repetitions)
    frames = derive_phonon_frames(modes, reference,
        primitive_atom_indices=indices, translations=translations,
        qpoint_index=qpoint_index, mode_index=mode_index, phases=[phase], amplitude=amplitude)
    positions = numpy.asarray(frames.datasets[0].data.values[0]) * _coordinate_scale(reference.coordinates.unit)
    return reference, indices, translations, positions


def _attribute(mesh, name, data_type, field, values):
    import numpy

    attribute = mesh.attributes.new(name, data_type, "POINT")
    attribute.data.foreach_set(field, numpy.asarray(values).reshape(-1))


def create_phonon_view(
    structure, modes, *, qpoint_index, mode_index, repetitions=(1, 1, 1),
    amplitude_scale=.4, phase=0, collection=None,
):
    import bpy

    repetitions = _repetitions(repetitions)
    reference, indices, translations, positions = _display_frame(
        structure, modes, repetitions, qpoint_index, mode_index, phase, amplitude_scale)
    previous_groups = set(bpy.data.node_groups)
    previous_materials = set(bpy.data.materials)
    obj = create_structure_view(reference,
        settings=StructureViewSettings(display_periodic_images=False),
        name="ChemBlender Phonon", collection=collection)
    try:
        for item in (obj, *obj.children_recursive):
            item["cb_scientific_component"] = "phonon_atoms"
            if item.data is not None:
                item.data["cb_scientific_owned"] = True
        for group in set(bpy.data.node_groups) - previous_groups:
            group["cb_scientific_owned"] = True
        for material in set(bpy.data.materials) - previous_materials:
            material["cb_scientific_owned"] = True
        _attribute(obj.data, _REFERENCE, "FLOAT_VECTOR", "vector",
            reference.coordinates.values * _coordinate_scale(reference.coordinates.unit))
        _attribute(obj.data, _PRIMITIVE, "INT", "value", indices)
        _attribute(obj.data, _TRANSLATION, "FLOAT_VECTOR", "vector", translations)
        obj["cb_phonon_contract"] = _CONTRACT
        obj["cb_structure_id"] = str(structure.id)
        obj["cb_structure_revision"] = structure.revision
        obj["cb_phonon_mode_set_id"] = str(modes.id)
        obj["cb_phonon_mode_set_revision"] = modes.revision
        obj["cb_phonon_qpoint_index"] = int(qpoint_index)
        obj["cb_phonon_mode_index"] = int(mode_index)
        obj["cb_phonon_repetitions"] = repetitions
        obj["cb_phonon_phase"] = float(phase)
        obj["cb_phonon_amplitude_scale"] = float(amplitude_scale)
        obj["cb_phonon_amplitude_unit"] = "angstrom"
        obj["cb_phonon_amplitude_convention"] = "display_scale_times_eigenvector_over_sqrt_mass_amu"
        obj["cb_phonon_phase_convention"] = "exp_i_2pi_qR_minus_phase"
        obj.data.vertices.foreach_set("co", positions.reshape(-1))
        obj.data.update()
        return obj
    except BaseException:
        remove_structure_view(obj)
        raise


def apply_phonon_phase(root, structure, modes, phase, *, amplitude_scale=.4):
    import bpy
    import numpy

    if not isinstance(root, bpy.types.Object) or root.type != "MESH" or root.get("cb_phonon_contract") != _CONTRACT:
        raise ValueError("object is not a phonon view")
    for key, expected in (
        ("cb_structure_id", str(structure.id)), ("cb_structure_revision", structure.revision),
        ("cb_phonon_mode_set_id", str(modes.id)), ("cb_phonon_mode_set_revision", modes.revision),
    ):
        if root.get(key) != expected:
            raise ValueError("phonon source identity or revision changed; rebuild the View")
    reference, indices, translations, positions = _display_frame(
        structure, modes, root["cb_phonon_repetitions"], root["cb_phonon_qpoint_index"],
        root["cb_phonon_mode_index"], phase, amplitude_scale)
    if len(root.data.vertices) != len(indices):
        raise ValueError("phonon mesh atom count changed; rebuild the View")
    for name, kind, field, expected in (
        (_PRIMITIVE, "INT", "value", indices),
        (_TRANSLATION, "FLOAT_VECTOR", "vector", translations),
        (_REFERENCE, "FLOAT_VECTOR", "vector", reference.coordinates.values * _coordinate_scale(reference.coordinates.unit)),
    ):
        attribute = root.data.attributes.get(name)
        if attribute is None or attribute.data_type != kind or attribute.domain != "POINT":
            raise ValueError("phonon reference attributes changed; rebuild the View")
        values = numpy.empty(numpy.asarray(expected).size)
        attribute.data.foreach_get(field, values)
        if not numpy.allclose(values, numpy.asarray(expected).reshape(-1), rtol=1e-6, atol=1e-6):
            raise ValueError("phonon reference attributes changed; rebuild the View")
    if root.data.users > 1:
        root.data = root.data.copy()
        root.data["cb_scientific_owned"] = True
    root.data.vertices.foreach_set("co", positions.reshape(-1))
    root["cb_phonon_phase"] = float(phase)
    root["cb_phonon_amplitude_scale"] = float(amplitude_scale)
    root.data.update()
