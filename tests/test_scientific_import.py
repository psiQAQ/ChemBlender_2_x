"""External reader staging, companion provenance and explicit scientific options."""

import hashlib
import importlib.util
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from ChemBlender.core import ImportBatch, ProvenanceRecord, close_session, create_session
from ChemBlender.core import phonopy_adapter, pymatgen_electronic
from ChemBlender.core.import_pipeline import ImportSource, ValidationMode
from ChemBlender.core.import_pipeline.parse import stage_import_batch
from ChemBlender.core.worker_protocol import WorkerResult, WorkerStatus, write_result
from ChemBlender.reader_api.builtin_bridge import public_batch_from_internal
from ChemBlender.reader_api.canonical_document import write_public_batch_bundle
from ChemBlender.reader_api.protocol import ParseRequest
from ChemBlender.ui import scientific_import as ui, wavefunction_import as importer
from ChemBlender.worker_client import start_worker
from tests.test_vibration_model import structure, mode_set
from tests.test_fermi_surface_model import fermi_surface
from tests.test_periodic_electronic_model import band_structure, periodic_structure


ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "examples" / "scientific-visualization" / "inputs"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ScientificImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "original.xml"
        self.source.write_bytes(b"synthetic reader boundary input")
        self.companion = self.root / "original.KPOINTS"
        self.companion.write_bytes(b"synthetic companion")
        self.tasks = []
        self.handles = []

    def tearDown(self):
        for handle in self.handles:
            handle.terminate()
        self.temporary.cleanup()

    def load(self, **kwargs):
        return importer.load_reader_batch(self.source, reader_id="pymatgen-vasprun-electronic",
            companions={"kpoints": self.companion}, canonical_parameters={"line_mode": "true"},
            python_executable=sys.executable, repository=ROOT, project_id=uuid4(),
            schema_version="0.2", temp_parent=self.root, **kwargs)

    def worker(self, request, workspace, **kwargs):
        process = Mock()
        process.poll.return_value = process.wait.return_value = 0
        with patch("ChemBlender.worker_client.subprocess.Popen", return_value=process):
            handle = start_worker(request, workspace, **kwargs)
        self.handles.append(handle)
        task = handle.request_path.parent
        self.tasks.append(task)
        source = task / request.parameters["source_artifact"]
        parameters = request.parameters["canonical_parameters"]
        companion = task / parameters["kpoints_artifact"]
        self.assertEqual(digest(companion), parameters["kpoints_sha256"])
        provenance = tuple(ProvenanceRecord(uuid4(), digest(path), "synthetic input", "1",
            str(path), digest(path), (), "read_input", ()) for path in (source, companion))
        reference = structure()
        modes = replace(mode_set(reference.id), provenance_ids=tuple(record.id for record in provenance))
        batch = stage_import_batch(source=ImportSource(source), validation_mode=ValidationMode.BALANCED,
            content_hash=digest(source), byte_size=source.stat().st_size, plugin_id="chemblender.builtin",
            reader_id=request.parameters["reader_id"], reader_version="2", api_version="1.0-rc1",
            canonical_parameters=tuple(sorted(parameters.items())), revision_id=request.request_id,
            parsed_batch=ImportBatch(structures=(reference,), datasets=(modes,), provenance=provenance))
        bundle = task / "reader-bundle"
        document = write_public_batch_bundle(bundle, public_batch_from_internal(batch))
        hashes = {path.relative_to(task).as_posix(): digest(path) for path in (bundle / "artifacts").glob("*.npy")}
        document_path = document.relative_to(task).as_posix()
        write_result(handle.result_path, WorkerResult(request.request_id, WorkerStatus.SUCCESS,
            artifacts=(document_path, *hashes), metadata={"operation": "reader.parse@0.1", "schema_version": "0.1",
                "document_path": document_path, "document_sha256": digest(document), "artifact_sha256": hashes}))
        return handle

    def test_companions_are_copied_hashed_restored_and_committed_once(self):
        with patch.object(importer, "start_worker", side_effect=self.worker):
            batch = self.load()
        self.assertFalse(any(path.exists() for path in self.tasks))
        self.assertEqual({record.source for record in batch.provenance}, {str(self.source), str(self.companion)})
        self.assertEqual(batch.source_revisions[0].locator, str(self.source))
        self.assertTrue(any(record.source_hash == digest(self.companion) for record in batch.provenance))
        session = create_session(temp_parent=self.root)
        try:
            importer.commit_reader_batch(session, batch)
            self.assertEqual(session.active_entity_id, batch.datasets[0].id)
            self.assertEqual(len(session.project.source_revisions), 1)
            with self.assertRaisesRegex(ValueError, "already imported"):
                importer.commit_reader_batch(session, batch)
        finally:
            close_session(session)

    def test_changed_original_or_staged_companion_never_publishes(self):
        for location in ("original", "staged"):
            self.companion.write_bytes(b"synthetic companion")
            def worker(*args, **kwargs):
                handle = self.worker(*args, **kwargs)
                path = self.companion if location == "original" else handle.request_path.parent / "KPOINTS"
                path.write_bytes(b"changed")
                return handle
            with self.subTest(location=location), patch.object(importer, "start_worker", side_effect=worker):
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.load()
        self.assertFalse(any(path.exists() for path in self.tasks))

    def request(self, parameters):
        return ParseRequest(self.source, digest(self.source), "balanced", parameters,
                            self.root, lambda _event: None, lambda: False)

    def test_vasp_request_passes_explicit_mode_and_verifies_companion(self):
        staged = self.root / "KPOINTS"
        staged.write_bytes(self.companion.read_bytes())
        parameters = {"line_mode": "true", "kpoints_artifact": "KPOINTS", "kpoints_sha256": digest(staged)}
        with patch.object(pymatgen_electronic, "parse_vasprun_electronic", return_value="batch") as parse:
            self.assertEqual(pymatgen_electronic.parse_vasprun_electronic_request(self.request(parameters)), "batch")
            parse.assert_called_once_with(self.source, kpoints_filename=staged, line_mode=True)
            for bad in ({**parameters, "kpoints_artifact": "../KPOINTS"}, {**parameters, "kpoints_sha256": "0" * 64}, {"line_mode": "auto"}):
                with self.assertRaises(ValueError):
                    pymatgen_electronic.parse_vasprun_electronic_request(self.request(bad))
            self.assertEqual(parse.call_count, 1)

    def test_phonopy_request_requires_explicit_forces_and_passes_qpoint_options(self):
        forces = self.root / "FORCE_SETS"
        forces.write_bytes(b"synthetic force set")
        parameters = {"force_sets_artifact": "FORCE_SETS", "force_sets_sha256": digest(forces),
                      "qpoints": "[[0.25,0,0]]", "with_group_velocities": "true"}
        request = self.request(parameters)
        with patch.object(phonopy_adapter, "parse_phonopy_file", return_value="batch") as parse:
            self.assertEqual(phonopy_adapter.parse_phonopy_request(request), "batch")
            parse.assert_called_once_with(self.source, force_sets_filename=forces, born_filename=None,
                qpoints=[[.25, 0, 0]], nac_q_direction=None, with_group_velocities=True, cancel_check=request.is_cancelled)
            with self.assertRaises(ValueError):
                phonopy_adapter.parse_phonopy_request(self.request({}))
            self.assertEqual(parse.call_count, 1)

    def test_ui_options_validate_explicit_modes_and_nonfinite_coordinates(self):
        settings = SimpleNamespace(reader_id="pymatgen-vasprun-electronic", line_mode="true", kpoints_file="")
        with self.assertRaisesRegex(ValueError, "matching KPOINTS"):
            ui.reader_options(settings)
        settings = SimpleNamespace(reader_id="phonopy-file", force_sets_file="FORCE_SETS", born_file="BORN",
            qpoints="0,0,0", with_group_velocities=True, use_nac_direction=True, nac_direction=(1., 0., 0.))
        options = ui.reader_options(settings)
        self.assertEqual(json.loads(options["canonical_parameters"]["qpoints"]), [[0., 0., 0.]])
        settings.use_nac_direction = False
        with self.assertRaisesRegex(ValueError, "Gamma"):
            ui.reader_options(settings)
        settings.born_file = ""
        settings.qpoints = "nan,0,0"
        with self.assertRaisesRegex(ValueError, "finite"):
            ui.reader_options(settings)


class FermiImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for name in ("INCAR", "KPOINTS", "POSCAR", "OUTCAR", "PROCAR", "IBZKPT"):
            (self.root / name).write_bytes(("synthetic text " + name).encode())
        (self.root / "POTCAR").write_bytes(b"must never be staged")
        (self.root / "ebs.pkl").write_bytes(b"must never be deserialized")
        self.handles, self.tasks = [], []

    def tearDown(self):
        for handle in self.handles:
            handle.terminate()
        self.temporary.cleanup()

    def load(self, **kwargs):
        return ui.load_fermi_batch(self.root, python_executable=sys.executable, repository=ROOT,
            project_id=uuid4(), schema_version="0.2", temp_parent=self.root, **kwargs)

    def worker(self, request, workspace, **kwargs):
        from ChemBlender.core import close_project, open_project, save_project
        from worker.wavefunction_operations import _output
        process = Mock()
        process.poll.return_value = process.wait.return_value = 0
        with patch("ChemBlender.worker_client.subprocess.Popen", return_value=process):
            handle = start_worker(request, workspace, **kwargs)
        self.handles.append(handle)
        task = handle.request_path.parent
        self.tasks.append(task)
        self.assertEqual(set(kwargs["staged_inputs"]), {"INCAR", "KPOINTS", "POSCAR", "OUTCAR", "PROCAR", "IBZKPT"})
        self.assertFalse((task / "POTCAR").exists())
        self.assertFalse((task / "ebs.pkl").exists())
        provenance = tuple(ProvenanceRecord(uuid4(), "fixture-" + str(index), "synthetic Fermi input",
            "1", "VASP text bundle", "a" * 64, (), "synthetic_fermi",
            (("source_artifacts", request.parameters["source_artifacts"]),)) for index in range(2))
        reference = periodic_structure()
        band = replace(band_structure(reference.id), revision="b" * 64, branches=(), provenance_ids=(provenance[0].id,))
        surface = replace(fermi_surface(reference.id, band.id), provenance_ids=(provenance[1].id,))
        batch = ImportBatch(structures=(reference,), datasets=(band, surface), provenance=provenance)
        project = open_project(request.project_locator)
        try:
            project.commit(batch)
            save_project(request.project_locator, project)
        finally:
            close_project(project)
        output = _output(batch)
        write_result(handle.result_path, WorkerResult(request.request_id, WorkerStatus.SUCCESS,
            outputs=output.outputs, cache_key=output.cache_key, metadata={
                "operation": "periodic.fermi_surface@1", "structure_id": str(reference.id),
                "band_structure_id": str(band.id), "fermi_surface_id": str(surface.id)}))
        return handle

    def test_directory_whitelist_detaches_mesh_and_preserves_original_hash_paths(self):
        with patch.object(importer, "start_worker", side_effect=self.worker):
            batch = self.load()
        self.assertFalse(any(path.exists() for path in self.tasks))
        self.assertEqual({type(item).__name__ for item in batch.datasets}, {"BandStructure", "FermiSurfaceMesh"})
        for record in batch.provenance:
            self.assertEqual(record.source, str(self.root))
            for name, metadata in dict(record.parameters)["source_artifacts"].items():
                self.assertEqual(metadata, {"path": str(self.root / name), "sha256": digest(self.root / name)})
        surface = next(item for item in batch.datasets if type(item).__name__ == "FermiSurfaceMesh")
        self.assertEqual(float(surface.data.values[1, 0]), 1.)

    def test_wrong_result_identity_and_changed_source_reject_output(self):
        from ChemBlender.core.worker_protocol import read_result
        for failure in ("identity", "source"):
            def worker(*args, **kwargs):
                handle = self.worker(*args, **kwargs)
                if failure == "identity":
                    write_result(handle.result_path, replace(read_result(handle.result_path), request_id=uuid4()))
                else:
                    (self.root / "PROCAR").write_bytes(b"changed")
                return handle
            with self.subTest(failure=failure), patch.object(importer, "start_worker", side_effect=worker):
                with self.assertRaisesRegex(ValueError, "identity mismatch|source changed"):
                    self.load()
        self.assertFalse(any(path.exists() for path in self.tasks))


