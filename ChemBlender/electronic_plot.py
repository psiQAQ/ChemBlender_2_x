import operator

import bpy

from .core.model import BandStructure, DensityOfStates, EnergyReference
from .spectrum_plot import (
    _curve_object as _new_curve, _flat_material, _plot_axes, _poly_spline,
    _plot_frame, _plot_position, _positive, _remove_objects,
)


def _energy_shift(dataset, reference):
    if not isinstance(reference, EnergyReference):
        raise TypeError("reference must be an EnergyReference")
    if dataset.energy_reference is not EnergyReference.ABSOLUTE:
        raise ValueError("plot input must use authoritative absolute energies")
    return dataset.fermi_energy if reference is EnergyReference.FERMI_SHIFTED else 0.0


def _energy_plot_range(data_range, energy_limits):
    """Optional shared limits use the already selected energy reference; never clip data."""
    if energy_limits is None:
        return data_range
    from math import isfinite

    lower, upper = map(float, energy_limits)
    if (not isfinite(lower) or not isfinite(upper) or lower > upper
            or lower > data_range[0] or upper < data_range[1]):
        raise ValueError("energy_limits must be finite, ordered and contain all plotted energies")
    return lower, upper


def _metadata(obj, dataset, reference, contract):
    obj["cb_dataset_id"] = str(dataset.id)
    obj["cb_dataset_revision"] = dataset.revision
    obj["cb_semantic_role"] = dataset.semantic_role
    obj["cb_energy_unit"] = "electron_volt"
    obj["cb_energy_reference"] = reference.value
    obj["cb_fermi_energy"] = dataset.fermi_energy
    obj["cb_plot_contract"] = contract


def create_band_structure_plot(
    dataset,
    *,
    name="ChemBlender Band Structure",
    collection=None,
    energy_reference=EnergyReference.FERMI_SHIFTED,
    energy_limits=None,
    material=None,
    axis_material=None,
    axes=True,
    line_radius=0.01,
):
    if not isinstance(dataset, BandStructure):
        raise TypeError("dataset must be a BandStructure")
    if not dataset.branches:
        raise ValueError("band line plots require an explicit kpoint path; a uniform Fermi mesh has no path")
    shift = _energy_shift(dataset, energy_reference)
    line_radius = _positive(line_radius, "line_radius")
    if not isinstance(axes, bool):
        raise TypeError("axes must be a bool")
    target = collection or bpy.context.collection
    distances = dataset.distances.values
    energies = dataset.data.values
    branches = tuple((branch.start_index, branch.end_index) for branch in dataset.branches)
    made, materials = [], []
    try:
        if material is None:
            material = _flat_material("ChemBlender Bands", (.08, .25, .65, 1.))
            materials.append(material)
        obj = _new_curve(name, target, radius=line_radius, material=material)
        made.append(obj)
        x_range, y_range = _plot_frame(obj, (distances.min(), distances.max()),
            _energy_plot_range((energies.min() - shift, energies.max() - shift), energy_limits))
        for spin_index in range(energies.shape[0]):
            for band_index in range(energies.shape[2]):
                for start, end in branches:
                    # A disconnected k-path branch is never joined by an invented band segment.
                    _poly_spline(obj.data, tuple(
                        _plot_position(distances[index], energies[spin_index, index, band_index] - shift,
                                       x_range, y_range)
                        for index in range(start, end + 1)))
        if axes:
            ticks = tuple((float(distance), label.replace("\\Gamma", "Γ"))
                          for distance, label in zip(distances, dataset.labels) if label)
            made.extend(_plot_axes(obj, target, x_range, y_range, "k path (Å⁻¹)",
                "E - E_F (eV)" if shift == dataset.fermi_energy and energy_reference is EnergyReference.FERMI_SHIFTED else "E (eV)",
                x_ticks=ticks or None, material=axis_material,
                note=f"E_F = {dataset.fermi_energy:.6g} eV; {', '.join(dataset.spin_channels)}"))
    except Exception:
        _remove_objects(made, materials=materials)
        raise
    _metadata(obj, dataset, energy_reference, "band_structure_curve_v1")
    obj["cb_plot_x_unit"] = dataset.distances.unit
    obj["cb_plot_y_unit"] = dataset.data.unit
    obj["cb_structure_id"] = str(dataset.structure_id)
    obj["cb_spin_channels"] = list(dataset.spin_channels)
    obj["cb_kpoint_labels"] = [label or "" for label in dataset.labels]
    obj["cb_curve_order"] = "spin_major_band_minor_branch_inner"
    obj["cb_branch_start_indices"] = [start for start, end in branches]
    obj["cb_branch_end_indices"] = [end for start, end in branches]
    obj["cb_band_count"] = dataset.data.shape[2]
    return obj


