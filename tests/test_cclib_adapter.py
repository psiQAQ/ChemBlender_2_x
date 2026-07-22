import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    CalculationStatus,
    CapabilitySupport,
    FrameSet,
    IssueKind,
    QCProject,
    SniffMatch,
)
from ChemBlender.core.cclib_adapter import (
    CCLIB_OUTPUT_READER,
    adapt_ccdata,
    parse_cclib_output,
    sniff_cclib_output,
)


ROOT = Path(__file__).resolve().parents[1]
CCLIB_ROOT = ROOT / "submodules" / "cclib"
GAUSSIAN_FIXTURE = (
    CCLIB_ROOT
    / "data"
    / "Gaussian"
    / "basicGaussian16"
    / "water_hf_solvent_cpcm.log"
)
ORCA_FIXTURE = (
    CCLIB_ROOT / "data" / "ORCA" / "basicORCA4.1" / "water_mp2.out"
)
HAS_CCLIB_INTEGRATION = (
    importlib.util.find_spec("cclib") is not None
    and GAUSSIAN_FIXTURE.is_file()
    and ORCA_FIXTURE.is_file()
)


def fake_ccdata(**overrides):
    values = {
        "atomnos": numpy.asarray([8, 1, 1]),
        "atomcoords": numpy.asarray(
            [
                [[0.0, 0.0, 0.0], [0.7, 0.0, 0.5], [-0.7, 0.0, 0.5]],
                [[0.0, 0.0, 0.1], [0.8, 0.0, 0.5], [-0.8, 0.0, 0.5]],
            ]
        ),
        "scfenergies": numpy.asarray([-75.0, -75.1]),
        "atomcharges": {"mulliken": numpy.asarray([-0.4, 0.2, 0.2])},
        "atomspins": {"lowdin": numpy.asarray([0.0, 0.0, 0.0])},
        "metadata": {
            "package": "Gaussian",
            "package_version": "2016+C.01",
            "methods": ["HF"],
            "basis_set": "STO-3G",
            "success": True,
        },
        "charge": 0,
        "mult": 1,
        "mpenergies": numpy.asarray([[-75.2]]),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CCLibAdapterTests(unittest.TestCase):
    def test_core_import_does_not_eagerly_load_optional_stack(self):
        code = (
            "import sys; import ChemBlender.core; "
            "assert 'cclib' not in sys.modules; "
            "assert 'scipy' not in sys.modules; "
            "assert 'numpy' not in sys.modules"
        )
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_sniff_identifies_gaussian_and_orca_markers(self):
        gaussian = sniff_cclib_output(
            Path("calculation.out"), b" Entering Gaussian System, Link 0=g16\n"
        )
        orca = sniff_cclib_output(
            Path("calculation.log"), b"*****\n* O   R   C   A *\n*****\n"
        )
        unknown = sniff_cclib_output(Path("notes.out"), b"ordinary text\n")
        self.assertEqual(gaussian.match, SniffMatch.EXACT)
        self.assertEqual(orca.match, SniffMatch.EXACT)
        self.assertEqual(unknown.match, SniffMatch.NONE)

    def test_adapt_ccdata_maps_structure_energy_properties_and_status(self):
        batch = adapt_ccdata(
            fake_ccdata(), Path("synthetic.log"), cclib_version="1.8.1"
        )

        self.assertEqual(len(batch.structures), 1)
        structure = batch.structures[0]
        self.assertEqual(structure.atomic_numbers, (8, 1, 1))
        self.assertEqual(structure.coordinates.shape, (3, 3))
        self.assertAlmostEqual(structure.coordinates.values[0, 2], 0.1)

        self.assertEqual(len(batch.calculations), 1)
        calculation = batch.calculations[0]
        self.assertIs(calculation.status, CalculationStatus.SUCCESS)
        self.assertEqual(calculation.result_structure_ids, (structure.id,))
        self.assertEqual(calculation.input_structure_ids, ())

        roles = {dataset.semantic_role: dataset for dataset in batch.datasets}
        self.assertEqual(
            set(roles),
            {"coordinates", "scf_energy", "mulliken_charge", "lowdin_spin_population"},
        )
        self.assertIsInstance(roles["coordinates"], FrameSet)
        self.assertEqual(roles["coordinates"].data.shape, (2, 3, 3))
        self.assertEqual(roles["scf_energy"].data.unit, "electron_volt")
        self.assertEqual(roles["scf_energy"].data.dims, ("step",))
        self.assertEqual(roles["mulliken_charge"].data.unit, "elementary_charge")
        self.assertEqual(roles["lowdin_spin_population"].data.unit, "dimensionless")
        self.assertTrue(
            all(dataset.source_calculation == calculation.id for dataset in roles.values())
        )
        self.assertEqual(set(calculation.dataset_ids), {dataset.id for dataset in roles.values()})

        params = dict(batch.provenance[0].parameters)
        self.assertEqual(params["package"], "Gaussian")
        self.assertEqual(params["cclib_version"], "1.8.1")
        self.assertIn("mpenergies", params["unmapped_attributes"])
        self.assertEqual(
            batch.report.parsed_capabilities,
            ("structure", "trajectory", "energy", "atomic_property"),
        )
        self.assertTrue(
            any(issue.kind is IssueKind.UNSUPPORTED for issue in batch.report.issues)
        )
        QCProject(id=uuid4(), schema_version="0.1").commit(batch)

    def test_missing_optional_fields_are_reported_without_empty_datasets(self):
        data = fake_ccdata(
            atomcoords=numpy.asarray([[[0.0, 0.0, 0.0], [0.7, 0.0, 0.5], [-0.7, 0.0, 0.5]]]),
            metadata={"package": "ORCA", "package_version": "5.0"},
        )
        del data.scfenergies
        del data.atomcharges
        del data.atomspins
        del data.mpenergies

        batch = adapt_ccdata(data, Path("incomplete.out"), cclib_version="1.8.1")

        self.assertEqual(batch.datasets, ())
        self.assertIs(batch.calculations[0].status, CalculationStatus.INCOMPLETE)
        self.assertEqual(batch.report.parsed_capabilities, ("structure",))
        issues = {(issue.kind, issue.path) for issue in batch.report.issues}
        self.assertIn((IssueKind.MISSING, "energy.scf"), issues)
        self.assertIn((IssueKind.MISSING, "atomic_property"), issues)
        self.assertIn((IssueKind.AMBIGUOUS, "calculation.status"), issues)

    def test_invalid_core_array_shapes_fail_explicitly(self):
        invalid = (
            fake_ccdata(atomnos=numpy.asarray([8, 1])),
            fake_ccdata(atomcoords=numpy.zeros((2, 3))),
            fake_ccdata(scfenergies=numpy.zeros((2, 1))),
            fake_ccdata(atomcharges={"mulliken": numpy.zeros(2)}),
        )
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    adapt_ccdata(data, Path("invalid.log"), cclib_version="1.8.1")

    def test_reader_descriptor_declares_only_implemented_capabilities(self):
        self.assertEqual(CCLIB_OUTPUT_READER.reader_id, "cclib_output")
        self.assertEqual(CCLIB_OUTPUT_READER.extensions, (".log", ".out"))
        self.assertEqual(
            CCLIB_OUTPUT_READER.capabilities,
            {
                "structure": CapabilitySupport.SUPPORTED,
                "trajectory": CapabilitySupport.SUPPORTED,
                "energy": CapabilitySupport.SUPPORTED,
                "atomic_property": CapabilitySupport.SUPPORTED,
            },
        )
        manifest = (ROOT / "ChemBlender" / "blender_manifest.toml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("cclib", manifest.lower())

    @unittest.skipUnless(HAS_CCLIB_INTEGRATION, "cclib integration environment unavailable")
    def test_real_gaussian_and_orca_outputs(self):
        for source, package, expected_charge_roles in (
            (GAUSSIAN_FIXTURE, "Gaussian", {"mulliken_charge", "mulliken_sum_charge"}),
            (ORCA_FIXTURE, "ORCA", {"mulliken_charge", "lowdin_charge"}),
        ):
            with self.subTest(source=source):
                batch = parse_cclib_output(source)
                roles = {dataset.semantic_role for dataset in batch.datasets}
                self.assertIn("scf_energy", roles)
                self.assertTrue(expected_charge_roles.issubset(roles))
                self.assertEqual(dict(batch.provenance[0].parameters)["package"], package)
                self.assertIs(batch.calculations[0].status, CalculationStatus.SUCCESS)
                QCProject(id=uuid4(), schema_version="0.1").commit(batch)


if __name__ == "__main__":
    unittest.main()
