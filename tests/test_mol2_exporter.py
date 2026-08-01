import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData, QCProject
from ChemBlender.core.exporters import (
    ExportCancelled,
    export_mol2,
    preview_mol2_export,
)
from ChemBlender.core.formats.mol2 import parse_mol2


FIXTURES = Path(__file__).with_name("fixtures") / "mol2"


class Mol2ExporterTests(unittest.TestCase):
    def dataset(self, batch, role):
        return next(value for value in batch.datasets if value.semantic_role == role)

    def test_aromatic_fixture_exports_deterministically(self):
        batch = parse_mol2(FIXTURES / "aromatic.mol2")

        first = export_mol2(batch, confirm_loss=True)
        second = export_mol2(batch, confirm_loss=True)

        self.assertEqual(first.text, second.text)
        self.assertTrue(first.report.requires_confirmation)
        self.assertIn("@<TRIPOS>MOLECULE\n", first.text)
        self.assertIn(" ar\n", first.text)

    def test_loss_preview_blocks_the_destination_until_confirmed(self):
        batch = parse_mol2(FIXTURES / "small.mol2")
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "normalized.mol2"

            blocked = export_mol2(batch, destination=destination)

            self.assertEqual(blocked.text, "")
            self.assertTrue(blocked.report.requires_confirmation)
            self.assertFalse(destination.exists())

    def test_small_fixture_reports_raw_only_loss(self):
        preview = preview_mol2_export(parse_mol2(FIXTURES / "small.mol2"))

        self.assertEqual(
            tuple(entry.code for entry in preview.entries),
            (
                "molecule_comments_omitted",
                "molecule_status_bits_omitted",
                "source_atom_ids_renumbered",
                "source_bond_ids_renumbered",
                "substructure_fields_omitted",
                "unknown_sections_omitted",
            ),
        )

    def test_missing_topology_is_unsupported(self):
        batch = parse_mol2(FIXTURES / "aromatic.mol2")

        with self.assertRaisesRegex(ValueError, "topology"):
            preview_mol2_export(replace(batch, topologies=()))

    def test_confirmed_small_fixture_semantically_reimports(self):
        source = parse_mol2(FIXTURES / "small.mol2")
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "normalized.mol2"
            exported = export_mol2(
                source,
                confirm_loss=True,
                destination=destination,
            )
            reparsed = parse_mol2(destination)

        self.assertTrue(exported.report.written)
        self.assertEqual(
            reparsed.structures[0].atomic_numbers,
            source.structures[0].atomic_numbers,
        )
        numpy.testing.assert_allclose(
            reparsed.structures[0].coordinates.values,
            source.structures[0].coordinates.values,
            rtol=0.0,
            atol=0.0,
        )
        numpy.testing.assert_array_equal(
            reparsed.topologies[0].bond_indices.values,
            source.topologies[0].bond_indices.values,
        )
        numpy.testing.assert_allclose(
            reparsed.topologies[0].bond_orders.values,
            source.topologies[0].bond_orders.values,
            rtol=0.0,
            atol=0.0,
        )
        for role in (
            "atom_type",
            "partial_charge",
            "substructure_id",
            "substructure_name",
        ):
            left = self.dataset(source, role).data
            right = self.dataset(reparsed, role).data
            if hasattr(left, "categories"):
                self.assertEqual(left.categories, right.categories)
                numpy.testing.assert_array_equal(left.codes.values, right.codes.values)
            else:
                numpy.testing.assert_allclose(
                    left.values,
                    right.values,
                    rtol=0.0,
                    atol=0.0,
                )
        self.assertEqual(
            {(value.key, value.value) for value in reparsed.annotations},
            {(value.key, value.value) for value in source.annotations if value.key != "status_bits"},
        )

    def test_amide_label_semantically_reimports(self):
        source = parse_mol2(FIXTURES / "substructure.mol2")

        exported = export_mol2(source, confirm_loss=True)
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "amide.mol2"
            destination.write_text(exported.text, encoding="utf-8")
            reparsed = parse_mol2(destination)

        self.assertEqual(reparsed.topologies[0].stereo_labels, ("amide", ""))

    def test_multi_record_order_is_source_order_and_container_independent(self):
        batch = parse_mol2(FIXTURES / "multi.mol2")
        reversed_batch = replace(
            batch,
            structures=tuple(reversed(batch.structures)),
            topologies=tuple(reversed(batch.topologies)),
            molecular_records=tuple(reversed(batch.molecular_records)),
            annotations=tuple(reversed(batch.annotations)),
            datasets=tuple(reversed(batch.datasets)),
        )
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        for name in (
            "structures",
            "topologies",
            "molecular_records",
            "annotations",
            "datasets",
        ):
            values = getattr(project, name)
            setattr(project, name, dict(reversed(tuple(values.items()))))

        original = export_mol2(batch, confirm_loss=True).text
        reversed_text = export_mol2(reversed_batch, confirm_loss=True).text
        project_text = export_mol2(project, confirm_loss=True).text

        self.assertEqual(original, reversed_text)
        self.assertEqual(original, project_text)
        self.assertLess(original.index("\nfirst\n"), original.index("\nsecond\n"))

    def test_charge_without_substructure_uses_literal_placeholders(self):
        batch = parse_mol2(FIXTURES / "small.mol2")
        batch = replace(
            batch,
            datasets=tuple(
                value
                for value in batch.datasets
                if value.semantic_role
                not in {"substructure_id", "substructure_name"}
            ),
        )

        exported = export_mol2(batch, confirm_loss=True)

        self.assertIn(" C.3 **** **** -0.12\n", exported.text)

    def test_confirmed_missing_charge_data_downgrades_to_no_charges(self):
        batch = parse_mol2(FIXTURES / "small.mol2")
        batch = replace(
            batch,
            datasets=tuple(
                value
                for value in batch.datasets
                if value.semantic_role != "partial_charge"
            ),
        )

        preview = preview_mol2_export(batch)
        exported = export_mol2(batch, confirm_loss=True)

        self.assertIn("missing:dataset.partial_charge", tuple(entry.code for entry in preview.entries))
        self.assertIn("\nNO_CHARGES\n", exported.text)

    def test_no_charges_with_authoritative_charge_requires_confirmation(self):
        batch = parse_mol2(FIXTURES / "small.mol2")
        charge_type = next(value for value in batch.annotations if value.key == "charge_type")
        batch = replace(
            batch,
            annotations=tuple(
                replace(value, value="NO_CHARGES") if value.id == charge_type.id else value
                for value in batch.annotations
            ),
        )

        preview = preview_mol2_export(batch)
        blocked = export_mol2(batch)
        exported = export_mol2(batch, confirm_loss=True)

        self.assertIn(
            "partial_charge_omitted",
            tuple(entry.code for entry in preview.entries),
        )
        self.assertEqual(blocked.text, "")
        self.assertIn("\nNO_CHARGES\n", exported.text)
        self.assertNotIn("-0.12", exported.text)

    def test_non_tripos_raw_record_can_be_confirmed_and_normalized(self):
        batch = parse_mol2(FIXTURES / "aromatic.mol2")
        batch = replace(
            batch,
            molecular_records=(replace(batch.molecular_records[0], raw_block=b"not MOL2\n"),),
        )

        preview = preview_mol2_export(batch)
        exported = export_mol2(batch, confirm_loss=True)

        self.assertIn("missing:molecular_record.raw_tripos", tuple(entry.code for entry in preview.entries))
        self.assertIn("@<TRIPOS>MOLECULE\n", exported.text)

    def test_partial_substructure_is_omitted_after_confirmation(self):
        batch = parse_mol2(FIXTURES / "small.mol2")
        substructure_name = self.dataset(batch, "substructure_name")
        batch = replace(
            batch,
            datasets=tuple(
                replace(value, status=value.status.PARTIAL)
                if value.id == substructure_name.id
                else value
                for value in batch.datasets
            ),
        )

        preview = preview_mol2_export(batch)
        exported = export_mol2(batch, confirm_loss=True)

        self.assertIn("missing:dataset.substructure_name", tuple(entry.code for entry in preview.entries))
        self.assertNotIn("@<TRIPOS>SUBSTRUCTURE", exported.text)
        self.assertIn(" C.3 **** **** -0.12\n", exported.text)

    def test_nonfinite_bond_order_is_rejected_even_for_aromatic_bond(self):
        batch = parse_mol2(FIXTURES / "aromatic.mol2")
        batch.topologies[0].bond_orders.values[0] = numpy.nan

        with self.assertRaisesRegex(ValueError, "bond orders.*finite"):
            export_mol2(batch, confirm_loss=True)

    def test_raw_bond_identity_reordering_requires_confirmation(self):
        batch = parse_mol2(FIXTURES / "aromatic.mol2")
        record = batch.molecular_records[0]
        canonical = record.raw_block.replace(
            b"1 1 2 ar\n2 2 3 ar\n3 3 4 ar\n4 4 5 ar\n5 5 6 ar\n6 6 1 ar\n",
            b"1 1 2 ar\n2 6 1 ar\n3 2 3 ar\n4 3 4 ar\n5 4 5 ar\n6 5 6 ar\n",
        )
        raw = canonical.replace(
            b"1 1 2 ar\n2 6 1 ar\n",
            b"1 6 1 ar\n2 1 2 ar\n",
        )
        canonical_batch = replace(
            batch,
            molecular_records=(replace(record, raw_block=canonical),),
        )
        batch = replace(batch, molecular_records=(replace(record, raw_block=raw),))

        canonical_preview = preview_mol2_export(canonical_batch)
        preview = preview_mol2_export(batch)

        self.assertNotIn(
            "source_bond_ids_renumbered",
            tuple(entry.code for entry in canonical_preview.entries),
        )
        self.assertIn("source_bond_ids_renumbered", tuple(entry.code for entry in preview.entries))

    def test_changed_raw_substructure_root_requires_confirmation(self):
        batch = parse_mol2(FIXTURES / "aromatic.mol2")
        record = batch.molecular_records[0]
        raw = record.raw_block.replace(b"1 BENZENE 1 GROUP", b"1 BENZENE 2 GROUP")
        batch = replace(batch, molecular_records=(replace(record, raw_block=raw),))

        preview = preview_mol2_export(batch)

        self.assertIn("substructure_fields_omitted", tuple(entry.code for entry in preview.entries))

    def test_title_rejects_unicode_line_boundaries(self):
        for separator in ("\u0085", "\u2028"):
            with self.subTest(separator=repr(separator)):
                batch = parse_mol2(FIXTURES / "aromatic.mol2")
                record = batch.molecular_records[0]
                batch = replace(
                    batch,
                    molecular_records=(replace(record, title=f"bad{separator}title"),),
                )
                with self.assertRaisesRegex(ValueError, "title"):
                    export_mol2(batch, confirm_loss=True)

    def test_cancelled_export_preempts_invalid_data_and_publishes_nothing(self):
        batch = parse_mol2(FIXTURES / "aromatic.mol2")
        batch.structures[0].coordinates.values[0, 0] = numpy.nan
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "cancelled.mol2"

            with self.assertRaises(ExportCancelled):
                export_mol2(
                    batch,
                    destination=destination,
                    is_cancelled=lambda: True,
                )

            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_mid_write_cancellation_cleans_temporary_file(self):
        batch = parse_mol2(FIXTURES / "aromatic.mol2")
        calls = 0

        def cancelled():
            nonlocal calls
            calls += 1
            return calls == 3

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "cancelled.mol2"
            with self.assertRaises(ExportCancelled):
                export_mol2(
                    batch,
                    confirm_loss=True,
                    destination=destination,
                    is_cancelled=cancelled,
                )
            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_replace_failure_preserves_destination_and_cleans_temporary_file(self):
        batch = parse_mol2(FIXTURES / "aromatic.mol2")
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "existing.mol2"
            destination.write_text("old\n", encoding="utf-8")
            with patch(
                "ChemBlender.core.exporters.xyz.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    export_mol2(
                        batch,
                        confirm_loss=True,
                        destination=destination,
                    )
            self.assertEqual(destination.read_text(encoding="utf-8"), "old\n")
            self.assertEqual(tuple(Path(directory).iterdir()), (destination,))

    def test_writer_rejects_invalid_values_without_publishing(self):
        cases = []
        non_finite = parse_mol2(FIXTURES / "small.mol2")
        self.dataset(non_finite, "partial_charge").data.values[0] = numpy.inf
        cases.append(("invalid", non_finite))

        non_angstrom = parse_mol2(FIXTURES / "aromatic.mol2")
        structure = non_angstrom.structures[0]
        non_angstrom = replace(
            non_angstrom,
            structures=(
                replace(
                    structure,
                    coordinates=replace(structure.coordinates, unit="bohr"),
                ),
            ),
        )
        cases.append(("angstrom", non_angstrom))

        periodic = parse_mol2(FIXTURES / "aromatic.mol2")
        topology = periodic.topologies[0]
        shifts = numpy.zeros((len(topology.stereo_labels), 3), dtype=numpy.int64)
        shifts[0, 0] = 1
        periodic = replace(
            periodic,
            topologies=(
                replace(
                    topology,
                    bond_lattice_shifts=ArrayData(
                        shifts,
                        ("bond", "xyz"),
                        "dimensionless",
                    ),
                ),
            ),
        )
        cases.append(("periodic", periodic))

        whitespace = parse_mol2(FIXTURES / "aromatic.mol2")
        molecule_type = next(
            value for value in whitespace.annotations if value.key == "molecule_type"
        )
        whitespace = replace(
            whitespace,
            annotations=tuple(
                replace(value, value="BAD TYPE")
                if value.id == molecule_type.id
                else value
                for value in whitespace.annotations
            ),
        )
        cases.append(("token", whitespace))

        for expected, value in cases:
            with self.subTest(expected=expected), TemporaryDirectory() as directory:
                destination = Path(directory) / "invalid.mol2"
                with self.assertRaisesRegex(ValueError, expected):
                    export_mol2(
                        value,
                        confirm_loss=True,
                        destination=destination,
                    )
                self.assertFalse(destination.exists())

    def test_confirm_loss_requires_exact_bool(self):
        with self.assertRaisesRegex(TypeError, "confirm_loss"):
            export_mol2(
                parse_mol2(FIXTURES / "aromatic.mol2"),
                confirm_loss=1,
            )


if __name__ == "__main__":
    unittest.main()
