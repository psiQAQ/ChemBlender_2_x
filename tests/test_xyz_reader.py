from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from ChemBlender.core import (
    CapabilitySupport,
    FrameSet,
    IssueKind,
    QCProject,
    ReaderRegistry,
    SniffMatch,
    XYZ_READER,
)
from ChemBlender.core.xyz import sniff_xyz


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "xyz" / "water.xyz"
TRAJECTORY_FIXTURE = (
    ROOT / "tests" / "fixtures" / "xyz" / "water-trajectory.xyz"
)


class XYZReaderTests(unittest.TestCase):
    def test_sniff_recognizes_complete_xyz_content(self):
        result = sniff_xyz(FIXTURE, FIXTURE.read_bytes())
        self.assertEqual(result.match, SniffMatch.EXACT)

    def test_sniff_rejects_non_xyz_content(self):
        result = sniff_xyz(Path("bad.xyz"), b"not-an-atom-count\n")
        self.assertEqual(result.match, SniffMatch.NONE)

    def test_registry_selects_xyz_by_content_with_wrong_extension(self):
        registry = ReaderRegistry((XYZ_READER,))
        with TemporaryDirectory() as directory:
            source = Path(directory) / "water.data"
            source.write_bytes(FIXTURE.read_bytes())
            self.assertIs(registry.select(source), XYZ_READER)

    def test_parse_normalizes_structure_and_provenance(self):
        batch = XYZ_READER.parse(FIXTURE)
        self.assertEqual(len(batch.structures), 1)
        structure = batch.structures[0]
        self.assertEqual(structure.atomic_numbers, (8, 1, 1))
        self.assertEqual(structure.coordinates.shape, (3, 3))
        self.assertEqual(structure.coordinates.dims, ("atom", "xyz"))
        self.assertEqual(structure.coordinates.unit, "angstrom")
        self.assertEqual(len(batch.provenance), 1)
        self.assertEqual(len(batch.provenance[0].source_hash), 64)
        self.assertEqual(
            dict(batch.provenance[0].parameters)["comment"],
            "water",
        )
        self.assertEqual(
            set(batch.report.created_entity_ids),
            {structure.id, batch.provenance[0].id},
        )

    def test_parse_normalizes_multi_frame_xyz(self):
        batch = XYZ_READER.parse(TRAJECTORY_FIXTURE)
        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(len(batch.datasets), 1)
        frames = batch.datasets[0]
        self.assertIsInstance(frames, FrameSet)
        self.assertEqual(frames.structure_id, batch.structures[0].id)
        self.assertEqual(frames.data.shape, (2, 3, 3))
        self.assertEqual(frames.comments, ("frame 0", "frame 1"))
        self.assertAlmostEqual(frames.data.values[1, 0, 0], 0.1)
        self.assertIn("trajectory", batch.report.parsed_capabilities)
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(batch)

    def test_single_frame_does_not_create_frame_set(self):
        batch = XYZ_READER.parse(FIXTURE)
        self.assertEqual(batch.datasets, ())
        self.assertEqual(batch.report.parsed_capabilities, ("structure",))

    def test_parsed_batch_commits_to_project(self):
        batch = ReaderRegistry((XYZ_READER,)).parse(FIXTURE)
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(batch)
        self.assertEqual(len(project.structures), 1)
        self.assertEqual(len(project.provenance), 1)

    def test_parse_rejects_invalid_symbol_and_nonfinite_coordinate(self):
        cases = (
            b"1\nbad\nNoSuch 0 0 0\n",
            b"1\nbad\nH nan 0 0\n",
        )
        for content in cases:
            with self.subTest(content=content):
                with TemporaryDirectory() as directory:
                    source = Path(directory) / "bad.xyz"
                    source.write_bytes(content)
                    with self.assertRaises(ValueError):
                        XYZ_READER.parse(source)

    def test_extra_columns_are_reported_for_multi_frame_xyz(self):
        content = b"1\nfirst\nH 0 0 0 charge=0\n1\nsecond\nH 1 0 0\n"
        with TemporaryDirectory() as directory:
            source = Path(directory) / "extra.xyz"
            source.write_bytes(content)
            batch = XYZ_READER.parse(source)
        issues = {issue.path: issue.kind for issue in batch.report.issues}
        self.assertEqual(
            issues,
            {
                "atom_properties": IssueKind.UNSUPPORTED,
            },
        )

    def test_multi_frame_rejects_changed_atoms_and_truncation(self):
        cases = (
            b"1\nfirst\nH 0 0 0\n1\nsecond\nO 1 0 0\n",
            b"1\nfirst\nH 0 0 0\n2\nsecond\nH 1 0 0\n",
        )
        for content in cases:
            with self.subTest(content=content):
                with TemporaryDirectory() as directory:
                    source = Path(directory) / "bad.xyz"
                    source.write_bytes(content)
                    with self.assertRaises(ValueError):
                        XYZ_READER.parse(source)

    def test_xyz_descriptor_supports_trajectory(self):
        self.assertIs(
            XYZ_READER.capabilities["trajectory"],
            CapabilitySupport.SUPPORTED,
        )

    def test_isotope_symbols_map_to_hydrogen_with_warning(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "isotopes.xyz"
            source.write_bytes(b"2\nisotopes\nD 0 0 0\nT 1 0 0\n")
            batch = XYZ_READER.parse(source)
        self.assertEqual(batch.structures[0].atomic_numbers, (1, 1))
        self.assertTrue(
            any(issue.kind is IssueKind.WARNING for issue in batch.report.issues)
        )


if __name__ == "__main__":
    unittest.main()
