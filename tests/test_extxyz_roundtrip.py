from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core.exporters.xyz import (
    export_extxyz,
    preview_extxyz_export,
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
    DatasetStatus,
    FrameProperty,
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
    def test_float_metadata_keeps_real_type_when_one_frame_is_integral(self):
        source_text = (
            "1\nProperties=species:S:1:pos:R:3 energy=-1.0\nH 0 0 0\n"
            "1\nProperties=species:S:1:pos:R:3 energy=-0.5\nH 0.1 0 0\n"
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "energy.extxyz"
            destination = root / "export.extxyz"
            source.write_text(source_text, encoding="utf-8")
            batch = parse_extxyz(source)
            structure, = batch.structures
            frame_set = next(
                item
                for item in batch.datasets
                if item.semantic_role == "coordinates"
            )
            properties = tuple(
                item for item in batch.datasets if item is not frame_set
            )

            export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=properties,
                confirm_loss=True,
            )
            reparsed = parse_extxyz(destination)

            self.assertEqual(
                semantic_extxyz_differences(batch, reparsed),
                (),
            )

    def test_preview_reports_loss_without_writing_or_requiring_destination(self):
        complete = parse_extxyz(FIXTURES / "multiframe-cell.extxyz")
        structure, = complete.structures
        frame_set = next(
            item
            for item in complete.datasets
            if item.semantic_role == "coordinates"
        )
        properties = tuple(
            item for item in complete.datasets if item is not frame_set
        )

        report = preview_extxyz_export(
            structure,
            frame_set=frame_set,
            properties=properties,
        )

        self.assertFalse(report.written)
        self.assertFalse(report.requires_confirmation)
        self.assertEqual(report.frame_count, 2)

        lossy = parse_extxyz(FIXTURES / "properties-mixed.extxyz")
        structure, = lossy.structures
        frame_set = next(
            item
            for item in lossy.datasets
            if item.semantic_role == "coordinates"
        )
        properties = tuple(
            item for item in lossy.datasets if item is not frame_set
        )
        report = preview_extxyz_export(
            structure,
            frame_set=frame_set,
            properties=properties,
        )

        self.assertFalse(report.written)
        self.assertTrue(report.requires_confirmation)
        self.assertTrue(
            any(entry.code == "ambiguous_property" for entry in report.entries)
        )

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

    def test_unmodeled_large_integer_metadata_requires_loss_confirmation(self):
        huge = 2**64
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "huge.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3 "
                f"huge_scalar={huge} "
                f"huge_vector=[{huge},{huge + 1}]\n"
                "H 0 0 0\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)
            structure, = batch.structures
            frame_set = next(
                item
                for item in batch.datasets
                if item.semantic_role == "coordinates"
            )
            destination = root / "export.extxyz"

            preview = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
            )

            self.assertFalse(preview.written)
            self.assertTrue(preview.requires_confirmation)
            omitted = {
                entry.message
                for entry in preview.entries
                if entry.code == "unsafe_metadata_omitted"
            }
            self.assertTrue(any("huge_scalar" in item for item in omitted))
            self.assertTrue(any("huge_vector" in item for item in omitted))
            self.assertFalse(destination.exists())

            report = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                confirm_loss=True,
            )
            self.assertTrue(report.written)
            output = destination.read_text(encoding="utf-8")
            self.assertNotIn("huge_scalar", output)
            self.assertNotIn("huge_vector", output)

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

    def test_missing_atom_category_requires_token_and_replace_is_atomic(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "categorical.extxyz"
            source.write_text(
                "2\nProperties=species:S:1:pos:R:3:label:S:1\n"
                "H 0 0 0 donor\n"
                "H 1 0 0 acceptor\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)
            structure, = batch.structures
            frame_set = next(
                item for item in batch.datasets if item.semantic_role == "coordinates"
            )
            label = next(
                item
                for item in batch.datasets
                if isinstance(item, AtomFrameProperty)
            )
            codes = numpy.asarray(label.data.codes.values).copy()
            codes[0, 1] = label.data.missing_code
            label = replace(
                label,
                data=CategoricalData(
                    replace(label.data.codes, values=codes),
                    label.data.categories,
                    label.data.missing_code,
                ),
                status=DatasetStatus.AMBIGUOUS,
            )
            destination = root / "export.extxyz"
            destination.write_bytes(b"existing\n")

            preview = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=(label,),
                confirm_loss=True,
            )

            self.assertFalse(preview.written)
            self.assertTrue(
                any(
                    entry.code == "missing_value_token_required"
                    for entry in preview.entries
                )
            )
            self.assertEqual(destination.read_bytes(), b"existing\n")

            with patch(
                "ChemBlender.core.exporters.xyz.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    export_extxyz(
                        destination,
                        structure,
                        frame_set=frame_set,
                        properties=(label,),
                        confirm_loss=True,
                        missing_value_token="0",
                    )
            self.assertEqual(destination.read_bytes(), b"existing\n")
            self.assertEqual(
                tuple(path.name for path in root.iterdir()),
                ("categorical.extxyz", "export.extxyz"),
            )

            report = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=(label,),
                confirm_loss=True,
                missing_value_token="0",
            )
            self.assertTrue(report.written)
            frame, = tuple(iter_extxyz_frames(destination))
            self.assertEqual(dict(frame.values)["label"], ("donor", "0"))

    def test_frame_missing_category_needs_no_cell_token_but_component_atom_does(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "categorical-components.extxyz"
            source.write_text(
                "2\nProperties=species:S:1:pos:R:3:tag:S:2 title=first\n"
                "H 0 0 0 a b\n"
                "H 1 0 0 c d\n"
                "2\nProperties=species:S:1:pos:R:3:tag:S:2\n"
                "H 0 0 0 a b\n"
                "H 1 0 0 c d\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)
            structure, = batch.structures
            frame_set = next(
                item for item in batch.datasets if item.semantic_role == "coordinates"
            )
            title = next(
                item
                for item in batch.datasets
                if isinstance(item, FrameProperty)
                and item.semantic_role == "title"
            )
            destination = root / "frame.extxyz"

            frame_report = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=(title,),
                confirm_loss=True,
            )
            self.assertTrue(frame_report.written)
            self.assertFalse(
                any(
                    entry.code == "missing_value_token_required"
                    for entry in frame_report.entries
                )
            )

            tag = next(
                item
                for item in batch.datasets
                if isinstance(item, AtomFrameProperty)
            )
            codes = numpy.asarray(tag.data.codes.values).copy()
            codes[0, 1, 1] = tag.data.missing_code
            tag = replace(
                tag,
                data=CategoricalData(
                    replace(tag.data.codes, values=codes),
                    tag.data.categories,
                    tag.data.missing_code,
                ),
                status=DatasetStatus.AMBIGUOUS,
            )
            component_preview = export_extxyz(
                root / "component.extxyz",
                structure,
                frame_set=frame_set,
                properties=(tag,),
                confirm_loss=True,
            )
            self.assertFalse(component_preview.written)
            self.assertTrue(
                any(
                    entry.code == "missing_value_token_required"
                    for entry in component_preview.entries
                )
            )
            component_report = export_extxyz(
                root / "component.extxyz",
                structure,
                frame_set=frame_set,
                properties=(tag,),
                confirm_loss=True,
                missing_value_token="0",
            )
            self.assertTrue(component_report.written)
            first, _second = tuple(
                iter_extxyz_frames(root / "component.extxyz")
            )
            self.assertEqual(
                dict(first.values)["tag"],
                (("a", "b"), ("c", "0")),
            )

    def test_all_missing_categorical_frame_is_omitted_without_a_token(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "categorical-frame.extxyz"
            source.write_text(
                "2\nProperties=species:S:1:pos:R:3:label:S:1\n"
                "H 0 0 0 donor\n"
                "H 1 0 0 acceptor\n"
                "2\nProperties=species:S:1:pos:R:3\n"
                "H 0 0 0\n"
                "H 1 0 0\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)
            structure, = batch.structures
            frame_set = next(
                item for item in batch.datasets if item.semantic_role == "coordinates"
            )
            label = next(
                item
                for item in batch.datasets
                if isinstance(item, AtomFrameProperty)
            )
            destination = root / "export.extxyz"

            report = export_extxyz(
                destination,
                structure,
                frame_set=frame_set,
                properties=(label,),
                confirm_loss=True,
            )

            self.assertTrue(report.written)
            self.assertFalse(
                any(
                    entry.code == "missing_value_token_required"
                    for entry in report.entries
                )
            )
            reparsed = parse_extxyz(destination)
            self.assertEqual(
                semantic_extxyz_differences(batch, reparsed),
                (),
            )

    def test_atom_alias_collision_fails_before_temporary_file_is_opened(self):
        batch = parse_extxyz(FIXTURES / "properties-mixed.extxyz")
        structure, = batch.structures
        frame_set = next(
            item for item in batch.datasets if item.semantic_role == "coordinates"
        )
        charge = next(
            item
            for item in batch.datasets
            if isinstance(item, AtomFrameProperty)
            and item.semantic_role == "atomic_charge"
        )
        alias = replace(charge, id=uuid4(), semantic_role="charge")

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "collision.extxyz"
            with patch(
                "ChemBlender.core.exporters.xyz.short_sibling_temporary_path"
            ) as temporary:
                with self.assertRaisesRegex(ValueError, "duplicate.*charge"):
                    export_extxyz(
                        destination,
                        structure,
                        frame_set=frame_set,
                        properties=(charge, alias),
                        confirm_loss=True,
                    )

            temporary.assert_not_called()
            self.assertFalse(destination.exists())

    def test_duplicate_frame_roles_fail_before_temporary_file_is_opened(self):
        batch = parse_extxyz(FIXTURES / "properties-mixed.extxyz")
        structure, = batch.structures
        frame_set = next(
            item for item in batch.datasets if item.semantic_role == "coordinates"
        )
        energy = next(
            item
            for item in batch.datasets
            if isinstance(item, FrameProperty)
            and item.semantic_role == "energy"
        )
        duplicate = replace(energy, id=uuid4())

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "duplicate.extxyz"
            with patch(
                "ChemBlender.core.exporters.xyz.short_sibling_temporary_path"
            ) as temporary:
                with self.assertRaisesRegex(
                    ValueError,
                    "duplicate extXYZ comment key.*energy",
                ):
                    export_extxyz(
                        destination,
                        structure,
                        frame_set=frame_set,
                        properties=(energy, duplicate),
                        confirm_loss=True,
                    )

            temporary.assert_not_called()

    def test_normalized_metadata_collision_fails_before_temporary_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "normalized.extxyz"
            source.write_text(
                "1\nProperties=species:S:1:pos:R:3 "
                "foo-bar=1 foo_bar=2\n"
                "H 0 0 0\n",
                encoding="utf-8",
            )
            batch = parse_extxyz(source)
            structure, = batch.structures
            frame_set = next(
                item
                for item in batch.datasets
                if item.semantic_role == "coordinates"
            )
            properties = tuple(
                item
                for item in batch.datasets
                if isinstance(item, FrameProperty)
            )
            self.assertEqual(
                tuple(item.semantic_role for item in properties),
                ("foo_bar", "foo_bar"),
            )
            destination = root / "normalized-export.extxyz"

            with patch(
                "ChemBlender.core.exporters.xyz.short_sibling_temporary_path"
            ) as temporary:
                with self.assertRaisesRegex(
                    ValueError,
                    "duplicate extXYZ comment key.*foo_bar",
                ):
                    export_extxyz(
                        destination,
                        structure,
                        frame_set=frame_set,
                        properties=properties,
                        confirm_loss=True,
                    )

            temporary.assert_not_called()

    def test_automatic_unit_key_collision_fails_before_temporary_file(self):
        batch = parse_extxyz(FIXTURES / "properties-mixed.extxyz")
        structure, = batch.structures
        frame_set = next(
            item for item in batch.datasets if item.semantic_role == "coordinates"
        )
        energy = next(
            item
            for item in batch.datasets
            if isinstance(item, FrameProperty)
            and item.semantic_role == "energy"
        )
        explicit_unit = replace(
            energy,
            id=uuid4(),
            semantic_role="energy_unit",
        )

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "unit-collision.extxyz"
            with patch(
                "ChemBlender.core.exporters.xyz.short_sibling_temporary_path"
            ) as temporary:
                with self.assertRaisesRegex(
                    ValueError,
                    "duplicate extXYZ comment key.*energy_unit",
                ):
                    export_extxyz(
                        destination,
                        structure,
                        frame_set=frame_set,
                        properties=(energy, explicit_unit),
                        confirm_loss=True,
                    )

            temporary.assert_not_called()


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

    def test_duplicate_dataset_keys_report_multiplicity_without_uuid_matching(self):
        batch = parse_extxyz(FIXTURES / "properties-mixed.extxyz")
        charge = next(
            item
            for item in batch.datasets
            if isinstance(item, AtomFrameProperty)
            and item.semantic_role == "atomic_charge"
        )
        duplicated = replace(
            batch,
            datasets=(*batch.datasets, replace(charge, id=uuid4())),
        )

        differences = semantic_extxyz_differences(duplicated, batch)

        self.assertTrue(
            any("atomic_charge multiplicity differs" in item for item in differences)
        )

    def test_duplicate_dataset_groups_match_independent_of_input_order(self):
        batch = parse_extxyz(FIXTURES / "properties-mixed.extxyz")
        charge = next(
            item
            for item in batch.datasets
            if isinstance(item, AtomFrameProperty)
            and item.semantic_role == "atomic_charge"
        )
        changed_values = numpy.asarray(charge.data.values).copy()
        changed_values[0, 0] = -0.4
        changed = replace(
            charge,
            id=uuid4(),
            data=replace(charge.data, values=changed_values),
        )
        without_charge = tuple(
            item for item in batch.datasets if item is not charge
        )
        left = replace(
            batch,
            datasets=(*without_charge, charge, changed),
        )
        right = replace(
            batch,
            datasets=(*without_charge, changed, charge),
        )

        self.assertEqual(semantic_extxyz_differences(left, right), ())

    def test_dataset_status_is_part_of_semantic_comparison(self):
        batch = parse_extxyz(FIXTURES / "properties-mixed.extxyz")
        charge = next(
            item
            for item in batch.datasets
            if isinstance(item, AtomFrameProperty)
            and item.semantic_role == "atomic_charge"
        )
        changed = replace(
            batch,
            datasets=tuple(
                replace(item, status=DatasetStatus.AMBIGUOUS)
                if item is charge
                else item
                for item in batch.datasets
            ),
        )

        self.assertIn(
            "atomic_charge status differs",
            semantic_extxyz_differences(batch, changed),
        )


if __name__ == "__main__":
    unittest.main()
