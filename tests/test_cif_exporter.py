import tempfile
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy

from ChemBlender.core import ArrayData, parse_cif
from ChemBlender.core.exporters import export_cif, plan_cif_export


FIXTURE = Path(__file__).parent / "fixtures" / "cif" / "partial-disorder.cif"


class CIFExporterTests(unittest.TestCase):
    def test_exporter_import_does_not_load_gemmi(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import ChemBlender.core.exporters; "
                    "raise SystemExit('gemmi' in sys.modules)"
                ),
            ],
            check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_unchanged_preserve_plan_and_export_keep_source_envelope(self):
        batch = parse_cif(FIXTURE)
        structure = batch.structures[0]
        envelope = batch.cif_envelopes[0]

        plan = plan_cif_export(
            structure,
            envelope=envelope,
            mode="preserve",
        )
        actions = {field.name: field.action for field in plan.fields}
        self.assertEqual(actions["cell"], "preserve")
        self.assertEqual(actions["atom_site"], "preserve")
        self.assertEqual(actions["occupancy"], "preserve")
        self.assertEqual(actions["declared_symmetry"], "preserve")
        self.assertEqual(actions["unknown_content"], "preserve")

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "preserved.cif"
            report = export_cif(
                destination,
                structure,
                envelope=envelope,
                mode="preserve",
            )
            reparsed = parse_cif(destination)
            self.assertTrue(report.written)
            self.assertIn(
                "_chemblender_unknown_tag",
                destination.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                reparsed.structures[0].periodic.site_labels,
                structure.periodic.site_labels,
            )

    def test_preserve_mode_patches_supported_fields(self):
        batch = parse_cif(FIXTURE)
        source = batch.structures[0]
        periodic = replace(
            source.periodic,
            fractional_coordinates=ArrayData(
                numpy.asarray([[0.2, 0.3, 0.4]]),
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=("C2",),
            occupancies=ArrayData(
                numpy.asarray([0.75]),
                ("atom",),
                "dimensionless",
            ),
            isotropic_displacements=ArrayData(
                numpy.asarray([0.02]),
                ("atom",),
                "angstrom_squared",
            ),
            anisotropic_displacements=ArrayData(
                numpy.asarray([[0.02, 0.03, 0.04, 0.001, 0.002, 0.003]]),
                ("atom", "tensor_component"),
                "angstrom_squared",
            ),
            adp_types=("Uiso",),
            disorder_assemblies=("A",),
            declared_space_group_name="P -1",
            declared_space_group_number=2,
            declared_hall_symbol="-P 1",
            symmetry_operations=("x,y,z", "-x,-y,-z"),
        )
        changed = replace(
            source,
            coordinates=ArrayData(
                numpy.asarray(periodic.fractional_coordinates.values)
                @ numpy.asarray(source.cell.values),
                ("atom", "xyz"),
                "angstrom",
            ),
            periodic=periodic,
        )

        plan = plan_cif_export(
            changed,
            envelope=batch.cif_envelopes[0],
            mode="preserve",
        )
        actions = {field.name: field.action for field in plan.fields}
        self.assertEqual(actions["atom_site"], "replace")
        self.assertEqual(actions["occupancy"], "replace")
        self.assertEqual(actions["u_iso"], "add")
        self.assertEqual(actions["u_aniso"], "add")
        self.assertEqual(actions["adp_type"], "add")
        self.assertEqual(actions["disorder_group"], "preserve")
        self.assertEqual(actions["disorder_assembly"], "add")
        self.assertEqual(actions["declared_symmetry"], "replace")

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "changed.cif"
            export_cif(
                destination,
                changed,
                envelope=batch.cif_envelopes[0],
                mode="preserve",
            )
            reparsed = parse_cif(destination).structures[0]
            content = destination.read_text(encoding="utf-8")

        self.assertIn("_chemblender_unknown_tag", content)
        self.assertEqual(reparsed.periodic.site_labels, ("C2",))
        self.assertTrue(
            numpy.allclose(
                reparsed.periodic.fractional_coordinates.values,
                [[0.2, 0.3, 0.4]],
            )
        )
        self.assertTrue(
            numpy.allclose(reparsed.periodic.occupancies.values, [0.75])
        )
        self.assertTrue(
            numpy.allclose(
                reparsed.periodic.isotropic_displacements.values,
                [0.02],
            )
        )
        self.assertTrue(
            numpy.allclose(
                reparsed.periodic.anisotropic_displacements.values,
                [[0.02, 0.03, 0.04, 0.001, 0.002, 0.003]],
            )
        )
        self.assertEqual(reparsed.periodic.adp_types, ("Uiso",))
        self.assertEqual(reparsed.periodic.disorder_groups, (1,))
        self.assertEqual(reparsed.periodic.disorder_assemblies, ("A",))
        self.assertEqual(
            reparsed.periodic.declared_symmetry,
            changed.periodic.declared_symmetry,
        )

    def test_preserve_mode_patches_disorder_and_adp_type(self):
        source = FIXTURE.read_text(encoding="utf-8").replace(
            "_atom_site_disorder_group\nC1 C 0.1 0.2 0.3 0.5 1",
            (
                "_atom_site_disorder_group\n"
                "_atom_site_disorder_assembly\n"
                "_atom_site_adp_type\n"
                "C1 C 0.1 0.2 0.3 0.5 1 A Uiso"
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source_path = directory / "source.cif"
            source_path.write_text(source, encoding="utf-8")
            batch = parse_cif(source_path)
            changed = replace(
                batch.structures[0],
                periodic=replace(
                    batch.structures[0].periodic,
                    disorder_groups=(0,),
                    disorder_assemblies=("none",),
                    adp_types=("none",),
                ),
            )
            plan = plan_cif_export(
                changed,
                envelope=batch.cif_envelopes[0],
                mode="preserve",
            )
            actions = {field.name: field.action for field in plan.fields}
            self.assertEqual(actions["disorder_group"], "replace")
            self.assertEqual(actions["disorder_assembly"], "replace")
            self.assertEqual(actions["adp_type"], "replace")

            destination = directory / "changed.cif"
            export_cif(
                destination,
                changed,
                envelope=batch.cif_envelopes[0],
                mode="preserve",
            )
            reparsed = parse_cif(destination).structures[0]

        self.assertEqual(reparsed.periodic.disorder_groups, (0,))
        self.assertEqual(reparsed.periodic.disorder_assemblies, ("none",))
        self.assertEqual(reparsed.periodic.adp_types, ("none",))

    def test_normalized_mode_does_not_fabricate_symmetry_or_disorder(self):
        source = parse_cif(FIXTURE).structures[0]
        periodic = replace(
            source.periodic,
            occupancies=ArrayData(
                numpy.ones(1),
                ("atom",),
                "dimensionless",
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",),
            disorder_groups=(0,),
            disorder_assemblies=("none",),
            declared_space_group_name=None,
            declared_space_group_number=None,
            declared_hall_symbol=None,
            symmetry_operations=(),
            cif_envelope_id=None,
            cif_block_name=None,
            cif_block_key=None,
            cif_block_index=None,
        )
        derived = replace(source, periodic=periodic)

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "normalized.cif"
            report = export_cif(
                destination,
                derived,
                mode="normalized",
                block_name="normalized",
            )
            content = destination.read_text(encoding="utf-8")
            reparsed = parse_cif(destination).structures[0]

        self.assertTrue(report.written)
        self.assertNotIn("_space_group", content)
        self.assertNotIn("_symmetry_", content)
        self.assertNotIn("_atom_site_disorder", content)
        self.assertEqual(reparsed.periodic.declared_symmetry.name, None)
        self.assertEqual(reparsed.periodic.site_labels, ("C1",))

    def test_preserve_mode_requires_the_bound_envelope(self):
        batch = parse_cif(FIXTURE)
        with self.assertRaisesRegex(ValueError, "matching CIF envelope"):
            plan_cif_export(batch.structures[0], mode="preserve")


if __name__ == "__main__":
    unittest.main()
