import operator
import re
from dataclasses import dataclass, field


_UNIT_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True, slots=True)
class ArrayData:
    values: object
    dims: tuple[str, ...]
    unit: str
    shape: tuple[int, ...] = field(init=False)
    dtype: str = field(init=False)

    def __post_init__(self):
        try:
            raw_shape = self.values.shape
        except AttributeError as error:
            raise TypeError("values must expose a shape") from error

        shape = []
        for dimension in raw_shape:
            if isinstance(dimension, bool):
                raise ValueError("array dimensions must be non-negative integers")
            try:
                size = operator.index(dimension)
            except TypeError as error:
                raise ValueError(
                    "array dimensions must be non-negative integers"
                ) from error
            if size < 0:
                raise ValueError("array dimensions must be non-negative integers")
            shape.append(size)

        dims = tuple(self.dims)
        if len(shape) != len(dims):
            raise ValueError("dims must match array rank")
        if len(set(dims)) != len(dims) or any(
            not isinstance(dim, str) or not dim for dim in dims
        ):
            raise ValueError("dims must be unique non-empty names")
        if not isinstance(self.unit, str) or not _UNIT_PATTERN.fullmatch(self.unit):
            raise ValueError("unit must be a lower_snake_case token")

        dtype = getattr(self.values, "dtype", getattr(self.values, "format", "unknown"))
        object.__setattr__(self, "dims", dims)
        object.__setattr__(self, "shape", tuple(shape))
        object.__setattr__(self, "dtype", str(dtype))
