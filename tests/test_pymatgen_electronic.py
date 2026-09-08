import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import EnergyReference, IssueKind, QCProject, SniffMatch
from ChemBlender.core.pymatgen_electronic import (
    PYMATGEN_VASP_ELECTRONIC_READER,
    PymatgenElectronicDependencyError,
    adapt_pymatgen_electronic,
    parse_vasprun_electronic,
    sniff_vasprun,
    _band_occupations,
)


ROOT = Path(__file__).resolve().parents[1]
HAS_PYMATGEN = importlib.util.find_spec("pymatgen") is not None


@unittest.skipUnless(HAS_PYMATGEN, "pymatgen-core dependency is unavailable")
class PymatgenElectronicIntegrationTests(unittest.TestCase):
    def setUp(self):
        from pymatgen.core import Lattice, Structure

        self.structure = Structure(
            Lattice.cubic(4.0),
            ["Si", "O"],
            [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]],
        )

    def band_structure(self, projected=True):
        from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
        from pymatgen.electronic_structure.core import Spin

        bands = {
            Spin.up: numpy.asarray([[4.0, 4.5, 5.0], [6.0, 6.5, 7.0]]),
            Spin.down: numpy.asarray([[4.1, 4.6, 5.1], [6.1, 6.6, 7.1]]),
        }
        projections = None
        if projected:
            projections = {
                Spin.up: numpy.arange(24.0).reshape((2, 3, 2, 2)),
                Spin.down: numpy.arange(24.0, 48.0).reshape((2, 3, 2, 2)),
            }
        reciprocal = self.structure.lattice.reciprocal_lattice
        return BandStructureSymmLine(
            [[0.0, 0.0, 0.0], [0.25, 0.0, 0.0], [0.5, 0.0, 0.0]],
            bands,
            reciprocal,
            5.5,
            {"GAMMA": [0.0, 0.0, 0.0], "X": [0.5, 0.0, 0.0]},
            structure=self.structure,
            projections=projections,
        )

    def complete_dos(self, normalize=False):
        from pymatgen.electronic_structure.core import Orbital, Spin
        from pymatgen.electronic_structure.dos import CompleteDos, Dos

        energies = numpy.asarray([-1.0, 0.0, 1.0])
        total = Dos(
            0.25,
            energies,
            {Spin.up: [1.0, 2.0, 3.0], Spin.down: [0.5, 1.0, 1.5]},
        )
        pdos = {
            self.structure[0]: {
                Orbital.s: {Spin.up: [0.1, 0.2, 0.3], Spin.down: [0.05, 0.1, 0.15]},
            },
            self.structure[1]: {
                Orbital.py: {Spin.up: [0.4, 0.5, 0.6], Spin.down: [0.2, 0.25, 0.3]},
            },
        }
        return CompleteDos(self.structure, total, pdos, normalize=normalize)

    def test_band_and_dos_share_structure_and_preserve_axes(self):
        from pymatgen.electronic_structure.core import Spin

        occupations = {
            Spin.up: numpy.asarray([[1.0, 1.0, 0.5], [0.0, 0.0, 0.0]]),
            Spin.down: numpy.asarray([[1.0, 1.0, 0.0], [0.0, 0.0, 0.0]]),
        }
        batch = adapt_pymatgen_electronic(
            band_structure=self.band_structure(),
            complete_dos=self.complete_dos(),
            occupations=occupations,
        )
        structure = batch.structures[0]
        band, dos = batch.datasets
        self.assertEqual(band.structure_id, structure.id)
        self.assertEqual(dos.structure_id, structure.id)
        self.assertEqual(band.data.shape, (2, 3, 2))
        self.assertEqual(band.occupations.shape, band.data.shape)
        self.assertEqual(band.projections.shape, (2, 3, 2, 2, 2))
        self.assertEqual(band.orbital_labels, ("s", "py"))
        self.assertEqual(band.labels, ("GAMMA", None, "X"))
        self.assertEqual((band.branches[0].start_label, band.branches[0].end_label), ("GAMMA", "X"))
        self.assertEqual(band.energy_reference, EnergyReference.ABSOLUTE)
        self.assertEqual(dos.projections.shape, (2, 3, 2, 2))
        self.assertEqual(dos.orbital_labels, ("s", "py"))
        self.assertTrue(numpy.allclose(dos.projections.values[0, :, 0, 1], 0.0))
        QCProject(id=structure.id, schema_version="0.1").commit(batch)

    def test_real_silicon_line_mode_and_dos_remain_separate(self):
        folder = ROOT / "examples/scientific-visualization/inputs/silicon"
        batch = parse_vasprun_electronic(folder / "bands/vasprun.xml.gz",
            kpoints_filename=folder / "bands/KPOINTS", line_mode=True)
        band = batch.datasets[0]
        self.assertEqual(band.data.shape[1], 160)
        self.assertTrue(band.branches)
        self.assertTrue(any(band.labels))
        self.assertEqual(band.occupations.shape, band.data.shape)
        self.assertTrue(dict(batch.provenance[-1].parameters)["line_mode_resolved"])
        self.assertEqual(batch.provenance[0].operation, "read_kpoints")
        dos_batch = parse_vasprun_electronic(folder / "dos/vasprun.xml.gz")
        self.assertFalse(dos_batch.datasets[0].branches)
        self.assertNotEqual(batch.structures[0].id, dos_batch.structures[0].id)
        self.assertNotEqual(band.revision, dos_batch.datasets[0].revision)
        QCProject(id=batch.structures[0].id, schema_version="0.1").commit(batch)

    def test_missing_optional_band_arrays_are_reported(self):
        batch = adapt_pymatgen_electronic(band_structure=self.band_structure(False))
        missing = {
            issue.path for issue in batch.report.issues if issue.kind is IssueKind.MISSING
        }
        self.assertEqual(missing, {"band_structure.occupations", "band_structure.projections"})

    def test_normalized_complete_dos_normalizes_pdos_too(self):
        batch = adapt_pymatgen_electronic(complete_dos=self.complete_dos(True))
        dos = batch.datasets[0]
        self.assertEqual(dos.data.unit, "states_per_electron_volt_per_cubic_angstrom")
        self.assertAlmostEqual(dos.projections.values[0, 0, 0, 0], 0.1 / 64.0)


