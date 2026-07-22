import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy

from ChemBlender.core import IssueKind, QCProject, SniffMatch
from ChemBlender.core.pymatgen_adapter import (
    PYMATGEN_VASP_GRID_READER,
    PymatgenDependencyError,
    adapt_vasp_volumetric,
    parse_vasp_volumetric,
    sniff_vasp_volumetric,
)


ROOT = Path(__file__).resolve().parents[1]
HAS_PYMATGEN = importlib.util.find_spec("pymatgen") is not None


@unittest.skipUnless(HAS_PYMATGEN, "pymatgen-core dependency is unavailable")
class PymatgenIntegrationTests(unittest.TestCase):
    @staticmethod
    def structure():
        from pymatgen.core import Lattice, Structure

        return Structure(
            Lattice([[4.0, 0.0, 0.0], [1.0, 3.0, 0.0], [0.0, 0.5, 5.0]]),
            ["Si", "O"],
            [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]],
        )

    def test_chgcar_normalizes_density_and_preserves_spin_and_affine_grid(self):
        from pymatgen.io.vasp import Chgcar

        shape = (2, 3, 4)
        total = numpy.full(shape, 2.5)
        diff = numpy.full(shape, 0.5)
        volume = Chgcar(
            self.structure(),
            {"total": total, "diff": diff},
            data_aug={"total": {1: numpy.asarray([1.0])}},
        )
        batch = adapt_vasp_volumetric(volume, source_kind="chgcar")
        structure = batch.structures[0]
        grids = {grid.semantic_role: grid for grid in batch.datasets}
        self.assertEqual(set(grids), {"electron_density", "spin_density"})
        density = grids["electron_density"]
        self.assertEqual(density.structure_id, structure.id)
        self.assertEqual(density.data.unit, "inverse_cubic_angstrom")
        self.assertTrue(numpy.allclose(density.data.values, total / 60.0))
        integrated = density.data.values.mean() * 60.0
        self.assertAlmostEqual(integrated, 2.5)
        self.assertTrue(
            numpy.allclose(
                density.step_vectors,
                [[2.0, 0.0, 0.0], [1.0 / 3.0, 1.0, 0.0], [0.0, 0.125, 1.25]],
            )
        )
        unsupported = {
            issue.path
            for issue in batch.report.issues
            if issue.kind is IssueKind.UNSUPPORTED
        }
        self.assertEqual(unsupported, {"volumetric_data.augmentation"})
        QCProject(id=structure.id, schema_version="0.1").commit(batch)

    def test_parchg_uses_partial_density_semantics(self):
        from pymatgen.io.vasp import Chgcar

        values = numpy.ones((2, 2, 2))
        batch = adapt_vasp_volumetric(
            Chgcar(self.structure(), {"total": values, "diff": values * 0.1}),
            source_kind="parchg",
        )
        self.assertEqual(
            {grid.semantic_role for grid in batch.datasets},
            {"partial_charge_density", "partial_spin_density"},
        )

    def test_elfcar_spin_keys_are_channels_not_total_and_difference(self):
        from pymatgen.io.vasp import Elfcar

        alpha = numpy.full((2, 2, 2), 0.8)
        beta = numpy.full((2, 2, 2), 0.6)
        batch = adapt_vasp_volumetric(
            Elfcar(self.structure(), {"total": alpha, "diff": beta}),
            source_kind="elfcar",
        )
        grids = {grid.semantic_role: grid for grid in batch.datasets}
        self.assertEqual(
            set(grids),
            {
                "electron_localization_function_alpha",
                "electron_localization_function_beta",
            },
        )
        self.assertTrue(
            numpy.array_equal(
                grids["electron_localization_function_beta"].data.values, beta
            )
        )
        self.assertEqual(
            grids["electron_localization_function_alpha"].data.unit,
            "dimensionless",
        )

    def test_locpot_two_and_four_component_semantics(self):
        from pymatgen.io.vasp import Locpot

        shape = (2, 2, 2)
        two = adapt_vasp_volumetric(
            Locpot(
                self.structure(),
                {"total": numpy.ones(shape), "diff": numpy.ones(shape) * 2},
            ),
            source_kind="locpot",
        )
        self.assertEqual(
            {grid.semantic_role for grid in two.datasets},
            {"local_potential_alpha", "local_potential_beta"},
        )
        four = adapt_vasp_volumetric(
            Locpot(
                self.structure(),
                {
                    "total": numpy.ones(shape),
                    "diff_x": numpy.ones(shape) * 2,
                    "diff_y": numpy.ones(shape) * 3,
                    "diff_z": numpy.ones(shape) * 4,
                    "diff": numpy.ones(shape) * 9,
                },
            ),
            source_kind="locpot",
        )
        self.assertEqual(
            {grid.semantic_role for grid in four.datasets},
            {
                "local_potential",
                "magnetic_potential_x",
                "magnetic_potential_y",
                "magnetic_potential_z",
            },
        )
        self.assertTrue(all(grid.data.unit == "electron_volt" for grid in four.datasets))

    def test_real_chgcar_roundtrip_parser(self):
        from pymatgen.io.vasp import Chgcar

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "CHGCAR"
            Chgcar(
                self.structure(), {"total": numpy.arange(8.0).reshape((2, 2, 2))}
            ).write_file(source)
            self.assertIs(
                sniff_vasp_volumetric(source, source.read_bytes()).match,
                SniffMatch.EXACT,
            )
            batch = parse_vasp_volumetric(source)
            self.assertEqual(batch.datasets[0].semantic_role, "electron_density")
            self.assertEqual(batch.report.reader_id, "pymatgen-vasp-grid")


class PymatgenAdapterTests(unittest.TestCase):
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

    def test_reader_descriptor(self):
        self.assertEqual(PYMATGEN_VASP_GRID_READER.reader_id, "pymatgen-vasp-grid")
        self.assertEqual(
            set(PYMATGEN_VASP_GRID_READER.capabilities),
            {"structure", "crystal", "grid"},
        )

    def test_parse_reports_missing_dependency(self):
        if HAS_PYMATGEN:
            self.skipTest("pymatgen-core is installed in this interpreter")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "CHGCAR"
            source.write_bytes(b"placeholder")
            with self.assertRaises(PymatgenDependencyError):
                parse_vasp_volumetric(source)


if __name__ == "__main__":
    unittest.main()
