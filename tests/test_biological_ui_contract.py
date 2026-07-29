import importlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from ChemBlender.core import QCProject
from ChemBlender.core.formats.pdb import parse_pdb
from ChemBlender.core.formats.pqr import parse_pqr
from ChemBlender.ui.project_browser.model import BrowserMode, build_browser_rows
from ChemBlender.views.structure import _structure_view_data
from ChemBlender.views import structure as structure_view


FIXTURES = Path(__file__).with_name("fixtures")


class BiologicalUIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.imported_module_names = (
            "ChemBlender.ui.biological",
            "ChemBlender.ui.properties",
            "ChemBlender.ui.session",
            "ChemBlender.dataset_view",
            "ChemBlender.trajectory_view",
        )
        cls.preexisting_modules = {
            name for name in cls.imported_module_names if name in sys.modules
        }

        class Operator:
            def report(self, *_args):
                pass

        fake_bpy = ModuleType("bpy")
        fake_bpy.types = SimpleNamespace(
            Operator=Operator,
            Object=object,
            PropertyGroup=object,
        )
        fake_props = ModuleType("bpy.props")
        for name in (
            "BoolProperty",
            "EnumProperty",
            "FloatProperty",
            "IntProperty",
            "PointerProperty",
            "StringProperty",
        ):
            setattr(fake_props, name, lambda **_keywords: None)
        cls.bpy_patch = patch.dict(
            sys.modules,
            {"bpy": fake_bpy, "bpy.props": fake_props},
        )
        cls.bpy_patch.start()
        cls.module = importlib.import_module("ChemBlender.ui.biological")

    @classmethod
    def tearDownClass(cls):
        cls.bpy_patch.stop()
        cls.module = None
        for name in cls.imported_module_names:
            if name not in cls.preexisting_modules:
                sys.modules.pop(name, None)

    def test_point_projection_preserves_categorical_mappings_and_properties(self):
        batch = parse_pdb(FIXTURES / "pdb" / "altloc.pdb")
        projection = self.module.biological_point_data(
            batch.structures[0],
            batch.biological_hierarchies[0],
            batch.datasets,
        )

        self.assertEqual(projection["cbq_chain_code"], (0, 0))
        self.assertEqual(projection["cbq_residue_code"], (0, 0))
        self.assertEqual(projection["cbq_residue_number"], (1, 1))
        self.assertEqual(projection["cbq_altloc_code"], (0, 1))
        self.assertEqual(projection["cbq_atom_name_code"], (0, 0))
        self.assertEqual(projection["cbq_record_kind_code"], (0, 0))
        self.assertEqual(projection["cbq_occupancy"], (0.6, 0.4))
        self.assertEqual(projection["cbq_b_factor"], (20.0, 21.0))
        self.assertEqual(projection["cbq_occupancy_valid"], (True, True))
        self.assertEqual(projection["cbq_partial_charge_valid"], (False, False))
        self.assertEqual(
            projection["categories"],
            {
                "cbq_altloc_code": ("A", "B"),
                "cbq_atom_name_code": ("CA",),
                "cbq_chain_code": ("A",),
                "cbq_record_kind_code": ("atom",),
                "cbq_residue_code": ("ALA 1",),
                "cbq_residue_name_code": ("ALA",),
            },
        )
        self.assertEqual(set(projection["category_hashes"]), set(projection["categories"]))
        self.assertTrue(
            all(
                len(value) == 64
                for value in projection["category_hashes"].values()
            )
        )

    def test_default_altloc_uses_highest_finite_occupancy_with_stable_tie_break(self):
        batch = parse_pdb(FIXTURES / "pdb" / "altloc.pdb")

        self.assertEqual(
            self.module.default_altloc_mask(
                batch.structures[0],
                batch.biological_hierarchies[0],
                batch.datasets,
            ),
            (True, False),
        )

    def test_chain_selection_uses_hierarchy_not_blender_rna(self):
        batch = parse_pqr(FIXTURES / "pqr" / "with-chain.pqr")

        self.assertEqual(
            self.module.biological_selection_indices(
                batch.structures[0],
                batch.biological_hierarchies[0],
                batch.datasets,
                chain_id="A",
            ),
            (0,),
        )

    def test_pqr_projection_preserves_charge_and_radius_as_numeric_properties(self):
        batch = parse_pqr(FIXTURES / "pqr" / "with-chain.pqr")
        projection = self.module.biological_point_data(
            batch.structures[0],
            batch.biological_hierarchies[0],
            batch.datasets,
        )

        self.assertEqual(projection["cbq_partial_charge"], (-0.3, -0.55))
        self.assertEqual(projection["cbq_pqr_radius"], (1.55, 1.4))
        self.assertEqual(projection["cbq_partial_charge_valid"], (True, True))
        self.assertEqual(projection["cbq_pqr_radius_valid"], (True, True))
        self.assertTrue(all(map(lambda value: value != value, projection["cbq_occupancy"])))
        self.assertEqual(projection["cbq_occupancy_valid"], (False, False))

    def test_structure_view_data_includes_biological_projection_and_default_filter(self):
        batch = parse_pdb(FIXTURES / "pdb" / "altloc.pdb")

        data = _structure_view_data(
            batch.structures[0],
            biological_hierarchy=batch.biological_hierarchies[0],
            atomic_properties=batch.datasets,
        )

        self.assertEqual(data["cbq_altloc_code"], (0, 1))
        self.assertEqual(data["cbq_selected"], (True, False))
        self.assertEqual(data["cbq_visible"], (True, False))
        self.assertIn("cbq_altloc_code", data["biological_categories"])
        self.assertEqual(len(data["biological_category_hashes"]["cbq_altloc_code"]), 64)

    def test_selection_predicates_compose_without_mutating_source_data(self):
        batch = parse_pqr(FIXTURES / "pqr" / "with-chain.pqr")
        structure = batch.structures[0]
        hierarchy = batch.biological_hierarchies[0]

        self.assertEqual(
            self.module.biological_selection_indices(
                structure,
                hierarchy,
                batch.datasets,
                residue_start=2,
                residue_end=2,
                residue_name="HOH",
                atom_name="O",
                property_role="partial_charge",
                comparison="less_equal",
                threshold=-0.4,
            ),
            (1,),
        )

    def test_biological_attributes_write_codes_masks_and_mapping_metadata(self):
        batch = parse_pdb(FIXTURES / "pdb" / "altloc.pdb")
        data = _structure_view_data(
            batch.structures[0],
            biological_hierarchy=batch.biological_hierarchies[0],
            atomic_properties=batch.datasets,
        )

        class View(dict):
            data = SimpleNamespace()

        view = View()
        writes = []
        with patch.object(
            structure_view,
            "_write_attribute",
            side_effect=lambda _mesh, name, data_type, field, values: writes.append(
                (name, data_type, field, tuple(values))
            ),
        ):
            structure_view._write_biological_attributes(view, data)

        written = {name: (data_type, values) for name, data_type, _field, values in writes}
        self.assertEqual(written["cbq_altloc_code"], ("INT", (0, 1)))
        self.assertEqual(
            written["cbq_altloc_code_valid"],
            ("BOOLEAN", (True, True)),
        )
        self.assertEqual(written["cbq_selected"], ("BOOLEAN", (True, False)))
        self.assertEqual(written["cbq_visible"], ("BOOLEAN", (True, False)))
        self.assertEqual(
            view["cb_biological_hierarchy_id"],
            str(batch.biological_hierarchies[0].id),
        )
        self.assertEqual(
            view["cb_biological_hierarchy_revision"],
            batch.biological_hierarchies[0].revision,
        )
        self.assertIn("cbq_altloc_code", view["cb_biological_categories"])
        self.assertIn("cbq_altloc_code", view["cb_biological_category_hashes"])

    def test_live_context_revalidates_entity_structure_hierarchy_and_mapping(self):
        batch = parse_pdb(FIXTURES / "pdb" / "altloc.pdb")
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        structure, hierarchy, properties, frame_set, topology = (
            self.module.resolve_biological_context(
                project,
                batch.biological_hierarchies[0].id,
            )
        )
        data = _structure_view_data(
            structure,
            biological_hierarchy=hierarchy,
            atomic_properties=properties,
        )

        class View(dict):
            data = SimpleNamespace(vertices=(None,) * len(structure.atomic_numbers))

        view = View(
            cb_structure_contract="structure_view_v1",
            cb_structure_id=str(structure.id),
            cb_structure_revision=structure.revision,
        )
        with patch.object(structure_view, "_write_attribute"):
            structure_view._write_biological_attributes(view, data)

        self.module.require_live_biological_view(
            view,
            structure,
            hierarchy,
            properties,
        )
        view["cb_biological_category_hashes"] = json.dumps(
            {"cbq_altloc_code": "0" * 64}
        )
        with self.assertRaisesRegex(ValueError, "mapping"):
            self.module.require_live_biological_view(
                view,
                structure,
                hierarchy,
                properties,
            )
        self.assertIsNone(frame_set)
        self.assertIsNone(topology)

    def test_biological_default_plan_is_size_and_topology_aware(self):
        batch = parse_pdb(FIXTURES / "pdb" / "conect.pdb")
        topology = batch.topologies[0]

        settings, reason = self.module.plan_biological_view(
            batch.structures[0],
            topology,
        )

        self.assertTrue(settings.attach_ball_and_stick)
        self.assertIn("selected topology", reason)
        with patch.object(self.module, "_BALL_STICK_ATOM_LIMIT", 1):
            settings, reason = self.module.plan_biological_view(
                batch.structures[0],
                topology,
            )
        self.assertFalse(settings.attach_ball_and_stick)
        self.assertIn("size-aware", reason)
        settings, reason = self.module.plan_biological_view(
            batch.structures[0],
            None,
        )
        self.assertFalse(settings.attach_ball_and_stick)
        self.assertIn("no selected topology", reason)

    def test_project_browser_has_one_hierarchy_group_with_chain_and_residue_rows(self):
        batch = parse_pdb(FIXTURES / "pdb" / "altloc.pdb")
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)

        rows = build_browser_rows(
            project,
            mode=BrowserMode.BY_DATA,
            session_id=project.id,
            browser_revision=1,
        )

        groups = [row for row in rows if row.id == "group:biological_hierarchies"]
        self.assertEqual(len(groups), 1)
        self.assertTrue(any(row.kind == "biological_chain" for row in rows))
        self.assertTrue(any(row.kind == "biological_residue" for row in rows))

    def test_selection_operator_uses_selected_entity_and_fails_closed_when_stale(self):
        batch = parse_pqr(FIXTURES / "pqr" / "with-chain.pqr")
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        structure = batch.structures[0]
        hierarchy = batch.biological_hierarchies[0]
        properties = tuple(batch.datasets)
        data = _structure_view_data(
            structure,
            biological_hierarchy=hierarchy,
            atomic_properties=properties,
        )

        class View(dict):
            name = "PQR biological view"
            data = SimpleNamespace(vertices=(None, None))

        view = View(
            cb_structure_contract="structure_view_v1",
            cb_structure_id=str(structure.id),
            cb_structure_revision=structure.revision,
        )
        with patch.object(structure_view, "_write_attribute"):
            structure_view._write_biological_attributes(view, data)
        session = SimpleNamespace(
            project=project,
            active_entity_id=hierarchy.id,
            active_view_object_name=view.name,
        )
        context = SimpleNamespace(
            active_object=view,
            scene=SimpleNamespace(objects={view.name: view}),
        )
        selected = []
        errors = []
        operation = self.module.CHEMBLENDER_OT_select_biological_atoms()
        operation.report = lambda _levels, message: errors.append(message)
        operation.selector = "chain"
        operation.chain_id = "A"
        with (
            patch.object(
                self.module,
                "get_scene_session",
                return_value=session,
            ),
            patch.object(
                self.module,
                "apply_atom_selection",
                side_effect=lambda _obj, indices, *, name: selected.append(
                    (tuple(indices), name)
                ),
            ),
        ):
            self.assertEqual(operation.execute(context), {"FINISHED"}, errors)
            view["cb_structure_revision"] = "stale"
            self.assertEqual(operation.execute(context), {"CANCELLED"})

        self.assertEqual(selected, [((0,), "chain:A")])

    def test_explicit_altloc_filter_updates_only_view_mask(self):
        batch = parse_pdb(FIXTURES / "pdb" / "altloc.pdb")

        self.assertEqual(
            self.module.altloc_filter_mask(
                batch.structures[0],
                batch.biological_hierarchies[0],
                batch.datasets,
                "B",
            ),
            (False, True),
        )
        self.assertEqual(
            self.module.altloc_filter_mask(
                batch.structures[0],
                batch.biological_hierarchies[0],
                batch.datasets,
                None,
            ),
            (True, False),
        )

    def test_model_operator_reuses_existing_trajectory_configuration(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "models.pdb"
            source.write_bytes(
                b"\n".join(
                    (
                        b"MODEL        1",
                        b"ATOM      1  N   GLY A   1      11.000  12.000  13.000  1.00 20.00           N",
                        b"ENDMDL",
                        b"MODEL        2",
                        b"ATOM      1  N   GLY A   1      14.000  15.000  16.000  1.00 21.00           N",
                        b"ENDMDL",
                        b"",
                    )
                )
            )
            batch = parse_pdb(source)
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        structure = batch.structures[0]
        hierarchy = batch.biological_hierarchies[0]
        frame_set = next(
            value
            for value in batch.datasets
            if type(value).__name__ == "FrameSet"
        )
        properties = tuple(
            value
            for value in batch.datasets
            if type(value).__name__ == "AtomicProperty"
        )
        data = _structure_view_data(
            structure,
            biological_hierarchy=hierarchy,
            atomic_properties=properties,
        )

        class View(dict):
            name = "PDB model view"
            data = SimpleNamespace(vertices=(None,))

        view = View(
            cb_structure_contract="structure_view_v1",
            cb_structure_id=str(structure.id),
            cb_structure_revision=structure.revision,
        )
        with patch.object(structure_view, "_write_attribute"):
            structure_view._write_biological_attributes(view, data)
        session = SimpleNamespace(
            project=project,
            active_entity_id=frame_set.id,
            active_view_object_name=view.name,
        )
        scene = SimpleNamespace(objects={view.name: view}, frame_end=1)
        context = SimpleNamespace(active_object=view, scene=scene)
        configured = []
        registered = []
        frame_handlers = []
        operation = self.module.CHEMBLENDER_OT_play_biological_models()
        operation.frame_start = 1
        operation.frame_step = 2
        with (
            patch.object(
                self.module.bpy,
                "app",
                SimpleNamespace(
                    handlers=SimpleNamespace(
                        frame_change_post=frame_handlers,
                    ),
                ),
                create=True,
            ),
            patch.object(
                self.module.trajectory_view,
                "register",
                side_effect=lambda: (
                    registered.append(True),
                    frame_handlers.append(
                        SimpleNamespace(
                            __module__=self.module.trajectory_view.__name__,
                            __name__="_frame_change_handler",
                        )
                    ),
                ),
            ),
            patch.object(
                self.module,
                "get_scene_session",
                return_value=session,
            ),
            patch.object(
                self.module.trajectory_view,
                "configure_trajectory_view",
                side_effect=lambda obj, frames, **keywords: configured.append(
                    (obj, frames, keywords)
                ),
            ),
        ):
            self.assertEqual(operation.execute(context), {"FINISHED"})

        self.assertEqual(registered, [True])
        self.assertEqual(len(frame_handlers), 1)
        self.assertEqual(
            configured,
            [
                (
                    view,
                    frame_set,
                    {"frame_start": 1, "frame_step": 2},
                )
            ],
        )
        self.assertEqual(scene.frame_end, 3)

    def test_project_browser_controls_use_selected_entity_and_expose_no_ribbon(self):
        batch = parse_pqr(FIXTURES / "pqr" / "with-chain.pqr")
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        events = []

        class Layout:
            def box(self):
                return self

            def label(self, **keywords):
                events.append(("label", keywords))

            def prop(self, owner, name, **keywords):
                events.append(("prop", owner, name, keywords))

            def operator(self, operator_id, **keywords):
                action = SimpleNamespace()
                events.append(("operator", operator_id, keywords, action))
                return action

        settings = SimpleNamespace(
            biological_chain="A",
            biological_residue_start=1,
            biological_residue_end=2,
            biological_residue_name="HOH",
            biological_atom_name="O",
            biological_altloc="",
            biological_property_role="partial_charge",
            biological_comparison="less_equal",
            biological_threshold=-0.4,
        )

        self.module.draw_biological_controls(
            Layout(),
            project,
            batch.biological_hierarchies[0].id,
            settings,
        )

        operator_ids = {
            event[1] for event in events if event[0] == "operator"
        }
        self.assertIn("chemblender.select_biological_atoms", operator_ids)
        self.assertIn("chemblender.create_biological_view", operator_ids)
        self.assertFalse(
            any(
                "ribbon" in str(event).casefold()
                or "cartoon" in str(event).casefold()
                for event in events
            )
        )

        pdb_batch = parse_pdb(FIXTURES / "pdb" / "altloc.pdb")
        self.assertEqual(
            self.module.biological_selection_indices(
                pdb_batch.structures[0],
                pdb_batch.biological_hierarchies[0],
                pdb_batch.datasets,
                altloc="B",
            ),
            (1,),
        )


if __name__ == "__main__":
    unittest.main()
