import importlib
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from chemblender_prepare.core.exporters import ExportCancelled
from tests.test_project_browser_model import (
    FORCE_ID,
    FRAME_SET_ID,
    STRUCTURE_ID,
    sample_trajectory_project,
)


MOL2_FIXTURES = Path(__file__).parent / "fixtures" / "mol2"
PDB_FIXTURES = Path(__file__).parent / "fixtures" / "pdb"
PQR_FIXTURES = Path(__file__).parent / "fixtures" / "pqr"


def _mol2_project(*names):
    from cbq_core.model import QCProject
    from chemblender_prepare.core.formats.mol2 import parse_mol2

    project = QCProject(uuid4(), "1.0")
    batches = tuple(parse_mol2(MOL2_FIXTURES / name) for name in names)
    for batch in batches:
        project.commit(batch)
    return project, batches


def _pdb_project(*names):
    from cbq_core.model import QCProject
    from chemblender_prepare.core.formats.pdb import parse_pdb

    project = QCProject(uuid4(), "1.0")
    batches = tuple(parse_pdb(PDB_FIXTURES / name) for name in names)
    for batch in batches:
        project.commit(batch)
    return project, batches


def _pqr_project(*names):
    from cbq_core.model import QCProject
    from chemblender_prepare.core.formats.pqr import parse_pqr

    project = QCProject(uuid4(), "1.0")
    batches = tuple(parse_pqr(PQR_FIXTURES / name) for name in names)
    for batch in batches:
        project.commit(batch)
    return project, batches


