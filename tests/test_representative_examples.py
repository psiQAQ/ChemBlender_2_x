import hashlib
import importlib.util
import io
import json
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = ROOT / "examples" / "user-workflows"
MANIFEST = EXAMPLE_ROOT / "manifest.json"
PREPARATION_SCRIPT = EXAMPLE_ROOT / "scripts" / "prepare_representative_inputs.py"
DIRECT_REPRESENTATIVE_PATHS = {
    "inputs/cif/cod-4503272-caffeine-cocrystal.cif",
    "inputs/cjson/avogadro-phthalocyanine.cjson",
    "inputs/mol2/openbabel-5sun-protein.mol2",
    "inputs/pdb/1d3z-ubiquitin-nmr.pdb",
    "inputs/pqr/apbs-protein-rna-nb.pqr",
    "inputs/qcschema/molssi-water-gradient-hf.json",
}
REPRESENTATIVE_MINIMUMS = {
    "inputs/extxyz/aspirin-rmd17-32.extxyz": {
        "frames": 32,
        "atoms_per_frame": 21,
    },
    "inputs/pdb/1d3z-ubiquitin-nmr.pdb": {"frames": 10},
    "inputs/mol2/openbabel-5sun-protein.mol2": {
        "atoms": 6185,
        "substructures": 390,
    },
    "inputs/cube/h2-lcao-1s-density-64.cube": {"grid": [64, 64, 64]},
    "inputs/sdf/ccd-3d-showcase.sdf": {"records": 3},
    "inputs/poscar/cod-9012293-diamond-2x2x2.CONTCAR": {"sites": 64},
}
REQUIRED_DOCUMENT_HEADINGS = (
    "## 用途与选择理由",
    "## 来源与许可",
    "## 规模与分辨率",
    "## 字段说明",
    "## ChemBlender 支持边界",
    "## 操作流程",
    "## Agent 提示词",
    "## 完整性与验证",
    "## 参考资料",
)
REQUIRED_KEYS = {
    "path",
    "family",
    "role",
    "source_platform",
    "source_id",
    "source_url",
    "retrieved_at",
    "license",
    "license_url",
    "derivation",
    "source_sha256",
    "sha256",
    "bytes",
    "runtime",
    "expected",
    "workflow",
    "metrics",
    "specifications",
    "documentation",
}


class RepresentativeExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.records = cls.manifest["files"]

    def test_manifest_schema_two_is_complete(self):
        self.assertEqual(self.manifest["schema_version"], "2")
        for record in self.records:
            self.assertEqual(set(record), REQUIRED_KEYS, record["path"])
            self.assertIn(record["role"], {"contract", "representative"})
            self.assertTrue(
                record["source_url"].startswith(("https://", "repository:")),
                record["path"],
            )
            self.assertTrue(record["license"])
            self.assertTrue(record["license_url"].startswith(("https://", "repository:")))
            self.assertTrue(record["documentation"].endswith(".md"))
            self.assertTrue(record["metrics"])
            self.assertTrue(record["specifications"])
            for specification in record["specifications"]:
                self.assertEqual(set(specification), {"title", "version", "url"})
                self.assertTrue(specification["url"].startswith("https://"))

    def test_manifest_exact_bytes_and_limits(self):
        for record in self.records:
            path = EXAMPLE_ROOT / record["path"]
            payload = path.read_bytes()
            self.assertEqual(len(payload), record["bytes"], record["path"])
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(),
                record["sha256"],
                record["path"],
            )
            self.assertLess(len(payload), 50 * 1024 * 1024, record["path"])
            self.assertLessEqual(len(payload), 100 * 1024 * 1024, record["path"])

    def test_authoritative_direct_sources_are_manifested(self):
        representative = {
            record["path"]
            for record in self.records
            if record["role"] == "representative"
        }
        self.assertTrue(DIRECT_REPRESENTATIVE_PATHS <= representative)

    def test_representative_metrics_meet_format_thresholds(self):
        by_path = {record["path"]: record for record in self.records}
        for path, expected in REPRESENTATIVE_MINIMUMS.items():
            with self.subTest(path=path):
                self.assertEqual(by_path[path]["role"], "representative")
                for key, value in expected.items():
                    self.assertEqual(by_path[path]["metrics"][key], value)

    def test_each_input_has_user_facing_adjacent_documentation(self):
        for record in self.records:
            with self.subTest(path=record["path"]):
                document = EXAMPLE_ROOT / record["documentation"]
                text = document.read_text(encoding="utf-8")
                for heading in REQUIRED_DOCUMENT_HEADINGS:
                    self.assertIn(heading, text)
                self.assertIn(record["source_id"], text)
                self.assertIn(record["license"], text)
                self.assertIn(record["retrieved_at"], text)
                self.assertIn(record["sha256"], text)
                self.assertIn(str(record["bytes"]), text)
                self.assertIn("Blender MCP", text)
                self.assertIn("bpy.ops.chemblender", text)

    def test_manifest_sdf_metrics_match_parsed_records(self):
        from ChemBlender.core.formats.sdf import parse_sdf

        for record in (item for item in self.records if item["family"] == "sdf"):
            with self.subTest(path=record["path"]):
                batch = parse_sdf(EXAMPLE_ROOT / record["path"])
                self.assertEqual(record["metrics"]["records"], len(batch.molecular_records))
                if "property_keys" in record["metrics"]:
                    property_keys = {
                        item.name
                        for molecular_record in batch.molecular_records
                        for item in molecular_record.ordered_raw_properties
                    }
                    self.assertEqual(record["metrics"]["property_keys"], len(property_keys))

    def test_derived_examples_parse_with_expected_semantics(self):
        import numpy

        from ChemBlender.core.cube import parse_cube
        from ChemBlender.core.formats.extxyz import parse_extxyz
        from ChemBlender.core.formats.mol import parse_mol
        from ChemBlender.core.formats.poscar import parse_poscar
        from ChemBlender.core.formats.sdf import parse_sdf
        from ChemBlender.core.formats.smiles import parse_smiles
        from ChemBlender.core.xyz import parse_xyz

        inputs = EXAMPLE_ROOT / "inputs"
        trajectory_path = inputs / "extxyz" / "aspirin-rmd17-32.extxyz"
        trajectory = parse_extxyz(trajectory_path)
        trajectory_data = {item.semantic_role: item for item in trajectory.datasets}
        self.assertEqual(len(trajectory.structures[0].atomic_numbers), 21)
        self.assertEqual(trajectory_data["coordinates"].data.shape, (32, 21, 3))
        self.assertEqual(trajectory_data["atomic_force"].data.shape, (32, 21, 3))
        self.assertEqual(
            trajectory_data["atomic_force"].data.unit,
            "electron_volt_per_angstrom",
        )
        self.assertEqual(trajectory_data["energy"].data.unit, "electron_volt")
        self.assertTrue(numpy.isfinite(trajectory_data["coordinates"].data.values).all())
        comments = trajectory_path.read_text(encoding="ascii").splitlines()[1::23]
        source_indices = [
            int(next(field for field in line.split() if field.startswith("source_index=")).split("=", 1)[1])
            for line in comments
        ]
        self.assertEqual(
            trajectory_data["source_index"].data.values.tolist(),
            source_indices,
        )

        cube = parse_cube(inputs / "cube" / "h2-lcao-1s-density-64.cube")
        grid = cube.datasets[0]
        values = numpy.asarray(grid.data.values)
        self.assertEqual(cube.structures[0].atomic_numbers, (1, 1))
        self.assertEqual(grid.data.shape, (64, 64, 64))
        self.assertTrue(numpy.isfinite(values).all())
        self.assertGreater(float(values.max()), float(values.min()))
        self.assertGreaterEqual(float(values.min()), 0.0)
        self.assertAlmostEqual(float(values.sum()) * (12.0 / 63.0) ** 3, 2.0, places=3)

        base = parse_poscar(inputs / "poscar" / "cod-9012293-diamond.POSCAR")
        supercell = parse_poscar(
            inputs / "poscar" / "cod-9012293-diamond-2x2x2.CONTCAR"
        )
        self.assertEqual(len(base.structures[0].atomic_numbers), 8)
        self.assertEqual(len(supercell.structures[0].atomic_numbers), 64)
        velocity = next(
            item for item in supercell.datasets if item.semantic_role == "atomic_velocity"
        )
        self.assertEqual(velocity.data.shape, (64, 3))
        self.assertTrue((numpy.asarray(velocity.data.values) == 0.0).all())

        aspirin = parse_mol(inputs / "mol" / "ain-aspirin-v2000.mol")
        paclitaxel = parse_mol(inputs / "mol" / "ta1-paclitaxel-v3000.mol")
        showcase = parse_sdf(inputs / "sdf" / "ccd-3d-showcase.sdf")
        smiles = parse_smiles(inputs / "smiles" / "ta1-paclitaxel-isomeric.smi")
        xyz = parse_xyz(inputs / "xyz" / "ta1-paclitaxel-ccd.xyz")
        self.assertEqual([len(item.atomic_numbers) for item in showcase.structures], [21, 24, 113])
        self.assertEqual(aspirin.structures[0].atomic_numbers, showcase.structures[0].atomic_numbers)
        self.assertEqual(paclitaxel.structures[0].atomic_numbers, showcase.structures[2].atomic_numbers)
        self.assertEqual(paclitaxel.structures[0].atomic_numbers, xyz.structures[0].atomic_numbers)
        self.assertEqual(len(smiles.structures), 1)
        self.assertEqual(len(smiles.structures[0].atomic_numbers), 62)
        self.assertEqual([item.code for item in smiles.diagnostics], ["smiles.planar_2d_generated"])

        paclitaxel_topology = paclitaxel.topologies[-1]
        smiles_topology = smiles.topologies[0]
        heavy = {
            index
            for index, atomic_number in enumerate(paclitaxel.structures[0].atomic_numbers)
            if atomic_number != 1
        }
        heavy_bond_indices = [
            index
            for index, (left, right) in enumerate(paclitaxel_topology.bond_indices.values)
            if int(left) in heavy and int(right) in heavy
        ]
        self.assertEqual(len(heavy_bond_indices), 68)
        self.assertEqual(
            sorted(float(paclitaxel_topology.bond_orders.values[index]) for index in heavy_bond_indices),
            sorted(float(value) for value in smiles_topology.bond_orders.values),
        )
        self.assertEqual(
            sum(bool(paclitaxel_topology.aromatic_flags.values[index]) for index in heavy_bond_indices),
            sum(bool(value) for value in smiles_topology.aromatic_flags.values),
        )
        self.assertEqual(
            int(numpy.asarray(paclitaxel.structures[0].atomic_identity.formal_charges.values).sum()),
            int(numpy.asarray(smiles.structures[0].atomic_identity.formal_charges.values).sum()),
        )
        self.assertGreater(
            sum(
                int(value) >= 0
                for value in smiles.structures[0].atomic_identity.stereo_labels.codes.values
            ),
            0,
        )

    def test_preparation_script_pins_only_https_sources(self):
        spec = importlib.util.spec_from_file_location(
            "prepare_representative_inputs",
            PREPARATION_SCRIPT,
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.SOURCES)
        for source in module.SOURCES.values():
            self.assertTrue(source["url"].startswith("https://"), source)
            self.assertTrue(source["license_url"].startswith("https://"), source)
            self.assertTrue(source["source_id"], source)
            self.assertEqual(len(source["sha256"]), 64, source)
            int(source["sha256"], 16)
            self.assertGreater(source["bytes"], 0, source)
        cube = next(
            record
            for record in self.records
            if record["path"] == "inputs/cube/h2-lcao-1s-density-64.cube"
        )
        self.assertEqual(
            hashlib.sha256(module.CUBE_SOURCE_DESCRIPTOR.encode("ascii")).hexdigest(),
            cube["source_sha256"],
        )

    def test_http_range_reader_retries_a_truncated_chunk(self):
        spec = importlib.util.spec_from_file_location(
            "prepare_representative_inputs",
            PREPARATION_SCRIPT,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        payload = b"abcdefghij"
        attempts = {}

        class Response(io.BytesIO):
            status = 206

            def __init__(self, content, content_range):
                super().__init__(content)
                self.headers = {"Content-Range": content_range}

        def fake_urlopen(request, timeout):
            value = request.headers["Range"]
            start, end = (int(part) for part in value.removeprefix("bytes=").split("-"))
            attempts[value] = attempts.get(value, 0) + 1
            content = payload[start : end + 1]
            if value == "bytes=0-3" and attempts[value] == 1:
                content = content[:-1]
            return Response(content, f"bytes {start}-{end}/{len(payload)}")

        with mock.patch.object(module.urllib.request, "urlopen", fake_urlopen):
            reader = module.HTTPRangeReader(
                "https://example.invalid/archive.tar.bz2",
                len(payload),
                chunk_bytes=4,
            )
            self.assertEqual(reader.read(), payload)
        self.assertEqual(attempts["bytes=0-3"], 2)


if __name__ == "__main__":
    unittest.main()
