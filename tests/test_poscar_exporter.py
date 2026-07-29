from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy

from ChemBlender.core import Structure, parse_poscar


FIXTURES = Path(__file__).parent / "fixtures" / "poscar"


class PoscarExporterTests(unittest.TestCase):
    def test_preserve_source_scale_keeps_negative_volume_convention(self):
        from ChemBlender.core.exporters import (
            PoscarExportSettings,
            export_poscar,
        )
        from ChemBlender.core.formats.poscar import parse_poscar_document

        batch = parse_poscar(FIXTURES / "negative-scale.vasp")
        structure, = batch.structures
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "POSCAR"
            report = export_poscar(
                destination,
                structure,
                PoscarExportSettings(
                    comment="negative scale Cartesian",
                    coordinate_mode="cartesian",
                    scale_policy="preserve_source",
                    source_scale=-8.0,
                ),
            )
            document = parse_poscar_document(destination.read_bytes())

        self.assertTrue(report.written)
        self.assertEqual(report.entries[0].code, "scale_preserve_source")
        self.assertEqual(document.scale, -8.0)
        self.assertEqual(document.coordinate_mode, "cartesian")
        numpy.testing.assert_allclose(document.lattice, structure.cell.values)
        numpy.testing.assert_allclose(
            document.coordinates,
            structure.coordinates.values,
        )

    def test_target_volume_must_match_the_scientific_cell(self):
        from ChemBlender.core.exporters import (
            PoscarExportSettings,
            export_poscar,
        )

        structure = parse_poscar(FIXTURES / "cscl.vasp").structures[0]
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "target_volume"):
                export_poscar(
                    Path(directory) / "POSCAR",
                    structure,
                    PoscarExportSettings(
                        scale_policy="target_volume",
                        target_volume=1.0,
                    ),
                )

    def test_nonperiodic_or_unknown_species_is_rejected(self):
        from ChemBlender.core.exporters import export_poscar

        periodic = parse_poscar(FIXTURES / "cscl.vasp").structures[0]
        nonperiodic = Structure(
            id=periodic.id,
            revision="nonperiodic",
            atomic_numbers=periodic.atomic_numbers,
            coordinates=periodic.coordinates,
        )
        unknown = replace(periodic, atomic_numbers=(0, 17))
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "POSCAR"
            with self.assertRaisesRegex(TypeError, "periodic"):
                export_poscar(destination, nonperiodic)
            with self.assertRaisesRegex(ValueError, "atomic number"):
                export_poscar(destination, unknown)

    def test_settings_validate_modes_and_single_line_comment(self):
        from ChemBlender.core.exporters import PoscarExportSettings

        with self.assertRaisesRegex(ValueError, "coordinate_mode"):
            PoscarExportSettings(coordinate_mode="fractional")
        with self.assertRaisesRegex(ValueError, "scale_policy"):
            PoscarExportSettings(scale_policy="raw")
        with self.assertRaisesRegex(ValueError, "one line"):
            PoscarExportSettings(comment="bad\ncomment")


if __name__ == "__main__":
    unittest.main()
