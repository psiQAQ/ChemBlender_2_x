import unittest
from dataclasses import replace
from pathlib import Path

from ChemBlender.core.exporters import mol2_export_readiness
from ChemBlender.core.formats.mol2 import parse_mol2


FIXTURE = Path(__file__).with_name("fixtures") / "mol2" / "small.mol2"


class Mol2ExportReadinessTests(unittest.TestCase):
    def setUp(self):
        self.batch = parse_mol2(FIXTURE)

    def test_complete_mol2_entities_preserve_the_p1_contract(self):
        report = mol2_export_readiness(self.batch)

        self.assertEqual(report.status.value, "Complete")
        self.assertEqual(report.missing_fields, ())

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


if __name__ == "__main__":
    unittest.main()
