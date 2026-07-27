from dataclasses import dataclass

from .arrays import ArrayData
from .categorical import CategoricalData


def _integer_atom_array(value, name, *, non_negative=False):
    import numpy

    if not isinstance(value, ArrayData):
        raise TypeError(f"{name} must be ArrayData")
    values = numpy.asarray(value.values)
    if (
        value.dims != ("atom",)
        or value.unit != "dimensionless"
        or values.dtype.kind not in "iu"
        or values.dtype.kind == "b"
        or values.dtype.hasobject
        or (non_negative and numpy.any(values < 0))
    ):
        raise TypeError(f"{name} must use a dimensionless integer atom array")
    return value


def _categorical_atom_array(value, name):
    if not isinstance(value, CategoricalData):
        raise TypeError(f"{name} must be CategoricalData")
    if value.dims != ("atom",) or value.unit != "dimensionless":
        raise ValueError(f"{name} must use a dimensionless atom axis")
    return value


@dataclass(frozen=True, slots=True)
class AtomicIdentityData:
    isotopes: ArrayData
    formal_charges: ArrayData
    atom_map_numbers: ArrayData
    atom_names: CategoricalData
    stereo_labels: CategoricalData

    def __post_init__(self):
        _integer_atom_array(self.isotopes, "isotopes", non_negative=True)
        _integer_atom_array(self.formal_charges, "formal_charges")
        _integer_atom_array(self.atom_map_numbers, "atom_map_numbers", non_negative=True)
        _categorical_atom_array(self.atom_names, "atom_names")
        _categorical_atom_array(self.stereo_labels, "stereo_labels")
        lengths = {
            self.isotopes.shape[0],
            self.formal_charges.shape[0],
            self.atom_map_numbers.shape[0],
            self.atom_names.shape[0],
            self.stereo_labels.shape[0],
        }
        if len(lengths) != 1:
            raise ValueError("atomic identity values must share one atom dimension")

    @property
    def atom_count(self):
        return self.isotopes.shape[0]
