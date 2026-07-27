from io import StringIO
from pathlib import Path
import unittest

from ChemBlender.core.formats.extxyz import (
    ExtXYZSyntaxError,
    iter_extxyz_frames,
    parse_extxyz_comment,
    parse_properties_descriptor,
)


FIXTURES = Path(__file__).parent / "fixtures" / "extxyz"


class ExtXYZPropertiesTests(unittest.TestCase):
    def test_properties_descriptor_parses_mixed_types(self):
        fields = parse_properties_descriptor(
            "species:S:+1:pos:R:3:force:R:3:charge:R:1:fixed:L:1:group:I:1"
        )

        self.assertEqual(
            [(field.name, field.kind, field.columns) for field in fields],
            [
                ("species", "S", 1),
                ("pos", "R", 3),
                ("force", "R", 3),
                ("charge", "R", 1),
                ("fixed", "L", 1),
                ("group", "I", 1),
            ],
        )

    def test_properties_descriptor_rejects_invalid_schema(self):
        cases = {
            "duplicate": "species:S:1:species:S:1",
            "invalid Properties type": "species:X:1",
            "positive": "species:S:0",
            "triplets": "species:S",
        }
        for message, descriptor in cases.items():
            with self.subTest(descriptor=descriptor):
                with self.assertRaisesRegex(ExtXYZSyntaxError, message):
                    parse_properties_descriptor(descriptor)


class ExtXYZCommentTests(unittest.TestCase):
    def test_comment_preserves_typed_scalars_vectors_matrices_and_raw_lexemes(self):
        parsed = parse_extxyz_comment(
            'Properties=species:S:1:pos:R:3 '
            'step = 4 energy=-1.25 active=T '
            'title="quoted \\"value\\"" vector=[1, 2.5, 3] '
            'matrix=[[1,2],[3,4]] '
            'mixed=[[1,label],[2,other]] '
            '"escaped key"=bare\\ value '
            'Lattice="1 0 0 0 2 0 0 0 3"'
        )
        values = {entry.key: entry for entry in parsed.entries}

        self.assertEqual(values["step"].value, 4)
        self.assertEqual(values["energy"].value, -1.25)
        self.assertIs(values["active"].value, True)
        self.assertEqual(values["title"].value, 'quoted "value"')
        self.assertEqual(values["vector"].value, (1.0, 2.5, 3.0))
        self.assertEqual(values["matrix"].value, ((1, 2), (3, 4)))
        self.assertEqual(
            values["mixed"].value,
            (("1", "label"), ("2", "other")),
        )
        self.assertEqual(values["escaped key"].value, "bare value")
        self.assertEqual(
            values["Lattice"].raw_lexeme,
            '"1 0 0 0 2 0 0 0 3"',
        )
        self.assertEqual(
            values["Lattice"].value,
            (1, 0, 0, 0, 2, 0, 0, 0, 3),
        )
        self.assertTrue(all(entry.diagnostic is None for entry in parsed.entries))

    def test_unsafe_typed_value_keeps_raw_lexeme_and_diagnostic(self):
        parsed = parse_extxyz_comment("ragged=[[1,2],[3]]")
        entry, = parsed.entries

        self.assertIsNone(entry.value)
        self.assertEqual(entry.raw_lexeme, "[[1,2],[3]]")
        self.assertIn("rectangular", entry.diagnostic)

    def test_comment_rejects_duplicate_keys_and_unclosed_quotes(self):
        with self.assertRaisesRegex(ExtXYZSyntaxError, "duplicate"):
            parse_extxyz_comment("step=1 step=2")
        with self.assertRaisesRegex(ExtXYZSyntaxError, "unclosed quoted"):
            parse_extxyz_comment('title="unfinished')

    def test_arrays_require_nonempty_comma_separated_items(self):
        parsed = parse_extxyz_comment(
            "empty=[] whitespace=[1 2] missing=[1,,2] "
            "empty_brace={} legacy={1 2} modern=[1,2] unclosed=[1,2"
        )
        values = {entry.key: entry for entry in parsed.entries}

        for key in ("empty", "whitespace", "missing", "empty_brace", "unclosed"):
            with self.subTest(key=key):
                self.assertIsNone(values[key].value)
                self.assertIsNotNone(values[key].diagnostic)
        self.assertEqual(values["legacy"].value, (1, 2))
        self.assertEqual(values["modern"].value, (1, 2))
        self.assertEqual(values["unclosed"].raw_lexeme, "[1,2")

    def test_bare_special_characters_require_quoting_or_escaping(self):
        parsed = parse_extxyz_comment(
            r"comma=a,b bracket=a[b] brace=a{b} equals=a=b "
            r'trailing=[1]x escaped=a\,b escaped\,key=1 quoted="a,b"'
        )
        values = {entry.key: entry for entry in parsed.entries}

        for key in ("comma", "bracket", "brace", "equals"):
            with self.subTest(key=key):
                self.assertIsNone(values[key].value)
                self.assertIn("quoted", values[key].diagnostic)
        self.assertIsNone(values["trailing"].value)
        self.assertIn("trailing", values["trailing"].diagnostic)
        self.assertEqual(values["escaped"].value, "a,b")
        self.assertIsNone(values["escaped"].diagnostic)
        self.assertEqual(values["escaped,key"].value, 1)
        self.assertEqual(values["quoted"].value, "a,b")
        self.assertIsNone(values["quoted"].diagnostic)

        with self.assertRaisesRegex(ExtXYZSyntaxError, "quoted"):
            parse_extxyz_comment("bad,key=1")


