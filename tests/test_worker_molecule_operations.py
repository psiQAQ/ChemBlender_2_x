import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

import numpy

from cbq_core.model import ImportBatch
from cbq_core.model import QCProject
from cbq_core.sidecar import close_project
from cbq_core.sidecar import open_project
from cbq_core.sidecar import save_project
from cbq_core.worker_protocol import EntityReference
from cbq_core.worker_protocol import WorkerRequest
from cbq_core.worker_protocol import WorkerStatus
from cbq_core.worker_protocol import write_request
from chemblender_prepare.worker.runner import default_registry
from chemblender_prepare.worker.runner import run_request


def smiles_batch(text):
    from chemblender_prepare.core.import_pipeline.preflight import preflight_import
    from chemblender_prepare.core.import_pipeline.request import ImportRequest
    from chemblender_prepare.core.import_pipeline.request import ImportSource
    from chemblender_prepare.core.import_pipeline.staging import StagedImportSession
    from chemblender_prepare.core.reader_catalog import builtin_reader_registry

    with TemporaryDirectory() as directory:
        session = StagedImportSession.create(temp_parent=Path(directory))
        try:
            preview = preflight_import(
                ImportRequest((ImportSource.smiles_text(text),)),
                builtin_reader_registry(), session,
            )
            return session.result(preview.staged_batch_ids[0])
        finally:
            session.discard()


class MoleculeWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project_path = self.root / "molecule.cbq"
        source = smiles_batch("c1ccccc1")
        project = QCProject(uuid4(), "1.1")
        project.commit(source)
        self.project_id = project.id
        self.source_ids = (
            source.structures[0].id, source.topologies[0].id,
            source.molecular_records[0].id,
        )
        save_project(self.project_path, project)
        close_project(project)

    def refs(self, *identities):
        project = open_project(self.project_path)
        try:
            registries = (
                project.structures, project.topologies,
                project.molecular_records, project.datasets,
            )
            entities = {
                identity: entity for registry in registries
                for identity, entity in registry.items()
            }
            return tuple(
                EntityReference(entities[identity].id, entities[identity].revision)
                for identity in identities
            )
        finally:
            close_project(project)

    def run_operation(self, operation, identities, parameters=None):
        request = WorkerRequest(
            request_id=uuid4(), project_locator=str(self.project_path),
            project_id=self.project_id, project_schema_version="1.1",
            operation_id=f"molecule.{operation}", operation_version="1",
            inputs=self.refs(*identities), parameters=parameters or {},
        )
        request_path = self.root / f"{operation}.request.json"
        result_path = self.root / f"{operation}.result.json"
        write_request(request_path, request)
        return run_request(request_path, result_path, default_registry())

    def test_smiles_kekulize_optimize_energy_and_exports_are_one_worker_loop(self):
        result = self.run_operation("smiles_to_3d", self.source_ids)
        self.assertIs(result.status, WorkerStatus.SUCCESS, result.error)
        structure_id = UUID(result.metadata["primary_id"])
        project = open_project(self.project_path)
        try:
            structure = project.structures[structure_id]
            topology = project.topologies[structure.topology_ids[0]]
            self.assertEqual(len(structure.atomic_numbers), 12)
            self.assertTrue(numpy.isfinite(structure.coordinates.values).all())
            self.assertEqual(result.cache_key, structure.revision)
            original_structure_id = self.source_ids[0]
            self.assertIn(original_structure_id, project.structures)
        finally:
            close_project(project)

        result = self.run_operation("kekulize", (structure.id, topology.id))
        self.assertIs(result.status, WorkerStatus.SUCCESS, result.error)
        kekule_id = UUID(result.metadata["structure_id"])
        project = open_project(self.project_path)
        try:
            kekule = project.structures[kekule_id]
            kekule_topology = project.topologies[kekule.topology_ids[0]]
            self.assertFalse(numpy.asarray(kekule_topology.aromatic_flags.values).any())
            self.assertEqual(
                set(numpy.asarray(kekule_topology.bond_orders.values)[:6]),
                {1.0, 2.0},
            )
        finally:
            close_project(project)

        result = self.run_operation("optimize", (kekule.id, kekule_topology.id), {
            "force_field": "UFF", "add_hydrogens": False,
            "max_iterations": 200,
        })
        self.assertIs(result.status, WorkerStatus.SUCCESS, result.error)
        optimized_id = UUID(result.metadata["structure_id"])
        project = open_project(self.project_path)
        try:
            optimized = project.structures[optimized_id]
            optimized_topology = project.topologies[optimized.topology_ids[0]]
            self.assertEqual(optimized.atomic_numbers, kekule.atomic_numbers)
            self.assertTrue(numpy.isfinite(optimized.coordinates.values).all())
        finally:
            close_project(project)

        result = self.run_operation("energy", (optimized.id, optimized_topology.id), {
            "force_field": "UFF",
        })
        self.assertIs(result.status, WorkerStatus.SUCCESS, result.error)
        project = open_project(self.project_path)
        try:
            dataset = project.datasets[UUID(result.metadata["dataset_id"])]
            self.assertEqual(dataset.semantic_role, "potential_energy")
            self.assertEqual(dataset.domain, "structure")
            self.assertEqual(dataset.data.unit, "kilocalorie_per_mole")
            self.assertEqual(dataset.data.shape, ())
            self.assertTrue(numpy.isfinite(numpy.asarray(dataset.data.values)).all())
        finally:
            close_project(project)

        from rdkit import Chem
        for format_name in ("mol", "sdf", "smiles"):
            with self.subTest(format_name=format_name):
                result = self.run_operation(
                    "export", (optimized.id, optimized_topology.id),
                    {"format": format_name, "confirm_loss": True,
                     "isomeric": True},
                )
                self.assertIs(result.status, WorkerStatus.SUCCESS, result.error)
                artifact = self.project_path / result.metadata["artifact"]
                self.assertTrue(artifact.is_file())
                if format_name == "mol":
                    parsed = Chem.MolFromMolBlock(
                        artifact.read_text("utf-8"), removeHs=False
                    )
                elif format_name == "sdf":
                    parsed = Chem.SDMolSupplier(
                        str(artifact), removeHs=False
                    )[0]
                else:
                    parsed = Chem.MolFromSmiles(artifact.read_text("utf-8").strip())
                self.assertIsNotNone(parsed)
                atom_count = (
                    Chem.AddHs(parsed).GetNumAtoms()
                    if format_name == "smiles" else parsed.GetNumAtoms()
                )
                self.assertEqual(atom_count, len(optimized.atomic_numbers))

    def test_export_requires_explicit_loss_confirmation_and_does_not_publish(self):
        generated = self.run_operation("smiles_to_3d", self.source_ids)
        structure_id = UUID(generated.metadata["primary_id"])
        project = open_project(self.project_path)
        try:
            structure = project.structures[structure_id]
            topology_id = structure.topology_ids[0]
            before = len(project.provenance)
        finally:
            close_project(project)
        result = self.run_operation("export", (structure_id, topology_id), {
            "format": "smiles", "confirm_loss": False,
        })
        self.assertIs(result.status, WorkerStatus.ERROR)
        self.assertEqual(
            result.error.code, "molecule_export_confirmation_required",
            result.error,
        )
        project = open_project(self.project_path)
        try:
            self.assertEqual(len(project.provenance), before)
        finally:
            close_project(project)


if __name__ == "__main__":
    unittest.main()
