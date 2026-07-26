import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import types
import unittest
from unittest.mock import patch

import ChemBlender.core.sidecar as sidecar
import ChemBlender.reader_api as reader_api
import ChemBlender.reader_api.canonical_document as canonical_document
from tests.test_reader_canonical_document import sample_batch
from tests.test_sidecar_storage import FIXTURES, GRID_ID, sample_project


_FIXTURE_HASHES = {
    "manifest.json": "a13f941fdd7124817e7af4256e7e28932441d4eba3d6d5cc109032b5945e7294",
    "arrays/32797cc6cc28d503b4b14f327da8f10aaea77c2f2375fdc32b7765fa653c66ed.npy":
        "2dade9ec528e018739f9cf2a48c85c0a65c15b84238232b33fd960e681f3660c",
    "arrays/50c2bb7ae9a3c89484fc3e03d15fff868a68d58002d1b7d4b78ff60c6c75c89f.npy":
        "6580aca8ead9a1ceb11fb1e772794918b927f686e09f8b5fdc115dcec97d50c8",
    "arrays/711072e3d962eef1cd6696efed6f03bb20ff165395d25c11b62b4ee9f87b6dfb.npy":
        "784b27f170cb8a88a34ece33c5b5cf1acd903430e4e49aefb5ac570964d4bf8e",
    "arrays/81f623b7e19fc2c2616c78b2f8aed72c26a594938d4db40036a4b8a003865e16.npy":
        "edb498bf8a1b7a15fa5a7ea1ed0646816bb9cb7477566bf6431f56938b961e4b",
    "arrays/c2bfa2da17439cd2389776bfafb32c015446164a335988de6cbbbec758f56fc2.npy":
        "23dd9625d24644656662ca7303243396e67b51e057569add945ffb4505059573",
    "arrays/eaa8b4c7dc192a4b22568349dec3af0b17c329e72d7eca0d5631466e09fd8970.npy":
        "f190a1e96267d0fb052410267622ccc11ffc9bfbf670df9bb59f20b50182ef6b",
}
_CANONICAL_DOCUMENT_SHA256 = (
    "cde1a31f0402c76e9d8cf40f634d9722bb7f4df4bc179a1bef0b6835b3fcd270"
)
_CANONICAL_ARTIFACT_HASHES = {
    "32797cc6cc28d503b4b14f327da8f10aaea77c2f2375fdc32b7765fa653c66ed.npy":
        "2dade9ec528e018739f9cf2a48c85c0a65c15b84238232b33fd960e681f3660c",
    "3af9ea8287712a9213296390e74cc29bfc19301ad39f4fc32b41ae3868860fe6.npy":
        "4a20348f13da823738aa5c8db15627fe65ac3945b4972d9c6034d8c6607a2787",
    "50c2bb7ae9a3c89484fc3e03d15fff868a68d58002d1b7d4b78ff60c6c75c89f.npy":
        "6580aca8ead9a1ceb11fb1e772794918b927f686e09f8b5fdc115dcec97d50c8",
    "711072e3d962eef1cd6696efed6f03bb20ff165395d25c11b62b4ee9f87b6dfb.npy":
        "784b27f170cb8a88a34ece33c5b5cf1acd903430e4e49aefb5ac570964d4bf8e",
    "c2bfa2da17439cd2389776bfafb32c015446164a335988de6cbbbec758f56fc2.npy":
        "23dd9625d24644656662ca7303243396e67b51e057569add945ffb4505059573",
    "eaa8b4c7dc192a4b22568349dec3af0b17c329e72d7eca0d5631466e09fd8970.npy":
        "f190a1e96267d0fb052410267622ccc11ffc9bfbf670df9bb59f20b50182ef6b",
}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fake_blender_modules(write_vdb):
    fake_bpy = types.ModuleType("bpy")

    def stop_after_replace(_name):
        raise RuntimeError("stop after VDB replace")

    fake_bpy.data = types.SimpleNamespace(
        volumes=types.SimpleNamespace(new=stop_after_replace)
    )
    fake_openvdb = types.ModuleType("openvdb")

    class FloatGrid:
        def __init__(self):
            self.name = ""
            self.transform = None

        def copyFromArray(self, _values):
            pass

    fake_openvdb.FloatGrid = FloatGrid
    fake_openvdb.createLinearTransform = lambda matrix: matrix
    fake_openvdb.write = write_vdb
    return fake_bpy, fake_openvdb


