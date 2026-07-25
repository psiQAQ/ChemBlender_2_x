import array
import importlib
import importlib.util
import json
import math
import sys
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import UUID, uuid4
from zipfile import ZipFile

import bpy


READER_API_HANDLE_KEY = "chemblender.reader_api.v0"
OPTIONAL_STACK_PREFIXES = (
    "ase",
    "cclib",
    "gbasis",
    "gemmi",
    "iodata",
    "phonopy",
    "pymatgen",
    "pyprocar",
    "qcengine",
    "pyscf",
    "scipy",
)


def assert_package_contents(package):
    required = {
        "blender_manifest.toml",
        "LICENSE",
        "Chem_Nodes.blend",
        "Chem_Nodes_En.blend",
        "assets/Chem_Workspace.blend",
        "wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl",
    }
    forbidden_prefixes = ("scripts/", "tests/", "worker/", "__pycache__/")

    with ZipFile(package) as archive:
        names = {entry.filename.replace("\\", "/") for entry in archive.infolist()}

    assert required <= names, required - names
    assert not any(name.startswith(forbidden_prefixes) for name in names)
    assert not any(name.endswith(".zip") for name in names)
    assert [name for name in names if name.endswith(".whl")] == [
        "wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl"
    ]


def relative_name(name, package_root):
    if name == package_root:
        return "."
    prefix = package_root + "."
    return "." + name[len(prefix) :] if name.startswith(prefix) else name


def owned_handlers(package_root):
    entries = []
    for owner_name in dir(bpy.app.handlers):
        callbacks = getattr(bpy.app.handlers, owner_name)
        if not isinstance(callbacks, list):
            continue
        for callback in callbacks:
            module_name = getattr(callback, "__module__", "")
            if module_name.startswith(package_root + "."):
                entries.append(
                    {
                        "owner": owner_name,
                        "module": relative_name(module_name, package_root),
                        "name": callback.__name__,
                    }
                )
    return sorted(entries, key=lambda item: tuple(item.values()))


def owned_menu_callbacks(package_root):
    entries = []
    for owner_name in dir(bpy.types):
        owner = getattr(bpy.types, owner_name)
        if not isinstance(owner, type) or not issubclass(owner, bpy.types.Menu):
            continue
        draw = getattr(owner, "draw", None)
        for callback in getattr(draw, "_draw_funcs", ()):
            module_name = getattr(callback, "__module__", "")
            if module_name.startswith(package_root + "."):
                entries.append(
                    {
                        "owner": owner_name,
                        "module": relative_name(module_name, package_root),
                        "name": callback.__name__,
                    }
                )
    return sorted(entries, key=lambda item: tuple(item.values()))


def owned_registration_classes(module_key):
    registration = importlib.import_module(
        f"{module_key}.runtime.registration"
    )
    extension = importlib.import_module(f"{module_key}.extension")
    file_handlers = importlib.import_module(f"{module_key}.ui.file_handlers")
    return tuple(
        dict.fromkeys(
            (
                *registration._registered_classes,
                *(menu_type for menu_type, _ in extension.cat_list),
                *file_handlers._REGISTERED_CLASSES,
            )
        )
    )


def registration_inventory(module_key):
    registration = importlib.import_module(
        f"{module_key}.runtime.registration"
    )
    auto_load = importlib.import_module(f"{module_key}.auto_load")
    classes = owned_registration_classes(module_key)
    base_types = {
        *auto_load.get_register_base_types(),
        bpy.types.FileHandler,
    }
    registered_classes = []
    for cls in classes:
        bases = sorted(
            base.__name__ for base in base_types if issubclass(cls, base)
        )
        registered_classes.append(
            {
                "module": relative_name(cls.__module__, module_key),
                "name": cls.__name__,
                "id": getattr(cls, "bl_idname", None) or None,
                "base": bases[0],
            }
        )
    module_callbacks = []
    for name in registration.REGISTER_MODULE_NAMES:
        module = importlib.import_module(name, module_key)
        has_register = callable(getattr(module, "register", None))
        has_unregister = callable(getattr(module, "unregister", None))
        if has_register or has_unregister:
            module_callbacks.append(
                {
                    "module": name,
                    "register": has_register,
                    "unregister": has_unregister,
                }
            )
    return {
        "registered_classes": sorted(
            registered_classes,
            key=lambda item: (
                item["module"],
                item["name"],
                item["id"] or "",
                item["base"],
            ),
        ),
        "module_callbacks": module_callbacks,
        "handlers": owned_handlers(module_key),
        "menu_callbacks": owned_menu_callbacks(module_key),
    }


def assert_registration_isolation(module_key, before_install_modules):
    registration = importlib.import_module(
        f"{module_key}.runtime.registration"
    )
    assert tuple(
        name
        for name in registration.REGISTER_MODULE_NAMES
        if f"{module_key}{name}" in sys.modules
    ) == registration.REGISTER_MODULE_NAMES
    assert f"{module_key}.ui.session" in sys.modules
    assert f"{module_key}.ui.properties" in sys.modules
    assert f"{module_key}.ui.quick_import" in sys.modules
    assert f"{module_key}.ui.import_preview" in sys.modules
    assert f"{module_key}.ui.project_browser.panel" in sys.modules
    assert f"{module_key}.ui.file_handlers" in sys.modules
    assert f"{module_key}.ui.workspace" in sys.modules
    newly_loaded = set(sys.modules) - before_install_modules
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in newly_loaded
        for prefix in OPTIONAL_STACK_PREFIXES
    ), sorted(
        name
        for name in newly_loaded
        if any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in OPTIONAL_STACK_PREFIXES
        )
    )


def assert_enabled(module_key, before_install_modules):
    assert module_key in bpy.context.preferences.addons
    assert f"{module_key}.trajectory_view" in sys.modules
    assert_registration_isolation(module_key, before_install_modules)
    assert sum(
        getattr(handler, "__module__", None) == f"{module_key}.trajectory_view"
        for handler in bpy.app.handlers.frame_change_post
    ) == 1
    for callbacks, name in (
        (bpy.app.handlers.load_post, "_load_post_handler"),
        (bpy.app.handlers.save_pre, "_save_pre_handler"),
    ):
        matching = [
            handler
            for handler in callbacks
            if getattr(handler, "__module__", None) == f"{module_key}.ui.session"
            and handler.__name__ == name
        ]
        assert len(matching) == 1
    assert hasattr(bpy.types.Object, "cif_original")
    assert hasattr(bpy.types.Object, "cif_current")
    assert hasattr(bpy.types.Scene, "my_tool")
    assert hasattr(bpy.types.Scene, "chemblender_quick_import")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_quick_import")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_open_workspace")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_confirm_import")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_cancel_import")
    assert_file_handlers(module_key)
    properties = importlib.import_module(f"{module_key}.ui.properties")
    property_identity = properties._scene_property_identity()
    assert property_identity is not None
    assert property_identity[0] == "rna"
    properties.register()
    assert properties._same_scene_property(
        properties._scene_property_identity(),
        property_identity,
    )
    assert sum(
        getattr(handler, "__module__", None) == f"{module_key}.ui.properties"
        for handler in bpy.app.handlers.load_pre
    ) == 1
    assert_reader_api_handle(module_key)


def assert_disabled(module_key, owned_classes):
    assert module_key not in bpy.context.preferences.addons
    assert not hasattr(bpy.types.Object, "cif_original")
    assert not hasattr(bpy.types.Object, "cif_current")
    assert not hasattr(bpy.types.Scene, "my_tool")
    assert not hasattr(bpy.types.Scene, "chemblender_quick_import")
    assert READER_API_HANDLE_KEY not in bpy.app.driver_namespace
    assert not any(
        getattr(handler, "__module__", None) == f"{module_key}.trajectory_view"
        for handler in bpy.app.handlers.frame_change_post
    )
    assert not any(
        getattr(handler, "__module__", None) == f"{module_key}.ui.session"
        for callbacks in (bpy.app.handlers.load_post, bpy.app.handlers.save_pre)
        for handler in callbacks
    )
    assert not any(
        getattr(handler, "__module__", None) == f"{module_key}.ui.properties"
        for handler in bpy.app.handlers.load_pre
    )
    assert not owned_menu_callbacks(module_key)
    assert all(
        not getattr(cls, "is_registered", False)
        for cls in owned_classes
    )


def assert_reader_api_handle(module_key):
    handle = bpy.app.driver_namespace[READER_API_HANDLE_KEY]
    assert handle.api_version == "0.1"
    assert handle.module_name == f"{module_key}.reader_api"
    assert importlib.import_module(handle.module_name).__name__ == handle.module_name
    assert callable(handle.register_callback)
    assert callable(handle.unregister_callback)
    assert (
        sum(
            key == READER_API_HANDLE_KEY
            for key in bpy.app.driver_namespace
        )
        == 1
    )


