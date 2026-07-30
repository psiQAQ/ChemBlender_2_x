import unittest
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch


class RDKitMolecularExportTests(unittest.TestCase):
    def source(self, text="[13CH3:7][C@H:8](F)/C=C/[N+:9](C)(C)C"):
        from ChemBlender.core.formats.smiles import parse_smiles_text
        batch = parse_smiles_text(text)
        return batch.structures[0], batch.topologies[0]

    def record(self, structure, topology, properties=(), title="title"):
        from ChemBlender.core.model import MolecularRecord
        from uuid import uuid4

        return MolecularRecord(
            uuid4(), "r", uuid4(), "0", structure.id, topology.id, b"",
            title, 0, "V2000", None, None, tuple(properties), (),
        )
    def test_public_exporter_module_exposes_molecular_entry_points(self):
        from ChemBlender.core.exporters.rdkit_molecular import (
            export_mol,
            export_sdf,
            export_smiles,
            preview_molecular_export,
        )

        self.assertTrue(callable(export_mol))
        self.assertTrue(callable(export_sdf))
        self.assertTrue(callable(export_smiles))
        self.assertTrue(callable(preview_molecular_export))

    def test_molecular_preview_reports_loss_without_constructing_rdkit_molecule(self):
        from ChemBlender.core.exporters import preview_molecular_export

        structure, topology = self.source()
        with patch(
            "ChemBlender.core.exporters.rdkit_molecular._molecule",
            side_effect=AssertionError("preview constructed an RDKit molecule"),
        ):
            report = preview_molecular_export(
                replace(structure, molecular_multiplicity=2),
                topology,
                format_name="sdf",
            )

        self.assertFalse(report.written)
        self.assertTrue(report.requires_confirmation)
        self.assertEqual(
            tuple(entry.code for entry in report.entries),
            ("multiplicity_omitted",),
        )

    def test_aromatic_implicit_hydrogen_requires_and_verifies_bound_record_seed(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol, export_smiles
        from ChemBlender.core.formats.smiles import parse_smiles_text

        batch = parse_smiles_text("[nH]1cccc1")
        with self.assertRaisesRegex(ValueError, "MolecularRecord seed"):
            export_mol(batch.structures[0], batch.topologies[0])
        record = batch.molecular_records[0]
        self.assertIn("V2000", export_mol(
            batch.structures[0], batch.topologies[0], record=record
        ).text)
        self.assertIn("[nH]", export_smiles(
            batch.structures[0], batch.topologies[0], record=record,
            confirm_loss=True,
        ).text)

    def test_tetrasubstituted_ez_requires_record_seed_and_preserves_configuration(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol
        from ChemBlender.core.formats.smiles import parse_smiles_text
        from rdkit import Chem

        batch = parse_smiles_text("F/C(Cl)=C(Br)/I")
        with self.assertRaisesRegex(ValueError, "exactly one explicit neighbor"):
            export_mol(batch.structures[0], batch.topologies[0])
        molecule = Chem.MolFromMolBlock(export_mol(
            batch.structures[0], batch.topologies[0], record=batch.molecular_records[0]
        ).text, removeHs=False)
        self.assertIn("STEREOZ", [str(bond.GetStereo()) for bond in molecule.GetBonds()])

    def test_authoritative_ez_requires_consistent_coordinates_and_can_override_seed(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol
        from ChemBlender.core.formats.smiles import parse_smiles_text
        from rdkit import Chem

        raw_z = parse_smiles_text("F/C(Cl)=C(Br)/I")
        authoritative_e = parse_smiles_text("F/C(Cl)=C(Br)\\I")
        seed = replace(raw_z.molecular_records[0], structure_id=authoritative_e.structures[0].id, topology_id=authoritative_e.topologies[0].id)
        molecule = Chem.MolFromMolBlock(export_mol(
            authoritative_e.structures[0], authoritative_e.topologies[0], record=seed
        ).text, removeHs=False)
        self.assertIn("STEREOE", [str(bond.GetStereo()) for bond in molecule.GetBonds()])
        conflicting = replace(raw_z.topologies[0], stereo_labels=tuple("E" if label == "Z" else label for label in raw_z.topologies[0].stereo_labels))
        seed = replace(raw_z.molecular_records[0], topology_id=conflicting.id)
        with self.assertRaisesRegex(ValueError, "bond semantics differ"):
            export_mol(raw_z.structures[0], conflicting, record=seed)

    def test_v3000_has_one_based_bond_ids_and_v2000_refuses_overflow(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol
        from ChemBlender.core.model import ArrayData
        import numpy
        structure, topology = self.source()
        text = export_mol(structure, topology, version="V3000").text
        self.assertIn("M  V30 1 ", text)
        self.assertNotIn("M  V30 0 ", text)
        identity = replace(
            structure.atomic_identity,
            atom_map_numbers=ArrayData(
                numpy.asarray([1000] + [0] * (len(structure.atomic_numbers) - 1), dtype=numpy.int64),
                ("atom",), "dimensionless",
            ),
        )
        overflow = replace(structure, atomic_identity=identity)
        with self.assertRaisesRegex(ValueError, "cannot represent"):
            export_mol(overflow, topology, version="V2000")
        self.assertIn("V3000", export_mol(overflow, topology).text)

    def test_mol_and_sdf_bytes_are_deterministic(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol, export_sdf, export_smiles

        structure, topology = self.source()
        self.assertEqual(export_mol(structure, topology).text.encode(), export_mol(structure, topology).text.encode())
        self.assertEqual(export_sdf(structure, topology).text.encode(), export_sdf(structure, topology).text.encode())
        self.assertEqual(export_smiles(structure, topology, confirm_loss=True).text.encode(), export_smiles(structure, topology, confirm_loss=True).text.encode())

    def test_export_preserves_identity_aromatic_and_stereo(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol
        from rdkit import Chem
        structure, topology = self.source()
        molecule = Chem.MolFromMolBlock(export_mol(structure, topology).text, removeHs=False)
        self.assertEqual(molecule.GetAtomWithIdx(0).GetIsotope(), 13)
        self.assertEqual(molecule.GetAtomWithIdx(0).GetAtomMapNum(), 7)
        self.assertIn("STEREOE", [str(item.GetStereo()) for item in molecule.GetBonds()])
        aromatic_structure, aromatic_topology = self.source("c1ccccc1")
        self.assertIn("  4", export_mol(aromatic_structure, aromatic_topology).text)

    def test_sdf_preserves_duplicate_empty_and_multiline_raw_properties(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_sdf
        from ChemBlender.core.model import RawRecordProperty
        structure, topology = self.source()
        record = self.record(structure, topology, (
            RawRecordProperty("x", "one"), RawRecordProperty("x", ""),
            RawRecordProperty("empty", ""), RawRecordProperty("multi", "a\nb"),
        ))
        second = self.record(structure, topology, (RawRecordProperty("second", "yes"),))
        text = export_sdf(structure, topology, records=(record, second)).text
        self.assertLess(text.index(">  <x>"), text.rindex(">  <x>"))
        self.assertIn(">  <multi>\na\nb", text)
        self.assertLess(text.index("title"), text.index("second"))
        from ChemBlender.core.formats.sdf import parse_sdf
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "records.sdf"
            destination.write_text(text, encoding="utf-8")
            reopened = parse_sdf(destination)
        self.assertEqual(
            reopened.molecular_records[0].ordered_raw_properties,
            record.ordered_raw_properties,
        )
        self.assertEqual(
            reopened.molecular_records[1].ordered_raw_properties,
            second.ordered_raw_properties,
        )
        with self.assertRaisesRegex(ValueError, "inject"):
            export_sdf(structure, topology, record=self.record(structure, topology, (RawRecordProperty("x", "ok\n> <bad>"),)))
        with self.assertRaisesRegex(ValueError, "separator"):
            export_sdf(structure, topology, record=self.record(structure, topology, (RawRecordProperty("x", "ok\n$$$$"),)))
        with self.assertRaisesRegex(ValueError, "at least one"):
            export_sdf(structure, topology, records=())

    def test_sdf_entries_keep_distinct_authoritative_records_in_order(self):
        from ChemBlender.core.exporters.rdkit_molecular import SDFExportEntry, export_sdf
        from ChemBlender.core.formats.sdf import parse_sdf
        from ChemBlender.core.model import RawRecordProperty

        first_structure, first_topology = self.source("CO")
        second_structure, second_topology = self.source("N")
        first = self.record(first_structure, first_topology, (RawRecordProperty("order", "first"),), "first")
        second = self.record(second_structure, second_topology, (RawRecordProperty("order", "second"),), "second")
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "distinct.sdf"
            export_sdf(entries=(
                SDFExportEntry(first_structure, first_topology, first),
                SDFExportEntry(second_structure, second_topology, second),
            ), destination=destination)
            reopened = parse_sdf(destination)
        self.assertEqual([item.title for item in reopened.molecular_records], ["first", "second"])
        self.assertEqual([item.ordered_raw_properties[0].value for item in reopened.molecular_records], ["first", "second"])

    def test_conformer_set_entries_keep_reference_atom_order_and_record_order(self):
        from ChemBlender.core.exporters.rdkit_molecular import (
            export_sdf, sdf_entries_from_conformer_set,
        )
        from ChemBlender.core.model import ArrayData, ConformerSet, DatasetStatus
        from uuid import uuid4
        import numpy

        structure, topology = self.source("CO")
        coordinates = numpy.asarray(structure.coordinates.values)
        conformers = ConformerSet(
            id=uuid4(), revision="r", semantic_role="coordinates", domain="conformer",
            data=ArrayData(numpy.stack((coordinates, coordinates + 1.0)), ("conformer", "atom", "xyz"), "angstrom"),
            status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
            reference_structure_id=structure.id, reference_topology_id=topology.id,
            record_ids=(uuid4(), uuid4()), record_keys=("first", "second"),
            atom_mappings=ArrayData(numpy.asarray(((0, 1), (1, 0)), dtype=numpy.int64), ("conformer", "atom"), "dimensionless"),
        )
        entries = sdf_entries_from_conformer_set(conformers, structure, topology, {})
        self.assertEqual(tuple(entries[1].structure.coordinates.values[0]), tuple(coordinates[0] + 1.0))
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "conformers.sdf"
            export_sdf(entries=entries, destination=destination, confirm_loss=True)
            from ChemBlender.core.formats.sdf import parse_sdf
            reopened = parse_sdf(destination)
            destination.write_text("old", encoding="utf-8")
            from ChemBlender.core.exporters.xyz import ExportCancelled
            with self.assertRaises(ExportCancelled):
                export_sdf(entries=entries, destination=destination, confirm_loss=True, is_cancelled=lambda: True)
            self.assertEqual(destination.read_text(encoding="utf-8"), "old")
        self.assertEqual([record.title for record in reopened.molecular_records], ["derived-first", "derived-second"])

    def test_conformer_set_uses_verified_reference_seed_and_row_property_lineage(self):
        from ChemBlender.core.exporters.rdkit_molecular import (
            export_sdf, sdf_entries_from_conformer_set,
        )
        from ChemBlender.core.formats.smiles import parse_smiles_text
        from ChemBlender.core.model import ArrayData, ConformerSet, DatasetStatus, RawRecordProperty
        from uuid import uuid4
        import numpy

        for source_text in ("[nH]1cccc1", "F/C(Cl)=C(Br)/I"):
            with self.subTest(source_text=source_text):
                batch = parse_smiles_text(source_text)
                structure, topology = batch.structures[0], batch.topologies[0]
                reference = batch.molecular_records[0]
                second = replace(
                    reference,
                    id=uuid4(),
                    record_key="second",
                    ordered_raw_properties=(RawRecordProperty("order", "second"),),
                )
                coordinates = numpy.asarray(structure.coordinates.values)
                atom_count = len(structure.atomic_numbers)
                conformers = ConformerSet(
                    id=uuid4(), revision="r", semantic_role="coordinates",
                    domain="conformer",
                    data=ArrayData(
                        numpy.stack((coordinates, coordinates)),
                        ("conformer", "atom", "xyz"), "angstrom",
                    ),
                    status=DatasetStatus.COMPLETE, source_calculation=None,
                    provenance_ids=(),
                    reference_structure_id=structure.id,
                    reference_topology_id=topology.id,
                    record_ids=(reference.id, second.id),
                    record_keys=(reference.record_key, second.record_key),
                    atom_mappings=ArrayData(
                        numpy.tile(numpy.arange(atom_count), (2, 1)),
                        ("conformer", "atom"), "dimensionless",
                    ),
                )
                entries = sdf_entries_from_conformer_set(
                    conformers, structure, topology,
                    {reference.id: reference, second.id: second},
                )
                self.assertIs(entries[0].seed_record, reference)
                self.assertIs(entries[1].seed_record, reference)
                text = export_sdf(entries=entries, confirm_loss=True).text
                self.assertEqual(text.count("$$$$"), 2)
                self.assertIn(">  <order>\nsecond", text)

                foreign = replace(reference, structure_id=uuid4())
                with self.assertRaisesRegex(ValueError, "reference seed lineage"):
                    sdf_entries_from_conformer_set(
                        conformers, structure, topology,
                        {reference.id: foreign, second.id: second},
                    )

    def test_cell_metadata_requires_loss_confirmation_but_nonzero_shift_is_rejected(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol
        from ChemBlender.core.model import ArrayData
        import numpy

        structure, topology = self.source("CO")
        structure = replace(
            structure,
            cell=ArrayData(numpy.eye(3), ("cell_vector", "xyz"), "angstrom"),
        )
        preview = export_mol(structure, topology)
        self.assertTrue(preview.report.requires_confirmation)
        self.assertIn("periodicity_omitted", {
            entry.code for entry in preview.report.entries
        })
        self.assertIn("V2000", export_mol(
            structure, topology, confirm_loss=True
        ).text)
        shifted = replace(
            topology,
            bond_lattice_shifts=ArrayData(
                numpy.asarray(((1, 0, 0),), dtype=numpy.int64),
                ("bond", "xyz"), "dimensionless",
            ),
        )
        with self.assertRaisesRegex(ValueError, "lattice shifts"):
            export_mol(structure, shifted, confirm_loss=True)

    def test_smiles_requires_loss_confirmation_before_write(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_smiles
        structure, topology = self.source()
        with TemporaryDirectory() as directory:
            target = Path(directory) / "x.smi"; target.write_text("old", encoding="utf-8")
            preview = export_smiles(structure, topology, destination=target)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertTrue(preview.report.requires_confirmation)
            export_smiles(structure, topology, destination=target, confirm_loss=True)
            self.assertNotEqual(target.read_text(encoding="utf-8"), "old")

    def test_multiplicity_loss_requires_confirmation_before_mol_or_sdf_write(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol, export_sdf

        structure, topology = self.source()
        structure = replace(structure, molecular_multiplicity=2)
        with TemporaryDirectory() as directory:
            mol_target = Path(directory) / "x.mol"
            sdf_target = Path(directory) / "x.sdf"
            mol_target.write_text("old", encoding="utf-8")
            sdf_target.write_text("old", encoding="utf-8")
            self.assertTrue(export_mol(structure, topology, destination=mol_target).report.requires_confirmation)
            self.assertTrue(export_sdf(structure, topology, destination=sdf_target).report.requires_confirmation)
            self.assertEqual(mol_target.read_text(encoding="utf-8"), "old")
            self.assertEqual(sdf_target.read_text(encoding="utf-8"), "old")
            export_mol(structure, topology, destination=mol_target, confirm_loss=True)
            export_sdf(structure, topology, destination=sdf_target, confirm_loss=True)
            self.assertNotEqual(mol_target.read_text(encoding="utf-8"), "old")
            self.assertNotEqual(sdf_target.read_text(encoding="utf-8"), "old")

    def test_atomic_cancel_and_replace_failure_preserve_existing_target(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol
        from ChemBlender.core.exporters.xyz import ExportCancelled

        structure, topology = self.source()
        with TemporaryDirectory() as directory:
            target = Path(directory) / "x.mol"
            target.write_text("old", encoding="utf-8")
            with self.assertRaises(ExportCancelled):
                export_mol(structure, topology, destination=target, is_cancelled=lambda: True)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            with patch("ChemBlender.core.exporters.xyz.os.replace", side_effect=OSError("replace")):
                with self.assertRaisesRegex(OSError, "replace"):
                    export_mol(structure, topology, destination=target)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual([path.name for path in Path(directory).iterdir()], ["x.mol"])

    def test_late_cancel_without_destination_stops_after_serialization(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol
        from ChemBlender.core.exporters.xyz import ExportCancelled

        structure, topology = self.source()
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 2
        with self.assertRaises(ExportCancelled):
            export_mol(structure, topology, is_cancelled=cancelled)

    def test_smiles_late_cancel_stops_after_serialization(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_smiles
        from ChemBlender.core.exporters.xyz import ExportCancelled

        structure, topology = self.source()
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 2
        with self.assertRaises(ExportCancelled):
            export_smiles(structure, topology, confirm_loss=True, is_cancelled=cancelled)

    def test_sdf_late_cancel_without_destination_stops_after_serialization(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_sdf
        from ChemBlender.core.exporters.xyz import ExportCancelled

        structure, topology = self.source()
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 3
        with self.assertRaises(ExportCancelled):
            export_sdf(structure, topology, is_cancelled=cancelled)

    def test_lazy_sidecar_arrays_close_after_export(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_mol
        from ChemBlender.core.model import ArrayData, CategoricalData
        from ChemBlender.core.sidecar import LazyNpyArray, _array_content_hash
        import numpy

        structure, topology = self.source()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            def lazy(name, values):
                path = root / f"{name}.npy"
                array = numpy.asarray(values)
                numpy.save(path, array)
                return LazyNpyArray(path, array.shape, array.dtype, _array_content_hash(array)[0])
            coordinates = lazy("coordinates", structure.coordinates.values)
            identity = structure.atomic_identity
            isotopes = lazy("isotopes", identity.isotopes.values)
            charges = lazy("charges", identity.formal_charges.values)
            maps = lazy("maps", identity.atom_map_numbers.values)
            names = lazy("names", identity.atom_names.codes.values)
            stereo = lazy("stereo", identity.stereo_labels.codes.values)
            indices = lazy("indices", topology.bond_indices.values)
            orders = lazy("orders", topology.bond_orders.values)
            aromatic = lazy("aromatic", topology.aromatic_flags.values)
            identity = replace(identity,
                isotopes=ArrayData(isotopes, ("atom",), "dimensionless"),
                formal_charges=ArrayData(charges, ("atom",), "dimensionless"),
                atom_map_numbers=ArrayData(maps, ("atom",), "dimensionless"),
                atom_names=CategoricalData(ArrayData(names, ("atom",), "dimensionless"), identity.atom_names.categories, identity.atom_names.missing_code),
                stereo_labels=CategoricalData(ArrayData(stereo, ("atom",), "dimensionless"), identity.stereo_labels.categories, identity.stereo_labels.missing_code),
            )
            structure = replace(structure, coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"), atomic_identity=identity)
            topology = replace(topology,
                bond_indices=ArrayData(indices, ("bond", "endpoint"), "dimensionless"),
                bond_orders=ArrayData(orders, ("bond",), "dimensionless"),
                aromatic_flags=ArrayData(aromatic, ("bond",), "dimensionless"),
            )
            for value in (coordinates, isotopes, charges, maps, names, stereo, indices, orders, aromatic):
                value.close()
            self.assertTrue(all(not value.loaded for value in (coordinates, isotopes, charges, maps, names, stereo, indices, orders, aromatic)))
            export_mol(structure, topology)
            self.assertTrue(all(not value.loaded for value in (coordinates, isotopes, charges, maps, names, stereo, indices, orders, aromatic)))

    def test_sdf_midstream_fatal_errors_preserve_target_and_cleanup(self):
        from ChemBlender.core.exporters.rdkit_molecular import export_sdf

        structure, topology = self.source()
        with TemporaryDirectory() as directory:
            target = Path(directory) / "x.sdf"
            for error in (MemoryError("memory"), KeyboardInterrupt()):
                target.write_text("old", encoding="utf-8")
                def chunks(*_args):
                    yield "partial\n"
                    raise error
                with patch("ChemBlender.core.exporters.rdkit_molecular._sdf_chunks", chunks):
                    with self.assertRaises(type(error)):
                        export_sdf(structure, topology, destination=target)
                self.assertEqual(target.read_text(encoding="utf-8"), "old")
                self.assertEqual([item.name for item in Path(directory).iterdir()], ["x.sdf"])
            with patch("ChemBlender.core.exporters.xyz.os.fsync", side_effect=OSError("fsync")):
                with self.assertRaisesRegex(OSError, "fsync"):
                    export_sdf(structure, topology, destination=target)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_public_import_does_not_eagerly_import_rdkit(self):
        result = subprocess.run(
            [sys.executable, "-c", "import sys; import ChemBlender.core.exporters; assert 'rdkit' not in sys.modules"],
            cwd=Path(__file__).parents[1], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
