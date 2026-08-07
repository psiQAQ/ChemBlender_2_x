import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = ROOT / "examples" / "user-workflows"
MANIFEST = EXAMPLE_ROOT / "manifest.json"
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


if __name__ == "__main__":
    unittest.main()
