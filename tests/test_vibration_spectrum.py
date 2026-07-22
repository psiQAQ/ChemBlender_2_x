import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    ImportBatch,
    QCProject,
    Spectrum,
    SpectrumKind,
    SpectrumProfile,
    derive_vibrational_spectrum,
)
from tests.test_vibration_model import mode_set, structure


class VibrationalSpectrumTests(unittest.TestCase):
    def test_stick_spectrum_preserves_signed_frequencies_and_intensities(self):
        reference = structure()
        modes = mode_set(reference.id)
        first = derive_vibrational_spectrum(
            modes,
            kind=SpectrumKind.IR,
            profile=SpectrumProfile.STICK,
        )
        second = derive_vibrational_spectrum(
            modes,
            kind=SpectrumKind.IR,
            profile=SpectrumProfile.STICK,
        )
        spectrum = first.datasets[0]
        self.assertIsInstance(spectrum, Spectrum)
        self.assertEqual(spectrum.semantic_role, "ir_spectrum")
        self.assertEqual(spectrum.axis.unit, "inverse_centimeter")
        self.assertEqual(spectrum.data.unit, "kilometer_per_mole")
        numpy.testing.assert_allclose(spectrum.axis.values, [-120.0, 1600.0])
        numpy.testing.assert_allclose(spectrum.data.values, [2.0, 20.0])
        self.assertEqual(spectrum.revision, second.datasets[0].revision)
        self.assertEqual(first.provenance[0].parent_ids, (modes.id,))

    def test_gaussian_and_lorentzian_use_fwhm_and_peak_normalization(self):
        reference = structure()
        modes = mode_set(
            reference.id,
            data=ArrayData(numpy.asarray([100.0]), ("mode",), "inverse_centimeter"),
            displacements=ArrayData(
                numpy.zeros((1, 2, 3)),
                ("mode", "atom", "xyz"),
                "angstrom",
            ),
            reduced_masses=None,
            force_constants=None,
            ir_intensities=ArrayData(
                numpy.asarray([2.0]), ("mode",), "kilometer_per_mole"
            ),
            raman_activities=ArrayData(
                numpy.asarray([3.0]),
                ("mode",),
                "angstrom_four_per_dalton",
            ),
            symmetries=None,
        )
        axis = numpy.asarray([100.0, 105.0])
        for profile in (SpectrumProfile.GAUSSIAN, SpectrumProfile.LORENTZIAN):
            with self.subTest(profile=profile):
                spectrum = derive_vibrational_spectrum(
                    modes,
                    kind=SpectrumKind.IR,
                    profile=profile,
                    axis=axis,
                    fwhm=10.0,
                ).datasets[0]
                numpy.testing.assert_allclose(spectrum.data.values, [2.0, 1.0])
                self.assertEqual(spectrum.fwhm, 10.0)

    def test_raman_and_explicit_imaginary_filter_use_mode_set_identity(self):
        reference = structure()
        modes = mode_set(reference.id)
        batch = derive_vibrational_spectrum(
            modes,
            kind=SpectrumKind.RAMAN,
            profile=SpectrumProfile.STICK,
            include_imaginary=False,
        )
        spectrum = batch.datasets[0]
        self.assertEqual(spectrum.semantic_role, "raman_spectrum")
        self.assertEqual(spectrum.source_dataset_id, modes.id)
        self.assertEqual(spectrum.data.unit, "angstrom_four_per_dalton")
        numpy.testing.assert_allclose(spectrum.axis.values, [1600.0])
        numpy.testing.assert_allclose(spectrum.data.values, [30.0])
        self.assertFalse(spectrum.include_imaginary)

        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(ImportBatch(structures=(reference,), datasets=(modes,)))
        project.commit(batch)
        self.assertIs(project.datasets[spectrum.id], spectrum)

    def test_missing_intensity_invalid_profile_axis_and_dangling_source_fail(self):
        reference = structure()
        no_raman = mode_set(reference.id, raman_activities=None)
        with self.assertRaises(ValueError):
            derive_vibrational_spectrum(
                no_raman,
                kind=SpectrumKind.RAMAN,
                profile=SpectrumProfile.STICK,
            )

        modes = mode_set(reference.id)
        invalid_calls = (
            {"profile": SpectrumProfile.GAUSSIAN, "axis": [1.0, 2.0]},
            {
                "profile": SpectrumProfile.GAUSSIAN,
                "axis": [2.0, 1.0],
                "fwhm": 10.0,
            },
            {
                "profile": SpectrumProfile.LORENTZIAN,
                "axis": [[1.0, 2.0]],
                "fwhm": 10.0,
            },
        )
        for values in invalid_calls:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    derive_vibrational_spectrum(
                        modes,
                        kind=SpectrumKind.IR,
                        **values,
                    )

        spectrum = derive_vibrational_spectrum(
            modes,
            kind=SpectrumKind.IR,
            profile=SpectrumProfile.STICK,
        ).datasets[0]
        project = QCProject(id=uuid4(), schema_version="0.1")
        with self.assertRaises(ValueError):
            project.commit(ImportBatch(structures=(reference,), datasets=(spectrum,)))


if __name__ == "__main__":
    unittest.main()
