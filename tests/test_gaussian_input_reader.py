from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from ChemBlender.core import CapabilitySupport, IssueKind, QCProject, ReaderRegistry, SniffMatch
from ChemBlender.core.formats.gaussian_input import (
    GAUSSIAN_INPUT_READER,
    parse_gaussian_input,
    sniff_gaussian_input,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "gaussian" / "water.gjf"


class GaussianInputReaderTests(unittest.TestCase):
    def parse_bytes(self, content, suffix=".gjf"):
        with TemporaryDirectory() as directory:
            source = Path(directory) / f"input{suffix}"
            source.write_bytes(content)
            return parse_gaussian_input(source)

    def assert_rejected(self, content, message):
        with self.assertRaisesRegex(ValueError, message):
            self.parse_bytes(content)

    def test_sniff_and_registry_select_complete_cartesian_input(self):
        content = FIXTURE.read_bytes()
        self.assertEqual(
            sniff_gaussian_input(FIXTURE, content).match,
            SniffMatch.EXACT,
        )
        with TemporaryDirectory() as directory:
            source = Path(directory) / "water.data"
            source.write_bytes(content)
            self.assertIs(
                ReaderRegistry((GAUSSIAN_INPUT_READER,)).select(source),
                GAUSSIAN_INPUT_READER,
            )

    def test_sniff_recognizes_truncated_named_input(self):
        content = b"%chk=water.chk\n#p hf/sto-3g\n\nwater\n"
        for suffix in (".gjf", ".com"):
            with self.subTest(suffix=suffix):
                self.assertEqual(
                    sniff_gaussian_input(Path(f"water{suffix}"), content).match,
                    SniffMatch.PROBABLE,
                )

    def test_parse_normalizes_structure_charge_and_provenance(self):
        batch = parse_gaussian_input(FIXTURE)
        structure, = batch.structures
        provenance, = batch.provenance

        self.assertEqual(structure.atomic_numbers, (8, 1, 1))
        self.assertEqual(structure.coordinates.shape, (3, 3))
        self.assertEqual(structure.coordinates.dims, ("atom", "xyz"))
        self.assertEqual(structure.coordinates.unit, "angstrom")
        self.assertEqual(structure.molecular_charge, 0)
        self.assertEqual(structure.molecular_multiplicity, 1)
        self.assertAlmostEqual(structure.coordinates.values[1, 0], 0.758602)
        self.assertEqual(len(provenance.source_hash), 64)
        self.assertEqual(
            dict(provenance.parameters),
            {
                "coordinate_mode": "cartesian",
                "format": "gaussian-input",
                "title": "water",
            },
        )
        self.assertEqual(batch.report.parsed_capabilities, ("structure",))
        self.assertEqual(
            set(batch.report.created_entity_ids),
            {structure.id, provenance.id},
        )

        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(batch)
        self.assertIn(structure.id, project.structures)

    def test_descriptor_is_dependency_free_structure_reader(self):
        self.assertEqual(
            GAUSSIAN_INPUT_READER.extensions,
            (".gjf", ".com"),
        )
        self.assertEqual(
            GAUSSIAN_INPUT_READER.capabilities,
            {"structure": CapabilitySupport.SUPPORTED},
        )

    def test_charge_multiplicity_and_isotope_warning(self):
        batch = self.parse_bytes(
            b"#p uhf/sto-3g\n\nradical\n\n-1 2\nD 0 0 0\nT 1 0 0\n\n"
        )
        structure, = batch.structures
        self.assertEqual(structure.atomic_numbers, (1, 1))
        self.assertEqual(structure.molecular_charge, -1)
        self.assertEqual(structure.molecular_multiplicity, 2)
        self.assertTrue(
            any(issue.kind is IssueKind.WARNING for issue in batch.report.issues)
        )

    def test_trailing_basis_section_does_not_change_structure(self):
        batch = self.parse_bytes(
            b"#p hf/gen\n\ncustom basis\n\n0 1\nH 0 0 0\nH 0 0 1\n\n"
            b"H 0\nSTO-3G\n****\n"
        )
        self.assertEqual(batch.structures[0].atomic_numbers, (1, 1))
        self.assertEqual(batch.report.issues, ())

    def test_rejects_missing_sections(self):
        cases = (
            (b"title\n\n0 1\nH 0 0 0\n", "route"),
            (b"#p hf/sto-3g\n\n\n0 1\nH 0 0 0\n", "title"),
            (b"#p hf/sto-3g\n\ntitle\n\nH 0 0 0\n", "charge"),
            (b"#p hf/sto-3g\n\ntitle\n\n0 1\n", "coordinate"),
        )
        for content, message in cases:
            with self.subTest(message=message):
                self.assert_rejected(content, message)

    def test_rejects_invalid_charge_atoms_and_coordinates(self):
        cases = (
            (b"#p hf/sto-3g\n\ntitle\n\n0 0\nH 0 0 0\n", "multiplicity"),
            (b"#p hf/sto-3g\n\ntitle\n\n0 1\nNoSuch 0 0 0\n", "element"),
            (b"#p hf/sto-3g\n\ntitle\n\n0 1\nH nan 0 0\n", "finite"),
            (b"#p hf/sto-3g\n\ntitle\n\n0 1\nH 0 0 0 layer\n", "four fields"),
        )
        for content, message in cases:
            with self.subTest(message=message):
                self.assert_rejected(content, message)

    def test_legacy_pseudo_symbols_are_recognized_but_rejected(self):
        for symbol in (b"Vac", b"Default", b"Bond"):
            with self.subTest(symbol=symbol):
                content = (
                    b"#p hf/sto-3g\n\ntitle\n\n0 1\n"
                    + symbol
                    + b" 0 0 0\n"
                )
                self.assertEqual(
                    sniff_gaussian_input(Path("pseudo.gjf"), content).match,
                    SniffMatch.PROBABLE,
                )
                self.assert_rejected(content, "element")

    def test_rejects_complex_or_ambiguous_geometry(self):
        cases = (
            (
                b"#p hf/sto-3g\n\nzmatrix\n\n0 1\nO\nH 1 R\n\nR=1.0\n",
                "four fields",
            ),
            (
                b"#p opt hf/sto-3g\n\nfrozen\n\n0 1\nH 0 0 0 0\n",
                "four fields",
            ),
            (
                FIXTURE.read_bytes() + b"--Link1--\n#p hf/sto-3g\n",
                "Link1",
            ),
            (
                b"#p oniom(hf/sto-3g:hf/sto-3g)\n\n"
                b"oniom\n\n0 1\nH 0 0 0\n",
                "ONIOM",
            ),
            (
                b"#p hf/sto-3g\n\nmultiple\n\n0 1\nH 0 0 0\n\n"
                b"O 1 0 0\n",
                "multiple",
            ),
        )
        for content, message in cases:
            with self.subTest(message=message):
                self.assert_rejected(content, message)


if __name__ == "__main__":
    unittest.main()
