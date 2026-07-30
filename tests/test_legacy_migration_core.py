import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import QCProject, close_project, create_session, open_project
from ChemBlender.legacy.extraction import (
    LegacyCIFAtomSnapshot,
    LegacyCIFSnapshot,
    LegacyDiagnostic,
    LegacyEdgeSnapshot,
    LegacyExtractionReport,
    LegacyObjectSnapshot,
)
from ChemBlender.legacy.migration import (
    LegacyMigrationCommitResult,
    QualityStatus,
    commit_legacy_migration,
    plan_legacy_migration,
)


def molecule_snapshot():
    return LegacyObjectSnapshot(
        name="legacy_formaldehyde",
        kind="scaffold",
        collections=("Legacy Molecules",),
        atomic_numbers=(6, 8, 1, 1),
        coordinates=((0.0, 0.0, 0.0), (1.21, 0.0, 0.0), (-0.6, 0.94, 0.0), (-0.6, -0.94, 0.0)),
        edges=(
            LegacyEdgeSnapshot((0, 1), 2, 0.65, False),
            LegacyEdgeSnapshot((0, 2), 1, 0.85, False),
            LegacyEdgeSnapshot((0, 3), 1, 0.85, False),
        ),
        radii=(0.76, 0.66, 0.31, 0.31),
        vdw_radii=(1.7, 1.55, 1.2, 1.2),
        atom_scales=(1.25, 1.1, 0.8, 0.8),
        colors=((0.12, 0.12, 0.12, 1.0), (1.0, 0.05, 0.05, 1.0), (1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0, 1.0)),
        cell=None,
        cif_original=None,
        cif_current=None,
    )


