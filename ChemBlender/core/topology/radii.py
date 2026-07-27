from ...Chem_data import ELEMENTS_DEFAULT, metals


_BY_ATOMIC_NUMBER = {
    data[0]: float(data[5])
    for data in ELEMENTS_DEFAULT.values()
    if 0 < data[0] <= 118
}
_METAL_ATOMIC_NUMBERS = frozenset(
    ELEMENTS_DEFAULT[symbol][0] for symbol in metals
)


def covalent_radius_angstrom(atomic_number):
    return _BY_ATOMIC_NUMBER.get(atomic_number, 0.0)


def is_metal(atomic_number):
    return atomic_number in _METAL_ATOMIC_NUMBERS
