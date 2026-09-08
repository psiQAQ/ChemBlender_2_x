from dataclasses import replace
import unittest
from uuid import uuid4

import numpy as np

from ChemBlender.core.grid_semantics import validate_nci_pair, resolve_grid_semantics
from ChemBlender.core.model import ArrayData, DatasetStatus
from tests.test_grid_difference import density


class NCIPairTests(unittest.TestCase):
    def test_pairing_and_scientific_validation(self):
        sid = uuid4()
        rdg = density(sid, np.ones((3, 3, 3)), semantic_role="reduced_density_gradient")
        rdg = replace(rdg, data=ArrayData(rdg.data.values, rdg.data.dims, "dimensionless"))
        signed = density(sid, np.linspace(-.03, .06, 27).reshape(3, 3, 3), semantic_role="sign_lambda2_rho")
        with self.assertRaisesRegex(ValueError, "Confirm"):
            validate_nci_pair(rdg, signed)
        validate_nci_pair(rdg, signed, pairing_confirmed=True)
        calculation = uuid4()
        validate_nci_pair(replace(rdg, source_calculation=calculation),
                          replace(signed, source_calculation=calculation))
        for changes in ({"structure_id": uuid4()}, {"structure_id": None},
                        {"origin": (0., 0., 0.)}, {"status": DatasetStatus.AMBIGUOUS},
                        {"semantic_role": "electron_density"},
                        {"data": ArrayData(np.ones((3, 3, 3)), ("x", "y", "z"), "dimensionless")}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_nci_pair(rdg, replace(signed, **changes), pairing_confirmed=True)
        for value in (-.01, np.nan, np.inf, 1j):
            bad = replace(rdg, data=ArrayData(np.full((3, 3, 3), value), rdg.data.dims, "dimensionless"))
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_nci_pair(bad, signed, pairing_confirmed=True)
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            resolve_grid_semantics(replace(rdg, status=DatasetStatus.AMBIGUOUS,
                data=ArrayData(-rdg.data.values, rdg.data.dims, "dimensionless")),
                dataset_index=0, preset_id="reduced_density_gradient", value_unit="dimensionless")
        multiple = replace(rdg, data=ArrayData(np.stack((-rdg.data.values, rdg.data.values)),
                                               ("dataset", "x", "y", "z"), "dimensionless"))
        validate_nci_pair(multiple, signed, surface_dataset_index=1, pairing_confirmed=True)
        with self.assertRaises(IndexError):
            validate_nci_pair(multiple, signed, surface_dataset_index=2, pairing_confirmed=True)
        np.testing.assert_array_equal(rdg.data.values, 1.)


if __name__ == "__main__":
    unittest.main()
