import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData
from ChemBlender.core.exporters import mol2_export_readiness
from ChemBlender.core.formats.mol2 import parse_mol2


FIXTURE = Path(__file__).with_name("fixtures") / "mol2" / "small.mol2"
AROMATIC_FIXTURE = Path(__file__).with_name("fixtures") / "mol2" / "aromatic.mol2"


class Mol2ExportReadinessTests(unittest.TestCase):
    def setUp(self):
        self.batch = parse_mol2(FIXTURE)
        self.aromatic_batch = parse_mol2(AROMATIC_FIXTURE)

    def dataset(self, semantic_role):
        return next(
            value
            for value in self.batch.datasets
            if value.semantic_role == semantic_role
        )

    def test_complete_mol2_entities_preserve_the_p1_contract(self):
        report = mol2_export_readiness(self.batch)

        self.assertEqual(report.status.value, "Complete")
        self.assertEqual(report.missing_fields, ())

    def test_raw_marker_acceptance_matches_the_mol2_tokenizer(self):
        raw = FIXTURE.read_bytes()
        molecule_tail = raw.split(b"\n", 1)[1]
        variants = (
            b"\xef\xbb\xbf  @<tripos>molecule  \r\n"
            + molecule_tail.replace(b"\n", b"\r\n"),
            b"\t@<TrIpOs>MoLeCuLe\t\n" + molecule_tail,
        )
        with TemporaryDirectory() as directory:
            for index, variant in enumerate(variants):
                with self.subTest(index=index):
                    source = Path(directory) / f"variant-{index}.mol2"
                    source.write_bytes(variant)
                    batch = parse_mol2(source)
                    report = mol2_export_readiness(batch)
                    self.assertEqual(report.status.value, "Complete")
                    self.assertNotIn(
                        "molecular_record.raw_tripos",
                        report.missing_fields,
                    )

    def test_missing_annotations_are_partial_not_a_structural_blocker(self):
        report = mol2_export_readiness(replace(self.batch, annotations=()))

        self.assertEqual(report.status.value, "Partial")
        self.assertEqual(
            report.missing_fields,
            ("annotation.charge_type", "annotation.molecule_type"),
        )

    def test_missing_topology_is_unsupported(self):
        report = mol2_export_readiness(replace(self.batch, topologies=()))

        self.assertEqual(report.status.value, "Unsupported")
        self.assertEqual(report.missing_fields, ("topology",))

    def test_missing_fields_are_sorted_and_deterministic(self):
        structure = replace(self.batch.structures[0], atomic_identity=None)
        incomplete = replace(
            self.batch,
            structures=(structure,),
            topologies=(),
            molecular_records=(),
            annotations=(),
            datasets=(),
        )

        first = mol2_export_readiness(incomplete)
        second = mol2_export_readiness(incomplete)

        self.assertEqual(first, second)
        self.assertEqual(first.status.value, "Unsupported")
        self.assertEqual(
            first.missing_fields,
            (
                "annotation.charge_type",
                "annotation.molecule_type",
                "dataset.atom_type",
                "dataset.partial_charge",
                "dataset.substructure_id",
                "dataset.substructure_name",
                "molecular_record.raw_tripos",
                "structure.atomic_identity.atom_names",
                "topology",
            ),
        )

    def test_unlinked_topology_and_record_do_not_change_the_explicit_context(self):
        topology = self.batch.topologies[0]
        extra_topology = replace(
            topology,
            id=uuid4(),
            bond_orders=ArrayData(
                numpy.asarray((1.5,)), ("bond",), "dimensionless"
            ),
            aromatic_flags=None,
        )
        extra_record = replace(
            self.batch.molecular_records[0],
            id=uuid4(),
            record_key="unlinked",
            source_record_index=1,
            topology_id=extra_topology.id,
        )
        extra_first = replace(
            self.batch,
            topologies=(extra_topology, topology),
            molecular_records=(extra_record, *self.batch.molecular_records),
        )
        extra_last = replace(
            self.batch,
            topologies=(topology, extra_topology),
            molecular_records=(*self.batch.molecular_records, extra_record),
        )

        self.assertEqual(mol2_export_readiness(extra_first), mol2_export_readiness(extra_last))
        self.assertEqual(mol2_export_readiness(extra_first).status.value, "Complete")

    def test_multiple_explicit_topologies_and_records_are_ambiguous(self):
        topology = self.batch.topologies[0]
        extra_topology = replace(topology, id=uuid4())
        extra_record = replace(
            self.batch.molecular_records[0],
            id=uuid4(),
            record_key="alternate",
            source_record_index=1,
            topology_id=extra_topology.id,
        )
        structure = replace(
            self.batch.structures[0],
            topology_ids=(topology.id, extra_topology.id),
        )
        report = mol2_export_readiness(
            replace(
                self.batch,
                structures=(structure,),
                topologies=(topology, extra_topology),
                molecular_records=(*self.batch.molecular_records, extra_record),
            )
        )

        self.assertEqual(report.status.value, "Unsupported")
        self.assertEqual(
            report.missing_fields,
            ("molecular_record.ambiguous", "topology.ambiguous"),
        )

    def test_multiple_explicit_topology_ids_are_ambiguous_when_one_is_missing(self):
        topology = self.batch.topologies[0]
        structure = replace(
            self.batch.structures[0], topology_ids=(topology.id, uuid4())
        )

        report = mol2_export_readiness(replace(self.batch, structures=(structure,)))

        self.assertEqual(report.status.value, "Unsupported")
        self.assertEqual(report.missing_fields, ("topology.ambiguous",))

    def test_duplicate_role_and_annotation_are_ambiguous(self):
        atom_type = self.dataset("atom_type")
        charge_type = next(
            value for value in self.batch.annotations if value.key == "charge_type"
        )
        report = mol2_export_readiness(
            replace(
                self.batch,
                datasets=(*self.batch.datasets, replace(atom_type, id=uuid4())),
                annotations=(
                    *self.batch.annotations,
                    replace(charge_type, id=uuid4(), value="NO_CHARGES"),
                ),
            )
        )

        self.assertEqual(report.status.value, "Unsupported")
        self.assertEqual(
            report.missing_fields,
            ("annotation.charge_type.ambiguous", "dataset.atom_type.ambiguous"),
        )

    def test_mixed_aromatic_and_nonaromatic_bond_orders_are_checked_per_bond(self):
        original = self.aromatic_batch.topologies[0]
        self.assertGreaterEqual(len(original.stereo_labels), 2)
        topology = replace(
            original,
            bond_orders=ArrayData(
                numpy.asarray(
                    (0.0, 1.5, *original.bond_orders.values[2:])
                ),
                ("bond",),
                "dimensionless",
            ),
            aromatic_flags=ArrayData(
                numpy.asarray((True, False, *original.aromatic_flags.values[2:])),
                ("bond",),
                "dimensionless",
            ),
        )

        report = mol2_export_readiness(
            replace(self.aromatic_batch, topologies=(topology,))
        )

        self.assertEqual(report.status.value, "Unsupported")
        self.assertIn("topology.bond_type_mapping", report.missing_fields)

    def test_categorical_ids_and_charges_are_not_numeric_properties(self):
        atom_type = self.dataset("atom_type")
        invalid_substructure = replace(self.dataset("substructure_id"), data=atom_type.data)
        invalid_charge = replace(self.dataset("partial_charge"), data=atom_type.data)
        datasets = tuple(
            invalid_substructure
            if value.id == invalid_substructure.id
            else invalid_charge
            if value.id == invalid_charge.id
            else value
            for value in self.batch.datasets
        )

        report = mol2_export_readiness(replace(self.batch, datasets=datasets))

        self.assertEqual(report.status.value, "Partial")
        self.assertEqual(
            report.missing_fields,
            ("dataset.partial_charge", "dataset.substructure_id"),
        )


if __name__ == "__main__":
    unittest.main()
