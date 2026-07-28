import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy

from ChemBlender.core import ArrayData, parse_cif
from ChemBlender.core.exporters import export_cif


class CIFControlledRoundTripTests(unittest.TestCase):
    def test_changed_selected_block_preserves_other_blocks_and_unknown_values(self):
        content = b"""data_first
_cell_length_a 4
_cell_length_b 4
_cell_length_c 4
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_custom_first 'keep first'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0 0 0

data_second
_custom_second 'keep second'
"""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "multi.cif"
            destination = Path(directory) / "exported.cif"
            source.write_bytes(content)
            batch = parse_cif(source)
            structure = batch.structures[0]
            periodic = replace(
                structure.periodic,
                occupancies=ArrayData(
                    numpy.asarray([0.5]),
                    ("atom",),
                    "dimensionless",
                ),
            )
            export_cif(
                destination,
                replace(structure, periodic=periodic),
                envelope=batch.cif_envelopes[0],
                mode="preserve",
            )
            output = destination.read_text(encoding="utf-8")
            reparsed = parse_cif(destination)

        self.assertIn("_custom_first 'keep first'", output)
        self.assertIn("_custom_second 'keep second'", output)
        self.assertEqual(reparsed.cif_envelopes[0].block_names, ("first", "second"))
        self.assertEqual(
            float(reparsed.structures[0].periodic.occupancies.values[0]),
            0.5,
        )


if __name__ == "__main__":
    unittest.main()
