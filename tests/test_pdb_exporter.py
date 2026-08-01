import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData, QCProject
from ChemBlender.core.exporters import (
    ExportCancelled,
    export_pdb,
    preview_pdb_export,
)
from ChemBlender.core.formats.pdb import parse_pdb
from tests.test_biological_atom_data import biological_mapping_fixture


FIXTURES = Path(__file__).with_name("fixtures") / "pdb"


def pdb_batch(*, include_frames=False, include_second=False):
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
        and (
            value.semantic_role in {"occupancy", "b_factor"}
            or include_frames
            and value.semantic_role == "coordinates"
        )
    )
    structures = (structure,)
    hierarchies = (hierarchy,)
    if include_second:
        second = next(
            value
            for value in batch.structures
            if value.revision == "pdb-incompatible-model-r1"
        )
        structures += (second,)
        hierarchies += tuple(
            value
            for value in batch.biological_hierarchies
            if value.structure_id == second.id
        )
    return replace(
        batch,
        structures=structures,
        biological_hierarchies=hierarchies,
        datasets=datasets,
    )


def ready_single_model():
    return pdb_batch()


def categorical_values(data):
    return tuple(
        None if int(code) == data.missing_code else data.categories[int(code)]
        for code in data.codes.values
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

    def test_container_order_does_not_change_multiple_structure_bytes(self):
        batch = pdb_batch(include_second=True)
        reversed_batch = replace(
            batch,
            structures=tuple(reversed(batch.structures)),
            biological_hierarchies=tuple(
                reversed(batch.biological_hierarchies)
            ),
            datasets=tuple(reversed(batch.datasets)),
        )
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        for name in ("structures", "biological_hierarchies", "datasets"):
            values = getattr(project, name)
            setattr(project, name, dict(reversed(tuple(values.items()))))

        expected = export_pdb(batch).text

        self.assertEqual(export_pdb(reversed_batch).text, expected)
        self.assertEqual(export_pdb(project).text, expected)

    def test_fixed_columns_preserve_hierarchy_and_record_kind(self):
        text = export_pdb(pdb_batch(include_second=True)).text
        atom_lines = tuple(
            line
            for line in text.splitlines()
            if line.startswith(("ATOM  ", "HETATM"))
        )

        self.assertEqual(tuple(line[:6] for line in atom_lines), (
            "HETATM",
            "ATOM  ",
            "ATOM  ",
        ))
        self.assertEqual(atom_lines[1][12:17], " CA A")
        self.assertEqual(atom_lines[1][17:27], "GLY A   7A")
        self.assertEqual(atom_lines[0][16], " ")
        self.assertEqual(atom_lines[0][26], " ")
        self.assertEqual(atom_lines[0][21], "B")

    def test_duplicate_source_serials_renumber_in_atom_order(self):
        batch = ready_single_model()
        hierarchy = batch.biological_hierarchies[0]
        sites = replace(
            hierarchy.atom_sites,
            serial_numbers=ArrayData(
                numpy.asarray((20, 20), dtype=numpy.int64),
                ("atom",),
                "dimensionless",
            ),
        )
        batch = replace(
            batch,
            biological_hierarchies=(replace(hierarchy, atom_sites=sites),),
        )

        preview = preview_pdb_export(batch)
        lines = export_pdb(batch, confirm_loss=True).text.splitlines()

        self.assertEqual(
            tuple(entry.code for entry in preview.entries),
            ("atom_serials_renumbered",),
        )
        self.assertEqual((lines[0][6:11], lines[1][6:11]), ("    1", "    2"))

    def test_partial_occupancy_and_b_factor_use_exact_blank_fields(self):
        lines = export_pdb(ready_single_model()).text.splitlines()

        self.assertEqual((lines[0][54:60], lines[0][60:66]), ("  1.00", " 12.50"))
        self.assertEqual((lines[1][54:60], lines[1][60:66]), ("      ", "      "))

        batch = ready_single_model()
        occupancy = next(
            value for value in batch.datasets if value.semantic_role == "occupancy"
        )
        invalid = replace(
            batch,
            datasets=tuple(
                replace(
                    value,
                    data=replace(value.data, unit="angstrom"),
                )
                if value.id == occupancy.id
                else value
                for value in batch.datasets
            ),
        )
        with self.assertRaisesRegex(ValueError, "dataset.occupancy.unit"):
            export_pdb(invalid)

    def test_frame_set_is_the_complete_model_inventory(self):
        exported = export_pdb(pdb_batch(include_frames=True)).text

        self.assertEqual(exported.count("MODEL"), 2)
        self.assertEqual(exported.count("ENDMDL"), 2)
        self.assertEqual(exported.count("ATOM  "), 4)
        self.assertNotIn("MODEL        3", exported)
        self.assertTrue(exported.endswith("END\n"))

    def test_model_number_overflow_fails_before_publication(self):
        batch = pdb_batch(include_frames=True)
        frames = next(
            value for value in batch.datasets if value.semantic_role == "coordinates"
        )
        repeated = numpy.repeat(frames.data.values[:1], 10_000, axis=0)
        batch = replace(
            batch,
            datasets=tuple(
                replace(
                    value,
                    data=replace(value.data, values=repeated),
                    comments=("",) * 10_000,
                )
                if value.id == frames.id
                else value
                for value in batch.datasets
            ),
        )

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "too-many-models.pdb"
            with self.assertRaisesRegex(ValueError, "model\\.overflow"):
                export_pdb(batch, destination=destination)
            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_invalid_live_element_after_preview_fails_before_publication(self):
        batch = ready_single_model()
        calls = 0

        def mutate_after_preview():
            nonlocal calls
            calls += 1
            if calls == 2:
                object.__setattr__(batch.structures[0], "atomic_numbers", (0, 7))
            return False

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "invalid.pdb"
            with self.assertRaisesRegex(ValueError, "atomic number"):
                export_pdb(
                    batch,
                    destination=destination,
                    is_cancelled=mutate_after_preview,
                )
            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_cancellation_preempts_invalid_data_and_cleans_mid_write(self):
        invalid = ready_single_model()
        invalid.structures[0].coordinates.values[0, 0] = numpy.nan
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "cancelled.pdb"
            with self.assertRaises(ExportCancelled):
                export_pdb(
                    invalid,
                    destination=destination,
                    is_cancelled=lambda: True,
                )
            self.assertEqual(tuple(Path(directory).iterdir()), ())

        calls = 0

        def cancel_during_atomic_write():
            nonlocal calls
            calls += 1
            return calls == 7

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "cancelled.pdb"
            with self.assertRaises(ExportCancelled):
                export_pdb(
                    ready_single_model(),
                    destination=destination,
                    is_cancelled=cancel_during_atomic_write,
                )
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_normalized_output_never_emits_conect_or_cryst1(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "periodic-connected.pdb"
            source.write_bytes(
                (FIXTURES / "cryst1.pdb").read_bytes()
                + (FIXTURES / "conect.pdb").read_bytes()
            )
            batch = parse_pdb(source)

            preview = preview_pdb_export(batch)
            text = export_pdb(batch, confirm_loss=True).text

        self.assertIn("cell_omitted", tuple(entry.code for entry in preview.entries))
        self.assertIn("topology_omitted", tuple(entry.code for entry in preview.entries))
        self.assertNotIn("CRYST1", text)
        self.assertNotIn("CONECT", text)

    def test_semantic_native_reimport_preserves_representable_fields(self):
        original = pdb_batch(include_frames=True)
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "roundtrip.pdb"
            export_pdb(original, destination=destination)
            imported = parse_pdb(destination)

        source_structure = original.structures[0]
        target_structure = imported.structures[0]
        self.assertEqual(target_structure.atomic_numbers, source_structure.atomic_numbers)
        numpy.testing.assert_allclose(
            target_structure.coordinates.values,
            source_structure.coordinates.values,
            atol=5e-4,
            rtol=0.0,
        )
        self.assertEqual(
            categorical_values(target_structure.atomic_identity.atom_names),
            categorical_values(source_structure.atomic_identity.atom_names),
        )

        source_hierarchy = original.biological_hierarchies[0]
        target_hierarchy = imported.biological_hierarchies[0]
        self.assertEqual(
            categorical_values(target_hierarchy.atom_sites.record_kinds),
            categorical_values(source_hierarchy.atom_sites.record_kinds),
        )
        self.assertEqual(
            categorical_values(target_hierarchy.atom_sites.alternate_locations),
            categorical_values(source_hierarchy.atom_sites.alternate_locations),
        )
        self.assertEqual(target_hierarchy.chains, source_hierarchy.chains)
        self.assertEqual(target_hierarchy.residues, source_hierarchy.residues)

        source_frames = next(
            value for value in original.datasets if value.semantic_role == "coordinates"
        )
        target_frames = next(
            value for value in imported.datasets if value.semantic_role == "coordinates"
        )
        self.assertEqual(target_frames.data.shape, source_frames.data.shape)
        numpy.testing.assert_allclose(
            target_frames.data.values,
            source_frames.data.values,
            atol=5e-4,
            rtol=0.0,
        )

        for role in ("occupancy", "b_factor"):
            source = next(
                value for value in original.datasets if value.semantic_role == role
            )
            target = next(
                value for value in imported.datasets if value.semantic_role == role
            )
            source_values = numpy.asarray(source.data.values)
            target_values = numpy.asarray(target.data.values)
            self.assertEqual(
                tuple(numpy.isfinite(target_values)),
                tuple(numpy.isfinite(source_values)),
            )
            numpy.testing.assert_allclose(
                target_values[numpy.isfinite(target_values)],
                source_values[numpy.isfinite(source_values)],
                atol=0.005,
                rtol=0.0,
            )


if __name__ == "__main__":
    unittest.main()
