from dataclasses import replace
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData, PeriodicSiteData, Structure
from ChemBlender.views.periodic import (
    PeriodicViewSettings,
    _cell_edge_geometry,
    _periodic_render_attributes,
)


def structure():
    cell = numpy.asarray(
        (
            (2.0, 0.0, 0.0),
            (0.5, 3.0, 0.0),
            (0.2, 0.3, 4.0),
        )
    )
    fractional = numpy.asarray(((0.0, 0.0, 0.0), (0.5, 0.5, 0.5)))
    return Structure(
        id=uuid4(),
        revision="node-contract-r1",
        atomic_numbers=(6, 8),
        coordinates=ArrayData(
            fractional @ cell,
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=ArrayData(cell, ("cell_vector", "xyz"), "angstrom"),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(
                fractional,
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=("C1", "O1"),
            occupancies=ArrayData(
                numpy.asarray((0.25, numpy.nan)),
                ("atom",),
                "dimensionless",
            ),
            isotropic_displacements=None,
            anisotropic_displacements=ArrayData(
                numpy.asarray(
                    (
                        (0.04, 0.09, 0.16, 0.0, 0.0, 0.0),
                        (numpy.nan,) * 6,
                    )
                ),
                ("atom", "tensor_component"),
                "angstrom_squared",
            ),
            adp_types=("uani", "none"),
            disorder_groups=(0, 0),
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=("x,y,z",),
            cif_envelope_id=None,
        ),
    )


class CrystalNodeContractTests(unittest.TestCase):
    def test_cell_edges_use_full_oblique_matrix_and_supercell_extent(self):
        reference = structure()

        vertices, edges = _cell_edge_geometry(
            reference,
            supercell=(2, 1, 1),
        )

        self.assertEqual(len(vertices), 8)
        self.assertEqual(len(edges), 12)
        numpy.testing.assert_allclose(vertices[0], (0.0, 0.0, 0.0))
        numpy.testing.assert_allclose(vertices[4], (4.0, 0.0, 0.0))
        numpy.testing.assert_allclose(vertices[7], (4.7, 3.3, 4.0))

    def test_occupancy_and_adp_attributes_preserve_missing_quality(self):
        attributes = _periodic_render_attributes(
            structure(),
            PeriodicViewSettings(
                occupancy_mode="radius",
                adp_probability=0.50,
            ),
        )

        self.assertEqual(attributes["cbq_occupancy_valid"], (True, False))
        numpy.testing.assert_allclose(
            attributes["cbq_occupancy_alpha"],
            (0.25, 1.0),
        )
        numpy.testing.assert_allclose(
            attributes["cbq_occupancy_radius"],
            (0.25 ** (1.0 / 3.0), 1.0),
        )
        self.assertEqual(attributes["cbq_adp_valid"], (True, False))
        first_scale = attributes["cbq_adp_scale"][0]
        self.assertGreater(first_scale[2], first_scale[1])
        self.assertGreater(first_scale[1], first_scale[0])
        self.assertEqual(
            attributes["cbq_adp_scale"][1],
            (0.2, 0.2, 0.2),
        )
        self.assertEqual(attributes["cbq_quality_badge"], (0, 3))

    def test_oblique_cif_uij_is_orthogonalized_before_eigendecomposition(self):
        reference = structure()
        values = numpy.asarray(
            reference.periodic.anisotropic_displacements.values
        ).copy()
        values[0] = (0.04, 0.09, 0.16, 0.01, 0.02, 0.03)
        reference = replace(
            reference,
            periodic=replace(
                reference.periodic,
                anisotropic_displacements=ArrayData(
                    values,
                    ("atom", "tensor_component"),
                    "angstrom_squared",
                ),
            ),
        )

        attributes = _periodic_render_attributes(
            reference,
            PeriodicViewSettings(adp_probability=0.50),
        )

        scales = numpy.asarray(attributes["cbq_adp_scale"][0]) / 1.5382
        self.assertAlmostEqual(
            float(numpy.sum(scales**2) / 3.0),
            0.10197393720337268,
            places=12,
        )

    def test_render_attributes_follow_derived_source_and_rotation(self):
        reference = structure()
        rotation = numpy.asarray(
            ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        )

        attributes = _periodic_render_attributes(
            reference,
            PeriodicViewSettings(),
            source_atom_ids=(0,),
            rotations=(rotation,),
        )

        self.assertEqual(attributes["cbq_occupancy_valid"], (True,))
        self.assertEqual(attributes["cbq_adp_valid"], (True,))
        self.assertGreater(
            attributes["cbq_adp_scale"][0][2],
            attributes["cbq_adp_scale"][0][0],
        )

    def test_adp_probability_changes_ellipsoid_scale(self):
        reference = structure()

        median = _periodic_render_attributes(
            reference,
            PeriodicViewSettings(adp_probability=0.50),
        )
        high = _periodic_render_attributes(
            reference,
            PeriodicViewSettings(adp_probability=0.95),
        )

        self.assertTrue(
            numpy.all(
                numpy.asarray(high["cbq_adp_scale"][0])
                > numpy.asarray(median["cbq_adp_scale"][0])
            )
        )

    def test_partial_uij_uses_uiso_fallback_but_keeps_quality_badge(self):
        reference = structure()
        reference = replace(
            reference,
            periodic=replace(
                reference.periodic,
                isotropic_displacements=ArrayData(
                    numpy.asarray((0.09, numpy.nan)),
                    ("atom",),
                    "angstrom_squared",
                ),
                anisotropic_displacements=ArrayData(
                    numpy.asarray(
                        (
                            (numpy.nan,) * 6,
                            (numpy.nan,) * 6,
                        )
                    ),
                    ("atom", "tensor_component"),
                    "angstrom_squared",
                ),
            ),
        )

        attributes = _periodic_render_attributes(
            reference,
            PeriodicViewSettings(adp_probability=0.50),
        )

        self.assertFalse(attributes["cbq_adp_valid"][0])
        numpy.testing.assert_allclose(
            attributes["cbq_adp_scale"][0],
            (1.5382 * 0.3,) * 3,
        )
        self.assertEqual(attributes["cbq_quality_badge"][0] & 2, 2)


if __name__ == "__main__":
    unittest.main()
