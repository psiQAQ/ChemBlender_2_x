import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    ImportBatch,
    PhononModeSet,
    QCProject,
)
from tests.test_periodic_electronic_model import periodic_structure


def phonon_modes(structure_id):
    eigenvectors = numpy.zeros((1, 6, 2, 3), dtype=complex)
    eigenvectors[0, 0, 0, 0] = 1.0 + 2.0j
    return PhononModeSet(
        id=uuid4(),
        revision="phonon-revision",
        semantic_role="phonon_modes",
        domain="mode",
        data=ArrayData(
            numpy.asarray([[-1.0, 2.0, 3.0, 4.0, 5.0, 6.0]]),
            ("qpoint", "mode"),
            "terahertz",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure_id,
        qpoints=ArrayData(
            numpy.asarray([[0.5, 0.0, 0.0]]),
            ("qpoint", "reciprocal_axis"),
            "dimensionless",
        ),
        eigenvectors=ArrayData(
            eigenvectors,
            ("qpoint", "mode", "atom", "xyz"),
            "dimensionless",
        ),
        masses=ArrayData(
            numpy.asarray([4.0, 16.0]), ("atom",), "atomic_mass_unit"
        ),
        group_velocities=None,
        weights=ArrayData(
            numpy.asarray([1.0]), ("qpoint",), "dimensionless"
        ),
        eigenvector_convention="phonopy_mass_weighted_dynamical_matrix",
    )


class PhononModelTests(unittest.TestCase):
    def test_project_commits_complex_modes_with_primitive_structure(self):
        structure = periodic_structure()
        modes = phonon_modes(structure.id)
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(ImportBatch(structures=(structure,), datasets=(modes,)))
        self.assertIn("complex", modes.eigenvectors.dtype)
        self.assertLess(modes.data.values[0, 0], 0.0)

    def test_project_rejects_dangling_or_wrong_atom_axis(self):
        with self.assertRaisesRegex(ValueError, "PhononModeSet.*structure"):
            QCProject(id=uuid4(), schema_version="0.1").commit(
                ImportBatch(datasets=(phonon_modes(uuid4()),))
            )
        structure = periodic_structure()
        valid = phonon_modes(structure.id)
        broken = PhononModeSet(
            **{
                field: getattr(valid, field)
                for field in valid.__dataclass_fields__
                if field not in {"shape", "dtype", "data", "eigenvectors", "masses"}
            },
            data=ArrayData(
                numpy.ones((1, 3)), ("qpoint", "mode"), "terahertz"
            ),
            eigenvectors=ArrayData(
                numpy.zeros((1, 3, 1, 3), dtype=complex),
                ("qpoint", "mode", "atom", "xyz"),
                "dimensionless",
            ),
            masses=ArrayData(
                numpy.ones(1), ("atom",), "atomic_mass_unit"
            ),
        )
        with self.assertRaisesRegex(ValueError, "atom dimension"):
            QCProject(id=uuid4(), schema_version="0.1").commit(
                ImportBatch(structures=(structure,), datasets=(broken,))
            )

    def test_mode_count_must_equal_three_times_atom_count(self):
        valid = phonon_modes(uuid4())
        with self.assertRaisesRegex(ValueError, "three modes per atom"):
            PhononModeSet(
                **{
                    field: getattr(valid, field)
                    for field in valid.__dataclass_fields__
                    if field not in {"shape", "dtype", "data", "eigenvectors"}
                },
                data=ArrayData(
                    numpy.ones((1, 5)), ("qpoint", "mode"), "terahertz"
                ),
                eigenvectors=ArrayData(
                    numpy.zeros((1, 5, 2, 3), dtype=complex),
                    ("qpoint", "mode", "atom", "xyz"),
                    "dimensionless",
                ),
            )


if __name__ == "__main__":
    unittest.main()
