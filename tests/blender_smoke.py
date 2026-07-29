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
        "wheels/gemmi-0.7.5-cp313-cp313-win_amd64.whl",
    }
    forbidden_prefixes = ("scripts/", "tests/", "worker/", "__pycache__/")

    with ZipFile(package) as archive:
        names = {entry.filename.replace("\\", "/") for entry in archive.infolist()}

    assert required <= names, required - names
    assert not any(name.startswith(forbidden_prefixes) for name in names)
    assert not any(name.endswith(".zip") for name in names)
    assert sorted(name for name in names if name.endswith(".whl")) == [
        "wheels/gemmi-0.7.5-cp313-cp313-win_amd64.whl",
        "wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl",
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
    assert {
        relative_name(cls.__module__, module_key)
        for cls in classes
    }.issubset(registration.REGISTER_MODULE_NAMES)
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
    assert f"{module_key}.ui.topology" in sys.modules
    assert f"{module_key}.ui.scientific_edit" in sys.modules
    assert f"{module_key}.ui.export" in sys.modules
    assert f"{module_key}.ui.grid" in sys.modules
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
    assert hasattr(bpy.types, "CHEMBLENDER_OT_compute_topology")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_accept_topology")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_reject_topology")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_switch_topology")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_apply_scientific_edits")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_apply_frame_force")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_export_project_entity")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_resolve_grid_semantics")
    assert hasattr(bpy.types, "CHEMBLENDER_OT_create_grid_view")
    assert hasattr(bpy.types.Scene, "chemblender_topology")
    assert hasattr(bpy.types.Scene, "chemblender_grid")
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
    assert not hasattr(bpy.types.Scene, "chemblender_topology")
    assert not hasattr(bpy.types.Scene, "chemblender_grid")
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
    import numpy

    ui = importlib.import_module(f"{module_key}.ui.session")
    core = importlib.import_module(f"{module_key}.core")
    links = importlib.import_module(f"{module_key}.project_link")
    views = importlib.import_module(f"{module_key}.views")
    scene = bpy.context.scene
    second_scene = bpy.data.scenes.new("ChemBlender shared session smoke")
    session = ui.new_scene_session(scene)
    assert ui.get_scene_session(second_scene) is session
    assert ui.get_scene_session(second_scene).project is session.project
    assert ui.get_scene_session(second_scene).temporary_root == session.temporary_root
    structure = core.Structure(
        id=uuid4(),
        revision="topology-ui-structure-r1",
        atomic_numbers=(8, 1, 1),
        coordinates=core.ArrayData(
            numpy.asarray(
                ((0.0, 0.0, 0.0), (0.96, 0.0, 0.0), (-0.24, 0.93, 0.0))
            ),
            ("atom", "xyz"),
            "angstrom",
        ),
    )
    session.project.commit(core.ImportBatch(structures=(structure,)))
    structure_obj = views.create_structure_view(
        structure,
        name="ChemBlender topology UI smoke",
        collection=scene.collection,
    )
    bpy.context.view_layer.objects.active = structure_obj
    structure_obj.select_set(True)
    session.active_entity_id = structure.id
    session.active_view_object_name = structure_obj.name
    assert bpy.ops.chemblender.compute_topology() == {"FINISHED"}
    topology_settings = scene.chemblender_topology
    topology_id = UUID(topology_settings.proposal_topology_id)
    topology = session.project.topologies[topology_id]
    assert topology.source_kind is core.TopologySource.DISTANCE_INFERRED
    assert bpy.ops.chemblender.accept_topology(
        topology_id=str(topology_id)
    ) == {"FINISHED"}
    assert len(structure_obj.data.edges) == 2
    assert structure_obj["cb_topology_id"] == str(topology_id)
    assert structure_obj["cb_topology_decision"] == "accepted"
    structure_revision = structure.revision
    assert bpy.ops.chemblender.switch_topology(
        atoms_only=True
    ) == {"FINISHED"}
    assert len(structure_obj.data.edges) == 0
    assert structure.revision == structure_revision
    assert topology_id in session.project.topologies
    assert bpy.ops.chemblender.switch_topology(
        topology_id=str(topology_id)
    ) == {"FINISHED"}
    assert len(structure_obj.data.edges) == 2
    assert bpy.ops.chemblender.reject_topology(
        topology_id=str(topology_id)
    ) == {"FINISHED"}
    assert len(structure_obj.data.edges) == 0
    assert topology_id in session.project.topologies
    assert bpy.ops.chemblender.accept_topology(
        topology_id=str(topology_id)
    ) == {"FINISHED"}
    atom_ids = [0] * 3
    structure_obj.data.attributes["cbq_atom_id"].data.foreach_get(
        "value", atom_ids
    )
    assert atom_ids == [0, 1, 2]
    topology_decisions = topology_settings.decisions_json
    grid = core.Grid3D(
        id=uuid4(),
        revision="topology-ui-grid-r1",
        semantic_role="electron_density",
        domain="grid",
        data=core.ArrayData(
            numpy.ones((1, 1, 1)),
            ("x", "y", "z"),
            "dimensionless",
        ),
        status=core.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        origin=(0.0, 0.0, 0.0),
        step_vectors=(
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ),
        coordinate_unit="angstrom",
        structure_id=structure.id,
    )
    session.project.commit(core.ImportBatch(datasets=(grid,)))
    session.mark_dirty("import")
    with TemporaryDirectory() as directory:
        scientific_edit = importlib.import_module(
            f"{module_key}.ui.scientific_edit"
        )
        structure_obj.location = (4.0, 5.0, 6.0)
        assert not scientific_edit.preview_structure_object_edits(
            session.project,
            structure_obj,
        ).has_changes
        structure_obj.data.vertices[1].co.x += 0.125
        structure_obj.data.update()
        edit_preview = scientific_edit.preview_structure_object_edits(
            session.project,
            structure_obj,
        )
        assert edit_preview.coordinate_change_count == 1
        assert edit_preview.affected_result_ids == (grid.id,)
        xyz_export = Path(directory) / "derived.xyz"
        assert bpy.ops.chemblender.apply_scientific_edits(
            export_xyz=True,
            export_path=str(xyz_export),
        ) == {"FINISHED"}
        derived_id = session.active_entity_id
        derived = session.project.structures[derived_id]
        derived_obj_name = session.active_view_object_name
        derived_obj = bpy.data.objects[derived_obj_name]
        derived_topology_id = UUID(derived_obj["cb_topology_id"])
        derived_topology = session.project.topologies[
            derived_topology_id
        ]
        assert derived_topology.source_kind is core.TopologySource.USER_EDITED
        assert derived_topology.structure_id == derived.id
        assert derived.topology_ids == (derived_topology.id,)
        assert numpy.allclose(
            structure.coordinates.values,
            ((0.0, 0.0, 0.0), (0.96, 0.0, 0.0), (-0.24, 0.93, 0.0)),
        )
        assert grid.structure_id == structure.id
        assert grid.id in session.project.datasets
        assert not any(
            getattr(dataset, "structure_id", None) == derived.id
            for dataset in session.project.datasets.values()
        )
        assert xyz_export.is_file()
        exported = core.parse_xyz(xyz_export).structures[0]
        assert exported.atomic_numbers == derived.atomic_numbers
        assert numpy.allclose(
            exported.coordinates.values,
            derived.coordinates.values,
            atol=1.0e-6,
        )
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
        sidecar = blend.with_suffix(".cbq")
        assert sidecar.is_dir()
        manifest_before = (sidecar / "manifest.json").read_bytes()
        assert bpy.ops.wm.save_mainfile() == {"FINISHED"}
        assert (sidecar / "manifest.json").read_bytes() == manifest_before
        third_scene = bpy.data.scenes.new(
            "ChemBlender link-only Scene smoke"
        )
        assert bpy.ops.wm.save_mainfile() == {"FINISHED"}
        assert (sidecar / "manifest.json").read_bytes() == manifest_before
        link_keys = (
            links.PROJECT_ID_KEY,
            links.PROJECT_SCHEMA_KEY,
            links.SIDECAR_LOCATOR_KEY,
            links.MANIFEST_HASH_KEY,
        )
        assert tuple(scene[key] for key in link_keys) == tuple(
            second_scene[key] for key in link_keys
        )
        assert tuple(scene[key] for key in link_keys) == tuple(
            third_scene[key] for key in link_keys
        )

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
        restored_obj = bpy.data.objects["ChemBlender topology UI smoke"]
        assert len(restored_obj.data.edges) == 2
        assert restored_obj["cb_topology_id"] == str(topology_id)
        assert restored_obj["cb_topology_revision"] == topology.revision
        assert topology_id in restored.project.topologies
        restored_derived = restored.project.structures[derived_id]
        assert restored_derived.revision == derived.revision
        restored_derived_obj = bpy.data.objects[derived_obj_name]
        assert restored_derived_obj["cb_structure_id"] == str(derived_id)
        assert (
            restored_derived_obj["cb_topology_id"]
            == str(derived_topology_id)
        )
        assert restored.project.datasets[grid.id].structure_id == structure.id
        assert (
            bpy.context.scene.chemblender_topology.decisions_json
            == topology_decisions
        )
        restored_scenes = tuple(bpy.data.scenes)
        assert len(restored_scenes) >= 2
        assert all(
            ui.get_scene_session(value) is restored
            for value in restored_scenes
        )
        assert len(
            {
                tuple(value[key] for key in link_keys)
                for value in restored_scenes
            }
        ) == 1
        assert ui.get_scene_session_status(bpy.context.scene)[0] == "connected"
        assert restored.sidecar_path == blend.with_suffix(".cbq")
        relinked_sidecar = Path(directory) / "relinked.cbq"
        core.save_project(relinked_sidecar, restored.project)
        relinked = core.relink_project_session_for_scenes(
            session=restored,
            scenes=restored_scenes,
            sidecar_path=relinked_sidecar,
            blend_path=blend,
        )
        assert relinked.status is core.ProjectServiceStatus.CONNECTED
        assert restored.sidecar_path == relinked_sidecar
        assert len(
            {
                tuple(value[key] for key in link_keys)
                for value in restored_scenes
            }
        ) == 1
        assert all(
            value[links.SIDECAR_LOCATOR_KEY] == "relinked.cbq"
            for value in restored_scenes
        )
        properties = importlib.import_module(f"{module_key}.ui.properties")
        assert properties.get_quick_import_state(restored).browser_revision == 1

        restored.mark_dirty("edit")
        verified_sidecar = restored.sidecar_path
        original_save = ui.save_project_session_for_scenes
        try:
            def fail_save(**_kwargs):
                raise RuntimeError("simulated sidecar failure")

            ui.save_project_session_for_scenes = fail_save
            ui._save_pre_handler(None)
        finally:
            ui.save_project_session_for_scenes = original_save
        assert restored.dirty
        assert restored.sidecar_path == verified_sidecar
        assert ui.get_scene_session_status(bpy.context.scene) == (
            "error",
            "simulated sidecar failure",
        )

        restored.mark_clean()
        conflicting = core.QCProject(id=uuid4(), schema_version="0.2")
        conflicting_sidecar = Path(directory) / "conflicting.cbq"
        core.save_project(conflicting_sidecar, conflicting)
        links.write_project_link(
            restored_scenes[1],
            conflicting,
            conflicting_sidecar,
            blend_path=blend,
        )
        save_pre_handlers = bpy.app.handlers.save_pre
        save_pre_index = save_pre_handlers.index(ui._save_pre_handler)
        save_pre_handlers.pop(save_pre_index)
        try:
            assert bpy.ops.wm.save_mainfile() == {"FINISHED"}
        finally:
            save_pre_handlers.insert(save_pre_index, ui._save_pre_handler)
        assert bpy.ops.wm.open_mainfile(filepath=str(blend)) == {"FINISHED"}
        ui = importlib.import_module(f"{module_key}.ui.session")
        conflicted_scenes = tuple(bpy.data.scenes)
        conflicted = ui.get_scene_session(conflicted_scenes[0])
        assert all(
            ui.get_scene_session(value) is conflicted
            for value in conflicted_scenes
        )
        assert ui.get_scene_session_status(conflicted_scenes[0]) == (
            "invalid",
            "conflicting scene project links",
        )
        assert conflicted.project.id not in {
            restored.project.id,
            conflicting.id,
        }

        temporary_root = conflicted.temporary_root
        ui.unregister()
        assert not temporary_root.exists()
        assert not any(
            getattr(handler, "__module__", None) == ui.__name__
            for callbacks in (bpy.app.handlers.load_post, bpy.app.handlers.save_pre)
            for handler in callbacks
        )