class PymatgenElectronicAdapterTests(unittest.TestCase):
    def test_occupations_follow_opt_and_hybrid_suffix_without_guessing_order(self):
        raw = SimpleNamespace(
            actual_kpoints=[[0, 0, 0], [.25, 0, 0], [.5, 0, 0]],
            eigenvalues={1: numpy.asarray([[[1, 1]], [[2, .5]], [[3, 0]]])},
        )
        band = SimpleNamespace(
            kpoints=[SimpleNamespace(frac_coords=point) for point in raw.actual_kpoints[1:]],
            bands={1: numpy.asarray([[2, 3]])},
        )
        result = SimpleNamespace(kpoints_opt_props=raw, actual_kpoints=[], eigenvalues={})
        self.assertEqual(_band_occupations(result, band)[1].tolist(), [[.5, 0]])
        self.assertEqual(_band_occupations(raw, band)[1].tolist(), [[.5, 0]])
        band.kpoints.reverse()
        with self.assertRaisesRegex(ValueError, "k-point order"):
            _band_occupations(result, band)
        band.kpoints.reverse()
        band.bands[1][0, 0] = 99
        with self.assertRaisesRegex(ValueError, "energies"):
            _band_occupations(result, band)

    def test_file_parser_tracks_companion_revision_and_rejects_mid_parse_change(self):
        from ChemBlender.core import ImportBatch, ParserReport, ProvenanceRecord
        point = SimpleNamespace(frac_coords=(0, 0, 0))
        band = SimpleNamespace(kpoints=[point], bands={1: numpy.asarray([[1.]])}, branches=("G-X",))
        class Result:
            kpoints_opt_props = None
            actual_kpoints = [(0, 0, 0)]
            eigenvalues = {1: numpy.asarray([[[1., 1.]]])}
            complete_dos = object()
            def get_band_structure(self, **kwargs):
                self.arguments = kwargs
                return band
        result = Result()
        def adapt(**kwargs):
            record = ProvenanceRecord(id=uuid4(), revision="raw", producer="test",
                producer_version="1", source=kwargs["source"],
                source_hash=__import__("hashlib").sha256(kwargs["source_bytes"]).hexdigest(),
                parent_ids=(), operation="normalize", parameters=())
            return ImportBatch(provenance=(record,), report=ParserReport(
                reader_id="test", reader_version="1", created_entity_ids=(record.id,),
                parsed_capabilities=(), issues=()))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "vasprun.xml"
            source.write_bytes(b"<modeling/>")
            companion = folder / "KPOINTS"
            companion.write_bytes(b"G-X")
            with patch("ChemBlender.core.pymatgen_electronic._pymatgen_electronic",
                       return_value=(lambda *args, **kwargs: result,)), patch(
                       "ChemBlender.core.pymatgen_electronic.adapt_pymatgen_electronic", side_effect=adapt):
                first = parse_vasprun_electronic(source, line_mode=True)
                self.assertEqual(result.arguments, {"kpoints_filename": str(companion), "line_mode": True})
                companion.write_bytes(b"G-L")
                second = parse_vasprun_electronic(source, line_mode=True)
                self.assertNotEqual(first.provenance[-1].revision, second.provenance[-1].revision)
                self.assertEqual(first.provenance[-1].source_hash, second.provenance[-1].source_hash)
                self.assertEqual(second.provenance[-1].parent_ids, (second.provenance[0].id,))
            def changing_adapt(**kwargs):
                companion.write_bytes(b"changed while parsing")
                return adapt(**kwargs)
            with patch("ChemBlender.core.pymatgen_electronic._pymatgen_electronic",
                       return_value=(lambda *args, **kwargs: result,)), patch(
                       "ChemBlender.core.pymatgen_electronic.adapt_pymatgen_electronic", side_effect=changing_adapt):
                with self.assertRaisesRegex(ValueError, "input changed"):
                    parse_vasprun_electronic(source)

    def test_line_mode_preflight_and_compressed_name(self):
        with self.assertRaisesRegex(TypeError, "line_mode"):
            parse_vasprun_electronic("missing", line_mode="true")
        self.assertIs(sniff_vasprun(Path("vasprun.xml.gz"), b"compressed").match,
            SniffMatch.POSSIBLE)

    def test_core_import_does_not_eagerly_load_pymatgen(self):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import ChemBlender.core; assert 'pymatgen' not in sys.modules",
            ],
            cwd=ROOT,
            check=True,
        )

    def test_reader_descriptor_and_sniffing(self):
        self.assertEqual(PYMATGEN_VASP_ELECTRONIC_READER.reader_id, "pymatgen-vasprun-electronic")
        self.assertEqual(
            set(PYMATGEN_VASP_ELECTRONIC_READER.capabilities),
            {"structure", "band_structure", "dos", "projection"},
        )
        self.assertIs(
            sniff_vasprun(Path("vasprun.xml"), b"<modeling><generator><i name='program'>vasp</i>").match,
            SniffMatch.EXACT,
        )

    def test_parse_reports_missing_dependency(self):
        if HAS_PYMATGEN:
            self.skipTest("pymatgen-core is installed in this interpreter")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "vasprun.xml"
            source.write_text("<modeling/>", encoding="utf-8")
            with self.assertRaises(PymatgenElectronicDependencyError):
                parse_vasprun_electronic(source)


if __name__ == "__main__":
    unittest.main()
