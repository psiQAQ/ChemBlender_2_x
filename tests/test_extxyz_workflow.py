import importlib
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import sleep
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from ChemBlender.core.exporters import ExportCancelled
from tests.test_project_browser_model import (
    FORCE_ID,
    FRAME_SET_ID,
    STRUCTURE_ID,
    sample_trajectory_project,
)


MODULE = "ChemBlender.ui.export"
MOL2_FIXTURES = Path(__file__).parent / "fixtures" / "mol2"


def _mol2_project(*names):
    from ChemBlender.core import QCProject
    from ChemBlender.core.formats.mol2 import parse_mol2

    project = QCProject(uuid4(), "1.0")
    batches = tuple(parse_mol2(MOL2_FIXTURES / name) for name in names)
    for batch in batches:
        project.commit(batch)
    return project, batches


class _Property:
    def __init__(self, kind, **keywords):
        self.kind = kind
        self.keywords = keywords


def _property(kind):
    return lambda **keywords: _Property(kind, **keywords)


class _Operator:
    def report(self, levels, message):
        self.last_report = (levels, message)


class _WindowManager:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.calls = []
        self.timer = object()

    def _call(self, name):
        self.calls.append(name)
        if self.fail_at == name:
            raise RuntimeError(f"{name} failed")

    def event_timer_add(self, _interval, *, window):
        self._call("event_timer_add")
        return self.timer

    def event_timer_remove(self, timer):
        self.assert_timer(timer)
        self._call("event_timer_remove")

    def progress_begin(self, _low, _high):
        self._call("progress_begin")

    def progress_update(self, _value):
        self._call("progress_update")

    def progress_end(self):
        self._call("progress_end")

    def modal_handler_add(self, _operator):
        self._call("modal_handler_add")

    def assert_timer(self, timer):
        if timer is not self.timer:
            raise AssertionError("unexpected timer")


