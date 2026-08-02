import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ChemBlender.core.exporters import (
    ExportCancelled,
    export_pqr,
    preview_pqr_export,
)
from ChemBlender.core.formats.pqr import parse_pqr
from ChemBlender.core.exporters.pdb_readiness import (
    PDBPQRExportReadiness,
    PDBPQRExportStatus,
)


FIXTURES = Path(__file__).with_name("fixtures") / "pqr"


class PQRExporterTests(unittest.TestCase):
    def test_ready_chain_and_no_chain_exports_are_deterministic_ascii_lf(self):
        cases = (
            ("with-chain.pqr", (11, 11)),
            ("no-chain.pqr", (10, 10)),
        )
        for filename, field_counts in cases:
            with self.subTest(filename=filename):
                batch = parse_pqr(FIXTURES / filename)

                first = export_pqr(batch)
                second = export_pqr(batch)

                self.assertEqual(first.text, second.text)
                self.assertEqual(first.text, (FIXTURES / filename).read_text("ascii"))
                self.assertTrue(first.text.isascii())
                self.assertTrue(first.text.endswith("\n"))
                self.assertEqual(
                    tuple(len(line.split()) for line in first.text.splitlines()),
                    field_counts,
                )

    def test_unsupported_readiness_includes_stable_status_and_token(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")

        with self.assertRaisesRegex(
            ValueError,
            "MissingHierarchy.*hierarchy.missing",
        ):
            preview_pqr_export(replace(batch, biological_hierarchies=()))

    def test_loss_preview_blocks_text_and_destination_until_confirmed(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        structure = replace(batch.structures[0], molecular_charge=1)
        batch = replace(batch, structures=(structure,))
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "normalized.pqr"

            blocked = export_pqr(batch, destination=destination)

            self.assertEqual(blocked.text, "")
            self.assertTrue(blocked.report.requires_confirmation)
            self.assertFalse(destination.exists())
            self.assertIn(
                "molecular_charge_omitted",
                tuple(entry.code for entry in blocked.report.entries),
            )

            written = export_pqr(
                batch,
                confirm_loss=True,
                destination=destination,
            )
            self.assertTrue(written.report.written)
            self.assertEqual(destination.read_text("ascii"), written.text)

    def test_confirm_loss_requires_exact_bool(self):
        with self.assertRaisesRegex(TypeError, "confirm_loss"):
            export_pqr(parse_pqr(FIXTURES / "with-chain.pqr"), confirm_loss=1)

    def test_cancellation_before_validation_publishes_nothing(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "cancelled.pqr"

            with self.assertRaises(ExportCancelled):
                export_pqr(
                    batch,
                    destination=destination,
                    is_cancelled=lambda: True,
                )

            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_control_label_is_rejected_before_destination_publication(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        identity = batch.structures[0].atomic_identity
        structure = replace(
            batch.structures[0],
            atomic_identity=replace(
                identity,
                atom_names=replace(
                    identity.atom_names,
                    categories=("N\x7f", "O"),
                ),
            ),
        )
        batch = replace(batch, structures=(structure,))
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "invalid-label.pqr"

            with self.assertRaisesRegex(ValueError, "PQR atom name is invalid"):
                export_pqr(batch, destination=destination)

            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_writer_rechecks_element_identity_after_readiness_bypass(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        batch = replace(
            batch,
            structures=(replace(batch.structures[0], atomic_numbers=(7, 7)),),
        )
        ready = PDBPQRExportReadiness(PDBPQRExportStatus.READY, ())
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "mismatched-element.pqr"
            with patch(
                "ChemBlender.core.exporters.pqr.pqr_export_readiness",
                return_value=ready,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "PQR identity.element.mismatch",
                ):
                    export_pqr(batch, destination=destination)

            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())


if __name__ == "__main__":
    unittest.main()
