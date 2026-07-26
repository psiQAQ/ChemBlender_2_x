import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


MODULE = "ChemBlender.ui.workspace"
ROOT = Path(__file__).resolve().parents[1]


class _Area:
    def __init__(self, area_type, x, y, width, height, *, sidebar=False):
        self.type = area_type
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.spaces = SimpleNamespace(
            active=SimpleNamespace(show_region_ui=sidebar)
        )


def _compatible_areas():
    return [
        _Area("VIEW_3D", 300, 220, 800, 600),
        _Area("VIEW_3D", 0, 220, 300, 600, sidebar=True),
        _Area("PROPERTIES", 1100, 220, 300, 600),
        _Area("TEXT_EDITOR", 0, 0, 1400, 220),
    ]


class _Workspace:
    def __init__(self, name, areas=None):
        self.name = name
        self.screens = [SimpleNamespace(areas=areas or [])]


class _Workspaces(list):
    def get(self, name):
        return next((item for item in self if item.name == name), None)

    def remove(self, workspace):
        super().remove(workspace)


class _Screens(list):
    def remove(self, screen):
        super().remove(screen)


class _LibraryContext:
    def __init__(self, data, names, created_workspace, *, exit_failure=None):
        self.data = data
        self.names = names
        self.created_workspace = created_workspace
        self.exit_failure = exit_failure
        self.data_to = SimpleNamespace(workspaces=[])

    def __enter__(self):
        return SimpleNamespace(workspaces=self.names), self.data_to

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None and self.data_to.workspaces:
            self.data.workspaces.append(self.created_workspace)
            self.data.screens.extend(self.created_workspace.screens)
            self.data_to.workspaces[:] = [self.created_workspace]
            if self.exit_failure is not None:
                raise self.exit_failure
        return False


class WorkspaceHarness:
    def __init__(
        self,
        asset,
        *,
        names=("ChemBlender",),
        appended=None,
        exit_failure=None,
    ):
        self.original = _Workspace("Layout", _compatible_areas())
        self.workspaces = _Workspaces([self.original])
        self.screens = _Screens(self.original.screens[:])
        self.appended = appended or _Workspace(
            "ChemBlender", _compatible_areas()
        )
        self.window = SimpleNamespace(workspace=self.original)
        self.reports = []
        self.asset = asset
        self.names = names
        self.exit_failure = exit_failure
        self.batch_failure = None

        fake_bpy = ModuleType("bpy")
        fake_bpy.types = SimpleNamespace(
            Operator=object,
            WorkSpace=object,
            Context=object,
        )
        fake_bpy.data = SimpleNamespace(
            workspaces=self.workspaces,
            screens=self.screens,
            libraries=SimpleNamespace(load=self.load),
            batch_remove=self.batch_remove,
        )
        self.bpy = fake_bpy

    def batch_remove(self, *, ids):
        if self.batch_failure is not None:
            raise self.batch_failure
        for item in ids:
            if item in self.workspaces:
                self.workspaces.remove(item)
            if item in self.screens:
                self.screens.remove(item)

    def load(self, path, *, link):
        self.loaded = (path, link)
        return _LibraryContext(
            self.bpy.data,
            self.names,
            self.appended,
            exit_failure=self.exit_failure,
        )

    def module(self):
        sys.modules.pop(MODULE, None)
        with patch.dict(sys.modules, {"bpy": self.bpy}):
            return importlib.import_module(MODULE)

    def operator(self, module):
        operator = module.CHEMBLENDER_OT_open_workspace()
        operator.report = lambda kinds, message: self.reports.append(
            (set(kinds), message)
        )
        return operator


class WorkspaceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.asset = Path(self.temp.name) / "Chem_Workspace.blend"
        self.asset.write_bytes(b"BLENDER")

    def tearDown(self):
        sys.modules.pop(MODULE, None)
        self.temp.cleanup()

    def test_000_workspace_module_and_operator_exist(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()

        self.assertEqual(module.WORKSPACE_NAME, "ChemBlender")
        self.assertEqual(
            module.CHEMBLENDER_OT_open_workspace.bl_idname,
            "chemblender.open_workspace",
        )

    def test_asset_path_is_package_relative_and_exact(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()

        expected = (
            Path(module.os.path.abspath(module.__file__)).parents[1]
            / "assets"
            / "Chem_Workspace.blend"
        )
        self.assertEqual(module.workspace_asset_path(), expected)

    def test_asset_path_keeps_lexical_package_path_before_link_check(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()
        lexical_file = (
            Path(self.temp.name)
            / "package-junction"
            / "ChemBlender"
            / "ui"
            / "workspace.py"
        )
        resolved_file = (
            Path(self.temp.name)
            / "real-package"
            / "ChemBlender"
            / "ui"
            / "workspace.py"
        )
        lexical_package = lexical_file.parents[1]

        with (
            patch.object(module, "__file__", str(lexical_file)),
            patch.object(
                Path,
                "resolve",
                return_value=resolved_file,
            ) as resolve,
            patch.object(
                module.os.path,
                "isjunction",
                side_effect=lambda candidate: (
                    Path(candidate) == lexical_package
                ),
            ),
        ):
            path = module.workspace_asset_path()

            self.assertEqual(
                path,
                lexical_package / "assets" / "Chem_Workspace.blend",
            )
            resolve.assert_not_called()
            self.assertTrue(module._is_link_like(path))

    def test_bundled_asset_has_a_blender_or_zstd_header(self):
        asset = ROOT / "ChemBlender/assets/Chem_Workspace.blend"

        self.assertTrue(asset.is_file())
        self.assertGreater(asset.stat().st_size, 32)
        self.assertIn(
            asset.read_bytes()[:4],
            (b"BLEN", bytes.fromhex("28b52ffd")),
        )

    def test_compatibility_requires_layout_and_left_sidebar(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()

        self.assertTrue(
            module.workspace_is_compatible(
                _Workspace("ChemBlender", _compatible_areas())
            )
        )
        without_sidebar = _compatible_areas()
        without_sidebar[1].spaces.active.show_region_ui = False
        self.assertFalse(
            module.workspace_is_compatible(
                _Workspace("ChemBlender", without_sidebar)
            )
        )
        wrong_positions = _compatible_areas()
        wrong_positions[1].x = 900
        self.assertFalse(
            module.workspace_is_compatible(
                _Workspace("ChemBlender", wrong_positions)
            )
        )
        wrong_positions = _compatible_areas()
        wrong_positions[2].x = 10
        self.assertFalse(
            module.workspace_is_compatible(
                _Workspace("ChemBlender", wrong_positions)
            )
        )
        wrong_positions = _compatible_areas()
        wrong_positions[3].y = 500
        self.assertFalse(
            module.workspace_is_compatible(
                _Workspace("ChemBlender", wrong_positions)
            )
        )

    def test_existing_compatible_workspace_is_reused_without_loading(self):
        harness = WorkspaceHarness(self.asset)
        existing = _Workspace("ChemBlender", _compatible_areas())
        harness.workspaces.append(existing)
        module = harness.module()
        operator = harness.operator(module)

        with patch.object(module, "workspace_asset_path", return_value=self.asset):
            result = operator.execute(SimpleNamespace(window=harness.window))

        self.assertEqual(result, {"FINISHED"})
        self.assertIs(harness.window.workspace, existing)
        self.assertEqual(len(harness.workspaces), 2)
        self.assertFalse(hasattr(harness, "loaded"))

    def test_existing_incompatible_workspace_fails_closed(self):
        harness = WorkspaceHarness(self.asset)
        foreign = _Workspace("ChemBlender", [_Area("VIEW_3D", 0, 0, 1, 1)])
        harness.workspaces.append(foreign)
        module = harness.module()
        operator = harness.operator(module)

        with patch.object(module, "workspace_asset_path", return_value=self.asset):
            result = operator.execute(SimpleNamespace(window=harness.window))

        self.assertEqual(result, {"CANCELLED"})
        self.assertIs(harness.window.workspace, harness.original)
        self.assertIn(foreign, harness.workspaces)
        self.assertTrue(any("incompatible" in message for _, message in harness.reports))

    def test_no_window_and_missing_asset_fail_without_loading(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()
        operator = harness.operator(module)

        self.assertEqual(
            operator.execute(SimpleNamespace(window=None)),
            {"CANCELLED"},
        )
        missing = self.asset.with_name("missing.blend")
        with patch.object(module, "workspace_asset_path", return_value=missing):
            self.assertEqual(
                operator.execute(SimpleNamespace(window=harness.window)),
                {"CANCELLED"},
            )
        self.assertIs(harness.window.workspace, harness.original)
        self.assertFalse(hasattr(harness, "loaded"))

    def test_process_control_exceptions_are_not_swallowed(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()
        operator = harness.operator(module)

        with (
            patch.object(
                module,
                "_retry_pending_rollback",
                side_effect=KeyboardInterrupt,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            operator.execute(SimpleNamespace(window=harness.window))

    def test_missing_name_and_incompatible_append_are_rolled_back(self):
        for names, appended in (
            (("Other",), _Workspace("ChemBlender", _compatible_areas())),
            (("ChemBlender",), _Workspace("ChemBlender", [])),
        ):
            with self.subTest(names=names):
                harness = WorkspaceHarness(
                    self.asset,
                    names=names,
                    appended=appended,
                )
                module = harness.module()
                operator = harness.operator(module)
                with patch.object(
                    module, "workspace_asset_path", return_value=self.asset
                ):
                    result = operator.execute(
                        SimpleNamespace(window=harness.window)
                    )
                self.assertEqual(result, {"CANCELLED"})
                self.assertEqual(harness.workspaces, [harness.original])
                self.assertEqual(harness.screens, harness.original.screens)
                self.assertIs(harness.window.workspace, harness.original)

    def test_switch_failure_restores_original_and_removes_only_new_data(self):
        harness = WorkspaceHarness(self.asset)
        foreign_screen = SimpleNamespace(areas=[])
        harness.screens.append(foreign_screen)

        class Window:
            def __init__(self, original):
                self._workspace = original

            @property
            def workspace(self):
                return self._workspace

            @workspace.setter
            def workspace(self, value):
                if value.name == "ChemBlender":
                    self._workspace = value
                    raise RuntimeError("switch failed")
                self._workspace = value

        window = Window(harness.original)
        module = harness.module()
        operator = harness.operator(module)
        with patch.object(module, "workspace_asset_path", return_value=self.asset):
            result = operator.execute(SimpleNamespace(window=window))

        self.assertEqual(result, {"CANCELLED"})
        self.assertIs(window.workspace, harness.original)
        self.assertEqual(harness.workspaces, [harness.original])
        self.assertIn(foreign_screen, harness.screens)
        self.assertNotIn(harness.appended.screens[0], harness.screens)

    def test_switch_and_restore_failure_reports_incomplete_rollback(self):
        harness = WorkspaceHarness(self.asset)
        existing = _Workspace("ChemBlender", _compatible_areas())
        harness.workspaces.append(existing)

        class Window:
            def __init__(self, original):
                self._workspace = original
                self.fail = True

            @property
            def workspace(self):
                return self._workspace

            @workspace.setter
            def workspace(self, value):
                if not self.fail:
                    self._workspace = value
                    return
                if value.name == "ChemBlender":
                    self._workspace = value
                raise RuntimeError("assignment failed")

        window = Window(harness.original)
        module = harness.module()
        operator = harness.operator(module)
        with patch.object(module, "workspace_asset_path", return_value=self.asset):
            result = operator.execute(SimpleNamespace(window=window))

        self.assertEqual(result, {"CANCELLED"})
        self.assertIs(window.workspace, existing)
        self.assertTrue(
            any("rollback failed" in message for _, message in harness.reports)
        )
        self.assertEqual(
            module._pending_rollback,
            (window, harness.original, existing, (), ()),
        )

        window.fail = False
        module._retry_pending_rollback(window)

        self.assertIs(window.workspace, harness.original)
        self.assertIn(existing, harness.workspaces)
        self.assertIsNone(module._pending_rollback)

    def test_cleanup_failure_retains_exact_owned_ids_for_retry(self):
        harness = WorkspaceHarness(self.asset, appended=_Workspace(
            "ChemBlender", []
        ))
        module = harness.module()
        operator = harness.operator(module)
        harness.batch_failure = OSError("locked datablock")
        with patch.object(module, "workspace_asset_path", return_value=self.asset):
            result = operator.execute(SimpleNamespace(window=harness.window))

        self.assertEqual(result, {"CANCELLED"})
        self.assertIn(harness.appended, harness.workspaces)
        self.assertEqual(
            module._pending_rollback,
            (
                harness.window,
                harness.original,
                harness.appended,
                (harness.appended,),
                tuple(harness.appended.screens),
            ),
        )
        foreign = _Workspace("Foreign", [])
        foreign_screen = SimpleNamespace(areas=[])
        harness.workspaces.append(foreign)
        harness.screens.append(foreign_screen)
        harness.batch_failure = None

        module._retry_pending_rollback(harness.window)

        self.assertNotIn(harness.appended, harness.workspaces)
        self.assertFalse(
            any(item is harness.appended.screens[0] for item in harness.screens)
        )
        self.assertIn(foreign, harness.workspaces)
        self.assertTrue(any(item is foreign_screen for item in harness.screens))
        self.assertIsNone(module._pending_rollback)

    def test_pending_rollback_restores_original_before_cleanup_retry(self):
        harness = WorkspaceHarness(self.asset)

        class Window:
            def __init__(self, original):
                self._workspace = original
                self.fail_restore = True

            @property
            def workspace(self):
                return self._workspace

            @workspace.setter
            def workspace(self, value):
                if value.name == "ChemBlender":
                    self._workspace = value
                    raise RuntimeError("switch failed after assignment")
                if self.fail_restore:
                    raise RuntimeError("restore failed")
                self._workspace = value

        window = Window(harness.original)
        module = harness.module()
        operator = harness.operator(module)
        with patch.object(module, "workspace_asset_path", return_value=self.asset):
            first = operator.execute(SimpleNamespace(window=window))

        self.assertEqual(first, {"CANCELLED"})
        self.assertIs(window.workspace, harness.appended)
        self.assertIs(module._pending_rollback[0], window)
        self.assertIs(module._pending_rollback[1], harness.original)

        window.fail_restore = False
        missing = self.asset.with_name("missing.blend")
        with patch.object(module, "workspace_asset_path", return_value=missing):
            second = operator.execute(SimpleNamespace(window=window))

        self.assertEqual(second, {"CANCELLED"})
        self.assertIs(window.workspace, harness.original)
        self.assertNotIn(harness.appended, harness.workspaces)
        self.assertIsNone(module._pending_rollback)

    def test_pending_rollback_preserves_owned_data_if_original_disappears(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()
        module._pending_rollback = (
            harness.window,
            harness.original,
            harness.appended,
            (harness.appended,),
            tuple(harness.appended.screens),
        )
        harness.workspaces.append(harness.appended)
        harness.screens.extend(harness.appended.screens)
        harness.workspaces.remove(harness.original)
        harness.window.workspace = harness.appended

        with self.assertRaisesRegex(
            RuntimeError,
            "original workspace is no longer available",
        ):
            module._retry_pending_rollback(harness.window)

        self.assertIn(harness.appended, harness.workspaces)
        self.assertIsNotNone(module._pending_rollback)

    def test_foreign_window_execute_does_not_consume_owner_rollback(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()
        owner = harness.window
        foreign = SimpleNamespace(workspace=harness.original)
        owner.workspace = harness.appended
        harness.workspaces.append(harness.appended)
        harness.screens.extend(harness.appended.screens)
        pending = (
            owner,
            harness.original,
            harness.appended,
            (harness.appended,),
            tuple(harness.appended.screens),
        )
        module._pending_rollback = pending
        operator = harness.operator(module)

        result = operator.execute(SimpleNamespace(window=foreign))

        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(module._pending_rollback, pending)
        self.assertIs(owner.workspace, harness.appended)
        self.assertIs(foreign.workspace, harness.original)
        self.assertIn(harness.appended, harness.workspaces)
        self.assertTrue(
            any(
                "belongs to another window" in message
                for _, message in harness.reports
            )
        )

    def test_foreign_window_unregister_does_not_consume_owner_rollback(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()
        owner = harness.window
        foreign = SimpleNamespace(workspace=harness.original)
        owner.workspace = harness.appended
        harness.workspaces.append(harness.appended)
        harness.screens.extend(harness.appended.screens)
        pending = (
            owner,
            harness.original,
            harness.appended,
            (harness.appended,),
            tuple(harness.appended.screens),
        )
        module._pending_rollback = pending
        module.bpy.context = SimpleNamespace(
            window=foreign,
            window_manager=SimpleNamespace(windows=(owner, foreign)),
        )

        module.unregister()

        self.assertEqual(module._pending_rollback, pending)
        self.assertIs(owner.workspace, harness.appended)
        self.assertIn(harness.appended, harness.workspaces)

    def test_pending_rollback_fails_safe_if_owner_window_disappears(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()
        owner = harness.window
        foreign = SimpleNamespace(workspace=harness.original)
        owner.workspace = harness.appended
        harness.workspaces.append(harness.appended)
        harness.screens.extend(harness.appended.screens)
        pending = (
            owner,
            harness.original,
            harness.appended,
            (harness.appended,),
            tuple(harness.appended.screens),
        )
        module._pending_rollback = pending
        module.bpy.context = SimpleNamespace(
            window=foreign,
            window_manager=SimpleNamespace(windows=(foreign,)),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "owner window is no longer available",
        ):
            module._retry_pending_rollback(owner)

        self.assertEqual(module._pending_rollback, pending)
        self.assertIn(harness.appended, harness.workspaces)

    def test_pending_rollback_preserves_workspace_used_by_foreign_window(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()
        owner = harness.window
        foreign = SimpleNamespace(workspace=harness.appended)
        owner.workspace = harness.appended
        harness.workspaces.append(harness.appended)
        harness.screens.extend(harness.appended.screens)
        pending = (
            owner,
            harness.original,
            harness.appended,
            (harness.appended,),
            tuple(harness.appended.screens),
        )
        module._pending_rollback = pending
        module.bpy.context = SimpleNamespace(
            window=owner,
            window_manager=SimpleNamespace(windows=(owner, foreign)),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "owned workspace is in use by another window",
        ):
            module._retry_pending_rollback(owner)

        self.assertIs(owner.workspace, harness.original)
        self.assertIs(foreign.workspace, harness.appended)
        self.assertEqual(module._pending_rollback, pending)
        self.assertIn(harness.appended, harness.workspaces)

    def test_pending_rollback_matches_same_rna_window_pointer(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()

        class Window:
            def __init__(self, workspace, pointer):
                self.workspace = workspace
                self._pointer = pointer

            def as_pointer(self):
                return self._pointer

        owner = Window(harness.appended, 1234)
        live_alias = Window(harness.appended, 1234)
        harness.workspaces.append(harness.appended)
        harness.screens.extend(harness.appended.screens)
        module._pending_rollback = (
            owner,
            harness.original,
            harness.appended,
            (harness.appended,),
            tuple(harness.appended.screens),
        )
        module.bpy.context = SimpleNamespace(
            window=live_alias,
            window_manager=SimpleNamespace(windows=(live_alias,)),
        )

        self.assertTrue(module._retry_pending_rollback(live_alias))

        self.assertIs(owner.workspace, harness.original)
        self.assertNotIn(harness.appended, harness.workspaces)
        self.assertIsNone(module._pending_rollback)

    def test_partial_append_failure_rolls_back_only_new_data(self):
        harness = WorkspaceHarness(
            self.asset,
            exit_failure=OSError("partial append failure"),
        )
        foreign_screen = SimpleNamespace(areas=[])
        harness.screens.append(foreign_screen)
        module = harness.module()
        operator = harness.operator(module)
        with patch.object(module, "workspace_asset_path", return_value=self.asset):
            result = operator.execute(SimpleNamespace(window=harness.window))

        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(harness.workspaces, [harness.original])
        self.assertIn(foreign_screen, harness.screens)
        self.assertNotIn(harness.appended.screens[0], harness.screens)
        self.assertIs(harness.window.workspace, harness.original)

    def test_corrupt_library_failure_preserves_current_workspace(self):
        harness = WorkspaceHarness(self.asset)
        harness.bpy.data.libraries.load = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("corrupt")
        )
        module = harness.module()
        operator = harness.operator(module)
        with patch.object(module, "workspace_asset_path", return_value=self.asset):
            result = operator.execute(SimpleNamespace(window=harness.window))

        self.assertEqual(result, {"CANCELLED"})
        self.assertIs(harness.window.workspace, harness.original)
        self.assertEqual(harness.workspaces, [harness.original])

    def test_link_like_asset_is_rejected(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()
        operator = harness.operator(module)
        with (
            patch.object(
                module, "workspace_asset_path", return_value=self.asset
            ),
            patch.object(module, "_is_link_like", return_value=True),
        ):
            result = operator.execute(SimpleNamespace(window=harness.window))

        self.assertEqual(result, {"CANCELLED"})
        self.assertFalse(hasattr(harness, "loaded"))

    def test_package_directory_link_like_is_rejected_without_a_real_link(self):
        harness = WorkspaceHarness(self.asset)
        module = harness.module()
        path = module.workspace_asset_path()

        with patch.object(
            module.os.path,
            "isjunction",
            side_effect=lambda candidate: Path(candidate) == path.parent.parent,
        ):
            self.assertTrue(module._is_link_like(path))


if __name__ == "__main__":
    unittest.main()
