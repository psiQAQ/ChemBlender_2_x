from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy

from ChemBlender.core import ArrayData, ImportBatch, parse_poscar


FIXTURES = Path(__file__).parent / "fixtures" / "poscar"


class PoscarRoundTripTests(unittest.TestCase):
    def test_direct_selective_dynamics_round_trips_semantically(self):
        from ChemBlender.core.exporters import (
            PoscarExportSettings,
            export_poscar,
            semantic_poscar_differences,
        )

        original = parse_poscar(FIXTURES / "cscl-selective.vasp")
        selective = next(
            value
            for value in original.datasets
            if value.semantic_role == "selective_dynamics"
        )
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "POSCAR"
            export_poscar(
                destination,
                original.structures[0],
                PoscarExportSettings(comment="selective", coordinate_mode="direct"),
                selective_dynamics=selective,
            )
            reparsed = parse_poscar(destination)

        self.assertEqual(semantic_poscar_differences(original, reparsed), ())

    def test_selected_ion_and_lattice_velocities_round_trip(self):
        from ChemBlender.core.exporters import (
            PoscarExportSettings,
            export_poscar,
            semantic_poscar_differences,
        )
        from ChemBlender.core.formats.poscar import parse_poscar_document

        source = FIXTURES / "velocities.CONTCAR"
        original = parse_poscar(source)
        document = parse_poscar_document(source.read_bytes())
        selective = next(
            value
            for value in original.datasets
            if value.semantic_role == "selective_dynamics"
        )
        velocity = next(
            value
            for value in original.datasets
            if value.semantic_role == "atomic_velocity"
        )
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "CONTCAR"
            export_poscar(
                destination,
                original.structures[0],
                PoscarExportSettings(
                    comment="velocity block",
                    coordinate_mode="cartesian",
                ),
                selective_dynamics=selective,
                velocities=velocity,
                lattice_velocities=document.lattice_velocities,
            )
            reparsed = parse_poscar(destination)
            exported_document = parse_poscar_document(destination.read_bytes())

        self.assertEqual(semantic_poscar_differences(original, reparsed), ())
        self.assertIsNotNone(exported_document.lattice_velocities)

    def test_velocity_mode_conversion_uses_the_structure_cell(self):
        from ChemBlender.core.exporters import (
            PoscarExportSettings,
            export_poscar,
            semantic_poscar_differences,
        )
        from ChemBlender.core.formats.poscar import parse_poscar_document

        source_text = """velocity basis
1
2 0 0
0 2 0
0 0 2
H
1
Direct
0 0 0
Direct
0.1 0.2 0.3
"""
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "source.POSCAR"
            source.write_text(source_text, encoding="utf-8")
            original = parse_poscar(source)
            velocity = next(
                value
                for value in original.datasets
                if value.semantic_role == "atomic_velocity"
            )

            converted = directory / "converted.POSCAR"
            export_poscar(
                converted,
                original.structures[0],
                PoscarExportSettings(velocity_mode="cartesian"),
                velocities=velocity,
            )
            converted_document = parse_poscar_document(
                converted.read_bytes()
            )
            reparsed = parse_poscar(converted)

            wrong = directory / "wrong.POSCAR"
            wrong.write_text(
                source_text.replace(
                    "\nDirect\n0.1 0.2 0.3\n",
                    "\nCartesian\n0.1 0.2 0.3\n",
                ),
                encoding="utf-8",
            )
            wrong_batch = parse_poscar(wrong)

        numpy.testing.assert_allclose(
            converted_document.velocities,
            ((0.2, 0.4, 0.6),),
        )
        self.assertEqual(semantic_poscar_differences(original, reparsed), ())
        self.assertEqual(
            semantic_poscar_differences(original, wrong_batch),
            ("atoms",),
        )

    def test_interleaved_species_are_grouped_without_semantic_loss(self):
        from ChemBlender.core.exporters import (
            export_poscar,
            semantic_poscar_differences,
        )

        original = parse_poscar(FIXTURES / "cscl.vasp")
        structure = original.structures[0]
        derived = replace(
            structure,
            revision="interleaved",
            atomic_numbers=(55, 17, 55),
            coordinates=ArrayData(
                numpy.asarray(
                    (
                        structure.coordinates.values[0],
                        structure.coordinates.values[1],
                        (1.0, 1.0, 1.0),
                    )
                ),
                ("atom", "xyz"),
                "angstrom",
            ),
            periodic=replace(
                structure.periodic,
                fractional_coordinates=ArrayData(
                    numpy.asarray(
                        (
                            structure.periodic.fractional_coordinates.values[0],
                            structure.periodic.fractional_coordinates.values[1],
                            numpy.asarray((1.0, 1.0, 1.0))
                            @ numpy.linalg.inv(structure.cell.values),
                        )
                    ),
                    ("atom", "xyz"),
                    "dimensionless",
                ),
                site_labels=("Cs1", "Cl1", "Cs2"),
                occupancies=ArrayData(
                    numpy.ones(3),
                    ("atom",),
                    "dimensionless",
                ),
                adp_types=("none",) * 3,
                disorder_groups=(0,) * 3,
                disorder_assemblies=("none",) * 3,
            ),
        )
        left = ImportBatch(structures=(derived,))
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "POSCAR"
            export_poscar(destination, derived)
            right = parse_poscar(destination)

        self.assertEqual(semantic_poscar_differences(left, right), ())


if __name__ == "__main__":
    unittest.main()
