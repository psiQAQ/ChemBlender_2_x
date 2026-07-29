import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from ChemBlender.core import QCProject, close_session, create_session, parse_poscar
from ChemBlender.core.import_pipeline.conformer_grouping import (
    suggest_staged_conformer_groups,
)
from ChemBlender.core.import_pipeline.request import (
    ImportRequest,
    ImportSource,
    ReaderOverride,
    ValidationMode,
)
from ChemBlender.reader_api.import_pipeline_bridge import (
    preflight_reader_plugins,
)
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "poscar"


class _Property:
    def __init__(self, kind, **keywords):
        self.kind = kind
        self.keywords = keywords


def _property(kind):
    return lambda **keywords: _Property(kind, **keywords)


class _Operator:
    def report(self, levels, message):
        self.last_report = (levels, message)


class _PropertyGroup:
    pass


class PoscarProductFlowTests(unittest.TestCase):
    def setUp(self):
        self.fake_bpy = ModuleType("bpy")
        props = ModuleType("bpy.props")
        for name, kind in (
            ("BoolProperty", "bool"),
            ("CollectionProperty", "collection"),
            ("EnumProperty", "enum"),
            ("FloatProperty", "float"),
            ("IntProperty", "int"),
            ("PointerProperty", "pointer"),
            ("StringProperty", "string"),
        ):
            setattr(props, name, _property(kind))
        self.fake_bpy.props = props
        self.fake_bpy.types = SimpleNamespace(
            Operator=_Operator,
            OperatorFileListElement=object,
            Panel=object,
            PropertyGroup=_PropertyGroup,
            Scene=type("Scene", (), {}),
        )
        self.fake_bpy.app = SimpleNamespace(background=True)
        self.fake_bpy.data = SimpleNamespace(
            objects=SimpleNamespace(remove=lambda *_args, **_kwargs: None),
            batch_remove=lambda **_kwargs: None,
        )
        self.fake_bpy.context = SimpleNamespace(collection=object())
        self.modules = patch.dict(
            sys.modules,
            {"bpy": self.fake_bpy, "bpy.props": props},
        )
        self.modules.start()
        for name in (
            "ChemBlender.ui.export",
            "ChemBlender.ui.import_preview",
            "ChemBlender.ui.properties",
        ):
            sys.modules.pop(name, None)
        self.properties = importlib.import_module("ChemBlender.ui.properties")
        self.preview_module = importlib.import_module(
            "ChemBlender.ui.import_preview"
        )
        self.export_module = importlib.import_module("ChemBlender.ui.export")
        self.temporary = tempfile.TemporaryDirectory()
        self.session = create_session(temp_parent=Path(self.temporary.name))

    def tearDown(self):
        try:
            self.properties.clear_quick_import_state(self.session)
        except BaseException:
            pass
        try:
            close_session(self.session)
        except BaseException:
            pass
        self.modules.stop()
        for name in (
            "ChemBlender.ui.export",
            "ChemBlender.ui.import_preview",
            "ChemBlender.ui.properties",
        ):
            sys.modules.pop(name, None)
        self.temporary.cleanup()

    def stage(self, source):
        staging = self.properties.create_quick_import_staging(self.session)
        request = ImportRequest(
            sources=(ImportSource(source),),
            validation_mode=ValidationMode.BALANCED,
        )
        registry = builtin_reader_plugin_registry()
        preview = preflight_reader_plugins(
            request,
            registry,
            staging,
            progress=lambda *_args: None,
            is_cancelled=lambda: False,
        )
        self.properties.store_quick_import_preview(
            self.session,
            staging,
            preview,
            conformer_grouping_suggestions=suggest_staged_conformer_groups(
                preview,
                staging,
            ),
        )
        return registry, self.properties.get_quick_import_state(self.session)

    def test_preview_summarizes_poscar_scientific_conventions(self):
        registry, state = self.stage(FIXTURES / "velocities.CONTCAR")

        row, = self.preview_module.project_import_preview(
            self.session,
            state,
            registry,
        )

        self.assertEqual(row.poscar_comment, "velocity block")
        self.assertIn("1", row.poscar_scale_summary)
        self.assertIn("27", row.poscar_cell_summary)
        self.assertEqual(row.poscar_species_summary, "Na Cl · 1 1")
        self.assertEqual(row.poscar_coordinate_mode, "Cartesian")
        self.assertEqual(row.poscar_selective_summary, "Selective Dynamics")
        self.assertEqual(
            row.poscar_velocity_summary,
            "Ion velocities · lattice velocities",
        )
        self.assertFalse(row.poscar_requires_species_assignment)

    def test_poscar_preview_bounds_comment_without_truncating_provenance(self):
        source = Path(self.temporary.name) / "long-comment.POSCAR"
        comment = "C" * 60_000
        lines = (FIXTURES / "cscl-selective.vasp").read_text(
            encoding="utf-8"
        ).splitlines()
        source.write_text(
            "\n".join((comment, *lines[1:])) + "\n",
            encoding="utf-8",
        )
        registry, state = self.stage(source)

        row, = self.preview_module.project_import_preview(
            self.session,
            state,
            registry,
        )
        batch = state.staging_session.result(
            state.preview.source_previews[0].staged_batch_ids[0]
        )
        provenance = next(
            value
            for value in batch.provenance
            if value.producer == "ChemBlender POSCAR adapter"
        )

        self.assertLessEqual(len(row.poscar_comment), 256)
        self.assertTrue(row.poscar_comment.endswith("…"))
        self.assertEqual(dict(provenance.parameters)["comment"], comment)

    def test_vasp4_species_assignment_restages_before_commit(self):
        registry, state = self.stage(FIXTURES / "vasp4-counts.POSCAR")
        row, = self.preview_module.project_import_preview(
            self.session,
            state,
            registry,
        )
        source_id = state.preview.source_previews[0].source_id

        self.assertTrue(row.poscar_requires_species_assignment)
        self.assertTrue(row.blocking)
        with self.assertRaisesRegex(ValueError, "count groups"):
            self.preview_module.restage_poscar_species_assignment(
                self.session,
                state,
                source_id,
                "Na",
                registry,
                ValidationMode.BALANCED,
            )

        self.preview_module.restage_poscar_species_assignment(
            self.session,
            state,
            source_id,
            "Na,Cl",
            registry,
            ValidationMode.BALANCED,
        )
        refreshed, = self.preview_module.project_import_preview(
            self.session,
            state,
            registry,
        )

        self.assertFalse(refreshed.poscar_requires_species_assignment)
        self.assertEqual(refreshed.poscar_species_assignment, "Na,Cl")
        self.assertFalse(refreshed.blocking)
        self.assertEqual(
            state.staging_session.result(
                state.preview.source_previews[0].staged_batch_ids[0]
            ).structures[0].atomic_numbers,
            (11, 11, 17),
        )

    def test_interactive_species_assignment_starts_cancellable_modal_job(self):
        registry, state = self.stage(FIXTURES / "vasp4-counts.POSCAR")
        source_id = state.preview.source_previews[0].source_id
        job = SimpleNamespace(
            staging=state.staging_session,
            attach_ui=Mock(),
            mark_progress_started=Mock(),
            start=Mock(),
        )
        manager = SimpleNamespace(
            event_timer_add=Mock(return_value=object()),
            progress_begin=Mock(),
            modal_handler_add=Mock(),
        )
        context = SimpleNamespace(
            scene=SimpleNamespace(
                chemblender_quick_import=SimpleNamespace(
                    validation_mode=ValidationMode.BALANCED.value,
                )
            ),
            window=object(),
            window_manager=manager,
        )
        operator = self.preview_module.CHEMBLENDER_OT_apply_poscar_species()
        operator.source_id = str(source_id)
        operator.species = "Na,Cl"
        self.fake_bpy.app.background = False
        try:
            with (
                patch.object(
                    self.preview_module,
                    "get_scene_session",
                    return_value=self.session,
                ),
                patch.object(
                    self.preview_module,
                    "get_reader_plugin_registry",
                    return_value=registry,
                ),
                patch.object(
                    self.preview_module,
                    "_new_preflight_job",
                    return_value=job,
                ),
            ):
                result = operator.execute(context)
        finally:
            self.fake_bpy.app.background = True

        self.assertEqual(result, {"RUNNING_MODAL"})
        job.start.assert_called_once_with()
        manager.progress_begin.assert_called_once_with(0, 100)
        self.assertIs(state.active_job, job)

    def test_poscar_modal_worker_forwards_parameters_without_grouping(self):
        quick_import = importlib.import_module("ChemBlender.ui.quick_import")
        staging = self.properties.create_quick_import_staging(self.session)
        source = ImportSource(FIXTURES / "vasp4-counts.POSCAR")
        job = quick_import._PreflightJob(
            ImportRequest(
                sources=(source,),
                validation_mode=ValidationMode.BALANCED,
                reader_overrides=(ReaderOverride(source.id, "poscar"),),
            ),
            builtin_reader_plugin_registry(),
            staging,
            canonical_parameters_by_source={
                source.id: {"species": "Na,Cl"}
            },
            prepare_conformers=False,
        )

        job.start()
        self.assertTrue(job.join(10))

        self.assertIsNone(job.error)
        self.assertIsNone(job.conformer_suggestions)
        batch = staging.result(
            job.preview.source_previews[0].staged_batch_ids[0]
        )
        self.assertEqual(batch.structures[0].atomic_numbers, (11, 11, 17))

    def test_poscar_modal_progress_failure_releases_ui_and_ownership(self):
        _registry, state = self.stage(FIXTURES / "vasp4-counts.POSCAR")
        source_id = state.preview.source_previews[0].source_id
        for failure in (
            RuntimeError("progress failed"),
            GeneratorExit("fatal progress failed"),
        ):
            with self.subTest(failure=type(failure).__name__):
                job = SimpleNamespace(
                    staging=state.staging_session,
                    drain_progress=Mock(
                        return_value=("preflight", 1, 3)
                    ),
                    done=False,
                    cancel=Mock(),
                    join=Mock(return_value=True),
                    release_ui=Mock(),
                    timer_pending=False,
                    abandon_ui=Mock(),
                    error=None,
                )
                self.properties.store_quick_import_job(
                    self.session,
                    state.staging_session,
                    job,
                )
                operator = (
                    self.preview_module.CHEMBLENDER_OT_apply_poscar_species()
                )
                operator._session = self.session
                operator._state = state
                operator._source_id = source_id
                operator._job = job
                context = SimpleNamespace(
                    window_manager=SimpleNamespace(
                        progress_update=Mock(side_effect=failure),
                    )
                )
                event = SimpleNamespace(type="TIMER")

                if isinstance(failure, GeneratorExit):
                    with self.assertRaises(GeneratorExit) as raised:
                        operator.modal(context, event)
                    self.assertIs(raised.exception, failure)
                else:
                    self.assertEqual(
                        operator.modal(context, event),
                        {"CANCELLED"},
                    )

                job.cancel.assert_called_once_with()
                job.join.assert_called_once_with(None)
                job.release_ui.assert_called_once_with()
                self.assertIsNone(state.active_job)
                self.assertIsNone(operator._job)

    def test_multiple_vasp4_assignments_survive_subsequent_restaging(self):
        staging = self.properties.create_quick_import_staging(self.session)
        first = Path(self.temporary.name) / "first.POSCAR"
        second = Path(self.temporary.name) / "second.POSCAR"
        shutil.copyfile(FIXTURES / "vasp4-counts.POSCAR", first)
        shutil.copyfile(FIXTURES / "vasp4-counts.POSCAR", second)
        sources = (
            ImportSource(first),
            ImportSource(second),
        )
        registry = builtin_reader_plugin_registry()
        preview = preflight_reader_plugins(
            ImportRequest(
                sources=sources,
                validation_mode=ValidationMode.BALANCED,
            ),
            registry,
            staging,
            progress=lambda *_args: None,
            is_cancelled=lambda: False,
        )
        self.properties.store_quick_import_preview(
            self.session,
            staging,
            preview,
        )
        state = self.properties.get_quick_import_state(self.session)

        self.preview_module.restage_poscar_species_assignment(
            self.session,
            state,
            sources[0].id,
            "Na,Cl",
            registry,
            ValidationMode.BALANCED,
        )
        with patch.object(
            self.preview_module,
            "preflight_reader_plugins",
            wraps=self.preview_module.preflight_reader_plugins,
        ) as preflight:
            self.preview_module.restage_poscar_species_assignment(
                self.session,
                state,
                sources[1].id,
                "K,Br",
                registry,
                ValidationMode.BALANCED,
            )

        atomic_numbers = tuple(
            state.staging_session.result(source.staged_batch_ids[0])
            .structures[0]
            .atomic_numbers
            for source in state.preview.source_previews
        )
        self.assertEqual(atomic_numbers, ((11, 11, 17), (19, 19, 35)))
        request = preflight.call_args.args[0]
        self.assertEqual(tuple(value.id for value in request.sources), (sources[1].id,))

    def test_poscar_export_selection_binds_properties_and_round_trips(self):
        batch = parse_poscar(FIXTURES / "cscl-selective.vasp")
        project = QCProject(uuid4(), "0.2")
        project.commit(batch)
        selection = self.export_module.resolve_export_selection(
            project,
            batch.structures[0].id,
        )

        self.assertIn("poscar", {item[0] for item in self.export_module._FORMAT_ITEMS})
        self.assertEqual(
            tuple(item.semantic_role for item in selection.properties),
            ("selective_dynamics",),
        )
        preview = self.export_module.preview_export_selection(
            selection,
            "poscar",
        )
        self.assertEqual(preview.format, "poscar")

        destination = Path(self.temporary.name) / "POSCAR"
        job = self.export_module.ExportJob(
            destination,
            selection,
            format_name="poscar",
            confirm_loss=False,
            missing_value_token=None,
        )
        job._run()

        self.assertIsNone(job.error)
        self.assertTrue(job.result.written)
        reparsed = parse_poscar(destination)
        self.assertEqual(
            reparsed.structures[0].atomic_numbers,
            batch.structures[0].atomic_numbers,
        )
        self.assertEqual(
            next(
                item
                for item in reparsed.datasets
                if item.semantic_role == "selective_dynamics"
            ).data.values.tolist(),
            next(
                item
                for item in batch.datasets
                if item.semantic_role == "selective_dynamics"
            ).data.values.tolist(),
        )

    def test_structure_view_data_projects_selective_axis_attributes(self):
        from ChemBlender.views.structure import _structure_view_data

        batch = parse_poscar(FIXTURES / "cscl-selective.vasp")
        selective = next(
            item
            for item in batch.datasets
            if item.semantic_role == "selective_dynamics"
        )

        data = _structure_view_data(
            batch.structures[0],
            selective_dynamics=selective,
        )

        self.assertEqual(data["cbq_selective_x"], (False, True))
        self.assertEqual(data["cbq_selective_y"], (False, False))
        self.assertEqual(data["cbq_selective_z"], (False, True))
        self.assertEqual(data["selective_atom_ids"], (0, 1))

    def test_selective_group_fatal_creation_cleans_partial_group(self):
        from ChemBlender.views import structure as structure_view

        fatal = GeneratorExit("node socket failed")
        group = SimpleNamespace(
            interface=SimpleNamespace(
                new_socket=Mock(side_effect=fatal),
            ),
            users=0,
        )
        node_groups = SimpleNamespace(
            get=Mock(return_value=None),
            new=Mock(return_value=group),
            remove=Mock(),
        )
        with patch.object(
            self.fake_bpy,
            "data",
            SimpleNamespace(node_groups=node_groups),
        ):
            with self.assertRaises(GeneratorExit) as raised:
                structure_view._ensure_selective_marker_group()

        self.assertIs(raised.exception, fatal)
        node_groups.remove.assert_called_once_with(group)

    def test_selective_marker_failure_cleans_object_mesh_and_group(self):
        from ChemBlender.views import structure as structure_view

        fatal = MemoryError("marker parenting failed")
        group = SimpleNamespace(users=0)
        mesh = SimpleNamespace(
            name="Marker",
            users=0,
            from_pydata=Mock(),
            update=Mock(),
        )

        class Modifier(dict):
            node_group = None

        modifier = Modifier()

        class Marker(dict):
            name = "Marker"
            modifiers = SimpleNamespace(new=Mock(return_value=modifier))
            show_in_front = False
            hide_render = False
            data = mesh

            @property
            def parent(self):
                return None

            @parent.setter
            def parent(self, _value):
                raise fatal

        marker = Marker()
        removed_objects = []
        removed_meshes = []
        removed_groups = []

        def remove_object(value, **_keywords):
            removed_objects.append(value)
            if modifier.node_group is not None:
                modifier.node_group.users = 0
            mesh.users = 0

        objects = SimpleNamespace(
            new=Mock(return_value=marker),
            remove=remove_object,
        )
        meshes = SimpleNamespace(
            new=Mock(return_value=mesh),
            remove=lambda value: removed_meshes.append(value),
        )
        node_groups = SimpleNamespace(
            get=Mock(return_value=None),
            remove=lambda value: removed_groups.append(value),
        )
        collection = SimpleNamespace(
            objects=SimpleNamespace(
                link=lambda _value: setattr(mesh, "users", 1),
            )
        )
        main = type(
            "Main",
            (dict,),
            {"name": "Structure"},
        )({"cb_structure_id": "structure-id"})
        with (
            patch.object(
                self.fake_bpy,
                "data",
                SimpleNamespace(
                    meshes=meshes,
                    objects=objects,
                    node_groups=node_groups,
                ),
            ),
            patch.object(
                structure_view,
                "_write_point_attributes",
                return_value=None,
            ),
            patch.object(
                structure_view,
                "_ensure_selective_marker_group",
                side_effect=lambda: (
                    setattr(group, "users", 1) or group
                ),
            ),
        ):
            with self.assertRaises(MemoryError) as raised:
                structure_view._selective_marker_object(
                    main,
                    collection,
                    {
                        "selective_atom_ids": (0,),
                        "coordinates": ((0.0, 0.0, 0.0),),
                    },
                )

        self.assertIs(raised.exception, fatal)
        self.assertEqual(removed_objects, [marker])
        self.assertEqual(removed_meshes, [mesh])
        self.assertEqual(removed_groups, [group])

    def test_structure_view_fatal_creation_removes_partial_main_object(self):
        from ChemBlender.views import structure as structure_view

        batch = parse_poscar(FIXTURES / "cscl-selective.vasp")
        structure, = batch.structures
        fatal = GeneratorExit("selective marker failed")
        mesh = SimpleNamespace(
            name="Structure",
            users=0,
            from_pydata=Mock(),
            update=Mock(),
        )

        class Objects:
            def __init__(self):
                self.values = {}

            def new(self, name, value):
                obj = type(
                    "Object",
                    (dict,),
                    {"name": name, "data": value, "modifiers": ()},
                )()
                self.values[name] = obj
                value.users = 1
                return obj

            def __contains__(self, name):
                return name in self.values

        objects = Objects()
        collection = SimpleNamespace(objects=SimpleNamespace(link=lambda _v: None))
        remove = Mock()
        with (
            patch.object(
                self.fake_bpy,
                "data",
                SimpleNamespace(
                    meshes=SimpleNamespace(new=Mock(return_value=mesh)),
                    objects=objects,
                ),
            ),
            patch.object(
                structure_view,
                "_write_point_attributes",
                return_value=None,
            ),
            patch.object(
                structure_view,
                "_write_edge_attributes",
                return_value=None,
            ),
            patch.object(
                structure_view,
                "_set_topology_metadata",
                return_value=None,
            ),
            patch.object(
                structure_view,
                "_selective_marker_object",
                side_effect=fatal,
            ),
            patch.object(
                structure_view,
                "remove_structure_view",
                remove,
            ),
        ):
            with self.assertRaises(GeneratorExit) as raised:
                structure_view.create_structure_view(
                    structure,
                    selective_dynamics=next(
                        value
                        for value in batch.datasets
                        if value.semantic_role == "selective_dynamics"
                    ),
                    collection=collection,
                )

        self.assertIs(raised.exception, fatal)
        remove.assert_called_once_with(objects.values["ChemBlender Structure"])


if __name__ == "__main__":
    unittest.main()
