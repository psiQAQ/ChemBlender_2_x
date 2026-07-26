import hashlib
import json
import unittest
from uuid import uuid4

from ChemBlender.core import (
    ImportBatch,
    ProvenanceRecord,
    QCProject,
    SourceRecord,
    SourceRevision,
    source_parse_identity,
)


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

    def test_project_commits_source_revision_with_created_entities_atomically(self):
        source = self._source()
        entity = self._provenance()
        revision = SourceRevision(
            **(
                self._revision_values()
                | {
                    "source_id": source.id,
                    "created_entity_ids": (entity.id,),
                }
            )
        )
        project = QCProject(uuid4(), "0.2")

        project.commit(
            ImportBatch(
                sources=[source],
                source_revisions=[revision],
                provenance=(entity,),
            )
        )

        self.assertEqual(project.sources, {source.id: source})
        self.assertEqual(project.source_revisions, {revision.id: revision})
        self.assertEqual(project.provenance, {entity.id: entity})

    def test_project_rejects_dangling_source_entity_and_diagnostic_without_mutation(self):
        source = self._source()
        invalid_revisions = {
            "source": SourceRevision(**self._revision_values()),
            "entity": SourceRevision(
                **(
                    self._revision_values()
                    | {
                        "source_id": source.id,
                        "created_entity_ids": (uuid4(),),
                    }
                )
            ),
            "diagnostic": SourceRevision(
                **(
                    self._revision_values()
                    | {
                        "source_id": source.id,
                        "diagnostic_ids": (uuid4(),),
                    }
                )
            ),
        }

        for name, revision in invalid_revisions.items():
            with self.subTest(name=name):
                project = QCProject(uuid4(), "0.2")
                with self.assertRaises(ValueError):
                    project.commit(
                        ImportBatch(
                            sources=(source,),
                            source_revisions=(revision,),
                        )
                    )
                self.assertEqual(project.sources, {})
                self.assertEqual(project.source_revisions, {})

    def test_existing_source_registries_enforce_the_same_relationships(self):
        source = self._source()
        entity = self._provenance()
        valid = SourceRevision(
            **(
                self._revision_values()
                | {
                    "source_id": source.id,
                    "created_entity_ids": (entity.id,),
                }
            )
        )
        project = QCProject(
            uuid4(),
            "0.2",
            sources={source.id: source},
            source_revisions={valid.id: valid},
            provenance={entity.id: entity},
        )
        self.assertEqual(project.source_revisions[valid.id], valid)

        invalid_values = (
            {"source_id": uuid4()},
            {"source_id": source.id, "created_entity_ids": (uuid4(),)},
            {"source_id": source.id, "diagnostic_ids": (uuid4(),)},
        )
        for values in invalid_values:
            with self.subTest(values=values):
                invalid = SourceRevision(**(self._revision_values() | values))
                with self.assertRaises(ValueError):
                    QCProject(
                        uuid4(),
                        "0.2",
                        sources={source.id: source},
                        source_revisions={invalid.id: invalid},
                        provenance={entity.id: entity},
                    )

    def test_source_ids_share_the_project_wide_uuid_namespace(self):
        shared_id = uuid4()
        source = self._source(id=shared_id)
        entity = self._provenance(id=shared_id)
        with self.assertRaises(ValueError):
            QCProject(
                uuid4(),
                "0.2",
                sources={shared_id: source},
                provenance={shared_id: entity},
            )
        with self.assertRaises(ValueError):
            QCProject(uuid4(), "0.2").commit(
                ImportBatch(sources=(source,), provenance=(entity,))
            )

    @staticmethod
    def _source(**changes):
        values = {
            "id": uuid4(),
            "display_name": "file.xyz",
            "source_kind": "local_file",
            "created_at_utc": "2026-07-24T00:00:00Z",
        }
        return SourceRecord(**(values | changes))

    @staticmethod
    def _provenance(**changes):
        values = {
            "id": uuid4(),
            "revision": "r1",
            "producer": "test",
            "producer_version": "1",
            "source": "file.xyz",
            "source_hash": "a" * 64,
            "parent_ids": (),
            "operation": "parse",
            "parameters": (),
        }
        return ProvenanceRecord(**(values | changes))

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
