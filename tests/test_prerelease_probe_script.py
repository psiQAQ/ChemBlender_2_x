import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "ChemBlender"
SCRIPTS = EXTENSION / "scripts"
sys.path.insert(0, str(SCRIPTS))

import probe_prerelease_version as probe_module
from probe_prerelease_version import probe_prerelease_version


PRODUCTION_MANIFEST_SHA256 = (
    "ed8ae130d6946725e9f2ed1bb141e2486c6d5cf80a589209480181ad7ea66f4e"
)
PROBE_VERSION = "2.3.0-alpha.1"


class _BinaryStdout:
    def __init__(self):
        self.buffer = io.BytesIO()


class PrereleaseProbeScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.extension_root = Path(self.temporary.name) / "ChemBlender"
        self.extension_root.mkdir()
        self.manifest = self.extension_root / "blender_manifest.toml"
        self.manifest.write_bytes(
            b'id = "chemblender"\r\n'
            b'version = "2.2.0"\r\n'
            b'platforms = ["windows-x64"]\r\n'
        )
        (self.extension_root / "keep.py").write_text(
            "VALUE = 1\n",
            encoding="utf-8",
            newline="\n",
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def completed(*, returncode=0, stdout="validated\n", stderr=""):
        return subprocess.CompletedProcess(
            args=[],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_production_manifest_bytes_are_unchanged(self):
        before = (EXTENSION / "blender_manifest.toml").read_bytes()

        digest = hashlib.sha256(before).hexdigest()

        self.assertEqual(digest, PRODUCTION_MANIFEST_SHA256)

    def test_probe_changes_exactly_one_temporary_version_and_preserves_source(self):
        source_before = self.manifest.read_bytes()
        observed = {}

        def inspect_copy(command, **kwargs):
            temporary_extension = Path(command[-1])
            observed["temporary_extension"] = temporary_extension
            observed["manifest"] = (
                temporary_extension / "blender_manifest.toml"
            ).read_bytes()
            observed["keep"] = (temporary_extension / "keep.py").read_text(
                encoding="utf-8"
            )
            return self.completed()

        with mock.patch.object(
            probe_module.subprocess,
            "run",
            side_effect=inspect_copy,
        ):
            result = probe_prerelease_version(
                self.extension_root,
                Path("C:/Blender/blender.exe"),
                PROBE_VERSION,
            )

        expected = source_before.replace(
            b'version = "2.2.0"',
            b'version = "2.3.0-alpha.1"',
        )
        self.assertEqual(observed["manifest"], expected)
        self.assertEqual(observed["manifest"].count(b"2.3.0-alpha.1"), 1)
        self.assertEqual(observed["keep"], "VALUE = 1\n")
        self.assertEqual(self.manifest.read_bytes(), source_before)
        self.assertFalse(observed["temporary_extension"].exists())
        self.assertTrue(result["temporary_root_cleaned"])

    def test_probe_excludes_build_outputs_caches_git_and_local_wheels(self):
        (self.extension_root / "chemblender-2.2.0.zip").write_bytes(b"zip")
        (self.extension_root / "chemblender-2.2.0.sha256").write_text(
            "digest\n",
            encoding="utf-8",
        )
        (self.extension_root / "__pycache__").mkdir()
        (self.extension_root / "__pycache__" / "cache.pyc").write_bytes(b"pyc")
        (self.extension_root / ".git").mkdir()
        (self.extension_root / ".git" / "config").write_text(
            "git\n",
            encoding="utf-8",
        )
        (self.extension_root / "wheels").mkdir()
        (self.extension_root / "wheels" / "local.whl").write_bytes(b"wheel")

        def inspect_copy(command, **kwargs):
            temporary_extension = Path(command[-1])
            for relative in (
                "chemblender-2.2.0.zip",
                "chemblender-2.2.0.sha256",
                "__pycache__",
                ".git",
                "wheels",
            ):
                self.assertFalse((temporary_extension / relative).exists(), relative)
            return self.completed()

        with mock.patch.object(
            probe_module.subprocess,
            "run",
            side_effect=inspect_copy,
        ):
            probe_prerelease_version(
                self.extension_root,
                "blender",
                PROBE_VERSION,
            )

    def test_probe_constructs_exact_native_validate_command(self):
        with mock.patch.object(
            probe_module.subprocess,
            "run",
            return_value=self.completed(stdout="ok", stderr="warn"),
        ) as run:
            result = probe_prerelease_version(
                self.extension_root,
                r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
                PROBE_VERSION,
            )

        command = run.call_args.args[0]
        self.assertEqual(
            command[:-1],
            [
                r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
                "--command",
                "extension",
                "validate",
            ],
        )
        self.assertEqual(Path(command[-1]).name, "ChemBlender")
        self.assertEqual(
            run.call_args.kwargs,
            {
                "capture_output": True,
                "text": True,
                "check": False,
            },
        )
        self.assertEqual(result["version"], PROBE_VERSION)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "ok")
        self.assertEqual(result["stderr"], "warn")

    def test_missing_multiple_and_malformed_version_fail_before_subprocess(self):
        cases = {
            "missing": b'id = "chemblender"\n',
            "multiple": (
                b'version = "2.2.0"\n'
                b'version = "2.2.1"\n'
            ),
            "malformed": b"version = 220\n",
        }
        for name, manifest_bytes in cases.items():
            with self.subTest(case=name):
                self.manifest.write_bytes(manifest_bytes)
                with mock.patch.object(
                    probe_module.subprocess,
                    "run",
                ) as run:
                    with self.assertRaisesRegex(ValueError, "version assignment"):
                        probe_prerelease_version(
                            self.extension_root,
                            "blender",
                            PROBE_VERSION,
                        )
                run.assert_not_called()

    def test_nonzero_validate_status_is_returned_and_temporary_root_is_removed(self):
        observed = {}

        def reject(command, **kwargs):
            observed["temporary_extension"] = Path(command[-1])
            return self.completed(
                returncode=7,
                stdout="",
                stderr="unsupported version",
            )

        with mock.patch.object(
            probe_module.subprocess,
            "run",
            side_effect=reject,
        ):
            result = probe_prerelease_version(
                self.extension_root,
                "blender",
                PROBE_VERSION,
            )

        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(result["stderr"], "unsupported version")
        self.assertFalse(observed["temporary_extension"].exists())
        self.assertTrue(result["temporary_root_cleaned"])

    def test_subprocess_launch_failure_still_removes_temporary_root(self):
        observed = {}

        def fail_launch(command, **kwargs):
            observed["temporary_extension"] = Path(command[-1])
            raise OSError("cannot launch Blender")

        with mock.patch.object(
            probe_module.subprocess,
            "run",
            side_effect=fail_launch,
        ):
            with self.assertRaisesRegex(OSError, "cannot launch Blender"):
                probe_prerelease_version(
                    self.extension_root,
                    "blender",
                    PROBE_VERSION,
                )

        self.assertFalse(observed["temporary_extension"].exists())

    def test_cli_emits_sorted_json_and_propagates_native_exit_code(self):
        payload = {
            "command": ["blender", "--command", "extension", "validate", "temporary"],
            "exit_code": 9,
            "stderr": "rejected",
            "stdout": "",
            "temporary_root": "temporary",
            "temporary_root_cleaned": True,
            "version": PROBE_VERSION,
        }
        stdout = _BinaryStdout()

        with (
            mock.patch.object(
                probe_module,
                "probe_prerelease_version",
                return_value=payload,
            ) as probe,
            mock.patch.object(sys, "stdout", stdout),
        ):
            result = probe_module.main(
                [
                    "--extension-root",
                    str(self.extension_root),
                    "--blender",
                    "blender",
                ]
            )

        self.assertEqual(result, 9)
        self.assertEqual(
            stdout.buffer.getvalue(),
            (
                json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
            ).encode("utf-8"),
        )
        probe.assert_called_once_with(
            self.extension_root,
            "blender",
            PROBE_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