def assert_quick_import(module_key, repository_root):
    core = importlib.import_module(f"{module_key}.core")
    ui = importlib.import_module(f"{module_key}.ui.session")
    properties = importlib.import_module(f"{module_key}.ui.properties")
    preview_ui = importlib.import_module(
        f"{module_key}.ui.import_preview"
    )
    registry = importlib.import_module(
        f"{module_key}.runtime.reader_api_bridge"
    ).get_reader_plugin_registry()
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
            "INVOKE_DEFAULT",
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

    assert bpy.ops.chemblender.import_smiles_text(
        "EXEC_DEFAULT",
        smiles_text="C/C=C/C",
        validation_mode="balanced",
    ) == {"FINISHED"}
    state = properties.get_quick_import_state(session)
    smiles_rows = preview_ui.project_import_preview(session, state, registry)
    assert smiles_rows[0].reader_id == "smiles"
    assert smiles_rows[0].molecular_record_count == 1
    assert smiles_rows[0].molecular_version_summary == "SMILES: 1"
    assert bpy.ops.chemblender.cancel_import() == {"FINISHED"}

    for relative, expected_records, expected_summary in (
        ("tests/fixtures/mol/water-v3000.mol", 1, "V3000: 1"),
        ("tests/fixtures/sdf/malformed-middle.sdf", 2, "V2000: 2"),
        ("tests/fixtures/sdf/mixed-properties.sdf", 3, "V2000: 3"),
    ):
        state = stage(repository_root / relative)
        molecular_rows = preview_ui.project_import_preview(
            session,
            state,
            registry,
        )
        assert molecular_rows[0].molecular_record_count == expected_records
        assert molecular_rows[0].molecular_version_summary == expected_summary
        if "malformed-middle" in relative:
            assert "1 recovered record" in (
                molecular_rows[0].molecular_recovery_summary
            )
        if "mixed-properties" in relative:
            assert "typed columns" in (
                molecular_rows[0].molecular_property_summary
            )
        assert bpy.ops.chemblender.cancel_import() == {"FINISHED"}

    state = stage(repository_root / "tests/fixtures/sdf/records.sdf")
    molecular_rows = preview_ui.project_import_preview(
        session,
        state,
        registry,
    )
    conformer_rows = preview_ui.project_conformer_suggestions(state)
    assert len(conformer_rows) == 1
    conformer_rows[0].grouping_action = "accept_group"
    conformer_rows[0].review_confirmed = conformer_rows[0].requires_review
    molecular_result = preview_ui.commit_project_import(
        session,
        state,
        molecular_rows,
        conformer_rows=conformer_rows,
        collection=bpy.context.scene.collection,
    )
    conformer_set = next(
        dataset
        for dataset in session.project.datasets.values()
        if type(dataset).__name__ == "ConformerSet"
    )
    browser = importlib.import_module(
        f"{module_key}.ui.project_browser.panel"
    )
    browser_rows = browser.refresh_project_browser(bpy.context.scene)
    assert sum(row.kind == "molecular_record" for row in browser_rows) >= 2
    assert any(row.entity_id == conformer_set.id for row in browser_rows)
    with TemporaryDirectory() as directory:
        exported = Path(directory) / "conformers.sdf"
        session.active_entity_id = conformer_set.id
        assert bpy.ops.chemblender.export_project_entity(
            filepath=str(exported),
            format_name="sdf",
            confirm_loss=True,
        ) == {"FINISHED"}
        reparsed = core.SDF_READER.parse(exported)
        assert len(reparsed.molecular_records) == 2
    assert molecular_result.status == "committed"

    cjson_source = repository_root / "tests/fixtures/cjson/water-results.cjson"
    state = stage(cjson_source)
    cjson_rows = preview_ui.project_import_preview(session, state, registry)
    assert cjson_rows[0].default_view_label == "Default view: Structure"
    cjson_batch = state.staging_session.result(
        state.preview.source_previews[0].staged_batch_ids[0]
    )
    cjson_structure, = cjson_batch.structures
    cjson_topology, = cjson_batch.topologies
    assert cjson_structure.topology is None
    assert cjson_structure.topology_ids == (cjson_topology.id,)
    source_revisions = set(session.project.source_revisions)
    assert bpy.ops.chemblender.confirm_import() == {"FINISHED"}
    cjson_revision_id, = set(session.project.source_revisions) - source_revisions
    cjson_revision = session.project.source_revisions[cjson_revision_id]
    cjson_structure = next(
        session.project.structures[entity_id]
        for entity_id in cjson_revision.created_entity_ids
        if entity_id in session.project.structures
    )
    assert cjson_structure.topology is None
    topology_id, = cjson_structure.topology_ids
    assert topology_id == cjson_topology.id
    topology = session.project.topologies[topology_id]
    topology_ui = importlib.import_module(f"{module_key}.ui.topology")
    choices = topology_ui.topology_choices(session.project, cjson_structure.id)
    assert tuple(choice.topology_id for choice in choices) == (topology_id,)
    assert topology.source_kind is core.TopologySource.EXPLICIT_FILE
    assert topology.quality_status is core.QualityStatus.COMPLETE
    views = importlib.import_module(f"{module_key}.views")
    cjson_view = views.create_structure_view(
        cjson_structure,
        topology,
        name="ChemBlender immediate CJSON topology smoke",
        collection=bpy.context.scene.collection,
    )
    try:
        assert cjson_view["cb_topology_id"] == str(topology_id)
        assert len(cjson_view.data.edges) == topology.bond_indices.shape[0]
    finally:
        views.remove_structure_view(cjson_view)

    state = stage(repository_root / "tests/fixtures/xyz/water.xyz")
    xyz_rows = preview_ui.project_import_preview(
        session,
        state,
        registry,
    )
    assert xyz_rows[0].default_view_label == "Default view: Structure"
    revision = state.browser_revision
    structure_count = len(session.project.structures)
    source_revisions = set(session.project.source_revisions)
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
    xyz_revision_id, = set(session.project.source_revisions) - source_revisions
    xyz_revision = session.project.source_revisions[xyz_revision_id]
    xyz_structure = next(
        session.project.structures[entity_id]
        for entity_id in xyz_revision.created_entity_ids
        if entity_id in session.project.structures
    )
    xyz_view = next(
        obj
        for obj in structure_views
        if obj.get("cb_structure_id") == str(xyz_structure.id)
    )
    assert xyz_view.type == "MESH"
    assert xyz_view["cb_structure_revision"] == xyz_structure.revision
    xyz_bindings = json.loads(xyz_view["cb_scene_bindings_json"])
    assert xyz_bindings["structure"] == {
        "entity_id": str(xyz_structure.id),
        "revision": xyz_structure.revision,
    }
    browser = importlib.import_module(
        f"{module_key}.ui.project_browser.panel"
    )
    switched_scene = bpy.data.scenes.new(
        "ChemBlender Quick Import shared session smoke"
    )
    switched_session = ui.get_scene_session(switched_scene)
    assert switched_session is session
    assert len(switched_session.project.structures) == structure_count + 1
    switched_rows = browser.refresh_project_browser(switched_scene)
    assert any(row.kind == "structure" for row in switched_rows)
    browser_settings = bpy.context.scene.chemblender_project_browser
    browser_settings.mode = "by_source"
    rows_before_cube = browser.refresh_project_browser(bpy.context.scene)
    assert any(row.kind == "structure" for row in rows_before_cube)

    duplicate_source = repository_root / "tests/fixtures/xyz/water.xyz"
    state = stage(duplicate_source)
    duplicate_rows = preview_ui.project_import_preview(
        session,
        state,
        registry,
    )
    assert len(duplicate_rows[0].conflict_candidates) == 1
    assert duplicate_rows[0].conflict_candidates[0].selected
    duplicate_rows[0].conflict_action = "independent_copy"
    preview_ui.commit_project_import(
        session,
        state,
        duplicate_rows,
        collection=bpy.context.scene.collection,
        apply_view=lambda *_args, **_kwargs: (),
    )

    state = stage(duplicate_source)
    target_rows = preview_ui.project_import_preview(
        session,
        state,
        registry,
    )
    target_row = target_rows[0]
    conflict = state.conflicts[0]
    assert len(target_row.conflict_candidates) == 2
    assert not any(
        candidate.selected
        for candidate in target_row.conflict_candidates
    )
    try:
        preview_ui.import_commit_decisions(
            state,
            target_rows,
            project_session=session,
        )
    except ValueError as error:
        assert "select exactly one conflict target" in str(error)
    else:
        raise AssertionError("ambiguous conflict target must fail")
    for selected_index, expected in enumerate(conflict.candidates):
        for index, candidate in enumerate(target_row.conflict_candidates):
            candidate.selected = index == selected_index
        decisions = preview_ui.import_commit_decisions(
            state,
            target_rows,
            project_session=session,
        )
        assert (
            decisions.conflict_decisions[
                conflict.id
            ].existing_revision_id
            == expected.revision_id
        )
    forged = replace(
        target_row,
        conflict_candidates=(
            replace(
                target_row.conflict_candidates[0],
                revision_id=str(uuid4()),
                selected=True,
            ),
            replace(
                target_row.conflict_candidates[1],
                selected=False,
            ),
        ),
    )
    try:
        preview_ui.import_commit_decisions(
            state,
            (forged,),
            project_session=session,
        )
    except ValueError as error:
        assert "conflict target is not allowed" in str(error)
    else:
        raise AssertionError("unknown conflict target must fail")
    preview_ui.cancel_project_import(session)

    state = stage(repository_root / "tests/fixtures/cube/sheared.cube")
    cube_rows = preview_ui.project_import_preview(
        session,
        state,
        registry,
    )
    assert cube_rows[0].default_view_label == "Default view: Grid Volume"
    assert cube_rows[0].grid_dataset_count == 1
    assert cube_rows[0].grid_shape == "2 × 2 × 2"
    assert cube_rows[0].grid_coordinate_unit == "bohr"
    assert cube_rows[0].grid_quality == "ambiguous"
    structure_count = len(session.project.structures)
    source_revisions = set(session.project.source_revisions)
    objects_before_cube = set(bpy.data.objects)
    assert bpy.ops.chemblender.confirm_import() == {"FINISHED"}
    assert len(session.project.structures) == structure_count + 1
    assert state.preview is None
    cube_revision_id, = set(session.project.source_revisions) - source_revisions
    cube_revision = session.project.source_revisions[cube_revision_id]
    cube_structure = next(
        session.project.structures[entity_id]
        for entity_id in cube_revision.created_entity_ids
        if entity_id in session.project.structures
    )
    cube_grid = next(
        session.project.datasets[entity_id]
        for entity_id in cube_revision.created_entity_ids
        if entity_id in session.project.datasets
    )
    assert cube_grid.structure_id == cube_structure.id
    assert cube_grid.status is core.DatasetStatus.AMBIGUOUS
    cube_objects = set(bpy.data.objects) - objects_before_cube
    cube_view, = cube_objects
    assert cube_view.type == "VOLUME"
    assert cube_view["cb_scene_preset_id"] == "grid_volume"
    assert cube_view["cb_dataset_id"] == str(cube_grid.id)
    assert cube_view["cb_dataset_revision"] == cube_grid.revision
    assert cube_view["cb_structure_id"] == str(cube_structure.id)
    assert cube_view["cb_scene_render_identity"]
    cube_bindings = json.loads(cube_view["cb_scene_bindings_json"])
    assert cube_bindings["grid"] == {
        "entity_id": str(cube_grid.id),
        "revision": cube_grid.revision,
    }
    cube_cache = Path(cube_view["cb_cache_path"]).resolve()
    session_root = Path(session.temporary_root).resolve()
    assert cube_cache.is_relative_to(session_root)
    assert cube_cache.parent == session_root / "view-cache" / "volume"
    assert cube_cache.is_file()
    session.active_entity_id = cube_grid.id
    grid_settings = bpy.context.scene.chemblender_grid
    grid_settings.dataset_index = 0
    grid_settings.preset_id = "generic_scalar"
    grid_settings.value_unit = "dimensionless"
    assert bpy.ops.chemblender.resolve_grid_semantics() == {"FINISHED"}
    resolved_grid = session.project.datasets[session.active_entity_id]
    assert resolved_grid.id != cube_grid.id
    assert resolved_grid.status is core.DatasetStatus.COMPLETE
    assert resolved_grid.semantic_role == "scalar_field"
    assert session.project.datasets[cube_grid.id] is cube_grid
    objects_before_surface = set(bpy.data.objects)
    assert bpy.ops.chemblender.create_grid_view(
        mode="signed_surface"
    ) == {"FINISHED"}
    cube_surface_objects = tuple(
        set(bpy.data.objects) - objects_before_surface
    )
    assert len(cube_surface_objects) == 2
    assert {
        obj["cb_surface_phase"] for obj in cube_surface_objects
    } == {"positive", "negative"}
    for obj in cube_surface_objects:
        assert obj["cb_dataset_id"] == str(resolved_grid.id)
        assert obj["cb_dataset_revision"] == resolved_grid.revision
        assert obj["cb_dataset_index"] == 0
        assert obj["cb_view_quality"] == "complete"
        assert obj["cb_report_eligible"]
        assert json.loads(obj["cb_scene_bindings_json"])["grid"] == {
            "entity_id": str(resolved_grid.id),
            "revision": resolved_grid.revision,
        }
    browser_settings.mode = "by_data"
    rows_after_cube = browser.refresh_project_browser(bpy.context.scene)
    assert browser_settings.quality_filter == "all"
    assert rows_after_cube is not rows_before_cube
    assert any(row.kind == "structure" for row in rows_after_cube)
    assert any(row.kind == "grid3d" for row in rows_after_cube)
    grid_row = next(
        row
        for row in rows_after_cube
        if row.entity_id == cube_grid.id
    )
    assert grid_row.view_count == 1
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
        projected_rows = preview_ui.project_import_preview(
            session,
            state,
            registry,
        )
        grouping_rows = preview_ui.project_grouping_suggestions(state)
        assert len(grouping_rows) == 1
        assert grouping_rows[0].grouping_action == "keep_independent"
        assert (
            preview_ui.import_commit_decisions(
                state,
                projected_rows,
                grouping_rows=grouping_rows,
                project_session=session,
            ).grouping_decisions
            == ()
        )
        group_count = len(session.project.calculation_groups)
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
        assert len(session.project.calculation_groups) == group_count

        third = directory / "third.xyz"
        fourth = directory / "fourth.xyz"
        third.write_text(
            "1\nthird\nH 0.3 0 0\n",
            encoding="utf-8",
        )
        fourth.write_text(
            "1\nfourth\nH 0.4 0 0\n",
            encoding="utf-8",
        )
        state = stage(third, fourth)
        projected_rows = preview_ui.project_import_preview(
            session,
            state,
            registry,
        )
        grouping_rows = preview_ui.project_grouping_suggestions(state)
        assert len(grouping_rows) == 1
        grouping_rows[0].grouping_action = "accept_group"
        selected_evidence_ids = tuple(
            UUID(item.evidence_id)
            for item in grouping_rows[0].evidence
            if item.selected
        )
        accepted = preview_ui.commit_project_import(
            session,
            state,
            projected_rows,
            grouping_rows=grouping_rows,
            collection=bpy.context.scene.collection,
            apply_view=lambda *_args, **_kwargs: (),
        )
        assert len(accepted.commit_result.calculation_group_ids) == 1
        assert len(session.project.calculation_groups) == group_count + 1
        accepted_group = session.project.calculation_groups[
            accepted.commit_result.calculation_group_ids[0]
        ]
        assert accepted_group.evidence_ids == tuple(
            sorted(selected_evidence_ids, key=str)
        )
        reopened = core.open_project(accepted.commit_result.sidecar_path)
        try:
            assert (
                reopened.calculation_groups
                == session.project.calculation_groups
            )
        finally:
            core.close_project(reopened)
    cube_volume = cube_view.data
    bpy.data.objects.remove(cube_view, do_unlink=True)
    if cube_volume.users == 0:
        bpy.data.volumes.remove(cube_volume)
    surface_view = importlib.import_module(f"{module_key}.surface_view")
    for obj in cube_surface_objects:
        surface_view.remove_surface_object(obj)
    bpy.data.scenes.remove(switched_scene)


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
            stable_mtime = cache.stat().st_mtime_ns
            assert adapter.ensure_grid_volume_cache(grid, cache) == cache
            assert cache.stat().st_mtime_ns == stable_mtime
            cache.write_bytes(b"corrupt VDB")
            assert adapter.ensure_grid_volume_cache(grid, cache) == cache
            assert openvdb.read(str(cache), "density").getAccessor().getValue(
                (1, 0, 1)
            ) == 5.0
            cache.unlink()
            assert adapter.ensure_grid_volume_cache(grid, cache) == cache
            assert openvdb.read(str(cache), "density").getAccessor().getValue(
                (1, 0, 1)
            ) == 5.0

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
    import warnings

    core = importlib.import_module(f"{module_key}.core")
    adapter = importlib.import_module(f"{module_key}.dataset_view")
    trajectory = importlib.import_module(f"{module_key}.trajectory_view")
    views = importlib.import_module(f"{module_key}.views")
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
    topology = core.TopologyRecord(
        id=uuid4(),
        revision="topology-revision",
        structure_id=structure_id,
        bond_indices=core.ArrayData(
            numpy.asarray([[0, 1], [0, 2]]),
            ("bond", "endpoint"),
            "dimensionless",
        ),
        bond_orders=core.ArrayData(
            numpy.asarray([1.0, 1.0]), ("bond",), "dimensionless"
        ),
        aromatic_flags=core.ArrayData(
            numpy.asarray([False, False]), ("bond",), "dimensionless"
        ),
        stereo_labels=("", ""),
        source_kind=core.TopologySource.EXPLICIT_FILE,
        quality_status=core.QualityStatus.COMPLETE,
        inference_parameters=(),
        provenance_ids=(),
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        obj = adapter.create_structure_view(
            structure,
            topology,
            name="ChemBlender dataset smoke",
            collection=bpy.context.scene.collection,
        )
    assert len(caught) == 1
    assert issubclass(caught[0].category, DeprecationWarning)
    mesh = obj.data
    try:
        assert obj["cb_structure_id"] == str(structure_id)
        assert obj["cb_topology_id"] == str(topology.id)
        assert obj["cbq_topology_source"] == "explicit_file"
        assert len(mesh.edges) == 2
        atom_ids = [0] * 3
        obj.data.attributes["cbq_atom_id"].data.foreach_get("value", atom_ids)
        assert atom_ids == [0, 1, 2]
        bond_ids = [0] * 2
        obj.data.attributes["cbq_bond_id"].data.foreach_get("value", bond_ids)
        assert bond_ids == [0, 1]
        exact_orders = [0.0] * 2
        obj.data.attributes["cbq_bond_order"].data.foreach_get(
            "value", exact_orders
        )
        assert exact_orders == [1.0, 1.0]
        ball_stick = [
            item
            for item in obj.modifiers
            if item.get("cbq_contract") == "structure_ball_stick_v1"
        ]
        assert len(ball_stick) == 1
        assert ball_stick[0]["cbq_contract_version"] == 1
        assert ball_stick[0].node_group["cbq_contract_version"] == 1
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
        assert len(obj.modifiers) == 2
        assert tuple(obj.modifiers)[0] == modifier
        adapter.apply_atomic_vector(obj, vector, display_scale=1.0)
        assert len(obj.modifiers) == 2
        bpy.context.view_layer.update()
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        evaluated_geometry = evaluated.evaluated_geometry()
        assert len(evaluated_geometry.instance_references()) >= 1
        assert len(evaluated_geometry.instances_pointcloud().points) >= 3

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
        frame_force = core.AtomFrameProperty(
            id=uuid4(),
            revision="trajectory-force-revision",
            semantic_role="atomic_force",
            domain="atom_frame",
            data=core.ArrayData(
                numpy.asarray(
                    [
                        [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 3.0]],
                        [[4.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 6.0]],
                    ]
                ),
                ("frame", "atom", "xyz"),
                "electron_volt_per_angstrom",
            ),
            status=core.DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            frame_set_id=frames.id,
        )
        project = core.QCProject(uuid4(), "0.2")
        project.commit(
            core.ImportBatch(
                structures=(structure,),
                datasets=(frames, frame_force),
            )
        )
        browser = importlib.import_module(
            f"{module_key}.ui.project_browser.panel"
        )
        force_structure, selected_force, values = (
            browser.atom_frame_vector(project, frame_force.id, 1)
        )
        assert force_structure is structure
        adapter.write_vector_view(
            obj,
            values,
            dataset_id=selected_force.id,
            revision=selected_force.revision,
            semantic_role=selected_force.semantic_role,
            unit=selected_force.data.unit,
            display_scale=0.5,
        )
        vector_values = [0.0] * 9
        obj.data.attributes["cbq_vector"].data.foreach_get(
            "vector", vector_values
        )
        assert vector_values == [2.0, 0.0, 0.0, 0.0, 2.5, 0.0, 0.0, 0.0, 3.0]
        bpy.context.scene.frame_set(100)
        assert obj["cb_trajectory_frame_index"] == 1
        assert len(bpy.data.objects) >= 1
        trajectory.clear_trajectory_view(obj)
    finally:
        bpy.context.scene.frame_set(1)
        if obj.name in bpy.data.objects:
            views.remove_structure_view(obj)


