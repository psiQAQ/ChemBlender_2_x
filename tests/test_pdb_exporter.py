import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from ChemBlender.core.exporters import export_pdb, preview_pdb_export
from ChemBlender.core.formats.pdb import parse_pdb
from tests.test_biological_atom_data import biological_mapping_fixture


FIXTURES = Path(__file__).with_name("fixtures") / "pdb"


def ready_single_model():
    batch = biological_mapping_fixture()
    structure = next(
        value for value in batch.structures if value.revision == "pdb-reference-r1"
    )
    hierarchy = next(
        value
        for value in batch.biological_hierarchies
        if value.structure_id == structure.id
    )
    datasets = tuple(
        value
        for value in batch.datasets
        if value.structure_id == structure.id
        and value.semantic_role in {"occupancy", "b_factor"}
    )
    return replace(
        batch,
        structures=(structure,),
        biological_hierarchies=(hierarchy,),
        datasets=datasets,
    )


class PDBExporterTests(unittest.TestCase):
    def test_ready_single_model_is_deterministic_without_confirmation(self):
        batch = ready_single_model()

        first = export_pdb(batch)
        second = export_pdb(batch)

        self.assertEqual(first.text, second.text)
        self.assertFalse(first.report.requires_confirmation)
        self.assertFalse(first.report.written)
        self.assertEqual(first.report.frame_count, 1)
        self.assertEqual(first.text.splitlines()[-1], "END")
        self.assertTrue(
            all(len(line) == 80 for line in first.text.splitlines()[:-1])
        )

    def test_real_omissions_have_stable_loss_codes(self):
        cases = {
            "topology_omitted": parse_pdb(FIXTURES / "conect.pdb"),
            "formal_charge_omitted": parse_pdb(
                FIXTURES / "atom-hetatm.pdb"
            ),
            "source_records_omitted": parse_pdb(FIXTURES / "altloc.pdb"),
        }
        with TemporaryDirectory() as directory:
            source = Path(directory) / "cell.pdb"
            source.write_bytes(
                (FIXTURES / "cryst1.pdb").read_bytes()
                + (FIXTURES / "altloc.pdb").read_bytes()
            )
            cases["cell_omitted"] = parse_pdb(source)

            for code, batch in cases.items():
                with self.subTest(code=code):
                    preview = preview_pdb_export(batch)
                    self.assertIn(code, tuple(entry.code for entry in preview.entries))
                    self.assertTrue(preview.requires_confirmation)

    def test_loss_preview_blocks_destination_until_confirmed(self):
        batch = parse_pdb(FIXTURES / "conect.pdb")
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "normalized.pdb"

            blocked = export_pdb(batch, destination=destination)

            self.assertEqual(blocked.text, "")
            self.assertTrue(blocked.report.requires_confirmation)
            self.assertFalse(destination.exists())

            written = export_pdb(
                batch,
                confirm_loss=True,
                destination=destination,
            )
            self.assertTrue(written.report.written)
            self.assertEqual(destination.read_text(encoding="utf-8"), written.text)

    def test_confirm_loss_requires_exact_bool(self):
        with self.assertRaisesRegex(TypeError, "confirm_loss"):
            export_pdb(ready_single_model(), confirm_loss=1)

    def test_unsupported_readiness_includes_status_and_tokens(self):
        batch = ready_single_model()
        batch = replace(batch, biological_hierarchies=())

        with self.assertRaisesRegex(
            ValueError,
            "MissingHierarchy.*hierarchy.missing",
        ):
            preview_pdb_export(batch)


if __name__ == "__main__":
    unittest.main()