class ExternalExportSelectionTests(unittest.TestCase):
    """Scientific selection and loss checks use the actual external export service."""

    def test_frame_set_selection_resolves_structure_and_related_properties(self):
        module = importlib.import_module("chemblender_prepare.export_service")

        selection = module.resolve_export_selection(
            sample_trajectory_project(),
            FRAME_SET_ID,
        )

        self.assertEqual(selection.structure.id, STRUCTURE_ID)
        self.assertEqual(selection.frame_set.id, FRAME_SET_ID)
        self.assertEqual(
            tuple(item.id for item in selection.properties),
            (FORCE_ID,),
        )
        report = module.preview_export_selection(selection, "extxyz")
        self.assertFalse(report.written)
        self.assertFalse(report.requires_confirmation)


    def test_pqr_selection_reuses_biological_projection_and_core_preview(self):
        from cbq_core.model import DatasetStatus
        from chemblender_prepare.core.exporters import preview_pqr_export

        module = importlib.import_module("chemblender_prepare.export_service")
        project, batches = _pqr_project("with-chain.pqr", "no-chain.pqr")
        selected, unrelated = batches
        selection = module.resolve_export_selection(
            project,
            selected.structures[0].id,
        )
        projection = module._pdb_entities(selection)

        self.assertEqual(projection.structures, selected.structures)
        self.assertEqual(
            projection.biological_hierarchies,
            selected.biological_hierarchies,
        )
        self.assertEqual(
            {value.semantic_role for value in projection.datasets},
            {"partial_charge", "radius"},
        )
        self.assertNotIn(unrelated.structures[0], projection.structures)
        self.assertTrue(
            all(
                value.structure_id == selection.structure.id
                for value in projection.datasets
            )
        )
        with patch.object(module, "export_pqr") as writer:
            self.assertEqual(
                module.preview_export_selection(selection, "pqr"),
                preview_pqr_export(projection),
            )
        writer.assert_not_called()

        hierarchy = selection.biological_hierarchies[0]
        for label, invalid, message in (
            (
                "missing charge",
                replace(
                    selection,
                    properties=tuple(
                        value
                        for value in selection.properties
                        if value.semantic_role != "partial_charge"
                    ),
                ),
                "Charge|charge",
            ),
            (
                "missing radius",
                replace(
                    selection,
                    properties=tuple(
                        value
                        for value in selection.properties
                        if value.semantic_role != "radius"
                    ),
                ),
                "Radius|radius",
            ),
            (
                "partial charge",
                replace(
                    selection,
                    properties=tuple(
                        replace(value, status=DatasetStatus.PARTIAL)
                        if value.semantic_role == "partial_charge"
                        else value
                        for value in selection.properties
                    ),
                ),
                "partial_charge",
            ),
            (
                "partial radius",
                replace(
                    selection,
                    properties=tuple(
                        replace(value, status=DatasetStatus.PARTIAL)
                        if value.semantic_role == "radius"
                        else value
                        for value in selection.properties
                    ),
                ),
                "radius",
            ),
            (
                "missing hierarchy",
                replace(selection, biological_hierarchies=()),
                "MissingHierarchy",
            ),
            (
                "ambiguous hierarchy",
                replace(
                    selection,
                    biological_hierarchies=(hierarchy, hierarchy),
                ),
                "Ambiguous",
            ),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    module.preview_export_selection(invalid, "pqr")


    def test_mol2_selection_projects_only_the_selected_record(self):
        module = importlib.import_module("chemblender_prepare.export_service")
        project, (selected, unrelated) = _mol2_project(
            "small.mol2",
            "aromatic.mol2",
        )

        selection = module.resolve_export_selection(
            project,
            selected.structures[0].id,
        )
        projection = module._mol2_entities(selection)

        self.assertEqual(projection.structures, (selection.structure,))
        self.assertEqual(projection.topologies, (selection.topology,))
        self.assertEqual(projection.molecular_records, (selection.record,))
        self.assertEqual(projection.datasets, selection.properties)
        self.assertEqual(projection.annotations, selection.annotations)
        self.assertEqual(
            {value.id for value in projection.annotations},
            {value.id for value in selected.annotations},
        )
        self.assertTrue(
            {value.id for value in projection.datasets}.isdisjoint(
                value.id for value in unrelated.datasets
            )
        )


    def test_mol2_multi_record_selection_excludes_sibling_datasets(self):
        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _mol2_project("multi.mol2")

        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )
        projection = module._mol2_entities(selection)
        selected_ids = {
            selection.structure.id,
            selection.topology.id,
            selection.record.id,
            *(value.id for value in projection.datasets),
        }

        self.assertEqual(
            {value.structure_id for value in projection.datasets},
            {selection.structure.id},
        )
        self.assertTrue(
            all(
                value.target_entity_id in selected_ids
                for value in projection.annotations
            )
        )


    def test_pdb_structure_selection_projects_exact_hierarchy_and_properties(self):
        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _pdb_project("atom-hetatm.pdb")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        helper = getattr(module, "_pdb_entities", None)
        self.assertIsNotNone(helper)
        projection = helper(selection)

        self.assertEqual(projection.structures, (selection.structure,))
        self.assertEqual(
            projection.biological_hierarchies,
            batch.biological_hierarchies,
        )
        self.assertEqual(
            {value.id for value in projection.datasets},
            {
                value.id
                for value in batch.datasets
                if getattr(value, "structure_id", None) == selection.structure.id
            },
        )


    def test_structure_extxyz_does_not_silently_drop_bound_properties(self):
        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _pdb_project("altloc.pdb")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        self.assertTrue(selection.properties)
        self.assertEqual(
            module._extxyz_properties(selection),
            selection.properties,
        )
        with self.assertRaisesRegex(
            TypeError,
            "properties must contain frame property datasets",
        ):
            module.preview_export_selection(selection, "extxyz")


    def test_pdb_frame_set_selection_emits_each_model_once_with_exact_datasets(self):
        from cbq_core.model import FrameSet
        from cbq_core.model import QCProject
        from chemblender_prepare.core.exporters import export_pdb
        from tests.test_biological_atom_data import biological_mapping_fixture

        module = importlib.import_module("chemblender_prepare.export_service")
        batch = biological_mapping_fixture()
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        frame_set = next(
            value for value in batch.datasets if isinstance(value, FrameSet)
        )

        selection = module.resolve_export_selection(project, frame_set.id)
        projection = module._pdb_entities(selection)

        expected_datasets = {
            value.id
            for value in batch.datasets
            if value is frame_set
            or getattr(value, "structure_id", None) == selection.structure.id
        }
        self.assertEqual(
            {value.id for value in projection.datasets},
            expected_datasets,
        )
        self.assertEqual(len(projection.biological_hierarchies), 1)
        exported = export_pdb(projection).text
        self.assertEqual(exported.count("MODEL"), 2)
        self.assertEqual(exported.count("ATOM  "), 4)
        self.assertEqual(
            module.preview_export_selection(selection, "extxyz").frame_count,
            2,
        )


    def test_pdb_preview_preserves_missing_and_ambiguous_hierarchy_fail_closed(self):
        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _pdb_project("atom-hetatm.pdb")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        with self.assertRaisesRegex(ValueError, "MissingHierarchy"):
            module.preview_export_selection(
                replace(selection, biological_hierarchies=()),
                "pdb",
            )
        hierarchy = selection.biological_hierarchies[0]
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            module.preview_export_selection(
                replace(
                    selection,
                    biological_hierarchies=(hierarchy, hierarchy),
                ),
                "pdb",
            )


    def test_molecular_structure_selection_binds_topology_and_raw_record(self):
        from chemblender_prepare.core.formats.smiles import parse_smiles_text

        module = importlib.import_module("chemblender_prepare.export_service")
        batch = parse_smiles_text("CO")
        structure = batch.structures[0]
        topology = batch.topologies[0]
        record = batch.molecular_records[0]
        project = SimpleNamespace(
            structures={structure.id: structure},
            topologies={topology.id: topology},
            molecular_records={record.id: record},
            datasets={},
        )

        selection = module.resolve_export_selection(project, structure.id)

        self.assertIs(selection.topology, topology)
        self.assertIs(selection.record, record)
        self.assertEqual(
            module.preview_export_selection(selection, "sdf").format,
            "sdf",
        )
        record_selection = module.resolve_export_selection(
            project,
            record.id,
        )
        self.assertIs(record_selection.structure, structure)
        self.assertIs(record_selection.topology, topology)
        self.assertIs(record_selection.record, record)


    def test_conformer_selection_uses_its_reference_topology(self):
        from chemblender_prepare.core.formats.smiles import parse_smiles_text

        module = importlib.import_module("chemblender_prepare.export_service")
        batch = parse_smiles_text("CO")
        structure = batch.structures[0]
        first_topology = batch.topologies[0]
        second_id = uuid4()
        second_topology = replace(
            first_topology,
            id=second_id,
            revision=str(second_id),
        )
        structure = replace(
            structure,
            topology_ids=(first_topology.id, second_topology.id),
        )
        record = batch.molecular_records[0]
        project = SimpleNamespace(
            topologies={
                first_topology.id: first_topology,
                second_topology.id: second_topology,
            },
            molecular_records={record.id: record},
        )
        conformer_set = SimpleNamespace(
            reference_topology_id=second_topology.id,
        )

        selection = module._molecular_selection(
            project,
            structure,
            conformer_set=conformer_set,
        )

        self.assertIs(selection.topology, second_topology)
        self.assertIsNone(selection.record)


    def test_conformer_selection_does_not_bind_an_unrelated_single_record(self):
        from chemblender_prepare.core.formats.smiles import parse_smiles_text

        module = importlib.import_module("chemblender_prepare.export_service")
        batch = parse_smiles_text("CO")
        structure = batch.structures[0]
        topology = batch.topologies[0]
        record = batch.molecular_records[0]
        selection = module._molecular_selection(
            SimpleNamespace(
                topologies={topology.id: topology},
                molecular_records={record.id: record},
            ),
            structure,
            conformer_set=SimpleNamespace(
                reference_topology_id=topology.id,
            ),
        )

        self.assertIs(selection.topology, topology)
        self.assertIsNone(selection.record)


    def test_record_selection_rejects_missing_complete_topology(self):
        from chemblender_prepare.core.formats.smiles import parse_smiles_text

        module = importlib.import_module("chemblender_prepare.export_service")
        batch = parse_smiles_text("CO")
        structure = batch.structures[0]
        topology = batch.topologies[0]
        record = batch.molecular_records[0]
        mismatched_record = SimpleNamespace(
            id=record.id,
            structure_id=structure.id,
            topology_id=object(),
        )
        project = SimpleNamespace(
            structures={structure.id: structure},
            topologies={topology.id: topology},
            molecular_records={record.id: mismatched_record},
            datasets={},
        )

        with self.assertRaisesRegex(
            ValueError,
            "selected MolecularRecord has no matching complete topology",
        ):
            module.resolve_export_selection(project, record.id)


    def test_conformer_preview_is_metadata_only(self):
        from chemblender_prepare.core.formats.smiles import parse_smiles_text

        module = importlib.import_module("chemblender_prepare.export_service")
        batch = parse_smiles_text("CO")
        selection = module.ExportSelection(
            structure=batch.structures[0],
            frame_set=None,
            properties=(),
            topology=batch.topologies[0],
            record=object(),
            conformer_set=SimpleNamespace(record_ids=(object(), object())),
            records_by_id={},
        )

        with (
            patch.object(
                module,
                "sdf_entries_from_conformer_set",
                side_effect=AssertionError("preview derived conformers"),
            ),
            patch.object(
                module,
                "export_sdf",
                side_effect=AssertionError("preview serialized SDF"),
            ),
        ):
            report = module.preview_export_selection(selection, "sdf")

        self.assertEqual(report.format, "sdf")
        self.assertFalse(report.written)
        self.assertEqual(report.frame_count, 2)


    def test_single_record_molecular_preview_never_calls_writers(self):
        from chemblender_prepare.core.formats.smiles import parse_smiles_text

        module = importlib.import_module("chemblender_prepare.export_service")
        batch = parse_smiles_text("CO")
        selection = module.ExportSelection(
            structure=batch.structures[0],
            frame_set=None,
            properties=(),
            topology=batch.topologies[0],
            record=batch.molecular_records[0],
        )

        with (
            patch.object(
                module,
                "export_mol",
                side_effect=AssertionError("preview serialized MOL"),
            ),
            patch.object(
                module,
                "export_sdf",
                side_effect=AssertionError("preview serialized SDF"),
            ),
        ):
            mol_report = module.preview_export_selection(selection, "mol")
            sdf_report = module.preview_export_selection(selection, "sdf")

        self.assertEqual(mol_report.format, "mol")
        self.assertEqual(sdf_report.format, "sdf")


    def test_conformer_preview_reports_metadata_and_missing_record_loss(self):
        from cbq_core.model import TopologySource
        from chemblender_prepare.core.formats.smiles import parse_smiles_text

        module = importlib.import_module("chemblender_prepare.export_service")
        batch = parse_smiles_text("CO")
        structure = replace(
            batch.structures[0],
            molecular_multiplicity=2,
        )
        topology = replace(
            batch.topologies[0],
            source_kind=TopologySource.DISTANCE_INFERRED,
            inference_parameters=(("algorithm", "test"),),
        )
        selection = module.ExportSelection(
            structure=structure,
            frame_set=None,
            properties=(),
            topology=topology,
            conformer_set=SimpleNamespace(
                record_ids=(uuid4(), uuid4()),
            ),
            records_by_id={},
        )

        report = module.preview_export_selection(selection, "sdf")

        self.assertTrue(report.requires_confirmation)
        self.assertEqual(
            {entry.code for entry in report.entries},
            {
                "conformer_properties_omitted",
                "inferred_connectivity",
                "multiplicity_omitted",
            },
        )


    def test_pqr_external_export_roundtrips_and_cancels_atomically(self):
        from chemblender_prepare.core.formats.pqr import parse_pqr

        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _pqr_project("with-chain.pqr")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "selected.pqr"
            result = module.export_selection(
                destination,
                selection,
                format_name="pqr",
                confirm_loss=True,
                missing_value_token=None,
            )
            self.assertTrue(result.written)
            reparsed = parse_pqr(destination)
            self.assertEqual(
                reparsed.structures[0].atomic_numbers,
                selection.structure.atomic_numbers,
            )
            self.assertEqual(
                {
                    value.semantic_role
                    for value in reparsed.datasets
                },
                {"partial_charge", "radius"},
            )

            destination.write_bytes(b"prior destination\n")
            with self.assertRaises(ExportCancelled):
                module.export_selection(
                    destination,
                    selection,
                    format_name="pqr",
                    confirm_loss=True,
                    missing_value_token=None,
                    is_cancelled=lambda: True,
                )
            self.assertEqual(destination.read_bytes(), b"prior destination\n")
            self.assertEqual(tuple(root.iterdir()), (destination,))


    def test_pqr_loss_preview_blocks_unconfirmed_external_write(self):
        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _pqr_project("with-chain.pqr")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )
        selection = replace(
            selection,
            structure=replace(selection.structure, molecular_charge=0),
        )
        preview = module.preview_export_selection(selection, "pqr")
        self.assertTrue(preview.requires_confirmation)

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "blocked.pqr"
            result = module.export_selection(
                destination,
                selection,
                format_name="pqr",
                confirm_loss=False,
                missing_value_token=None,
            )
            self.assertFalse(result.written)
            self.assertFalse(destination.exists())


    def test_pdb_conect_topology_reaches_loss_preview_and_confirmation(self):
        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _pdb_project("conect.pdb")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        self.assertIsNone(selection.topology)
        self.assertEqual(selection.associated_topologies, batch.topologies)
        projection = module._pdb_entities(selection)
        self.assertEqual(projection.topologies, batch.topologies)
        report = module.preview_export_selection(selection, "pdb")
        self.assertTrue(report.requires_confirmation)
        self.assertIn(
            "topology_omitted",
            tuple(entry.code for entry in report.entries),
        )

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "blocked.pdb"
            result = module.export_selection(destination, selection, format_name="pdb", confirm_loss=False)
            self.assertFalse(result.written)
            self.assertFalse(destination.exists())


    def test_pdb_preview_matches_core_and_requires_explicit_loss_confirmation(self):
        from chemblender_prepare.core.exporters import preview_pdb_export

        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _pdb_project("atom-hetatm.pdb")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        self.assertIsNotNone(getattr(module, "preview_pdb_export", None))
        report = module.preview_export_selection(selection, "pdb")
        self.assertEqual(report, preview_pdb_export(module._pdb_entities(selection)))
        self.assertTrue(report.requires_confirmation)

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "blocked.pdb"
            result = module.export_selection(destination, selection, format_name="pdb", confirm_loss=False)
            self.assertFalse(result.written)
            self.assertFalse(destination.exists())


    def test_pdb_external_export_roundtrips_selected_structure(self):
        from chemblender_prepare.core.formats.pdb import parse_pdb

        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _pdb_project("atom-hetatm.pdb")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "selected.pdb"
            result = module.export_selection(
                destination,
                selection,
                format_name="pdb",
                confirm_loss=True,
                missing_value_token=None,
            )

            self.assertTrue(result.written)
            reparsed = parse_pdb(destination)
            self.assertEqual(
                reparsed.structures[0].atomic_numbers,
                selection.structure.atomic_numbers,
            )
            self.assertEqual(
                reparsed.biological_hierarchies[0].atom_count,
                selection.biological_hierarchies[0].atom_count,
            )


    def test_pdb_external_export_blocks_unconfirmed_loss_without_writing(self):
        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _pdb_project("atom-hetatm.pdb")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "blocked.pdb"
            result = module.export_selection(
                destination,
                selection,
                format_name="pdb",
                confirm_loss=False,
                missing_value_token=None,
            )

            self.assertFalse(result.written)
            self.assertFalse(destination.exists())


    def test_cancelled_pdb_export_preserves_destination_and_cleans_temporary(self):
        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _pdb_project("atom-hetatm.pdb")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "selected.pdb"
            destination.write_bytes(b"prior destination\n")
            with self.assertRaises(ExportCancelled):
                module.export_selection(
                    destination,
                    selection,
                    format_name="pdb",
                    confirm_loss=True,
                    missing_value_token=None,
                    is_cancelled=lambda: True,
                )

            self.assertEqual(destination.read_bytes(), b"prior destination\n")
            self.assertEqual(tuple(root.iterdir()), (destination,))


    def test_mol2_preview_matches_core_and_rejects_conformers(self):
        from chemblender_prepare.core.exporters import preview_mol2_export

        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _mol2_project("small.mol2")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        with patch.object(
            module,
            "export_mol2",
            side_effect=AssertionError("preview serialized MOL2"),
        ):
            report = module.preview_export_selection(selection, "mol2")

        self.assertEqual(
            report,
            preview_mol2_export(module._mol2_entities(selection)),
        )
        self.assertTrue(report.requires_confirmation)
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "blocked.mol2"
            result = module.export_selection(destination, selection, format_name="mol2", confirm_loss=False)
            self.assertFalse(result.written)
            self.assertFalse(destination.exists())
        with self.assertRaisesRegex(ValueError, "ConformerSet export requires SDF"):
            module.preview_export_selection(
                replace(selection, conformer_set=object()),
                "mol2",
            )


    def test_mol2_external_export_roundtrips_and_cancels_atomically(self):
        from chemblender_prepare.core.formats.mol2 import parse_mol2

        module = importlib.import_module("chemblender_prepare.export_service")
        project, (batch,) = _mol2_project("small.mol2")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "selected.mol2"
            result = module.export_selection(
                destination,
                selection,
                format_name="mol2",
                confirm_loss=True,
                missing_value_token=None,
            )
            reparsed = parse_mol2(destination)
            self.assertEqual(
                reparsed.structures[0].atomic_numbers,
                selection.structure.atomic_numbers,
            )
            self.assertEqual(
                tuple(map(tuple, reparsed.topologies[0].bond_indices.values)),
                tuple(map(tuple, selection.topology.bond_indices.values)),
            )

            destination.write_bytes(b"prior destination\n")
            with self.assertRaises(ExportCancelled):
                module.export_selection(
                    destination,
                    selection,
                    format_name="mol2",
                    confirm_loss=True,
                    missing_value_token=None,
                    is_cancelled=lambda: True,
                )
            self.assertEqual(destination.read_bytes(), b"prior destination\n")
            self.assertEqual(tuple(root.iterdir()), (destination,))


    def test_cancelled_external_export_leaves_no_destination_or_temporary(self):
        module = importlib.import_module("chemblender_prepare.export_service")
        selection = module.resolve_export_selection(
            sample_trajectory_project(),
            FRAME_SET_ID,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "trajectory.extxyz"
            with self.assertRaises(ExportCancelled):
                module.export_selection(
                    destination,
                    selection,
                    format_name="extxyz",
                    confirm_loss=False,
                    missing_value_token=None,
                    is_cancelled=lambda: True,
                )


            self.assertFalse(destination.exists())
            self.assertEqual(tuple(root.iterdir()), ())


    def test_cli_reports_unconfirmed_export_as_failure_and_writes_only_after_confirmation(self):
        import io
        import json
        from contextlib import redirect_stdout
        from cbq_core.sidecar import save_project
        from chemblender_prepare.cli import main
        cases = (("pdb", _pdb_project, "atom-hetatm.pdb"),
                 ("mol2", _mol2_project, "small.mol2"),
                 ("pqr", _pqr_project, "with-chain.pqr"))
        for format_name, factory, fixture in cases:
            with self.subTest(format=format_name), TemporaryDirectory() as directory:
                root = Path(directory)
                project, (batch,) = factory(fixture)
                if format_name == "pqr":
                    # PQR cannot retain a molecular charge; make that loss explicit.
                    structure = batch.structures[0]
                    project.structures[structure.id] = replace(structure, molecular_charge=0)
                source = root / "input.cbq"
                save_project(source, project)
                destination = root / ("output." + format_name)
                args = ["export", str(source), "-o", str(destination), "--entity",
                        str(batch.structures[0].id), "--format", format_name, "--json"]
                stream = io.StringIO()
                with redirect_stdout(stream):
                    code = main(args + ["--preview"])
                preview = json.loads(stream.getvalue())
                self.assertEqual(code, 0, preview)
                self.assertTrue(preview["metadata"]["preview"]["requires_confirmation"])
                self.assertFalse(destination.exists())
                stream = io.StringIO()
                with redirect_stdout(stream):
                    code = main(args)
                failure = json.loads(stream.getvalue())
                self.assertEqual(code, 1, failure)
                self.assertEqual(failure["status"], "error")
                self.assertFalse(destination.exists())
                stream = io.StringIO()
                with redirect_stdout(stream):
                    code = main(args + ["--confirm-loss"])
                result = json.loads(stream.getvalue())
                self.assertEqual(code, 0, result)
                self.assertTrue(result["metadata"]["report"]["written"])
                self.assertTrue(destination.is_file())


    def test_molecular_formats_are_public_export_choices(self):
        from chemblender_prepare.cli import build_parser
        from chemblender_prepare.gui import command_arguments
        for format_name in ('mol', 'sdf', 'smiles'):
            with self.subTest(format=format_name):
                args = command_arguments({"command": "export", "sources": "input.cbq",
                    "output": "selected." + format_name, "entity": str(STRUCTURE_ID), "format": format_name})
                parsed = build_parser().parse_args(args)
                self.assertEqual(parsed.format, format_name)
                self.assertEqual(parsed.entity, str(STRUCTURE_ID))
                self.assertEqual(parsed.output, "selected." + format_name)


    def test_mol2_is_a_public_export_choice_in_cli_and_gui(self):
        from chemblender_prepare.cli import build_parser
        from chemblender_prepare.gui import command_arguments
        for format_name in ('mol2',):
            with self.subTest(format=format_name):
                args = command_arguments({"command": "export", "sources": "input.cbq",
                    "output": "selected." + format_name, "entity": str(STRUCTURE_ID), "format": format_name})
                parsed = build_parser().parse_args(args)
                self.assertEqual(parsed.format, format_name)
                self.assertEqual(parsed.entity, str(STRUCTURE_ID))
                self.assertEqual(parsed.output, "selected." + format_name)


    def test_pdb_is_a_public_export_choice_in_cli_and_gui(self):
        from chemblender_prepare.cli import build_parser
        from chemblender_prepare.gui import command_arguments
        for format_name in ('pdb',):
            with self.subTest(format=format_name):
                args = command_arguments({"command": "export", "sources": "input.cbq",
                    "output": "selected." + format_name, "entity": str(STRUCTURE_ID), "format": format_name})
                parsed = build_parser().parse_args(args)
                self.assertEqual(parsed.format, format_name)
                self.assertEqual(parsed.entity, str(STRUCTURE_ID))
                self.assertEqual(parsed.output, "selected." + format_name)


    def test_pqr_is_a_public_export_choice_in_cli_and_gui(self):
        from chemblender_prepare.cli import build_parser
        from chemblender_prepare.gui import command_arguments
        for format_name in ('pqr',):
            with self.subTest(format=format_name):
                args = command_arguments({"command": "export", "sources": "input.cbq",
                    "output": "selected." + format_name, "entity": str(STRUCTURE_ID), "format": format_name})
                parsed = build_parser().parse_args(args)
                self.assertEqual(parsed.format, format_name)
                self.assertEqual(parsed.entity, str(STRUCTURE_ID))
                self.assertEqual(parsed.output, "selected." + format_name)


class ExternalExportInteractionTests(unittest.TestCase):
    """Explicit external format selection and task cancellation replace legacy RNA/modal calls."""

    def test_conformers_require_explicit_sdf_in_external_tool(self):
        from chemblender_prepare.export_service import ExportSelection, preview_export_selection
        from chemblender_prepare.core.formats.smiles import parse_smiles_text
        batch = parse_smiles_text("CO")
        selection = ExportSelection(batch.structures[0], None, (), topology=batch.topologies[0],
            conformer_set=SimpleNamespace(record_ids=(uuid4(), uuid4())), records_by_id={})
        with self.assertRaisesRegex(ValueError, "ConformerSet export requires SDF"):
            preview_export_selection(selection, "mol")
        self.assertEqual(preview_export_selection(selection, "sdf").frame_count, 2)

    def test_record_selection_preserves_explicit_molecular_format(self):
        from chemblender_prepare.export_service import ExportSelection, preview_export_selection
        from chemblender_prepare.core.formats.smiles import parse_smiles_text
        from chemblender_prepare.gui import command_arguments
        from chemblender_prepare.cli import build_parser
        batch = parse_smiles_text("CO")
        selection = ExportSelection(batch.structures[0], None, (), topology=batch.topologies[0], record=batch.molecular_records[0])
        args = command_arguments({"command": "export", "sources": "input.cbq", "output": "output.smiles",
            "format": "smiles", "entity": str(batch.molecular_records[0].id)})
        parsed = build_parser().parse_args(args)
        self.assertEqual(parsed.format, "smiles")
        self.assertEqual(preview_export_selection(selection, parsed.format).format, "smiles")

    def test_changed_export_values_reset_confirmation_and_request_preview(self):
        from chemblender_prepare.gui import PrepareWindow
        from unittest.mock import Mock
        window = PrepareWindow.__new__(PrepareWindow)
        window.confirm_loss, window.preview = Mock(), Mock()
        window.job = None
        window.invalidate_export_confirmation()
        window.confirm_loss.set.assert_called_once_with(False)
        window.preview.set.assert_called_once_with(True)
        self.assertIsNone(window.job)

    def test_unchanged_text_event_does_not_clear_confirmation(self):
        from chemblender_prepare.gui import PrepareWindow
        from unittest.mock import Mock
        window = PrepareWindow.__new__(PrepareWindow)
        window.invalidate_export_confirmation = Mock()
        widget = Mock()
        widget.edit_modified.return_value = False
        window.input_text_changed(SimpleNamespace(widget=widget))
        window.invalidate_export_confirmation.assert_not_called()
        widget.edit_modified.return_value = True
        window.input_text_changed(SimpleNamespace(widget=widget))
        window.invalidate_export_confirmation.assert_called_once_with()
        widget.edit_modified.assert_called_with(False)

    def test_raw_export_is_not_a_viewer_registration_root(self):
        from ChemBlender.runtime.registration import REGISTER_MODULE_NAMES
        self.assertNotIn(".ui.export", REGISTER_MODULE_NAMES)
        from chemblender_prepare.cli import build_parser
        args = build_parser().parse_args(["export", "input.cbq", "-o", "output.pdb",
            "--format", "pdb", "--entity", str(STRUCTURE_ID)])
        self.assertEqual(args.command, "export")

    def test_gui_cancel_collects_real_child_before_releasing_task_once(self):
        import subprocess
        import time
        from unittest.mock import Mock
        import chemblender_prepare.gui as gui
        script = """
import sys, time
from pathlib import Path
from uuid import uuid4
from cbq_core.worker_protocol import WorkerResult, WorkerStatus, WorkerError, write_result
cancel, task = map(Path, sys.argv[1:])
task.mkdir()
(task / 'ready').touch()
while not cancel.exists():
    time.sleep(.01)
write_result(task / 'result.json', WorkerResult(uuid4(), WorkerStatus.CANCELLED, error=WorkerError('cancelled', 'Cancelled by user')))
"""
        original = subprocess.Popen
        def launch(argv, **kwargs):
            cancel = argv[argv.index("--cancel-file") + 1]
            task = argv[argv.index("--task-directory") + 1]
            return original([sys.executable, "-c", script, cancel, task], **kwargs)
        with patch.object(gui.subprocess, "Popen", side_effect=launch):
            job = gui.CliProcess(["formats"])
        root = job.root
        window = gui.PrepareWindow.__new__(gui.PrepareWindow)
        window.job, window.closing = job, False
        window.root, window.status, window.bar, window.report, window.run_button = (Mock() for _ in range(5))
        try:
            deadline = time.monotonic() + 10
            while not (job.task / "ready").exists() and time.monotonic() < deadline:
                self.assertIsNone(job.process.poll())
                time.sleep(.01)
            self.assertTrue((job.task / "ready").exists())
            with patch.object(job, "close", wraps=job.close) as close:
                window.cancel()
                deadline = time.monotonic() + 10
                while window.job is not None and time.monotonic() < deadline:
                    window.poll()
                    time.sleep(.01)
                self.assertIsNone(window.job)
                self.assertIsNotNone(job.process.poll())
                close.assert_called_once_with()
                self.assertFalse(root.exists())
                self.assertIn('"status": "cancelled"', window.report.insert.call_args.args[1])
                window.cancel()
                window.poll()
                close.assert_called_once_with()
        finally:
            if job.process.poll() is None:
                job.cancel()
                job.process.wait(timeout=10)
            if root.exists():
                job.close()


if __name__ == "__main__":
    unittest.main()