def assert_unwrapped_periodic_inference_view(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    views = importlib.import_module(f"{module_key}.views")
    structure_id = uuid4()
    structure = core.Structure(
        id=structure_id,
        revision="periodic-structure-revision",
        atomic_numbers=(14, 14),
        coordinates=core.ArrayData(
            numpy.asarray([[0.1, 0.0, 0.0], [3.8, 0.0, 0.0]]),
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=core.ArrayData(
            numpy.asarray([[4.0, 0.0, 0.0], [1.0, 3.0, 0.0], [0.0, 0.5, 5.0]]),
            ("cell_vector", "xyz"),
            "angstrom",
        ),
        periodic=core.PeriodicSiteData(
            fractional_coordinates=core.ArrayData(
                numpy.asarray([[0.025, 0.0, 0.0], [0.95, 0.0, 0.0]]),
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=("Si1", "Si2"),
            occupancies=core.ArrayData(
                numpy.ones(2), ("atom",), "dimensionless"
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none", "none"),
            disorder_groups=(0, 0),
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=(),
            cif_envelope_id=None,
            pbc=(True, False, True),
        ),
    )
    unwrapped = replace(
        structure,
        coordinates=core.ArrayData(
            numpy.asarray([[0.1, 0.0, 0.0], [11.8, 0.0, 0.0]]),
            ("atom", "xyz"),
            "angstrom",
        ),
        periodic=replace(
            structure.periodic,
            fractional_coordinates=core.ArrayData(
                numpy.asarray([[0.025, 0.0, 0.0], [2.95, 0.0, 0.0]]),
                ("atom", "xyz"),
                "dimensionless",
            ),
        ),
    )
    infer_periodic_topology = importlib.import_module(
        f"{module_key}.core.topology.periodic"
    ).infer_periodic_topology
    reference_topology, = infer_periodic_topology(structure).topologies
    topology, = infer_periodic_topology(unwrapped).topologies
    assert topology.id == reference_topology.id
    assert topology.revision == reference_topology.revision
    assert topology.bond_indices.values.tolist() == [[0, 1]]
    assert topology.bond_lattice_shifts.values.tolist() == [[-1, 0, 0]]
    assert (
        "fractional_normalization",
        "cartesian_pbc_modulo_one",
    ) in topology.inference_parameters
    obj = views.create_structure_view(
        unwrapped,
        topology,
        name="ChemBlender periodic structure smoke",
        collection=bpy.context.scene.collection,
    )
    try:
        assert len(obj.data.vertices) == 2
        assert len(obj.data.edges) == 0
        assert numpy.allclose(obj.data.vertices[1].co, (11.8, 0.0, 0.0))
        assert obj["cb_periodic"] is True
        assert list(obj["cb_pbc"]) == [True, False, True]
        assert numpy.allclose(
            list(obj["cb_periodic_cell"]),
            [4.0, 0.0, 0.0, 1.0, 3.0, 0.0, 0.0, 0.5, 5.0],
        )
        display = bpy.data.objects[obj["cb_periodic_display_object"]]
        assert display["cb_structure_contract"] == "structure_periodic_display_v1"
        assert len(display.data.vertices) == 2
        assert len(display.data.edges) == 1
        segment = numpy.asarray(
            [tuple(vertex.co) for vertex in display.data.vertices]
        )
        assert numpy.allclose(segment, ((0.1, 0.0, 0.0), (-0.2, 0.0, 0.0)))
        assert numpy.isclose(numpy.linalg.norm(segment[1] - segment[0]), 0.3)
        assert obj["cb_periodic_display_bond_count"] == 1
        assert any(
            item.get("cbq_contract") == "structure_periodic_display_v1"
            for item in obj.modifiers
        )
        bpy.context.view_layer.update()
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        assert evaluated.evaluated_geometry() is not None
    finally:
        views.remove_structure_view(obj)


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
    import openvdb

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
            assert all(obj["cb_view_quality"] == "complete" for obj in signed_objects)
            assert all(obj["cb_report_eligible"] for obj in signed_objects)
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
            assert property_obj["cb_view_quality"] == "complete"
            assert property_obj["cb_report_eligible"]
            assert property_obj["cb_surface_dataset_id"] == str(density_grid.id)
            assert property_obj["cb_surface_dataset_revision"] == density_grid.revision
            assert property_obj["cb_surface_dataset_index"] == 0
            assert property_obj["cb_surface_semantic_role"] == density_grid.semantic_role
            assert property_obj["cb_surface_unit"] == density_grid.data.unit
            assert property_obj["cb_property_dataset_id"] == str(property_grid.id)
            assert property_obj["cb_property_dataset_revision"] == property_grid.revision
            assert property_obj["cb_property_dataset_index"] == 0
            assert property_obj["cb_property_semantic_role"] == property_grid.semantic_role
            assert property_obj["cb_property_unit"] == property_grid.data.unit
            assert property_obj["cb_scene_render_identity"] == property_plan.render_identity
            assert all(
                obj["cb_cache_format_version"] == 1
                for obj in (*signed_objects, property_obj)
            )
            assert len(list(Path(cache_root).glob("surface/*.vdb"))) == 3

            ambiguous_grid = replace(
                signed_grid,
                id=uuid4(),
                revision="ambiguous-grid-r1",
                semantic_role="scalar_field",
                data=replace(signed_grid.data, unit="unknown"),
                status=core.DatasetStatus.AMBIGUOUS,
            )
            grid_project.commit(core.ImportBatch(datasets=(ambiguous_grid,)))
            ambiguous_plan = core.plan_scene_preset(
                presets["signed_isosurface"],
                grid_project,
                {"grid": ambiguous_grid.id},
                {"isovalue": 0.5},
            )
            ambiguous_objects = view.apply_scene_preset(
                ambiguous_plan,
                grid_project,
                cache_root=Path(cache_root) / "preview",
                collection=bpy.context.scene.collection,
            )
            try:
                assert all(
                    obj["cb_view_quality"] == "ambiguous"
                    and not obj["cb_report_eligible"]
                    for obj in ambiguous_objects
                )
                browser = importlib.import_module(
                    f"{module_key}.ui.project_browser.panel"
                )
                records = tuple(
                    record
                    for record in browser.presentation_view_records(
                        bpy.context.scene
                    )
                    if record.object_name
                    in {obj.name for obj in ambiguous_objects}
                )
                assert records
                assert all(
                    record.quality == "ambiguous"
                    and not record.report_eligible
                    for record in records
                )
            finally:
                for obj in ambiguous_objects:
                    surface_view.remove_surface_object(obj)

            view_cache = importlib.import_module(f"{module_key}.ui.view_cache")
            sidecar = Path(cache_root) / "durable.cbq"
            sidecar.mkdir()
            session_root = Path(cache_root) / "session"
            session_root.mkdir()
            session = core.ProjectSession(
                uuid4(),
                grid_project,
                session_root,
                sidecar_path=sidecar,
                link_status="connected",
            )
            object_count = len(bpy.data.objects)
            assert view_cache.repair_project_view_caches(
                session=session,
                objects=(*signed_objects, property_obj),
                blend_path=Path(cache_root) / "durable.blend",
            ) == 3
            assert len(bpy.data.objects) == object_count
            assert all(
                obj.data.filepath.startswith("//durable.cbq/cache/render/surface/")
                for obj in (*signed_objects, property_obj)
            )
            durable_files = sorted(
                (sidecar / "cache" / "render" / "surface").glob("*.vdb")
            )
            assert len(durable_files) == 3
            durable_files[0].write_bytes(b"corrupt VDB")
            assert view_cache.repair_project_view_caches(
                session=session,
                objects=(*signed_objects, property_obj),
                blend_path=Path(cache_root) / "durable.blend",
            ) == 3
            assert len(openvdb.readAll(str(durable_files[0]))[0]) in {1, 2}
            cleared = core.clear_derived_cache(sidecar_path=sidecar)
            assert cleared.complete
            assert sidecar / "cache" / "render" in cleared.removed_paths
            session.mark_dirty("view_cache")
            assert view_cache.repair_project_view_caches(
                session=session,
                objects=(*signed_objects, property_obj),
                blend_path=Path(cache_root) / "durable.blend",
            ) == 3
            assert len(
                list((sidecar / "cache" / "render" / "surface").glob("*.vdb"))
            ) == 3
            save_as_sidecar = Path(cache_root) / "save-as.cbq"
            save_as_sidecar.mkdir()
            session.sidecar_path = save_as_sidecar
            assert view_cache.repair_project_view_caches(
                session=session,
                objects=(*signed_objects, property_obj),
                blend_path=Path(cache_root) / "save-as.blend",
            ) == 3
            assert all(
                obj.data.filepath.startswith("//save-as.cbq/cache/render/surface/")
                for obj in (*signed_objects, property_obj)
            )

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
    views = importlib.import_module(f"{module_key}.views")
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
        views.remove_structure_view(obj)


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


def assert_extxyz_workflow(module_key, repository_root):
    core = importlib.import_module(f"{module_key}.core")
    formats = importlib.import_module(
        f"{module_key}.core.formats.extxyz"
    )
    exporters = importlib.import_module(
        f"{module_key}.core.exporters"
    )
    export_ui = importlib.import_module(f"{module_key}.ui.export")
    preview_ui = importlib.import_module(
        f"{module_key}.ui.import_preview"
    )
    browser_model = importlib.import_module(
        f"{module_key}.ui.project_browser.model"
    )
    ordinary = core.parse_xyz(
        repository_root / "tests" / "fixtures" / "xyz" / "water.xyz"
    )
    assert len(ordinary.structures) == 1

    source_text = (
        "2\n"
        'Lattice="4 0 0 0 4 0 0 0 4" '
        "Properties=species:S:1:pos:R:3:force:R:3:"
        'custom:R:1:flag:L:1:label:S:1 pbc="T F T" energy=-1.0\n'
        "C 0 0 0 1 0 0 2.5 T donor\n"
        "H 1 0 0 0 1 0 3.5 F acceptor\n"
        "2\n"
        'Lattice="5 0 0 0 5 0 0 0 5" '
        "Properties=species:S:1:pos:R:3:"
        'custom:R:1:flag:L:1:label:S:1 pbc="F F F" energy=-0.5\n'
        "C 0.1 0 0 4.5 F donor\n"
        "H 1.1 0 0 5.5 T acceptor\n"
    )
    with TemporaryDirectory(prefix="chemblender-extxyz-smoke-") as directory:
        root = Path(directory)
        source = root / "trajectory.extxyz"
        source.write_text(source_text, encoding="utf-8")
        batch = formats.parse_extxyz(source)
        structure, = batch.structures
        frame_set = next(
            item
            for item in batch.datasets
            if isinstance(item, core.FrameSet)
        )
        force = next(
            item
            for item in batch.datasets
            if isinstance(item, core.AtomFrameProperty)
            and item.semantic_role == "atomic_force"
        )
        assert frame_set.data.shape == (2, 2, 3)
        assert force.status is core.DatasetStatus.PARTIAL
        assert any(
            isinstance(item, core.CellFrameProperty)
            for item in batch.datasets
        )
        pbc = next(
            item
            for item in batch.datasets
            if isinstance(item, core.FrameProperty)
            and item.semantic_role == "pbc"
        )
        assert tuple(map(tuple, pbc.data.values)) == (
            (True, False, True),
            (False, False, False),
        )
        for role in ("custom", "flag", "label"):
            item = next(
                value
                for value in batch.datasets
                if value.semantic_role == role
            )
            assert item.status is core.DatasetStatus.AMBIGUOUS

        summary = preview_ui.extxyz_preview_summary(batch)
        assert summary.frame_count == 2
        assert "atomic_force" in summary.atom_properties
        assert summary.has_lattice
        assert summary.assumed_units

        project = core.QCProject(uuid4(), "0.2")
        project.commit(batch)
        rows = browser_model.build_browser_rows(
            project,
            mode=browser_model.BrowserMode.BY_DATA,
            browser_revision=1,
        )
        frame_row = next(row for row in rows if row.entity_id == frame_set.id)
        force_row = next(row for row in rows if row.entity_id == force.id)
        assert force_row.parent_id == frame_row.id

        selection = export_ui.resolve_export_selection(
            project,
            frame_set.id,
        )
        preview = export_ui.preview_export_selection(
            selection,
            "extxyz",
        )
        assert preview.requires_confirmation
        destination = root / "trajectory-export.extxyz"
        job = export_ui.ExportJob(
            destination,
            selection,
            format_name="extxyz",
            confirm_loss=True,
            missing_value_token=None,
        )
        job.start()
        assert job.join(30)
        assert job.error is None
        assert job.result.written
        reparsed = formats.parse_extxyz(destination)
        assert exporters.semantic_extxyz_differences(batch, reparsed) == ()

        xyz_destination = root / "structure.xyz"
        xyz_job = export_ui.ExportJob(
            xyz_destination,
            export_ui.resolve_export_selection(project, structure.id),
            format_name="xyz",
            confirm_loss=False,
            missing_value_token=None,
        )
        xyz_job.start()
        assert xyz_job.join(30)
        assert xyz_job.error is None
        assert xyz_job.result.written
        assert len(core.parse_xyz(xyz_destination).structures) == 1

        sidecar = root / "trajectory.cbq"
        core.save_project(sidecar, project)
        reopened = core.open_project(sidecar)
        try:
            assert frame_set.id in reopened.datasets
            assert force.id in reopened.datasets
        finally:
            core.close_project(reopened)


def assert_cif_workflow(module_key, repository_root):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    export_ui = importlib.import_module(f"{module_key}.ui.export")
    node_module = importlib.import_module(f"{module_key}.node")
    ui = importlib.import_module(f"{module_key}.ui.session")
    views = importlib.import_module(f"{module_key}.views")
    assert "spglib" not in sys.modules

    batch = core.parse_cif(
        repository_root / "tests" / "fixtures" / "cif" / "partial-disorder.cif"
    )
    structure, = batch.structures
    assert structure.periodic is not None
    assert tuple(structure.periodic.occupancies.values) == (0.5,)
    session = ui.new_scene_session(bpy.context.scene)
    session.project.commit(batch)
    session.mark_dirty("import")
    view = views.create_periodic_structure_view(
        structure,
        settings=views.PeriodicViewSettings(
            representation="supercell",
            supercell=(2, 1, 1),
        ),
        name="ChemBlender CIF smoke",
        collection=bpy.context.scene.collection,
    )
    assert len(view.data.vertices) == len(structure.atomic_numbers)
    assert view["cbq_periodic_representation"] == "supercell"
    assert tuple(view["cbq_periodic_supercell"]) == (2, 1, 1)
    derived = bpy.data.objects[view["cbq_periodic_site_display_object"]]
    assert derived["cbq_contract"] == "structure_periodic_sites_v1"
    assert len(derived.data.vertices) == view["cbq_periodic_derived_site_count"]
    assert len(derived.data.vertices) > 0
    assert derived.data.attributes["cbq_display_only"] is not None
    derived_ball_stick, = derived.modifiers
    assert derived_ball_stick["cbq_contract_version"] == 1
    assert derived_ball_stick.node_group["cbq_contract_version"] == 1
    for name, contract in (
        (
            "CH_添加分子属性" if node_module.language
            else "CH_Add Attributes",
            "legacy_atom_attributes_asset_v1",
        ),
        (
            "CH_分子球棍模型" if node_module.language
            else "CH_Ball and Stick",
            "legacy_ball_stick_asset_v1",
        ),
        (
            "CH_添加分子材质" if node_module.language
            else "CH_Add Material",
            "legacy_molecule_material_asset_v1",
        ),
    ):
        assert bpy.data.node_groups[name]["cbq_contract"] == contract
        assert bpy.data.node_groups[name]["cbq_contract_version"] == 1
    occupancy = [0.0] * len(structure.atomic_numbers)
    view.data.attributes["cbq_occupancy"].data.foreach_get("value", occupancy)
    assert occupancy == [0.5]
    cell_display = bpy.data.objects[view["cbq_periodic_cell_object"]]
    adp_display = bpy.data.objects[view["cbq_periodic_adp_object"]]
    occupancy_display = bpy.data.objects[
        view["cbq_periodic_occupancy_object"]
    ]
    for display, contract in (
        (cell_display, "periodic_cell_edges_v1"),
        (adp_display, "periodic_thermal_ellipsoid_v1"),
        (occupancy_display, "periodic_site_occupancy_v1"),
    ):
        modifier, = display.modifiers
        assert modifier["cbq_contract"] == contract
        assert modifier["cbq_contract_version"] == 1
        assert modifier.node_group["cbq_contract"] == contract
        assert modifier.node_group["cbq_contract_version"] == 1
        evaluated = display.evaluated_get(
            bpy.context.evaluated_depsgraph_get()
        )
        evaluated_mesh = evaluated.to_mesh()
        try:
            assert len(evaluated_mesh.vertices) > 0, (
                display.name,
                contract,
                len(evaluated_mesh.vertices),
            )
        finally:
            evaluated.to_mesh_clear()
    for attribute in (
        "siteid",
        "cbq_site_label",
        "cbq_disorder_group",
        "cbq_disorder_assembly",
        "cbq_adp_type",
        "cbq_u_iso",
        "cbq_u11",
        "cbq_u22",
        "cbq_u33",
        "cbq_u12",
        "cbq_u13",
        "cbq_u23",
    ):
        assert view.data.attributes[attribute] is not None
    session.active_entity_id = structure.id
    session.active_view_object_name = view.name

    standard = replace(
        structure,
        id=uuid4(),
        revision=f"{structure.revision}-standard-smoke",
        topology_ids=(),
    )
    symmetry = object.__new__(core.SymmetryResult)
    object.__setattr__(symmetry, "id", uuid4())
    object.__setattr__(symmetry, "structure_id", structure.id)
    object.__setattr__(symmetry, "standardized_structure_id", standard.id)
    session.project.structures[standard.id] = standard
    session.project.symmetry_results[symmetry.id] = symmetry
    standard_view = None
    try:
        bpy.context.view_layer.objects.active = view
        view.select_set(True)
        assert bpy.ops.chemblender.view_standardized_structure(
            symmetry_result_id=str(symmetry.id),
        ) == {"FINISHED"}
        standard_view = bpy.data.objects[session.active_view_object_name]
        assert standard_view["cb_structure_id"] == str(standard.id)
        assert standard_view["cb_structure_contract"] == "structure_view_v1"
        assert standard_view["cbq_periodic_representation"] == "source_sites"
        assert view.name in bpy.data.objects
        with TemporaryDirectory(
            prefix="chemblender-cif-normalized-smoke-"
        ) as directory:
            destination = Path(directory) / "standardized.cif"
            selection = export_ui.resolve_export_selection(
                session.project,
                standard.id,
            )
            preview = export_ui.preview_export_selection(
                selection,
                "cif",
                cif_mode="normalized",
                destination=destination,
            )
            assert preview.requires_confirmation
            assert any(
                entry.code == "structure:derived"
                for entry in preview.entries
            )
            job = export_ui.ExportJob(
                destination,
                selection,
                format_name="cif",
                confirm_loss=True,
                missing_value_token=None,
                cif_mode="normalized",
            )
            job._run()
            assert job.error is None
            normalized, = core.parse_cif(destination).structures
            assert normalized.atomic_numbers == standard.atomic_numbers
            assert numpy.allclose(
                normalized.cell.values,
                standard.cell.values,
                rtol=0.0,
                atol=1.0e-12,
            )
            assert numpy.allclose(
                normalized.periodic.fractional_coordinates.values,
                standard.periodic.fractional_coordinates.values,
                rtol=0.0,
                atol=1.0e-12,
            )
            assert numpy.allclose(
                normalized.periodic.occupancies.values,
                standard.periodic.occupancies.values,
                rtol=0.0,
                atol=1.0e-12,
                equal_nan=True,
            )
            assert (
                normalized.periodic.site_labels
                == standard.periodic.site_labels
            )
            for name in (
                "isotropic_displacements",
                "anisotropic_displacements",
            ):
                expected = getattr(standard.periodic, name)
                actual = getattr(normalized.periodic, name)
                assert (actual is None) == (expected is None)
                if expected is not None:
                    assert numpy.allclose(
                        actual.values,
                        expected.values,
                        rtol=0.0,
                        atol=1.0e-12,
                        equal_nan=True,
                    )
            assert (
                normalized.periodic.declared_symmetry
                == standard.periodic.declared_symmetry
            )
    finally:
        if (
            standard_view is not None
            and standard_view.name in bpy.data.objects
        ):
            views.remove_structure_view(standard_view)
        session.project.symmetry_results.pop(symmetry.id, None)
        session.project.structures.pop(standard.id, None)
        session.active_entity_id = structure.id
        session.active_view_object_name = view.name

    mixed, = core.parse_cif(
        repository_root / "tests" / "fixtures" / "cif" / "mixed-site-data.cif"
    ).structures
    oblique_cell = numpy.asarray(
        ((2.0, 0.0, 0.0), (0.5, 3.0, 0.0), (0.2, 0.3, 4.0))
    )
    fractional = numpy.asarray(
        mixed.periodic.fractional_coordinates.values,
        dtype=float,
    )
    oblique = replace(
        mixed,
        revision=f"{mixed.revision}-oblique-smoke",
        cell=core.ArrayData(
            oblique_cell,
            ("cell_vector", "xyz"),
            "angstrom",
        ),
        coordinates=core.ArrayData(
            fractional @ oblique_cell,
            ("atom", "xyz"),
            "angstrom",
        ),
    )
    oblique_view = views.create_periodic_structure_view(
        oblique,
        settings=views.PeriodicViewSettings(
            representation="supercell",
            supercell=(2, 1, 1),
            occupancy_mode="radius",
            show_axes=True,
        ),
        name="ChemBlender oblique ADP smoke",
        collection=bpy.context.scene.collection,
    )
    oblique_cell_display = bpy.data.objects[
        oblique_view["cbq_periodic_cell_object"]
    ]
    numpy.testing.assert_allclose(
        oblique_cell_display.data.vertices[7].co,
        (4.7, 3.3, 4.0),
    )
    assert len(oblique_cell_display.data.vertices) == 14
    assert len(oblique_cell_display.data.edges) == 15
    oblique_adp = bpy.data.objects[oblique_view["cbq_periodic_adp_object"]]
    occupancy_valid = [False] * 2
    adp_valid = [False] * len(oblique_adp.data.vertices)
    quality = [0] * len(oblique_adp.data.vertices)
    oblique_view.data.attributes["cbq_occupancy_valid"].data.foreach_get(
        "value",
        occupancy_valid,
    )
    oblique_adp.data.attributes["cbq_adp_valid"].data.foreach_get(
        "value",
        adp_valid,
    )
    oblique_adp.data.attributes["cbq_quality_badge"].data.foreach_get(
        "value",
        quality,
    )
    assert occupancy_valid == [False, True]
    assert adp_valid == [True, False, True, False]
    assert quality == [1, 2, 1, 2]
    evaluated_adp = oblique_adp.evaluated_get(
        bpy.context.evaluated_depsgraph_get()
    )
    evaluated_adp_mesh = evaluated_adp.to_mesh()
    try:
        assert len(evaluated_adp_mesh.vertices) > len(oblique_adp.data.vertices)
    finally:
        evaluated_adp.to_mesh_clear()
    views.remove_structure_view(oblique_view)

    occupancy_geometry = {}
    for mode in ("opacity", "pie", "split_site"):
        mode_view = views.create_periodic_structure_view(
            mixed,
            settings=views.PeriodicViewSettings(
                occupancy_mode=mode,
                show_cell=False,
                show_axes=mode == "opacity",
            ),
            name=f"ChemBlender {mode} occupancy smoke",
            collection=bpy.context.scene.collection,
        )
        mode_display = bpy.data.objects[
            mode_view["cbq_periodic_occupancy_object"]
        ]
        source_scale = [1.0] * len(mode_view.data.vertices)
        mode_view.data.attributes["atom_scale_f"].data.foreach_get(
            "value",
            source_scale,
        )
        assert source_scale == [0.0] * len(source_scale)
        evaluated = mode_display.evaluated_get(
            bpy.context.evaluated_depsgraph_get()
        )
        evaluated_mesh = evaluated.to_mesh()
        try:
            occupancy_geometry[mode] = (
                len(mode_display.data.vertices),
                len(mode_display.data.polygons),
                len(evaluated_mesh.vertices),
            )
            assert len(evaluated_mesh.vertices) > 0
        finally:
            evaluated.to_mesh_clear()
        if mode == "pie":
            assert len(mode_display.data.polygons) > 0
            material = bpy.data.materials[
                mode_view["cbq_periodic_occupancy_material"]
            ]
            try:
                node_module.ensure_periodic_occupancy_modifier(
                    mode_display,
                    "opacity",
                    material,
                )
            except RuntimeError as error:
                assert "incompatible modifier" in str(error)
            else:
                raise AssertionError("occupancy node mode was silently reused")
        if mode == "opacity":
            axes = bpy.data.objects[
                mode_view["cbq_periodic_cell_object"]
            ]
            assert len(axes.data.vertices) == 6
            assert len(axes.data.edges) == 3
        views.remove_structure_view(mode_view)
    assert len(set(occupancy_geometry.values())) == 3

    conflict_mesh = bpy.data.meshes.new("ChemBlender node conflict smoke")
    conflict = bpy.data.objects.new(conflict_mesh.name, conflict_mesh)
    bpy.context.scene.collection.objects.link(conflict)
    modifier = conflict.modifiers.new(
        "ChemBlender Periodic Cell",
        "NODES",
    )
    foreign_group = bpy.data.node_groups.new(
        "Foreign Periodic Cell",
        "GeometryNodeTree",
    )
    foreign_group["cbq_contract"] = "periodic_cell_edges_v1"
    modifier.node_group = foreign_group
    try:
        node_module.ensure_periodic_cell_modifier(conflict)
    except RuntimeError as error:
        assert "incompatible modifier" in str(error)
    else:
        raise AssertionError("incompatible periodic node contract was reused")
    bpy.data.objects.remove(conflict, do_unlink=True)
    bpy.data.meshes.remove(conflict_mesh)
    bpy.data.node_groups.remove(foreign_group)

    foreign_owner = views.create_periodic_structure_view(
        mixed,
        settings=views.PeriodicViewSettings(
            occupancy_mode="radius",
            show_cell=False,
        ),
        name="ChemBlender foreign ownership smoke",
        collection=bpy.context.scene.collection,
    )
    foreign_mesh = bpy.data.meshes.new("Foreign cell v2")
    foreign_child = bpy.data.objects.new(foreign_mesh.name, foreign_mesh)
    bpy.context.scene.collection.objects.link(foreign_child)
    foreign_child.parent = foreign_owner
    foreign_child["cbq_contract"] = "periodic_cell_display_v1"
    foreign_child["cbq_contract_version"] = 2
    foreign_owner["cbq_periodic_cell_object"] = foreign_child.name
    foreign_material = bpy.data.materials.new("Foreign occupancy material v2")
    foreign_material["cbq_contract"] = "periodic_occupancy_material_v1"
    foreign_material["cbq_contract_version"] = 2
    foreign_owner["cbq_periodic_occupancy_material"] = foreign_material.name
    views.remove_structure_view(foreign_owner)
    assert foreign_child.name in bpy.data.objects
    assert foreign_material.name in bpy.data.materials
    bpy.data.objects.remove(foreign_child, do_unlink=True)
    bpy.data.meshes.remove(foreign_mesh)
    bpy.data.materials.remove(foreign_material)

    supercell_name = (
        "CH_超胞" if node_module.language else "CH_Supercell"
    )
    legacy_conflict = bpy.data.node_groups.new(
        supercell_name,
        "GeometryNodeTree",
    )
    source_collection = bpy.data.collections.new("Scaffold_smoke")
    bpy.context.scene.collection.children.link(source_collection)
    source_mesh = bpy.data.meshes.new("unit_smoke")
    source = bpy.data.objects.new("unit_smoke", source_mesh)
    source_collection.objects.link(source)
    source["cell lengths"] = "1,1,1"
    source["cell angles"] = "90,90,90"
    bpy.context.view_layer.objects.active = source
    source.select_set(True)
    source.hide_set(False)
    objects_before = set(bpy.data.objects.keys())
    modifiers_before = tuple(source.modifiers)
    groups_before = set(bpy.data.node_groups.keys())
    try:
        result = bpy.ops.chem.supercell()
    except RuntimeError as error:
        assert "incompatible node group" in str(error)
    else:
        assert result == {"CANCELLED"}
    assert not source.hide_get()
    assert set(bpy.data.objects.keys()) == objects_before
    assert tuple(source.modifiers) == modifiers_before
    assert set(bpy.data.node_groups.keys()) == groups_before
    bpy.data.node_groups.remove(legacy_conflict)
    assert bpy.ops.chem.supercell() == {"FINISHED"}
    generated = bpy.data.objects["crystal_smoke"]
    supercell_modifier = generated.modifiers["Supercell_smoke"]
    assert supercell_modifier.get(
        "cbq_contract"
    ) == "legacy_supercell_wrapper_v1", (
        tuple(supercell_modifier.items()),
        tuple(supercell_modifier.node_group.items()),
    )
    assert supercell_modifier["cbq_contract_version"] == 1
    assert supercell_modifier.node_group[
        "cbq_contract"
    ] == "legacy_supercell_wrapper_v1"
    assert supercell_modifier.node_group["cbq_contract_version"] == 1
    assert bpy.data.node_groups[supercell_name][
        "cbq_contract"
    ] == "legacy_supercell_asset_v1"
    assert bpy.data.node_groups[supercell_name][
        "cbq_contract_version"
    ] == 1
    generated_mesh = generated.data
    bpy.data.objects.remove(generated, do_unlink=True)
    bpy.data.meshes.remove(generated_mesh)
    bpy.data.objects.remove(source, do_unlink=True)
    bpy.data.meshes.remove(source_mesh)
    bpy.data.collections.remove(source_collection)

    cell_mesh = bpy.data.meshes.new("ChemBlender legacy cell smoke")
    cell_obj = bpy.data.objects.new(cell_mesh.name, cell_mesh)
    bpy.context.scene.collection.objects.link(cell_obj)
    bpy.context.view_layer.objects.active = cell_obj
    cell_obj.select_set(True)
    cell_modifier = node_module.add_geometry_nodetree(
        cell_obj,
        "ChemBlender Legacy Cell",
        "ChemBlender Legacy Cell Nodes",
    )
    node_module.Cell_Edges(
        cell_modifier,
        (1.0, 1.0, 1.0),
        (90.0, 90.0, 90.0),
    )
    assert cell_modifier["cbq_contract"] == "legacy_cell_edges_wrapper_v1"
    assert cell_modifier["cbq_contract_version"] == 1
    assert cell_modifier.node_group[
        "cbq_contract"
    ] == "legacy_cell_edges_wrapper_v1"
    for name, contract in (
        (
            "CH_边线扫描" if node_module.language else "CH_Edge Sweep",
            "legacy_cell_edge_sweep_asset_v1",
        ),
        (
            "CH_晶轴箭头" if node_module.language else "CH_Axes Arrows",
            "legacy_cell_axes_asset_v1",
        ),
    ):
        assert bpy.data.node_groups[name]["cbq_contract"] == contract
        assert bpy.data.node_groups[name]["cbq_contract_version"] == 1
    bpy.data.objects.remove(cell_obj, do_unlink=True)
    bpy.data.meshes.remove(cell_mesh)

    poly_mesh = bpy.data.meshes.new("ChemBlender polyhedra contract smoke")
    poly_mesh.from_pydata(((0.0, 0.0, 0.0),), (), ())
    poly_obj = bpy.data.objects.new(poly_mesh.name, poly_mesh)
    bpy.context.scene.collection.objects.link(poly_obj)
    bpy.context.view_layer.objects.active = poly_obj
    poly_obj.select_set(True)
    poly_modifier = node_module.add_geometry_nodetree(
        poly_obj,
        "ChemBlender Polyhedra",
        "ChemBlender Polyhedra Nodes",
    )
    node_module.Ball_Stick_nodetree(poly_modifier)
    node_module.CoordPolyhedra(
        poly_modifier,
        "1",
        False,
        0.0,
        3.0,
        (6,),
        (8,),
    )
    assert poly_modifier.node_group[
        "cbq_contract"
    ] == "legacy_coord_polyhedra_wrapper_v1"
    assert poly_modifier.node_group["cbq_contract_version"] == 1
    assert poly_modifier[
        "cbq_contract"
    ] == "legacy_coord_polyhedra_wrapper_v1"
    assert poly_modifier["cbq_contract_version"] == 1
    for name, contract in (
        (
            "CH_配位多面体" if node_module.language
            else "CH_Coord Polyhedra",
            "legacy_coord_polyhedra_asset_v1",
        ),
        (
            "CH_移除共面边" if node_module.language
            else "CH_Remove Coplanar Edges",
            "legacy_remove_coplanar_edges_v1",
        ),
        (
            "CH_原子序数选中项" if node_module.language
            else "CH_AtomicNum Selection",
            "legacy_atomic_selection_v1",
        ),
    ):
        assert bpy.data.node_groups[name]["cbq_contract"] == contract
        assert bpy.data.node_groups[name]["cbq_contract_version"] == 1
    bpy.data.objects.remove(poly_obj, do_unlink=True)
    bpy.data.meshes.remove(poly_mesh)

    with TemporaryDirectory(prefix="chemblender-cif-smoke-") as directory:
        root = Path(directory)
        blend = root / "partial-disorder.blend"
        assert bpy.ops.wm.save_as_mainfile(
            filepath=str(blend),
            check_existing=False,
        ) == {"FINISHED"}
        assert bpy.ops.wm.save_mainfile() == {"FINISHED"}
        assert blend.with_suffix(".cbq").is_dir()
        assert bpy.ops.wm.open_mainfile(filepath=str(blend)) == {"FINISHED"}

        ui = importlib.import_module(f"{module_key}.ui.session")
        restored = ui.get_scene_session(bpy.context.scene)
        assert structure.id in restored.project.structures
        restored_view = bpy.data.objects["ChemBlender CIF smoke"]
        assert restored_view["cb_structure_id"] == str(structure.id)
        assert restored_view["cb_periodic"] is True
        assert len(restored_view.data.vertices) == len(structure.atomic_numbers)
        assert restored_view["cbq_periodic_representation"] == "supercell"
        restored_derived = bpy.data.objects[
            restored_view["cbq_periodic_site_display_object"]
        ]
        assert restored_derived["cbq_contract"] == "structure_periodic_sites_v1"
        restored_cell = bpy.data.objects[
            restored_view["cbq_periodic_cell_object"]
        ]
        restored_adp = bpy.data.objects[
            restored_view["cbq_periodic_adp_object"]
        ]
        assert restored_cell.modifiers[0].node_group[
            "cbq_contract_version"
        ] == 1
        assert restored_adp.modifiers[0].node_group[
            "cbq_contract_version"
        ] == 1

        destination = root / "partial-disorder-export.cif"
        selection = export_ui.resolve_export_selection(
            restored.project,
            structure.id,
        )
        preview = export_ui.preview_export_selection(
            selection,
            "cif",
            cif_mode="preserve",
            destination=destination,
        )
        assert not preview.requires_confirmation
        assert any(
            entry.code == "target:cif_preserve"
            for entry in preview.entries
        )
        job = export_ui.ExportJob(
            destination,
            selection,
            format_name="cif",
            confirm_loss=False,
            missing_value_token=None,
            cif_mode="preserve",
        )
        job.start()
        assert job.join(30)
        assert job.error is None
        assert job.result.written
        exported = core.parse_cif(destination)
        preserved, = exported.structures
        assert preserved.atomic_numbers == structure.atomic_numbers
        assert numpy.allclose(
            preserved.cell.values,
            structure.cell.values,
            rtol=0.0,
            atol=1.0e-12,
        )
        assert numpy.allclose(
            preserved.periodic.fractional_coordinates.values,
            structure.periodic.fractional_coordinates.values,
            rtol=0.0,
            atol=1.0e-12,
        )
        assert tuple(preserved.periodic.occupancies.values) == (0.5,)
        assert (
            preserved.periodic.declared_symmetry
            == structure.periodic.declared_symmetry
        )
        assert b"_chemblender_unknown_tag" in destination.read_bytes()
        assert "spglib" not in sys.modules

        views.remove_structure_view(restored_view)
        ui.close_scene_session(bpy.context.scene)


def assert_poscar_workflow(module_key, repository_root):
    import numpy

    assert bpy.ops.wm.read_homefile(use_empty=True) == {"FINISHED"}
    core = importlib.import_module(f"{module_key}.core")
    export_ui = importlib.import_module(f"{module_key}.ui.export")
    ui = importlib.import_module(f"{module_key}.ui.session")
    views = importlib.import_module(f"{module_key}.views")
    source = (
        repository_root
        / "tests"
        / "fixtures"
        / "poscar"
        / "cscl-selective.vasp"
    )
    batch = core.parse_poscar(source)
    structure, = batch.structures
    selective = next(
        value
        for value in batch.datasets
        if value.semantic_role == "selective_dynamics"
    )
    session = ui.new_scene_session(bpy.context.scene)
    session.project.commit(batch)
    session.mark_dirty("import")
    view = views.create_periodic_structure_view(
        structure,
        settings=views.PeriodicViewSettings(show_constraints=False),
        selective_dynamics=selective,
        name="ChemBlender POSCAR smoke",
        collection=bpy.context.scene.collection,
    )
    marker = bpy.data.objects[view["cb_selective_marker_object"]]
    assert view.data.attributes["cbq_selective_x"] is not None
    assert view.data.attributes["cbq_selective_y"] is not None
    assert view.data.attributes["cbq_selective_z"] is not None
    assert marker["cbq_contract"] == "structure_selective_marker_v1"
    assert view["cb_selective_constraint_count"] == 2
    assert marker.hide_get()
    session.active_entity_id = structure.id
    session.active_view_object_name = view.name
    bpy.context.view_layer.objects.active = view
    view.select_set(True)
    assert bpy.ops.chemblender.toggle_selective_constraints() == {"FINISHED"}
    assert not marker.hide_get()
    assert bpy.ops.chemblender.toggle_selective_constraints() == {"FINISHED"}
    assert marker.hide_get()

    with TemporaryDirectory(prefix="chemblender-poscar-smoke-") as directory:
        root = Path(directory)
        blend = root / "selective.blend"
        assert bpy.ops.wm.save_as_mainfile(
            filepath=str(blend),
            check_existing=False,
        ) == {"FINISHED"}
        assert bpy.ops.wm.save_mainfile() == {"FINISHED"}
        assert session.link_status == "connected", (
            session.link_status,
            ui.get_scene_session_status(bpy.context.scene),
        )
        assert structure.id in session.project.structures
        assert bpy.ops.wm.open_mainfile(filepath=str(blend)) == {"FINISHED"}
        ui = importlib.import_module(f"{module_key}.ui.session")
        restored = ui.get_scene_session(bpy.context.scene)
        assert structure.id in restored.project.structures, (
            tuple(restored.project.structures),
            restored.link_status,
            ui.get_scene_session_status(bpy.context.scene),
        )
        restored_view = bpy.data.objects["ChemBlender POSCAR smoke"]
        restored_marker = bpy.data.objects[
            restored_view["cb_selective_marker_object"]
        ]
        assert restored_marker["cb_structure_id"] == str(structure.id)
        restored_selective = next(
            value
            for value in restored.project.datasets.values()
            if (
                value.semantic_role == "selective_dynamics"
                and value.structure_id == structure.id
            )
        )
        assert (
            numpy.asarray(restored_selective.data.values).tolist()
            == selective.data.values.tolist()
        )

        destination = root / "POSCAR"
        selection = export_ui.resolve_export_selection(
            restored.project,
            structure.id,
        )
        settings = export_ui.PoscarExportSettings(
            comment="ChemBlender smoke",
            coordinate_mode="cartesian",
            scale_policy="unit",
            include_selective_dynamics=True,
        )
        preview = export_ui.preview_export_selection(
            selection,
            "poscar",
            poscar_settings=settings,
            destination=destination,
        )
        assert not preview.requires_confirmation
        assert any(
            entry.code == "coordinates_cartesian"
            for entry in preview.entries
        )
        job = export_ui.ExportJob(
            destination,
            selection,
            format_name="poscar",
            confirm_loss=False,
            missing_value_token=None,
            poscar_settings=settings,
        )
        job.start()
        assert job.join(30)
        assert job.error is None
        assert job.result.written
        reparsed = core.parse_poscar(destination)
        exporters = importlib.import_module(
            f"{module_key}.core.exporters"
        )
        assert exporters.semantic_poscar_differences(batch, reparsed) == ()
        reparsed_selective = next(
            value
            for value in reparsed.datasets
            if value.semantic_role == "selective_dynamics"
        )
        assert (
            reparsed_selective.data.values.tolist()
            == selective.data.values.tolist()
        )

        velocity_batch = core.parse_poscar(
            repository_root
            / "tests"
            / "fixtures"
            / "poscar"
            / "velocities.CONTCAR"
        )
        restored.project.commit(velocity_batch)
        velocity_structure, = velocity_batch.structures
        velocity_destination = root / "CONTCAR"
        velocity_selection = export_ui.resolve_export_selection(
            restored.project,
            velocity_structure.id,
        )
        velocity_job = export_ui.ExportJob(
            velocity_destination,
            velocity_selection,
            format_name="poscar",
            confirm_loss=True,
            missing_value_token=None,
        )
        velocity_job._run()
        assert velocity_job.error is None
        velocity_document = importlib.import_module(
            f"{module_key}.core.formats.poscar"
        ).parse_poscar_document(velocity_destination.read_bytes())
        assert velocity_document.velocities is not None
        assert velocity_document.lattice_velocities is not None

        views.remove_structure_view(restored_view)
        ui.close_scene_session(bpy.context.scene)


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


def assert_sdf_10k_workflow_budget(module_key):
    from statistics import median
    from time import perf_counter
    import tracemalloc

    from rdkit import Chem, rdBase
    from rdkit.Chem import rdDepictor

    core = importlib.import_module(f"{module_key}.core")
    conformer_grouping = importlib.import_module(
        f"{module_key}.core.import_pipeline.conformer_grouping"
    )
    request_model = importlib.import_module(
        f"{module_key}.core.import_pipeline.request"
    )
    reader_bridge = importlib.import_module(
        f"{module_key}.reader_api.import_pipeline_bridge"
    )
    registry = importlib.import_module(
        f"{module_key}.runtime.reader_api_bridge"
    ).get_reader_plugin_registry()
    properties = importlib.import_module(f"{module_key}.ui.properties")
    preview_ui = importlib.import_module(
        f"{module_key}.ui.import_preview"
    )
    browser_model = importlib.import_module(
        f"{module_key}.ui.project_browser.model"
    )
    suffixes = (
        "",
        "O",
        "N",
        "F",
        "Cl",
        "Br",
        "S",
        "C#N",
        "C=O",
        "C(=O)O",
    )
    molecules = tuple(
        Chem.MolFromSmiles("C" * length + suffix)
        for length in range(1, 11)
        for suffix in suffixes
    )
    canonical_identities = tuple(
        Chem.MolToSmiles(
            molecule,
            canonical=True,
            isomericSmiles=True,
        )
        for molecule in molecules
    )
    assert len(molecules) == len(set(canonical_identities)) == 100
    before_objects = tuple(bpy.data.objects)
    timings = {}

    def measured(name, repeats, operation):
        samples = []
        result = None
        for index in range(repeats):
            started = perf_counter()
            result = operation(index)
            samples.append(perf_counter() - started)
        timings[name] = samples
        return result

    with TemporaryDirectory(
        prefix="chemblender-sdf-workflow-benchmark-"
    ) as directory:
        root = Path(directory)
        source = root / "10k.sdf"
        with source.open("wb") as stream:
            for identity_index, molecule in enumerate(molecules):
                molecule.SetProp("_Name", f"Identity {identity_index:03d}")
                rdDepictor.Compute2DCoords(molecule)
                record = Chem.MolToMolBlock(molecule).encode("utf-8")
                for _ in range(100):
                    stream.write(record)
                    stream.write(b"$$$$\n")

        source_model = request_model.ImportSource(source)
        request = request_model.ImportRequest(
            sources=(source_model,),
            validation_mode=request_model.ValidationMode.BALANCED,
        )
        session = core.create_session(temp_parent=root)
        staging = properties.create_quick_import_staging(session)
        tracemalloc.start()
        measured_sequence_started = perf_counter()
        try:
            preview = measured(
                "reader_preflight",
                1,
                lambda _index: reader_bridge.preflight_reader_plugins(
                    request,
                    registry,
                    staging,
                    progress=lambda *_args: None,
                    is_cancelled=lambda: False,
                ),
            )
            suggestions = measured(
                "conformer_suggestion",
                3,
                lambda _index: (
                    conformer_grouping.suggest_staged_conformer_groups(
                        preview,
                        staging,
                    )
                ),
            )
            properties.store_quick_import_preview(
                session,
                staging,
                preview,
                conformer_grouping_suggestions=suggestions,
            )
            state = properties.get_quick_import_state(session)
            preview_rows, conformer_rows = measured(
                "preview_projection",
                3,
                lambda _index: (
                    preview_ui.project_import_preview(
                        session,
                        state,
                        registry,
                    ),
                    preview_ui.project_conformer_suggestions(state),
                ),
            )
            source_preview, = preview.source_previews
            staged_batch_id, = source_preview.staged_batch_ids
            batch = staging.result(staged_batch_id)
            source_revision_ids = {
                record.source_revision_id
                for record in batch.molecular_records
            }
            assert len(batch.molecular_records) == 10_000
            assert source_revision_ids == {batch.source_revisions[0].id}
            assert len(suggestions) == len(conformer_rows) == 100
            assert preview_rows[0].molecular_record_count == 10_000
            assert preview_rows[0].conformer_suggestion_count == 100
            measured(
                "project_commit",
                1,
                lambda _index: session.project.commit(batch),
            )

            browser_samples = []
            filter_samples = []
            for revision in range(1, 4):
                started = perf_counter()
                browser_rows = browser_model.build_browser_rows(
                    session.project,
                    session_id=session.id,
                    browser_revision=revision,
                )
                browser_samples.append(perf_counter() - started)
                started = perf_counter()
                filtered_rows = browser_model.build_browser_rows(
                    session.project,
                    session_id=session.id,
                    browser_revision=revision,
                    search="Identity 042",
                )
                filter_samples.append(perf_counter() - started)
            timings["browser_projection"] = browser_samples
            timings["browser_filter"] = filter_samples
            timings["measured_sequence_wall"] = [
                perf_counter() - measured_sequence_started
            ]
            _current, peak = tracemalloc.get_traced_memory()

            assert sum(
                row.kind == "molecular_record"
                for row in browser_rows
            ) == 10_000
            assert sum(
                row.kind == "molecular_record"
                for row in filtered_rows
            ) == 100
            assert tuple(bpy.data.objects) == before_objects
        finally:
            tracemalloc.stop()
            try:
                properties.clear_quick_import_state(session)
            finally:
                core.close_session(session)

        def timing_summary(samples):
            ordered = sorted(samples)
            return {
                "samples": len(samples),
                "median": median(samples),
                "p95": ordered[math.ceil(len(samples) * 0.95) - 1],
            }

        print(
            "PERF: "
            + json.dumps(
                {
                    "benchmark": "sdf_10k_workflow",
                    "environment": {
                        "blender": bpy.app.version_string,
                        "python": sys.version.split()[0],
                        "rdkit": rdBase.rdkitVersion,
                    },
                    "input": {
                        "canonical_identity_count": 100,
                        "record_count": 10_000,
                        "records_per_identity": 100,
                        "size_bytes": source.stat().st_size,
                        "source_revision_count": len(
                            source_revision_ids
                        ),
                    },
                    "memory": {"peak_bytes": peak},
                    "output": {
                        "browser_row_count": len(browser_rows),
                        "conformer_suggestion_count": len(suggestions),
                        "filtered_record_count": sum(
                            row.kind == "molecular_record"
                            for row in filtered_rows
                        ),
                    },
                    "timing_seconds": {
                        name: timing_summary(samples)
                        for name, samples in timings.items()
                    },
                },
                sort_keys=True,
            )
        )


def assert_project_browser_rna_budget(module_key):
    from time import perf_counter
    import tracemalloc
    from unittest.mock import patch

    panel = importlib.import_module(
        f"{module_key}.ui.project_browser.panel"
    )
    model = importlib.import_module(
        f"{module_key}.ui.project_browser.model"
    )
    scene = bpy.data.scenes.new("ChemBlender Browser RNA Budget")
    rows = tuple(
        model.BrowserRow(
            id=f"record-{index}",
            parent_id=None,
            depth=1,
            kind="molecular_record",
            label=f"Record {index}",
            quality="complete",
            view_count=0,
            entity_id=None,
        )
        for index in range(40007)
    )
    session = SimpleNamespace(
        id=uuid4(),
        project=object(),
        active_entity_id=None,
    )
    try:
        with (
            patch.object(panel, "get_scene_session", return_value=session),
            patch.object(
                panel,
                "get_quick_import_state",
                return_value=SimpleNamespace(browser_revision=1),
            ),
            patch.object(panel, "build_browser_rows", return_value=rows),
        ):
            tracemalloc.start()
            samples = []
            for _ in range(3):
                started = perf_counter()
                projected = panel.refresh_project_browser(scene)
                samples.append((perf_counter() - started) * 1000.0)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        settings = scene.chemblender_project_browser
        assert projected is rows
        assert settings.total_row_count == len(rows)
        assert len(settings.rows) == panel._BROWSER_RNA_ROW_LIMIT
        assert max(samples) < 200.0, samples
        ordered = sorted(samples)
        print(
            "PERF: Project Browser 40,007-row RNA projection "
            f"median={ordered[1]:.2f}ms p95={ordered[-1]:.2f}ms "
            f"peak={peak}B visible={len(settings.rows)}"
        )
    finally:
        bpy.data.scenes.remove(scene)


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
    {"module": ".ui.grid", "register": True, "unregister": True},
    {"module": ".ui.project_browser.panel", "register": True, "unregister": True},
    {"module": ".ui.file_handlers", "register": True, "unregister": True},
    {"module": ".ui.workspace", "register": True, "unregister": True},
]
expected_inventory["registered_classes"] += [
    {
        "module": ".ui.grid",
        "name": "CHEMBLENDER_OT_create_grid_view",
        "id": "chemblender.create_grid_view",
        "base": "Operator",
    },
    {
        "module": ".ui.grid",
        "name": "CHEMBLENDER_OT_resolve_grid_semantics",
        "id": "chemblender.resolve_grid_semantics",
        "base": "Operator",
    },
    {
        "module": ".ui.grid",
        "name": "CHEMBLENDER_PG_grid_settings",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.export",
        "name": "CHEMBLENDER_OT_export_project_entity",
        "id": "chemblender.export_project_entity",
        "base": "Operator",
    },
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
        "name": "CHEMBLENDER_OT_apply_poscar_species",
        "id": "chemblender.apply_poscar_species",
        "base": "Operator",
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
        "name": "CHEMBLENDER_PG_import_conformer_evidence",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.import_preview",
        "name": "CHEMBLENDER_PG_import_conformer_suggestion",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.import_preview",
        "name": "CHEMBLENDER_PG_import_conflict_candidate",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.import_preview",
        "name": "CHEMBLENDER_PG_import_grouping_evidence",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.import_preview",
        "name": "CHEMBLENDER_PG_import_grouping_suggestion",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.import_preview",
        "name": "CHEMBLENDER_PG_import_preview_row",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.scientific_edit",
        "name": "CHEMBLENDER_OT_apply_scientific_edits",
        "id": "chemblender.apply_scientific_edits",
        "base": "Operator",
    },
    {
        "module": ".ui.topology",
        "name": "CHEMBLENDER_OT_accept_topology",
        "id": "chemblender.accept_topology",
        "base": "Operator",
    },
    {
        "module": ".ui.topology",
        "name": "CHEMBLENDER_OT_compute_topology",
        "id": "chemblender.compute_topology",
        "base": "Operator",
    },
    {
        "module": ".ui.topology",
        "name": "CHEMBLENDER_OT_reject_topology",
        "id": "chemblender.reject_topology",
        "base": "Operator",
    },
    {
        "module": ".ui.topology",
        "name": "CHEMBLENDER_OT_switch_topology",
        "id": "chemblender.switch_topology",
        "base": "Operator",
    },
    {
        "module": ".ui.topology",
        "name": "CHEMBLENDER_PG_topology_settings",
        "id": None,
        "base": "PropertyGroup",
    },
    {
        "module": ".ui.quick_import",
        "name": "CHEMBLENDER_OT_import_smiles_text",
        "id": "chemblender.import_smiles_text",
        "base": "Operator",
    },
    {
        "module": ".ui.quick_import",
        "name": "CHEMBLENDER_PT_quick_import",
        "id": "CHEMBLENDER_PT_QUICK_IMPORT",
        "base": "Panel",
    },
    {
        "module": ".ui.properties",
        "name": "CHEMBLENDER_OT_derive_crystal_symmetry",
        "id": "chemblender.derive_crystal_symmetry",
        "base": "Operator",
    },
    {
        "module": ".ui.properties",
        "name": "CHEMBLENDER_OT_view_standardized_structure",
        "id": "chemblender.view_standardized_structure",
        "base": "Operator",
    },
    {
        "module": ".ui.properties",
        "name": "CHEMBLENDER_OT_toggle_selective_constraints",
        "id": "chemblender.toggle_selective_constraints",
        "base": "Operator",
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
        "name": "CHEMBLENDER_OT_apply_frame_force",
        "id": "chemblender.apply_frame_force",
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
assert stable_inventory == expected_inventory, (
    stable_inventory,
    expected_inventory,
)

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
assert_unwrapped_periodic_inference_view(module_key)
assert_periodic_electronic_plots(module_key)
assert_scene_preset_application(module_key)
assert_complex_phonon_trajectory(module_key)
assert_fermi_surface_view(module_key)
assert_project_sidecar_link(module_key)
assert_quick_import(module_key, package.parent.parent)
assert_cif_workflow(module_key, package.parent.parent)
assert_poscar_workflow(module_key, package.parent.parent)
assert_optional_workspace(module_key)
assert_project_session_manager(module_key)
assert_topology_view(module_key, package.parent.parent)
assert_extxyz_workflow(module_key, package.parent.parent)
assert_legacy_crystal_reader_baseline(module_key, package.parent.parent)
assert_sdf_10k_workflow_budget(module_key)
assert_project_browser_rna_budget(module_key)

import rdkit
import gemmi
from rdkit import Chem
from rdkit.Chem import AllChem

assert rdkit.__version__
assert version("rdkit") == "2026.3.3"
assert gemmi.__version__ == "0.7.5"
assert version("gemmi") == "0.7.5"
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
