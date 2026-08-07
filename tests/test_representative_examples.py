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