def crystal_snapshot():
    cif = LegacyCIFSnapshot(
        cell=(5.0, 6.0, 7.0, 90.0, 100.0, 110.0),
        space_group="P -1",
        space_group_number=2,
        symmetry_operations=("x,y,z", "-x,-y,-z"),
        atoms=(
            LegacyCIFAtomSnapshot("Cu1", "Cu", (0.1, 0.2, 0.3), 0.75, 0.01, "Uani", (0.011, 0.013, 0.017, 0.003, 0.002, 0.001)),
        ),
    )
    return LegacyObjectSnapshot(
        name="unit_partial_uij",
        kind="crystal",
        collections=("Legacy Crystal",),
        atomic_numbers=(29, 29),
        coordinates=((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
        edges=(),
        radii=None,
        vdw_radii=None,
        atom_scales=None,
        colors=None,
        cell=cif.cell,
        cif_original=cif,
        cif_current=cif,
    )


class LegacyMigrationCoreTests(unittest.TestCase):
    def setUp(self):
        self.project = QCProject(id=uuid4(), schema_version="1.0")

    def test_plan_maps_molecule_to_scientific_topology_and_display_plan(self):
        candidate, view_plans, report = plan_legacy_migration(
            LegacyExtractionReport(
                (molecule_snapshot(),),
                (LegacyDiagnostic("unknown_custom_property", "legacy note", "legacy_formaldehyde"),),
                None,
            ),
            self.project,
        )

        self.assertIsNot(candidate, self.project)
        self.assertEqual(self.project.structures, {})
        structure = next(iter(candidate.structures.values()))
        topology = next(iter(candidate.topologies.values()))
        self.assertEqual(structure.atomic_numbers, (6, 8, 1, 1))
        numpy.testing.assert_allclose(structure.coordinates.values, molecule_snapshot().coordinates)
        self.assertEqual(structure.topology_ids, (topology.id,))
        numpy.testing.assert_array_equal(topology.bond_indices.values, ((0, 1), (0, 2), (0, 3)))
        self.assertEqual(view_plans[0].settings.radii, molecule_snapshot().radii)
        self.assertEqual(view_plans[0].settings.colors, molecule_snapshot().colors)
        self.assertEqual(view_plans[0].settings.bond_scales, (0.65, 0.85, 0.85))
        self.assertEqual(view_plans[0].settings.dashed, (False, False, False))
        self.assertTrue(all(item.quality_status is QualityStatus.AMBIGUOUS for item in report.diagnostics))
        self.assertTrue(all(item.code == "legacy_unverified" for item in report.diagnostics))

    def test_plan_uses_current_cif_sites_and_skips_cell_only_auxiliary_object(self):
        cell_only = LegacyObjectSnapshot(
            name="cell_edges_partial_uij", kind="cell", collections=("Legacy Crystal",),
            atomic_numbers=(), coordinates=(), edges=(), radii=None, vdw_radii=None,
            atom_scales=None, colors=None, cell=crystal_snapshot().cell,
            cif_original=None, cif_current=None,
        )
        candidate, view_plans, _report = plan_legacy_migration(
            LegacyExtractionReport((crystal_snapshot(), cell_only), (), None), self.project
        )

        self.assertEqual(len(candidate.structures), 1)
        structure = next(iter(candidate.structures.values()))
        self.assertEqual(structure.atomic_numbers, (29,))
        self.assertIsNotNone(structure.periodic)
        self.assertEqual(structure.periodic.site_labels, ("Cu1",))
        self.assertEqual(structure.periodic.declared_space_group_name, "P -1")
        self.assertEqual(structure.periodic.declared_space_group_number, 2)
        self.assertEqual(structure.periodic.symmetry_operations, ("x,y,z", "-x,-y,-z"))
        numpy.testing.assert_allclose(structure.periodic.occupancies.values, (0.75,))
        self.assertEqual(len(view_plans), 1)

    def test_plan_records_missing_source_and_legacy_parents_without_fabricating_hash(self):
        candidate, _view_plans, report = plan_legacy_migration(
            LegacyExtractionReport((molecule_snapshot(),), (), None), self.project
        )

        provenance = next(iter(candidate.provenance.values()))
        self.assertEqual(provenance.operation, "legacy_blend_migration")
        self.assertEqual(provenance.source, "")
        self.assertEqual(provenance.source_hash, "")
        self.assertEqual(dict(provenance.parameters)["legacy_object_name"], "legacy_formaldehyde")
        self.assertEqual(dict(provenance.parameters)["legacy_collection_parents"], ("Legacy Molecules",))
        self.assertTrue(any(item.code == "legacy_unverified" for item in report.diagnostics))

    def test_plan_hashes_only_a_real_regular_blend_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "legacy.blend"
            source.write_bytes(b"legacy blend bytes")
            candidate, _view_plans, report = plan_legacy_migration(
                LegacyExtractionReport((molecule_snapshot(),), (), str(source)),
                self.project,
            )

        provenance = next(iter(candidate.provenance.values()))
        expected = sha256(b"legacy blend bytes").hexdigest()
        self.assertEqual(report.source_hash, expected)
        self.assertEqual(provenance.source, str(source))
        self.assertEqual(provenance.source_hash, expected)

    def test_plan_rejects_invalid_scientific_shape_and_commit_adopts_only_verified_project(self):
        malformed = molecule_snapshot()
        fields = {
            field: getattr(malformed, field)
            for field in malformed.__dataclass_fields__
        }
        fields["atomic_numbers"] = (6,)
        malformed = LegacyObjectSnapshot(
            **fields,
        )
        with self.assertRaisesRegex(ValueError, "atomic_numbers"):
            plan_legacy_migration(LegacyExtractionReport((malformed,), (), None), self.project)

        candidate, _view_plans, _report = plan_legacy_migration(
            LegacyExtractionReport((molecule_snapshot(),), (), None), self.project
        )
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=directory, project=self.project)
            original = session.project
            with patch("ChemBlender.legacy.migration.solidify_session", side_effect=OSError("publish failed")):
                with self.assertRaisesRegex(OSError, "publish failed"):
                    commit_legacy_migration(session, candidate)
            self.assertIs(session.project, original)
            result = commit_legacy_migration(session, candidate)
            self.assertIsInstance(result, LegacyMigrationCommitResult)
            self.assertIs(session.project, result.project)
            self.assertIsNot(session.project, candidate)
            reopened = open_project(result.sidecar_path)
            try:
                self.assertEqual(reopened.id, candidate.id)
            finally:
                close_project(reopened)
            close_project(session.project)


if __name__ == "__main__":
    unittest.main()
