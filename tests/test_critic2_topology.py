import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy as np

from ChemBlender.core import (
    ArrayData,
    CriticalPointKind,
    DatasetStatus,
    ImportBatch,
    QCProject,
    Structure,
    TopologyConnection,
    TopologyGraph,
    TopologyPath,
    close_project,
    open_project,
    parse_critic2_cpreport,
    save_project,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "critic2" / "cpreport-minimal.json"


def structure(structure_id):
    return Structure(
        id=structure_id,
        revision="structure-r1",
        atomic_numbers=(1, 1),
        coordinates=ArrayData(np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]]), ("atom", "xyz"), "bohr"),
    )


class Critic2TopologyTests(unittest.TestCase):
    def test_minimal_cpreport_parses_stable_points_and_connections(self):
        structure_id = uuid4()
        first = parse_critic2_cpreport(FIXTURE, structure_id=structure_id)
        second = parse_critic2_cpreport(FIXTURE, structure_id=structure_id)
        graph = first.datasets[0]
        self.assertIsInstance(graph, TopologyGraph)
        self.assertEqual(graph.revision, second.datasets[0].revision)
        self.assertEqual(graph.critical_point_ids, second.datasets[0].critical_point_ids)
        self.assertEqual(
            graph.kinds,
            (CriticalPointKind.NUCLEAR, CriticalPointKind.NUCLEAR, CriticalPointKind.BOND),
        )
        self.assertEqual(graph.data.dims, ("critical_point", "xyz"))
        self.assertEqual(graph.field_semantic_role, "electron_density")
        np.testing.assert_allclose(graph.data.values[2], [1.0, 0.0, 0.0])
        self.assertEqual(len(graph.connections), 2)
        self.assertEqual(graph.connections[0].critical_point_id, graph.critical_point_ids[2])
        self.assertEqual(graph.connections[0].endpoint_id, graph.critical_point_ids[0])
        self.assertEqual(graph.paths, ())
        self.assertEqual(first.report.parsed_capabilities, ("topology",))

    def test_graph_and_sampled_path_enforce_identity_shape_and_units(self):
        graph = parse_critic2_cpreport(FIXTURE, structure_id=uuid4()).datasets[0]
        with self.assertRaisesRegex(ValueError, "endpoint"):
            replace(
                graph,
                connections=(
                    replace(graph.connections[0], endpoint_id=uuid4()),
                ),
            )
        path = TopologyPath(
            id=uuid4(),
            start_id=graph.critical_point_ids[0],
            end_id=graph.critical_point_ids[2],
            samples=ArrayData(np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]), ("sample", "xyz"), "bohr"),
        )
        self.assertEqual(path.samples.shape, (2, 3))
        with self.assertRaisesRegex(ValueError, "samples"):
            replace(path, samples=ArrayData(np.array([[0.0, 0.0, 0.0]]), ("sample", "xyz"), "bohr"))

    def test_invalid_signature_and_dangling_connection_are_rejected(self):
        document = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            document["critical_points"]["nonequivalent_cps"][2]["signature"] = 0
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "signature"):
                parse_critic2_cpreport(path, structure_id=uuid4())

            document = json.loads(FIXTURE.read_text(encoding="utf-8"))
            document["critical_points"]["cell_cps"][2]["attractors"][0]["cell_id"] = 99
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "endpoint"):
                parse_critic2_cpreport(path, structure_id=uuid4())

    def test_topology_round_trips_through_cbq(self):
        structure_id = uuid4()
        source_structure = structure(structure_id)
        batch = parse_critic2_cpreport(FIXTURE, structure_id=structure_id)
        project = QCProject(uuid4(), "0.1")
        project.commit(
            ImportBatch(
                structures=(source_structure,),
                datasets=batch.datasets,
                provenance=batch.provenance,
            )
        )
        with TemporaryDirectory() as directory:
            sidecar = Path(directory) / "project.cbq"
            save_project(sidecar, project)
            restored = open_project(sidecar)
            graph = next(iter(restored.datasets.values()))
            self.assertIsInstance(graph, TopologyGraph)
            self.assertEqual(graph.status, DatasetStatus.COMPLETE)
            self.assertEqual(graph.structure_id, structure_id)
            self.assertEqual(len(graph.connections), 2)
            close_project(restored)


if __name__ == "__main__":
    unittest.main()
