import hashlib
import json
import unittest
from uuid import uuid4

from ChemBlender.core import SourceRecord, SourceRevision, source_parse_identity


class SourceModelTests(unittest.TestCase):
    def test_parse_identity_uses_canonical_inputs_only(self):
        content_hash = "a" * 64
        parameters = (("mode", "balanced"), ("strict", True))
        expected = hashlib.sha256(
            json.dumps(
                {
                    "content_hash": content_hash,
                    "parameters": parameters,
                    "plugin_id": "builtin",
                    "reader_id": "xyz",
                    "reader_version": "2",
                },
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        first = source_parse_identity(
            content_hash, "builtin", "xyz", "2", parameters
        )
        second = source_parse_identity(
            content_hash, "builtin", "xyz", "2", tuple(reversed(parameters))
        )

        self.assertEqual(first, expected)
        self.assertEqual(second, expected)

    def test_source_record_requires_uuid_token_and_text(self):
        with self.assertRaises(TypeError):
            SourceRecord("not-a-uuid", "example", "local_file", "2026-07-24T00:00:00Z")
        with self.assertRaises(ValueError):
            SourceRecord(uuid4(), "example", "Local File", "2026-07-24T00:00:00Z")
        with self.assertRaises(ValueError):
            SourceRecord(uuid4(), "", "local_file", "2026-07-24T00:00:00Z")

    def test_source_revision_requires_sha256_and_nonnegative_size(self):
        values = self._revision_values()
        for name, value in (
            ("content_hash", "bad"),
            ("import_parameters_hash", "BAD" * 22),
            ("parse_identity", "c" * 63),
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    SourceRevision(**(values | {name: value}))
        for value in (-1, True):
            with self.subTest(byte_size=value):
                with self.assertRaises(ValueError):
                    SourceRevision(**(values | {"byte_size": value}))

    def test_source_revision_normalizes_uuid_tuples_and_validates_locator_kind(self):
        values = self._revision_values()
        created_id, diagnostic_id = uuid4(), uuid4()
        revision = SourceRevision(
            **(
                values
                | {
                    "created_entity_ids": [created_id],
                    "diagnostic_ids": [diagnostic_id],
                }
            )
        )

        self.assertEqual(revision.created_entity_ids, (created_id,))
        self.assertEqual(revision.diagnostic_ids, (diagnostic_id,))
        with self.assertRaises(ValueError):
            SourceRevision(**(values | {"locator_kind": "Local File"}))
        with self.assertRaises(TypeError):
            SourceRevision(**(values | {"created_entity_ids": ("not-a-uuid",)}))

    @staticmethod
    def _revision_values():
        return {
            "id": uuid4(),
            "source_id": uuid4(),
            "content_hash": "a" * 64,
            "byte_size": 0,
            "locator": "file.xyz",
            "locator_kind": "path",
            "original_filename": "file.xyz",
            "reader_plugin_id": "chemblender.builtin",
            "reader_id": "xyz",
            "reader_version": "2",
            "reader_api_version": "0.1",
            "import_parameters_hash": "b" * 64,
            "parse_identity": "c" * 64,
            "created_entity_ids": (),
            "diagnostic_ids": (),
        }


if __name__ == "__main__":
    unittest.main()
