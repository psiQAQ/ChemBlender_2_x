import hashlib
import json
import subprocess
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import get_args, get_origin
import unittest

import ChemBlender.reader_api as reader_api
from ChemBlender.core.readers import READER_API_VERSION as CORE_READER_API_VERSION
from ChemBlender.reader_api import canonical_document
from ChemBlender.reader_api import public_model
from ChemBlender.reader_api.manifest import ReaderManifestEntry, ReaderPluginManifest
from ChemBlender.reader_api.registry import builtin_reader_plugins


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "reader-api"
    / "public-schema-v1-rc1.json"
)
FIXTURE_HASH = FIXTURE.with_suffix(".json.sha256")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _type_document(value):
    origin = get_origin(value)
    if origin is not None:
        return [
            _type_document(origin),
            *(_type_document(item) for item in get_args(value)),
        ]
    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"
    return repr(value)


def _default_document(item):
    if item.default is not MISSING:
        return ["value", repr(item.default)]
    if item.default_factory is not MISSING:
        factory = item.default_factory
        return [
            "factory",
            f"{factory.__module__}.{factory.__qualname__}",
        ]
    return ["required"]


def _field_document(model_type):
    return [
        [
            item.name,
            _type_document(item.type),
            _default_document(item),
        ]
        for item in fields(model_type)
        if item.init
    ]


def _snapshot_hash(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _schema_document():
    public_types = {
        name: getattr(reader_api, name)
        for name in reader_api.__all__
        if isinstance(getattr(reader_api, name), type)
    }
    dataclass_types = {
        name: value
        for name, value in public_types.items()
        if is_dataclass(value)
    }
    enum_types = {
        name: value
        for name, value in public_types.items()
        if issubclass(value, Enum)
    }
    return {
        "reader_api_version": reader_api.READER_API_VERSION,
        "public_exports": list(reader_api.__all__),
        "dataclass_types": {
            name: _snapshot_hash(_field_document(model_type))
            for name, model_type in dataclass_types.items()
        },
        "enum_types": {
            name: _snapshot_hash([member.value for member in enum_type])
            for name, enum_type in enum_types.items()
        },
    }


class ReaderApiV1RcTests(unittest.TestCase):
    def test_public_schema_fixture_disables_checkout_line_ending_conversion(
        self,
    ):
        relative = FIXTURE.relative_to(REPOSITORY_ROOT).as_posix()
        result = subprocess.run(
            ["git", "check-attr", "text", "--", relative],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip(), f"{relative}: text: unset")

    def test_version_and_builtin_manifest_use_v1_compatibility_family(self):
        self.assertEqual(reader_api.READER_API_VERSION, "1.0-rc1")
        self.assertEqual(reader_api.READER_API_VERSION, CORE_READER_API_VERSION)
        manifests = {plugin.manifest for plugin in builtin_reader_plugins()}
        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests.pop().chemblender_api, ">=1.0,<2.0")

    def test_v1_range_accepts_rc_and_v0_experiment_range_has_clear_error(self):
        entry = ReaderManifestEntry(
            "example",
            "1",
            (".example",),
            ("structure",),
        )
        manifest = ReaderPluginManifest(
            "1",
            "org.example.reader",
            "1.0.0",
            ">=1.0,<2.0",
            "extension",
            ("SPDX:MIT",),
            (entry,),
        )
        self.assertEqual(manifest.chemblender_api, ">=1.0,<2.0")
        with self.assertRaisesRegex(
            ValueError,
            r"Reader API 0\.x plugin.*incompatible.*1\.0-rc1",
        ):
            ReaderPluginManifest(
                "1",
                "org.example.reader",
                "1.0.0",
                ">=0.1,<1.0",
                "extension",
                ("SPDX:MIT",),
                (entry,),
            )

    def test_public_schema_snapshot_and_hash_are_exhaustive(self):
        self.assertEqual(
            set(canonical_document._MODEL_TYPES.values()),
            set(public_model._PUBLIC_MODEL_TYPES)
            | {reader_api.PublicImportBatch},
        )
        public_dataclasses = {
            getattr(reader_api, name)
            for name in reader_api.__all__
            if isinstance(getattr(reader_api, name), type)
            and is_dataclass(getattr(reader_api, name))
        }
        self.assertTrue(
            {ReaderManifestEntry, ReaderPluginManifest}
            <= public_dataclasses
        )
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(snapshot, _schema_document())
        self.assertEqual(
            hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            FIXTURE_HASH.read_text(encoding="ascii").split()[0],
        )
        for model_type in canonical_document._MODEL_TYPES.values():
            self.assertTrue(is_dataclass(model_type))
        for enum_type in canonical_document._MODEL_ENUMS.values():
            self.assertTrue(issubclass(enum_type, Enum))

    def test_reader_api_rc_spec_records_freeze_and_document_version_boundary(self):
        document = (
            REPOSITORY_ROOT
            / "docs"
            / "quantum-visualization"
            / "2.3.0"
            / "reader-api-v1-rc.md"
        ).read_text(encoding="utf-8")
        self.assertIn("1.0-rc1", document)
        self.assertIn(">=1.0,<2.0", document)
        self.assertIn("reader-import` / `0.1", document)
        self.assertIn("release-blocking ADR", document)


if __name__ == "__main__":
    unittest.main()
