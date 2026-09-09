import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy

from cbq_core.model import ArrayData
from cbq_core.model import ImportBatch
from cbq_core.model import QCProject
from cbq_core.model import QualityStatus
from cbq_core.model import Structure
from cbq_core.model import TopologyRecord
from cbq_core.model import TopologySource
from cbq_core.session import close_session
from cbq_core.session import create_session
from chemblender_prepare.core.topology.infer import TopologyInferenceSettings
from ChemBlender.ui.topology import (
    record_topology_decision,
    suggested_topology_id,
    topology_choices,
)
from ChemBlender.ui.project_browser.model import ViewRecord, build_browser_rows


def structure(*, periodic=False):
    values = {
        "id": uuid4(),
        "revision": "structure-r1",
        "atomic_numbers": (8, 1, 1),
        "coordinates": ArrayData(
            numpy.asarray(
                ((0.0, 0.0, 0.0), (0.96, 0.0, 0.0), (-0.24, 0.93, 0.0))
            ),
            ("atom", "xyz"),
            "angstrom",
        ),
    }
    if periodic:
        from cbq_core.model import PeriodicSiteData

        values.update(
            cell=ArrayData(
                numpy.diag((10.0, 10.0, 10.0)),
                ("cell_vector", "xyz"),
                "angstrom",
            ),
            periodic=PeriodicSiteData(
                fractional_coordinates=ArrayData(
                    numpy.asarray(
                        ((0.0, 0.0, 0.0), (0.096, 0.0, 0.0), (0.976, 0.093, 0.0))
                    ),
                    ("atom", "xyz"),
                    "dimensionless",
                ),
                site_labels=("O1", "H1", "H2"),
                occupancies=ArrayData(
                    numpy.ones(3), ("atom",), "dimensionless"
                ),
                isotropic_displacements=None,
                anisotropic_displacements=None,
                adp_types=("none",) * 3,
                disorder_groups=(0,) * 3,
                declared_space_group_name=None,
                declared_space_group_number=None,
                symmetry_operations=(),
                cif_envelope_id=None,
                pbc=(True, True, True),
            ),
        )
    return Structure(**values)


def explicit_topology(reference):
    return TopologyRecord(
        id=uuid4(),
        revision="topology-r1",
        structure_id=reference.id,
        bond_indices=ArrayData(
            numpy.asarray(((0, 1), (0, 2))),
            ("bond", "endpoint"),
            "dimensionless",
        ),
        bond_orders=ArrayData(
            numpy.asarray((1.0, 1.0)), ("bond",), "dimensionless"
        ),
        aromatic_flags=None,
        stereo_labels=("", ""),
        source_kind=TopologySource.EXPLICIT_FILE,
        quality_status=QualityStatus.COMPLETE,
        inference_parameters=(),
        provenance_ids=(),
    )


