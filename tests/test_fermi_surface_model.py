import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    FermiSurfaceMesh,
    ImportBatch,
    QCProject,
    SurfaceProperty,
)
from tests.test_periodic_electronic_model import band_structure, periodic_structure


def fermi_surface(structure_id, band_id):
    return FermiSurfaceMesh(
        id=uuid4(),
        revision="surface-revision",
        semantic_role="fermi_surface",
        domain="surface_vertex",
        data=ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            ("vertex", "xyz"),
            "inverse_angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure_id,
        band_structure_id=band_id,
        faces=ArrayData(
            numpy.asarray([[0, 1, 2]], dtype=numpy.int64),
            ("face", "corner"),
            "dimensionless",
        ),
        band_indices=ArrayData(
            numpy.asarray([1], dtype=numpy.int64), ("face",), "dimensionless"
        ),
        spin_index=0,
        fermi_energy=5.0,
        coordinate_convention="cartesian_reciprocal_2pi",
        properties=(
            SurfaceProperty(
                semantic_role="fermi_velocity",
                domain="vertex",
                data=ArrayData(
                    numpy.ones((3, 3)), ("vertex", "xyz"), "meter_per_second"
                ),
            ),
            SurfaceProperty(
                semantic_role="orbital_contribution",
                domain="vertex",
                data=ArrayData(
                    numpy.asarray([0.2, 0.4, 0.6]),
                    ("vertex",),
                    "dimensionless",
                ),
            ),
        ),
    )


class FermiSurfaceModelTests(unittest.TestCase):
    def test_project_commits_surface_linked_to_structure_and_band(self):
        structure = periodic_structure()
        band = band_structure(structure.id)
        surface = fermi_surface(structure.id, band.id)
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(
            ImportBatch(structures=(structure,), datasets=(band, surface))
        )
        self.assertIs(project.datasets[surface.id], surface)

    def test_project_rejects_dangling_or_mismatched_band(self):
        structure = periodic_structure()
        surface = fermi_surface(structure.id, uuid4())
        with self.assertRaisesRegex(ValueError, "band structure"):
            QCProject(id=uuid4(), schema_version="0.1").commit(
                ImportBatch(structures=(structure,), datasets=(surface,))
            )

        other = periodic_structure()
        band = band_structure(other.id)
        surface = fermi_surface(structure.id, band.id)
        with self.assertRaisesRegex(ValueError, "same structure"):
            QCProject(id=uuid4(), schema_version="0.1").commit(
                ImportBatch(structures=(structure, other), datasets=(band, surface))
            )

    def test_rejects_face_range_and_property_domain_shape(self):
        valid = fermi_surface(uuid4(), uuid4())
        common = {
            field: getattr(valid, field)
            for field in valid.__dataclass_fields__
            if field not in {"shape", "dtype", "faces", "properties"}
        }
        with self.assertRaisesRegex(ValueError, "face indices"):
            FermiSurfaceMesh(
                **common,
                faces=ArrayData(
                    numpy.asarray([[0, 1, 3]]),
                    ("face", "corner"),
                    "dimensionless",
                ),
                properties=valid.properties,
            )
        with self.assertRaisesRegex(ValueError, "surface property"):
            FermiSurfaceMesh(
                **common,
                faces=valid.faces,
                properties=(
                    SurfaceProperty(
                        semantic_role="bad",
                        domain="face",
                        data=ArrayData(
                            numpy.ones(3), ("face",), "dimensionless"
                        ),
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()
