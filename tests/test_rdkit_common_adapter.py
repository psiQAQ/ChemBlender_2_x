import importlib
from dataclasses import fields
import os
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import UUID

import numpy


ROOT = Path(__file__).resolve().parents[1]
RDKIT_SITE = (
    Path(os.environ["APPDATA"])
    / "Blender Foundation"
    / "Blender"
    / "5.1"
    / "extensions"
    / ".local"
    / "lib"
    / "python3.13"
    / "site-packages"
)
if RDKIT_SITE.is_dir():
    sys.path.insert(0, str(RDKIT_SITE))

from rdkit import Chem
from rdkit.Chem import rdDepictor


def _context(module, *, record_key="record-0000"):
    return module.RDKitMoleculeContext(
        source_revision_id=UUID("11111111-1111-1111-1111-111111111111"),
        source_hash="a" * 64,
        record_key=record_key,
        source_record_index=0,
        title="adapter fixture",
        block_version="V2000",
    )


def _identity_values(identity):
    categories = identity.atom_names.categories
    names = tuple(
        None if code == identity.atom_names.missing_code else categories[code]
        for code in identity.atom_names.codes.values.tolist()
    )
    categories = identity.stereo_labels.categories
    stereo = tuple(
        None if code == identity.stereo_labels.missing_code else categories[code]
        for code in identity.stereo_labels.codes.values.tolist()
    )
    return (
        identity.isotopes.values.tolist(),
        identity.formal_charges.values.tolist(),
        identity.atom_map_numbers.values.tolist(),
        names,
        stereo,
    )


def _add_conformer(molecule):
    conformer = Chem.Conformer(molecule.GetNumAtoms())
    for index in range(molecule.GetNumAtoms()):
        conformer.SetAtomPosition(index, (float(index), 0.0, 0.0))
    conformer.Set3D(True)
    molecule.AddConformer(conformer)
    return molecule