def assert_file_handlers(module_key):
    file_handlers = importlib.import_module(
        f"{module_key}.ui.file_handlers"
    )
    bridge = importlib.import_module(
        f"{module_key}.runtime.reader_api_bridge"
    )
    expected_extensions = ";".join(
        sorted(
            {
                extension.lower()
                for descriptor in bridge.get_reader_plugin_registry().descriptors
                if descriptor.plugin_id == "chemblender.builtin"
                and descriptor.availability.available
                for extension in descriptor.extensions
            }
        )
    )
    window, sidebar = file_handlers.FILE_HANDLER_CLASSES
    assert len(file_handlers.FILE_HANDLER_CLASSES) == 2
    for cls in file_handlers.FILE_HANDLER_CLASSES:
        assert cls.is_registered
        assert getattr(bpy.types, cls.__name__) is cls
        assert cls.bl_import_operator == "chemblender.quick_import"
        assert cls.bl_file_extensions == expected_extensions
    assert window.poll_drop(
        SimpleNamespace(
            area=SimpleNamespace(type="VIEW_3D"),
            region=SimpleNamespace(type="WINDOW"),
        )
    ) is True
    assert sidebar.poll_drop(
        SimpleNamespace(
            area=SimpleNamespace(type="VIEW_3D"),
            region=SimpleNamespace(type="UI"),
        )
    ) is True
    for cls in file_handlers.FILE_HANDLER_CLASSES:
        assert cls.poll_drop(
            SimpleNamespace(
                area=SimpleNamespace(type="FILE_BROWSER"),
                region=SimpleNamespace(type="WINDOW"),
            )
        ) is False
        assert cls.poll_drop(
            SimpleNamespace(
                area=SimpleNamespace(type="OUTLINER"),
                region=SimpleNamespace(type="WINDOW"),
            )
        ) is False


def assert_project_session_manager(module_key):
    ui = importlib.import_module(f"{module_key}.ui.session")
    scene = bpy.context.scene
    session = ui.new_scene_session(scene)
    session.mark_dirty("import")
    with TemporaryDirectory() as directory:
        blend = Path(directory) / "session-manager.blend"
        result = bpy.ops.wm.save_as_mainfile(
            filepath=str(blend),
            check_existing=False,
        )
        assert result == {"FINISHED"}, result
        assert session.dirty
        result = bpy.ops.wm.save_mainfile()
        assert result == {"FINISHED"}, result
        assert not session.dirty
        assert (blend.with_suffix(".cbq")).is_dir()

        reader_handle = bpy.app.driver_namespace[READER_API_HANDLE_KEY]
        reader_api = importlib.import_module(f"{module_key}.reader_api")
        model_identities = (
            reader_api.PublicImportBatch,
            reader_api.PublicReaderDescriptor,
            reader_api.ReaderPluginManifest,
        )
        registry = importlib.import_module(
            f"{module_key}.runtime.reader_api_bridge"
        ).get_reader_plugin_registry()
        result = bpy.ops.wm.open_mainfile(filepath=str(blend))
        assert result == {"FINISHED"}, result
        assert bpy.app.driver_namespace[READER_API_HANDLE_KEY] is reader_handle
        bridge = importlib.import_module(
            f"{module_key}.runtime.reader_api_bridge"
        )
        assert bridge.get_reader_plugin_registry() is registry
        current_reader_api = importlib.import_module(f"{module_key}.reader_api")
        assert (
            current_reader_api.PublicImportBatch,
            current_reader_api.PublicReaderDescriptor,
            current_reader_api.ReaderPluginManifest,
        ) == model_identities
        ui = importlib.import_module(f"{module_key}.ui.session")
        restored = ui.get_scene_session(bpy.context.scene)
        assert ui.get_scene_session_status(bpy.context.scene)[0] == "connected"
        assert restored.sidecar_path == blend.with_suffix(".cbq")
        properties = importlib.import_module(f"{module_key}.ui.properties")
        assert properties.get_quick_import_state(restored).browser_revision == 1

        restored.mark_dirty("edit")
        verified_sidecar = restored.sidecar_path
        original_save = ui.save_project_session
        try:
            def fail_save(**_kwargs):
                raise RuntimeError("simulated sidecar failure")

            ui.save_project_session = fail_save
            ui._save_pre_handler(None)
        finally:
            ui.save_project_session = original_save
        assert restored.dirty
        assert restored.sidecar_path == verified_sidecar
        assert ui.get_scene_session_status(bpy.context.scene) == (
            "error",
            "simulated sidecar failure",
        )

        temporary_root = restored.temporary_root
        restored.mark_clean()
        ui.unregister()
        assert not temporary_root.exists()
        assert not any(
            getattr(handler, "__module__", None) == ui.__name__
            for callbacks in (bpy.app.handlers.load_post, bpy.app.handlers.save_pre)
            for handler in callbacks
        )


def assert_quick_import(module_key, repository_root):
    ui = importlib.import_module(f"{module_key}.ui.session")
    properties = importlib.import_module(f"{module_key}.ui.properties")
    preview_ui = importlib.import_module(
        f"{module_key}.ui.import_preview"
    )
    session = ui.new_scene_session(bpy.context.scene)

    def project_snapshot():
        project = session.project
        return (
            id(project),
            project.id,
            project.schema_version,
            tuple(
                (name, tuple(getattr(project, name).items()))
                for name in project.__dataclass_fields__
                if isinstance(getattr(project, name), dict)
            ),
            session.dirty_reasons,
        )

    def stage(*sources):
        directory = sources[0].parent
        assert all(source.parent == directory for source in sources)
        result = bpy.ops.chemblender.quick_import(
            directory=str(directory),
            files=[{"name": source.name} for source in sources],
            validation_mode="balanced",
        )
        assert result == {"FINISHED"}, (sources, result)
        state = properties.get_quick_import_state(session)
        assert state.preview is not None
        assert state.active_job is None
        return state

    before = project_snapshot()
    before_objects = tuple(bpy.data.objects)
    for relative in (
        "tests/fixtures/xyz/water.xyz",
        "tests/fixtures/cube/sheared.cube",
    ):
        source = repository_root / relative
        state = stage(source)
        assert len(state.preview.source_previews) == 1
        assert state.preview.source_previews[0].source_path == source.resolve()
        assert project_snapshot() == before
        assert bpy.ops.chemblender.cancel_import() == {"FINISHED"}
        assert project_snapshot() == before
        assert tuple(bpy.data.objects) == before_objects
        assert state.preview is None

    state = stage(repository_root / "tests/fixtures/xyz/water.xyz")
    revision = state.browser_revision
    structure_count = len(session.project.structures)
    assert bpy.ops.chemblender.confirm_import() == {"FINISHED"}
    assert len(session.project.structures) == structure_count + 1
    assert state.browser_revision == revision + 1
    assert state.preview is None
    assert session.dirty_reasons == frozenset({"import"})
    structure_views = [
        obj
        for obj in bpy.data.objects
        if obj.get("cb_scene_preset_id") == "structure_publication"
    ]
    assert structure_views
    browser = importlib.import_module(
        f"{module_key}.ui.project_browser.panel"
    )
    browser_settings = bpy.context.scene.chemblender_project_browser
    browser_settings.mode = "by_source"
    rows_before_cube = browser.refresh_project_browser(bpy.context.scene)
    assert any(row.kind == "structure" for row in rows_before_cube)

    state = stage(repository_root / "tests/fixtures/cube/sheared.cube")
    structure_count = len(session.project.structures)
    assert bpy.ops.chemblender.confirm_import() == {"FINISHED"}
    assert len(session.project.structures) == structure_count + 1
    assert state.preview is None
    browser_settings.mode = "by_data"
    rows_after_cube = browser.refresh_project_browser(bpy.context.scene)
    assert browser_settings.quality_filter == "all"
    assert rows_after_cube is not rows_before_cube
    assert any(row.kind == "structure" for row in rows_after_cube)
    assert any(row.kind == "grid3d" for row in rows_after_cube)
    grid_label = next(
        row.label for row in rows_after_cube if row.kind == "grid3d"
    )
    browser_settings.search = grid_label.swapcase()
    searched = browser.refresh_project_browser(bpy.context.scene)
    assert any(row.kind == "grid3d" for row in searched)
    browser_settings.search = ""
    browser.refresh_project_browser(bpy.context.scene)
    selected_index = next(
        index
        for index, row in enumerate(browser_settings.rows)
        if row.entity_id
    )
    browser_settings.selected_index = selected_index
    assert session.active_entity_id == UUID(
        browser_settings.rows[selected_index].entity_id
    )
    selected_entity_id = session.active_entity_id
    grid = next(
        dataset
        for dataset in session.project.datasets.values()
        if type(dataset).__name__ == "Grid3D"
    )
    original_values = grid.data.values

    class ArraySentinel:
        def __array__(self, *_args, **_kwargs):
            raise AssertionError("Project Browser materialized Grid3D")

        def __iter__(self):
            raise AssertionError("Project Browser traversed Grid3D")

    object.__setattr__(grid.data, "values", ArraySentinel())
    try:
        for mode in ("by_source", "by_data"):
            browser_settings.mode = mode
            browser_settings.search = "density"
            assert browser.refresh_project_browser(bpy.context.scene)
            assert session.active_entity_id == selected_entity_id
    finally:
        object.__setattr__(grid.data, "values", original_values)
        browser_settings.search = ""

    with TemporaryDirectory() as directory:
        directory = Path(directory)
        first = directory / "first.xyz"
        second = directory / "second.xyz"
        first.write_text(
            "1\nfirst\nH 0.1 0 0\n",
            encoding="utf-8",
        )
        second.write_text(
            "1\nsecond\nH 0.2 0 0\n",
            encoding="utf-8",
        )
        state = stage(first, second)
        before_failure_objects = tuple(bpy.data.objects)
        before_failure_structures = len(session.project.structures)
        original_apply = preview_ui.apply_scene_preset
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated view failure")
            return original_apply(*args, **kwargs)

        try:
            preview_ui.apply_scene_preset = fail_second
            assert bpy.ops.chemblender.confirm_import() == {"FINISHED"}
        finally:
            preview_ui.apply_scene_preset = original_apply
        assert len(session.project.structures) == before_failure_structures + 2
        assert tuple(bpy.data.objects) == before_failure_objects
        assert (
            bpy.context.scene.chemblender_quick_import.recent_summary
            == "data committed; view failed"
        )
        assert state.preview is None


