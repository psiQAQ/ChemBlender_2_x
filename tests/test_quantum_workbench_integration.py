"""Workbench boundaries; real IOData/GBasis checks skip absent optional stacks."""

import hashlib
import importlib.util
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import numpy

from ChemBlender.core import close_session, create_session, DensityMatrixLevel, DensityMatrixSpin
from ChemBlender.core.import_pipeline import ImportCancelled, ImportSource, ValidationMode
from ChemBlender.core.import_pipeline.parse import stage_import_batch
from ChemBlender.core.iodata_adapter import adapt_iodata
from ChemBlender.core.worker_protocol import WorkerError, WorkerResult, WorkerStatus, write_result
from ChemBlender.reader_api.builtin_bridge import public_batch_from_internal
from ChemBlender.reader_api.canonical_document import write_public_batch_bundle
from ChemBlender.reader_api.worker_bridge import WorkerReaderExecutionError, WorkerReaderIntegrityError
from ChemBlender.ui import wavefunction_import as importer
from ChemBlender.worker_client import start_worker
from tests.test_iodata_adapter import fake_iodata


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "submodules" / "iodata" / "iodata" / "test" / "data"
PINNED_FIXTURES = {
    "water_sto3g_hf_g03.fchk": "aa8dec77849d4f9e1e9dc9357c80f5b4d6ba1efc3bbc17da6c59754bdaed0816",
    "ch3_hf_sto3g.fchk": "b5b33475a6766447a287e6cf16ac6111eb489a5985743413b056ac2e7a4c384c",
    "h2o.molden.input": "2bf025dc02fdb689e61c980ac55dc4bef35a31e4bfc819a668ac36d721f44f06",
}
HAS_IODATA = importlib.util.find_spec("iodata") is not None
HAS_GBASIS = importlib.util.find_spec("gbasis") is not None


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class WavefunctionImportBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "original.molden.input"
        self.source.write_bytes(b"[Molden Format]\n[Atoms] AU\n")
        self.task_directories = []
        self.handles = []

    def tearDown(self):
        self.temporary.cleanup()

    def _load(self, **kwargs):
        return importer.load_wavefunction_batch(
            self.source, python_executable=sys.executable, repository=ROOT,
            project_id=uuid4(), schema_version="0.2",
            temp_parent=kwargs.pop("temp_parent", self.root), **kwargs,
        )

    def _synthetic_worker(self, request, workspace, **kwargs):
        """Mock only the process/parser, retaining canonical bundle verification."""
        process = Mock()
        process.poll.return_value = 0
        process.wait.return_value = 0
        with patch("ChemBlender.worker_client.subprocess.Popen", return_value=process):
            handle = start_worker(request, workspace, **kwargs)
        self.handles.append(handle)
        task = handle.request_path.parent
        self.task_directories.append(task)
        source = task / request.parameters["source_artifact"]
        self.assertEqual(source.name, "source.molden")
        self.assertEqual(_hash(source), request.parameters["source_sha256"])
        batch = stage_import_batch(
            source=ImportSource(source), validation_mode=ValidationMode.BALANCED,
            content_hash=_hash(source), byte_size=source.stat().st_size,
            plugin_id="chemblender.builtin", reader_id="iodata_wavefunction",
            reader_version="1", api_version="1.0-rc1",
            parsed_batch=adapt_iodata(fake_iodata(), source, iodata_version="synthetic"),
            revision_id=request.request_id,
        )
        bundle = task / "reader-bundle"
        document = write_public_batch_bundle(bundle, public_batch_from_internal(batch))
        hashes = {path.relative_to(task).as_posix(): _hash(path)
                  for path in (bundle / "artifacts").glob("*.npy")}
        document_path = document.relative_to(task).as_posix()
        result = WorkerResult(request.request_id, WorkerStatus.SUCCESS,
            artifacts=(document_path, *hashes), metadata={
                "operation": "reader.parse@0.1", "schema_version": "0.1",
                "document_path": document_path, "document_sha256": _hash(document),
                "artifact_sha256": hashes,
            })
        write_result(handle.result_path, result)
        return handle

    def test_verified_import_detaches_arrays_rebinds_source_and_commits(self):
        with patch.object(importer, "start_worker", side_effect=self._synthetic_worker):
            batch = self._load()
        self.assertTrue(all(not path.exists() for path in self.task_directories))
        revision = batch.source_revisions[0]
        self.assertEqual(revision.locator, str(self.source))
        self.assertEqual(revision.original_filename, self.source.name)
        self.assertEqual(revision.content_hash, _hash(self.source))
        self.assertEqual(batch.sources[0].display_name, self.source.name)
        self.assertEqual(batch.provenance[0].source, str(self.source))
        self.assertEqual(batch.provenance[0].source_hash, _hash(self.source))
        numpy.testing.assert_allclose(batch.orbital_sets[0].channels[0].coefficients.values,
                                      [[1, 0], [0.2, 0.8]])
        session = create_session(temp_parent=self.root)
        try:
            importer.commit_wavefunction_batch(session, batch)
            self.assertEqual(session.active_entity_id, batch.orbital_sets[0].id)
            self.assertEqual(len(session.project.structures), 1)
            self.assertEqual(len(session.project.orbital_sets), 1)
            self.assertEqual(len(session.project.density_matrices), 1)
            previous = session.project
            with self.assertRaisesRegex(ValueError, "already imported"):
                importer.commit_wavefunction_batch(session, batch)
            self.assertIs(session.project, previous)
            self.assertEqual(len(session.project.source_revisions), 1)
        finally:
            close_session(session)

    def test_standard_blender_session_depth_allows_full_hash_artifacts(self):
        # A normal Blender temp/session prefix on Windows is already 91 chars.
        parent = self.root / ("s" * max(1, 91 - len(str(self.root)) - 1))
        parent.mkdir()
        with patch.object(importer, "start_worker", side_effect=self._synthetic_worker):
            batch = self._load(temp_parent=parent)
        self.assertTrue(batch.orbital_sets)
        for task in self.task_directories:
            self.assertLess(len(str(task / "reader-bundle" / "artifacts" / ("0" * 64 + ".npy"))), 260)
        self.assertFalse(tuple(parent.iterdir()))

    @unittest.skipUnless(sys.platform == "win32", "Windows executable path limit")
    def test_deep_temporary_root_is_rejected_before_launch(self):
        for component in ("d" * 110, "\U0001f52c" * 55):
            with self.subTest(component=component):
                parent = self.root / component
                parent.mkdir()
                with patch.object(importer, "start_worker") as launch:
                    with self.assertRaisesRegex(ValueError, "shorter Temporary Files directory"):
                        self._load(temp_parent=parent)
                    launch.assert_not_called()
                self.assertFalse(tuple(parent.iterdir()))

    def test_failed_publication_preserves_project(self):
        with patch.object(importer, "start_worker", side_effect=self._synthetic_worker):
            batch = self._load()
        session = create_session(temp_parent=self.root)
        previous = session.project
        try:
            with patch("ChemBlender.core.import_pipeline.transaction.solidify_session",
                       side_effect=OSError("injected disk failure")):
                with self.assertRaisesRegex(OSError, "disk failure"):
                    importer.commit_wavefunction_batch(session, batch)
            self.assertIs(session.project, previous)
            self.assertFalse(session.project.orbital_sets)
            self.assertFalse(session.dirty)
            self.assertFalse(tuple((session.temporary_root / "chemblender-import-staging").iterdir()))
        finally:
            close_session(session)

    def test_missing_reader_diagnosis_requires_matching_worker_result(self):
        for matching_id in (True, False):
            with self.subTest(matching_id=matching_id):
                def launch(request, workspace, **kwargs):
                    handle = self._synthetic_worker(request, workspace, **kwargs)
                    result = WorkerResult(
                        request.request_id if matching_id else uuid4(), WorkerStatus.ERROR,
                        error=WorkerError("reader_unavailable", "reader unavailable"),
                    )
                    write_result(handle.result_path, result)
                    return handle
                with patch.object(importer, "start_worker", side_effect=launch):
                    if matching_id:
                        with self.assertRaisesRegex(WorkerReaderExecutionError, "qc-iodata") as raised:
                            self._load()
                        self.assertIn(sys.executable, str(raised.exception))
                        self.assertIn("Worker Setup", str(raised.exception))
                    else:
                        with self.assertRaisesRegex(WorkerReaderIntegrityError, "request ID mismatch"):
                            self._load()
                self.assertTrue(all(not path.exists() for path in self.task_directories))

    def test_changed_source_and_tampered_artifact_never_return_a_batch(self):
        for tamper in ("source", "artifact"):
            with self.subTest(tamper=tamper):
                self.source.write_bytes(b"[Molden Format]\n[Atoms] AU\n")
                def launch(request, workspace, **kwargs):
                    handle = self._synthetic_worker(request, workspace, **kwargs)
                    if tamper == "source":
                        self.source.write_bytes(b"[Molden Format]\nchanged content")
                    else:
                        next((handle.request_path.parent / "reader-bundle" / "artifacts").glob("*.npy")).write_bytes(b"tampered")
                    return handle
                with patch.object(importer, "start_worker", side_effect=launch):
                    with self.assertRaises((ValueError, WorkerReaderIntegrityError)):
                        self._load()
                self.assertTrue(all(not path.exists() for path in self.task_directories))

    def test_cancel_before_launch_and_invalid_content_have_no_process(self):
        with patch.object(importer, "start_worker") as launch:
            with self.assertRaises(ImportCancelled):
                self._load(is_cancelled=lambda: True)
            self.source.write_text("ordinary text", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content"):
                self._load()
            launch.assert_not_called()

    def test_cancel_while_parsing_stops_owned_process_and_cleans_workspace(self):
        cancelled = [False]
        def launch(request, workspace, **kwargs):
            process = Mock()
            process.poll.return_value = None
            with patch("ChemBlender.worker_client.subprocess.Popen", return_value=process):
                handle = start_worker(request, workspace, **kwargs)
            def poll():
                cancelled[0] = True
                return None
            handle.process.poll = Mock(side_effect=poll)
            self.handles.append(handle)
            self.task_directories.append(handle.request_path.parent)
            return handle
        with patch.object(importer, "start_worker", side_effect=launch):
            with self.assertRaises(ImportCancelled):
                self._load(is_cancelled=lambda: cancelled[0])
        self.handles[0].process.terminate.assert_called_once()
        self.assertFalse(self.task_directories[0].exists())

    def test_session_cleanup_cancels_joins_and_releases_only_its_import(self):
        session, other_session = object(), object()
        operator = Mock(_session=session)
        other = Mock(_session=other_session)
        with patch.object(importer, "_ACTIVE_IMPORTS", [operator, other]):
            importer._cancel_session_imports(session)
        operator._job.request_cancel.assert_called_once()
        operator._job.join.assert_called_once_with()
        operator._finish_modal.assert_called_once()
        other._job.request_cancel.assert_not_called()

    @unittest.skipUnless(importer.bpy is not None, "requires the real Blender operator class")
    def test_blender_file_selector_cancel_before_execute(self):
        operator_type = importer.CHEMBLENDER_OT_import_wavefunction
        # ImportHelper may cancel before execute initializes any job or timer.
        operator = SimpleNamespace()
        operator._finish_modal = lambda: operator_type._finish_modal(operator)
        operator_type.cancel(operator, None)
        operator_type._finish_modal(operator)


class RealWavefunctionWorkbenchTests(unittest.TestCase):
    def fixture(self, name):
        path = FIXTURES / name
        if not path.is_file():
            self.skipTest("pinned IOData fixture submodule is not initialized")
        return path

    def test_pinned_fixture_bytes(self):
        for name, digest in PINNED_FIXTURES.items():
            self.assertEqual(_hash(self.fixture(name)), digest, name)

    def _load(self, name, temporary):
        return importer.load_wavefunction_batch(
            self.fixture(name), python_executable=sys.executable, repository=ROOT,
            project_id=uuid4(), schema_version="0.2", temp_parent=Path(temporary),
        )

    @unittest.skipUnless(HAS_IODATA, "external Python needs optional qc-iodata")
    def test_real_fchk_and_molden_cross_worker_boundary(self):
        for name in PINNED_FIXTURES:
            with self.subTest(name=name), TemporaryDirectory() as temporary:
                batch = self._load(name, temporary)
                structure, basis, orbitals = batch.structures[0], batch.basis_sets[0], batch.orbital_sets[0]
                self.assertEqual(structure.coordinates.unit, "bohr")
                self.assertEqual(basis.structure_id, structure.id)
                self.assertEqual(orbitals.basis_set_id, basis.id)
                self.assertEqual(orbitals.structure_id, structure.id)
                self.assertEqual(batch.source_revisions[0].content_hash, PINNED_FIXTURES[name])
                self.assertEqual(batch.provenance[0].source, str(self.fixture(name)))
                charges = next(data for data in batch.datasets if data.semantic_role == "nuclear_charge")
                self.assertEqual(charges.structure_id, structure.id)
                self.assertEqual(charges.data.unit, "elementary_charge")
                if name.endswith(".fchk"):
                    self.assertTrue(any(matrix.spin_role is DensityMatrixSpin.TOTAL for matrix in batch.density_matrices))
                else:
                    self.assertFalse(batch.density_matrices)
                if name.startswith("ch3"):
                    self.assertEqual(tuple(channel.label for channel in orbitals.channels), ("alpha", "beta"))

    @unittest.skipUnless(HAS_IODATA, "external Python needs optional qc-iodata")
    def test_real_ghost_nuclear_charge_is_not_atomic_number(self):
        with TemporaryDirectory() as temporary:
            batch = self._load("he2_ghost_psi4_1.0.molden", temporary)
        charges = next(data for data in batch.datasets if data.semantic_role == "nuclear_charge")
        numpy.testing.assert_array_equal(charges.data.values, [0.0, 2.0])
        self.assertEqual(batch.structures[0].atomic_numbers, (2, 2))

    @unittest.skipUnless(HAS_IODATA and HAS_GBASIS, "external Python needs optional qc-iodata and qc-gbasis")
    def test_molden_explicit_density_derivation_drives_density_and_esp(self):
        from ChemBlender.core.wavefunction_observables import (
            derive_density_matrix_from_orbitals, evaluate_density_matrix_grid,
            evaluate_electrostatic_potential_grid,
        )
        from ChemBlender.core.wavefunction_grid import evaluate_electron_density_grid
        with TemporaryDirectory() as temporary:
            batch = self._load("h2o.molden.input", temporary)
        structure, basis, orbitals = batch.structures[0], batch.basis_sets[0], batch.orbital_sets[0]
        derived = derive_density_matrix_from_orbitals(
            structure, basis, orbitals, level=DensityMatrixLevel.SCF, source_provenance=batch.provenance,
        )
        matrix = derived.density_matrices[0]
        self.assertIs(matrix.spin_role, DensityMatrixSpin.TOTAL)
        self.assertTrue(derived.provenance)
        grid = dict(origin=(1.8, 1.5, 2.0), step_vectors=((0.2, 0, 0), (0.05, 0.2, 0), (0, 0.05, 0.2)), shape=(2, 2, 2))
        density = evaluate_density_matrix_grid(structure, basis, matrix, **grid).datasets[0]
        reference = evaluate_electron_density_grid(structure, basis, orbitals, **grid).datasets[0]
        numpy.testing.assert_allclose(density.data.values, reference.data.values, rtol=1e-10, atol=1e-12)
        charges = next(data for data in batch.datasets if data.semantic_role == "nuclear_charge")
        esp = evaluate_electrostatic_potential_grid(structure, basis, matrix, charges, **grid).datasets[0]
        self.assertTrue(numpy.isfinite(esp.data.values).all())
        self.assertEqual(esp.structure_id, structure.id)
        unsupported = replace(orbitals, channels=(replace(orbitals.channels[0], occupations=None),))
        with self.assertRaises((ValueError, NotImplementedError)):
            derive_density_matrix_from_orbitals(structure, basis, unsupported,
                level=DensityMatrixLevel.SCF, source_provenance=batch.provenance)

    @unittest.skipIf(HAS_IODATA, "missing dependency boundary requires a Python without qc-iodata")
    def test_missing_external_dependency_fails_without_residue(self):
        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(WorkerReaderExecutionError, "qc-iodata") as raised:
                self._load("water_sto3g_hf_g03.fchk", temporary)
            self.assertIn(sys.executable, str(raised.exception))
            self.assertIn("Worker Setup", str(raised.exception))
            self.assertFalse(tuple(Path(temporary).iterdir()))


if __name__ == "__main__":
    unittest.main()
