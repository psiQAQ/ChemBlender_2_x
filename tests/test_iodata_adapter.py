import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    BasisFunctionKind,
    CapabilitySupport,
    IssueKind,
    OrbitalKind,
    QCProject,
    SniffMatch,
)
from ChemBlender.core.iodata_adapter import (
    IODATA_WAVEFUNCTION_READER,
    adapt_iodata,
    parse_iodata_wavefunction,
    sniff_iodata_wavefunction,
)


ROOT = Path(__file__).resolve().parents[1]
IODATA_ROOT = ROOT / "submodules" / "iodata"
DATA_ROOT = IODATA_ROOT / "iodata" / "test" / "data"
RESTRICTED_FCHK = DATA_ROOT / "water_sto3g_hf_g03.fchk"
UNRESTRICTED_FCHK = DATA_ROOT / "ch3_hf_sto3g.fchk"
MOLDEN_FIXTURE = DATA_ROOT / "h2o.molden.input"
HAS_IODATA_INTEGRATION = importlib.util.find_spec("iodata") is not None and all(
    path.is_file() for path in (RESTRICTED_FCHK, UNRESTRICTED_FCHK, MOLDEN_FIXTURE)
)


def fake_shell():
    return SimpleNamespace(
        icenter=0,
        angmoms=numpy.asarray([0]),
        kinds=numpy.asarray(["c"]),
        exponents=numpy.asarray([1.0, 0.5]),
        coeffs=numpy.asarray([[0.7], [0.3]]),
    )


def fake_basis():
    return SimpleNamespace(
        shells=[fake_shell(), fake_shell()],
        conventions={(0, "c"): ["1"]},
        primitive_normalization="L2",
    )


def fake_mo(kind="restricted"):
    if kind == "restricted":
        return SimpleNamespace(
            kind=kind,
            norba=2,
            norbb=2,
            coeffs=numpy.asarray([[1.0, 0.2], [0.0, 0.8]]),
            energies=numpy.asarray([-0.5, 0.1]),
            occs=numpy.asarray([2.0, 0.0]),
            irreps=numpy.asarray(["a1", "b1"]),
        )
    if kind == "unrestricted":
        return SimpleNamespace(
            kind=kind,
            norba=2,
            norbb=1,
            coeffs=numpy.asarray([[1.0, 0.2, 0.1], [0.0, 0.8, 0.9]]),
            energies=numpy.asarray([-0.5, 0.1, -0.4]),
            occs=numpy.asarray([1.0, 0.0, 1.0]),
            irreps=numpy.asarray(["a1", "b1", "a1"]),
        )
    return SimpleNamespace(
        kind="generalized",
        norba=None,
        norbb=None,
        coeffs=numpy.asarray(
            [[1.0, 0.0], [0.0, 1.0], [0.2, 0.1], [0.1, 0.2]]
        ),
        energies=numpy.asarray([-0.5, 0.1]),
        occs=numpy.asarray([1.0, 0.0]),
        irreps=None,
    )


