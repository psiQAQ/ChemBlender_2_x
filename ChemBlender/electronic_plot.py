import operator

import bpy

from .core.model import BandStructure, DensityOfStates, EnergyReference


def _energy_shift(dataset, reference):
    if not isinstance(reference, EnergyReference):
        raise TypeError("reference must be an EnergyReference")
    if dataset.energy_reference is not EnergyReference.ABSOLUTE:
        raise ValueError("plot input must use authoritative absolute energies")
    return dataset.fermi_energy if reference is EnergyReference.FERMI_SHIFTED else 0.0


def _curve_object(name, collection):
    curve = bpy.data.curves.new(name=name, type="CURVE")
    curve.dimensions = "2D"
    obj = bpy.data.objects.new(name, curve)
    (collection or bpy.context.collection).objects.link(obj)
    return obj


def _poly_spline(curve, coordinates):
    spline = curve.splines.new("POLY")
    spline.points.add(len(coordinates) - 1)
    for point, coordinate in zip(spline.points, coordinates):
        point.co = (*coordinate, 1.0)
    return spline


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
):
    if not isinstance(dataset, BandStructure):
        raise TypeError("dataset must be a BandStructure")
    shift = _energy_shift(dataset, energy_reference)
    obj = _curve_object(name, collection)
    distances = dataset.distances.values
    energies = dataset.data.values
    for spin_index in range(energies.shape[0]):
        for band_index in range(energies.shape[2]):
            _poly_spline(
                obj.data,
                tuple(
                    (float(distance), float(energy - shift), 0.0)
                    for distance, energy in zip(
                        distances, energies[spin_index, :, band_index]
                    )
                ),
            )
    _metadata(obj, dataset, energy_reference, "band_structure_curve_v1")
    obj["cb_structure_id"] = str(dataset.structure_id)
    obj["cb_spin_channels"] = list(dataset.spin_channels)
    obj["cb_kpoint_labels"] = [label or "" for label in dataset.labels]
    obj["cb_curve_order"] = "spin_major_band_minor"
    obj["cb_band_count"] = dataset.data.shape[2]
    return obj


def create_dos_plot(
    dataset,
    *,
    name="ChemBlender Density of States",
    collection=None,
    energy_reference=EnergyReference.FERMI_SHIFTED,
    mirror_beta=True,
):
    if not isinstance(dataset, DensityOfStates):
        raise TypeError("dataset must be a DensityOfStates")
    if not isinstance(mirror_beta, bool):
        raise TypeError("mirror_beta must be a bool")
    shift = _energy_shift(dataset, energy_reference)
    obj = _curve_object(name, collection)
    for spin_index, densities in enumerate(dataset.data.values):
        sign = -1.0 if mirror_beta and spin_index == 1 else 1.0
        _poly_spline(
            obj.data,
            tuple(
                (float(sign * density), float(energy - shift), 0.0)
                for density, energy in zip(densities, dataset.energies.values)
            ),
        )
    _metadata(obj, dataset, energy_reference, "density_of_states_curve_v1")
    obj["cb_structure_id"] = str(dataset.structure_id)
    obj["cb_spin_channels"] = list(dataset.spin_channels)
    obj["cb_curve_order"] = "spin_index"
    obj["cb_mirror_beta"] = mirror_beta
    obj["cb_density_unit"] = dataset.data.unit
    return obj


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
