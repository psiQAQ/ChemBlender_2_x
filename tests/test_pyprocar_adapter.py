import subprocess
import sys
import unittest

import numpy

from ChemBlender.core import IssueKind, QCProject
from ChemBlender.core.pyprocar_adapter import adapt_pyprocar_fermi_surface
from tests.test_periodic_electronic_model import band_structure, periodic_structure


class FakeSurface:
    def __init__(self):
        self.points = numpy.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]
        )
        self.faces = numpy.asarray([3, 0, 1, 2, 3, 0, 2, 3])
        self.point_data = {
            "fermi_velocity": numpy.arange(12.0).reshape((4, 3)),
            "fermi_speed": numpy.arange(4.0),
            "spin": numpy.ones((4, 3)),
            "scalars": numpy.linspace(0.1, 0.4, 4),
            "unknown": numpy.ones(4),
        }
        self.cell_data = {"band_index": numpy.asarray([0, 1])}
        self.band_isosurface_index_map = {1: 0, 3: 1}


class PyProcarAdapterTests(unittest.TestCase):
    def test_maps_mesh_band_identity_and_allowed_properties(self):
        structure = periodic_structure()
        band = band_structure(structure.id)
        batch = adapt_pyprocar_fermi_surface(
            FakeSurface(), band, spin_index=1, fermi_energy=5.25
        )
        surface = batch.datasets[0]
        self.assertEqual(surface.faces.values.tolist(), [[0, 1, 2], [0, 2, 3]])
        self.assertEqual(surface.band_indices.values.tolist(), [1, 3])
        self.assertEqual(surface.spin_index, 1)
        properties = {prop.semantic_role: prop for prop in surface.properties}
        self.assertEqual(
            set(properties),
            {"fermi_velocity", "fermi_speed", "spin_texture", "orbital_contribution"},
        )
        self.assertEqual(properties["fermi_velocity"].data.unit, "meter_per_second")
        self.assertEqual(properties["spin_texture"].data.dims, ("vertex", "xyz"))
        warnings = {
            issue.path for issue in batch.report.issues if issue.kind is IssueKind.UNSUPPORTED
        }
        self.assertEqual(warnings, {"pyprocar.point_data.unknown"})
        project = QCProject(id=structure.id, schema_version="0.1")
        project.commit(
            type(batch)(structures=(structure,), datasets=(band,))
        )
        project.commit(batch)

    def test_rejects_non_triangular_or_missing_band_data(self):
        structure = periodic_structure()
        band = band_structure(structure.id)
        surface = FakeSurface()
        surface.faces = numpy.asarray([4, 0, 1, 2, 3])
        with self.assertRaisesRegex(ValueError, "triangulated"):
            adapt_pyprocar_fermi_surface(surface, band, spin_index=0, fermi_energy=5.0)
        surface = FakeSurface()
        surface.cell_data = {}
        with self.assertRaisesRegex(ValueError, "band_index"):
            adapt_pyprocar_fermi_surface(surface, band, spin_index=0, fermi_energy=5.0)

    def test_core_import_does_not_eagerly_load_pyprocar_or_pyvista(self):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import ChemBlender.core; assert 'pyprocar' not in sys.modules; assert 'pyvista' not in sys.modules",
            ],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
