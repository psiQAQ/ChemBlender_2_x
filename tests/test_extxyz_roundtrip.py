from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy

from ChemBlender.core.exporters.xyz import (
    export_extxyz,
    semantic_extxyz_differences,
)
from ChemBlender.core.formats.extxyz import (
    ExtXYZSyntaxError,
    iter_extxyz_frames,
    parse_extxyz,
    parse_extxyz_comment,
)
from ChemBlender.core.model import (
    AtomFrameProperty,
    CategoricalData,
    CellFrameProperty,
    ImportBatch,
)


FIXTURES = Path(__file__).parent / "fixtures" / "extxyz"


def _replace_label_categories(batch):
    datasets = []
    for dataset in batch.datasets:
        if (
            isinstance(dataset, AtomFrameProperty)
            and dataset.semantic_role == "label"
        ):
            datasets.append(
                replace(
                    dataset,
                    data=CategoricalData(
                        dataset.data.codes,
                        ('donor "site"', r"acceptor\site"),
                        dataset.data.missing_code,
                    ),
                )
            )
        elif dataset.semantic_role == "title":
            datasets.append(
                replace(
                    dataset,
                    data=CategoricalData(
                        dataset.data.codes,
                        ("4",),
                        dataset.data.missing_code,
                    ),
                )
            )
        else:
            datasets.append(dataset)
    return replace(batch, datasets=tuple(datasets))