class RDKitCommonAdapterTests(unittest.TestCase):
    @staticmethod
    def adapter():
        try:
            return importlib.import_module("ChemBlender.core.formats.rdkit_common")
        except ModuleNotFoundError as error:
            if error.name in {
                "ChemBlender.core.formats",
                "ChemBlender.core.formats.rdkit_common",
            }:
                raise AssertionError("shared RDKit adapter is missing") from error
            raise

    def test_core_and_reader_api_imports_do_not_load_rdkit(self):
        code = (
            "import sys; import ChemBlender.core; import ChemBlender.reader_api; "
            "assert 'rdkit' not in sys.modules"
        )
        subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)

    def test_maps_identity_explicit_topology_and_raw_bytes_deterministically(self):
        adapter = self.adapter()
        molecule = Chem.MolFromSmiles("[13CH3:7][C@H:8](F)/C=C/[N+:9](C)(C)C")
        _add_conformer(molecule)
        molecule.GetAtomWithIdx(0).SetProp("atomName", "isotope-carbon")
        molecule.GetAtomWithIdx(1).SetProp("atomName", "stereo-carbon")
        molecule.GetBondWithIdx(2).SetStereo(Chem.BondStereo.STEREOE)
        raw = b"adapter\r\nexact raw bytes\xff\n"

        first = adapter.adapt_rdkit_molecule(molecule, raw, _context(adapter))
        second = adapter.adapt_rdkit_molecule(molecule, raw, _context(adapter))

        self.assertEqual(first.raw_block, raw)
        self.assertEqual(first.structure.id, second.structure.id)
        self.assertEqual(first.provenance.id, second.provenance.id)
        self.assertEqual(first.molecular_record.id, second.molecular_record.id)
        self.assertEqual(first.structure.topology_ids, (first.topologies[0].id,))
        self.assertEqual(first.topologies[0].source_kind.value, "explicit_file")
        self.assertEqual(first.topologies[0].bond_indices.values.tolist(), [[0, 1], [1, 2], [1, 3], [3, 4], [4, 5], [5, 6], [5, 7], [5, 8]])
        self.assertEqual(first.topologies[0].bond_orders.values.tolist(), [1.0, 1.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0])
        self.assertEqual(first.topologies[0].stereo_labels[3], "E")
        self.assertEqual(
            _identity_values(first.structure.atomic_identity),
            ([13, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 1, 0, 0, 0], [7, 8, 0, 0, 0, 9, 0, 0, 0], ("isotope-carbon", "stereo-carbon", None, None, None, None, None, None, None), (None, "CHI_TETRAHEDRAL_CCW", None, None, None, None, None, None, None)),
        )
        self.assertFalse(
            any(
                type(getattr(first, field.name)).__module__.startswith("rdkit")
                for field in fields(first)
            )
        )

    def test_uses_a_second_sanitized_topology_only_when_sanitization_changes_interpretation(self):
        adapter = self.adapter()
        molecule = Chem.MolFromSmiles("C1=CC=CC=C1", sanitize=False)

        adapted = adapter.adapt_rdkit_molecule(molecule, b"kekule\n", _context(adapter))

        self.assertEqual(
            tuple(item.source_kind.value for item in adapted.topologies),
            ("explicit_file", "rdkit_sanitized"),
        )
        self.assertEqual(adapted.topologies[0].bond_orders.values.tolist(), [2.0, 1.0, 1.0, 2.0, 1.0, 2.0])
        self.assertEqual(adapted.topologies[1].bond_orders.values.tolist(), [1.5] * 6)
        self.assertEqual(adapted.topologies[1].aromatic_flags.values.tolist(), [True] * 6)

    def test_sanitize_failure_retains_explicit_topology_and_diagnostic(self):
        adapter = self.adapter()
        editable = Chem.RWMol()
        carbon = editable.AddAtom(Chem.Atom(6))
        for _ in range(5):
            editable.AddBond(carbon, editable.AddAtom(Chem.Atom(9)), Chem.BondType.SINGLE)
        _add_conformer(editable)

        adapted = adapter.adapt_rdkit_molecule(editable.GetMol(), b"invalid-valence\n", _context(adapter))

        self.assertEqual(len(adapted.topologies), 1)
        self.assertEqual(adapted.topologies[0].source_kind.value, "explicit_file")
        self.assertEqual(tuple(item.code for item in adapted.diagnostics), ("mol.sanitize_failed",))
        self.assertEqual(adapted.molecular_record.raw_block, b"invalid-valence\n")

    def test_preserves_3d_coordinates_and_labels_planar_2d(self):
        adapter = self.adapter()
        three_dimensional = Chem.MolFromSmiles("CO")
        conformer = Chem.Conformer(2)
        conformer.SetAtomPosition(0, (1.0, 2.0, 3.0))
        conformer.SetAtomPosition(1, (4.0, 5.0, 6.0))
        conformer.Set3D(True)
        three_dimensional.AddConformer(conformer)
        planar = Chem.MolFromSmiles("C=C")
        rdDepictor.Compute2DCoords(planar)

        three_d = adapter.adapt_rdkit_molecule(three_dimensional, b"3d\n", _context(adapter, record_key="3d"))
        two_d = adapter.adapt_rdkit_molecule(planar, b"2d\n", _context(adapter, record_key="2d"))

        self.assertTrue(numpy.array_equal(three_d.structure.coordinates.values, numpy.asarray(((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))))
        self.assertTrue(numpy.allclose(two_d.structure.coordinates.values[:, 2], 0.0))
        self.assertEqual(tuple(item.code for item in two_d.diagnostics), ("mol.coordinates_2d",))

    def test_missing_conformer_has_no_fake_structure_or_record(self):
        adapter = self.adapter()

        adapted = adapter.adapt_rdkit_molecule(Chem.MolFromSmiles("CC"), b"no coordinates\n", _context(adapter))

        self.assertIsNone(adapted.structure)
        self.assertIsNone(adapted.molecular_record)
        self.assertEqual(len(adapted.topologies), 1)
        self.assertEqual(adapted.topologies[0].source_kind.value, "explicit_file")
        self.assertEqual(tuple(item.code for item in adapted.diagnostics), ("mol.coordinates_missing",))


if __name__ == "__main__":
    unittest.main()
