import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import CalculationStatus, QualityStatus, TopologySource


class SMILES3DDerivationTests(unittest.TestCase):
    def source(self):
        batch = self._source_batch("C[C@H](O)Cl")
        return (
            batch.structures[0], batch.topologies[0], batch.molecular_records[0],
            batch.source_revisions[0],
        )

    def test_etkdg_derivation_is_reproducible_and_records_explicit_parameters(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        first = derive_smiles_3d(structure, topology, record, source_revision)
        second = derive_smiles_3d(structure, topology, record, source_revision)

        self.assertEqual(first.calculations[0].status, CalculationStatus.SUCCESS)
        self.assertEqual(first.structures[0].id, second.structures[0].id)
        self.assertEqual(first.structures[0].revision, second.structures[0].revision)
        numpy.testing.assert_allclose(
            first.structures[0].coordinates.values,
            second.structures[0].coordinates.values,
            rtol=0.0,
            atol=0.0,
        )
        parameters = dict(first.provenance[0].parameters)
        self.assertEqual(parameters["embedding"], "ETKDGv3")
        self.assertEqual(parameters["random_seed"], 0xC0FFEE)
        self.assertEqual(parameters["num_threads"], 1)
        self.assertTrue(parameters["add_hydrogens"])
        self.assertEqual(parameters["force_field"], "MMFF94")
        self.assertEqual(first.provenance[0].parent_ids, (record.id, structure.id, topology.id))
        self.assertEqual(first.topologies[0].source_kind, TopologySource.RDKIT_SANITIZED)
        self.assertEqual(first.topologies[0].quality_status, QualityStatus.COMPLETE)

    def test_embedding_failure_keeps_the_source_untouched_and_has_no_derived_structure(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        with patch("rdkit.Chem.AllChem.EmbedMolecule", return_value=-1):
            batch = derive_smiles_3d(structure, topology, record, source_revision)

        self.assertEqual(batch.calculations[0].status, CalculationStatus.FAILED)
        self.assertEqual(batch.structures, ())
        self.assertEqual(batch.topologies, ())
        self.assertEqual(batch.diagnostics[0].code, "smiles_3d.embedding_failed")
        self.assertEqual(batch.provenance[0].parent_ids, (record.id, structure.id, topology.id))

    def test_recoverable_embedding_runtime_error_is_a_failed_result(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        with patch("rdkit.Chem.AllChem.EmbedMolecule", side_effect=RuntimeError("embed")):
            batch = derive_smiles_3d(structure, topology, record, source_revision)
        self.assertEqual(batch.calculations[0].status, CalculationStatus.FAILED)
        self.assertEqual(batch.structures, ())
        self.assertEqual(batch.diagnostics[0].code, "smiles_3d.embedding_runtime_failed")
        self.assertEqual(dict(batch.provenance[0].parameters)["outcome_code"], "smiles_3d.embedding_runtime_failed")

    def test_runtime_error_messages_do_not_create_same_identity_with_different_diagnostics(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        with patch("rdkit.Chem.AllChem.EmbedMolecule", side_effect=RuntimeError("first detail")):
            first = derive_smiles_3d(structure, topology, record, source_revision)
        with patch("rdkit.Chem.AllChem.EmbedMolecule", side_effect=RuntimeError("second detail")):
            second = derive_smiles_3d(structure, topology, record, source_revision)
        self.assertEqual(first.provenance[0].revision, second.provenance[0].revision)
        self.assertEqual(first.diagnostics[0].id, second.diagnostics[0].id)
        self.assertEqual(first.diagnostics[0].message, second.diagnostics[0].message)

    def test_recoverable_force_field_parameter_error_is_incomplete(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        with patch("rdkit.Chem.AllChem.MMFFHasAllMoleculeParams", side_effect=RuntimeError("parameters")):
            batch = derive_smiles_3d(structure, topology, record, source_revision)
        self.assertEqual(batch.calculations[0].status, CalculationStatus.INCOMPLETE)
        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(batch.diagnostics[0].code, "smiles_3d.force_field_setup_failed")
        self.assertEqual(dict(batch.provenance[0].parameters)["outcome_code"], "smiles_3d.force_field_setup_failed")

    def test_nonnegative_embedding_conformer_id_is_successful(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d
        from rdkit.Chem import AllChem

        structure, topology, record, source_revision = self.source()
        embed = AllChem.EmbedMolecule
        with patch("rdkit.Chem.AllChem.EmbedMolecule", side_effect=lambda *args: (embed(*args), 7)[1]):
            batch = derive_smiles_3d(structure, topology, record, source_revision)
        self.assertNotEqual(batch.calculations[0].status, CalculationStatus.FAILED)
        self.assertEqual(dict(batch.provenance[0].parameters)["embed_code"], 7)

    def test_result_identities_distinguish_success_partial_and_embedding_failure(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        success = derive_smiles_3d(structure, topology, record, source_revision)
        with patch("rdkit.Chem.AllChem.MMFFOptimizeMolecule", return_value=1):
            partial = derive_smiles_3d(structure, topology, record, source_revision)
        with patch("rdkit.Chem.AllChem.EmbedMolecule", return_value=-1):
            failed = derive_smiles_3d(structure, topology, record, source_revision)
        self.assertEqual(len({success.provenance[0].revision, partial.provenance[0].revision, failed.provenance[0].revision}), 3)
        self.assertTrue(dict(success.provenance[0].parameters)["rdkit_version"])
        self.assertIsNotNone(dict(success.provenance[0].parameters)["coordinates_digest"])

    def test_partial_outcome_code_distinguishes_same_coordinate_result_identity(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        with patch("rdkit.Chem.AllChem.MMFFHasAllMoleculeParams", return_value=False):
            unavailable = derive_smiles_3d(structure, topology, record, source_revision)
        with patch("rdkit.Chem.AllChem.MMFFOptimizeMolecule", side_effect=RuntimeError("setup")):
            setup_failed = derive_smiles_3d(structure, topology, record, source_revision)
        self.assertEqual(unavailable.calculations[0].status, CalculationStatus.INCOMPLETE)
        self.assertEqual(setup_failed.calculations[0].status, CalculationStatus.INCOMPLETE)
        self.assertNotEqual(unavailable.provenance[0].revision, setup_failed.provenance[0].revision)
        self.assertEqual(dict(unavailable.provenance[0].parameters)["outcome_code"], "smiles_3d.force_field_unavailable")
        self.assertEqual(dict(setup_failed.provenance[0].parameters)["outcome_code"], "smiles_3d.optimization_setup_failed")

    def test_derivation_reconstructs_stereo_and_aromatic_bracket_h_from_exact_smiles(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        stereo = self._source_batch("C/C=C/C")
        aromatic = self._source_batch("c1cc[nH]c1")
        stereo_result = derive_smiles_3d(stereo.structures[0], stereo.topologies[0], stereo.molecular_records[0], stereo.source_revisions[0])
        aromatic_result = derive_smiles_3d(aromatic.structures[0], aromatic.topologies[0], aromatic.molecular_records[0], aromatic.source_revisions[0])
        self.assertIn("E", stereo_result.topologies[0].stereo_labels)
        self.assertGreater(len(aromatic_result.structures[0].atomic_numbers), len(aromatic.structures[0].atomic_numbers))

    def test_cancellation_and_fatal_errors_are_not_converted_to_partial_results(self):
        from ChemBlender.core.derivations.smiles_3d import Smiles3DCancelled, derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        with self.assertRaises(Smiles3DCancelled):
            derive_smiles_3d(structure, topology, record, source_revision, is_cancelled=lambda: True)
        with patch("rdkit.Chem.AllChem.MMFFOptimizeMolecule", side_effect=MemoryError("fatal")):
            with self.assertRaises(MemoryError):
                derive_smiles_3d(structure, topology, record, source_revision)

    def test_failed_optimization_retains_embedded_coordinates_as_partial(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        with patch("rdkit.Chem.AllChem.MMFFOptimizeMolecule", return_value=1):
            batch = derive_smiles_3d(structure, topology, record, source_revision)

        self.assertEqual(batch.calculations[0].status, CalculationStatus.INCOMPLETE)
        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(batch.topologies[0].quality_status, QualityStatus.COMPLETE)
        self.assertEqual(batch.diagnostics[0].code, "smiles_3d.optimization_incomplete")
        self.assertTrue(numpy.isfinite(batch.structures[0].coordinates.values).all())

    def test_derived_batch_uses_the_real_source_revision_and_commits_to_project(self):
        from ChemBlender.core import QCProject
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d
        source = self._source_batch("CCO")
        project = QCProject(id=uuid4(), schema_version="1.0")
        project.commit(source)
        result = derive_smiles_3d(
            source.structures[0], source.topologies[0], source.molecular_records[0], source.source_revisions[0]
        )

        self.assertEqual(
            result.diagnostics,
            (),
        )
        project.commit(result)
        self.assertIn(result.structures[0].id, project.structures)

    def test_parameters_change_derivation_identity_and_add_hydrogens_is_explicit(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        with_hydrogens = derive_smiles_3d(structure, topology, record, source_revision)
        without_hydrogens = derive_smiles_3d(
            structure, topology, record, source_revision, add_hydrogens=False, force_field="UFF", max_iterations=50
        )
        self.assertNotEqual(with_hydrogens.structures[0].id, without_hydrogens.structures[0].id)
        self.assertGreater(len(with_hydrogens.structures[0].atomic_numbers), len(structure.atomic_numbers))
        self.assertEqual(without_hydrogens.structures[0].atomic_numbers, structure.atomic_numbers)
        self.assertEqual(dict(without_hydrogens.provenance[0].parameters)["max_iterations"], 50)

    def test_rdkit_signed_int_parameters_are_rejected_at_python_boundary(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d

        structure, topology, record, source_revision = self.source()
        with self.assertRaisesRegex(ValueError, "random_seed.*32-bit"):
            derive_smiles_3d(structure, topology, record, source_revision, random_seed=2_147_483_648)
        with self.assertRaisesRegex(ValueError, "max_iterations.*32-bit"):
            derive_smiles_3d(structure, topology, record, source_revision, max_iterations=2_147_483_648)

    def test_disconnected_input_is_a_failed_calculation_with_no_derived_structure(self):
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d
        source = self._source_batch("CC.O")
        batch = derive_smiles_3d(source.structures[0], source.topologies[0], source.molecular_records[0], source.source_revisions[0])
        self.assertEqual(batch.calculations[0].status, CalculationStatus.FAILED)
        self.assertEqual(batch.structures, ())
        self.assertEqual(batch.diagnostics[0].code, "smiles_3d.disconnected")

    def test_partial_and_failed_derivations_commit_to_the_source_project(self):
        from ChemBlender.core import QCProject
        from ChemBlender.core.derivations.smiles_3d import derive_smiles_3d
        for outcome in ("partial", "failed"):
            with self.subTest(outcome=outcome):
                source = self._source_batch("CCO")
                project = QCProject(id=uuid4(), schema_version="1.0")
                project.commit(source)
                target = "rdkit.Chem.AllChem.MMFFOptimizeMolecule" if outcome == "partial" else "rdkit.Chem.AllChem.EmbedMolecule"
                with patch(target, return_value=-1):
                    batch = derive_smiles_3d(source.structures[0], source.topologies[0], source.molecular_records[0], source.source_revisions[0])
                project.commit(batch)
                self.assertIn(batch.calculations[0].id, project.calculations)

    def _source_batch(self, text):
        from pathlib import Path
        from ChemBlender.core import builtin_reader_registry
        from ChemBlender.core.import_pipeline.preflight import preflight_import
        from ChemBlender.core.import_pipeline.request import ImportRequest, ImportSource
        from ChemBlender.core.import_pipeline.staging import StagedImportSession

        source = ImportSource.smiles_text(text)
        with TemporaryDirectory() as directory:
            session = StagedImportSession.create(temp_parent=Path(directory))
            try:
                preview = preflight_import(
                    ImportRequest((source,)), builtin_reader_registry(), session
                )
                return session.result(preview.staged_batch_ids[0])
            finally:
                session.discard()


if __name__ == "__main__":
    unittest.main()