def fake_iodata(kind="restricted", **overrides):
    values = {
        "atnums": numpy.asarray([1]),
        "atcoords": numpy.asarray([[0.0, 0.0, 0.0]]),
        "obasis": fake_basis(),
        "obasis_name": "sto-3g",
        "mo": fake_mo(kind),
        "title": "synthetic wavefunction",
        "energy": -0.5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class GeneralizedData(SimpleNamespace):
    @property
    def spinpol(self):
        raise NotImplementedError


class IODataAdapterTests(unittest.TestCase):
    def test_core_import_does_not_eagerly_load_iodata_stack(self):
        code = (
            "import sys; import ChemBlender.core; "
            "assert 'iodata' not in sys.modules; "
            "assert 'attrs' not in sys.modules; "
            "assert 'scipy' not in sys.modules; "
            "assert 'numpy' not in sys.modules"
        )
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_sniff_recognizes_fchk_and_molden_only(self):
        fchk = sniff_iodata_wavefunction(
            Path("wavefunction.data"),
            b"title\nSP        RHF      STO-3G\nNumber of atoms        I       3\n",
        )
        molden = sniff_iodata_wavefunction(
            Path("wavefunction.data"), b"[Molden Format]\n[Atoms] AU\n"
        )
        unknown = sniff_iodata_wavefunction(Path("notes.fchk"), b"ordinary text\n")
        self.assertEqual(fchk.match, SniffMatch.EXACT)
        self.assertEqual(molden.match, SniffMatch.EXACT)
        self.assertEqual(unknown.match, SniffMatch.NONE)

    def test_restricted_mapping_preserves_basis_convention_and_orbitals(self):
        batch = adapt_iodata(
            fake_iodata(), Path("synthetic.fchk"), iodata_version="1.0.1"
        )
        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(len(batch.basis_sets), 1)
        self.assertEqual(len(batch.orbital_sets), 1)
        structure = batch.structures[0]
        basis = batch.basis_sets[0]
        orbitals = batch.orbital_sets[0]
        self.assertEqual(structure.coordinates.unit, "bohr")
        self.assertEqual(basis.basis_function_count, 2)
        self.assertIs(basis.shells[0].kinds[0], BasisFunctionKind.CARTESIAN)
        self.assertEqual(basis.conventions[0].functions, ("1",))
        self.assertIs(orbitals.kind, OrbitalKind.RESTRICTED)
        restricted = orbitals.channels[0]
        self.assertEqual(restricted.label, "restricted")
        self.assertEqual(restricted.coefficients.shape, (2, 2))
        self.assertAlmostEqual(restricted.coefficients.values[1, 0], 0.2)
        self.assertEqual(restricted.energies.unit, "hartree")
        self.assertEqual(restricted.occupations.unit, "dimensionless")
        self.assertEqual(restricted.irreps, ("a1", "b1"))
        self.assertEqual(
            batch.report.parsed_capabilities, ("structure", "basis_set", "orbital")
        )
        params = dict(batch.provenance[0].parameters)
        self.assertEqual(params["iodata_version"], "1.0.1")
        self.assertIn("energy", params["unmapped_attributes"])
        self.assertTrue(
            any(issue.kind is IssueKind.UNSUPPORTED for issue in batch.report.issues)
        )
        QCProject(id=uuid4(), schema_version="0.1").commit(batch)

    def test_unrestricted_channels_can_have_different_orbital_counts(self):
        orbitals = adapt_iodata(
            fake_iodata("unrestricted"),
            Path("open-shell.fchk"),
            iodata_version="1.0.1",
        ).orbital_sets[0]
        self.assertIs(orbitals.kind, OrbitalKind.UNRESTRICTED)
        alpha, beta = orbitals.channels
        self.assertEqual((alpha.label, beta.label), ("alpha", "beta"))
        self.assertEqual(alpha.coefficients.shape, (2, 2))
        self.assertEqual(beta.coefficients.shape, (1, 2))
        self.assertAlmostEqual(beta.coefficients.values[0, 1], 0.9)

    def test_generalized_orbitals_keep_spin_basis_dimension(self):
        data = fake_iodata("generalized")
        data = GeneralizedData(**vars(data))
        orbitals = adapt_iodata(
            data,
            Path("spinor.fchk"),
            iodata_version="1.0.1",
        ).orbital_sets[0]
        self.assertIs(orbitals.kind, OrbitalKind.GENERALIZED)
        channel = orbitals.channels[0]
        self.assertEqual(channel.label, "generalized")
        self.assertEqual(channel.coefficients.shape, (2, 4))
        self.assertEqual(
            channel.coefficients.dims, ("orbital", "spin_basis_function")
        )

    def test_missing_optional_orbital_arrays_are_reported(self):
        mo = fake_mo()
        mo.energies = None
        mo.occs = None
        mo.irreps = None
        batch = adapt_iodata(
            fake_iodata(mo=mo), Path("partial.molden"), iodata_version="1.0.1"
        )
        channel = batch.orbital_sets[0].channels[0]
        self.assertIsNone(channel.energies)
        self.assertIsNone(channel.occupations)
        self.assertEqual(channel.irreps, ())
        issues = {(issue.kind, issue.path) for issue in batch.report.issues}
        self.assertIn((IssueKind.MISSING, "orbital.energies"), issues)
        self.assertIn((IssueKind.MISSING, "orbital.occupations"), issues)
        self.assertIn((IssueKind.MISSING, "orbital.irreps"), issues)

    def test_invalid_required_shapes_and_basis_kinds_fail(self):
        invalid_basis = fake_basis()
        invalid_basis.shells[0].kinds = numpy.asarray(["invalid"])
        cases = (
            fake_iodata(atcoords=numpy.zeros((1, 1, 3))),
            fake_iodata(atnums=numpy.asarray([1, 1])),
            fake_iodata(obasis=invalid_basis),
            fake_iodata(mo=SimpleNamespace(**{**vars(fake_mo()), "coeffs": numpy.zeros((3, 2))})),
        )
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    adapt_iodata(data, Path("invalid.fchk"), iodata_version="1.0.1")

    def test_descriptor_declares_only_wavefunction_capabilities(self):
        self.assertEqual(IODATA_WAVEFUNCTION_READER.reader_id, "iodata_wavefunction")
        self.assertEqual(
            IODATA_WAVEFUNCTION_READER.capabilities,
            {
                "structure": CapabilitySupport.SUPPORTED,
                "basis_set": CapabilitySupport.SUPPORTED,
                "orbital": CapabilitySupport.SUPPORTED,
            },
        )
        manifest = (ROOT / "ChemBlender" / "blender_manifest.toml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("iodata", manifest.lower())

    @unittest.skipUnless(HAS_IODATA_INTEGRATION, "IOData integration environment unavailable")
    def test_real_fchk_and_molden_wavefunctions(self):
        cases = (
            (RESTRICTED_FCHK, OrbitalKind.RESTRICTED, 7, 7),
            (UNRESTRICTED_FCHK, OrbitalKind.UNRESTRICTED, 8, 8),
            (MOLDEN_FIXTURE, OrbitalKind.RESTRICTED, 19, 19),
        )
        for source, kind, basis_count, alpha_count in cases:
            with self.subTest(source=source):
                batch = parse_iodata_wavefunction(source)
                basis = batch.basis_sets[0]
                orbitals = batch.orbital_sets[0]
                self.assertEqual(basis.basis_function_count, basis_count)
                self.assertIs(orbitals.kind, kind)
                self.assertEqual(orbitals.channels[0].coefficients.shape[0], alpha_count)
                self.assertEqual(
                    orbitals.channels[0].coefficients.shape[1], basis_count
                )
                if source == MOLDEN_FIXTURE:
                    self.assertTrue(
                        any(
                            issue.kind is IssueKind.WARNING
                            and issue.path == "iodata.load"
                            for issue in batch.report.issues
                        )
                    )
                QCProject(id=uuid4(), schema_version="0.1").commit(batch)


if __name__ == "__main__":
    unittest.main()
