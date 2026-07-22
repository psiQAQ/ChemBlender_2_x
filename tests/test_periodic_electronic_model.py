import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    BandPathBranch,
    BandStructure,
    DatasetStatus,
    DensityOfStates,
    EnergyReference,
    ImportBatch,
    PeriodicSiteData,
    QCProject,
    Structure,
)


def periodic_structure():
    return Structure(
        id=uuid4(),
        revision="structure-revision",
        atomic_numbers=(14, 8),
        coordinates=ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0], [1.5, 1.5, 1.5]]),
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=ArrayData(
            numpy.eye(3) * 3.0, ("cell_vector", "xyz"), "angstrom"
        ),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(
                numpy.asarray([[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]]),
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=("Si1", "O1"),
            occupancies=ArrayData(
                numpy.ones(2), ("atom",), "dimensionless"
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none", "none"),
            disorder_groups=(0, 0),
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=(),
            cif_envelope_id=None,
        ),
    )


def band_structure(structure_id):
    return BandStructure(
        id=uuid4(),
        revision="band-revision",
        semantic_role="band_structure",
        domain="band",
        data=ArrayData(
            numpy.arange(24.0).reshape((2, 3, 4)),
            ("spin", "kpoint", "band"),
            "electron_volt",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure_id,
        occupations=ArrayData(
            numpy.ones((2, 3, 4)),
            ("spin", "kpoint", "band"),
            "dimensionless",
        ),
        kpoints=ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [0.5, 0.5, 0.0]]),
            ("kpoint", "reciprocal_axis"),
            "dimensionless",
        ),
        reciprocal_lattice=ArrayData(
            numpy.eye(3),
            ("reciprocal_vector", "cartesian_axis"),
            "inverse_angstrom",
        ),
        distances=ArrayData(
            numpy.asarray([0.0, 0.5, 1.0]),
            ("kpoint",),
            "inverse_angstrom",
        ),
        spin_channels=("alpha", "beta"),
        labels=("GAMMA", None, "X"),
        branches=(BandPathBranch(0, 2, "GAMMA", "X"),),
        projections=ArrayData(
            numpy.ones((2, 3, 4, 2, 3)),
            ("spin", "kpoint", "band", "atom", "orbital"),
            "dimensionless",
        ),
        orbital_labels=("s", "py", "pz"),
        fermi_energy=5.0,
        energy_reference=EnergyReference.ABSOLUTE,
    )


def density_of_states(structure_id):
    return DensityOfStates(
        id=uuid4(),
        revision="dos-revision",
        semantic_role="density_of_states",
        domain="energy",
        data=ArrayData(
            numpy.ones((2, 5)),
            ("spin", "energy"),
            "states_per_electron_volt",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure_id,
        energies=ArrayData(
            numpy.linspace(-1.0, 1.0, 5), ("energy",), "electron_volt"
        ),
        spin_channels=("alpha", "beta"),
        projections=ArrayData(
            numpy.ones((2, 5, 2, 3)),
            ("spin", "energy", "atom", "orbital"),
            "states_per_electron_volt",
        ),
        orbital_labels=("s", "py", "pz"),
        fermi_energy=0.2,
        energy_reference=EnergyReference.ABSOLUTE,
    )


class PeriodicElectronicModelTests(unittest.TestCase):
    def test_project_commits_band_and_dos_with_shared_structure(self):
        structure = periodic_structure()
        band = band_structure(structure.id)
        dos = density_of_states(structure.id)
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(
            ImportBatch(structures=(structure,), datasets=(band, dos))
        )
        self.assertIs(project.datasets[band.id], band)
        self.assertIs(project.datasets[dos.id], dos)

    def test_project_rejects_dangling_structure_references(self):
        project = QCProject(id=uuid4(), schema_version="0.1")
        with self.assertRaisesRegex(ValueError, "BandStructure.*structure"):
            project.commit(ImportBatch(datasets=(band_structure(uuid4()),)))
        with self.assertRaisesRegex(ValueError, "DensityOfStates.*structure"):
            project.commit(ImportBatch(datasets=(density_of_states(uuid4()),)))

    def test_band_rejects_projection_or_occupation_shape_mismatch(self):
        structure_id = uuid4()
        valid = band_structure(structure_id)
        with self.assertRaisesRegex(ValueError, "occupations"):
            BandStructure(
                **{
                    field: getattr(valid, field)
                    for field in valid.__dataclass_fields__
                    if field not in {"shape", "dtype", "occupations"}
                },
                occupations=ArrayData(
                    numpy.ones((2, 4, 3)),
                    ("spin", "kpoint", "band"),
                    "dimensionless",
                ),
            )

    def test_dos_rejects_non_monotonic_energy_axis(self):
        valid = density_of_states(uuid4())
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            DensityOfStates(
                **{
                    field: getattr(valid, field)
                    for field in valid.__dataclass_fields__
                    if field not in {"shape", "dtype", "energies"}
                },
                energies=ArrayData(
                    numpy.asarray([0.0, 1.0, 0.5, 2.0, 3.0]),
                    ("energy",),
                    "electron_volt",
                ),
            )


if __name__ == "__main__":
    unittest.main()
