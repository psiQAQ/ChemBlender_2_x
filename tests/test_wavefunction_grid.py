import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    BasisConvention,
    BasisFunctionKind,
    BasisSet,
    BasisShell,
    ImportBatch,
    OrbitalChannel,
    OrbitalKind,
    OrbitalSet,
    QCProject,
    Structure,
    evaluate_electron_density_grid,
    evaluate_molecular_orbital_grid,
)
from ChemBlender.core.wavefunction_grid import _basis_function_signs


ROOT = Path(__file__).resolve().parents[1]
FCHK = (
    ROOT
    / "submodules"
    / "iodata"
    / "iodata"
    / "test"
    / "data"
    / "water_sto3g_hf_g03.fchk"
)
PURE_FCHK = FCHK.with_name("water_ccpvdz_pure_hf_g03.fchk")
HAS_INTEGRATION = (
    importlib.util.find_spec("gbasis") is not None
    and importlib.util.find_spec("iodata") is not None
    and FCHK.is_file()
    and PURE_FCHK.is_file()
)


def entities(kind=OrbitalKind.RESTRICTED, *, occupations=True):
    revision = "a" * 64
    structure = Structure(
        id=uuid4(),
        revision=revision,
        atomic_numbers=(1,),
        coordinates=ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0]]), ("atom", "xyz"), "bohr"
        ),
    )
    basis = BasisSet(
        id=uuid4(),
        revision=revision,
        structure_id=structure.id,
        name="minimal",
        shells=(
            BasisShell(
                center_atom=0,
                angular_momenta=(0,),
                kinds=(BasisFunctionKind.CARTESIAN,),
                exponents=ArrayData(
                    numpy.asarray([1.0]), ("primitive",), "inverse_square_bohr"
                ),
                coefficients=ArrayData(
                    numpy.asarray([[1.0]]),
                    ("primitive", "contraction"),
                    "dimensionless",
                ),
            ),
        ),
        conventions=(BasisConvention(0, BasisFunctionKind.CARTESIAN, ("1",)),),
        primitive_normalization="l2",
        provenance_ids=(),
    )
    labels = {
        OrbitalKind.RESTRICTED: ("restricted",),
        OrbitalKind.UNRESTRICTED: ("alpha", "beta"),
        OrbitalKind.GENERALIZED: ("generalized",),
    }[kind]
    channels = []
    for label in labels:
        generalized = label == "generalized"
        coefficients = (
            numpy.asarray([[1.0, 0.0], [0.5, 0.0]])
            if generalized
            else numpy.asarray([[1.0], [0.5]])
        )
        channels.append(
            OrbitalChannel(
                label=label,
                coefficients=ArrayData(
                    coefficients,
                    ("orbital", "spin_basis_function")
                    if generalized
                    else ("orbital", "basis_function"),
                    "dimensionless",
                ),
                energies=ArrayData(numpy.asarray([-0.5, 0.1]), ("orbital",), "hartree"),
                occupations=None
                if not occupations
                else ArrayData(
                    numpy.asarray([1.0, 0.0])
                    if kind is OrbitalKind.UNRESTRICTED
                    else numpy.asarray([2.0, 0.0]),
                    ("orbital",),
                    "dimensionless",
                ),
                irreps=("a", "b"),
            )
        )
    orbitals = OrbitalSet(
        id=uuid4(),
        revision=revision,
        structure_id=structure.id,
        basis_set_id=basis.id,
        kind=kind,
        channels=tuple(channels),
        provenance_ids=(),
    )
    return structure, basis, orbitals


GRID = {
    "origin": (1.0, 2.0, 3.0),
    "step_vectors": ((0.5, 0.0, 0.0), (0.1, 0.4, 0.0), (0.0, 0.2, 0.3)),
    "shape": (2, 1, 1),
}