def assert_optional_workspace(module_key):
    workspace_module = importlib.import_module(
        f"{module_key}.ui.workspace"
    )
    asset = workspace_module.workspace_asset_path()
    assert asset == (
        Path(workspace_module.__file__).resolve().parents[1]
        / "assets"
        / "Chem_Workspace.blend"
    )
    assert asset.is_file()
    with bpy.data.libraries.load(str(asset), link=False) as (
        data_from,
        _data_to,
    ):
        assert list(data_from.workspaces) == ["ChemBlender"]
        for field in (
            "scenes",
            "objects",
            "collections",
            "meshes",
            "materials",
            "images",
            "texts",
            "node_groups",
        ):
            assert list(getattr(data_from, field)) == [], field

    window = bpy.context.window
    if window is None or bpy.app.background:
        before_workspaces = tuple(bpy.data.workspaces)
        before_screens = tuple(bpy.data.screens)
        with bpy.data.libraries.load(str(asset), link=False) as (
            _data_from,
            data_to,
        ):
            data_to.workspaces = ["ChemBlender"]
        appended = data_to.workspaces[0]
        assert workspace_module.workspace_is_compatible(appended)
        workspace_module._remove_new_data(
            before_workspaces,
            before_screens,
        )
        return

    original = window.workspace
    before_count = len(bpy.data.workspaces)
    assert bpy.ops.chemblender.open_workspace() == {"FINISHED"}
    assert window.workspace.name == "ChemBlender"
    assert workspace_module.workspace_is_compatible(window.workspace)
    appended_count = len(bpy.data.workspaces)
    assert appended_count == before_count + 1
    assert bpy.ops.chemblender.open_workspace() == {"FINISHED"}
    assert len(bpy.data.workspaces) == appended_count

    window.workspace = original
    appended = bpy.data.workspaces.get("ChemBlender")
    bpy.data.batch_remove(ids=(appended, *tuple(appended.screens)))
    real_path = workspace_module.workspace_asset_path
    try:
        workspace_module.workspace_asset_path = lambda: asset.with_name(
            "missing-workspace.blend"
        )
        assert bpy.ops.chemblender.open_workspace() == {"CANCELLED"}
    finally:
        workspace_module.workspace_asset_path = real_path
    assert window.workspace is original
    assert bpy.data.workspaces.get("ChemBlender") is None
    registration = importlib.import_module(
        f"{module_key}.runtime.registration"
    )
    registered_names = {
        cls.__name__
        for cls in registration._registered_classes
        if getattr(cls, "is_registered", False)
    }
    assert "CHEMBLENDER_PT_quick_import" in registered_names
    assert "CHEMBLENDER_PT_project_browser" in registered_names


def assert_installed_blend_libraries(module_key):
    spec = importlib.util.find_spec(module_key)
    assert spec is not None and spec.submodule_search_locations
    extension_root = Path(next(iter(spec.submodule_search_locations)))
    expected_node_groups = {
        "Chem_Nodes.blend": 174,
        "Chem_Nodes_En.blend": 171,
    }

    for filename, expected_count in expected_node_groups.items():
        blend_file = extension_root / filename
        assert blend_file.is_file(), blend_file
        with bpy.data.libraries.load(str(blend_file), link=False) as (data_from, _):
            assert len(data_from.node_groups) == expected_count, filename


def assert_grid_volume_adapter(module_key):
    import openvdb

    core = importlib.import_module(f"{module_key}.core")
    adapter = importlib.import_module(f"{module_key}.grid_volume")
    values = memoryview(array.array("d", range(8)))
    values = values.cast("B").cast("d", shape=(2, 2, 2))
    dataset_id = uuid4()
    structure_id = uuid4()
    grid = core.Grid3D(
        id=dataset_id,
        revision="grid-revision",
        semantic_role="molecular_orbital",
        domain="grid",
        data=core.ArrayData(
            values, ("x", "y", "z"), "inverse_bohr_to_three_halves"
        ),
        status=core.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        origin=(1.0, 2.0, 3.0),
        step_vectors=((1.0, 0.0, 0.0), (0.2, 1.0, 0.0), (0.0, 0.3, 1.0)),
        coordinate_unit="bohr",
        structure_id=structure_id,
    )
    with TemporaryDirectory() as directory:
        cache_root = Path(directory)
        cache = adapter.volume_cache_path(cache_root, grid)
        obj = adapter.create_grid_volume(
            grid,
            cache_root,
            collection=bpy.context.scene.collection,
        )
        volume = obj.data
        try:
            assert cache.is_file()
            assert obj.type == "VOLUME" and obj.matrix_world.is_identity
            assert len(volume.grids) == 1 and volume.grids["density"] is not None
            assert obj["cb_dataset_id"] == str(dataset_id)
            assert obj["cb_dataset_revision"] == "grid-revision"
            assert obj["cb_structure_id"] == str(structure_id)
            assert obj["cb_dataset_index"] == 0
            assert obj["cb_semantic_role"] == "molecular_orbital"
            assert obj["cb_value_unit"] == "inverse_bohr_to_three_halves"
            assert obj["cb_source_coordinate_unit"] == "bohr"
            assert obj["cb_display_coordinate_unit"] == "angstrom"
            assert obj["cb_render_cache_key"] == cache.stem
            cached = openvdb.read(str(cache), "density")
            assert cached.getAccessor().getValue((1, 0, 1)) == 5.0
            expected = tuple(value * 0.529177210903 for value in (2.2, 3.3, 4.0))
            actual = tuple(cached.transform.indexToWorld((1, 1, 1)))
            assert all(abs(a - b) < 1e-12 for a, b in zip(actual, expected))

            lod = core.derive_grid_lod(grid, strides=(2, 1, 1)).datasets[0]
            lod_cache = adapter.volume_cache_path(cache_root, lod)
            assert lod_cache != cache
            lod_obj = adapter.create_grid_volume(
                lod, cache_root, collection=bpy.context.scene.collection
            )
            lod_volume = lod_obj.data
            try:
                assert lod_cache.is_file()
                assert lod_obj["cb_render_cache_key"] == lod_cache.stem
                lod_cached = openvdb.read(str(lod_cache), "density")
                assert lod_cached.getAccessor().getValue((0, 1, 1)) == 3.0
                lod_world = tuple(
                    lod_cached.transform.indexToWorld((1, 0, 0))
                )
                expected_lod = tuple(
                    value * 0.529177210903 for value in (3.0, 2.0, 3.0)
                )
                assert all(
                    abs(a - b) < 1e-12
                    for a, b in zip(lod_world, expected_lod)
                )
            finally:
                bpy.data.objects.remove(lod_obj, do_unlink=True)
                bpy.data.volumes.remove(lod_volume)
        finally:
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.volumes.remove(volume)


