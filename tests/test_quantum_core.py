import array
import subprocess
import sys
import unittest

from ChemBlender.core import ArrayData


def array_view(values, shape):
    raw = memoryview(array.array("d", values))
    return raw.cast("B").cast("d", shape=shape)


class QuantumCoreTests(unittest.TestCase):
    def test_core_import_does_not_load_bpy(self):
        code = "import sys; import ChemBlender.core; assert 'bpy' not in sys.modules"
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_array_data_reads_shape_dtype_and_unit(self):
        data = ArrayData(
            array_view(range(6), (2, 3)),
            ("atom", "xyz"),
            "angstrom",
        )
        self.assertEqual(data.shape, (2, 3))
        self.assertEqual(data.dtype, "d")

    def test_array_data_rejects_invalid_dimensions_and_units(self):
        values = array_view(range(6), (2, 3))
        cases = (
            (("atom",), "angstrom"),
            (("atom", "atom"), "angstrom"),
            (("atom", "xyz"), ""),
        )
        for dims, unit in cases:
            with self.subTest(dims=dims, unit=unit):
                with self.assertRaises(ValueError):
                    ArrayData(values, dims, unit)


if __name__ == "__main__":
    unittest.main()
