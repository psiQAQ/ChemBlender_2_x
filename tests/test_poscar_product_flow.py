import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from chemblender_prepare.core.formats.poscar import parse_poscar


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "poscar"


class PoscarProductFlowTests(unittest.TestCase):
    """External preparation replaces the historical Blender raw-file modal UI."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "structure.cbq"

    def cli(self, *args, success=True):
        import io
        import json
        from contextlib import redirect_stdout
        from chemblender_prepare.cli import main
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main([str(value) for value in args] + ["--json"])
        result = json.loads(stream.getvalue())
        self.assertEqual(code, 0 if success else 1, result)
        return result

    def test_preview_summarizes_poscar_scientific_conventions(self):
        row = self.cli("inspect", FIXTURES / "velocities.CONTCAR")["metadata"]["poscar"]
        self.assertEqual(row["comment"], "velocity block")
        self.assertEqual(row["scale"], 1)
        self.assertEqual(row["cell_volume"], 27)
        self.assertEqual(row["cell_unit"], "angstrom")
        self.assertEqual(row["species"], ["Na", "Cl"])
        self.assertEqual(row["counts"], [1, 1])
        self.assertEqual(row["coordinate_mode"], "cartesian")
        self.assertTrue(row["selective_dynamics"])
        self.assertTrue(row["ion_velocities"])
        self.assertTrue(row["lattice_velocities"])
        self.assertFalse(row["requires_species_assignment"])
        self.assertFalse(self.output.exists())

    def test_preview_bounds_comment_without_truncating_provenance(self):
        from cbq_core.sidecar import open_project, close_project
        source = self.root / "long.POSCAR"
        comment = "C" * 60_000
        lines = (FIXTURES / "cscl-selective.vasp").read_text(encoding="utf-8").splitlines()
        source.write_text("\n".join((comment, *lines[1:])) + "\n", encoding="utf-8")
        row = self.cli("inspect", source)["metadata"]["poscar"]
        self.assertLessEqual(len(row["comment"]), 256)
        self.assertTrue(row["comment"].endswith("…"))
        self.cli("convert", source, "-o", self.output)
        project = open_project(self.output)
        try:
            provenance = next(value for value in project.provenance.values()
                              if value.producer == "ChemBlender POSCAR adapter")
            self.assertEqual(dict(provenance.parameters)["comment"], comment)
        finally:
            close_project(project)

    def test_vasp4_assignment_is_required_before_publication(self):
        source = FIXTURES / "vasp4-counts.POSCAR"
        row = self.cli("inspect", source)["metadata"]["poscar"]
        self.assertTrue(row["requires_species_assignment"])
        for params in ((), ("--param", "species=Na")):
            self.cli("convert", source, "-o", self.output, *params, success=False)
            self.assertFalse(self.output.exists())
        self.cli("convert", source, "-o", self.output, "--param", "species=Na,Cl")
        self.assertTrue((self.output / "manifest.json").is_file())

    def test_gui_subprocess_forwards_species_without_loading_blender(self):
        import time
        from chemblender_prepare.gui import CliProcess, command_arguments
        from cbq_core.sidecar import open_project, close_project
        args = command_arguments({"command": "convert", "sources": str(FIXTURES / "vasp4-counts.POSCAR"),
            "output": str(self.output), "reader": "poscar", "params": "species=Na,Cl"})
        job = CliProcess(args)
        try:
            deadline = time.monotonic() + 20
            result = None
            while result is None and time.monotonic() < deadline:
                result = job.poll()
                time.sleep(0.01)
            self.assertIsNotNone(result)
            self.assertEqual(result.status.value, "success", result)
            project = open_project(self.output)
            try:
                self.assertEqual(next(iter(project.structures.values())).atomic_numbers, (11, 11, 17))
            finally:
                close_project(project)
        finally:
            if job.process.poll() is None:
                job.cancel()
                job.process.wait(timeout=10)
            job.close()

    def test_cancel_marker_prevents_poscar_publication(self):
        cancel = self.root / "cancel"
        cancel.touch()
        result = self.cli("convert", FIXTURES / "vasp4-counts.POSCAR", "-o", self.output,
                          "--param", "species=Na,Cl", "--cancel-file", cancel, success=False)
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse(self.output.exists())

    def test_gui_progress_failure_waits_for_owned_process_before_cleanup(self):
        from chemblender_prepare.gui import PrepareWindow
        window = PrepareWindow.__new__(PrepareWindow)
        job = SimpleNamespace(poll=Mock(return_value=None), progress=Mock(side_effect=RuntimeError("progress failed")),
            process=SimpleNamespace(poll=Mock(return_value=None)), cancel=Mock(), close=Mock())
        window.job, window.closing = job, False
        window.status, window.bar, window.report, window.run_button, window.root = (Mock() for _ in range(5))
        window.poll()
        job.cancel.assert_called_once_with()
        job.close.assert_not_called()
        self.assertIs(window.job, job)
        window.root.after.assert_called_once_with(100, window.poll)
        job.process.poll.return_value = 1
        job.poll.side_effect = RuntimeError("CLI exited without result")
        window.poll()
        job.close.assert_called_once_with()
        self.assertIsNone(window.job)

    def test_multiple_assignments_append_and_preserve_existing_package(self):
        from cbq_core.sidecar import open_project, close_project
        source = FIXTURES / "vasp4-counts.POSCAR"
        self.cli("convert", source, "-o", self.output, "--param", "species=Na,Cl")
        original = {p.relative_to(self.output): p.read_bytes() for p in self.output.rglob("*") if p.is_file()}
        second = self.root / "second.cbq"
        self.cli("convert", source, "--project", self.output, "-o", second, "--param", "species=K,Br")
        project = open_project(second)
        try:
            self.assertEqual({s.atomic_numbers for s in project.structures.values()}, {(11, 11, 17), (19, 19, 35)})
        finally:
            close_project(project)
        self.assertEqual(original, {p.relative_to(self.output): p.read_bytes() for p in self.output.rglob("*") if p.is_file()})

    def test_export_selection_binds_properties_and_round_trips(self):
        from cbq_core.sidecar import open_project, close_project
        from chemblender_prepare.export_service import resolve_export_selection
        import numpy
        self.cli("convert", FIXTURES / "cscl-selective.vasp", "-o", self.output)
        project = open_project(self.output)
        try:
            structure = next(iter(project.structures.values()))
            selection = resolve_export_selection(project, structure.id)
            self.assertEqual(tuple(item.semantic_role for item in selection.properties), ("selective_dynamics",))
            destination = self.root / "POSCAR"
            self.cli("export", self.output, "-o", destination, "--entity", structure.id, "--format", "poscar", "--preview")
            self.assertFalse(destination.exists())
            self.cli("export", self.output, "-o", destination, "--entity", structure.id, "--format", "poscar")
            reparsed = parse_poscar(destination)
            self.assertEqual(reparsed.structures[0].atomic_numbers, structure.atomic_numbers)
            self.assertEqual(next(item for item in reparsed.datasets if item.semantic_role == "selective_dynamics").data.values.tolist(),
                             numpy.asarray(selection.properties[0].data.values).tolist())
        finally:
            close_project(project)


class PreparedPoscarViewTests(unittest.TestCase):
    """Display prepared attributes independently of the external import UI."""

    def setUp(self):
        self.fake_bpy = ModuleType("bpy")
        self.fake_bpy.data = SimpleNamespace()
        self.modules = patch.dict(sys.modules, {"bpy": self.fake_bpy})
        self.modules.start()
        self.addCleanup(self.modules.stop)

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
