import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "legacy-blend"
README = FIXTURE_ROOT / "README.md"
METADATA_BEGIN = "<!-- fixture-metadata-begin -->"
METADATA_END = "<!-- fixture-metadata-end -->"

EXPECTED = {
    "chemblender-2.1-molecule.blend": {
        "sha256": "36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4",
        "bytes": 153914,
        "chemblender_version": "2.1.1",
        "chemblender_commit": "2b72abf9e0e1f987014c8a95193bed06cc8dd988",
        "blender_version": "5.1.2",
        "collections": ["Legacy 2.1 Molecule"],
        "objects": ["legacy_formaldehyde"],
        "expected_recoverable_fields": [
            'object["Type"]',
            'object["Elements"]',
            "mesh.vertices",
            "mesh.edges",
            "mesh.attributes.atomic_num",
            "mesh.attributes.bond_order",
            "mesh.attributes.atom_scale_f",
            "mesh.attributes.bond_scale_f",
            "geometry_nodes",
        ],
    },
    "chemblender-2.2-crystal.blend": {
        "sha256": "f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a",
        "bytes": 201029,
        "chemblender_version": "2.2.0",
        "chemblender_commit": "cdc723649a28fe30cfa2ba956318444fc3783ec1",
        "blender_version": "5.1.2",
        "collections": ["Legacy 2.2 Crystal"],
        "objects": ["cell_edges_partial_uij", "unit_partial_uij"],
        "expected_recoverable_fields": [
            'object["Type"]',
            'object["cell lengths"]',
            'object["cell angles"]',
            'object["space group"]',
            'object["SG No."]',
            'object["symops"]',
            "object.cif_original.atoms[].occupancy",
            "object.cif_original.atoms[].u11..u23",
            "object.cif_current.atoms[].occupancy",
            "object.cif_current.atoms[].u11..u23",
            "mesh.attributes.atomic_num",
            "mesh.attributes.u_scale",
            "mesh.attributes.u_v1",
            "mesh.attributes.u_v2",
            "mesh.attributes.u_v3",
            "cell_edges.custom_properties",
        ],
    },
    "chemblender-2.2-edited-scaffold.blend": {
        "sha256": "a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740",
        "bytes": 154011,
        "chemblender_version": "2.2.0",
        "chemblender_commit": "cdc723649a28fe30cfa2ba956318444fc3783ec1",
        "blender_version": "5.1.2",
        "collections": ["Legacy 2.2 Edited Scaffold"],
        "objects": ["legacy_edited_ethanol"],
        "expected_recoverable_fields": [
            'object["Type"]',
            'object["Elements"]',
            "mesh.vertices",
            "mesh.edges",
            "mesh.attributes.atomic_num",
            "mesh.attributes.bond_order",
            "mesh.attributes.atom_scale_f",
            "mesh.attributes.bond_scale_f",
            "mesh.attributes.colour",
            "mesh.attributes.dashed",
            "geometry_nodes",
        ],
    },
}


def read_metadata():
    text = README.read_text(encoding="utf-8")
    payload = text.split(METADATA_BEGIN, 1)[1].split(METADATA_END, 1)[0]
    payload = payload.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(payload)


class LegacyFixtureInventoryTests(unittest.TestCase):
    def test_expected_fixture_files_exist(self):
        missing = [
            path.name
            for path in [README, *(FIXTURE_ROOT / name for name in EXPECTED)]
            if not path.is_file()
        ]

        self.assertEqual(missing, [])

    def test_binary_hashes_match_reviewed_inventory(self):
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                path = FIXTURE_ROOT / name
                self.assertTrue(path.is_file(), f"missing fixture for hash: {name}")
                data = path.read_bytes()
                self.assertGreater(len(data), 1024)
                self.assertTrue(
                    data.startswith((b"BLENDER", b"\x28\xb5\x2f\xfd"))
                )
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected["sha256"])
                self.assertEqual(len(data), expected["bytes"])

    def test_readme_metadata_matches_binary_inventory(self):
        self.assertTrue(README.is_file(), "missing fixture companion metadata")
        metadata = read_metadata()

        self.assertEqual(metadata["schema_version"], 1)
        self.assertIs(metadata["redistributable"], True)
        recorded = {item["file"]: item for item in metadata["fixtures"]}
        self.assertEqual(set(recorded), set(EXPECTED))
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                self.assertEqual(recorded[name], {"file": name, **expected})
                path = FIXTURE_ROOT / name
                self.assertEqual(recorded[name]["bytes"], path.stat().st_size)
                self.assertEqual(
                    recorded[name]["sha256"],
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