def create_dos_plot(
    dataset,
    *,
    name="ChemBlender Density of States",
    collection=None,
    energy_reference=EnergyReference.FERMI_SHIFTED,
    energy_limits=None,
    mirror_beta=True,
    atom_indices=None,
    orbital_labels=None,
    spin_indices=None,
    material=None,
    axis_material=None,
    axes=True,
    line_radius=0.01,
):
    if not isinstance(dataset, DensityOfStates):
        raise TypeError("dataset must be a DensityOfStates")
    if not isinstance(mirror_beta, bool):
        raise TypeError("mirror_beta must be a bool")
    if not isinstance(axes, bool):
        raise TypeError("axes must be a bool")
    line_radius = _positive(line_radius, "line_radius")
    shift = _energy_shift(dataset, energy_reference)
    densities, selected_spins, selected_atoms, selected_orbitals = select_dos_data(
        dataset, atom_indices=atom_indices, orbital_labels=orbital_labels, spin_indices=spin_indices)
    import numpy

    plotted = numpy.asarray([values * (-1. if mirror_beta and dataset.spin_channels[index] == "beta" else 1.)
                             for index, values in zip(selected_spins, densities)])
    target = collection or bpy.context.collection
    made, materials = [], []
    try:
        if material is None:
            material = _flat_material("ChemBlender DOS", (.08, .25, .65, 1.))
            materials.append(material)
        obj = _new_curve(name, target, radius=line_radius, material=material)
        made.append(obj)
        x_range, y_range = _plot_frame(obj, (min(0., plotted.min()), max(0., plotted.max())),
            _energy_plot_range((dataset.energies.values.min() - shift, dataset.energies.values.max() - shift), energy_limits))
        for values in plotted:
            _poly_spline(obj.data, tuple(_plot_position(density, energy - shift, x_range, y_range)
                for density, energy in zip(values, dataset.energies.values)))
        if axes:
            density_unit = "states / (eV Å³)" if dataset.data.unit.endswith("per_cubic_angstrom") else "states / eV"
            selection = ("Total DOS" if selected_atoms is None else
                         f"PDOS atoms {','.join(str(index + 1) for index in selected_atoms)}; {','.join(selected_orbitals)}")
            channels = ", ".join(dataset.spin_channels[index] for index in selected_spins)
            note = f"{selection}; {channels}; E_F = {dataset.fermi_energy:.6g} eV"
            if mirror_beta and 1 in selected_spins:
                note += "; beta mirrored"
            made.extend(_plot_axes(obj, target, x_range, y_range,
                density_unit, "E - E_F (eV)" if energy_reference is EnergyReference.FERMI_SHIFTED else "E (eV)",
                material=axis_material, note=note))
    except Exception:
        _remove_objects(made, materials=materials)
        raise
    _metadata(obj, dataset, energy_reference, "density_of_states_curve_v1")
    obj["cb_plot_x_unit"] = dataset.data.unit
    obj["cb_plot_y_unit"] = dataset.energies.unit
    obj["cb_structure_id"] = str(dataset.structure_id)
    obj["cb_spin_channels"] = list(dataset.spin_channels)
    obj["cb_curve_order"] = "spin_index"
    obj["cb_mirror_beta"] = mirror_beta
    obj["cb_density_unit"] = dataset.data.unit
    obj["cb_plot_spin_indices"] = list(selected_spins)
    obj["cb_dos_projection"] = "total" if selected_atoms is None else "atom_orbital_sum"
    if selected_atoms is not None:
        obj["cb_dos_atom_indices"] = list(selected_atoms)
        obj["cb_dos_orbital_labels"] = list(selected_orbitals)
    return obj