class TopologyUIContractTests(unittest.TestCase):
    def test_choices_report_source_quality_edges_parameters_and_view_usage(self):
        reference = structure()
        selected = explicit_topology(reference)
        project = QCProject(uuid4(), "0.2")
        project.commit(ImportBatch(structures=(reference,), topologies=(selected,)))

        choices = topology_choices(
            project,
            reference.id,
            decisions_json="{}",
            view_usage={selected.id: 2},
        )

        self.assertEqual(len(choices), 1)
        choice = choices[0]
        self.assertEqual(choice.topology_id, selected.id)
        self.assertEqual(choice.source, "explicit_file")
        self.assertEqual(choice.quality, "complete")
        self.assertEqual(choice.edge_count, 2)
        self.assertEqual(choice.parameters, ())
        self.assertEqual(choice.view_count, 2)
        self.assertFalse(choice.accepted)
        self.assertFalse(choice.rejected)
        self.assertEqual(suggested_topology_id(choices), selected.id)

        rows = build_browser_rows(
            project,
            mode="by_data",
            browser_revision=1,
            views=(
                ViewRecord(
                    object_name="Water",
                    entity_id=selected.id,
                    revision=selected.revision,
                    view_kind="structure_topology",
                    label="Water",
                ),
            ),
        )
        topology_row = next(
            row for row in rows if row.entity_id == selected.id
        )
        self.assertEqual(topology_row.kind, "topology_record")
        self.assertEqual(topology_row.quality, "complete")
        self.assertIn("Explicit File: 2 bonds", topology_row.label)
        self.assertEqual(topology_row.view_count, 1)

    def test_accept_and_reject_are_canonical_per_structure_decisions(self):
        reference = structure()
        selected = explicit_topology(reference)
        project = QCProject(uuid4(), "0.2")
        project.commit(ImportBatch(structures=(reference,), topologies=(selected,)))

        rejected = record_topology_decision(
            project,
            "{}",
            reference.id,
            selected.id,
            accept=False,
        )
        self.assertEqual(
            json.loads(rejected),
            {
                str(reference.id): {
                    "accepted": None,
                    "rejected": [str(selected.id)],
                }
            },
        )
        choices = topology_choices(project, reference.id, rejected)
        self.assertTrue(choices[0].rejected)
        self.assertIsNone(suggested_topology_id(choices))

        accepted = record_topology_decision(
            project,
            rejected,
            reference.id,
            selected.id,
            accept=True,
        )
        self.assertEqual(
            accepted,
            json.dumps(
                {
                    str(reference.id): {
                        "accepted": str(selected.id),
                        "rejected": [],
                    }
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        choices = topology_choices(project, reference.id, accepted)
        self.assertTrue(choices[0].accepted)
        self.assertFalse(choices[0].rejected)

    def test_decisions_reject_malformed_and_foreign_topology_ids(self):
        reference = structure()
        other = structure()
        selected = explicit_topology(other)
        project = QCProject(uuid4(), "0.2")
        project.commit(
            ImportBatch(structures=(reference, other), topologies=(selected,))
        )

        for encoded in (
            "[]",
            '{"bad":{}}',
            '{"x":1}',
            json.dumps(
                {
                    str(uuid4()): {
                        "accepted": None,
                        "rejected": [],
                    }
                }
            ),
        ):
            with self.subTest(encoded=encoded):
                with self.assertRaises((TypeError, ValueError)):
                    topology_choices(project, reference.id, encoded)
        with self.assertRaisesRegex(ValueError, "does not belong"):
            record_topology_decision(
                project,
                "{}",
                reference.id,
                selected.id,
                accept=True,
            )

    def convert(self, source, output, *args, success=True):
        import io
        from contextlib import redirect_stdout
        from chemblender_prepare.cli import main
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(["convert", str(source), "-o", str(output), "--infer-bonds",
                         *map(str, args), "--json"])
        result = json.loads(stream.getvalue())
        self.assertEqual(code, 0 if success else 1, result)
        return result

    def test_external_conversion_prepares_deterministic_molecular_bonds(self):
        from cbq_core.sidecar import open_project, close_project
        from chemblender_prepare.core.topology.infer import infer_distance_topology
        with TemporaryDirectory() as directory:
            source, output = Path(directory) / "water.xyz", Path(directory) / "water.cbq"
            source.write_text("3\nwater\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n", encoding="utf-8")
            self.convert(source, output)
            project = open_project(output, verify_arrays=True)
            try:
                reference = next(iter(project.structures.values()))
                proposal = project.topologies[reference.topology_ids[0]]
                self.assertEqual(proposal.source_kind, TopologySource.DISTANCE_INFERRED)
                numpy.testing.assert_array_equal(proposal.bond_indices.values, ((0, 1), (0, 2)))
                # Determinism is relative to the same source UUID and revision.
                first = infer_distance_topology(reference).topologies[0]
                second = infer_distance_topology(reference).topologies[0]
                self.assertEqual((first.id, first.revision), (second.id, second.revision))
                self.assertEqual(len(project.topologies), 1)
            finally:
                close_project(project)

    def test_external_conversion_selects_periodic_inference(self):
        from cbq_core.sidecar import open_project, close_project
        source = Path(__file__).resolve().parent / "fixtures/poscar/cscl-selective.vasp"
        with TemporaryDirectory() as directory:
            output = Path(directory) / "periodic.cbq"
            self.convert(source, output)
            project = open_project(output, verify_arrays=True)
            try:
                reference = next(iter(project.structures.values()))
                proposal = project.topologies[reference.topology_ids[0]]
                self.assertEqual(proposal.structure_id, reference.id)
                self.assertIn(("periodic", True), proposal.inference_parameters)
                self.assertIsNotNone(proposal.bond_lattice_shifts)
            finally:
                close_project(project)

    def test_external_failure_and_late_cancellation_do_not_publish_or_mutate_input(self):
        from chemblender_prepare.core.topology.infer import infer_distance_topology
        for cancel_result in (False, True):
            with self.subTest(cancel=cancel_result), TemporaryDirectory() as directory:
                source, output = Path(directory) / "water.xyz", Path(directory) / "water.cbq"
                cancel = Path(directory) / "cancel"
                raw = b"3\nwater\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n"
                source.write_bytes(raw)
                def interrupted(reference, settings):
                    self.assertFalse(output.exists())
                    self.assertFalse(reference.topology_ids)
                    batch = infer_distance_topology(reference, settings)
                    if cancel_result:
                        cancel.touch()
                        return batch
                    raise RuntimeError("inference failed")
                with patch("chemblender_prepare.core.topology.infer.infer_distance_topology", side_effect=interrupted):
                    result = self.convert(source, output, "--cancel-file", cancel, success=False)
                self.assertEqual(result["status"], "cancelled" if cancel_result else "error")
                self.assertFalse(output.exists())
                self.assertEqual(source.read_bytes(), raw)

    def test_external_gui_cleanup_retries_without_losing_job_ownership(self):
        from unittest.mock import Mock
        from chemblender_prepare.gui import PrepareWindow
        from cbq_core.worker_protocol import WorkerResult, WorkerStatus
        job = SimpleNamespace(poll=Mock(return_value=WorkerResult(uuid4(), WorkerStatus.SUCCESS)),
                              process=SimpleNamespace(poll=Mock(return_value=0)),
                              close=Mock(side_effect=[OSError("cleanup busy"), None]))
        window = PrepareWindow.__new__(PrepareWindow)
        window.job, window.closing = job, False
        window.root, window.bar, window.run_button, window.status, window.report = (Mock() for _ in range(5))
        with self.assertRaisesRegex(OSError, "cleanup busy"):
            window.poll()
        self.assertIs(window.job, job)
        window.root.after.assert_called_once_with(100, window.poll)
        window.poll()
        self.assertIsNone(window.job)
        self.assertEqual(job.close.call_count, 2)


if __name__ == "__main__":
    unittest.main()
