import array
import subprocess
import sys
import unittest
from uuid import uuid4

from ChemBlender.core import (
    ArrayData,
    CalculationRecord,
    CalculationStatus,
    DatasetStatus,
    Grid3D,
    ImportBatch,
    ParserReport,
    PropertyDataset,
    ProvenanceRecord,
    QCProject,
    Structure,
)


def array_view(values, shape):
    raw = memoryview(array.array("d", values))
    return raw.cast("B").cast("d", shape=shape)


class QuantumCoreTests(unittest.TestCase):
    def test_core_import_does_not_load_bpy(self):
        code = "import sys; import ChemBlender.core; assert 'bpy' not in sys.modules"
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_array_data_reads_shape_dtype_and_unit(self):
        data = ArrayData(
            array_view(range(6), (2, 3)),
            ("atom", "xyz"),
            "angstrom",
        )
        self.assertEqual(data.shape, (2, 3))
        self.assertEqual(data.dtype, "d")

    def test_array_data_rejects_invalid_dimensions_and_units(self):
        values = array_view(range(6), (2, 3))
        cases = (
            (("atom",), "angstrom"),
            (("atom", "atom"), "angstrom"),
            (("atom", "xyz"), ""),
        )
        for dims, unit in cases:
            with self.subTest(dims=dims, unit=unit):
                with self.assertRaises(ValueError):
                    ArrayData(values, dims, unit)

    def test_structure_and_non_orthogonal_grid(self):
        structure = Structure(
            id=uuid4(),
            revision="r1",
            atomic_numbers=(6, 1),
            coordinates=ArrayData(
                array_view(range(6), (2, 3)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        grid = Grid3D(
            id=uuid4(),
            revision="g1",
            semantic_role="electron_density",
            domain="grid",
            data=ArrayData(
                array_view(range(24), (2, 3, 4)),
                ("x", "y", "z"),
                "electron_per_cubic_bohr",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            origin=(0.0, 0.0, 0.0),
            step_vectors=(
                (1.0, 0.0, 0.0),
                (0.2, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ),
            coordinate_unit="bohr",
        )
        self.assertEqual(structure.coordinates.shape, (2, 3))
        self.assertEqual(grid.grid_shape, (2, 3, 4))

    def test_open_shell_dimensions_are_explicit(self):
        data = ArrayData(
            array_view(range(24), (2, 3, 4)),
            ("spin", "orbital", "basis_function"),
            "dimensionless",
        )
        self.assertEqual(data.dims, ("spin", "orbital", "basis_function"))

    def test_grid_rejects_singular_vectors_and_wrong_spatial_dims(self):
        cases = (
            (
                ArrayData(
                    array_view(range(8), (2, 2, 2)),
                    ("x", "y", "z"),
                    "dimensionless",
                ),
                (
                    (1.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 0.0, 1.0),
                ),
            ),
            (
                ArrayData(
                    array_view(range(8), (2, 2, 2)),
                    ("z", "y", "x"),
                    "dimensionless",
                ),
                (
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.0, 0.0, 1.0),
                ),
            ),
        )
        for data, steps in cases:
            with self.subTest(dims=data.dims, steps=steps):
                with self.assertRaises(ValueError):
                    Grid3D(
                        id=uuid4(),
                        revision="g1",
                        semantic_role="test_grid",
                        domain="grid",
                        data=data,
                        status=DatasetStatus.COMPLETE,
                        source_calculation=None,
                        provenance_ids=(),
                        origin=(0.0, 0.0, 0.0),
                        step_vectors=steps,
                        coordinate_unit="bohr",
                    )

    def test_unknown_unit_requires_ambiguous_status(self):
        common = {
            "id": uuid4(),
            "revision": "d1",
            "semantic_role": "mulliken_charge",
            "domain": "atom",
            "data": ArrayData(
                array_view(range(2), (2,)),
                ("atom",),
                "unknown",
            ),
            "source_calculation": None,
            "provenance_ids": (),
        }
        with self.assertRaises(ValueError):
            PropertyDataset(status=DatasetStatus.COMPLETE, **common)
        dataset = PropertyDataset(status=DatasetStatus.AMBIGUOUS, **common)
        self.assertEqual(dataset.status, DatasetStatus.AMBIGUOUS)

    def test_project_commits_valid_batch(self):
        structure_id, calculation_id, dataset_id, provenance_id = (
            uuid4() for _ in range(4)
        )
        structure = Structure(
            id=structure_id,
            revision="s1",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                array_view(range(3), (1, 3)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        provenance = ProvenanceRecord(
            id=provenance_id,
            revision="p1",
            producer="test",
            producer_version="1",
            source="fixture.xyz",
            source_hash="a" * 64,
            parent_ids=(),
            operation="parse",
            parameters=(),
        )
        dataset = PropertyDataset(
            id=dataset_id,
            revision="d1",
            semantic_role="mulliken_charge",
            domain="atom",
            data=ArrayData(
                array_view(range(1), (1,)),
                ("atom",),
                "elementary_charge",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=calculation_id,
            provenance_ids=(provenance_id,),
        )
        calculation = CalculationRecord(
            id=calculation_id,
            revision="c1",
            status=CalculationStatus.SUCCESS,
            input_structure_ids=(structure_id,),
            result_structure_ids=(structure_id,),
            dataset_ids=(dataset_id,),
            provenance_ids=(provenance_id,),
        )
        report = ParserReport(
            reader_id="test",
            reader_version="1",
            created_entity_ids=(
                structure_id,
                calculation_id,
                dataset_id,
                provenance_id,
            ),
            parsed_capabilities=("structure", "atomic_property"),
            issues=(),
        )
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(
            ImportBatch(
                structures=(structure,),
                calculations=(calculation,),
                datasets=(dataset,),
                provenance=(provenance,),
                report=report,
            )
        )
        self.assertIs(project.structures[structure_id], structure)
        self.assertIs(project.calculations[calculation_id], calculation)
        self.assertIs(project.datasets[dataset_id], dataset)
        self.assertIs(project.provenance[provenance_id], provenance)

    def test_project_rejects_dangling_reference_atomically(self):
        project = QCProject(id=uuid4(), schema_version="0.1")
        calculation = CalculationRecord(
            id=uuid4(),
            revision="c1",
            status=CalculationStatus.SUCCESS,
            input_structure_ids=(uuid4(),),
            result_structure_ids=(),
            dataset_ids=(),
            provenance_ids=(),
        )
        with self.assertRaises(ValueError):
            project.commit(ImportBatch(calculations=(calculation,)))
        self.assertEqual(project.calculations, {})

    def test_project_rejects_duplicate_uuid_atomically(self):
        duplicate_id = uuid4()
        structure = Structure(
            id=duplicate_id,
            revision="s1",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                array_view(range(3), (1, 3)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        dataset = PropertyDataset(
            id=duplicate_id,
            revision="d1",
            semantic_role="charge",
            domain="atom",
            data=ArrayData(
                array_view(range(1), (1,)),
                ("atom",),
                "elementary_charge",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
        )
        project = QCProject(id=uuid4(), schema_version="0.1")
        with self.assertRaises(ValueError):
            project.commit(
                ImportBatch(structures=(structure,), datasets=(dataset,))
            )
        self.assertEqual(project.structures, {})
        self.assertEqual(project.datasets, {})


if __name__ == "__main__":
    unittest.main()
