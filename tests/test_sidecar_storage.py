import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

import numpy

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    FrameSet,
    ImportBatch,
    PropertyDataset,
    ProvenanceRecord,
    QCProject,
    Structure,
    TrajectoryFrameManager,
)
from ChemBlender.core.sidecar import (
    LazyNpyArray,
    SidecarCompatibilityError,
    SidecarIntegrityError,
    close_project,
    open_project,
    save_project,
)


PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
STRUCTURE_ID = UUID("20000000-0000-0000-0000-000000000002")
DATASET_ID = UUID("30000000-0000-0000-0000-000000000003")
FRAMES_ID = UUID("40000000-0000-0000-0000-000000000004")
PROVENANCE_ID = UUID("50000000-0000-0000-0000-000000000005")


def sample_project():
    coordinates = numpy.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]])
    structure = Structure(
        id=STRUCTURE_ID,
        revision="structure-r1",
        atomic_numbers=(1, 1),
        coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"),
    )
    provenance = ProvenanceRecord(
        id=PROVENANCE_ID,
        revision="provenance-r1",
        producer="test",
        producer_version="1",
        source="h2.xyz",
        source_hash="a" * 64,
        parent_ids=(),
        operation="parse",
        parameters=(("charge", 0),),
    )
    charges = PropertyDataset(
        id=DATASET_ID,
        revision="charges-r1",
        semantic_role="mulliken_charge",
        domain="atom",
        data=ArrayData(numpy.asarray([0.1, -0.1]), ("atom",), "elementary_charge"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(PROVENANCE_ID,),
    )
    frames = FrameSet(
        id=FRAMES_ID,
        revision="frames-r1",
        semantic_role="coordinates",
        domain="frame",
        data=ArrayData(
            numpy.stack((coordinates, coordinates + 1.0)),
            ("frame", "atom", "xyz"),
            "angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(PROVENANCE_ID,),
        structure_id=STRUCTURE_ID,
        comments=("first", "second"),
    )
    project = QCProject(id=PROJECT_ID, schema_version="0.1")
    project.commit(
        ImportBatch(
            structures=(structure,),
            datasets=(charges, frames),
            provenance=(provenance,),
        )
    )
    return project


class SidecarStorageTests(unittest.TestCase):
    def test_round_trip_restores_identity_and_lazy_arrays(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, sample_project())
            loaded = open_project(root)

            self.assertEqual(loaded.id, PROJECT_ID)
            self.assertEqual(loaded.structures[STRUCTURE_ID].revision, "structure-r1")
            self.assertEqual(loaded.datasets[DATASET_ID].provenance_ids, (PROVENANCE_ID,))
            values = loaded.datasets[FRAMES_ID].data.values
            self.assertIsInstance(values, LazyNpyArray)
            self.assertFalse(values.loaded)

    def test_trajectory_manager_releases_lazy_sidecar_memory_map(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, sample_project())
            loaded = open_project(root)
            values = loaded.datasets[FRAMES_ID].data.values
            manager = TrajectoryFrameManager(loaded.datasets[FRAMES_ID])
            self.assertFalse(values.loaded)
            self.assertTrue(
                numpy.allclose(manager.frame(1)[1], [1.0, 1.0, 1.74])
            )
            self.assertTrue(values.loaded)
            manager.close()
            self.assertFalse(values.loaded)
            self.assertTrue(numpy.allclose(numpy.asarray(values)[1, 1], [1.0, 1.0, 1.74]))
            self.assertTrue(values.loaded)
            close_project(loaded)
            self.assertFalse(values.loaded)

    def test_content_addressing_deduplicates_equal_arrays(self):
        project = sample_project()
        project.datasets[DATASET_ID] = PropertyDataset(
            id=DATASET_ID,
            revision="charges-r2",
            semantic_role="mulliken_charge",
            domain="atom",
            data=ArrayData(
                numpy.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]]),
                ("atom", "xyz"),
                "dimensionless",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(PROVENANCE_ID,),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, project)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            references = []

            def visit(value):
                if isinstance(value, dict):
                    if value.get("$type") == "ArrayData":
                        references.append(value["values"]["path"])
                    for child in value.values():
                        visit(child)
                elif isinstance(value, list):
                    for child in value:
                        visit(child)

            visit(manifest["project"])
            self.assertLess(len(set(references)), len(references))
            self.assertEqual(len(list((root / "arrays").glob("*.npy"))), len(set(references)))

    def test_tamper_and_expected_identity_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, sample_project())
            with self.assertRaises(SidecarCompatibilityError):
                open_project(root, expected_project_id=UUID(int=0))
            with self.assertRaises(SidecarCompatibilityError):
                open_project(root, expected_schema_version="9")
            array_path = next((root / "arrays").glob("*.npy"))
            array_path.write_bytes(array_path.read_bytes() + b"tampered")
            with self.assertRaises(SidecarIntegrityError):
                open_project(root)

    def test_array_path_cannot_escape_sidecar(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, sample_project())
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            def replace_first_array(value):
                if isinstance(value, dict):
                    if value.get("$array") == "npy":
                        value["path"] = "../outside.npy"
                        return True
                    return any(replace_first_array(child) for child in value.values())
                if isinstance(value, list):
                    return any(replace_first_array(child) for child in value)
                return False

            self.assertTrue(replace_first_array(manifest["project"]))
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SidecarIntegrityError):
                open_project(root)

    def test_failed_manifest_replace_preserves_previous_project(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, sample_project())
            previous = (root / "manifest.json").read_bytes()
            with patch("ChemBlender.core.sidecar.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    save_project(root, sample_project())
            self.assertEqual((root / "manifest.json").read_bytes(), previous)
            self.assertEqual(open_project(root).id, PROJECT_ID)

    def test_object_arrays_are_rejected(self):
        project = sample_project()
        project.datasets[DATASET_ID] = PropertyDataset(
            id=DATASET_ID,
            revision="bad",
            semantic_role="labels",
            domain="atom",
            data=ArrayData(numpy.asarray([object(), object()], dtype=object), ("atom",), "dimensionless"),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(PROVENANCE_ID,),
        )
        with TemporaryDirectory() as directory:
            with self.assertRaises(SidecarIntegrityError):
                save_project(Path(directory) / "bad.cbq", project)


if __name__ == "__main__":
    unittest.main()
