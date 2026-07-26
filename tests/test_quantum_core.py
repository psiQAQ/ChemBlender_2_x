import array
import dataclasses
import subprocess
import sys
import unittest
from uuid import uuid4

from ChemBlender.core import (
    ArrayData,
    CalculationGroup,
    CalculationRecord,
    CalculationStatus,
    DatasetStatus,
    FrameSet,
    Grid3D,
    ImportBatch,
    ParserReport,
    PropertyDataset,
    ProvenanceRecord,
    QCProject,
    SourceRecord,
    SourceRevision,
    Structure,
)


def array_view(values, shape):
    raw = memoryview(array.array("d", values))
    return raw.cast("B").cast("d", shape=shape)


class QuantumCoreTests(unittest.TestCase):
    @staticmethod
    def source_pair():
        sources = tuple(
            SourceRecord(
                id=uuid4(),
                display_name=f"source-{index}.xyz",
                source_kind="local_file",
                created_at_utc="2026-07-24T00:00:00Z",
            )
            for index in range(2)
        )
        revisions = tuple(
            SourceRevision(
                id=uuid4(),
                source_id=source.id,
                content_hash=f"{index + 1:064x}",
                byte_size=index + 1,
                locator=f"C:/source-{index}.xyz",
                locator_kind="absolute_path",
                original_filename=f"source-{index}.xyz",
                reader_plugin_id="chemblender.builtin",
                reader_id="fixture",
                reader_version="1",
                reader_api_version="0.1",
                import_parameters_hash="a" * 64,
                parse_identity=f"{index + 10:064x}",
                created_entity_ids=(),
                diagnostic_ids=(),
            )
            for index, source in enumerate(sources)
        )
        return sources, revisions

    def test_project_commits_calculation_group_atomically(self):
        sources, revisions = self.source_pair()
        project = QCProject(id=uuid4(), schema_version="0.2")
        project.commit(
            ImportBatch(sources=sources, source_revisions=revisions)
        )
        group = CalculationGroup(
            suggestion_id=uuid4(),
            source_revision_ids=tuple(item.id for item in revisions),
            evidence_ids=(uuid4(),),
        )

        project.commit_calculation_groups((group,))

        self.assertEqual(project.calculation_groups, {group.id: group})

    def test_project_rejects_invalid_calculation_groups_without_mutation(self):
        sources, revisions = self.source_pair()
        group = CalculationGroup(
            suggestion_id=uuid4(),
            source_revision_ids=tuple(item.id for item in revisions),
            evidence_ids=(uuid4(),),
        )
        cases = (
            (ImportBatch(), (group,)),
            (
                ImportBatch(sources=sources, source_revisions=revisions),
                (group, group),
            ),
            (
                ImportBatch(
                    sources=(
                        dataclasses.replace(sources[0], id=group.id),
                        sources[1],
                    ),
                    source_revisions=(
                        dataclasses.replace(
                            revisions[0],
                            source_id=group.id,
                        ),
                        revisions[1],
                    ),
                ),
                (group,),
            ),
        )
        for batch, groups in cases:
            with self.subTest(groups=len(groups), sources=len(batch.sources)):
                project = QCProject(id=uuid4(), schema_version="0.2")
                project.commit(batch)
                before = dict(project.calculation_groups)
                with self.assertRaises(ValueError):
                    project.commit_calculation_groups(groups)
                self.assertEqual(project.calculation_groups, before)

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

    def test_frame_set_commits_with_matching_reference_structure(self):
        structure = Structure(
            id=uuid4(),
            revision="s1",
            atomic_numbers=(1, 1),
            coordinates=ArrayData(
                array_view(range(6), (2, 3)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        frames = FrameSet(
            id=uuid4(),
            revision="f1",
            semantic_role="coordinates",
            domain="frame",
            data=ArrayData(
                array_view(range(12), (2, 2, 3)),
                ("frame", "atom", "xyz"),
                "angstrom",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure.id,
            comments=("first", "second"),
        )
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(ImportBatch(structures=(structure,), datasets=(frames,)))
        self.assertIs(project.datasets[frames.id], frames)

    def test_frame_set_rejects_invalid_shape_and_comments(self):
        common = {
            "id": uuid4(),
            "revision": "f1",
            "semantic_role": "coordinates",
            "domain": "frame",
            "status": DatasetStatus.COMPLETE,
            "source_calculation": None,
            "provenance_ids": (),
            "structure_id": uuid4(),
        }
        with self.assertRaises(ValueError):
            FrameSet(
                data=ArrayData(
                    array_view(range(6), (2, 3)),
                    ("atom", "xyz"),
                    "angstrom",
                ),
                comments=("first",),
                **common,
            )
        with self.assertRaises(ValueError):
            FrameSet(
                data=ArrayData(
                    array_view(range(6), (2, 1, 3)),
                    ("frame", "atom", "xyz"),
                    "angstrom",
                ),
                comments=("only one",),
                **common,
            )

    def test_project_rejects_invalid_frame_set_reference_atomically(self):
        frames = FrameSet(
            id=uuid4(),
            revision="f1",
            semantic_role="coordinates",
            domain="frame",
            data=ArrayData(
                array_view(range(6), (2, 1, 3)),
                ("frame", "atom", "xyz"),
                "angstrom",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=uuid4(),
            comments=("first", "second"),
        )
        project = QCProject(id=uuid4(), schema_version="0.1")
        with self.assertRaises(ValueError):
            project.commit(ImportBatch(datasets=(frames,)))
        self.assertEqual(project.datasets, {})

    def test_project_rejects_frame_set_atom_and_unit_mismatch(self):
        structure = Structure(
            id=uuid4(),
            revision="s1",
            atomic_numbers=(1, 1),
            coordinates=ArrayData(
                array_view(range(6), (2, 3)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        for atom_count, unit in ((1, "angstrom"), (2, "bohr")):
            with self.subTest(atom_count=atom_count, unit=unit):
                frames = FrameSet(
                    id=uuid4(),
                    revision="f1",
                    semantic_role="coordinates",
                    domain="frame",
                    data=ArrayData(
                        array_view(
                            range(2 * atom_count * 3),
                            (2, atom_count, 3),
                        ),
                        ("frame", "atom", "xyz"),
                        unit,
                    ),
                    status=DatasetStatus.COMPLETE,
                    source_calculation=None,
                    provenance_ids=(),
                    structure_id=structure.id,
                    comments=("first", "second"),
                )
                project = QCProject(id=uuid4(), schema_version="0.1")
                with self.assertRaises(ValueError):
                    project.commit(
                        ImportBatch(
                            structures=(structure,),
                            datasets=(frames,),
                        )
                    )
                self.assertEqual(project.structures, {})
                self.assertEqual(project.datasets, {})

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
