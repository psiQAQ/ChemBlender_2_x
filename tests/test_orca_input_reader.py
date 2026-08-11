from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from ChemBlender.core import CapabilitySupport, IssueKind, QCProject, ReaderRegistry, SniffMatch
from ChemBlender.core.formats.gaussian_input import parse_gaussian_input
from ChemBlender.core.formats.orca_input import (
    ORCA_INPUT_READER,
    parse_orca_input,
    sniff_orca_input,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "orca" / "water.inp"
GAUSSIAN_FIXTURE = ROOT / "tests" / "fixtures" / "gaussian" / "water.gjf"


class OrcaInputReaderTests(unittest.TestCase):
    def parse_bytes(self, content, suffix=".inp"):
        with TemporaryDirectory() as directory:
            source = Path(directory) / f"input{suffix}"
            source.write_bytes(content)
            return parse_orca_input(source)

    def assert_rejected(self, content, message):
        with self.assertRaisesRegex(ValueError, message):
            self.parse_bytes(content)

    def test_sniff_selects_inline_xyz_and_rejects_generic_inp(self):
        content = FIXTURE.read_bytes()
        self.assertEqual(
            sniff_orca_input(FIXTURE, content).match,
            SniffMatch.EXACT,
        )
        self.assertEqual(
            sniff_orca_input(Path("script.inp"), b"ordinary input text\n").match,
            SniffMatch.NONE,
        )
        with TemporaryDirectory() as directory:
            source = Path(directory) / "water.data"
            source.write_bytes(content)
            self.assertIs(
                ReaderRegistry((ORCA_INPUT_READER,)).select(source),
                ORCA_INPUT_READER,
            )

    def test_parse_normalizes_structure_and_matches_gaussian(self):
        batch = parse_orca_input(FIXTURE)
        structure, = batch.structures
        gaussian = parse_gaussian_input(GAUSSIAN_FIXTURE).structures[0]

        self.assertEqual(structure.atomic_numbers, gaussian.atomic_numbers)
        self.assertEqual(structure.coordinates.shape, (3, 3))
        self.assertEqual(structure.coordinates.dims, ("atom", "xyz"))
        self.assertEqual(structure.coordinates.unit, "angstrom")
        self.assertEqual(
            structure.coordinates.values.tolist(),
            gaussian.coordinates.values.tolist(),
        )
        self.assertEqual(structure.molecular_charge, 0)
        self.assertEqual(structure.molecular_multiplicity, 1)
        provenance, = batch.provenance
        self.assertEqual(len(provenance.source_hash), 64)
        self.assertEqual(
            dict(provenance.parameters),
            {
                "coordinate_mode": "cartesian",
                "format": "orca-input",
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
        self.assertEqual(ORCA_INPUT_READER.extensions, (".inp",))
        self.assertEqual(
            ORCA_INPUT_READER.capabilities,
            {"structure": CapabilitySupport.SUPPORTED},
        )

    def test_charge_multiplicity_and_isotope_warning(self):
        batch = self.parse_bytes(
            b"! UHF\n* xyz -1 2\nD 0 0 0\nT 1 0 0\n*\n"
        )
        structure, = batch.structures
        self.assertEqual(structure.atomic_numbers, (1, 1))
        self.assertEqual(structure.molecular_charge, -1)
        self.assertEqual(structure.molecular_multiplicity, 2)
        self.assertTrue(
            any(issue.kind is IssueKind.WARNING for issue in batch.report.issues)
        )

    def test_xyzfile_is_recognized_but_rejected(self):
        content = b"! HF STO-3G\n* xyzfile 0 1 water.xyz\n"
        self.assertEqual(
            sniff_orca_input(Path("water.inp"), content).match,
            SniffMatch.PROBABLE,
        )
        self.assert_rejected(content, "xyzfile")

    def test_internal_coordinates_are_recognized_but_rejected(self):
        internal = b"! HF\n* int 0 1\nH 0 0 0 0 0 0\n*\n"
        self.assertEqual(
            sniff_orca_input(Path("water.inp"), internal).match,
            SniffMatch.PROBABLE,
        )
        self.assert_rejected(internal, "internal")
        self.assert_rejected(
            b"* xyz 0 1\nH 0 0 0\n*\n"
            b"* int 0 1\nH 0 0 0 0 0 0\n*\n",
            "internal",
        )

    def test_rejects_incomplete_or_multiple_blocks(self):
        cases = (
            (b"! HF\n* xyz 0 1\nH 0 0 0\n", "terminated"),
            (b"! HF\n* xyz 0 1\n*\n", "empty"),
            (
                b"* xyz 0 1\nH 0 0 0\n*\n* xyz 0 1\nH 1 0 0\n*\n",
                "multiple",
            ),
            (b"! HF\n* xyz 0 0\nH 0 0 0\n*\n", "multiplicity"),
        )
        for content, message in cases:
            with self.subTest(message=message):
                self.assert_rejected(content, message)

    def test_rejects_invalid_atoms_and_coordinates(self):
        cases = (
            (b"* xyz 0 1\nNoSuch 0 0 0\n*\n", "element"),
            (b"* xyz 0 1\nH inf 0 0\n*\n", "finite"),
            (b"* xyz 0 1\nH 0 0 0 extra\n*\n", "four fields"),
        )
        for content, message in cases:
            with self.subTest(message=message):
                self.assert_rejected(content, message)

    def test_legacy_pseudo_symbols_are_recognized_but_rejected(self):
        for symbol in (b"Vac", b"Default", b"Bond"):
            with self.subTest(symbol=symbol):
                content = b"* xyz 0 1\n" + symbol + b" 0 0 0\n*\n"
                self.assertEqual(
                    sniff_orca_input(Path("pseudo.inp"), content).match,
                    SniffMatch.PROBABLE,
                )
                self.assert_rejected(content, "element")


if __name__ == "__main__":
    unittest.main()