class AtomicPathBudgetTests(unittest.TestCase):
    def assert_short_replace_source(self, source, destination):
        source = Path(source)
        destination = Path(destination)
        self.assertEqual(source.parent, destination.parent)
        self.assertLessEqual(len(source.name), 48)
        if len(destination.stem) == 64:
            self.assertNotIn(destination.stem, source.name)

    def test_short_sibling_path_contract_for_hash_destinations(self):
        spec = importlib.util.find_spec(
            "ChemBlender.core.storage.atomic_paths"
        )
        self.assertIsNotNone(spec, "atomic path helper module is missing")
        module = importlib.import_module(
            "ChemBlender.core.storage.atomic_paths"
        )
        helper = module.short_sibling_temporary_path
        long_parent = Path("parent-" + "x" * 180)
        destinations = (
            long_parent / f"{'a' * 64}.npy",
            long_parent / f"{'b' * 64}.vdb",
        )
        generated = set()
        for destination in destinations:
            for suffix in (".tmp", ".partial"):
                candidate = helper(destination, suffix=suffix)
                self.assertEqual(candidate.parent, destination.parent)
                self.assertLessEqual(len(candidate.name), 48)
                self.assertNotIn(destination.stem, candidate.name)
                self.assertRegex(
                    candidate.name,
                    rf"^\.[0-9a-f]{{32}}{re.escape(suffix)}$",
                )
                self.assertNotIn(candidate, generated)
                generated.add(candidate)

        for suffix in ("../escape", r"\escape", "bad\0suffix"):
            with self.subTest(suffix=suffix):
                with self.assertRaises(ValueError):
                    helper(destinations[0], suffix=suffix)

    def test_sidecar_array_writer_uses_short_replace_source(self):
        with TemporaryDirectory() as temporary:
            replacements = []
            real_replace = os.replace

            def capture(source, destination):
                replacements.append((Path(source), Path(destination)))
                return real_replace(source, destination)

            with patch.object(sidecar.os, "replace", side_effect=capture):
                sidecar.save_project(
                    Path(temporary) / "project.cbq",
                    sample_project(),
                )
            array_replacements = [
                pair for pair in replacements if pair[1].suffix == ".npy"
            ]
            self.assertTrue(array_replacements)
            for source, destination in array_replacements:
                self.assert_short_replace_source(source, destination)
            manifest_replacements = [
                pair
                for pair in replacements
                if pair[1].name == "manifest.json"
            ]
            self.assertEqual(len(manifest_replacements), 1)
            self.assert_short_replace_source(*manifest_replacements[0])

    def test_canonical_array_writer_uses_short_replace_source(self):
        with TemporaryDirectory() as temporary:
            replacements = []
            real_replace = os.replace

            def capture(source, destination):
                replacements.append((Path(source), Path(destination)))
                return real_replace(source, destination)

            with patch.object(
                canonical_document.os,
                "replace",
                side_effect=capture,
            ):
                reader_api.write_public_batch_bundle(
                    Path(temporary) / "bundle",
                    sample_batch(),
                )
            array_replacements = [
                pair for pair in replacements if pair[1].suffix == ".npy"
            ]
            self.assertTrue(array_replacements)
            for source, destination in array_replacements:
                self.assert_short_replace_source(source, destination)
            document_replacements = [
                pair
                for pair in replacements
                if pair[1].name == "import-batch.json"
            ]
            self.assertEqual(len(document_replacements), 1)
            self.assert_short_replace_source(*document_replacements[0])

    def test_grid_volume_writer_uses_short_replace_source(self):
        with TemporaryDirectory() as temporary:
            replacements = []
            real_replace = os.replace

            def write_vdb(path, _grid, metadata=None):
                Path(path).write_bytes(b"vdb")

            fake_bpy, fake_openvdb = _fake_blender_modules(write_vdb)
            with patch.dict(
                sys.modules,
                {"bpy": fake_bpy, "openvdb": fake_openvdb},
            ):
                sys.modules.pop("ChemBlender.grid_volume", None)
                module = importlib.import_module("ChemBlender.grid_volume")

                def capture(source, destination):
                    replacements.append((Path(source), Path(destination)))
                    return real_replace(source, destination)

                destination = Path(temporary) / f"{'c' * 64}.vdb"
                with patch.object(
                    module.os,
                    "replace",
                    side_effect=capture,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "stop after VDB replace",
                    ):
                        module.create_grid_volume(
                            sample_project().datasets[GRID_ID],
                            destination,
                            collection=object(),
                        )
            sys.modules.pop("ChemBlender.grid_volume", None)
            self.assertEqual(len(replacements), 1)
            self.assert_short_replace_source(*replacements[0])

    def test_surface_writer_uses_short_replace_source(self):
        with TemporaryDirectory() as temporary:
            replacements = []
            real_replace = os.replace

            def write_vdb(path, _grids, metadata=None):
                Path(path).write_bytes(b"vdb")

            fake_bpy, fake_openvdb = _fake_blender_modules(write_vdb)
            with patch.dict(
                sys.modules,
                {"bpy": fake_bpy, "openvdb": fake_openvdb},
            ):
                sys.modules.pop("ChemBlender.grid_volume", None)
                sys.modules.pop("ChemBlender.surface_view", None)
                module = importlib.import_module("ChemBlender.surface_view")

                def capture(source, destination):
                    replacements.append((Path(source), Path(destination)))
                    return real_replace(source, destination)

                destination = Path(temporary) / f"{'d' * 64}.vdb"
                with patch.object(
                    module.os,
                    "replace",
                    side_effect=capture,
                ):
                    module._write_vdb(destination, (), {})
            sys.modules.pop("ChemBlender.surface_view", None)
            sys.modules.pop("ChemBlender.grid_volume", None)
            self.assertEqual(len(replacements), 1)
            self.assert_short_replace_source(*replacements[0])

    def test_grid_primary_error_wins_when_cleanup_also_fails(self):
        with TemporaryDirectory() as temporary:
            def write_vdb(path, _grid, metadata=None):
                Path(path).write_bytes(b"partial")
                raise OSError("grid write failed")

            fake_bpy, fake_openvdb = _fake_blender_modules(write_vdb)
            with patch.dict(
                sys.modules,
                {"bpy": fake_bpy, "openvdb": fake_openvdb},
            ):
                sys.modules.pop("ChemBlender.grid_volume", None)
                module = importlib.import_module("ChemBlender.grid_volume")
                destination = Path(temporary) / f"{'e' * 64}.vdb"
                with patch.object(
                    module.Path,
                    "unlink",
                    side_effect=OSError("grid cleanup failed"),
                ):
                    with self.assertRaisesRegex(
                        OSError,
                        "^grid write failed$",
                    ):
                        module.create_grid_volume(
                            sample_project().datasets[GRID_ID],
                            destination,
                            collection=object(),
                        )
            sys.modules.pop("ChemBlender.grid_volume", None)

    def test_surface_primary_error_wins_when_cleanup_also_fails(self):
        with TemporaryDirectory() as temporary:
            def write_vdb(path, _grids, metadata=None):
                Path(path).write_bytes(b"partial")
                raise OSError("surface write failed")

            fake_bpy, fake_openvdb = _fake_blender_modules(write_vdb)
            with patch.dict(
                sys.modules,
                {"bpy": fake_bpy, "openvdb": fake_openvdb},
            ):
                sys.modules.pop("ChemBlender.grid_volume", None)
                sys.modules.pop("ChemBlender.surface_view", None)
                module = importlib.import_module("ChemBlender.surface_view")
                destination = Path(temporary) / f"{'f' * 64}.vdb"
                with patch.object(
                    module.Path,
                    "unlink",
                    side_effect=OSError("surface cleanup failed"),
                ):
                    with self.assertRaisesRegex(
                        OSError,
                        "^surface write failed$",
                    ):
                        module._write_vdb(destination, (), {})
            sys.modules.pop("ChemBlender.surface_view", None)
            sys.modules.pop("ChemBlender.grid_volume", None)

    def test_grid_vdb_failures_remove_temporary_file(self):
        for failure in ("write", "replace"):
            with self.subTest(failure=failure), TemporaryDirectory() as temporary:
                temporary_paths = []

                def write_vdb(path, _grid, metadata=None):
                    temporary_path = Path(path)
                    temporary_paths.append(temporary_path)
                    temporary_path.write_bytes(b"partial")
                    if failure == "write":
                        raise OSError("grid write failed")

                fake_bpy, fake_openvdb = _fake_blender_modules(write_vdb)
                with patch.dict(
                    sys.modules,
                    {"bpy": fake_bpy, "openvdb": fake_openvdb},
                ):
                    sys.modules.pop("ChemBlender.grid_volume", None)
                    module = importlib.import_module("ChemBlender.grid_volume")
                    destination = Path(temporary) / f"{'1' * 64}.vdb"
                    replace = (
                        patch.object(
                            module.os,
                            "replace",
                            side_effect=OSError("grid replace failed"),
                        )
                        if failure == "replace"
                        else patch.object(module.os, "replace", wraps=os.replace)
                    )
                    with replace, self.assertRaisesRegex(
                        OSError,
                        f"^grid {failure} failed$",
                    ):
                        module.create_grid_volume(
                            sample_project().datasets[GRID_ID],
                            destination,
                            collection=object(),
                        )
                sys.modules.pop("ChemBlender.grid_volume", None)
                self.assertEqual(len(temporary_paths), 1)
                self.assertFalse(temporary_paths[0].exists())
                self.assertFalse(destination.exists())

    def test_surface_vdb_failures_remove_temporary_file(self):
        for failure in ("write", "replace"):
            with self.subTest(failure=failure), TemporaryDirectory() as temporary:
                temporary_paths = []

                def write_vdb(path, _grids, metadata=None):
                    temporary_path = Path(path)
                    temporary_paths.append(temporary_path)
                    temporary_path.write_bytes(b"partial")
                    if failure == "write":
                        raise OSError("surface write failed")

                fake_bpy, fake_openvdb = _fake_blender_modules(write_vdb)
                with patch.dict(
                    sys.modules,
                    {"bpy": fake_bpy, "openvdb": fake_openvdb},
                ):
                    sys.modules.pop("ChemBlender.grid_volume", None)
                    sys.modules.pop("ChemBlender.surface_view", None)
                    module = importlib.import_module("ChemBlender.surface_view")
                    destination = Path(temporary) / f"{'2' * 64}.vdb"
                    replace = (
                        patch.object(
                            module.os,
                            "replace",
                            side_effect=OSError("surface replace failed"),
                        )
                        if failure == "replace"
                        else patch.object(module.os, "replace", wraps=os.replace)
                    )
                    with replace, self.assertRaisesRegex(
                        OSError,
                        f"^surface {failure} failed$",
                    ):
                        module._write_vdb(destination, (), {})
                sys.modules.pop("ChemBlender.surface_view", None)
                sys.modules.pop("ChemBlender.grid_volume", None)
                self.assertEqual(len(temporary_paths), 1)
                self.assertFalse(temporary_paths[0].exists())
                self.assertFalse(destination.exists())

    def test_sidecar_primary_error_wins_when_cleanup_also_fails(self):
        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / "manifest.json"
            with patch.object(
                sidecar.os,
                "replace",
                side_effect=OSError("replace failed"),
            ), patch.object(
                sidecar.Path,
                "unlink",
                side_effect=OSError("cleanup failed"),
            ):
                with self.assertRaisesRegex(OSError, "^replace failed$"):
                    sidecar._atomic_bytes(destination, b"document")

    def test_sidecar_array_primary_error_wins_when_cleanup_also_fails(self):
        with TemporaryDirectory() as temporary:
            with patch.object(
                sidecar.os,
                "replace",
                side_effect=OSError("array replace failed"),
            ), patch.object(
                sidecar.Path,
                "unlink",
                side_effect=OSError("array cleanup failed"),
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "^array replace failed$",
                ):
                    sidecar.save_project(
                        Path(temporary) / "project.cbq",
                        sample_project(),
                    )

    def test_replace_failure_removes_temporary_file(self):
        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / "manifest.json"
            with patch.object(
                sidecar.os,
                "replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaisesRegex(OSError, "^replace failed$"):
                    sidecar._atomic_bytes(destination, b"document")
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_legacy_fixture_file_hashes_are_unchanged(self):
        root = FIXTURES / "sidecar" / "model-v01"
        actual = {
            path.relative_to(root).as_posix(): _sha256(path)
            for path in root.rglob("*")
            if path.is_file()
            and path.relative_to(root).as_posix() in _FIXTURE_HASHES
        }
        self.assertEqual(actual, _FIXTURE_HASHES)

    def test_canonical_document_and_artifact_hashes_are_unchanged(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = reader_api.public_batch_document(
                sample_batch(),
                root,
            )
            artifacts = {
                path.name: _sha256(path)
                for path in (root / "artifacts").glob("*.npy")
            }
        self.assertEqual(
            hashlib.sha256(document).hexdigest(),
            _CANONICAL_DOCUMENT_SHA256,
        )
        self.assertEqual(artifacts, _CANONICAL_ARTIFACT_HASHES)


if __name__ == "__main__":
    unittest.main()
