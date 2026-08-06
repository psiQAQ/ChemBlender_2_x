import hashlib
import json
import re
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
EXPECTED_DOCS = (
    "README.md",
    "01-import.md",
    "02-process.md",
    "03-visualize.md",
    "04-export.md",
    "05-project-lifecycle.md",
    "formats.md",
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
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


class UserWorkflowContractTests(unittest.TestCase):
    def manifest(self):
        path = EXAMPLE_ROOT / "manifest.json"
        self.assertTrue(path.is_file(), path)
        return json.loads(path.read_text(encoding="utf-8"))

    def local_link_targets(self, path):
        targets = set()
        for raw_target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
            raw_target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not raw_target or raw_target.startswith(("http://", "https://", "mailto:")):
                continue
            target = (path.parent / raw_target).resolve()
            self.assertTrue(target.is_relative_to(ROOT.resolve()), (path, raw_target))
            self.assertTrue(target.exists(), (path, raw_target))
            targets.add(target)
        return targets

    def test_workflow_document_inventory_and_links(self):
        paths = tuple(DOC_ROOT / name for name in EXPECTED_DOCS)
        for path in paths:
            self.assertTrue(path.is_file(), path)
        for path in paths:
            self.local_link_targets(path)

    def test_repository_entrypoints_link_to_workflow_index(self):
        index = (DOC_ROOT / "README.md").resolve()
        for path in (
            ROOT / "README.md",
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "user" / "2.4.0-experience-review.md",
        ):
            self.assertIn(index, self.local_link_targets(path), path)

    def test_every_sample_is_linked_from_the_workflow_documents(self):
        linked = set()
        for name in EXPECTED_DOCS:
            path = DOC_ROOT / name
            if path.is_file():
                linked.update(self.local_link_targets(path))
        expected = {
            (EXAMPLE_ROOT / record["path"]).resolve()
            for record in self.manifest()["files"]
        }
        self.assertEqual(expected - linked, set())

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
