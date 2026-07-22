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
    DatasetStatus,
    ExcitedStateSet,
    FrameSet,
    IssueKind,
    QCProject,
    SniffMatch,
    SpinChannel,
    VibrationalModeSet,
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
VIBRATION_FIXTURES = (
    (
        CCLIB_ROOT / "data" / "Gaussian" / "basicGaussian16" / "dvb_ir.out",
        "Gaussian",
        53.1981,
        False,
        True,
    ),
    (
        CCLIB_ROOT / "data" / "Gaussian" / "basicGaussian16" / "dvb_raman.out",
        "Gaussian",
        53.1117,
        True,
        True,
    ),
    (
        CCLIB_ROOT / "data" / "ORCA" / "basicORCA5.0" / "dvb_ir.out",
        "ORCA",
        45.66,
        False,
        False,
    ),
    (
        CCLIB_ROOT / "data" / "ORCA" / "basicORCA5.0" / "dvb_raman.out",
        "ORCA",
        77.7,
        True,
        False,
    ),
)
EXCITED_STATE_FIXTURES = (
    (
        CCLIB_ROOT / "data" / "Gaussian" / "basicGaussian16" / "dvb_td.out",
        "Gaussian",
        5,
        43030.485341579,
        True,
        0.0,
    ),
    (
        CCLIB_ROOT / "data" / "Gaussian" / "basicGaussian09" / "dvb_td.out",
        "Gaussian",
        5,
        45398.529145123,
        True,
        -0.478,
    ),
    (
        CCLIB_ROOT / "data" / "ORCA" / "basicORCA5.0" / "dvb_td.out",
        "ORCA",
        10,
        25241.0,
        False,
        0.0,
    ),
    (
        CCLIB_ROOT / "data" / "ORCA" / "basicORCA5.0" / "dvb_adc2.log",
        "ORCA",
        2,
        44797.1,
        False,
        0.0,
    ),
)
HAS_CCLIB_INTEGRATION = (
    importlib.util.find_spec("cclib") is not None
    and GAUSSIAN_FIXTURE.is_file()
    and ORCA_FIXTURE.is_file()
    and all(case[0].is_file() for case in VIBRATION_FIXTURES)
    and all(case[0].is_file() for case in EXCITED_STATE_FIXTURES)
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

    def test_vibrations_map_signed_modes_and_all_available_quantities(self):
        data = fake_ccdata(
            vibfreqs=numpy.asarray([-120.0, 1600.0]),
            vibdisps=numpy.zeros((2, 3, 3)),
            vibrmasses=numpy.asarray([1.0, 2.0]),
            vibfconsts=numpy.asarray([0.1, 1.2]),
            vibirs=numpy.asarray([2.0, 20.0]),
            vibramans=numpy.asarray([3.0, 30.0]),
            vibsyms=["A1", "B2"],
        )
        batch = adapt_ccdata(data, Path("frequency.log"), cclib_version="1.8.1")
        modes = next(
            dataset
            for dataset in batch.datasets
            if isinstance(dataset, VibrationalModeSet)
        )
        self.assertEqual(modes.data.values[0], -120.0)
        self.assertEqual(modes.displacements.shape, (2, 3, 3))
        self.assertEqual(modes.reduced_masses.unit, "dalton")
        self.assertEqual(modes.force_constants.unit, "millidyne_per_angstrom")
        self.assertEqual(modes.ir_intensities.unit, "kilometer_per_mole")
        self.assertEqual(modes.raman_activities.unit, "angstrom_four_per_dalton")
        self.assertEqual(modes.symmetries, ("A1", "B2"))
        self.assertIn("vibration", batch.report.parsed_capabilities)
        self.assertIn(modes.id, batch.calculations[0].dataset_ids)
        QCProject(id=uuid4(), schema_version="0.1").commit(batch)

    def test_vibration_missing_and_partial_fields_are_reported(self):
        complete_minimum = fake_ccdata(
            vibfreqs=numpy.asarray([100.0]),
            vibdisps=numpy.zeros((1, 3, 3)),
        )
        batch = adapt_ccdata(
            complete_minimum, Path("minimal-frequency.out"), cclib_version="1.8.1"
        )
        self.assertTrue(
            any(isinstance(item, VibrationalModeSet) for item in batch.datasets)
        )
        missing_paths = {
            issue.path
            for issue in batch.report.issues
            if issue.kind is IssueKind.MISSING
        }
        self.assertTrue(
            {"vibration.ir_intensity", "vibration.raman_activity"}.issubset(
                missing_paths
            )
        )

        partial = fake_ccdata(vibfreqs=numpy.asarray([100.0]))
        partial_batch = adapt_ccdata(
            partial, Path("partial-frequency.out"), cclib_version="1.8.1"
        )
        self.assertFalse(
            any(isinstance(item, VibrationalModeSet) for item in partial_batch.datasets)
        )
        self.assertTrue(
            any(
                issue.kind is IssueKind.MISSING
                and issue.path == "vibration.displacements"
                for issue in partial_batch.report.issues
            )
        )

    def test_invalid_vibration_shapes_fail_explicitly(self):
        invalid = (
            fake_ccdata(
                vibfreqs=numpy.zeros((2, 1)),
                vibdisps=numpy.zeros((2, 3, 3)),
            ),
            fake_ccdata(
                vibfreqs=numpy.zeros(2),
                vibdisps=numpy.zeros((1, 3, 3)),
            ),
            fake_ccdata(
                vibfreqs=numpy.zeros(2),
                vibdisps=numpy.zeros((2, 3, 3)),
                vibirs=numpy.zeros(1),
            ),
        )
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    adapt_ccdata(
                        data, Path("invalid-vibration.log"), cclib_version="1.8.1"
                    )

    def test_excited_states_map_signed_configurations_and_optional_fields(self):
        data = fake_ccdata(
            etenergies=numpy.asarray([25000.0, 30000.0]),
            etoscs=numpy.asarray([0.1, 0.2]),
            etrotats=numpy.asarray([-1.5, 2.0]),
            etdips=numpy.asarray([[1.0, 0.0, 0.0], [0.0, 2.0, 0.0]]),
            etveldips=numpy.zeros((2, 3)),
            etmagdips=numpy.ones((2, 3)),
            etsyms=["Singlet-A", "Triplet-B"],
            etsecs=[
                [((1, 0), (2, 0), -0.8)],
                [((0, 1), (3, 1), 0.5)],
            ],
        )
        batch = adapt_ccdata(data, Path("td.log"), cclib_version="1.8.1")
        states = next(
            item for item in batch.datasets if isinstance(item, ExcitedStateSet)
        )

        self.assertEqual(states.data.unit, "inverse_centimeter")
        self.assertEqual(states.oscillator_strengths.unit, "dimensionless")
        self.assertEqual(states.rotatory_strengths.unit, "unknown")
        self.assertIs(states.status, DatasetStatus.AMBIGUOUS)
        self.assertEqual(states.multiplicities, (1, 3))
        transition = states.configurations[0][0]
        self.assertEqual(transition.occupied_spin, SpinChannel.ALPHA)
        self.assertEqual(transition.virtual_spin, SpinChannel.ALPHA)
        self.assertEqual(transition.coefficient, -0.8)
        self.assertIn("excited_state", batch.report.parsed_capabilities)
        issues = {(issue.kind, issue.path) for issue in batch.report.issues}
        self.assertIn(
            (IssueKind.AMBIGUOUS, "excited_state.rotatory_strength.unit"), issues
        )
        QCProject(id=uuid4(), schema_version="0.1").commit(batch)

    def test_partial_excited_states_report_missing_and_invalid_configurations(self):
        missing_energy = fake_ccdata(etoscs=numpy.asarray([0.1]))
        batch = adapt_ccdata(
            missing_energy, Path("partial-td.log"), cclib_version="1.8.1"
        )
        self.assertFalse(
            any(isinstance(item, ExcitedStateSet) for item in batch.datasets)
        )
        self.assertIn(
            (IssueKind.MISSING, "excited_state.energies"),
            {(issue.kind, issue.path) for issue in batch.report.issues},
        )

        for etsecs in (
            [[((1, 9), (2, 0), 0.8)]],
            [[((1, 0), (2, 0), float("nan"))]],
        ):
            with self.subTest(etsecs=etsecs):
                malformed = fake_ccdata(
                    etenergies=numpy.asarray([25000.0]), etsecs=etsecs
                )
                malformed_batch = adapt_ccdata(
                    malformed, Path("malformed-td.log"), cclib_version="1.8.1"
                )
                states = next(
                    item
                    for item in malformed_batch.datasets
                    if isinstance(item, ExcitedStateSet)
                )
                self.assertIsNone(states.configurations)
                self.assertIn(
                    (IssueKind.INVALID, "excited_state.configurations"),
                    {
                        (issue.kind, issue.path)
                        for issue in malformed_batch.report.issues
                    },
                )

    def test_invalid_excited_state_arrays_fail_explicitly(self):
        invalid = (
            fake_ccdata(etenergies=numpy.zeros((2, 1))),
            fake_ccdata(etenergies=numpy.asarray([-1.0])),
            fake_ccdata(
                etenergies=numpy.asarray([1.0, 2.0]),
                etoscs=numpy.asarray([0.1]),
            ),
            fake_ccdata(
                etenergies=numpy.asarray([1.0]),
                etdips=numpy.zeros((1, 2)),
            ),
        )
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    adapt_ccdata(
                        data, Path("invalid-td.log"), cclib_version="1.8.1"
                    )

    def test_reader_descriptor_declares_only_implemented_capabilities(self):
        self.assertEqual(CCLIB_OUTPUT_READER.reader_id, "cclib_output")
        self.assertEqual(CCLIB_OUTPUT_READER.reader_version, "3")
        self.assertEqual(CCLIB_OUTPUT_READER.extensions, (".log", ".out"))
        self.assertEqual(
            CCLIB_OUTPUT_READER.capabilities,
            {
                "structure": CapabilitySupport.SUPPORTED,
                "trajectory": CapabilitySupport.SUPPORTED,
                "energy": CapabilitySupport.SUPPORTED,
                "atomic_property": CapabilitySupport.SUPPORTED,
                "vibration": CapabilitySupport.SUPPORTED,
                "excited_state": CapabilitySupport.SUPPORTED,
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

    @unittest.skipUnless(
        HAS_CCLIB_INTEGRATION, "cclib integration environment unavailable"
    )
    def test_real_gaussian_and_orca_vibrations(self):
        for source, package, first_frequency, has_raman, has_mass in VIBRATION_FIXTURES:
            with self.subTest(source=source):
                batch = parse_cclib_output(source)
                modes = next(
                    dataset
                    for dataset in batch.datasets
                    if isinstance(dataset, VibrationalModeSet)
                )
                self.assertEqual(modes.data.shape, (54,))
                self.assertEqual(modes.displacements.shape, (54, 20, 3))
                self.assertAlmostEqual(modes.data.values[0], first_frequency, places=4)
                self.assertEqual(modes.raman_activities is not None, has_raman)
                self.assertEqual(modes.reduced_masses is not None, has_mass)
                self.assertEqual(
                    dict(batch.provenance[0].parameters)["package"], package
                )
                QCProject(id=uuid4(), schema_version="0.1").commit(batch)

    @unittest.skipUnless(
        HAS_CCLIB_INTEGRATION, "cclib integration environment unavailable"
    )
    def test_real_gaussian_and_orca_excited_states(self):
        for source, package, state_count, first_energy, has_dipoles, first_rotatory in (
            EXCITED_STATE_FIXTURES
        ):
            with self.subTest(source=source):
                batch = parse_cclib_output(source)
                states = next(
                    item
                    for item in batch.datasets
                    if isinstance(item, ExcitedStateSet)
                )
                self.assertEqual(states.data.shape, (state_count,))
                self.assertAlmostEqual(states.data.values[0], first_energy, places=6)
                self.assertEqual(states.electric_transition_dipoles is not None, has_dipoles)
                self.assertAlmostEqual(
                    states.rotatory_strengths.values[0], first_rotatory
                )
                self.assertEqual(
                    dict(batch.provenance[0].parameters)["package"], package
                )
                self.assertIsNotNone(states.configurations)
                QCProject(id=uuid4(), schema_version="0.1").commit(batch)


if __name__ == "__main__":
    unittest.main()
