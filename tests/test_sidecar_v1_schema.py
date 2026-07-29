import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy

from ChemBlender.core import (
    SidecarIntegrityError,
    close_project,
    open_project,
    save_project,
)
from ChemBlender.core.sidecar import _manifest_hash
from ChemBlender.core.sidecar_migrations import (
    CURRENT_MANIFEST_VERSION,
    CURRENT_PROJECT_SCHEMA_VERSION,
)
from tests.test_sidecar_storage import (
    DATASET_ID,
    FIXTURES,
    FRAMES_ID,
    GRID_ID,
    STRUCTURE_ID,
    sample_project,
    write_manifest,
)

LEGACY_SIDECAR = FIXTURES / "sidecar" / "model-v01"
HASHED_LEGACY_SIDECAR = FIXTURES / "sidecar" / "model-v02"
CURRENT_SIDECAR = FIXTURES / "sidecar" / "model-v10"


def _sample_v02_project():
    project = sample_project()
    project.schema_version = "0.2"
    return project


def _downgrade_to_v02(root, *, remove_registries=()):
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_version"] = "0.2"
    manifest["project_schema_version"] = "0.2"
    manifest["project"]["schema_version"] = "0.2"
    for name in remove_registries:
        del manifest["project"][name]
    write_manifest(manifest_path, manifest)


class SidecarV1SchemaTests(unittest.TestCase):
    def assert_sample_arrays(self, project):
        numpy.testing.assert_allclose(
            numpy.asarray(project.structures[STRUCTURE_ID].coordinates.values),
            ((0.0, 0.0, 0.0), (0.0, 0.0, 0.74)),
        )
        numpy.testing.assert_allclose(
            numpy.asarray(project.datasets[DATASET_ID].data.values),
            (0.1, -0.1),
        )
        numpy.testing.assert_allclose(
            numpy.asarray(project.datasets[FRAMES_ID].data.values),
            (
                ((0.0, 0.0, 0.0), (0.0, 0.0, 0.74)),
                ((1.0, 1.0, 1.0), (1.0, 1.0, 1.74)),
            ),
        )
        numpy.testing.assert_array_equal(
            numpy.asarray(project.datasets[GRID_ID].data.values),
            numpy.arange(8, dtype=numpy.float64).reshape((2, 2, 2)),
        )

    def test_current_schema_is_v1_and_save_never_mutates_legacy_caller(self):
        self.assertEqual(CURRENT_MANIFEST_VERSION, "1.0")
        self.assertEqual(CURRENT_PROJECT_SCHEMA_VERSION, "1.0")
        project = _sample_v02_project()
        self.assertEqual(project.schema_version, "0.2")
        with TemporaryDirectory() as temporary:
            root = save_project(Path(temporary) / "current.cbq", project)
            manifest = json.loads(
                (root / "manifest.json").read_text(encoding="utf-8")
            )
        self.assertEqual(project.schema_version, "0.2")
        self.assertEqual(manifest["manifest_version"], "1.0")
        self.assertEqual(manifest["project_schema_version"], "1.0")
        self.assertEqual(manifest["project"]["schema_version"], "1.0")

    def test_v01_fixture_opens_as_v1_with_lazy_arrays(self):
        project = open_project(LEGACY_SIDECAR)
        try:
            self.assertEqual(project.schema_version, "1.0")
            self.assertTrue(project.structures)
            self.assertTrue(project.datasets)
            values = next(iter(project.datasets.values())).data.values
            self.assertFalse(values.loaded)
            self.assert_sample_arrays(project)
        finally:
            close_project(project)

    def test_v02_fixture_migrates_entities_and_preserves_arrays(self):
        manifest = json.loads(
            (HASHED_LEGACY_SIDECAR / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["manifest_version"], "0.2")
        self.assertEqual(manifest["project_schema_version"], "0.2")
        project = open_project(
            HASHED_LEGACY_SIDECAR,
            expected_schema_version="0.2",
        )
        try:
            self.assertEqual(project.schema_version, "1.0")
            self.assertTrue(project.structures)
            self.assertTrue(project.datasets)
            self.assertEqual(project.diagnostics, {})
            self.assertEqual(project.calculation_groups, {})
            self.assertEqual(len(project.topologies), 1)
            self.assertEqual(project.molecular_records, {})
            structure = next(iter(project.structures.values()))
            self.assertIsNone(structure.topology)
            self.assertEqual(
                structure.topology_ids,
                tuple(project.topologies),
            )
            self.assert_sample_arrays(project)
        finally:
            close_project(project)

    def test_v1_fixture_opens_without_migration_and_preserves_arrays(self):
        manifest = json.loads(
            (CURRENT_SIDECAR / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["manifest_version"], "1.0")
        self.assertEqual(manifest["project_schema_version"], "1.0")
        project = open_project(CURRENT_SIDECAR)
        try:
            self.assertEqual(project.schema_version, "1.0")
            self.assert_sample_arrays(project)
        finally:
            close_project(project)

    def test_migrated_project_resaves_only_as_v1(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            legacy = save_project(
                directory / "legacy-v02.cbq",
                _sample_v02_project(),
            )
            _downgrade_to_v02(legacy)
            project = open_project(legacy)
            try:
                current = save_project(directory / "current.cbq", project)
            finally:
                close_project(project)
            manifest = json.loads(
                (current / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["manifest_version"], "1.0")
            self.assertEqual(manifest["project_schema_version"], "1.0")
            self.assertEqual(
                manifest["manifest_sha256"],
                _manifest_hash(manifest),
            )

    def test_v02_hash_is_verified_before_migration(self):
        with TemporaryDirectory() as temporary:
            root = save_project(
                Path(temporary) / "legacy-v02.cbq",
                _sample_v02_project(),
            )
            _downgrade_to_v02(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["project"]["schema_version"] = "tampered"
            write_manifest(manifest_path, manifest, update_hash=False)
            with self.assertRaisesRegex(
                SidecarIntegrityError,
                "manifest hash mismatch",
            ):
                open_project(root)

    def test_sidecar_v1_spec_records_authority_migration_and_freeze(self):
        document = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "quantum-visualization"
            / "2.3.0"
            / "specs"
            / "cbq-sidecar-v1.md"
        ).read_text(encoding="utf-8")
        self.assertIn('manifest_version` 与 `project_schema_version` 均为 `"1.0"`', document)
        self.assertIn("cache/render/", document)
        self.assertIn("v0.1/v0.2", document)
        self.assertIn("release-blocking ADR", document)


if __name__ == "__main__":
    unittest.main()
