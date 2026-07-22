import math
import unittest
from uuid import UUID

from ChemBlender.core.cache_identity import (
    CacheIdentityError,
    derivation_cache_key,
    parser_cache_key,
    render_cache_key,
    source_hash_bytes,
)


class CacheIdentityTests(unittest.TestCase):
    def test_source_and_parser_keys_are_deterministic(self):
        source_hash = source_hash_bytes(b"same source")
        first = parser_cache_key(
            source_hash,
            "cclib-output",
            "1.8.1",
            {"program": "orca", "indices": [2, 1]},
        )
        second = parser_cache_key(
            source_hash,
            "cclib-output",
            "1.8.1",
            {"indices": [2, 1], "program": "orca"},
        )
        self.assertEqual(first, second)
        self.assertNotEqual(
            first,
            parser_cache_key(
                source_hash,
                "cclib-output",
                "1.8.2",
                {"indices": [2, 1], "program": "orca"},
            ),
        )

    def test_derivation_and_render_layers_invalidate_independently(self):
        entity_id = UUID("10000000-0000-0000-0000-000000000001")
        derivation = derivation_cache_key(
            ((entity_id, "revision-1"),),
            "molecular_orbital_grid",
            "1",
            {"shape": (40, 40, 40), "orbital": 5},
        )
        changed_input = derivation_cache_key(
            ((entity_id, "revision-2"),),
            "molecular_orbital_grid",
            "1",
            {"shape": (40, 40, 40), "orbital": 5},
        )
        self.assertNotEqual(derivation, changed_input)

        first = render_cache_key(
            entity_id,
            "revision-1",
            derivation,
            "grid-volume",
            "1",
            {"isovalue": 0.05},
        )
        second = render_cache_key(
            entity_id,
            "revision-1",
            derivation,
            "grid-volume",
            "2",
            {"isovalue": 0.05},
        )
        self.assertNotEqual(first, second)

    def test_rejects_non_canonical_values(self):
        with self.assertRaises(CacheIdentityError):
            parser_cache_key("a" * 64, "reader", "1", {"bad": math.nan})
        with self.assertRaises(CacheIdentityError):
            parser_cache_key("not-a-hash", "reader", "1", {})
        with self.assertRaises(TypeError):
            source_hash_bytes("text")


if __name__ == "__main__":
    unittest.main()
