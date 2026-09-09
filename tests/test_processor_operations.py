"""Unified Blender-side scientific operation publication contracts."""

from pathlib import Path
import os
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy

from cbq_core.model import (
    AtomicProperty, FermiSurfaceMesh, Grid3D, PhononModeSet, QCProject,
)
from cbq_core.session import ProjectSession
from cbq_core.sidecar import close_project
from ChemBlender.ui.processor import ProcessorState
from ChemBlender.ui.processor_operations import (
    ProcessorError, molecule_inputs, publish_operation, start_fermi_operation,
    start_molecule_operation, start_reader_operation,
    start_professional_operation, start_wavefunction_operation,
    wavefunction_inputs,
)


ROOT = Path(__file__).resolve().parents[1]
PROCESSOR = ROOT / ".venv" / "Scripts" / "chemblender-prepare.exe"
FIXTURE = ROOT / "tests" / "fixtures" / "xyz" / "water.xyz"
FERMI_FIXTURE = ROOT / ".agents" / "cache" / "scientific-visualization" / "fermi"
PROCESSOR_CONFIG = (ROOT / ".blend-analysis" /
                    "2026-09-08-cbq-architecture-consolidation" /
                    "processor-config-01.json")


def wait_for(operation, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = operation.poll()
        if snapshot.state in {
            ProcessorState.SUCCEEDED,
            ProcessorState.CANCELLED,
            ProcessorState.FAILED,
        }:
            return snapshot
        time.sleep(.02)
    raise AssertionError("processor operation did not finish")


@unittest.skipUnless(PROCESSOR.is_file(), "project processor launcher required")
class ProcessorOperationTests(unittest.TestCase):
    def test_molecular_operations_append_select_export_and_survive_cleanup(self):
        from tests.test_worker_molecule_operations import smiles_batch

        with TemporaryDirectory(prefix="processor-operation-") as temporary:
            root = Path(temporary)
            source = smiles_batch("c1ccccc1")
            project = QCProject(id=uuid4(), schema_version="1.1")
            project.commit(source)
            session = ProjectSession(uuid4(), project, root)
            original_ids = frozenset(project.structures)

            inputs = molecule_inputs(
                project, "molecule.smiles_to_3d",
                source.structures[0].id, source.topologies[0].id,
            )
            operation = start_molecule_operation(
                PROCESSOR, root, project, "molecule.smiles_to_3d", inputs,
                {"add_hydrogens": True, "force_field": "MMFF94",
                 "random_seed": 0xC0FFEE, "num_threads": 1,
                 "max_iterations": 200},
            )
            try:
                snapshot = wait_for(operation)
                self.assertIs(snapshot.state, ProcessorState.SUCCEEDED,
                              snapshot.error)
                structure_id = publish_operation(operation, session)
            finally:
                operation.cleanup()
            self.assertIn(structure_id, session.project.structures)
            self.assertTrue(original_ids.issubset(session.project.structures))
            structure = session.project.structures[structure_id]
            topology = session.project.topologies[structure.topology_ids[0]]
            coordinates = numpy.asarray(structure.coordinates.values).copy()

            inputs = molecule_inputs(
                session.project, "molecule.energy", structure.id, topology.id,
            )
            operation = start_molecule_operation(
                PROCESSOR, root, session.project, "molecule.energy", inputs,
                {"force_field": "MMFF94"},
            )
            try:
                self.assertIs(wait_for(operation).state, ProcessorState.SUCCEEDED)
                energy_id = publish_operation(operation, session)
            finally:
                operation.cleanup()
            energy = session.project.datasets[energy_id]
            self.assertEqual(energy.data.unit, "kilocalorie_per_mole")

            destination = root / "benzene.sdf"
            inputs = molecule_inputs(
                session.project, "molecule.export", structure.id, topology.id,
            )
            operation = start_molecule_operation(
                PROCESSOR, root, session.project, "molecule.export", inputs,
                {"format": "sdf", "confirm_loss": True, "isomeric": True},
                export_destination=destination,
            )
            try:
                self.assertIs(wait_for(operation).state, ProcessorState.SUCCEEDED)
                selected = publish_operation(operation, session)
            finally:
                operation.cleanup()
            self.assertEqual(selected, structure.id)
            self.assertTrue(destination.is_file())
            self.assertEqual(
                numpy.asarray(session.project.structures[structure.id].coordinates.values).shape,
                coordinates.shape,
            )
            close_project(session.project)

    def test_molecule_export_requires_destination(self):
        from tests.test_worker_molecule_operations import smiles_batch

        with TemporaryDirectory(prefix="processor-operation-") as temporary:
            root = Path(temporary)
            source = smiles_batch("CO")
            project = QCProject(id=uuid4(), schema_version="1.1")
            project.commit(source)
            inputs = molecule_inputs(
                project, "molecule.export",
                source.structures[0].id, source.topologies[0].id,
            )
            with self.assertRaisesRegex(ProcessorError, "export destination"):
                start_molecule_operation(
                    PROCESSOR, root, project, "molecule.export", inputs,
                    {"format": "sdf", "confirm_loss": True},
                    export_destination="",
                )

    def test_reader_result_is_verified_appended_selected_and_detached(self):
        with TemporaryDirectory(prefix="processor-operation-") as temporary:
            root = Path(temporary)
            project = QCProject(id=uuid4(), schema_version="1.1")
            session = ProjectSession(uuid4(), project, root)
            operation = start_reader_operation(PROCESSOR, root, project, FIXTURE, "xyz")
            snapshot = wait_for(operation)
            self.assertIs(snapshot.state, ProcessorState.SUCCEEDED)

            task_directory = operation.task.task_directory
            primary = publish_operation(operation, session)
            self.assertEqual(session.active_entity_id, primary)
            self.assertIn(primary, session.project.structures)
            coordinates = numpy.asarray(
                session.project.structures[primary].coordinates.values
            ).copy()
            operation.cleanup()

            self.assertFalse(task_directory.exists())
            self.assertEqual(coordinates.shape, (3, 3))
            self.assertEqual(
                numpy.asarray(session.project.structures[primary].coordinates.values).shape,
                (3, 3),
            )
            revision = next(iter(session.project.source_revisions.values()))
            self.assertEqual(Path(revision.locator), FIXTURE.resolve())
            self.assertEqual(revision.original_filename, FIXTURE.name)
            self.assertTrue(all(str(task_directory) not in record.source
                                for record in session.project.provenance.values()))
            close_project(session.project)

    def test_tampered_reader_result_does_not_mutate_project(self):
        with TemporaryDirectory(prefix="processor-operation-") as temporary:
            root = Path(temporary)
            project = QCProject(id=uuid4(), schema_version="1.1")
            session = ProjectSession(uuid4(), project, root)
            operation = start_reader_operation(PROCESSOR, root, project, FIXTURE, "xyz")
            self.assertIs(wait_for(operation).state, ProcessorState.SUCCEEDED)

            array = next(operation.result_project.rglob("*.npy"))
            data = bytearray(array.read_bytes())
            data[-1] ^= 1
            array.write_bytes(data)
            with self.assertRaises(Exception):
                publish_operation(operation, session)
            self.assertFalse(session.project.structures)
            operation.cleanup()

    @unittest.skipUnless((FERMI_FIXTURE / "PROCAR").is_file()
                         and PROCESSOR_CONFIG.is_file(),
                         "real cached Fermi fixture and processor config required")
    def test_real_fermi_result_uses_original_sources_and_survives_cleanup(self):
        with TemporaryDirectory(prefix="processor-operation-") as temporary:
            root = Path(temporary)
            session = ProjectSession(uuid4(), QCProject(uuid4(), "1.1"), root)
            with patch.dict(os.environ, {
                    "CHEMBLENDER_PREPARE_CONFIG": str(PROCESSOR_CONFIG.resolve())}):
                operation = start_fermi_operation(
                    PROCESSOR, root, session.project, FERMI_FIXTURE,
                )
                try:
                    snapshot = wait_for(operation, timeout=120)
                    self.assertIs(snapshot.state, ProcessorState.SUCCEEDED,
                                  snapshot.error)
                    task_directory = operation.task.task_directory
                    primary = publish_operation(operation, session)
                    surface = session.project.datasets[primary]
                    self.assertIsInstance(surface, FermiSurfaceMesh)
                    vertices = numpy.asarray(surface.data.values).copy()
                    faces = numpy.asarray(surface.faces.values).copy()
                    for record in session.project.provenance.values():
                        self.assertEqual(Path(record.source), FERMI_FIXTURE.resolve())
                        for name, metadata in dict(record.parameters)[
                                "source_artifacts"].items():
                            self.assertEqual(Path(metadata["path"]),
                                             (FERMI_FIXTURE / name).resolve())
                finally:
                    operation.cleanup()
            self.assertFalse(task_directory.exists())
            self.assertGreater(vertices.shape[0], 100)
            self.assertGreater(faces.shape[0], 100)
            self.assertEqual(numpy.asarray(surface.data.values).shape, vertices.shape)
            close_project(session.project)

    @unittest.skipUnless(PROCESSOR_CONFIG.is_file(),
                         "real processor config required")
    def test_real_wavefunction_operations_share_the_verified_entrypoint(self):
        source = (ROOT / "examples" / "scientific-visualization" / "inputs" /
                  "wavefunction" / "water_sto3g_hf_g03.fchk")
        if not source.is_file():
            self.skipTest("wavefunction fixture required")
        with TemporaryDirectory(prefix="processor-operation-") as temporary, \
                patch.dict(os.environ, {
                    "CHEMBLENDER_PREPARE_CONFIG": str(PROCESSOR_CONFIG.resolve())}):
            root = Path(temporary)
            session = ProjectSession(uuid4(), QCProject(uuid4(), "1.1"), root)
            reader = start_reader_operation(
                PROCESSOR, root, session.project, source, "iodata_wavefunction",
            )
            try:
                self.assertIs(wait_for(reader, 60).state, ProcessorState.SUCCEEDED)
                publish_operation(reader, session)
            finally:
                reader.cleanup()
            orbitals = next(iter(session.project.orbital_sets.values()))
            matrix = next(iter(session.project.density_matrices.values()))
            charges = next(
                value for value in session.project.datasets.values()
                if isinstance(value, AtomicProperty)
                and value.semantic_role == "nuclear_charge"
            )
            nearby = {
                "origin": [-1., -1., -1.],
                "step_vectors": [[.5, 0., 0.], [0., .5, 0.], [0., 0., .5]],
                "shape": [3, 3, 3], "chunk_size": 4096,
            }
            far = {**nearby, "origin": [4., 4., 4.]}
            cases = (
                ("wavefunction.mo_grid", orbitals.id,
                 {**nearby, "channel": orbitals.channels[0].label,
                  "orbital_index": 0}, "molecular_orbital"),
                ("wavefunction.electron_density_grid", orbitals.id,
                 nearby, "electron_density"),
                ("wavefunction.density_matrix_grid", matrix.id,
                 nearby, "electron_density"),
                ("wavefunction.esp_grid", matrix.id,
                 far, "electrostatic_potential"),
                ("wavefunction.esp_from_orbitals_grid", orbitals.id,
                 {**far, "density_level": "scf"}, "electrostatic_potential"),
            )
            outputs = []
            for operation_id, source_id, parameters, role in cases:
                inputs = wavefunction_inputs(
                    session.project, operation_id, source_id,
                    nuclear_charge_id=(charges.id if operation_id.startswith(
                        "wavefunction.esp") else None),
                )
                operation = start_wavefunction_operation(
                    PROCESSOR, root, session.project, operation_id,
                    inputs, parameters,
                )
                try:
                    snapshot = wait_for(operation, 60)
                    self.assertIs(snapshot.state, ProcessorState.SUCCEEDED,
                                  snapshot.error)
                    identity = publish_operation(operation, session)
                    grid = session.project.datasets[identity]
                    self.assertIsInstance(grid, Grid3D)
                    self.assertEqual(grid.semantic_role, role)
                    self.assertTrue(numpy.isfinite(grid.data.values).all())
                    outputs.append(identity)
                finally:
                    operation.cleanup()
            self.assertEqual(len(set(outputs)), 5)
            self.assertTrue(set(outputs).issubset(session.project.datasets))
            close_project(session.project)

    @unittest.skipUnless(PROCESSOR_CONFIG.is_file(),
                         "real processor config required")
    def test_real_phonon_operation_is_published_and_detached(self):
        source = ROOT / "examples/scientific-visualization/inputs/phonopy/NaCl"
        with TemporaryDirectory(prefix="processor-operation-") as temporary, \
                patch.dict(os.environ, {
                    "CHEMBLENDER_PREPARE_CONFIG": str(PROCESSOR_CONFIG.resolve())}):
            root = Path(temporary)
            session = ProjectSession(uuid4(), QCProject(uuid4(), "1.1"), root)
            operation = start_professional_operation(
                PROCESSOR, root, session.project, "periodic.phonon", (),
                {"qpoints": ((.1, .2, .3),), "nac_q_direction": (1., 0., 0.),
                 "with_group_velocities": True},
                {"displacement_yaml": source / "phonopy_disp.yaml",
                 "force_sets": source / "FORCE_SETS", "born": source / "BORN"},
            )
            try:
                snapshot = wait_for(operation, 60)
                self.assertIs(snapshot.state, ProcessorState.SUCCEEDED,
                              snapshot.error)
                primary = publish_operation(operation, session)
                modes = session.project.datasets[primary]
                self.assertIsInstance(modes, PhononModeSet)
                self.assertEqual(modes.data.shape, (1, 6))
                self.assertTrue(all(
                    Path(item["path"]).is_absolute()
                    for record in session.project.provenance.values()
                    for item in dict(record.parameters)["source_artifacts"].values()
                ))
            finally:
                operation.cleanup()
            self.assertTrue(numpy.isfinite(modes.data.values).all())
            close_project(session.project)


if __name__ == "__main__":
    unittest.main()
