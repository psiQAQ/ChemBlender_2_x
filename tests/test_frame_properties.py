import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    AtomFrameProperty,
    CategoricalData,
    CellFrameProperty,
    DatasetStatus,
    FrameProperty,
    FrameSet,
    ImportBatch,
    QCProject,
    Structure,
)
from ChemBlender.core.sidecar import close_project, open_project, save_project


def structure_and_frames(*, frame_count=2, atom_count=2):
    structure = Structure(
        id=uuid4(),
        revision="structure-r1",
        atomic_numbers=(6,) * atom_count,
        coordinates=ArrayData(
            numpy.zeros((atom_count, 3)),
            ("atom", "xyz"),
            "angstrom",
        ),
    )
    frames = FrameSet(
        id=uuid4(),
        revision="frames-r1",
        semantic_role="coordinates",
        domain="frame",
        data=ArrayData(
            numpy.zeros((frame_count, atom_count, 3)),
            ("frame", "atom", "xyz"),
            "angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure.id,
        comments=("",) * frame_count,
    )
    return structure, frames


def property_fields(*, domain, data, frame_set_id, status=DatasetStatus.COMPLETE):
    return {
        "id": uuid4(),
        "revision": "property-r1",
        "semantic_role": "test_property",
        "domain": domain,
        "data": data,
        "status": status,
        "source_calculation": None,
        "provenance_ids": (),
        "frame_set_id": frame_set_id,
    }


class CategoricalDataTests(unittest.TestCase):
    def test_integer_codes_preserve_categories_and_explicit_missing_value(self):
        data = CategoricalData(
            codes=ArrayData(
                numpy.asarray([0, 1, -1], dtype=numpy.int16),
                ("atom",),
                "dimensionless",
            ),
            categories=("donor", "acceptor"),
            missing_code=-1,
        )

        self.assertEqual(data.categories[data.codes.values[1]], "acceptor")
        self.assertEqual(data.missing_code, -1)
        self.assertFalse(data.codes.values.dtype.hasobject)
        self.assertFalse(hasattr(data, "validity_mask"))

    def test_rejects_noninteger_codes_duplicate_categories_and_invalid_codes(self):
        cases = (
            {
                "codes": ArrayData(
                    numpy.asarray([0.0]), ("atom",), "dimensionless"
                ),
                "categories": ("carbon",),
                "missing_code": -1,
            },
            {
                "codes": ArrayData(
                    numpy.asarray(["carbon"], dtype=object),
                    ("atom",),
                    "dimensionless",
                ),
                "categories": ("carbon",),
                "missing_code": -1,
            },
            {
                "codes": ArrayData(
                    numpy.asarray([0]), ("atom",), "dimensionless"
                ),
                "categories": ("carbon", "carbon"),
                "missing_code": -1,
            },
            {
                "codes": ArrayData(
                    numpy.asarray([2]), ("atom",), "dimensionless"
                ),
                "categories": ("carbon",),
                "missing_code": -1,
            },
            {
                "codes": ArrayData(
                    numpy.asarray([0]), ("atom",), "dimensionless"
                ),
                "categories": ("carbon",),
                "missing_code": 0,
            },
        )
        for fields in cases:
            with self.subTest(fields=fields):
                with self.assertRaises((TypeError, ValueError)):
                    CategoricalData(**fields)


class FramePropertyValidationTests(unittest.TestCase):
    def test_frame_property_requires_leading_frame_dimension(self):
        _, frames = structure_and_frames()
        with self.assertRaisesRegex(ValueError, "leading frame"):
            FrameProperty(
                **property_fields(
                    domain="frame",
                    data=ArrayData(
                        numpy.zeros(2), ("sample",), "dimensionless"
                    ),
                    frame_set_id=frames.id,
                )
            )

    def test_atom_and_cell_properties_require_their_exact_prefixes(self):
        _, frames = structure_and_frames()
        with self.assertRaisesRegex(ValueError, "frame, atom"):
            AtomFrameProperty(
                **property_fields(
                    domain="atom_frame",
                    data=ArrayData(
                        numpy.zeros((2, 3)),
                        ("atom", "xyz"),
                        "electron_volt_per_angstrom",
                    ),
                    frame_set_id=frames.id,
                )
            )
        with self.assertRaisesRegex(ValueError, "frame, cell_vector, xyz"):
            CellFrameProperty(
                **property_fields(
                    domain="cell_frame",
                    data=ArrayData(
                        numpy.zeros((2, 3)),
                        ("frame", "xyz"),
                        "angstrom",
                    ),
                    frame_set_id=frames.id,
                )
            )
        with self.assertRaisesRegex(ValueError, "3 by 3"):
            CellFrameProperty(
                **property_fields(
                    domain="cell_frame",
                    data=ArrayData(
                        numpy.zeros((2, 2, 3)),
                        ("frame", "cell_vector", "xyz"),
                        "angstrom",
                    ),
                    frame_set_id=frames.id,
                )
            )

    def test_partial_numeric_property_requires_exact_boolean_mask(self):
        _, frames = structure_and_frames()
        data = ArrayData(
            numpy.zeros((2, 2, 3)),
            ("frame", "atom", "xyz"),
            "electron_volt_per_angstrom",
        )
        common = property_fields(
            domain="atom_frame",
            data=data,
            frame_set_id=frames.id,
            status=DatasetStatus.PARTIAL,
        )
        with self.assertRaisesRegex(ValueError, "validity mask"):
            AtomFrameProperty(**common)

        invalid_masks = (
            ArrayData(
                numpy.ones((2, 2), dtype=numpy.int8),
                ("frame", "atom"),
                "dimensionless",
            ),
            ArrayData(
                numpy.ones((2, 2), dtype=numpy.bool_),
                ("frame", "atom"),
                "angstrom",
            ),
            ArrayData(
                numpy.ones(2, dtype=numpy.bool_),
                ("frame",),
                "dimensionless",
            ),
        )
        for mask in invalid_masks:
            with self.subTest(mask=mask):
                with self.assertRaisesRegex(ValueError, "validity mask"):
                    AtomFrameProperty(**common, validity_mask=mask)

        valid = AtomFrameProperty(
            **common,
            validity_mask=ArrayData(
                numpy.asarray([[True, False], [True, True]]),
                ("frame", "atom"),
                "dimensionless",
            ),
        )
        self.assertEqual(valid.validity_mask.shape, (2, 2))

        logical = property_fields(
            domain="frame",
            data=ArrayData(
                numpy.asarray([True, False]),
                ("frame",),
                "dimensionless",
            ),
            frame_set_id=frames.id,
            status=DatasetStatus.PARTIAL,
        )
        with self.assertRaisesRegex(ValueError, "validity mask"):
            FrameProperty(**logical)
        self.assertIsNotNone(
            FrameProperty(
                **logical,
                validity_mask=ArrayData(
                    numpy.asarray([True, True]),
                    ("frame",),
                    "dimensionless",
                ),
            ).validity_mask
        )

    def test_complete_property_forbids_mask_and_categorical_partial_uses_missing_code(self):
        _, frames = structure_and_frames()
        complete = property_fields(
            domain="frame",
            data=ArrayData(
                numpy.zeros(2), ("frame",), "dimensionless"
            ),
            frame_set_id=frames.id,
        )
        with self.assertRaisesRegex(ValueError, "Complete.*mask"):
            FrameProperty(
                **complete,
                validity_mask=ArrayData(
                    numpy.ones(2, dtype=numpy.bool_),
                    ("frame",),
                    "dimensionless",
                ),
            )

        categorical = AtomFrameProperty(
            **property_fields(
                domain="atom_frame",
                data=CategoricalData(
                    codes=ArrayData(
                        numpy.asarray([[0, -1], [1, 0]], dtype=numpy.int8),
                        ("frame", "atom"),
                        "dimensionless",
                    ),
                    categories=("donor", "acceptor"),
                    missing_code=-1,
                ),
                frame_set_id=frames.id,
                status=DatasetStatus.PARTIAL,
            )
        )
        self.assertIsNone(categorical.validity_mask)

    def test_frame_and_cell_partial_masks_use_their_declared_prefixes(self):
        _, frames = structure_and_frames()
        frame_property = FrameProperty(
            **property_fields(
                domain="frame",
                data=ArrayData(
                    numpy.zeros((2, 3)),
                    ("frame", "xyz"),
                    "dimensionless",
                ),
                frame_set_id=frames.id,
                status=DatasetStatus.PARTIAL,
            ),
            validity_mask=ArrayData(
                numpy.asarray([True, False]),
                ("frame",),
                "dimensionless",
            ),
        )
        cell_property = CellFrameProperty(
            **property_fields(
                domain="cell_frame",
                data=ArrayData(
                    numpy.zeros((2, 3, 3)),
                    ("frame", "cell_vector", "xyz"),
                    "angstrom",
                ),
                frame_set_id=frames.id,
                status=DatasetStatus.PARTIAL,
            ),
            validity_mask=ArrayData(
                numpy.asarray([True, False]),
                ("frame",),
                "dimensionless",
            ),
        )

        self.assertEqual(frame_property.validity_mask.dims, ("frame",))
        self.assertEqual(cell_property.validity_mask.dims, ("frame",))


class FramePropertyProjectTests(unittest.TestCase):
    def test_commit_validates_frame_set_reference_and_frame_atom_counts(self):
        structure, frames = structure_and_frames()
        project = QCProject(id=uuid4(), schema_version="0.2")
        project.commit(ImportBatch(structures=(structure,), datasets=(frames,)))

        valid = AtomFrameProperty(
            **property_fields(
                domain="atom_frame",
                data=ArrayData(
                    numpy.zeros((2, 2, 3)),
                    ("frame", "atom", "xyz"),
                    "electron_volt_per_angstrom",
                ),
                frame_set_id=frames.id,
            )
        )
        project.commit(ImportBatch(datasets=(valid,)))
        self.assertIs(project.datasets[valid.id], valid)

        cases = (
            FrameProperty(
                **property_fields(
                    domain="frame",
                    data=ArrayData(
                        numpy.zeros(3), ("frame",), "dimensionless"
                    ),
                    frame_set_id=frames.id,
                )
            ),
            AtomFrameProperty(
                **property_fields(
                    domain="atom_frame",
                    data=ArrayData(
                        numpy.zeros((2, 3)),
                        ("frame", "atom"),
                        "dimensionless",
                    ),
                    frame_set_id=frames.id,
                )
            ),
            CellFrameProperty(
                **property_fields(
                    domain="cell_frame",
                    data=ArrayData(
                        numpy.zeros((3, 3, 3)),
                        ("frame", "cell_vector", "xyz"),
                        "angstrom",
                    ),
                    frame_set_id=frames.id,
                )
            ),
            FrameProperty(
                **property_fields(
                    domain="frame",
                    data=ArrayData(
                        numpy.zeros(2), ("frame",), "dimensionless"
                    ),
                    frame_set_id=uuid4(),
                )
            ),
        )
        for invalid in cases:
            with self.subTest(dataset=type(invalid).__name__):
                with self.assertRaises(ValueError):
                    project.commit(ImportBatch(datasets=(invalid,)))

    def test_sidecar_round_trip_preserves_all_property_types_without_object_arrays(self):
        structure, frames = structure_and_frames()
        frame_property = FrameProperty(
            **property_fields(
                domain="frame",
                data=ArrayData(
                    numpy.asarray([1.0, 2.0]), ("frame",), "hartree"
                ),
                frame_set_id=frames.id,
            )
        )
        atom_property = AtomFrameProperty(
            **property_fields(
                domain="atom_frame",
                data=CategoricalData(
                    codes=ArrayData(
                        numpy.asarray([[0, 1], [1, -1]], dtype=numpy.int16),
                        ("frame", "atom"),
                        "dimensionless",
                    ),
                    categories=("donor", "acceptor"),
                    missing_code=-1,
                ),
                frame_set_id=frames.id,
                status=DatasetStatus.PARTIAL,
            )
        )
        cell_property = CellFrameProperty(
            **property_fields(
                domain="cell_frame",
                data=ArrayData(
                    numpy.stack((numpy.eye(3), numpy.eye(3) * 2.0)),
                    ("frame", "cell_vector", "xyz"),
                    "angstrom",
                ),
                frame_set_id=frames.id,
            )
        )
        project = QCProject(id=uuid4(), schema_version="0.2")
        project.commit(
            ImportBatch(
                structures=(structure,),
                datasets=(
                    frames,
                    frame_property,
                    atom_property,
                    cell_property,
                ),
            )
        )

        with TemporaryDirectory() as temporary:
            root = save_project(Path(temporary) / "frames.cbq", project)
            restored = open_project(root)
            try:
                self.assertIs(
                    type(restored.datasets[frame_property.id]),
                    FrameProperty,
                )
                restored_atom = restored.datasets[atom_property.id]
                self.assertIs(type(restored_atom), AtomFrameProperty)
                self.assertEqual(
                    restored_atom.data.categories,
                    ("donor", "acceptor"),
                )
                self.assertEqual(
                    numpy.asarray(restored_atom.data.codes.values).tolist(),
                    [[0, 1], [1, -1]],
                )
                self.assertIs(
                    type(restored.datasets[cell_property.id]),
                    CellFrameProperty,
                )
                for array_path in root.joinpath("arrays").glob("*.npy"):
                    self.assertFalse(
                        numpy.load(array_path, allow_pickle=False).dtype.hasobject
                    )
            finally:
                close_project(restored)


if __name__ == "__main__":
    unittest.main()
