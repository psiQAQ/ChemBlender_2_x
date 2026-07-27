import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    ImportBatch,
    QCProject,
    QualityStatus,
    Structure,
    TopologyRecord,
    TopologySource,
    close_session,
    create_session,
)
from ChemBlender.core.topology.infer import TopologyInferenceSettings
from ChemBlender.ui.topology import (
    compute_topology_proposal,
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
        from ChemBlender.core import PeriodicSiteData

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

    def test_compute_commits_one_deterministic_nonperiodic_proposal(self):
        reference = structure()
        project = QCProject(uuid4(), "0.2")
        project.commit(ImportBatch(structures=(reference,)))
        with TemporaryDirectory() as directory:
            session = create_session(
                temp_parent=Path(directory),
                project=project,
            )
            try:
                first, created = compute_topology_proposal(
                    session,
                    reference.id,
                    TopologyInferenceSettings(),
                )
                second, repeated = compute_topology_proposal(
                    session,
                    reference.id,
                    TopologyInferenceSettings(),
                )

                self.assertTrue(created)
                self.assertFalse(repeated)
                self.assertIs(second, first)
                self.assertEqual(len(project.topologies), 1)
                self.assertEqual(first.source_kind, TopologySource.DISTANCE_INFERRED)
                self.assertIn("topology", session.dirty_reasons)
            finally:
                close_session(session)

    def test_compute_selects_periodic_inference_for_periodic_structure(self):
        reference = structure(periodic=True)
        project = QCProject(uuid4(), "0.2")
        project.commit(ImportBatch(structures=(reference,)))
        with TemporaryDirectory() as directory:
            session = create_session(
                temp_parent=Path(directory),
                project=project,
            )
            try:
                proposal, created = compute_topology_proposal(
                    session,
                    reference.id,
                    TopologyInferenceSettings(),
                )

                self.assertTrue(created)
                self.assertEqual(proposal.structure_id, reference.id)
                self.assertIn(
                    ("periodic", True),
                    proposal.inference_parameters,
                )
            finally:
                close_session(session)


if __name__ == "__main__":
    unittest.main()