def _selection_indices(values, count, name):
    if values is None:
        return tuple(range(count))
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an integer sequence")
    result = tuple(_selection_index(value, count, name) for value in values)
    if not result or len(set(result)) != len(result):
        raise ValueError(f"{name} must be non-empty and unique")
    return result


def select_dos_data(dataset, *, atom_indices=None, orbital_labels=None, spin_indices=None):
    """Return selected spin-energy values and exact source indices, without mutating DOS."""
    import numpy

    if not isinstance(dataset, DensityOfStates):
        raise TypeError("dataset must be a DensityOfStates")
    spins = _selection_indices(spin_indices, dataset.data.shape[0], "spin_indices")
    if atom_indices is None and orbital_labels is None:
        return numpy.asarray(dataset.data.values)[list(spins)], spins, None, None
    if dataset.projections is None:
        raise ValueError("PDOS selection requires explicit atom-orbital projections")
    atoms = _selection_indices(atom_indices, dataset.projections.shape[2], "atom_indices")
    if isinstance(orbital_labels, (str, bytes)):
        raise TypeError("orbital_labels must be a sequence of exact labels")
    labels = dataset.orbital_labels if orbital_labels is None else tuple(orbital_labels)
    if not labels or any(not isinstance(label, str) for label in labels) or len(set(labels)) != len(labels):
        raise ValueError("orbital_labels must be non-empty and unique")
    if any(label not in dataset.orbital_labels for label in labels):
        raise ValueError("orbital_labels contains an unknown orbital")
    orbitals = tuple(dataset.orbital_labels.index(label) for label in labels)
    values = numpy.asarray(dataset.projections.values)
    selected = values[numpy.ix_(spins, range(values.shape[1]), atoms, orbitals)].sum(axis=(2, 3))
    return selected, spins, atoms, labels


def _selection_index(value, size, name):
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    try:
        value = operator.index(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an integer") from error
    if not 0 <= value < size:
        raise IndexError(f"{name} is outside the dataset")
    return int(value)


def _require_plot(obj, dataset, contract):
    if getattr(obj, "type", None) != "CURVE":
        raise TypeError("plot object must be a Curve")
    if obj.get("cb_plot_contract") != contract or obj.get("cb_dataset_id") != str(dataset.id):
        raise ValueError("plot object does not match dataset")


def select_band_sample(obj, dataset, spin_index, kpoint_index, band_index):
    if not isinstance(dataset, BandStructure):
        raise TypeError("dataset must be a BandStructure")
    _require_plot(obj, dataset, "band_structure_curve_v1")
    spin_index = _selection_index(spin_index, dataset.data.shape[0], "spin_index")
    kpoint_index = _selection_index(kpoint_index, dataset.data.shape[1], "kpoint_index")
    band_index = _selection_index(band_index, dataset.data.shape[2], "band_index")
    obj["cb_selected_spin"] = spin_index
    obj["cb_selected_kpoint"] = kpoint_index
    obj["cb_selected_band"] = band_index


def select_dos_sample(obj, dataset, spin_index, energy_index):
    if not isinstance(dataset, DensityOfStates):
        raise TypeError("dataset must be a DensityOfStates")
    _require_plot(obj, dataset, "density_of_states_curve_v1")
    spin_index = _selection_index(spin_index, dataset.data.shape[0], "spin_index")
    energy_index = _selection_index(energy_index, dataset.data.shape[1], "energy_index")
    obj["cb_selected_spin"] = spin_index
    obj["cb_selected_energy"] = energy_index
