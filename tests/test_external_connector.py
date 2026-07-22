import json
import unittest

from ChemBlender.core import (
    ExternalConnectorError,
    ExternalRecordRequest,
    builtin_external_connectors,
    external_record_request_document,
    external_record_request_from_document,
    external_record_source_uri,
)


class ExternalConnectorTests(unittest.TestCase):
    def test_builtin_descriptors_are_versioned_and_provider_specific(self):
        connectors = builtin_external_connectors()
        self.assertEqual(set(connectors), {"aiida", "nomad", "qcarchive"})
        self.assertEqual(connectors["qcarchive"].locator_fields, ("server_url", "record_id"))
        self.assertEqual(connectors["aiida"].locator_fields, ("profile", "node_uuid"))
        self.assertEqual(connectors["nomad"].locator_fields, ("base_url", "entry_id"))
        self.assertTrue(all(item.version == "1" for item in connectors.values()))

    def test_request_codec_is_strict_and_never_contains_credentials(self):
        request = ExternalRecordRequest(
            provider="qcarchive",
            connector_version="1",
            locator=(
                ("server_url", "https://archive.example.org"),
                ("record_id", "1234"),
            ),
            envelope_type="qcschema",
            authentication_ref="env:CHEMBLENDER_QCARCHIVE_TOKEN",
        )
        document = external_record_request_document(request)
        self.assertEqual(external_record_request_from_document(document), request)
        serialized = json.dumps(document)
        self.assertNotIn("secret-value", serialized)
        self.assertEqual(external_record_source_uri(request), "qcarchive://record/1234")

        document["unexpected"] = True
        with self.assertRaises(ExternalConnectorError):
            external_record_request_from_document(document)
        with self.assertRaisesRegex(ExternalConnectorError, "credentials"):
            ExternalRecordRequest(
                provider="qcarchive",
                connector_version="1",
                locator=(("server_url", "https://user:secret@example.org"), ("record_id", "1")),
                envelope_type="qcschema",
                authentication_ref=None,
            )

    def test_version_locator_and_auth_reference_fail_closed(self):
        invalid = (
            dict(provider="qcarchive", connector_version="2", locator=(("server_url", "https://example.org"), ("record_id", "1")), envelope_type="qcschema", authentication_ref=None),
            dict(provider="nomad", connector_version="1", locator=(("entry_id", "x"),), envelope_type="qcschema", authentication_ref=None),
            dict(provider="aiida", connector_version="1", locator=(("profile", "default"), ("node_uuid", "x")), envelope_type="qcschema", authentication_ref="plain-secret"),
        )
        for fields in invalid:
            with self.subTest(fields=fields):
                with self.assertRaises(ExternalConnectorError):
                    ExternalRecordRequest(**fields)


if __name__ == "__main__":
    unittest.main()
