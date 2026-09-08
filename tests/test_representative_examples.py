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

        from ChemBlender.core.reader_catalog import builtin_reader_registry

        inputs = EXAMPLE_ROOT / "inputs"
        registry = builtin_reader_registry()

        def parse(path, reader_id):
            return registry.parse(path, reader_id=reader_id)

        trajectory_path = inputs / "extxyz" / "aspirin-rmd17-32.extxyz"
        trajectory = parse(trajectory_path, "extxyz")
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

        cube = parse(inputs / "cube" / "h2-lcao-1s-density-64.cube", "cube")
        grid = cube.datasets[0]
        values = numpy.asarray(grid.data.values)
        self.assertEqual(cube.structures[0].atomic_numbers, (1, 1))
        self.assertEqual(grid.data.shape, (64, 64, 64))
        self.assertTrue(numpy.isfinite(values).all())
        self.assertGreater(float(values.max()), float(values.min()))
        self.assertGreaterEqual(float(values.min()), 0.0)
        self.assertAlmostEqual(float(values.sum()) * (12.0 / 63.0) ** 3, 2.0, places=3)

        base = parse(
            inputs / "poscar" / "cod-9012293-diamond.POSCAR",
            "poscar",
        )
        supercell = parse(
            inputs / "poscar" / "cod-9012293-diamond-2x2x2.CONTCAR",
            "poscar",
        )
        self.assertEqual(len(base.structures[0].atomic_numbers), 8)
        self.assertEqual(len(supercell.structures[0].atomic_numbers), 64)
        velocity = next(
            item for item in supercell.datasets if item.semantic_role == "atomic_velocity"
        )
        self.assertEqual(velocity.data.shape, (64, 3))
        self.assertTrue((numpy.asarray(velocity.data.values) == 0.0).all())

        aspirin = parse(inputs / "mol" / "ain-aspirin-v2000.mol", "mol")
        paclitaxel = parse(inputs / "mol" / "ta1-paclitaxel-v3000.mol", "mol")
        showcase = parse(inputs / "sdf" / "ccd-3d-showcase.sdf", "sdf")
        smiles = parse(
            inputs / "smiles" / "ta1-paclitaxel-isomeric.smi",
            "smiles",
        )
        xyz = parse(inputs / "xyz" / "ta1-paclitaxel-ccd.xyz", "xyz")
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

    def test_direct_examples_parse_with_expected_semantics(self):
        import numpy

        from ChemBlender.core.formats.mol2 import (
            iter_mol2_records,
            parse_mol2_record,
        )
        from ChemBlender.core.reader_catalog import builtin_reader_registry

        inputs = EXAMPLE_ROOT / "inputs"
        registry = builtin_reader_registry()

        def parse(relative_path, reader_id):
            return registry.parse(inputs / relative_path, reader_id=reader_id)

        cif_path = inputs / "cif" / "cod-4503272-caffeine-cocrystal.cif"
        cif = parse("cif/cod-4503272-caffeine-cocrystal.cif", "cif")
        crystal = cif.structures[0]
        periodic = crystal.periodic
        self.assertEqual(len(crystal.atomic_numbers), 64)
        self.assertEqual(crystal.cell.shape, (3, 3))
        self.assertEqual(periodic.declared_space_group_number, 64)
        self.assertEqual(len(periodic.symmetry_operations), 16)
        self.assertEqual(
            int(numpy.count_nonzero(numpy.asarray(periodic.occupancies.values) < 1.0)),
            23,
        )
        self.assertEqual(sum(value > 0 for value in periodic.disorder_groups), 9)
        self.assertEqual(cif.cif_envelopes[0].source_bytes, cif_path.read_bytes())

        cjson_path = inputs / "cjson" / "avogadro-phthalocyanine.cjson"
        cjson = parse("cjson/avogadro-phthalocyanine.cjson", "cjson")
        self.assertEqual(len(cjson.structures[0].atomic_numbers), 57)
        self.assertEqual(cjson.topologies[0].bond_indices.shape, (68, 2))
        self.assertEqual(
            [(item.semantic_role, item.data.shape) for item in cjson.datasets],
            [("formal_charge", (57,))],
        )
        self.assertEqual(cjson.cjson_envelopes[0].format_version, 1)
        self.assertEqual(cjson.cjson_envelopes[0].source_bytes, cjson_path.read_bytes())

        mol2 = parse("mol2/openbabel-5sun-protein.mol2", "mol2")
        preserved = parse_mol2_record(
            next(iter_mol2_records(mol2.molecular_records[0].raw_block))
        )
        self.assertEqual(len(mol2.structures[0].atomic_numbers), 6185)
        self.assertEqual(mol2.topologies, ())
        self.assertEqual(
            (
                preserved.counts.atom_count,
                preserved.counts.bond_count,
                preserved.counts.substructure_count,
            ),
            (6185, 6248, 390),
        )
        self.assertEqual(len(preserved.bonds), 6248)
        self.assertEqual(len(preserved.substructures), 390)
        self.assertEqual(
            [bond.bond_type for bond in preserved.bonds if bond.unknown],
            ["un"],
        )
        self.assertEqual(len(preserved.unknown_sections), 4)

        pdb = parse("pdb/1d3z-ubiquitin-nmr.pdb", "pdb")
        pdb_data = {item.semantic_role: item for item in pdb.datasets}
        pdb_hierarchy = pdb.biological_hierarchies[0]
        self.assertEqual(len(pdb.structures[0].atomic_numbers), 1231)
        self.assertEqual(pdb_data["coordinates"].data.shape, (10, 1231, 3))
        self.assertEqual(pdb_data["occupancy"].data.shape, (1231,))
        self.assertEqual(pdb_data["b_factor"].data.shape, (1231,))
        self.assertEqual(
            [(chain.chain_id, chain.segment_index) for chain in pdb_hierarchy.chains],
            [("A", 0)],
        )
        self.assertEqual(len(pdb_hierarchy.residues), 76)

        pqr = parse("pqr/apbs-protein-rna-nb.pqr", "pqr")
        pqr_data = {item.semantic_role: item for item in pqr.datasets}
        pqr_hierarchy = pqr.biological_hierarchies[0]
        self.assertEqual(len(pqr.structures[0].atomic_numbers), 998)
        self.assertEqual(pqr_data["partial_charge"].data.shape, (998,))
        self.assertEqual(pqr_data["radius"].data.shape, (998,))
        self.assertTrue(
            numpy.isfinite(numpy.asarray(pqr_data["partial_charge"].data.values)).all()
        )
        self.assertTrue(
            numpy.isfinite(numpy.asarray(pqr_data["radius"].data.values)).all()
        )
        self.assertEqual(
            int(numpy.count_nonzero(numpy.asarray(pqr_data["radius"].data.values) == 0.0)),
            22,
        )
        self.assertEqual(
            [(chain.chain_id, chain.segment_index) for chain in pqr_hierarchy.chains],
            [("", 0), ("", 1)],
        )
        self.assertEqual(len(pqr_hierarchy.residues), 41)
        self.assertEqual(len(pqr.diagnostics), 1)
        self.assertEqual(pqr.diagnostics[0].field_path, "record[*].element")

        qcschema_path = inputs / "qcschema" / "molssi-water-gradient-hf.json"
        qcschema = parse("qcschema/molssi-water-gradient-hf.json", "qcschema")
        qcschema_data = {item.semantic_role: item for item in qcschema.datasets}
        envelope = qcschema.qcschema_envelopes[0]
        calculation = qcschema.calculations[0]
        self.assertEqual(len(qcschema.structures[0].atomic_numbers), 3)
        self.assertEqual(qcschema.report.reader_id, "qcschema_atomic_result_v1")
        self.assertEqual(len(qcschema.datasets), 13)
        self.assertEqual(qcschema_data["gradient"].data.shape, (3, 3))
        self.assertEqual(qcschema_data["gradient"].data.unit, "hartree_per_bohr")
        self.assertEqual(qcschema_data["gradient"].structure_id, calculation.result_structure_ids[0])
        self.assertEqual((envelope.schema_name, envelope.schema_version), ("qc_schema_output", 1))
        self.assertEqual(
            json.loads(envelope.source_bytes),
            json.loads(qcschema_path.read_bytes()),
        )
        self.assertEqual(calculation.metadata.driver, "gradient")

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