class ExtXYZFrameIteratorTests(unittest.TestCase):
    def test_default_properties_support_plain_xyz_and_stream_one_frame_at_a_time(self):
        source = iter(
            (
                "1\n",
                "plain comment\n",
                "H 0 0 0 ignored-extra-column\n",
                "not-a-count\n",
            )
        )
        frames = iter_extxyz_frames(source)

        frame = next(frames)
        self.assertEqual(frame.atom_count, 1)
        self.assertEqual(frame.comment.raw, "plain comment")
        self.assertEqual(
            [(field.name, field.kind, field.columns) for field in frame.properties],
            [("species", "S", 1), ("pos", "R", 3)],
        )
        self.assertEqual(dict(frame.values), {"species": ("H",), "pos": ((0.0, 0.0, 0.0),)})
        with self.assertRaisesRegex(ExtXYZSyntaxError, "atom count"):
            next(frames)

    def test_mixed_properties_fixture_parses_exact_typed_columns(self):
        with (FIXTURES / "properties-mixed.extxyz").open(
            encoding="utf-8"
        ) as stream:
            frame, = tuple(iter_extxyz_frames(stream))

        values = dict(frame.values)
        self.assertEqual(values["species"], ("C", "H"))
        self.assertEqual(values["pos"][1], (1.0, 0.0, 0.0))
        self.assertEqual(values["charge"], (-0.2, 0.2))
        self.assertEqual(values["fixed"], (False, True))
        self.assertEqual(values["group"], (2, 3))

    def test_iterator_rejects_truncated_and_wrong_width_rows(self):
        cases = {
            "declared atom rows": "2\n\nH 0 0 0\n",
            "columns": "1\nProperties=species:S:1:pos:R:3\nH 0 0\n",
        }
        for message, text in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(ExtXYZSyntaxError, message):
                    tuple(iter_extxyz_frames(StringIO(text)))

        with self.assertRaisesRegex(ExtXYZSyntaxError, "positive"):
            tuple(iter_extxyz_frames(FIXTURES / "invalid-property.extxyz"))

    def test_common_compatibility_fixtures_parse_without_runtime_dependencies(self):
        for name in (
            "libatoms-typed.extxyz",
            "libatoms-legacy-array.extxyz",
            "ase-lattice.extxyz",
            "ovito-properties.extxyz",
            "multiframe-cell.extxyz",
        ):
            with self.subTest(name=name):
                with (FIXTURES / name).open(encoding="utf-8") as stream:
                    self.assertGreaterEqual(
                        sum(1 for _frame in iter_extxyz_frames(stream)),
                        1,
                    )

    def test_plain_comment_with_equals_suffix_falls_back_as_a_whole(self):
        for comment in (
            "plain comment with x=y suffix",
            "energy=-1 trailing,text",
        ):
            with self.subTest(comment=comment):
                frame, = tuple(
                    iter_extxyz_frames(
                        StringIO(
                            "1\n"
                            f"{comment}\n"
                            "H 0 0 0\n"
                        )
                    )
                )

                self.assertEqual(frame.comment.raw, comment)
                self.assertEqual(frame.comment.entries, ())

    def test_all_key_value_comment_without_properties_remains_typed(self):
        frame, = tuple(
            iter_extxyz_frames(
                StringIO(
                    "1\n"
                    'energy=-1 Lattice="1 0 0 0 1 0 0 0 1"\n'
                    "H 0 0 0\n"
                )
            )
        )
        values = {entry.key: entry.value for entry in frame.comment.entries}

        self.assertEqual(values["energy"], -1)
        self.assertEqual(values["Lattice"], (1, 0, 0, 0, 1, 0, 0, 0, 1))

    def test_reserved_marker_followed_by_free_text_never_drops_schema(self):
        comments = (
            "Properties=species:S:1:pos:R:3:force:R:3 trailing prose",
            'Lattice="1 0 0 0 1 0 0 0 1" trailing prose',
            'pbc="T T T" trailing prose',
        )
        for comment in comments:
            with self.subTest(comment=comment):
                with self.assertRaisesRegex(
                    ExtXYZSyntaxError,
                    "free text.*extXYZ marker",
                ):
                    tuple(
                        iter_extxyz_frames(
                            StringIO(
                                "1\n"
                                f"{comment}\n"
                                "H 0 0 0 1 2 3\n"
                            )
                        )
                    )


if __name__ == "__main__":
    unittest.main()
