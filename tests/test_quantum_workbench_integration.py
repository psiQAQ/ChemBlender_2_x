"""Workbench boundaries; real IOData/GBasis checks skip absent optional stacks."""

import hashlib
import importlib.util
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import numpy

from cbq_core.model import DensityMatrixLevel
from cbq_core.model import DensityMatrixSpin
from chemblender_prepare.core.import_pipeline import ImportSource
from chemblender_prepare.core.import_pipeline import ValidationMode
from chemblender_prepare.core.import_pipeline.parse import stage_import_batch
from chemblender_prepare.core.iodata_adapter import adapt_iodata
from cbq_core.worker_protocol import WorkerResult
from cbq_core.worker_protocol import WorkerStatus
from chemblender_prepare.reader_api.builtin_bridge import public_batch_from_internal
from chemblender_prepare.reader_api.canonical_document import write_public_batch_bundle
from chemblender_prepare.reader_api.worker_bridge import WorkerReaderIntegrityError
from chemblender_prepare import cli as importer
from cbq_core.model import QCProject
from concurrent.futures import CancelledError
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


def load_reader(source, reader_id, temp_parent, *, parameters=None, companions=None, cancel=None):
    """Exercise the same frozen reader/typed bundle boundary used by convert."""
    with TemporaryDirectory(prefix="reader-test-", dir=temp_parent) as temporary:
        directory = Path(temporary)
        cancel = Path(cancel) if cancel else directory / "cancel"
        importer._check(cancel)
        return importer._reader_batch(source, reader_id, parameters or {}, companions or {},
            directory, QCProject(uuid4(), "1.1"), cancel, "balanced")


def synthetic_result(request, task, batch):
    source = task / request.parameters["source_artifact"]
    parameters = request.parameters["canonical_parameters"]
    staged = stage_import_batch(
        source=ImportSource(source), validation_mode=ValidationMode.BALANCED,
        content_hash=_hash(source), byte_size=source.stat().st_size,
        plugin_id="chemblender.builtin", reader_id=request.parameters["reader_id"],
        reader_version="1", api_version="1.0-rc1", canonical_parameters=tuple(sorted(parameters.items())),
        parsed_batch=batch, revision_id=request.request_id)
    bundle = task / "reader-bundle"
    document = write_public_batch_bundle(bundle, public_batch_from_internal(staged))
    hashes = {path.relative_to(task).as_posix(): _hash(path) for path in (bundle / "artifacts").glob("*.npy")}
    return WorkerResult(request.request_id, WorkerStatus.SUCCESS,
        artifacts=(document.relative_to(task).as_posix(), *hashes), metadata={
            "operation": "reader.parse@0.1", "schema_version": "0.1",
            "document_path": document.relative_to(task).as_posix(),
            "document_sha256": _hash(document), "artifact_sha256": hashes})


class WavefunctionImportBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "original.molden.input"
        self.source.write_bytes(b"[Molden Format]\n[Atoms] AU\n")
        self.tasks = []
        descriptor = SimpleNamespace(reader_id="iodata_wavefunction",
            availability=SimpleNamespace(available=True))
        self.descriptor = patch.object(importer, "_descriptor", return_value=descriptor)
        self.descriptor.start()
        self.addCleanup(self.descriptor.stop)

    def load(self, **kwargs):
        return load_reader(self.source, "iodata_wavefunction", self.root, **kwargs)

    def worker(self, request, directory, cancel):
        self.tasks.append(directory)
        source = directory / request.parameters["source_artifact"]
        self.assertEqual(source.name, self.source.name)
        self.assertEqual(_hash(source), request.parameters["source_sha256"])
        return synthetic_result(request, directory, adapt_iodata(fake_iodata(), source, iodata_version="synthetic"))

    def test_verified_import_detaches_arrays_and_restores_source_identity(self):
        with patch.object(importer, "_run_worker", side_effect=self.worker):
            batch = self.load()
        self.assertTrue(all(not path.exists() for path in self.tasks))
        self.assertEqual(batch.source_revisions[0].locator, str(self.source))
        self.assertEqual(batch.source_revisions[0].content_hash, _hash(self.source))
        self.assertEqual(batch.sources[0].display_name, self.source.name)
        self.assertEqual(batch.provenance[0].source, str(self.source))
        numpy.testing.assert_allclose(batch.orbital_sets[0].channels[0].coefficients.values, [[1, 0], [.2, .8]])
        project = QCProject(uuid4(), "1.1")
        project.commit(batch)
        self.assertEqual(len(project.structures), 1)
        self.assertEqual(len(project.orbital_sets), 1)
        self.assertEqual(len(project.density_matrices), 1)

    def test_tampered_source_bundle_and_worker_identity_are_rejected(self):
        for failure in ("source", "artifact", "identity"):
            self.source.write_bytes(b"[Molden Format]\n[Atoms] AU\n")
            def worker(request, directory, cancel):
                result = self.worker(request, directory, cancel)
                if failure == "source":
                    self.source.write_bytes(b"[Molden Format]\nchanged")
                elif failure == "artifact":
                    next((directory / "reader-bundle/artifacts").glob("*.npy")).write_bytes(b"tampered")
                else:
                    result = replace(result, request_id=uuid4())
                return result
            with self.subTest(failure=failure), patch.object(importer, "_run_worker", side_effect=worker):
                with self.assertRaises((ValueError, WorkerReaderIntegrityError)):
                    self.load()
            self.assertTrue(all(not path.exists() for path in self.tasks))

    def test_cancel_before_and_during_parsing_cleans_owned_workspace(self):
        cancel = self.root / "cancel"
        cancel.touch()
        with patch.object(importer, "_run_worker") as run:
            with self.assertRaises(CancelledError):
                self.load(cancel=cancel)
            run.assert_not_called()
        cancel.unlink()
        def worker(request, directory, cancel):
            result = self.worker(request, directory, cancel)
            cancel.touch()
            return result
        with patch.object(importer, "_run_worker", side_effect=worker):
            with self.assertRaises(CancelledError):
                self.load(cancel=cancel)
        self.assertTrue(all(not path.exists() for path in self.tasks))


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
        return load_reader(self.fixture(name), "iodata_wavefunction", temporary)


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
        from chemblender_prepare.core.wavefunction_observables import derive_density_matrix_from_orbitals
        from chemblender_prepare.core.wavefunction_observables import evaluate_density_matrix_grid
        from chemblender_prepare.core.wavefunction_observables import evaluate_electrostatic_potential_grid
        from chemblender_prepare.core.wavefunction_grid import evaluate_electron_density_grid
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
            with self.assertRaisesRegex(ValueError, "unavailable"):
                self._load("water_sto3g_hf_g03.fchk", temporary)
            self.assertFalse(tuple(Path(temporary).iterdir()))


if __name__ == "__main__":
    unittest.main()