class RealScientificReaderTests(unittest.TestCase):
    def test_real_sources_cross_external_worker_boundary(self):
        cases = (
            ("cclib", "cclib_output", "cclib/Gaussian/basicGaussian16/dvb_ir.out", {}, {}, "VibrationalModeSet"),
            ("pymatgen", "pymatgen-vasprun-electronic", "silicon/bands/vasprun.xml.gz",
             {"kpoints": INPUTS / "silicon/bands/KPOINTS"}, {"line_mode": "true"}, "BandStructure"),
            ("pymatgen", "pymatgen-vasprun-electronic", "silicon/dos/vasprun.xml.gz", {}, {"line_mode": "false"}, "DensityOfStates"),
            ("phonopy", "phonopy-file", "phonopy/NaCl/phonopy_disp.yaml",
             {"force_sets": INPUTS / "phonopy/NaCl/FORCE_SETS", "born": INPUTS / "phonopy/NaCl/BORN"},
             {"qpoints": "[[0,0,0],[0.25,0,0]]", "nac_q_direction": "[1,0,0]"}, "PhononModeSet"),
        )
        available = [case for case in cases if importlib.util.find_spec(case[0]) is not None]
        if not available:
            self.skipTest("optional scientific worker dependencies are absent")
        with TemporaryDirectory() as temporary:
            for _dependency, reader, relative, companions, parameters, expected in available:
                with self.subTest(reader=reader, source=relative):
                    source = INPUTS / relative
                    if not source.is_file():
                        self.skipTest("pinned scientific inputs are not prepared")
                    batch = importer.load_reader_batch(source, reader_id=reader, companions=companions,
                        canonical_parameters=parameters, python_executable=sys.executable, repository=ROOT,
                        project_id=uuid4(), schema_version="0.2", temp_parent=temporary)
                    self.assertTrue(batch.structures)
                    self.assertIn(expected, {type(value).__name__ for value in batch.datasets})
                    self.assertEqual(batch.source_revisions[0].content_hash, digest(source))
                    self.assertEqual(batch.source_revisions[0].locator, str(source))
                    self.assertTrue(set(str(path) for path in companions.values()) <= {record.source for record in batch.provenance})


if __name__ == "__main__":
    unittest.main()