def assert_vibration_view_adapter(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    adapter = importlib.import_module(f"{module_key}.vibration_view")
    mesh = bpy.data.meshes.new("ChemBlender vibration smoke mesh")
    mesh.from_pydata([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [], [])
    obj = bpy.data.objects.new("ChemBlender vibration smoke", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mode_set_id = uuid4()
    modes = core.VibrationalModeSet(
        id=mode_set_id,
        revision="vibration-revision",
        semantic_role="vibrational_modes",
        domain="mode",
        data=core.ArrayData(numpy.asarray([-100.0]), ("mode",), "inverse_centimeter"),
        status=core.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=uuid4(),
        displacements=core.ArrayData(
            numpy.asarray([[[1.0, 0.0, 0.0], [0.0, 0.5, 0.0]]]),
            ("mode", "atom", "xyz"),
            "angstrom",
        ),
        reduced_masses=None,
        force_constants=None,
        ir_intensities=None,
        raman_activities=None,
        symmetries=None,
        displacement_convention="cclib_cartesian",
    )
    try:
        modifier = adapter.create_vibration_view(
            obj,
            modes,
            mode_index=0,
            arrow_scale=2.0,
        )
        assert obj["cb_vibration_mode_set_id"] == str(mode_set_id)
        assert obj["cb_vibration_mode_index"] == 0
        assert modifier.type == "NODES"
        assert modifier.node_group["cbq_contract"] == "vector_arrow_v1"
        assert len(obj.modifiers) == 1
        assert mesh.attributes["cbq_vector"].domain == "POINT"
        vectors = [0.0] * 6
        mesh.attributes["cbq_vector"].data.foreach_get("vector", vectors)
        assert vectors == [2.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        evaluated_geometry = evaluated.evaluated_geometry()
        assert len(evaluated_geometry.instance_references()) == 1
        assert len(evaluated_geometry.instances_pointcloud().points) == 2

        adapter.apply_vibration_phase(obj, math.pi / 2.0, amplitude_scale=0.5)
        coordinates = [0.0] * 6
        mesh.vertices.foreach_get("co", coordinates)
        assert numpy.allclose(coordinates, [0.5, 0.0, 0.0, 1.0, 0.25, 0.0])
        adapter.apply_vibration_phase(obj, math.pi, amplitude_scale=0.5)
        mesh.vertices.foreach_get("co", coordinates)
        assert numpy.allclose(coordinates, [0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def assert_dataset_and_trajectory_views(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    adapter = importlib.import_module(f"{module_key}.dataset_view")
    trajectory = importlib.import_module(f"{module_key}.trajectory_view")
    structure_id = uuid4()
    structure = core.Structure(
        id=structure_id,
        revision="structure-revision",
        atomic_numbers=(8, 1, 1),
        coordinates=core.ArrayData(
            numpy.asarray(
                [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [-2.0, 0.0, 0.0]]
            ),
            ("atom", "xyz"),
            "bohr",
        ),
    )
    obj = adapter.create_structure_view(
        structure,
        name="ChemBlender dataset smoke",
        collection=bpy.context.scene.collection,
    )
    mesh = obj.data
    try:
        assert obj["cb_structure_id"] == str(structure_id)
        atom_ids = [0] * 3
        obj.data.attributes["cbq_atom_id"].data.foreach_get("value", atom_ids)
        assert atom_ids == [0, 1, 2]
        coordinates = [0.0] * 9
        obj.data.vertices.foreach_get("co", coordinates)
        assert numpy.allclose(
            coordinates,
            [
                0.0,
                0.0,
                0.0,
                1.058354421806,
                0.0,
                0.0,
                -1.058354421806,
                0.0,
                0.0,
            ],
        )

        scalar_id = uuid4()
        scalar = core.AtomicProperty(
            id=scalar_id,
            revision="scalar-revision",
            semantic_role="mulliken_charge",
            domain="atom",
            data=core.ArrayData(
                numpy.asarray([-0.2, numpy.nan, 0.4]),
                ("atom",),
                "elementary_charge",
            ),
            status=core.DatasetStatus.PARTIAL,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure_id,
        )
        adapter.apply_atomic_scalar(obj, scalar, symmetric=True)
        scalar_values = [0.0] * 3
        scalar_valid = [False] * 3
        obj.data.attributes["cbq_atom_scalar"].data.foreach_get(
            "value", scalar_values
        )
        obj.data.attributes["cbq_atom_scalar_valid"].data.foreach_get(
            "value", scalar_valid
        )
        assert numpy.allclose(scalar_values, [-0.2, 0.0, 0.4])
        assert scalar_valid == [True, False, True]
        assert obj["cb_scalar_dataset_id"] == str(scalar_id)
        assert obj["cb_scalar_unit"] == "elementary_charge"
        assert obj["cb_scalar_display_min"] == -0.4
        assert obj["cb_scalar_display_max"] == 0.4
        assert obj.data.attributes["colour"].domain == "POINT"

        vector_id = uuid4()
        vector = core.AtomicProperty(
            id=vector_id,
            revision="vector-revision",
            semantic_role="force",
            domain="atom",
            data=core.ArrayData(
                numpy.asarray(
                    [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 3.0]]
                ),
                ("atom", "xyz"),
                "hartree_per_bohr",
            ),
            status=core.DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure_id,
        )
        modifier = adapter.apply_atomic_vector(obj, vector, display_scale=0.5)
        assert modifier.node_group["cbq_contract"] == "vector_arrow_v1"
        assert obj["cb_vector_dataset_id"] == str(vector_id)
        assert obj["cb_vector_unit"] == "hartree_per_bohr"
        vector_values = [0.0] * 9
        obj.data.attributes["cbq_vector"].data.foreach_get(
            "vector", vector_values
        )
        assert vector_values == [0.5, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.5]
        assert len(obj.modifiers) == 1
        adapter.apply_atomic_vector(obj, vector, display_scale=1.0)
        assert len(obj.modifiers) == 1
        bpy.context.view_layer.update()
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        evaluated_geometry = evaluated.evaluated_geometry()
        assert len(evaluated_geometry.instance_references()) == 1
        assert len(evaluated_geometry.instances_pointcloud().points) == 3

        adapter.apply_atom_selection(obj, [0, 2], name="terminal_atoms")
        selected = [False] * 3
        obj.data.attributes["cbq_selected"].data.foreach_get("value", selected)
        assert selected == [True, False, True]
        assert obj["cb_selection_name"] == "terminal_atoms"

        states = core.ExcitedStateSet(
            id=uuid4(),
            revision="states-revision",
            semantic_role="excited_states",
            domain="state",
            data=core.ArrayData(
                numpy.asarray([20000.0, 30000.0]),
                ("state",),
                "inverse_centimeter",
            ),
            status=core.DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure_id,
            oscillator_strengths=core.ArrayData(
                numpy.asarray([0.1, 0.2]), ("state",), "dimensionless"
            ),
            rotatory_strengths=None,
            electric_transition_dipoles=None,
            velocity_transition_dipoles=None,
            magnetic_transition_dipoles=None,
            symmetries=None,
            multiplicities=(None, None),
            configurations=None,
            state_references=(
                core.ExcitedStateReferences(),
                core.ExcitedStateReferences(),
            ),
        )
        spectrum = core.derive_electronic_spectrum(
            states,
            kind=core.SpectrumKind.UV_VIS,
            profile=core.SpectrumProfile.STICK,
        ).datasets[0]
        adapter.link_stick_spectrum_selection(obj, spectrum, states, 1)
        assert obj["cb_selection_spectrum_id"] == str(spectrum.id)
        assert obj["cb_selection_dataset_id"] == str(states.id)
        assert obj["cb_selection_domain"] == "state"
        assert obj["cb_selection_index"] == 1
        broadened = core.derive_electronic_spectrum(
            states,
            kind=core.SpectrumKind.UV_VIS,
            profile=core.SpectrumProfile.GAUSSIAN,
            axis=numpy.asarray([19000.0, 20000.0, 21000.0]),
            fwhm=1000.0,
        ).datasets[0]
        try:
            adapter.link_stick_spectrum_selection(obj, broadened, states, 0)
        except ValueError:
            pass
        else:
            raise AssertionError("broadened spectrum selection must be rejected")

        frames = core.FrameSet(
            id=uuid4(),
            revision="trajectory-revision",
            semantic_role="coordinates",
            domain="frame",
            data=core.ArrayData(
                numpy.asarray(
                    [
                        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [-2.0, 0.0, 0.0]],
                        [[0.0, 0.0, 1.0], [2.0, 0.0, 1.0], [-2.0, 0.0, 1.0]],
                    ]
                ),
                ("frame", "atom", "xyz"),
                "bohr",
            ),
            status=core.DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure_id,
            comments=("first", "second"),
        )
        invalid_frames = core.FrameSet(
            id=uuid4(),
            revision="invalid-trajectory-revision",
            semantic_role="coordinates",
            domain="frame",
            data=core.ArrayData(
                numpy.asarray(
                    [
                        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [-2.0, 0.0, 0.0]],
                        [[0.0, 0.0, float("nan")], [2.0, 0.0, 1.0], [-2.0, 0.0, 1.0]],
                    ]
                ),
                ("frame", "atom", "xyz"),
                "bohr",
            ),
            status=core.DatasetStatus.PARTIAL,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure_id,
            comments=("first", "invalid"),
        )
        invalid_manager = core.TrajectoryFrameManager(invalid_frames)
        try:
            invalid_manager.frame(1)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid trajectory frames must be rejected")
        finally:
            invalid_manager.close()
        trajectory.configure_trajectory_view(
            obj, frames, frame_start=10, frame_step=2, cache_size=2
        )
        trajectory.configure_trajectory_view(
            obj, frames, frame_start=10, frame_step=2, cache_size=2
        )
        handlers = [
            handler
            for handler in bpy.app.handlers.frame_change_post
            if handler.__module__ == trajectory.__name__
        ]
        assert len(handlers) == 1
        bpy.context.scene.frame_set(12)
        obj.data.vertices.foreach_get("co", coordinates)
        assert numpy.allclose(
            numpy.asarray(coordinates).reshape((3, 3))[:, 2],
            [0.529177210903] * 3,
        )
        assert obj["cb_trajectory_frame_index"] == 1
        assert obj["cb_trajectory_cache_size"] == 2
        assert obj["cb_trajectory_prefetch_ahead"] == 0
        bpy.context.scene.frame_set(100)
        assert obj["cb_trajectory_frame_index"] == 1
        assert len(bpy.data.objects) >= 1
        trajectory.clear_trajectory_view(obj)
    finally:
        bpy.context.scene.frame_set(1)
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.name in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)


def assert_periodic_structure_view(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    adapter = importlib.import_module(f"{module_key}.dataset_view")
    structure = core.Structure(
        id=uuid4(),
        revision="periodic-structure-revision",
        atomic_numbers=(14,),
        coordinates=core.ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0]]), ("atom", "xyz"), "angstrom"
        ),
        cell=core.ArrayData(
            numpy.asarray([[4.0, 0.0, 0.0], [1.0, 3.0, 0.0], [0.0, 0.5, 5.0]]),
            ("cell_vector", "xyz"),
            "angstrom",
        ),
        periodic=core.PeriodicSiteData(
            fractional_coordinates=core.ArrayData(
                numpy.asarray([[0.0, 0.0, 0.0]]),
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=("Si1",),
            occupancies=core.ArrayData(
                numpy.ones(1), ("atom",), "dimensionless"
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",),
            disorder_groups=(0,),
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=(),
            cif_envelope_id=None,
            pbc=(True, False, True),
        ),
    )
    obj = adapter.create_structure_view(
        structure,
        name="ChemBlender periodic structure smoke",
        collection=bpy.context.scene.collection,
    )
    mesh = obj.data
    try:
        assert obj["cb_periodic"] is True
        assert list(obj["cb_pbc"]) == [True, False, True]
        assert numpy.allclose(
            list(obj["cb_periodic_cell"]),
            [4.0, 0.0, 0.0, 1.0, 3.0, 0.0, 0.0, 0.5, 5.0],
        )
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def assert_periodic_electronic_plots(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    plots = importlib.import_module(f"{module_key}.electronic_plot")
    structure_id = uuid4()
    common = dict(
        revision="electronic-revision",
        status=core.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure_id,
        spin_channels=("alpha", "beta"),
        fermi_energy=5.0,
        energy_reference=core.EnergyReference.ABSOLUTE,
    )
    band = core.BandStructure(
        id=uuid4(),
        semantic_role="band_structure",
        domain="band",
        data=core.ArrayData(
            numpy.asarray([[[4.0, 6.0], [4.5, 6.5]], [[4.1, 6.1], [4.6, 6.6]]]),
            ("spin", "kpoint", "band"),
            "electron_volt",
        ),
        occupations=None,
        kpoints=core.ArrayData(numpy.asarray([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]]), ("kpoint", "reciprocal_axis"), "dimensionless"),
        reciprocal_lattice=core.ArrayData(numpy.eye(3), ("reciprocal_vector", "cartesian_axis"), "inverse_angstrom"),
        distances=core.ArrayData(numpy.asarray([0.0, 1.0]), ("kpoint",), "inverse_angstrom"),
        labels=("GAMMA", "X"),
        branches=(core.BandPathBranch(0, 1, "GAMMA", "X"),),
        projections=None,
        orbital_labels=(),
        **common,
    )
    dos = core.DensityOfStates(
        id=uuid4(),
        semantic_role="density_of_states",
        domain="energy",
        data=core.ArrayData(numpy.asarray([[1.0, 2.0, 3.0], [0.5, 1.0, 1.5]]), ("spin", "energy"), "states_per_electron_volt"),
        energies=core.ArrayData(numpy.asarray([4.0, 5.0, 6.0]), ("energy",), "electron_volt"),
        projections=None,
        orbital_labels=(),
        **common,
    )
    band_obj = plots.create_band_structure_plot(band, collection=bpy.context.scene.collection)
    dos_obj = plots.create_dos_plot(dos, collection=bpy.context.scene.collection)
    try:
        assert len(band_obj.data.splines) == 4
        assert band_obj["cb_energy_reference"] == "fermi_shifted"
        assert band_obj.data.splines[0].points[0].co.y == -1.0
        assert len(dos_obj.data.splines) == 2
        assert dos_obj.data.splines[1].points[0].co.x == -0.5
        plots.select_band_sample(band_obj, band, 1, 0, 1)
        assert band_obj["cb_selected_spin"] == 1
        assert band_obj["cb_selected_band"] == 1
        plots.select_dos_sample(dos_obj, dos, 0, 2)
        assert dos_obj["cb_selected_energy"] == 2
    finally:
        for obj in (band_obj, dos_obj):
            curve = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.curves.remove(curve)


def assert_scene_preset_application(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    view = importlib.import_module(f"{module_key}.scene_preset_view")
    surface_view = importlib.import_module(f"{module_key}.surface_view")
    presets = core.builtin_scene_presets()
    structure = core.Structure(
        id=uuid4(), revision="scene-structure-r1", atomic_numbers=(8, 1),
        coordinates=core.ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
            ("atom", "xyz"), "angstrom",
        ),
    )
    modes = core.VibrationalModeSet(
        id=uuid4(), revision="scene-modes-r1", semantic_role="vibrational_modes",
        domain="mode", data=core.ArrayData(numpy.asarray([1000.0]), ("mode",), "inverse_centimeter"),
        status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        structure_id=structure.id,
        displacements=core.ArrayData(numpy.asarray([[[0.1, 0.0, 0.0], [-0.1, 0.0, 0.0]]]), ("mode", "atom", "xyz"), "angstrom"),
        reduced_masses=None, force_constants=None,
        ir_intensities=core.ArrayData(numpy.asarray([10.0]), ("mode",), "kilometer_per_mole"),
        raman_activities=None, symmetries=("A1",), displacement_convention="cclib_cartesian",
    )
    states = core.ExcitedStateSet(
        id=uuid4(), revision="scene-states-r1", semantic_role="excited_states",
        domain="state", data=core.ArrayData(numpy.asarray([20000.0]), ("state",), "inverse_centimeter"),
        status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        structure_id=structure.id,
        oscillator_strengths=core.ArrayData(numpy.asarray([0.2]), ("state",), "dimensionless"),
        rotatory_strengths=None, electric_transition_dipoles=None,
        velocity_transition_dipoles=None, magnetic_transition_dipoles=None,
        symmetries=("A1",), multiplicities=(1,), configurations=((),),
        state_references=(core.ExcitedStateReferences(),),
    )
    ir_batch = core.derive_vibrational_spectrum(
        modes, kind=core.SpectrumKind.IR, profile=core.SpectrumProfile.STICK
    )
    ir = ir_batch.datasets[0]
    uv_batch = core.derive_electronic_spectrum(
        states, kind=core.SpectrumKind.UV_VIS, profile=core.SpectrumProfile.STICK
    )
    uv = uv_batch.datasets[0]
    project = core.QCProject(uuid4(), "0.1")
    project.commit(core.ImportBatch(structures=(structure,), datasets=(modes, states)))
    project.commit(ir_batch)
    project.commit(uv_batch)

    created = []
    try:
        structure_plan = core.plan_scene_preset(
            presets["structure_publication"], project, {"structure": structure.id}, {}
        )
        created.extend(view.apply_scene_preset(structure_plan, project, collection=bpy.context.scene.collection))
        assert created[-1]["cb_scene_render_identity"] == structure_plan.render_identity

        vibration_plan = core.plan_scene_preset(
            presets["vibration_spectrum_linked"], project,
            {"structure": structure.id, "modes": modes.id, "spectrum": ir.id},
            {"arrow_scale": 2.0},
        )
        vibration_objects = view.apply_scene_preset(vibration_plan, project, collection=bpy.context.scene.collection)
        created.extend(vibration_objects)
        assert {obj.type for obj in vibration_objects} == {"MESH", "CURVE"}
        assert vibration_objects[0]["cb_selection_domain"] == "mode"
        assert vibration_objects[1]["cb_plot_contract"] == "spectrum_curve_v1"
        assert len(vibration_objects[1].data.splines) == 1

        electronic_plan = core.plan_scene_preset(
            presets["electronic_spectrum_linked"], project,
            {"structure": structure.id, "states": states.id, "spectrum": uv.id}, {},
        )
        electronic_objects = view.apply_scene_preset(electronic_plan, project, collection=bpy.context.scene.collection)
        created.extend(electronic_objects)
        assert electronic_objects[0]["cb_selection_domain"] == "state"

        grid_coordinates = numpy.indices((5, 5, 5), dtype=float)
        signed_values = grid_coordinates[0] - 2.0
        radius = numpy.sqrt(sum((axis - 2.0) ** 2 for axis in grid_coordinates))
        density_values = 1.5 - radius
        property_values = sum(axis - 2.0 for axis in grid_coordinates)
        grid_fields = dict(
            domain="grid", status=core.DatasetStatus.COMPLETE,
            source_calculation=None, provenance_ids=(), structure_id=None,
            origin=(-2.0, -2.0, -2.0),
            step_vectors=((1.0, 0.0, 0.0), (0.2, 1.0, 0.0), (0.0, 0.1, 1.0)),
            coordinate_unit="angstrom",
        )
        signed_grid = core.Grid3D(
            id=uuid4(), revision="signed-grid-r1", semantic_role="molecular_orbital",
            data=core.ArrayData(signed_values, ("x", "y", "z"), "dimensionless"),
            **grid_fields,
        )
        density_grid = core.Grid3D(
            id=uuid4(), revision="density-grid-r1", semantic_role="electron_density",
            data=core.ArrayData(density_values, ("x", "y", "z"), "dimensionless"),
            **grid_fields,
        )
        property_grid = core.Grid3D(
            id=uuid4(), revision="property-grid-r1", semantic_role="electrostatic_potential",
            data=core.ArrayData(property_values, ("x", "y", "z"), "dimensionless"),
            **grid_fields,
        )
        grid_project = core.QCProject(uuid4(), "0.1")
        grid_project.commit(core.ImportBatch(datasets=(signed_grid, density_grid, property_grid)))
        with TemporaryDirectory() as cache_root:
            signed_plan = core.plan_scene_preset(
                presets["signed_isosurface"], grid_project, {"grid": signed_grid.id},
                {"isovalue": 0.5},
            )
            signed_objects = view.apply_scene_preset(
                signed_plan, grid_project, cache_root=cache_root,
                collection=bpy.context.scene.collection,
            )
            created.extend(signed_objects)
            assert [obj["cb_surface_phase"] for obj in signed_objects] == ["positive", "negative"]
            assert [obj["cb_surface_isovalue"] for obj in signed_objects] == [0.5, -0.5]
            bpy.context.view_layer.update()
            depsgraph = bpy.context.evaluated_depsgraph_get()
            for obj in signed_objects:
                evaluated = obj.evaluated_get(depsgraph)
                geometry = evaluated.evaluated_geometry()
                assert geometry.mesh is not None
                assert len(geometry.mesh.vertices) > 0

            property_plan = core.plan_scene_preset(
                presets["property_on_surface"], grid_project,
                {"surface_grid": density_grid.id, "property_grid": property_grid.id},
                {"surface_isovalue": 0.2, "color_min": -3.0, "color_max": 3.0},
            )
            property_objects = view.apply_scene_preset(
                property_plan, grid_project, cache_root=cache_root,
                collection=bpy.context.scene.collection,
            )
            created.extend(property_objects)
            property_obj = property_objects[0]
            bpy.context.view_layer.update()
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated = property_obj.evaluated_get(depsgraph)
            geometry = evaluated.evaluated_geometry()
            assert geometry.mesh is not None
            mesh = geometry.mesh
            assert len(mesh.vertices) > 0
            attribute = mesh.attributes["cbq_surface_property"]
            sampled = [0.0] * len(mesh.vertices)
            attribute.data.foreach_get("value", sampled)
            assert min(sampled) < max(sampled)
            assert property_obj["cb_property_colormap"] == "coolwarm"
            assert len(list(Path(cache_root).glob("surface/*.vdb"))) == 3

        periodic_id = uuid4()
        band = core.BandStructure(
            id=uuid4(), revision="scene-band-r1", semantic_role="band_structure", domain="band",
            data=core.ArrayData(numpy.asarray([[[4.0], [6.0]]]), ("spin", "kpoint", "band"), "electron_volt"),
            status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(), structure_id=periodic_id,
            occupations=None,
            kpoints=core.ArrayData(numpy.asarray([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]]), ("kpoint", "reciprocal_axis"), "dimensionless"),
            reciprocal_lattice=core.ArrayData(numpy.eye(3), ("reciprocal_vector", "cartesian_axis"), "inverse_angstrom"),
            distances=core.ArrayData(numpy.asarray([0.0, 1.0]), ("kpoint",), "inverse_angstrom"),
            spin_channels=("alpha",), labels=("GAMMA", "X"), branches=(core.BandPathBranch(0, 1, "GAMMA", "X"),),
            projections=None, orbital_labels=(), fermi_energy=5.0, energy_reference=core.EnergyReference.ABSOLUTE,
        )
        dos = core.DensityOfStates(
            id=uuid4(), revision="scene-dos-r1", semantic_role="density_of_states", domain="energy",
            data=core.ArrayData(numpy.asarray([[1.0, 2.0]]), ("spin", "energy"), "states_per_electron_volt"),
            status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(), structure_id=periodic_id,
            energies=core.ArrayData(numpy.asarray([4.0, 6.0]), ("energy",), "electron_volt"),
            spin_channels=("alpha",), projections=None, orbital_labels=(), fermi_energy=5.0,
            energy_reference=core.EnergyReference.ABSOLUTE,
        )
        periodic = core.Structure(
            id=periodic_id, revision="periodic-r1", atomic_numbers=(14,),
            coordinates=core.ArrayData(numpy.zeros((1, 3)), ("atom", "xyz"), "angstrom"),
        )
        periodic_project = core.QCProject(uuid4(), "0.1")
        periodic_project.commit(core.ImportBatch(structures=(periodic,), datasets=(band, dos)))
        band_plan = core.plan_scene_preset(
            presets["band_dos_linked"], periodic_project, {"band": band.id, "dos": dos.id}, {}
        )
        band_objects = view.apply_scene_preset(band_plan, periodic_project, collection=bpy.context.scene.collection)
        created.extend(band_objects)
        assert [obj["cb_plot_contract"] for obj in band_objects] == ["band_structure_curve_v1", "density_of_states_curve_v1"]

        before = len(bpy.data.objects)
        project.structures[structure.id] = replace(structure, revision="scene-structure-r2")
        try:
            view.apply_scene_preset(structure_plan, project)
            raise AssertionError("stale plan must fail")
        except core.ScenePresetError:
            pass
        assert len(bpy.data.objects) == before

        original = view.create_spectrum_plot
        view.create_spectrum_plot = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced failure"))
        project.structures[structure.id] = structure
        before = len(bpy.data.objects)
        try:
            view.apply_scene_preset(vibration_plan, project)
            raise AssertionError("adapter failure must fail")
        except RuntimeError as error:
            assert str(error) == "forced failure"
        finally:
            view.create_spectrum_plot = original
        assert len(bpy.data.objects) == before
    finally:
        for obj in reversed(created):
            if obj.type == "VOLUME":
                surface_view.remove_surface_object(obj)
            else:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data.users == 0:
                    bpy.data.batch_remove(ids=(data,))


def assert_complex_phonon_trajectory(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    views = importlib.import_module(f"{module_key}.dataset_view")
    trajectory = importlib.import_module(f"{module_key}.trajectory_view")
    primitive_id = uuid4()
    eigenvectors = numpy.zeros((1, 3, 1, 3), dtype=complex)
    eigenvectors[0, 0, 0, 0] = 1.0 + 2.0j
    modes = core.PhononModeSet(
        id=uuid4(), revision="phonon-smoke", semantic_role="phonon_modes", domain="mode",
        data=core.ArrayData(numpy.asarray([[-1.0, 2.0, 3.0]]), ("qpoint", "mode"), "terahertz"),
        status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        structure_id=primitive_id,
        qpoints=core.ArrayData(numpy.asarray([[0.5, 0.0, 0.0]]), ("qpoint", "reciprocal_axis"), "dimensionless"),
        eigenvectors=core.ArrayData(eigenvectors, ("qpoint", "mode", "atom", "xyz"), "dimensionless"),
        masses=core.ArrayData(numpy.asarray([4.0]), ("atom",), "atomic_mass_unit"),
        group_velocities=None, weights=None,
        eigenvector_convention="phonopy_mass_weighted_dynamical_matrix",
    )
    supercell = core.Structure(
        id=uuid4(), revision="phonon-supercell", atomic_numbers=(14, 14),
        coordinates=core.ArrayData(numpy.asarray([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0]]), ("atom", "xyz"), "angstrom"),
        cell=core.ArrayData(numpy.diag([6.0, 3.0, 3.0]), ("cell_vector", "xyz"), "angstrom"),
        periodic=core.PeriodicSiteData(
            fractional_coordinates=core.ArrayData(numpy.asarray([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]]), ("atom", "xyz"), "dimensionless"),
            site_labels=("Si1", "Si2"), occupancies=core.ArrayData(numpy.ones(2), ("atom",), "dimensionless"),
            isotropic_displacements=None, anisotropic_displacements=None,
            adp_types=("none", "none"), disorder_groups=(0, 0),
            declared_space_group_name=None, declared_space_group_number=None,
            symmetry_operations=(), cif_envelope_id=None,
        ),
    )
    frames = core.derive_phonon_frames(
        modes, supercell,
        primitive_atom_indices=[0, 0], translations=[[0, 0, 0], [1, 0, 0]],
        qpoint_index=0, mode_index=0, phases=[0.0, math.pi / 2], amplitude=2.0,
    ).datasets[0]
    obj = views.create_structure_view(supercell, name="ChemBlender phonon smoke", collection=bpy.context.scene.collection)
    mesh = obj.data
    try:
        bpy.context.scene.frame_set(1)
        trajectory.configure_trajectory_view(obj, frames)
        first = [0.0] * 6
        mesh.vertices.foreach_get("co", first)
        assert numpy.allclose(first, [1.0, 0.0, 0.0, 2.0, 0.0, 0.0])
        bpy.context.scene.frame_set(2)
        second = [0.0] * 6
        mesh.vertices.foreach_get("co", second)
        assert numpy.allclose(second, [2.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    finally:
        trajectory.clear_trajectory_view(obj)
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def assert_fermi_surface_view(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    view = importlib.import_module(f"{module_key}.fermi_surface_view")
    surface = core.FermiSurfaceMesh(
        id=uuid4(), revision="fermi-smoke", semantic_role="fermi_surface", domain="surface_vertex",
        data=core.ArrayData(numpy.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]), ("vertex", "xyz"), "inverse_angstrom"),
        status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        structure_id=uuid4(), band_structure_id=uuid4(),
        faces=core.ArrayData(numpy.asarray([[0, 1, 2], [0, 2, 3]]), ("face", "corner"), "dimensionless"),
        band_indices=core.ArrayData(numpy.asarray([1, 3]), ("face",), "dimensionless"),
        spin_index=1, fermi_energy=5.25, coordinate_convention="cartesian_reciprocal_2pi",
        properties=(
            core.SurfaceProperty("orbital_contribution", "vertex", core.ArrayData(numpy.asarray([0.1, 0.2, 0.3, 0.4]), ("vertex",), "dimensionless")),
            core.SurfaceProperty("spin_texture", "vertex", core.ArrayData(numpy.ones((4, 3)), ("vertex", "xyz"), "dimensionless")),
        ),
    )
    obj = view.create_fermi_surface_view(surface, collection=bpy.context.scene.collection)
    mesh = obj.data
    try:
        assert len(mesh.vertices) == 4 and len(mesh.polygons) == 2
        bands = [0, 0]
        mesh.attributes["cbq_band_index"].data.foreach_get("value", bands)
        assert bands == [1, 3]
        scalars = [0.0] * 4
        mesh.attributes["cbq_orbital_contribution"].data.foreach_get("value", scalars)
        assert numpy.allclose(scalars, [0.1, 0.2, 0.3, 0.4])
        view.select_fermi_face(obj, surface, 1)
        assert obj["cb_selected_face"] == 1
        assert obj["cb_selected_band"] == 3
        assert obj["cb_spin_index"] == 1
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def assert_project_sidecar_link(module_key):
    core = importlib.import_module(f"{module_key}.core")
    links = importlib.import_module(f"{module_key}.project_link")
    scene = bpy.context.scene
    marker = bpy.data.meshes.new("ChemBlender sidecar marker mesh")
    marker_object = bpy.data.objects.new("ChemBlender sidecar marker", marker)
    scene.collection.objects.link(marker_object)
    try:
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            blend_path = directory / "scene" / "view.blend"
            sidecar = directory / "data" / "smoke.cbq"
            project = core.QCProject(id=uuid4(), schema_version="0.1")
            core.save_project(sidecar, project)
            locator = links.write_project_link(
                scene, project, sidecar, blend_path=blend_path
            )
            assert not Path(locator).is_absolute()
            assert links.MANIFEST_HASH_KEY in scene
            result = links.resolve_project_link(scene, blend_path=blend_path)
            assert result.status is links.ProjectLinkStatus.CONNECTED
            assert result.project.id == project.id
            core.close_project(result.project)

            core.save_project(sidecar, project)
            result = links.resolve_project_link(scene, blend_path=blend_path)
            assert result.status is links.ProjectLinkStatus.MISMATCH
            assert marker_object.name in bpy.data.objects

            links.write_project_link(
                scene, project, sidecar, blend_path=blend_path
            )
            manifest_path = sidecar / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["manifest_sha256"] = "0" * 64
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True),
                encoding="utf-8",
            )
            result = links.resolve_project_link(scene, blend_path=blend_path)
            assert result.status is links.ProjectLinkStatus.INVALID
            assert marker_object.name in bpy.data.objects

            scene[links.SIDECAR_LOCATOR_KEY] = "missing.cbq"
            result = links.resolve_project_link(scene, blend_path=blend_path)
            assert result.status is links.ProjectLinkStatus.MISSING
            assert marker_object.name in bpy.data.objects
    finally:
        for key in (
            links.PROJECT_ID_KEY,
            links.PROJECT_SCHEMA_KEY,
            links.SIDECAR_LOCATOR_KEY,
            links.MANIFEST_HASH_KEY,
        ):
            if key in scene:
                del scene[key]
        bpy.data.objects.remove(marker_object, do_unlink=True)
        bpy.data.meshes.remove(marker)


