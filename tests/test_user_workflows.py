import hashlib
import json
import unittest
from pathlib import Path

from ChemBlender.core.cjson_adapter import parse_cjson
from ChemBlender.core.cube import parse_cube
from ChemBlender.core.formats.extxyz import parse_extxyz
from ChemBlender.core.formats.mol2 import parse_mol2
from ChemBlender.core.formats.pdb import parse_pdb
from ChemBlender.core.formats.poscar import parse_poscar
from ChemBlender.core.formats.pqr import parse_pqr
from ChemBlender.core.qcschema_adapter import parse_qcschema
from ChemBlender.core.xyz import parse_xyz


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs" / "user" / "workflows"
EXAMPLE_ROOT = ROOT / "examples" / "user-workflows"
EXPECTED_FAMILIES = (
    "cif",
    "cjson",
    "cube",
    "extxyz",
    "legacy",
    "mol",
    "mol2",
    "pdb",
    "poscar",
    "pqr",
    "qcschema",
    "sdf",
    "smiles",
    "xyz",
)
REQUIRED_RECORD_KEYS = {
    "path",
    "family",
    "source",
    "provenance",
    "sha256",
    "bytes",
    "runtime",
    "expected",
    "workflow",
}


class UserWorkflowContractTests(unittest.TestCase):
    def manifest(self):
        path = EXAMPLE_ROOT / "manifest.json"
        self.assertTrue(path.is_file(), path)
        return json.loads(path.read_text(encoding="utf-8"))

    def test_manifest_covers_each_base_format_family(self):
        manifest = self.manifest()
        self.assertEqual(manifest["schema_version"], "1")
        families = tuple(
            sorted({record["family"] for record in manifest["files"]})
        )
        self.assertEqual(families, EXPECTED_FAMILIES)

    def test_manifest_paths_are_unique_and_ordinally_sorted(self):
        records = self.manifest()["files"]
        paths = [record["path"] for record in records]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        for record in records:
            self.assertTrue(REQUIRED_RECORD_KEYS <= record.keys())

    def test_manifest_matches_tracked_file_bytes(self):
        for record in self.manifest()["files"]:
            path = EXAMPLE_ROOT / record["path"]
            data = path.read_bytes()
            self.assertEqual(record["bytes"], len(data), path)
            self.assertEqual(
                record["sha256"], hashlib.sha256(data).hexdigest(), path
            )
            self.assertLessEqual(len(data), 100 * 1024 * 1024, path)
            if len(data) > 50 * 1024 * 1024:
                self.assertTrue(record.get("size_exception_reason"), path)

    def test_builtin_samples_parse_to_expected_entities(self):
        cases = (
            (
                "inputs/cjson/water-results.cjson",
                parse_cjson,
                ("structures", "cjson_envelopes"),
            ),
            (
                "inputs/cube/two-datasets.cube",
                parse_cube,
                ("structures", "datasets"),
            ),
            (
                "inputs/extxyz/carbon-trajectory.extxyz",
                parse_extxyz,
                ("structures",),
            ),
            (
                "inputs/mol2/substructure.mol2",
                parse_mol2,
                ("structures", "topologies"),
            ),
            ("inputs/pdb/multimodel.pdb", parse_pdb, ("structures",)),
            ("inputs/poscar/si.POSCAR", parse_poscar, ("structures",)),
            ("inputs/poscar/velocities.CONTCAR", parse_poscar, ("structures",)),
            (
                "inputs/pqr/with-chain.pqr",
                parse_pqr,
                ("structures", "biological_hierarchies", "datasets"),
            ),
            (
                "inputs/qcschema/atomic-result.json",
                parse_qcschema,
                ("structures", "qcschema_envelopes"),
            ),
            ("inputs/xyz/water.xyz", parse_xyz, ("structures",)),
        )
        for relative, parser, attributes in cases:
            with self.subTest(path=relative):
                batch = parser(EXAMPLE_ROOT / relative)
                for attribute in attributes:
                    self.assertTrue(getattr(batch, attribute), attribute)

    def test_dependency_backed_samples_are_declared_for_blender_runtime(self):
        records = self.manifest()["files"]
        declared = {
            (record["family"], record["runtime"])
            for record in records
            if record["runtime"] in {"gemmi", "rdkit"}
        }
        self.assertEqual(
            declared,
            {
                ("cif", "gemmi"),
                ("mol", "rdkit"),
                ("sdf", "rdkit"),
                ("smiles", "rdkit"),
            },
        )


if __name__ == "__main__":
    unittest.main()
