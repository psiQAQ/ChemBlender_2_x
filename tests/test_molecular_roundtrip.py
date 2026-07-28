import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory


class MolecularRoundTripTests(unittest.TestCase):
    def test_semantic_molecular_roundtrip_comparator_is_public(self):
        from ChemBlender.core.exporters.rdkit_molecular import (
            semantic_molecular_differences,
        )

        self.assertTrue(callable(semantic_molecular_differences))

    def test_mol_roundtrip_preserves_molecular_semantics(self):
        from ChemBlender.core.exporters.rdkit_molecular import (
            export_mol,
            semantic_molecular_differences,
        )
        from ChemBlender.core.formats.mol import parse_mol
        from ChemBlender.core.formats.smiles import parse_smiles_text

        source = parse_smiles_text("[13CH3:7][C@H:8](F)/C=C/[N+:9](C)(C)C")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "roundtrip.mol"
            export_mol(source.structures[0], source.topologies[0], destination=path)
            reopened = parse_mol(path)
        self.assertEqual(semantic_molecular_differences(source, reopened), ())

    def test_tetrasubstituted_ez_roundtrip_uses_verified_structure_record_seed(self):
        from ChemBlender.core.exporters.rdkit_molecular import (
            export_mol,
            semantic_molecular_differences,
        )
        from ChemBlender.core.formats.mol import parse_mol
        from ChemBlender.core.formats.smiles import parse_smiles_text

        source = parse_smiles_text("F/C(Cl)=C(Br)/I")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ez.mol"
            export_mol(
                source.structures[0], source.topologies[0],
                record=source.molecular_records[0], destination=path,
            )
            reopened = parse_mol(path)
        self.assertEqual(semantic_molecular_differences(source, reopened), ())

    def test_nonisomeric_smiles_roundtrip_allows_documented_non_graph_losses(self):
        from ChemBlender.core.exporters.rdkit_molecular import (
            export_smiles,
            semantic_molecular_differences,
        )
        from ChemBlender.core.formats.smiles import parse_smiles_text

        source = parse_smiles_text("[13CH3:7][C@H:8](F)/C=C/[N+:9](C)(C)C")
        text = export_smiles(source.structures[0], source.topologies[0], isomeric=False, confirm_loss=True).text
        reopened = parse_smiles_text(text)
        self.assertEqual(semantic_molecular_differences(source, reopened, allow_smiles_loss=True, allow_nonisomeric_smiles_loss=True), ())

    def test_comparator_detects_multiplicity_and_large_coordinate_delta(self):
        from ChemBlender.core.exporters.rdkit_molecular import semantic_molecular_differences
        from ChemBlender.core.formats.smiles import parse_smiles_text
        from ChemBlender.core.model import ArrayData, ImportBatch
        import numpy

        source = parse_smiles_text("CO")
        multiplicity = replace(source.structures[0], molecular_multiplicity=2)
        changed = replace(source, structures=(multiplicity,))
        self.assertIn("molecular multiplicity differs", semantic_molecular_differences(source, changed)[0])
        coordinates = numpy.asarray(source.structures[0].coordinates.values).copy()
        coordinates[0, 0] = 1000.0005
        shifted = replace(source.structures[0], coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"))
        changed = replace(source, structures=(shifted,))
        self.assertIn("coordinates differ", semantic_molecular_differences(source, changed)[0])


if __name__ == "__main__":
    unittest.main()
