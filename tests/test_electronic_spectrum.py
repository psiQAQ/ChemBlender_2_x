import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    ImportBatch,
    QCProject,
    Spectrum,
    SpectrumKind,
    SpectrumProfile,
    derive_electronic_spectrum,
)
from tests.test_excited_state_model import state_set
from tests.test_vibration_model import structure


class ElectronicSpectrumTests(unittest.TestCase):
    def test_uv_vis_sticks_preserve_energies_and_oscillator_strengths(self):
        reference = structure()
        states = state_set(reference.id)
        first = derive_electronic_spectrum(
            states,
            kind=SpectrumKind.UV_VIS,
            profile=SpectrumProfile.STICK,
        )
        second = derive_electronic_spectrum(
            states,
            kind=SpectrumKind.UV_VIS,
            profile=SpectrumProfile.STICK,
        )
        spectrum = first.datasets[0]

        self.assertIsInstance(spectrum, Spectrum)
        self.assertEqual(spectrum.semantic_role, "uv_vis_spectrum")
        self.assertEqual(spectrum.axis.unit, "inverse_centimeter")
        self.assertEqual(spectrum.data.unit, "dimensionless")
        self.assertEqual(spectrum.selection_policy, "all_states")
        numpy.testing.assert_allclose(spectrum.axis.values, [20000.0, 30000.0])
        numpy.testing.assert_allclose(spectrum.data.values, [0.1, 0.2])
        self.assertEqual(spectrum.revision, second.datasets[0].revision)
        self.assertEqual(first.provenance[0].parent_ids, (states.id,))

    def test_broadened_uv_vis_uses_wavenumber_fwhm(self):
        reference = structure()
        states = state_set(
            reference.id,
            data=ArrayData(
                numpy.asarray([20000.0]), ("state",), "inverse_centimeter"
            ),
            oscillator_strengths=ArrayData(
                numpy.asarray([2.0]), ("state",), "dimensionless"
            ),
            symmetries=("Singlet-A",),
            multiplicities=(1,),
            configurations=None,
            electric_transition_dipoles=None,
            state_references=(state_set(reference.id).state_references[0],),
        )
        axis = numpy.asarray([20000.0, 20005.0])
        for profile in (SpectrumProfile.GAUSSIAN, SpectrumProfile.LORENTZIAN):
            with self.subTest(profile=profile):
                spectrum = derive_electronic_spectrum(
                    states,
                    kind=SpectrumKind.UV_VIS,
                    profile=profile,
                    axis=axis,
                    fwhm=10.0,
                ).datasets[0]
                numpy.testing.assert_allclose(spectrum.data.values, [2.0, 1.0])
                self.assertEqual(spectrum.fwhm, 10.0)

    def test_ecd_preserves_signed_strength_and_ambiguous_unit(self):
        reference = structure()
        states = state_set(
            reference.id,
            rotatory_strengths=ArrayData(
                numpy.asarray([-0.4, 0.2]), ("state",), "unknown"
            ),
            status=DatasetStatus.AMBIGUOUS,
        )
        batch = derive_electronic_spectrum(
            states,
            kind=SpectrumKind.ECD,
            profile=SpectrumProfile.STICK,
        )
        spectrum = batch.datasets[0]

        self.assertEqual(spectrum.data.unit, "unknown")
        self.assertIs(spectrum.status, DatasetStatus.AMBIGUOUS)
        numpy.testing.assert_allclose(spectrum.data.values, [-0.4, 0.2])

        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(ImportBatch(structures=(reference,), datasets=(states,)))
        project.commit(batch)
        self.assertIs(project.datasets[spectrum.id], spectrum)

    def test_missing_strength_invalid_kind_and_dangling_source_fail(self):
        reference = structure()
        no_oscillator = state_set(reference.id, oscillator_strengths=None)
        with self.assertRaises(ValueError):
            derive_electronic_spectrum(
                no_oscillator,
                kind=SpectrumKind.UV_VIS,
                profile=SpectrumProfile.STICK,
            )

        states = state_set(reference.id)
        with self.assertRaises(ValueError):
            derive_electronic_spectrum(
                states,
                kind=SpectrumKind.IR,
                profile=SpectrumProfile.STICK,
            )

        spectrum = derive_electronic_spectrum(
            states,
            kind=SpectrumKind.UV_VIS,
            profile=SpectrumProfile.STICK,
        ).datasets[0]
        with self.assertRaises(ValueError):
            QCProject(id=uuid4(), schema_version="0.1").commit(
                ImportBatch(structures=(reference,), datasets=(spectrum,))
            )


if __name__ == "__main__":
    unittest.main()
