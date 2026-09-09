import importlib.util
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from cbq_core.model import QCProject
from chemblender_prepare.core.formats.cif import parse_cif
from ChemBlender.ui.project_browser.model import BrowserMode, build_browser_rows


ROOT = Path(__file__).resolve().parents[1]
MULTI = ROOT / "tests" / "fixtures" / "cif" / "multi-block.cif"
MIXED = ROOT / "tests" / "fixtures" / "cif" / "mixed-site-data.cif"
HAS_GEMMI = importlib.util.find_spec("gemmi") is not None
if HAS_GEMMI:
    import gemmi  # noqa: F401  # keep native types loaded across module patches


@unittest.skipUnless(HAS_GEMMI, "Gemmi dependency unavailable")
class CIFProductFlowTests(unittest.TestCase):
    def cli(self, *args):
        import io
        import json
        from contextlib import redirect_stdout
        from chemblender_prepare.cli import main
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main([str(value) for value in args] + ["--json"])
        result = json.loads(stream.getvalue())
        self.assertEqual(code, 0, result)
        return result

    def test_preview_and_conversion_preserve_all_cif_blocks(self):
        from cbq_core.sidecar import open_project, close_project
        import numpy
        row = self.cli("inspect", MULTI)["metadata"]["cif"]
        self.assertEqual((row["block_count"], row["valid_block_count"], row["site_count"]), (2, 2, 4))
        self.assertEqual([block["name"] for block in row["blocks"]], ["first", "second"])
        self.assertAlmostEqual(row["blocks"][0]["cell"][0][0], 4.12)
        self.assertEqual(row["blocks"][0]["cell_unit"], "angstrom")
        self.assertEqual(row["conversion_policy"], "all_valid_blocks")
        original = MULTI.read_bytes()
        expected = parse_cif(MULTI)
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.cif", Path(directory) / "all.cbq"
            source.write_bytes(original)
            self.cli("convert", source, "-o", output)
            source.unlink()
            project = open_project(output, verify_arrays=True)
            try:
                structures = sorted(project.structures.values(), key=lambda value: value.periodic.cif_block_index)
                self.assertEqual(len(structures), 2)
                self.assertEqual(len({value.id for value in structures}), 2)
                for index, (actual, before) in enumerate(zip(structures, expected.structures)):
                    self.assertEqual(actual.periodic.cif_block_index, index)
                    self.assertEqual(actual.periodic.cif_block_key, before.periodic.cif_block_key)
                    envelope = project.cif_envelopes[actual.periodic.cif_envelope_id]
                    self.assertEqual(envelope.source_bytes, original)
                    self.assertEqual(envelope.block_keys[index], actual.periodic.cif_block_key)
                    numpy.testing.assert_array_equal(actual.coordinates.values, before.coordinates.values)
                    numpy.testing.assert_array_equal(actual.cell.values, before.cell.values)
            finally:
                close_project(project)

    def test_preview_bounds_blocks_and_rejects_input_changed_during_parse(self):
        from unittest.mock import patch
        import io
        import json
        from contextlib import redirect_stdout
        from chemblender_prepare.cli import main
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "many.cif"
            source.write_bytes(MULTI.read_bytes() + b"".join(
                ("\ndata_note" + str(index) + "\n_audit_creation_method notes\n").encode()
                for index in range(101)))
            row = self.cli("inspect", source)["metadata"]["cif"]
            self.assertEqual(row["block_count"], 103)
            self.assertEqual(len(row["blocks"]), 100)
            self.assertTrue(row["blocks_truncated"])
            self.assertEqual(row["diagnostic_count"], len(parse_cif(source).report.issues))
            self.assertEqual(len(row["diagnostics"]), 100)
            def changed(path):
                batch = parse_cif(path)
                path.write_bytes(b"data_changed\n_audit_creation_method changed\n")
                return batch
            stream = io.StringIO()
            with patch("chemblender_prepare.core.formats.cif.parse_cif", side_effect=changed), redirect_stdout(stream):
                code = main(["inspect", str(source), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("Input changed during inspection", stream.getvalue())
            self.assertEqual(json.loads(stream.getvalue())["status"], "error")

    def test_preview_reports_nonstructural_blocks_without_inventing_sites(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "mixed.cif"
            source.write_bytes(MULTI.read_bytes() + b"\ndata_notes\n_audit_creation_method 'notes only'\n")
            row = self.cli("inspect", source)["metadata"]["cif"]
        self.assertEqual((row["block_count"], row["valid_block_count"], row["site_count"]), (3, 2, 4))
        self.assertFalse(row["blocks"][2]["has_structure"])
        self.assertIsNone(row["blocks"][2]["cell"])
        self.assertTrue(any(issue["path"] == "cif.blocks[2]" for issue in row["diagnostics"]))


@unittest.skipUnless(HAS_GEMMI, "Gemmi dependency unavailable")
class PreparedCIFProductFlowTests(unittest.TestCase):
    def test_browser_exposes_site_occupancy_disorder_and_adp_summaries(self):
        batch = parse_cif(MIXED)
        project = QCProject(uuid4(), "0.2")
        project.commit(batch)

        rows = build_browser_rows(
            project,
            mode=BrowserMode.BY_DATA,
            session_id=uuid4(),
            browser_revision=1,
        )
        labels = tuple(row.label for row in rows)

        self.assertTrue(any("Sites: 2" in label for label in labels))
        self.assertTrue(any("Occupancy:" in label for label in labels))
        self.assertTrue(any("Disorder:" in label for label in labels))
        self.assertTrue(any("ADP:" in label for label in labels))


    def test_background_cif_export_uses_bound_envelope(self):
        from chemblender_prepare import export_service
        batch = parse_cif(MIXED)
        project = QCProject(uuid4(), "0.2")
        project.commit(batch)
        structure = batch.structures[0]
        selection = export_service.resolve_export_selection(
            project,
            structure.id,
        )
        self.assertIs(selection.cif_envelope, batch.cif_envelopes[0])
        preview = export_service.preview_export_selection(selection, "cif")
        self.assertEqual(preview.format, "cif")
        self.assertTrue(
            any(entry.code == "preserve:unknown_content" for entry in preview.entries)
        )

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "exported.cif"
            report = export_service.export_selection(destination, selection, format_name="cif", confirm_loss=False)
            self.assertTrue(report.written)
            restored_labels = parse_cif(destination).structures[0].periodic.site_labels
        self.assertEqual(
            restored_labels,
            structure.periodic.site_labels,
        )



if __name__ == "__main__":
    unittest.main()
