import math
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData, PeriodicSiteData, Structure
from ChemBlender.core.phonon_frames import derive_phonon_frames
from tests.test_phonon_model import phonon_modes


def supercell_structure():
    return Structure(
        id=uuid4(),
        revision="supercell-revision",
        atomic_numbers=(14, 8, 14, 8),
        coordinates=ArrayData(
            numpy.asarray(
                [[0.0, 0.0, 0.0], [1.5, 1.5, 1.5], [3.0, 0.0, 0.0], [4.5, 1.5, 1.5]]
            ),
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=ArrayData(numpy.diag([6.0, 3.0, 3.0]), ("cell_vector", "xyz"), "angstrom"),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(
                numpy.asarray([[0.0, 0.0, 0.0], [0.25, 0.5, 0.5], [0.5, 0.0, 0.0], [0.75, 0.5, 0.5]]),
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=("Si1", "O1", "Si2", "O2"),
            occupancies=ArrayData(numpy.ones(4), ("atom",), "dimensionless"),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",) * 4,
            disorder_groups=(0,) * 4,
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=(),
            cif_envelope_id=None,
        ),
    )


class PhononFrameTests(unittest.TestCase):
    def test_complex_phase_mass_scaling_and_translation(self):
        primitive_id = uuid4()
        modes = phonon_modes(primitive_id)
        supercell = supercell_structure()
        batch = derive_phonon_frames(
            modes,
            supercell,
            primitive_atom_indices=[0, 1, 0, 1],
            translations=[[0, 0, 0], [0, 0, 0], [1, 0, 0], [1, 0, 0]],
            qpoint_index=0,
            mode_index=0,
            phases=[0.0, math.pi / 2],
            amplitude=2.0,
        )
        frames = batch.datasets[0]
        displacements = frames.data.values - supercell.coordinates.values
        self.assertTrue(numpy.allclose(displacements[0, 0], [1.0, 0.0, 0.0]))
        self.assertTrue(numpy.allclose(displacements[0, 2], [-1.0, 0.0, 0.0]))
        self.assertTrue(numpy.allclose(displacements[1, 0], [2.0, 0.0, 0.0]))
        self.assertTrue(numpy.allclose(displacements[1, 2], [-2.0, 0.0, 0.0]))
        self.assertEqual(frames.structure_id, supercell.id)
        parameters = dict(batch.provenance[0].parameters)
        self.assertEqual(parameters["frequency_terahertz"], -1.0)

    def test_rejects_invalid_mapping_and_zero_amplitude(self):
        modes = phonon_modes(uuid4())
        supercell = supercell_structure()
        with self.assertRaisesRegex(ValueError, "primitive_atom_indices"):
            derive_phonon_frames(
                modes,
                supercell,
                primitive_atom_indices=[0],
                translations=numpy.zeros((4, 3)),
                qpoint_index=0,
                mode_index=0,
                phases=[0.0],
            )
        with self.assertRaisesRegex(ValueError, "amplitude"):
            derive_phonon_frames(
                modes,
                supercell,
                primitive_atom_indices=[0, 1, 0, 1],
                translations=numpy.asarray([[0, 0, 0], [0, 0, 0], [1, 0, 0], [1, 0, 0]]),
                qpoint_index=0,
                mode_index=0,
                phases=[0.0],
                amplitude=0.0,
            )


if __name__ == "__main__":
    unittest.main()
