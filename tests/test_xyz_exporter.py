from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core.exporters.xyz import export_xyz
from ChemBlender.core.model import ArrayData, Structure


def _structure(*, unit="angstrom"):
    return Structure(
        id=uuid4(),
        revision="structure-r1",
        atomic_numbers=(8, 1, 1),
        coordinates=ArrayData(
            numpy.asarray(
                (
                    (-0.0, 0.0, 0.0),
                    (0.0, 0.0, 1.25),
                    (1.0, -2.5, 0.0),
                ),
                dtype=numpy.float64,
            ),
            ("atom", "xyz"),
            unit,
        ),
    )


class XYZExporterTests(unittest.TestCase):
    def test_structure_exports_deterministic_finite_xyz_with_final_newline(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "water.xyz"

            report = export_xyz(
                destination,
                _structure(),
                title="water sample",
            )

            self.assertEqual(
                destination.read_bytes(),
                (
                    b"3\n"
                    b"water sample\n"
                    b"O 0 0 0\n"
                    b"H 0 0 1.25\n"
                    b"H 1 -2.5 0\n"
                ),
            )
            self.assertTrue(report.written)
            self.assertFalse(report.requires_confirmation)
            self.assertEqual(report.entries, ())

    def test_unsupported_unit_and_nonfinite_values_do_not_replace_destination(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "structure.xyz"
            destination.write_bytes(b"existing\n")

            with self.assertRaisesRegex(ValueError, "angstrom"):
                export_xyz(destination, _structure(unit="bohr"))
            self.assertEqual(destination.read_bytes(), b"existing\n")

            structure = _structure()
            structure.coordinates.values[0, 0] = numpy.nan
            with self.assertRaisesRegex(ValueError, "finite"):
                export_xyz(destination, structure)
            self.assertEqual(destination.read_bytes(), b"existing\n")


if __name__ == "__main__":
    unittest.main()
