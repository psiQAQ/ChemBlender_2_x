"""Exercise Mesh Apply -> external RDKit -> appended CBQ results in Blender."""

import importlib
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import numpy


arguments = sys.argv[sys.argv.index("--") + 1:]
root = Path(arguments[0]).resolve(strict=True)
processor_executable = Path(arguments[1]).resolve(strict=True)
source_package = Path(arguments[2]).resolve(strict=True)
extension_package = (
    Path(arguments[3]).resolve(strict=True) if len(arguments) == 4 else None
)
profile = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve(strict=True)
assert bpy.app.version >= (5, 1, 0)
assert profile != Path.home() and root not in profile.parents

if extension_package is None:
    sys.path.insert(0, str(root))
    package_root = "ChemBlender"
else:
    assert bpy.ops.extensions.package_install_files(
        filepath=str(extension_package), repo="user_default",
        enable_on_install=True, overwrite=False,
    ) == {"FINISHED"}
    package_root = "bl_ext.user_default.chemblender"

core_root = "cbq_core" if extension_package is None else package_root + "._cbq_core"
model = importlib.import_module(core_root + ".model")
registration = importlib.import_module(package_root + ".runtime.registration")
processor_operations = importlib.import_module(package_root + ".ui.processor_operations")
session_ui = importlib.import_module(package_root + ".ui.session")

if extension_package is None:
    registration.register_extension(package_root)
else:
    assert Path(processor_operations.__file__).resolve().is_relative_to(profile)

scene = bpy.context.scene
preferences = SimpleNamespace(processor_executable=str(processor_executable))
with TemporaryDirectory(prefix="molecule-blender-") as temporary:
    temporary = Path(temporary)
    imported_package = temporary / "benzene.cbq"
    shutil.copytree(source_package, imported_package)
    scene.chemblender_cbq.input_path = str(imported_package)
    assert bpy.ops.chemblender.preview_cbq() == {"FINISHED"}
    assert bpy.ops.chemblender.import_cbq() == {"FINISHED"}
    session = session_ui.get_scene_session(scene)
    source = next(iter(session.project.structures.values()))
    source_id = source.id
    source_coordinates = numpy.array(source.coordinates.values, copy=True)
    source_topology = session.project.topologies[source.topology_ids[0]]

    session.active_entity_id = source.id
    scene.chemblender_project_browser.active_entity_id = str(source.id)
    scene.chemblender_scientific_view.preset_id = "structure_publication"
    assert bpy.ops.chemblender.scientific_view(action="CREATE") == {"FINISHED"}
    source_view = bpy.context.view_layer.objects.active
    source_view.data.vertices[0].co.z += .15
    source_view["cbq_mesh_edit_pending"] = True
    assert bpy.ops.chemblender.apply_mesh_edits() == {"FINISHED"}
    edited = session.project.structures[session.active_entity_id]
    edited_topology = session.project.topologies[edited.topology_ids[0]]
    assert edited.id != source_id and source_id in session.project.structures
    assert source_topology.id in session.project.topologies
    assert not numpy.array_equal(
        numpy.array(edited.coordinates.values, copy=True),
        source_coordinates,
    )

    settings = scene.chemblender_processor_operation
    settings.molecule_force_field = "UFF"
    settings.molecule_add_hydrogens = False
    settings.molecule_max_iterations = 200
    with patch(
        package_root + ".ui.processor.get_processor_preferences",
        return_value=preferences,
    ):
        before = set(session.project.structures)
        assert bpy.ops.chemblender.processor_operation(
            "EXEC_DEFAULT", action="MOLECULE",
            operation_id="molecule.optimize", source_id=str(edited.id),
            topology_id=str(edited_topology.id),
        ) == {"FINISHED"}
        optimized = session.project.structures[session.active_entity_id]
        assert optimized.id not in before
        assert before.issubset(session.project.structures)
        assert numpy.isfinite(
            numpy.array(optimized.coordinates.values, copy=True)
        ).all()
        optimized_topology = session.project.topologies[optimized.topology_ids[0]]

        assert bpy.ops.chemblender.processor_operation(
            "EXEC_DEFAULT", action="MOLECULE",
            operation_id="molecule.energy", source_id=str(optimized.id),
            topology_id=str(optimized_topology.id),
        ) == {"FINISHED"}
        energy = session.project.datasets[session.active_entity_id]
        assert isinstance(energy, model.PropertyDataset)
        assert energy.semantic_role == "potential_energy"
        assert energy.data.unit == "kilocalorie_per_mole"

        destination = temporary / "edited-benzene.sdf"
        settings.molecule_export_format = "sdf"
        settings.molecule_export_path = str(destination)
        assert bpy.ops.chemblender.processor_operation(
            "EXEC_DEFAULT", action="MOLECULE",
            operation_id="molecule.export", source_id=str(optimized.id),
            topology_id=str(optimized_topology.id),
        ) == {"FINISHED"}
        assert destination.is_file() and destination.stat().st_size > 0

    saved = temporary / "molecule-operation.blend"
    assert bpy.ops.wm.save_as_mainfile(filepath=str(saved)) == {"FINISHED"}
    shutil.rmtree(imported_package)
    assert bpy.ops.wm.open_mainfile(filepath=str(saved)) == {"FINISHED"}
    reopened = session_ui.get_scene_session(bpy.context.scene)
    assert source_id in reopened.project.structures
    assert edited.id in reopened.project.structures
    assert optimized.id in reopened.project.structures
    assert energy.id in reopened.project.datasets
    assert numpy.isfinite(
        numpy.array(
            reopened.project.structures[optimized.id].coordinates.values,
            copy=True,
        )
    ).all()
    assert any(
        obj.get("cb_structure_id") == str(optimized.id)
        for obj in bpy.data.objects
    )
    session_ui.close_scene_session(bpy.context.scene)

if extension_package is None:
    registration.unregister_extension()
else:
    assert bpy.ops.preferences.addon_disable(module=package_root) == {"FINISHED"}

print("BLENDER_MOLECULE_OPERATIONS_PASSED")
