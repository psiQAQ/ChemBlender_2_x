"""Shared transfer functions for native materials and their numeric legends."""

from math import isfinite


COLORMAPS = ("coolwarm", "esp", "nci", "viridis", "density")
_BLUE = (.23, .30, .75, 1.)
_RED = (.70, .02, .15, 1.)
_WHITE = (.95, .95, .95, 1.)
_SEQUENTIAL = {
    "viridis": ((.267, .005, .329, 1.), (.230, .322, .546, 1.),
                (.128, .567, .551, 1.), (.369, .789, .383, 1.),
                (.993, .906, .144, 1.)),
    "density": ((.018, .040, .16, 1.), (.02, .22, .52, 1.),
                (.06, .63, .78, 1.), (.70, .95, 1., 1.)),
}


def color_stops(color_min, color_max, colormap="coolwarm"):
    """Return normalized stops; a diverging midpoint is located at actual zero."""
    if (isinstance(color_min, bool) or isinstance(color_max, bool)
            or not all(isfinite(value) for value in (color_min, color_max))
            or color_min >= color_max):
        raise ValueError("color range must be finite and increasing")
    if colormap not in COLORMAPS:
        raise ValueError("unsupported scientific colormap")
    if colormap in _SEQUENTIAL:
        colors = _SEQUENTIAL[colormap]
        return tuple((index / (len(colors) - 1), color)
                     for index, color in enumerate(colors))
    negative, neutral, positive = _BLUE, _WHITE, _RED
    if colormap == "esp":
        negative, positive = _RED, _BLUE
    elif colormap == "nci":
        neutral = (.05, .80, .12, 1.)

    def color(value):
        edge = negative if value < 0 else positive
        extent = -color_min if value < 0 else color_max
        weight = abs(value) / extent if value else 0.
        return tuple(a + weight * (b - a) for a, b in zip(neutral, edge))

    stops = [(0., color(color_min)), (1., color(color_max))]
    if color_min < 0 < color_max:
        stops.insert(1, (-color_min / (color_max - color_min), neutral))
    return tuple(stops)
