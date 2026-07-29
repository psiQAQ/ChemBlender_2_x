import importlib
from dataclasses import fields
from enum import Enum, StrEnum
import inspect
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
_RDKIT_SITE_PATH = str(RDKIT_SITE)
_added_rdkit_site = RDKIT_SITE.is_dir() and _RDKIT_SITE_PATH not in sys.path
if _added_rdkit_site:
    sys.path.insert(0, _RDKIT_SITE_PATH)

try:
    from rdkit import Chem
    from rdkit.Chem import rdDepictor
finally:
    if _added_rdkit_site:
        sys.path.remove(_RDKIT_SITE_PATH)

from ChemBlender.core import ImportBatch
from ChemBlender.core.import_pipeline import ValidationMode
from ChemBlender.reader_api.builtin_bridge import public_batch_from_internal


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


class RDKitHarnessIsolationTests(unittest.TestCase):
    def test_import_does_not_retain_or_reorder_shared_dependency_path(self):
        self.assertTrue(RDKIT_SITE.is_dir())
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        for already_present in (False, True):
            with self.subTest(already_present=already_present):
                code = f"""
import os
import sys
from pathlib import Path

site = Path(os.environ["APPDATA"]) / "Blender Foundation" / "Blender" / "5.1" / "extensions" / ".local" / "lib" / "python3.13" / "site-packages"
site_text = str(site)
if {already_present}:
    sys.path.insert(2, site_text)
else:
    assert site_text not in sys.path
before = list(sys.path)
import tests.test_rdkit_common_adapter
assert sys.path == before, (before, sys.path)
"""
                subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=ROOT,
                    check=True,
                    env=environment,
                )


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
        molecule = _add_conformer(Chem.MolFromSmiles("C1=CC=CC=C1", sanitize=False))

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
        planar.GetConformer().SetAtomPosition(0, (0.0, 0.0, 9.0))
        planar.GetConformer().SetAtomPosition(1, (1.0, 0.0, -9.0))

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
        self.assertEqual(adapted.topologies, ())
        self.assertEqual(tuple(item.code for item in adapted.diagnostics), ("mol.coordinates_missing",))

    def test_context_preserves_writer_metadata_and_validates_mode(self):
        adapter = self.adapter()
        names = {field.name for field in fields(adapter.RDKitMoleculeContext)}

        self.assertTrue({"writer_name", "writer_version", "validation_mode"} <= names)
        context = adapter.RDKitMoleculeContext(
            source_revision_id=UUID("11111111-1111-1111-1111-111111111111"),
            source_hash="a" * 64,
            record_key="writer",
            source_record_index=0,
            title="writer fixture",
            block_version="V2000",
            writer_name="RDKit",
            writer_version="2026.03.3",
            validation_mode="maximum",
        )
        adapted = adapter.adapt_rdkit_molecule(
            _add_conformer(Chem.MolFromSmiles("CO")), b"writer\n", context
        )
        self.assertEqual(adapted.molecular_record.writer_name, "RDKit")
        self.assertEqual(adapted.molecular_record.writer_version, "2026.03.3")
        with self.assertRaises(ValueError):
            adapter.RDKitMoleculeContext(
                UUID(int=1), "a" * 64, "invalid", 0, "", None,
                "", None, "guess",
            )

    def test_cancellation_is_cooperative_and_fatal_callback_errors_propagate(self):
        adapter = self.adapter()
        parameters = inspect.signature(adapter.adapt_rdkit_molecule).parameters

        self.assertIn("is_cancelled", parameters)
        cancelled = getattr(adapter, "RDKitMoleculeCancelled", None)
        self.assertIsNotNone(cancelled)
        molecule = _add_conformer(Chem.MolFromSmiles("CO"))
        with self.assertRaises(cancelled):
            adapter.adapt_rdkit_molecule(
                molecule, b"cancel\n", _context(adapter), is_cancelled=lambda: True
            )
        failure = RuntimeError("cancellation callback failed")
        with self.assertRaises(RuntimeError) as raised:
            adapter.adapt_rdkit_molecule(
                molecule,
                b"fatal\n",
                _context(adapter),
                is_cancelled=lambda: (_ for _ in ()).throw(failure),
            )
        self.assertIs(raised.exception, failure)

    def test_alias_bond_direction_and_assigned_double_bond_stereo_are_preserved(self):
        adapter = self.adapter()
        mol_block = b"""\n     RDKit          2D\n\n  4  3  0  0  0  0  0  0  0  0999 V2000\n   -1.9796   -0.1365    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\n   -0.5994    0.4508    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n    0.5994   -0.4508    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n    1.9796    0.1365    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\n  1  2  1  0\n  2  3  2  0\n  3  4  1  0\nM  END\n"""
        molecule = Chem.MolFromMolBlock(mol_block, sanitize=False, removeHs=False)
        molecule.GetAtomWithIdx(0).SetProp("molFileAlias", "fluorine-alias")

        adapted = adapter.adapt_rdkit_molecule(molecule, mol_block, _context(adapter))

        self.assertEqual(_identity_values(adapted.structure.atomic_identity)[3][0], "fluorine-alias")
        self.assertEqual(
            adapted.topologies[0].stereo_labels,
            ("bond_dir:endupright", "", "bond_dir:endupright"),
        )
        self.assertEqual(
            adapted.topologies[1].stereo_labels,
            ("bond_dir:endupright", "E", "bond_dir:endupright"),
        )

    def test_nonfinite_coordinates_and_zero_bond_molecules_keep_valid_fragments(self):
        adapter = self.adapter()
        invalid = _add_conformer(Chem.MolFromSmiles("CO"))
        invalid.GetConformer().SetAtomPosition(0, (float("nan"), 0.0, 0.0))

        adapted = adapter.adapt_rdkit_molecule(invalid, b"nan\n", _context(adapter))

        self.assertIsNone(adapted.structure)
        self.assertIsNone(adapted.molecular_record)
        self.assertEqual(adapted.topologies, ())
        self.assertEqual(tuple(item.code for item in adapted.diagnostics), ("mol.coordinates_invalid",))
        helium = _add_conformer(Chem.MolFromSmiles("[He]"))
        zero_bond = adapter.adapt_rdkit_molecule(helium, b"helium\n", _context(adapter, record_key="helium"))
        self.assertEqual(zero_bond.topologies[0].bond_indices.shape, (0, 2))
        self.assertEqual(zero_bond.topologies[0].bond_orders.shape, (0,))

    def test_uncommon_bond_stereo_labels_are_not_discarded(self):
        adapter = self.adapter()
        for stereo, expected in (
            (Chem.BondStereo.STEREOANY, "stereo:any"),
            (Chem.BondStereo.STEREOATROPCCW, "stereo:atropccw"),
        ):
            with self.subTest(stereo=stereo):
                molecule = _add_conformer(Chem.MolFromSmiles("CC"))
                molecule.GetBondWithIdx(0).SetStereo(stereo)
                adapted = adapter.adapt_rdkit_molecule(
                    molecule,
                    f"{stereo}\n".encode(),
                    _context(adapter, record_key=str(stereo)),
                )
                self.assertEqual(adapted.topologies[0].stereo_labels, (expected,))

    def test_validation_mode_enum_is_canonicalized_for_the_public_bridge(self):
        adapter = self.adapter()
        context = adapter.RDKitMoleculeContext(
            UUID("11111111-1111-1111-1111-111111111111"),
            "a" * 64,
            "mode",
            0,
            "mode fixture",
            "V2000",
            validation_mode=ValidationMode.MAXIMUM,
        )
        adapted = adapter.adapt_rdkit_molecule(
            _add_conformer(Chem.MolFromSmiles("CO")), b"mode\n", context
        )

        self.assertEqual(context.validation_mode, "maximum")
        try:
            public = public_batch_from_internal(
                ImportBatch(
                    structures=(adapted.structure,),
                    topologies=adapted.topologies,
                    molecular_records=(adapted.molecular_record,),
                    provenance=(adapted.provenance,),
                    diagnostics=adapted.diagnostics,
                )
            )
        except TypeError as error:
            self.fail(f"ValidationMode leaked through public bridge: {error}")
        self.assertEqual(
            public.provenance[0].parameters,
            (("record_key", "mode"), ("rdkit_sanitized", True), ("validation_mode", "maximum")),
        )

    def test_context_text_str_enums_are_canonicalized_for_the_public_bridge(self):
        class ContextText(str, Enum):
            SOURCE_HASH = "a" * 64
            RECORD_KEY = "enum-record"
            TITLE = "enum title"
            BLOCK_VERSION = "V2000"
            WRITER_NAME = "RDKit"
            WRITER_VERSION = "2026.03.3"

        class ContextStrEnum(StrEnum):
            SOURCE_HASH = "a" * 64
            RECORD_KEY = "enum-record"
            TITLE = "enum title"
            BLOCK_VERSION = "V2000"
            WRITER_NAME = "RDKit"
            WRITER_VERSION = "2026.03.3"

        adapter = self.adapter()
        values = {
            "source_revision_id": UUID("11111111-1111-1111-1111-111111111111"),
            "source_hash": "a" * 64,
            "record_key": "plain-record",
            "source_record_index": 0,
            "title": "plain title",
            "block_version": "V2000",
            "writer_name": "plain writer",
            "writer_version": "1",
            "validation_mode": "maximum",
        }
        for enum_type in (ContextText, ContextStrEnum):
            enum_fields = {
                "source_hash": enum_type.SOURCE_HASH,
                "record_key": enum_type.RECORD_KEY,
                "title": enum_type.TITLE,
                "block_version": enum_type.BLOCK_VERSION,
                "writer_name": enum_type.WRITER_NAME,
                "writer_version": enum_type.WRITER_VERSION,
            }
            for name, value in enum_fields.items():
                with self.subTest(enum_type=enum_type.__name__, name=name):
                    candidate = dict(values)
                    candidate[name] = value
                    context = adapter.RDKitMoleculeContext(**candidate)
                    self.assertIs(type(getattr(context, name)), str)
                    self.assertEqual(getattr(context, name), value.value)

        context = adapter.RDKitMoleculeContext(
            **{
                **values,
                "source_hash": ContextText.SOURCE_HASH,
                "record_key": ContextText.RECORD_KEY,
                "title": ContextText.TITLE,
                "block_version": ContextText.BLOCK_VERSION,
                "writer_name": ContextText.WRITER_NAME,
                "writer_version": ContextText.WRITER_VERSION,
            }
        )
        adapted = adapter.adapt_rdkit_molecule(
            _add_conformer(Chem.MolFromSmiles("CO")), b"context\n", context
        )
        try:
            public = public_batch_from_internal(
                ImportBatch(
                    structures=(adapted.structure,),
                    topologies=adapted.topologies,
                    molecular_records=(adapted.molecular_record,),
                    provenance=(adapted.provenance,),
                    diagnostics=adapted.diagnostics,
                )
            )
        except TypeError as error:
            self.fail(f"context text subtype leaked through public bridge: {error}")
        self.assertIs(type(public.molecular_records[0].record_key), str)
        self.assertIs(type(public.molecular_records[0].title), str)
        self.assertIs(type(public.molecular_records[0].block_version), str)
        self.assertIs(type(public.molecular_records[0].writer_name), str)
        self.assertIs(type(public.molecular_records[0].writer_version), str)
        self.assertIs(type(public.provenance[0].source_hash), str)


if __name__ == "__main__":
    unittest.main()