class ExtXYZWorkflowTests(unittest.TestCase):
    def setUp(self):
        fake_bpy = ModuleType("bpy")
        fake_props = ModuleType("bpy.props")
        for name, kind in (
            ("BoolProperty", "bool"),
            ("EnumProperty", "enum"),
            ("FloatProperty", "float"),
            ("StringProperty", "string"),
        ):
            setattr(fake_props, name, _property(kind))
        fake_bpy.props = fake_props
        fake_bpy.types = SimpleNamespace(Operator=_Operator)
        fake_bpy.app = SimpleNamespace(background=True)
        self.modules = patch.dict(
            sys.modules,
            {"bpy": fake_bpy, "bpy.props": fake_props},
        )
        self.modules.start()
        sys.modules.pop(MODULE, None)

    def tearDown(self):
        sys.modules.pop(MODULE, None)
        self.modules.stop()

    def test_frame_set_selection_resolves_structure_and_related_properties(self):
        module = importlib.import_module(MODULE)

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

    def test_molecular_formats_are_public_export_choices(self):
        module = importlib.import_module(MODULE)
        self.assertTrue({"mol", "sdf", "smiles"}.issubset({item[0] for item in module._FORMAT_ITEMS}))

    def test_mol2_is_a_public_export_choice_and_filter(self):
        module = importlib.import_module(MODULE)

        self.assertIn("mol2", {item[0] for item in module._FORMAT_ITEMS})
        filter_glob = (
            module.CHEMBLENDER_OT_export_project_entity
            .__annotations__["filter_glob"]
            .keywords["default"]
        )
        self.assertIn("*.mol2", filter_glob.split(";"))

    def test_mol2_selection_projects_only_the_selected_record(self):
        module = importlib.import_module(MODULE)
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

    def test_mol2_preview_matches_core_and_rejects_conformers(self):
        from ChemBlender.core.exporters import preview_mol2_export

        module = importlib.import_module(MODULE)
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
        operator = module.CHEMBLENDER_OT_export_project_entity()
        operator.filepath = "blocked.mol2"
        operator.format_name = "mol2"
        operator.confirm_loss = False
        operator.missing_value_token = ""
        with (
            patch.object(
                module,
                "get_scene_session",
                return_value=SimpleNamespace(
                    project=project,
                    active_entity_id=batch.structures[0].id,
                ),
            ),
            patch.object(module.ExportJob, "start") as start,
        ):
            result = operator.execute(SimpleNamespace(scene=object()))
        self.assertEqual(result, {"CANCELLED"})
        start.assert_not_called()
        with self.assertRaisesRegex(ValueError, "ConformerSet export requires SDF"):
            module.preview_export_selection(
                replace(selection, conformer_set=object()),
                "mol2",
            )

    def test_mol2_background_export_roundtrips_and_cancels_atomically(self):
        from ChemBlender.core.formats.mol2 import parse_mol2

        module = importlib.import_module(MODULE)
        project, (batch,) = _mol2_project("small.mol2")
        selection = module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "selected.mol2"
            job = module.ExportJob(
                destination,
                selection,
                format_name="mol2",
                confirm_loss=True,
                missing_value_token=None,
            )
            job.start()
            self.assertTrue(job.join(5))
            self.assertIsNone(job.error)
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
            cancelled = module.ExportJob(
                destination,
                selection,
                format_name="mol2",
                confirm_loss=True,
                missing_value_token=None,
            )
            cancelled.cancel()
            cancelled.start()
            self.assertTrue(cancelled.join(5))
            self.assertIsInstance(cancelled.error, ExportCancelled)
            self.assertEqual(destination.read_bytes(), b"prior destination\n")
            self.assertEqual(tuple(root.iterdir()), (destination,))

    def test_molecular_structure_selection_binds_topology_and_raw_record(self):
        from ChemBlender.core.formats.smiles import parse_smiles_text

        module = importlib.import_module(MODULE)
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
        from ChemBlender.core.formats.smiles import parse_smiles_text

        module = importlib.import_module(MODULE)
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
        from ChemBlender.core.formats.smiles import parse_smiles_text

        module = importlib.import_module(MODULE)
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
        from ChemBlender.core.formats.smiles import parse_smiles_text

        module = importlib.import_module(MODULE)
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
        from ChemBlender.core.formats.smiles import parse_smiles_text

        module = importlib.import_module(MODULE)
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
        from ChemBlender.core.formats.smiles import parse_smiles_text

        module = importlib.import_module(MODULE)
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
        from ChemBlender.core import TopologySource
        from ChemBlender.core.formats.smiles import parse_smiles_text

        module = importlib.import_module(MODULE)
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

    def test_conformer_selection_forces_sdf_format(self):
        module = importlib.import_module(MODULE)
        operator = module.CHEMBLENDER_OT_export_project_entity()
        operator.format_name = "mol"
        operator.missing_value_token = ""
        context = SimpleNamespace(
            scene=object(),
        )
        conformer_set = object()
        selection = module.ExportSelection(
            structure=object(),
            frame_set=None,
            properties=(),
            conformer_set=conformer_set,
        )

        session = SimpleNamespace(project=object(), active_entity_id=object())
        with (
            patch.object(module, "get_scene_session", return_value=session),
            patch.object(module, "resolve_export_selection", return_value=selection),
            patch.object(
                module,
                "preview_export_selection",
                return_value=SimpleNamespace(entries=()),
            ),
        ):
            resolved, _preview = operator._selection_and_preview(
                context,
                default_format=True,
            )

        self.assertIs(resolved.conformer_set, conformer_set)
        self.assertEqual(operator.format_name, "sdf")

    def test_record_selection_preserves_explicit_molecular_format(self):
        module = importlib.import_module(MODULE)
        operator = module.CHEMBLENDER_OT_export_project_entity()
        operator.format_name = "smiles"
        operator.missing_value_token = ""
        context = SimpleNamespace(scene=object())
        selection = module.ExportSelection(
            structure=object(),
            frame_set=None,
            properties=(),
            topology=object(),
            record=object(),
        )
        session = SimpleNamespace(project=object(), active_entity_id=object())

        with (
            patch.object(module, "get_scene_session", return_value=session),
            patch.object(module, "resolve_export_selection", return_value=selection),
            patch.object(
                module,
                "preview_export_selection",
                return_value=SimpleNamespace(entries=()),
            ),
        ):
            operator._selection_and_preview(context)

        self.assertEqual(operator.format_name, "smiles")

    def test_format_change_refreshes_loss_preview_and_clears_confirmation(self):
        module = importlib.import_module(MODULE)
        operator = module.CHEMBLENDER_OT_export_project_entity()
        operator.format_name = "smiles"
        operator.missing_value_token = ""
        operator.confirm_loss = True
        operator.loss_preview = "No data loss"
        context = SimpleNamespace(scene=object())
        selection = module.ExportSelection(
            structure=object(),
            frame_set=None,
            properties=(),
            topology=object(),
            record=object(),
        )
        report = SimpleNamespace(
            entries=(SimpleNamespace(message="SMILES omits coordinates"),),
        )
        session = SimpleNamespace(project=object(), active_entity_id=object())

        with (
            patch.object(module, "get_scene_session", return_value=session),
            patch.object(module, "resolve_export_selection", return_value=selection),
            patch.object(
                module,
                "preview_export_selection",
                return_value=report,
            ) as preview,
        ):
            update = (
                module.CHEMBLENDER_OT_export_project_entity
                .__annotations__["format_name"]
                .keywords["update"]
            )
            update(operator, context)

        preview.assert_called_once_with(selection, "smiles", "")
        self.assertEqual(operator.loss_preview, "SMILES omits coordinates")
        self.assertFalse(operator.confirm_loss)

    def test_export_update_callback_ignores_stale_rna_owner(self):
        module = importlib.import_module(MODULE)
        update = (
            module.CHEMBLENDER_OT_export_project_entity
            .__annotations__["format_name"]
            .keywords["update"]
        )
        owner = SimpleNamespace(confirm_loss=True, loss_preview="stale")

        update(owner, SimpleNamespace(scene=object()))

        self.assertFalse(owner.confirm_loss)
        self.assertEqual(owner.loss_preview, "stale")

    def test_cancelled_background_export_leaves_no_destination_or_temporary(self):
        module = importlib.import_module(MODULE)
        selection = module.resolve_export_selection(
            sample_trajectory_project(),
            FRAME_SET_ID,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "trajectory.extxyz"
            job = module.ExportJob(
                destination,
                selection,
                format_name="extxyz",
                confirm_loss=False,
                missing_value_token=None,
            )

            job.cancel()
            job.start()
            self.assertTrue(job.join(5))

            self.assertTrue(job.done)
            self.assertIsInstance(job.error, ExportCancelled)
            self.assertFalse(destination.exists())
            self.assertEqual(tuple(root.iterdir()), ())

    def test_export_operator_rna_is_small_and_module_is_explicit_root(self):
        module = importlib.import_module(MODULE)
        registration = importlib.import_module(
            "ChemBlender.runtime.registration"
        )

        self.assertIn(".ui.export", registration.REGISTER_MODULE_NAMES)
        operator = module.CHEMBLENDER_OT_export_project_entity
        self.assertEqual(operator.__module__, MODULE)
        self.assertTrue(
            all(
                value.kind in {"bool", "enum", "float", "string"}
                for value in operator.__annotations__.values()
            )
        )

    def test_modal_setup_failures_release_owned_ui_in_reverse_order(self):
        module = importlib.import_module(MODULE)
        module.bpy.app.background = False
        session = SimpleNamespace(
            project=sample_trajectory_project(),
            active_entity_id=FRAME_SET_ID,
        )
        cases = (
            (
                "progress_begin",
                (
                    "event_timer_add",
                    "progress_begin",
                    "event_timer_remove",
                ),
            ),
            (
                "modal_handler_add",
                (
                    "event_timer_add",
                    "progress_begin",
                    "progress_update",
                    "modal_handler_add",
                    "progress_end",
                    "event_timer_remove",
                ),
            ),
            (
                "job.start",
                (
                    "event_timer_add",
                    "progress_begin",
                    "progress_update",
                    "modal_handler_add",
                    "progress_end",
                    "event_timer_remove",
                ),
            ),
        )
        for failure, expected_calls in cases:
            with self.subTest(failure=failure):
                manager = _WindowManager(
                    None if failure == "job.start" else failure
                )
                context = SimpleNamespace(
                    scene=object(),
                    window=object(),
                    window_manager=manager,
                )
                operation = module.CHEMBLENDER_OT_export_project_entity()
                operation.filepath = "trajectory.extxyz"
                operation.format_name = "extxyz"
                operation.confirm_loss = False
                operation.missing_value_token = ""
                start_patch = (
                    patch.object(
                        module.ExportJob,
                        "start",
                        side_effect=RuntimeError("job.start failed"),
                    )
                    if failure == "job.start"
                    else patch.object(module.ExportJob, "start")
                )
                with (
                    patch.object(
                        module,
                        "get_scene_session",
                        return_value=session,
                    ),
                    start_patch,
                ):
                    result = operation.execute(context)

                self.assertEqual(result, {"CANCELLED"})
                self.assertEqual(tuple(manager.calls), expected_calls)
                self.assertIsNone(getattr(operation, "_job", None))
                self.assertIsNone(getattr(operation, "_timer", None))

    def test_operator_cancel_joins_worker_and_releases_ui_once(self):
        module = importlib.import_module(MODULE)
        selection = module.resolve_export_selection(
            sample_trajectory_project(),
            FRAME_SET_ID,
        )
        started = Event()

        def wait_for_cancel(*_args, is_cancelled, **_keywords):
            started.set()
            while not is_cancelled():
                sleep(0.001)
            raise ExportCancelled("export cancelled")

        manager = _WindowManager()
        job = module.ExportJob(
            "trajectory.extxyz",
            selection,
            format_name="extxyz",
            confirm_loss=False,
            missing_value_token=None,
        )
        job.attach_ui(manager, manager.timer)
        manager.progress_begin(0, 100)
        job.mark_progress_started()
        operation = module.CHEMBLENDER_OT_export_project_entity()
        operation._job = job
        operation._timer = manager.timer
        with patch.object(module, "export_extxyz", wait_for_cancel):
            job.start()
            self.assertTrue(started.wait(1))
            operation.cancel(SimpleNamespace(window_manager=manager))

        self.assertTrue(job.done)
        self.assertTrue(job.join(0))
        self.assertIsInstance(job.error, ExportCancelled)
        self.assertEqual(
            tuple(manager.calls),
            ("progress_begin", "progress_end", "event_timer_remove"),
        )
        self.assertIsNone(operation._job)
        self.assertIsNone(operation._timer)
        operation.cancel(SimpleNamespace(window_manager=manager))
        self.assertEqual(
            tuple(manager.calls),
            ("progress_begin", "progress_end", "event_timer_remove"),
        )

    def test_finish_job_reraises_generator_exit_unchanged(self):
        module = importlib.import_module(MODULE)
        operation = module.CHEMBLENDER_OT_export_project_entity()
        fatal = GeneratorExit("worker stopped")

        with self.assertRaises(GeneratorExit) as raised:
            operation._finish_job(SimpleNamespace(error=fatal))

        self.assertIs(raised.exception, fatal)

    def test_modal_progress_fatal_releases_job_before_reraising(self):
        module = importlib.import_module(MODULE)
        operation = module.CHEMBLENDER_OT_export_project_entity()
        released = []
        job = SimpleNamespace(
            done=True,
            error=None,
            join=lambda _timeout: True,
            release_ui=lambda: released.append(True),
        )
        operation._job = job
        operation._timer = object()
        context = SimpleNamespace(
            window_manager=SimpleNamespace(
                progress_update=lambda _value: (_ for _ in ()).throw(
                    MemoryError("progress exhausted memory")
                )
            )
        )

        with self.assertRaises(MemoryError):
            operation.modal(context, SimpleNamespace(type="TIMER"))

        self.assertEqual(released, [True])
        self.assertIsNone(operation._job)

    def test_modal_retries_timer_cleanup_before_reraising_completion_fatal(self):
        module = importlib.import_module(MODULE)
        operation = module.CHEMBLENDER_OT_export_project_entity()
        progress_calls = []
        release_calls = []
        job = SimpleNamespace(
            done=True,
            error=None,
            join=lambda _timeout: True,
            timer_pending=True,
        )

        def release():
            release_calls.append(True)
            if len(release_calls) == 1:
                raise OSError("timer cleanup failed")
            job.timer_pending = False

        job.release_ui = release
        job.abandon_ui = lambda: None
        operation._job = job
        operation._timer = object()
        operation.report = lambda *_args: None
        context = SimpleNamespace(
            window_manager=SimpleNamespace(
                progress_update=lambda _value: (
                    progress_calls.append(True)
                    or (_ for _ in ()).throw(
                        MemoryError("progress exhausted memory")
                    )
                )
            )
        )

        self.assertEqual(
            operation.modal(context, SimpleNamespace(type="TIMER")),
            {"RUNNING_MODAL"},
        )
        self.assertIs(operation._job, job)
        with self.assertRaisesRegex(MemoryError, "exhausted memory"):
            operation.modal(context, SimpleNamespace(type="TIMER"))

        self.assertEqual(progress_calls, [True])
        self.assertEqual(release_calls, [True, True])
        self.assertIsNone(operation._job)

    def test_cancel_reraises_fatal_cleanup_error(self):
        module = importlib.import_module(MODULE)
        operation = module.CHEMBLENDER_OT_export_project_entity()
        operation._job = object()
        fatal = MemoryError("cleanup exhausted memory")

        with patch.object(
            operation,
            "_cancel_and_release_job",
            side_effect=fatal,
        ):
            with self.assertRaises(MemoryError) as raised:
                operation.cancel(None)

        self.assertIs(raised.exception, fatal)


if __name__ == "__main__":
    unittest.main()
