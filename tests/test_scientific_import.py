"""External reader staging, companion provenance and explicit scientific options."""

import hashlib
import importlib.util
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from cbq_core.model import ImportBatch
from cbq_core.model import ProvenanceRecord
from chemblender_prepare.core import phonopy_adapter
from chemblender_prepare.core import pymatgen_electronic
from cbq_core.worker_protocol import WorkerResult
from cbq_core.worker_protocol import WorkerStatus
from chemblender_prepare.reader_api.protocol import ParseRequest
from chemblender_prepare import cli as importer
from tests.test_quantum_workbench_integration import load_reader, synthetic_result
from cbq_core.model import QCProject
from cbq_core.sidecar import close_project, open_project, save_project
from contextlib import redirect_stdout
import io
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
        descriptor = SimpleNamespace(reader_id="pymatgen-vasprun-electronic", availability=SimpleNamespace(available=True))
        mocking = patch.object(importer, "_descriptor", return_value=descriptor)
        mocking.start()
        self.addCleanup(mocking.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def load(self, **kwargs):
        return load_reader(self.source, "pymatgen-vasprun-electronic", self.root,
            companions={"kpoints": self.companion}, parameters={"line_mode": "true"}, **kwargs)

    def worker(self, request, task, cancel):
        self.tasks.append(task)
        source = task / request.parameters["source_artifact"]
        parameters = request.parameters["canonical_parameters"]
        companion = task / parameters["kpoints_artifact"]
        self.assertEqual(digest(companion), parameters["kpoints_sha256"])
        provenance = tuple(ProvenanceRecord(uuid4(), digest(path), "synthetic input", "1",
            str(path), digest(path), (), "read_input", ()) for path in (source, companion))
        reference = structure()
        modes = replace(mode_set(reference.id), provenance_ids=tuple(record.id for record in provenance))
        return synthetic_result(request, task,
            ImportBatch(structures=(reference,), datasets=(modes,), provenance=provenance))

    def test_companions_are_copied_hashed_restored_and_committed_once(self):
        with patch.object(importer, "_run_worker", side_effect=self.worker):
            batch = self.load()
        self.assertFalse(any(path.exists() for path in self.tasks))
        self.assertEqual({record.source for record in batch.provenance}, {str(self.source), str(self.companion)})
        self.assertEqual(batch.source_revisions[0].locator, str(self.source))
        self.assertTrue(any(record.source_hash == digest(self.companion) for record in batch.provenance))
        project = QCProject(uuid4(), "1.1")
        project.commit(batch)
        self.assertEqual(len(project.source_revisions), 1)
        self.assertEqual(len(project.datasets), 1)

    def test_changed_original_or_staged_companion_never_publishes(self):
        for location in ("original", "staged"):
            self.companion.write_bytes(b"synthetic companion")
            def worker(*args, **kwargs):
                result = self.worker(*args, **kwargs)
                path = self.companion if location == "original" else args[1] / "KPOINTS"
                path.write_bytes(b"changed")
                return result
            with self.subTest(location=location), patch.object(importer, "_run_worker", side_effect=worker):
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

class FermiImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.names = ("INCAR", "KPOINTS", "POSCAR", "OUTCAR", "PROCAR", "IBZKPT")
        for name in self.names:
            (self.root / name).write_bytes(("synthetic text " + name).encode())
        (self.root / "POTCAR").write_bytes(b"must never be staged")
        (self.root / "ebs.pkl").write_bytes(b"must never be deserialized")
        self.input = self.root / "input.cbq"
        self.output = self.root / "result.cbq"
        save_project(self.input, QCProject(uuid4(), "1.1"))

    def run_cli(self, success=True):
        args = ["derive", str(self.input), "-o", str(self.output), "--operation", "periodic.fermi_surface", "--json"]
        for name in self.names:
            args.extend(("--artifact", name + "=" + str(self.root / name)))
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = importer.main(args)
        result = json.loads(stream.getvalue())
        self.assertEqual(code, 0 if success else 1, result)
        return result

    def worker(self, request_path, result_path, registry, cancel_path=None):
        from cbq_core.worker_protocol import read_request
        from chemblender_prepare.worker.wavefunction_operations import _output
        request = read_request(request_path)
        task = request_path.parent
        artifacts = request.parameters["source_artifacts"]
        self.assertEqual(set(artifacts), set(self.names))
        self.assertFalse((task / "inputs/POTCAR").exists())
        self.assertFalse((task / "inputs/ebs.pkl").exists())
        for name, item in artifacts.items():
            self.assertEqual(digest(task / item["path"]), digest(self.root / name))
        provenance = tuple(ProvenanceRecord(uuid4(), "fixture-" + str(index), "synthetic Fermi input",
            "1", "VASP text bundle", "a" * 64, (), "synthetic_fermi",
            (("source_artifacts", artifacts),)) for index in range(2))
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
        return WorkerResult(request.request_id, WorkerStatus.SUCCESS,
            outputs=output.outputs, cache_key=output.cache_key)

    def test_directory_whitelist_detaches_mesh_and_preserves_original_hash_paths(self):
        with patch("chemblender_prepare.worker.runner.run_request", side_effect=self.worker):
            self.run_cli()
        project = open_project(self.output)
        try:
            self.assertEqual({type(item).__name__ for item in project.datasets.values()}, {"BandStructure", "FermiSurfaceMesh"})
            for record in project.provenance.values():
                for name, metadata in dict(record.parameters)["source_artifacts"].items():
                    self.assertEqual(metadata, {"path": str(self.root / name), "sha256": digest(self.root / name)})
            surface = next(item for item in project.datasets.values() if type(item).__name__ == "FermiSurfaceMesh")
            self.assertEqual(float(surface.data.values[1, 0]), 1.)
        finally:
            close_project(project)

    def test_wrong_result_identity_and_changed_source_reject_output(self):
        for failure in ("identity", "source"):
            def worker(*args, **kwargs):
                result = self.worker(*args, **kwargs)
                if failure == "identity":
                    result = replace(result, request_id=uuid4())
                else:
                    (self.root / "PROCAR").write_bytes(b"changed")
                return result
            with self.subTest(failure=failure), patch("chemblender_prepare.worker.runner.run_request", side_effect=worker):
                result = self.run_cli(success=False)
                self.assertRegex(result["error"]["message"], "identity mismatch|source changed")
                self.assertFalse(self.output.exists())


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
                    batch = load_reader(source, reader, temporary, companions=companions, parameters=parameters)
                    self.assertTrue(batch.structures)
                    self.assertIn(expected, {type(value).__name__ for value in batch.datasets})
                    self.assertEqual(batch.source_revisions[0].content_hash, digest(source))
                    self.assertEqual(batch.source_revisions[0].locator, str(source))
                    self.assertTrue(set(str(path) for path in companions.values()) <= {record.source for record in batch.provenance})


if __name__ == "__main__":
    unittest.main()