class ExtXYZExporterTests(unittest.TestCase):
    def test_schema_metadata_and_categorical_values_are_deterministic(self):
        source_text = (
            "2\n"
            'Lattice="4 0 0 0 4 0 0 0 4" pbc="T F T" '
            "Properties=species:S:1:pos:R:3:zeta:R:1:label:S:1:"
            "force:R:3:flag:L:1 "
            'title="hello world" step=4 vector=[1,2.5,3] '
            "matrix=[[1,2],[3,4]] active=T "
            "force_unit=electron_volt_per_angstrom\n"
            "C -0 0 0 9 donor 1 2 3 T\n"
            "H 1 0 0 8 acceptor 4 5 6 F\n"
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.extxyz"
            source.write_text(source_text, encoding="utf-8")
            batch = _replace_label_categories(parse_extxyz(source))
            structure, = batch.structures
            frame_set = next(
                item for item in batch.datasets if item.semantic_role == "coordinates"
            )
            properties = tuple(
                item for item in batch.datasets if item is not frame_set
            )
            destination = root / "export.extxyz"

            preview = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=properties,
            )

            self.assertFalse(preview.written)
            self.assertTrue(preview.requires_confirmation)
            self.assertFalse(destination.exists())

            report = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=properties,
                confirm_loss=True,
            )
            first_bytes = destination.read_bytes()
            export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=properties,
                confirm_loss=True,
            )

            self.assertTrue(report.written)
            self.assertEqual(destination.read_bytes(), first_bytes)
            self.assertNotIn(b"-0 ", first_bytes)
            frame, = tuple(iter_extxyz_frames(destination))
            self.assertEqual(
                tuple(field.name for field in frame.properties),
                ("species", "pos", "force", "zeta", "label", "flag"),
            )
            comment = parse_extxyz_comment(frame.comment.raw)
            metadata = {entry.key: entry.value for entry in comment.entries}
            self.assertEqual(metadata["title"], "4")
            self.assertEqual(metadata["step"], 4)
            self.assertEqual(metadata["vector"], (1.0, 2.5, 3.0))
            self.assertEqual(metadata["matrix"], ((1, 2), (3, 4)))
            self.assertIs(metadata["active"], True)
            self.assertEqual(
                dict(frame.values)["label"],
                ('donor "site"', r"acceptor\site"),
            )

            reparsed = parse_extxyz(destination)
            self.assertEqual(
                semantic_extxyz_differences(batch, reparsed),
                (),
            )

    def test_multiframe_cell_round_trip_ignores_identity_and_whitespace(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "cells.extxyz"
            batch = parse_extxyz(FIXTURES / "multiframe-cell.extxyz")
            structure, = batch.structures
            frame_set = next(
                item for item in batch.datasets if item.semantic_role == "coordinates"
            )
            properties = tuple(
                item for item in batch.datasets if item is not frame_set
            )

            report = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=properties,
            )
            reparsed = parse_extxyz(destination)

            self.assertTrue(report.written)
            self.assertEqual(report.frame_count, 2)
            self.assertTrue(
                any(
                    isinstance(item, CellFrameProperty)
                    for item in reparsed.datasets
                )
            )
            self.assertEqual(
                semantic_extxyz_differences(batch, reparsed),
                (),
            )

    def test_unsafe_raw_metadata_requires_confirmation_before_omission(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "unsafe.extxyz"
            source.write_text(
                "1\n"
                "Properties=species:S:1:pos:R:3 ragged=[[1,2],[3]]\n"
                "H 0 0 0\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)
            structure, = batch.structures
            frame_set = next(
                item for item in batch.datasets if item.semantic_role == "coordinates"
            )
            destination = root / "export.extxyz"

            preview = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
            )

            self.assertFalse(preview.written)
            self.assertTrue(preview.requires_confirmation)
            self.assertTrue(
                any(entry.code == "unsafe_metadata_omitted" for entry in preview.entries)
            )
            self.assertFalse(destination.exists())

            report = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                confirm_loss=True,
            )
            self.assertTrue(report.written)
            self.assertNotIn("ragged", destination.read_text(encoding="utf-8"))

    def test_nonfinite_partial_export_requires_explicit_missing_token(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "nonfinite.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3:q:R:1\n"
                "H 0 0 0 1\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)
            structure, = batch.structures
            frame_set = next(
                item for item in batch.datasets if item.semantic_role == "coordinates"
            )
            q_property = next(
                item
                for item in batch.datasets
                if isinstance(item, AtomFrameProperty)
            )
            values = numpy.asarray(q_property.data.values).copy()
            values[0, 0] = numpy.nan
            q_property = replace(
                q_property,
                data=replace(q_property.data, values=values),
            )
            destination = root / "export.extxyz"

            preview = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=(q_property,),
                confirm_loss=True,
            )

            self.assertFalse(preview.written)
            self.assertTrue(preview.requires_confirmation)
            self.assertTrue(
                any(entry.code == "missing_value_token_required" for entry in preview.entries)
            )

            report = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=(q_property,),
                confirm_loss=True,
                missing_value_token="0",
            )
            self.assertTrue(report.written)
            self.assertEqual(report.missing_value_token, "0")

    def test_malformed_quoted_atom_value_is_a_stable_syntax_error(self):
        with self.assertRaisesRegex(ExtXYZSyntaxError, "invalid quoted columns"):
            tuple(
                iter_extxyz_frames(
                    StringIO(
                        "1\n"
                        "Properties=species:S:1:pos:R:3:label:S:1\n"
                        'H 0 0 0 "unfinished\n'
                    )
                )
            )


class ExtXYZSemanticComparatorTests(unittest.TestCase):
    def test_reports_semantic_changes_but_not_uuid_or_comment_whitespace(self):
        batch = parse_extxyz(FIXTURES / "properties-mixed.extxyz")
        frame_set = next(
            item for item in batch.datasets if item.semantic_role == "coordinates"
        )
        changed_comments = replace(
            frame_set,
            comments=("different serialization",),
        )
        equivalent = ImportBatch(
            structures=batch.structures,
            datasets=(
                changed_comments,
                *(item for item in batch.datasets if item is not frame_set),
            ),
        )
        self.assertEqual(semantic_extxyz_differences(batch, equivalent), ())

        shifted_values = numpy.asarray(frame_set.data.values).copy()
        shifted_values[0, 0, 0] += 0.1
        changed = replace(
            equivalent,
            datasets=(
                replace(
                    changed_comments,
                    data=replace(changed_comments.data, values=shifted_values),
                ),
                *(item for item in batch.datasets if item is not frame_set),
            ),
        )
        self.assertIn(
            "coordinates values differ",
            semantic_extxyz_differences(batch, changed),
        )


if __name__ == "__main__":
    unittest.main()
