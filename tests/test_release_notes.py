import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ChemBlender" / "scripts"))

from extract_release_notes import extract_release_notes


class ReleaseNotesTests(unittest.TestCase):
    def test_extracts_only_requested_version_body(self):
        changelog = """# Changelog

## [Unreleased]

- Later work.

## [2.2.0] - 2026-07-21

### Added

- Extension packaging.

## [2.1.1] - 2026-07-21

- Slim assets.
"""

        notes = extract_release_notes(changelog, "2.2.0")

        self.assertEqual(notes, "### Added\n\n- Extension packaging.\n")

    def test_missing_version_fails(self):
        with self.assertRaisesRegex(ValueError, "exactly one dated entry"):
            extract_release_notes("# Changelog\n", "2.2.0")

    def test_duplicate_version_fails(self):
        changelog = """## [2.2.0] - 2026-07-21

- First.

## [2.2.0] - 2026-07-22

- Second.
"""

        with self.assertRaisesRegex(ValueError, "exactly one dated entry"):
            extract_release_notes(changelog, "2.2.0")

    def test_extracts_exact_prerelease_heading(self):
        changelog = """## [2.3.0-alpha.1] - 2026-07-26

- Alpha release.

## [2.3.0] - 2026-07-27

- Stable release.
"""

        notes = extract_release_notes(changelog, "2.3.0-alpha.1")

        self.assertEqual(notes, "- Alpha release.\n")

    def test_prerelease_entry_must_be_unique_present_and_nonempty(self):
        duplicate = """## [2.3.0-alpha.1] - 2026-07-26

- First.

## [2.3.0-alpha.1] - 2026-07-27

- Second.
"""
        empty = """## [2.3.0-alpha.1] - 2026-07-26

## [2.3.0] - 2026-07-27

- Stable.
"""

        with self.assertRaisesRegex(ValueError, "exactly one dated entry"):
            extract_release_notes("# Changelog\n", "2.3.0-alpha.1")
        with self.assertRaisesRegex(ValueError, "exactly one dated entry"):
            extract_release_notes(duplicate, "2.3.0-alpha.1")
        with self.assertRaisesRegex(ValueError, "empty"):
            extract_release_notes(empty, "2.3.0-alpha.1")

    def test_invalid_prerelease_version_fails_before_heading_lookup(self):
        with self.assertRaisesRegex(ValueError, "release version"):
            extract_release_notes("# Changelog\n", "2.3.0-preview.1")

    def test_reference_links_are_not_release_notes(self):
        changelog = """## [2.1.0] - 2026-07-07

- Imported baseline.

[2.1.0]: https://example.invalid/v2.1.0
"""

        notes = extract_release_notes(changelog, "2.1.0")

        self.assertEqual(notes, "- Imported baseline.\n")

    def test_cli_writes_utf8_notes_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            changelog = temp / "CHANGELOG.md"
            output = temp / "notes.md"
            changelog.write_text(
                "## [2.2.0] - 2026-07-21\n\n- Release body.\n",
                encoding="utf-8",
            )

            from extract_release_notes import main

            result = main(
                [
                    "--changelog",
                    str(changelog),
                    "--version",
                    "2.2.0",
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(result, 0)
            self.assertEqual(output.read_bytes(), b"- Release body.\n")


if __name__ == "__main__":
    unittest.main()
