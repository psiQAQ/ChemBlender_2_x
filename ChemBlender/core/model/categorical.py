from dataclasses import dataclass

from .arrays import ArrayData


@dataclass(frozen=True, slots=True)
class CategoricalData:
    codes: ArrayData
    categories: tuple[str, ...]
    missing_code: int

    def __post_init__(self):
        import numpy

        if not isinstance(self.codes, ArrayData):
            raise TypeError("codes must be ArrayData")
        if self.codes.unit != "dimensionless":
            raise ValueError("categorical codes must be dimensionless")
        if numpy.dtype(self.codes.dtype).kind not in "iu":
            raise TypeError("categorical codes must use an integer dtype")
        categories = tuple(self.categories)
        if any(not isinstance(category, str) for category in categories):
            raise TypeError("categories must contain strings")
        if len(categories) != len(set(categories)):
            raise ValueError("categories must be unique")
        if isinstance(self.missing_code, bool) or not isinstance(
            self.missing_code, int
        ):
            raise TypeError("missing_code must be an integer")
        if 0 <= self.missing_code < len(categories):
            raise ValueError("missing_code must not identify a category")
        codes = numpy.asarray(self.codes.values)
        if numpy.any(
            (codes != self.missing_code)
            & ((codes < 0) | (codes >= len(categories)))
        ):
            raise ValueError("categorical code has no matching category")
        object.__setattr__(self, "categories", categories)

    @property
    def dims(self):
        return self.codes.dims

    @property
    def shape(self):
        return self.codes.shape

    @property
    def unit(self):
        return self.codes.unit

    @property
    def dtype(self):
        return self.codes.dtype
