import contextlib
import hashlib
import importlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "ChemBlender" / "scripts"
EXTENSION = ROOT / "ChemBlender"
sys.path.insert(0, str(SCRIPTS))

import build_extension
import release_metadata
from release_metadata import (
    ParsedReleaseVersion,
    ReleaseMetadata,
    parse_release_version,
    read_release_metadata,
    release_metadata_document,
)


PRODUCTION_MANIFEST_SHA256 = (
    "ec73b31fc8f9341105376c73510dbba7857f57775d7ba2d1f568843fcce5df29"
)


class ReleaseMetadataTests(unittest.TestCase):
    def _write_manifest(
        self,
        root: Path,
        *,
        extension_id: object = "chemblender",
        version: object = "2.2.0",
        platforms: object = ("windows-x64",),
        omit: str | None = None,
    ) -> Path:
        lines = []
        if omit != "id":
            lines.append(
                f"id = {json.dumps(extension_id)}"
                if isinstance(extension_id, str)
                else f"id = {extension_id}"
            )
        if omit != "version":
            lines.append(
                f"version = {json.dumps(version)}"
                if isinstance(version, str)
                else f"version = {version}"
            )
        if omit != "platforms":
            if isinstance(platforms, tuple):
                encoded = ", ".join(json.dumps(value) for value in platforms)
                lines.append(f"platforms = [{encoded}]")
            elif isinstance(platforms, str):
                lines.append(f"platforms = {json.dumps(platforms)}")
            else:
                lines.append(f"platforms = {platforms}")
        path = root / "blender_manifest.toml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_reads_current_manifest_and_derives_exact_names(self):
        metadata = read_release_metadata(EXTENSION)

        self.assertEqual(
            metadata,
            ReleaseMetadata(
                extension_id="chemblender",
                version="2.3.0-rc.1",
                platform="windows-x64",
                package_name="chemblender-2.3.0-rc.1.zip",
                checksum_name="chemblender-2.3.0-rc.1.sha256",
                artifact_name="chemblender-2.3.0-rc.1-windows-x64",
            ),
        )

    def test_parses_supported_stable_and_prerelease_versions(self):
        cases = (
            (
                "2.3.0",
                ParsedReleaseVersion(
                    value="2.3.0",
                    major=2,
                    minor=3,
                    patch=0,
                    channel=None,
                    channel_number=None,
                    is_prerelease=False,
                ),
            ),
            (
                "2.3.0-alpha.1",
                ParsedReleaseVersion(
                    value="2.3.0-alpha.1",
                    major=2,
                    minor=3,
                    patch=0,
                    channel="alpha",
                    channel_number=1,
                    is_prerelease=True,
                ),
            ),
            (
                "2.3.0-beta.2",
                ParsedReleaseVersion(
                    value="2.3.0-beta.2",
                    major=2,
                    minor=3,
                    patch=0,
                    channel="beta",
                    channel_number=2,
                    is_prerelease=True,
                ),
            ),
            (
                "2.3.0-rc.1",
                ParsedReleaseVersion(
                    value="2.3.0-rc.1",
                    major=2,
                    minor=3,
                    patch=0,
                    channel="rc",
                    channel_number=1,
                    is_prerelease=True,
                ),
            ),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(parse_release_version(value), expected)

    def test_parsed_release_version_is_frozen_and_slotted(self):
        parsed = parse_release_version("2.3.0-alpha.1")

        with self.assertRaises(FrozenInstanceError):
            parsed.channel = "beta"
        self.assertFalse(hasattr(parsed, "__dict__"))

    def test_release_channel_document_uses_shared_version_parser(self):
        cases = (
            (
                "2.3.0",
                {"channel": "final", "is_prerelease": False},
            ),
            (
                "2.3.0-alpha.1",
                {"channel": "alpha", "is_prerelease": True},
            ),
            (
                "2.3.0-beta.2",
                {"channel": "beta", "is_prerelease": True},
            ),
            (
                "2.3.0-rc.1",
                {"channel": "rc", "is_prerelease": True},
            ),
        )
        for version, expected in cases:
            with self.subTest(version=version):
                self.assertEqual(
                    release_metadata.release_channel_document(version),
                    expected,
                )

        with self.assertRaisesRegex(ValueError, "release version"):
            release_metadata.release_channel_document("2.3.0-preview.1")

    def test_select_exact_package_run_accepts_one_successful_tag_run(self):
        tag = "v2.3.0-alpha.1"
        commit = "1" * 40

        selected = release_metadata.select_exact_package_run(
            [
                {
                    "id": 101,
                    "head_sha": commit,
                    "head_branch": tag,
                    "event": "push",
                    "conclusion": "failure",
                },
                {
                    "id": 102,
                    "head_sha": "2" * 40,
                    "head_branch": tag,
                    "event": "push",
                    "conclusion": "success",
                },
                {
                    "id": 103,
                    "head_sha": commit,
                    "head_branch": tag,
                    "event": "push",
                    "conclusion": "success",
                },
            ],
            tag=tag,
            tag_commit=commit,
        )

        self.assertEqual(selected, 103)

    def test_select_exact_package_run_rejects_ambiguous_or_malformed_results(self):
        tag = "v2.3.0-alpha.1"
        commit = "1" * 40
        matching_run = {
            "id": 103,
            "head_sha": commit,
            "head_branch": tag,
            "event": "push",
            "conclusion": "success",
        }
        cases = (
            ([], "successful exact package run"),
            ([matching_run, {**matching_run, "id": 104}], "successful exact package run"),
            ([{**matching_run, "id": "103"}], "id"),
            ({"id": 103}, "run records"),
        )

        for records, message in cases:
            with self.subTest(records=records):
                with self.assertRaisesRegex(ValueError, message):
                    release_metadata.select_exact_package_run(
                        records,
                        tag=tag,
                        tag_commit=commit,
                    )

    def test_paginated_workflow_run_records_keep_matches_after_page_one(self):
        tag = "v2.3.0-alpha.1"
        commit = "1" * 40
        pages = [
            {
                "total_count": 101,
                "workflow_runs": [
                    {
                        "id": index,
                        "head_sha": "2" * 40,
                        "head_branch": tag,
                        "event": "push",
                        "conclusion": "success",
                    }
                    for index in range(1, 101)
                ],
            },
            {
                "total_count": 101,
                "workflow_runs": [
                    {
                        "id": 501,
                        "head_sha": commit,
                        "head_branch": tag,
                        "event": "push",
                        "conclusion": "success",
                    }
                ],
            },
        ]

        records = release_metadata.workflow_run_records_from_pages(pages)

        self.assertEqual(len(records), 101)
        self.assertEqual(
            release_metadata.select_exact_package_run(
                records,
                tag=tag,
                tag_commit=commit,
            ),
            501,
        )

    def test_select_exact_package_artifact_requires_one_unexpired_exact_name(self):
        artifact_name = "chemblender-2.3.0-alpha.1-windows-x64"
        selected = release_metadata.select_exact_package_artifact(
            {
                "artifacts": [
                    {"id": 301, "name": artifact_name, "expired": True},
                    {"id": 302, "name": "other", "expired": False},
                    {"id": 303, "name": artifact_name, "expired": False},
                ]
            },
            artifact_name=artifact_name,
        )

        self.assertEqual(selected, 303)

        for document, message in (
            ({"artifacts": []}, "unexpired exact artifact"),
            (
                {
                    "artifacts": [
                        {"id": 303, "name": artifact_name, "expired": False},
                        {"id": 304, "name": artifact_name, "expired": False},
                    ]
                },
                "unexpired exact artifact",
            ),
            ({"artifacts": [{"id": "303", "name": artifact_name, "expired": False}]}, "id"),
            ({"artifacts": "not-a-list"}, "artifacts"),
        ):
            with self.subTest(document=document):
                with self.assertRaisesRegex(ValueError, message):
                    release_metadata.select_exact_package_artifact(
                        document,
                        artifact_name=artifact_name,
                    )

    def test_selection_cli_parses_paginated_rest_workflow_run_pages(self):
        tag = "v2.3.0-alpha.1"
        commit = "1" * 40
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "release_metadata.py"),
                "--select-package-run",
                "--tag",
                tag,
                "--tag-commit",
                commit,
            ],
            input=json.dumps(
                [
                    {
                        "total_count": 1,
                        "workflow_runs": [
                            {
                                "id": 501,
                                "head_sha": commit,
                                "head_branch": tag,
                                "event": "push",
                                "conclusion": "success",
                            }
                        ],
                    }
                ]
            ).encode("utf-8"),
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b'{"run_id":501}\n')
        self.assertEqual(result.stderr, b"")

    def test_rejects_versions_outside_proven_grammar(self):
        invalid = (
            "2.3.0-alpha",
            "2.3.0-alpha.",
            "2.3.0-alpha.0",
            "2.3.0-alpha.01",
            "2.3.0-preview.1",
            "v2.3.0",
            "02.3.0",
            "2.03.0",
            "2.3.00",
            " 2.3.0",
            "2.3.0 ",
            "2.3.0\n",
            "2.3/0",
            "2.3\\0",
            "2\u0663.3.0",
            "2.3.0-alpha.1\u0661",
            "",
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "release version"):
                    parse_release_version(value)

    def test_release_metadata_is_frozen_and_slotted(self):
        metadata = read_release_metadata(EXTENSION)

        with self.assertRaises(FrozenInstanceError):
            metadata.version = "9.9.9"
        self.assertFalse(hasattr(metadata, "__dict__"))

    def test_document_contains_only_release_metadata_fields(self):
        metadata = read_release_metadata(EXTENSION)

        self.assertEqual(
            release_metadata_document(metadata),
            {
                "artifact_name": "chemblender-2.3.0-rc.1-windows-x64",
                "checksum_name": "chemblender-2.3.0-rc.1.sha256",
                "extension_id": "chemblender",
                "package_name": "chemblender-2.3.0-rc.1.zip",
                "platform": "windows-x64",
                "version": "2.3.0-rc.1",
            },
        )

    def test_missing_required_fields_fail(self):
        for field in ("id", "version", "platforms"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                self._write_manifest(root, omit=field)

                with self.assertRaisesRegex(ValueError, field):
                    read_release_metadata(root)

    def test_required_fields_have_exact_types(self):
        cases = (
            {"extension_id": 3},
            {"version": 220},
            {"platforms": "windows-x64"},
        )
        for values in cases:
            with self.subTest(values=values), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                self._write_manifest(root, **values)

                with self.assertRaises(ValueError):
                    read_release_metadata(root)

    def test_manifest_root_must_be_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_manifest(root)

            with mock.patch.object(release_metadata.tomllib, "loads", return_value=[]):
                with self.assertRaisesRegex(ValueError, "root"):
                    read_release_metadata(root)

    def test_extension_id_must_be_chemblender(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_manifest(root, extension_id="other")

            with self.assertRaisesRegex(ValueError, "chemblender"):
                read_release_metadata(root)

    def test_platforms_must_be_exactly_windows_x64(self):
        for platforms in ((), ("windows-x64", "linux-x64"), ("linux-x64",)):
            with (
                self.subTest(platforms=platforms),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                root = Path(temp_dir)
                self._write_manifest(root, platforms=platforms)

                with self.assertRaisesRegex(ValueError, "windows-x64"):
                    read_release_metadata(root)

    def test_invalid_manifest_versions_fail(self):
        unsafe_versions = (
            "",
            " 2.2.0",
            "2.2.0 ",
            "2.é.0",
            "2.2.0.",
            '2.2"0',
            "2.2<0",
            "2.2>0",
            "2.2:0",
            "2.2/0",
            "2.2\\0",
            "2.2|0",
            "2.2?0",
            "2.2*0",
            "02.2.0",
            "2.2.0-alpha.0",
            "2.2.0-preview.1",
        )
        for version in unsafe_versions:
            with (
                self.subTest(version=version),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                root = Path(temp_dir)
                self._write_manifest(root, version=version)

                with self.assertRaises(ValueError):
                    read_release_metadata(root)

    def test_control_and_nul_versions_fail(self):
        for encoded in ('version = "2.2.\\u0001"', 'version = "2.2.\\u0000"'):
            with self.subTest(encoded=encoded), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                path = self._write_manifest(root)
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        'version = "2.2.0"', encoded
                    ),
                    encoding="utf-8",
                )

                with self.assertRaises(ValueError):
                    read_release_metadata(root)

    def test_cli_json_is_compact_sorted_and_deterministic(self):
        command = [
            sys.executable,
            str(SCRIPTS / "release_metadata.py"),
            "--extension-root",
            str(EXTENSION),
            "--format",
            "json",
        ]

        first = subprocess.run(command, capture_output=True, check=False)
        second = subprocess.run(command, capture_output=True, check=False)

        expected = (
            b'{"artifact_name":"chemblender-2.3.0-rc.1-windows-x64",'
            b'"checksum_name":"chemblender-2.3.0-rc.1.sha256",'
            b'"extension_id":"chemblender",'
            b'"package_name":"chemblender-2.3.0-rc.1.zip",'
            b'"platform":"windows-x64","version":"2.3.0-rc.1"}\n'
        )
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        self.assertEqual(first.stdout, expected)
        self.assertEqual(second.stdout, expected)
        self.assertEqual(first.stderr, b"")

    def test_cli_channel_fields_are_explicitly_opt_in(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "release_metadata.py"),
                "--extension-root",
                str(EXTENSION),
                "--format",
                "json",
                "--include-channel",
            ],
            capture_output=True,
            check=False,
        )

        expected = (
            b'{"artifact_name":"chemblender-2.3.0-rc.1-windows-x64",'
            b'"channel":"rc",'
            b'"checksum_name":"chemblender-2.3.0-rc.1.sha256",'
            b'"extension_id":"chemblender","is_prerelease":true,'
            b'"package_name":"chemblender-2.3.0-rc.1.zip",'
            b'"platform":"windows-x64","version":"2.3.0-rc.1"}\n'
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, expected)
        self.assertEqual(result.stderr, b"")

    def test_cli_failure_uses_stderr_and_exit_one(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "release_metadata.py"),
                    "--extension-root",
                    temp_dir,
                    "--format",
                    "json",
                ],
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"ERROR:", result.stderr)

    def test_direct_and_package_imports_are_side_effect_free(self):
        bpy_before = sys.modules.get("bpy")
        direct = importlib.import_module("release_metadata")
        packaged = importlib.import_module("ChemBlender.scripts.release_metadata")
        packaged_build = importlib.import_module(
            "ChemBlender.scripts.build_extension"
        )
        packaged_verifier = importlib.import_module(
            "ChemBlender.scripts.verify_release_artifact"
        )
        packaged_notes = importlib.import_module(
            "ChemBlender.scripts.extract_release_notes"
        )
        packaged_validator = importlib.import_module(
            "ChemBlender.scripts.validate_extension"
        )

        self.assertIsNotNone(direct.ReleaseMetadata)
        self.assertIsNotNone(packaged.ReleaseMetadata)
        self.assertIsNotNone(packaged_build.main)
        self.assertIsNotNone(packaged_verifier.verify_artifact)
        self.assertIsNotNone(packaged_notes.extract_release_notes)
        self.assertIsNotNone(packaged_validator.main)
        self.assertIs(sys.modules.get("bpy"), bpy_before)

    def test_build_and_verifier_do_not_reassemble_release_names(self):
        for name in ("build_extension.py", "verify_release_artifact.py"):
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertNotIn('f"chemblender-', text, name)
            self.assertNotIn("f'chemblender-", text, name)

    def test_build_reads_metadata_once_and_requires_exact_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            extension_root = Path(temp_dir)
            self._write_manifest(extension_root)

            def fake_run(command, *, cwd):
                if command[-3:] == ["--command", "extension", "build"]:
                    (cwd / "chemblender-2.2.0.zip").write_bytes(b"zip")

            output = io.StringIO()
            with (
                mock.patch.object(build_extension, "_extension_root", return_value=extension_root),
                mock.patch.object(build_extension, "_agent_system", return_value="windows"),
                mock.patch.object(build_extension, "_resolve_python_runner", return_value="python"),
                mock.patch.object(build_extension, "_resolve_blender_binary", return_value="blender"),
                mock.patch.object(build_extension, "_run", side_effect=fake_run),
                mock.patch.object(
                    build_extension,
                    "read_release_metadata",
                    wraps=read_release_metadata,
                ) as read_metadata,
                mock.patch.object(sys, "argv", ["build_extension.py"]),
                contextlib.redirect_stdout(output),
            ):
                result = build_extension.main()

        self.assertEqual(result, 0)
        read_metadata.assert_called_once_with(extension_root)
        self.assertIn("chemblender-2.2.0.zip", output.getvalue())
        self.assertIn("chemblender-2.2.0-windows-x64", output.getvalue())

    def test_build_rejects_missing_exact_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            extension_root = Path(temp_dir)
            self._write_manifest(extension_root)
            error = io.StringIO()
            with (
                mock.patch.object(build_extension, "_extension_root", return_value=extension_root),
                mock.patch.object(build_extension, "_agent_system", return_value="windows"),
                mock.patch.object(build_extension, "_resolve_python_runner", return_value="python"),
                mock.patch.object(build_extension, "_resolve_blender_binary", return_value="blender"),
                mock.patch.object(build_extension, "_run"),
                mock.patch.object(sys, "argv", ["build_extension.py"]),
                contextlib.redirect_stderr(error),
            ):
                result = build_extension.main()

        self.assertEqual(result, 1)
        self.assertIn("chemblender-2.2.0.zip", error.getvalue())

    def test_production_manifest_bytes_are_unchanged(self):
        manifest = (EXTENSION / "blender_manifest.toml").read_bytes()
        digest = hashlib.sha256(manifest.replace(b"\r\n", b"\n")).hexdigest()

        self.assertEqual(digest, PRODUCTION_MANIFEST_SHA256)


if __name__ == "__main__":
    unittest.main()