def assert_topology_view(module_key, repository_root):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    view = importlib.import_module(f"{module_key}.topology_view")
    fixture = (
        repository_root
        / "tests"
        / "fixtures"
        / "critic2"
        / "cpreport-minimal.json"
    )
    graph = core.parse_critic2_cpreport(
        fixture, structure_id=uuid4()
    ).datasets[0]
    path = core.TopologyPath(
        id=uuid4(),
        start_id=graph.critical_point_ids[0],
        end_id=graph.critical_point_ids[2],
        samples=core.ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
            ("sample", "xyz"),
            "bohr",
        ),
    )
    graph = replace(graph, paths=(path,))
    points, paths = view.create_topology_view(graph)
    mesh = points.data
    curve = paths.data
    try:
        assert len(mesh.vertices) == 3
        assert numpy.allclose(mesh.vertices[1].co, [1.058354421806, 0.0, 0.0])
        kinds = [0, 0, 0]
        mesh.attributes["cbq_critical_point_kind"].data.foreach_get("value", kinds)
        assert kinds == [0, 0, 2]
        fields = [0.0, 0.0, 0.0]
        mesh.attributes["cbq_field_value"].data.foreach_get("value", fields)
        assert numpy.allclose(fields, [10.0, 10.0, 0.25])
        assert points["cb_topology_contract"] == "topology_graph_v1"
        assert len(curve.splines) == 1
        assert len(curve.splines[0].points) == 2
        assert paths["cb_topology_contract"] == "topology_paths_v1"
    finally:
        bpy.data.objects.remove(paths, do_unlink=True)
        bpy.data.curves.remove(curve)
        bpy.data.objects.remove(points, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def assert_legacy_crystal_reader_baseline(module_key, repository_root):
    reader = importlib.import_module(f"{module_key}.read")
    cif = repository_root / "tests" / "fixtures" / "cif" / "cscl.cif"
    poscar = repository_root / "tests" / "fixtures" / "poscar" / "cscl.vasp"
    cif_result = reader.read_cif(cif)
    assert cif_result[0] == [4.12, 4.12, 4.12]
    assert cif_result[1] == [90.0, 90.0, 90.0]
    assert cif_result[3] == 221
    assert cif_result[4] == ["Cs", "Cl"]
    assert cif_result[5] == ["Cs1", "Cl1"]
    assert cif_result[6:9] == ([0.0, 0.5], [0.0, 0.5], [0.0, 0.5])
    assert cif_result[9] == ["x,y,z"]

    poscar_result = reader.read_poscar(poscar)
    assert poscar_result[0] == (4.12, 4.12, 4.12), poscar_result
    assert poscar_result[1] == (90.0, 90.0, 90.0)
    assert poscar_result[3] == 221
    assert poscar_result[4] == ["Cs", "Cl"]
    assert poscar_result[5] == ["Cs1", "Cl1"]
    assert poscar_result[6:9] == ([0.0, 0.5], [0.0, 0.5], [0.0, 0.5])
    assert len(poscar_result[9]) == 48


arguments = sys.argv[sys.argv.index("--") + 1 :]
assert len(arguments) in (1, 2), "expected ZIP path and optional --keep-enabled"
assert len(arguments) == 1 or arguments[1] == "--keep-enabled"
keep_enabled = arguments[1:] == ["--keep-enabled"]
package = Path(arguments[0]).resolve()
assert package.is_file(), package
assert_package_contents(package)
before_install_modules = set(sys.modules)

result = bpy.ops.extensions.package_install_files(
    filepath=str(package),
    repo="user_default",
    enable_on_install=True,
    overwrite=True,
)
assert result == {"FINISHED"}, result

module_keys = sorted(
    addon.module
    for addon in bpy.context.preferences.addons
    if addon.module.rsplit(".", 1)[-1] == "chemblender"
)
assert len(module_keys) == 1, module_keys
module_key = module_keys[0]
assert_enabled(module_key, before_install_modules)
legacy_inventory = json.loads(
    (
        package.parent.parent
        / "tests/fixtures/registration/legacy-registration-inventory.json"
    ).read_text(encoding="utf-8")
)
assert legacy_inventory["installed_package_name"] == module_key
stable_inventory = registration_inventory(module_key)
expected_inventory = {
    name: legacy_inventory[name]
    for name in (
        "registered_classes",
        "module_callbacks",
        "handlers",
        "menu_callbacks",
    )
}
expected_inventory["module_callbacks"] += [
    {"module": ".ui.session", "register": True, "unregister": True},
    {"module": ".ui.properties", "register": True, "unregister": True},
    {"module": ".ui.project_browser.panel", "register": True, "unregister": True},
    {"module": ".ui.file_handlers", "register": True, "unregister": True},
    {"module": ".ui.workspace", "register": True, "unregister": True},
]
expected_inventory["registered_classes"] += [
    {
        "module": ".ui.file_handlers",
        "name": "CHEMBLENDER_FH_project_browser",
        "id": "CHEMBLENDER_FH_project_browser",
        "base": "FileHandler",
    },
    {
        "module": ".ui.file_handlers",
        "name": "CHEMBLENDER_FH_view_3d_window",
        "id": "CHEMBLENDER_FH_view_3d_window",
        "base": "FileHandler",
    },
    {
        "module": ".ui.import_preview",
        "name": "CHEMBLENDER_OT_cancel_import",
        "id": "chemblender.cancel_import",
        "base": "Operator",
    },
    {
        "module": ".ui.import_preview",
        "name": "CHEMBLENDER_OT_confirm_import",
        "id": "chemblender.confirm_import",
        "base": "Operator",
    },
    {
        "module": ".ui.import_preview",
        "name": "CHEMBLENDER_PG_import_preview_row",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.quick_import",
        "name": "CHEMBLENDER_PT_quick_import",
        "id": "CHEMBLENDER_PT_QUICK_IMPORT",
        "base": "Panel",
    },
    {
        "module": ".ui.properties",
        "name": "CHEMBLENDER_PG_quick_import",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.quick_import",
        "name": "CHEMBLENDER_OT_quick_import",
        "id": "chemblender.quick_import",
        "base": "Operator",
    },
    {
        "module": ".ui.workspace",
        "name": "CHEMBLENDER_OT_open_workspace",
        "id": "chemblender.open_workspace",
        "base": "Operator",
    },
    {
        "module": ".ui.project_browser.panel",
        "name": "CHEMBLENDER_PG_project_browser",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.project_browser.panel",
        "name": "CHEMBLENDER_PG_project_browser_row",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.project_browser.panel",
        "name": "CHEMBLENDER_PT_project_browser",
        "id": "CHEMBLENDER_PT_PROJECT_BROWSER",
        "base": "Panel",
    },
    {
        "module": ".ui.project_browser.panel",
        "name": "CHEMBLENDER_UL_project_rows",
        "id": None,
        "base": "UIList",
    },
]
expected_inventory["registered_classes"].sort(
    key=lambda item: (
        item["module"],
        item["name"],
        item["id"] or "",
        item["base"],
    )
)
expected_inventory["handlers"] += [
    {"owner": "load_post", "module": ".runtime.registration", "name": "_reader_api_load_post_handler"},
    {"owner": "load_post", "module": ".ui.session", "name": "_load_post_handler"},
    {"owner": "load_pre", "module": ".ui.properties", "name": "_load_pre_handler"},
    {"owner": "save_pre", "module": ".ui.session", "name": "_save_pre_handler"},
]
expected_inventory["handlers"].sort(key=lambda item: tuple(item.values()))
assert stable_inventory == expected_inventory

bridge = importlib.import_module(f"{module_key}.runtime.reader_api_bridge")
reader_api = importlib.import_module(f"{module_key}.reader_api")
registry_module = importlib.import_module(f"{module_key}.reader_api.registry")
registry = bridge.get_reader_plugin_registry()
builtin_identities = tuple(
    id(item) for item in registry.descriptors
)
model_identities = (
    reader_api.PublicImportBatch,
    reader_api.PublicReaderDescriptor,
    reader_api.ReaderPluginManifest,
)
builtin = registry_module.builtin_reader_plugins()[0]
descriptor = replace(
    builtin.descriptor,
    plugin_id="org.example.blender_lifecycle",
    reader_id="external.blender_lifecycle",
)
entry = replace(
    builtin.manifest.readers[0],
    reader_id=descriptor.reader_id,
    reader_version=descriptor.reader_version,
    extensions=descriptor.extensions,
    capabilities=tuple(
        sorted(
            name
            for name, support in descriptor.capabilities.items()
            if support is reader_api.CapabilitySupport.SUPPORTED
        )
    ),
)
external = replace(
    builtin,
    descriptor=descriptor,
    manifest=replace(
        builtin.manifest,
        plugin_id=descriptor.plugin_id,
        readers=(entry,),
    ),
)
bpy.app.driver_namespace[READER_API_HANDLE_KEY].register_callback(external)

for _ in range(2):
    owned_classes = owned_registration_classes(module_key)
    old_handle = bpy.app.driver_namespace[READER_API_HANDLE_KEY]
    assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
    assert_disabled(module_key, owned_classes)
    assert bridge.get_reader_plugin_registry() is registry
    assert next(
        item
        for item in registry.descriptors
        if item.reader_id == descriptor.reader_id
    ) is descriptor
    assert bpy.ops.preferences.addon_enable(module=module_key) == {"FINISHED"}
    assert_enabled(module_key, before_install_modules)
    assert registration_inventory(module_key) == stable_inventory
    assert bpy.app.driver_namespace[READER_API_HANDLE_KEY] is not old_handle
    assert bridge.get_reader_plugin_registry() is registry
    assert tuple(
        id(item)
        for item in registry.descriptors
        if item.plugin_id == "chemblender.builtin"
    ) == builtin_identities
    current_reader_api = importlib.import_module(f"{module_key}.reader_api")
    assert (
        current_reader_api.PublicImportBatch,
        current_reader_api.PublicReaderDescriptor,
        current_reader_api.ReaderPluginManifest,
    ) == model_identities
    assert next(
        item
        for item in registry.descriptors
        if item.reader_id == descriptor.reader_id
    ) is descriptor

bpy.app.driver_namespace[READER_API_HANDLE_KEY].unregister_callback(
    external.manifest
)

core = importlib.import_module(f"{module_key}.core")
assert set(core.builtin_recipes()) == {
    "tddft_uvvis",
    "vibrational_ir_spectrum",
    "wavefunction_molecular_orbital_grid",
}
assert_installed_blend_libraries(module_key)
assert_grid_volume_adapter(module_key)
assert_vibration_view_adapter(module_key)
assert_dataset_and_trajectory_views(module_key)
assert_periodic_structure_view(module_key)
assert_periodic_electronic_plots(module_key)
assert_scene_preset_application(module_key)
assert_complex_phonon_trajectory(module_key)
assert_fermi_surface_view(module_key)
assert_project_sidecar_link(module_key)
assert_quick_import(module_key, package.parent.parent)
assert_optional_workspace(module_key)
assert_project_session_manager(module_key)
assert_topology_view(module_key, package.parent.parent)
assert_legacy_crystal_reader_baseline(module_key, package.parent.parent)

import rdkit
from rdkit import Chem
from rdkit.Chem import AllChem

assert rdkit.__version__
assert version("rdkit") == "2026.3.3"
molecule = Chem.AddHs(Chem.MolFromSmiles("CCO"))
assert molecule is not None
assert AllChem.EmbedMolecule(molecule, randomSeed=0xC0FFEE) == 0

if keep_enabled:
    print("PASS: ChemBlender extension installed and enabled")
else:
    owned_classes = owned_registration_classes(module_key)
    assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
    assert_disabled(module_key, owned_classes)
    print("PASS: ChemBlender extension lifecycle")