class WavefunctionGridTests(unittest.TestCase):
    def test_core_import_does_not_load_gbasis_or_scipy(self):
        code = (
            "import sys; import ChemBlender.core; "
            "assert 'gbasis' not in sys.modules; "
            "assert 'scipy' not in sys.modules"
        )
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_cartesian_convention_signs_are_applied_explicitly(self):
        structure, basis, _ = entities()
        signed_basis = BasisSet(
            id=basis.id,
            revision=basis.revision,
            structure_id=structure.id,
            name=basis.name,
            shells=basis.shells,
            conventions=(BasisConvention(0, BasisFunctionKind.CARTESIAN, ("-1",)),),
            primitive_normalization="l2",
            provenance_ids=(),
        )
        self.assertEqual(_basis_function_signs(signed_basis), (-1.0,))

    @mock.patch("ChemBlender.core.wavefunction_grid._evaluate_channel")
    def test_mo_grid_preserves_affine_points_phase_and_provenance(self, evaluate):
        structure, basis, orbitals = entities()
        evaluate.return_value = numpy.asarray([[2.0, -3.0]])
        first = evaluate_molecular_orbital_grid(
            structure,
            basis,
            orbitals,
            channel="restricted",
            orbital_index=0,
            **GRID,
        )
        second = evaluate_molecular_orbital_grid(
            structure,
            basis,
            orbitals,
            channel="restricted",
            orbital_index=0,
            **GRID,
        )

        grid = first.datasets[0]
        provenance = first.provenance[0]
        self.assertEqual(grid.semantic_role, "molecular_orbital")
        self.assertEqual(grid.data.unit, "inverse_bohr_to_three_halves")
        numpy.testing.assert_allclose(grid.data.values[:, 0, 0], [2.0, -3.0])
        points = evaluate.call_args_list[0].args[3]
        numpy.testing.assert_allclose(points, [[1.0, 2.0, 3.0], [1.5, 2.0, 3.0]])
        self.assertEqual(provenance.parent_ids, (structure.id, basis.id, orbitals.id))
        self.assertEqual(grid.provenance_ids, (provenance.id,))
        params = dict(provenance.parameters)
        self.assertEqual(params["channel"], "restricted")
        self.assertEqual(params["orbital_index"], 0)
        self.assertEqual(params["shape"], (2, 1, 1))
        self.assertEqual(first.datasets[0].revision, second.datasets[0].revision)
        self.assertEqual(
            first.provenance[0].source_hash, second.provenance[0].source_hash
        )
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(
            ImportBatch(
                structures=(structure,),
                basis_sets=(basis,),
                orbital_sets=(orbitals,),
            )
        )
        project.commit(first)

    @mock.patch("ChemBlender.core.wavefunction_grid._evaluate_channel")
    def test_density_sums_occupations_over_unrestricted_channels(self, evaluate):
        structure, basis, orbitals = entities(OrbitalKind.UNRESTRICTED)
        evaluate.side_effect = (
            numpy.asarray([[1.0, 2.0], [9.0, 9.0]]),
            numpy.asarray([[3.0, 4.0], [9.0, 9.0]]),
        )
        batch = evaluate_electron_density_grid(structure, basis, orbitals, **GRID)
        grid = batch.datasets[0]
        self.assertEqual(grid.semantic_role, "electron_density")
        self.assertEqual(grid.data.unit, "electron_per_cubic_bohr")
        numpy.testing.assert_allclose(grid.data.values[:, 0, 0], [10.0, 20.0])
        self.assertEqual(evaluate.call_count, 2)

    def test_invalid_references_units_grid_and_orbitals_fail_before_backend(self):
        structure, basis, orbitals = entities()
        wrong_basis = BasisSet(
            id=basis.id,
            revision=basis.revision,
            structure_id=uuid4(),
            name=basis.name,
            shells=basis.shells,
            conventions=basis.conventions,
            primitive_normalization=basis.primitive_normalization,
            provenance_ids=(),
        )
        angstrom_structure = Structure(
            id=structure.id,
            revision=structure.revision,
            atomic_numbers=structure.atomic_numbers,
            coordinates=ArrayData(
                structure.coordinates.values, ("atom", "xyz"), "angstrom"
            ),
        )
        for args, kwargs in (
            (
                (structure, wrong_basis, orbitals),
                {"channel": "restricted", "orbital_index": 0, **GRID},
            ),
            (
                (angstrom_structure, basis, orbitals),
                {"channel": "restricted", "orbital_index": 0, **GRID},
            ),
            (
                (structure, basis, orbitals),
                {"channel": "restricted", "orbital_index": 5, **GRID},
            ),
            (
                (structure, basis, orbitals),
                {"channel": "beta", "orbital_index": 0, **GRID},
            ),
            (
                (structure, basis, orbitals),
                {
                    "channel": "restricted",
                    "orbital_index": 0,
                    **{**GRID, "shape": (0, 1, 1)},
                },
            ),
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((ValueError, IndexError)):
                    evaluate_molecular_orbital_grid(*args, **kwargs)

        generalized = entities(OrbitalKind.GENERALIZED)
        with self.assertRaises(NotImplementedError):
            evaluate_molecular_orbital_grid(
                *generalized, channel="generalized", orbital_index=0, **GRID
            )
        missing_occupations = entities(occupations=False)
        with self.assertRaises(ValueError):
            evaluate_electron_density_grid(*missing_occupations, **GRID)

    @unittest.skipUnless(
        HAS_INTEGRATION, "GBasis/IOData integration environment unavailable"
    )
    def test_real_fchk_mo_norm_and_density_electron_count(self):
        from ChemBlender.core import parse_iodata_wavefunction

        imported = parse_iodata_wavefunction(FCHK)
        structure = imported.structures[0]
        basis = imported.basis_sets[0]
        orbitals = imported.orbital_sets[0]
        spacing = 0.1
        coords = structure.coordinates.values
        lower = numpy.floor((coords.min(axis=0) - 6.0) / spacing) * spacing
        upper = numpy.ceil((coords.max(axis=0) + 6.0) / spacing) * spacing
        shape = tuple(
            int(round((high - low) / spacing)) + 1 for low, high in zip(lower, upper)
        )
        grid_args = {
            "origin": tuple(lower),
            "step_vectors": (
                (spacing, 0.0, 0.0),
                (0.0, spacing, 0.0),
                (0.0, 0.0, spacing),
            ),
            "shape": shape,
        }
        mo = evaluate_molecular_orbital_grid(
            structure,
            basis,
            orbitals,
            channel="restricted",
            orbital_index=0,
            **grid_args,
        ).datasets[0]
        density = evaluate_electron_density_grid(
            structure, basis, orbitals, **grid_args
        ).datasets[0]
        voxel_volume = spacing**3
        mo_norm = float(numpy.sum(mo.data.values**2) * voxel_volume)
        electron_count = float(numpy.sum(density.data.values) * voxel_volume)
        self.assertAlmostEqual(mo_norm, 1.0045725101, places=6)
        self.assertAlmostEqual(electron_count, 10.0097251825, places=6)

    @unittest.skipUnless(
        HAS_INTEGRATION, "GBasis/IOData integration environment unavailable"
    )
    def test_pure_basis_convention_matches_official_iodata_wrapper(self):
        from gbasis.evals.eval import evaluate_basis
        from gbasis.wrappers import from_iodata
        from iodata import load_one

        from ChemBlender.core import parse_iodata_wavefunction

        imported = parse_iodata_wavefunction(PURE_FCHK)
        structure = imported.structures[0]
        basis = imported.basis_sets[0]
        orbitals = imported.orbital_sets[0]
        origin = (-0.3, 0.2, -0.1)
        steps = ((0.17, 0.0, 0.0), (0.02, 0.11, 0.0), (0.0, 0.01, 0.13))
        derived = evaluate_molecular_orbital_grid(
            structure,
            basis,
            orbitals,
            channel="restricted",
            orbital_index=0,
            origin=origin,
            step_vectors=steps,
            shape=(3, 1, 1),
        ).datasets[0]

        raw = load_one(PURE_FCHK)
        points = numpy.asarray(
            [
                numpy.asarray(origin) + index * numpy.asarray(steps[0])
                for index in range(3)
            ]
        )
        expected = evaluate_basis(
            from_iodata(raw), points, transform=raw.mo.coeffs[:, :1].T
        )[0]
        numpy.testing.assert_allclose(
            derived.data.values[:, 0, 0], expected, rtol=1e-12, atol=1e-12
        )


if __name__ == "__main__":
    unittest.main()
