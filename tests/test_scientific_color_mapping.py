import unittest

from ChemBlender.core.color_mapping import COLORMAPS, color_stops


class ScientificColorMappingTests(unittest.TestCase):
    def test_true_zero_and_quantity_palettes(self):
        for palette in ("coolwarm", "esp", "nci"):
            stops = color_stops(-2., 1., palette)
            self.assertEqual(stops[1][0], 2. / 3.)
            self.assertEqual(len(stops), 3)
        self.assertEqual(color_stops(-1, 1, "esp")[0][1],
                         color_stops(-1, 1)[-1][1])
        self.assertGreater(color_stops(-1, 1, "nci")[1][1][1], .7)
        for palette in COLORMAPS:
            for limits in ((-2., 1.), (.2, 1.), (-2., -.3)):
                stops = color_stops(*limits, palette)
                self.assertEqual((stops[0][0], stops[-1][0]), (0., 1.))
                self.assertTrue(all(0 <= channel <= 1 for _, color in stops for channel in color))
        for limits in ((1, 1), (2, 1), (float("nan"), 1), (0, float("inf"))):
            with self.assertRaises(ValueError):
                color_stops(*limits)


if __name__ == "__main__":
    unittest.main()
