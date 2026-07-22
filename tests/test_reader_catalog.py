import json
import unittest
from pathlib import Path

from ChemBlender.core import (
    CapabilitySupport,
    builtin_reader_descriptors,
    builtin_reader_registry,
    reader_capability_document,
)


MATRIX = Path(__file__).parents[1] / "docs" / "quantum-visualization" / "reader-capability-matrix.json"


class ReaderCatalogTests(unittest.TestCase):
    def test_builtin_catalog_has_unique_descriptors_and_fresh_matrix(self):
        readers = builtin_reader_descriptors()
        self.assertEqual(len(readers), 11)
        self.assertEqual(len({reader.reader_id for reader in readers}), len(readers))
        registry = builtin_reader_registry()
        for reader in readers:
            self.assertIs(registry.select("unused", reader_id=reader.reader_id), reader)
            self.assertTrue(
                all(isinstance(value, CapabilitySupport) for value in reader.capabilities.values())
            )
        expected = reader_capability_document(readers)
        self.assertEqual(json.loads(MATRIX.read_text(encoding="utf-8")), expected)

    def test_matrix_is_deterministic_and_json_serializable(self):
        first = reader_capability_document()
        second = reader_capability_document(reversed(builtin_reader_descriptors()))
        self.assertEqual(first, second)
        encoded = json.dumps(first, sort_keys=True, separators=(",", ":"), allow_nan=False)
        self.assertNotIn("callable", encoded.lower())

    def test_builtin_registry_routes_xyz_and_extxyz_without_ambiguity(self):
        registry = builtin_reader_registry()
        fixtures = Path(__file__).parent / "fixtures" / "xyz"
        self.assertEqual(registry.select(fixtures / "water.xyz").reader_id, "xyz")
        self.assertEqual(
            registry.select(fixtures / "periodic-extra.extxyz").reader_id,
            "ase-structure",
        )


if __name__ == "__main__":
    unittest.main()
