"""Private Blender RNA import and late-cancellation regression (synthetic files)."""

import os
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import bpy
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
assert ROOT / ".agents" / "cache" in private.parents
private.mkdir(parents=True, exist_ok=True)

from ChemBlender.core import ImportBatch, close_project, create_session, open_project, save_project
from ChemBlender.core.import_pipeline import ImportCancelled
from ChemBlender.ui import scientific_import, session as session_ui, topology_import, wavefunction_import
from ChemBlender.ui.project_browser import panel
from ChemBlender.ui.tasks import Task, TaskState, TaskWorker
from tests.test_topology_import import topology_files

operator_types = (
    wavefunction_import.CHEMBLENDER_OT_import_wavefunction,
    scientific_import.CHEMBLENDER_OT_import_scientific_file,
    scientific_import.CHEMBLENDER_OT_import_fermi,
    topology_import.CHEMBLENDER_OT_import_topology,
)
classes = (panel.CHEMBLENDER_PG_project_browser_row, panel.CHEMBLENDER_PG_project_browser,
           topology_import.CHEMBLENDER_PG_topology_import, *operator_types)
for cls in classes:
    bpy.utils.register_class(cls)
bpy.types.Scene.chemblender_project_browser = bpy.props.PointerProperty(type=panel.CHEMBLENDER_PG_project_browser)
topology_import.register()
topology_import.register()
wavefunction_import.register()
scene = bpy.context.scene
session = create_session(temp_parent=private.parent)
session_ui._FILE_SESSION = session_ui._SessionEntry(session)
structure, cp, flux, samples = topology_files(private)
session.project.commit(ImportBatch(structures=(structure,)))
settings = scene.chemblender_topology_import


def finished_host(operator_type, *, error=None):
    def work(_cancelled, _progress):
        if error is not None:
            raise error
        return object()
    job = TaskWorker(Task(), work)
    job.start("completed reader")
    assert job.join(5)
    host = SimpleNamespace(_job=job, _session=session, _timer=object(),
        _manager=SimpleNamespace(event_timer_remove=Mock()), _cancel_requested=False,
        commit_batch=Mock(), report=Mock())
    host._finish_modal = MethodType(operator_type._finish_modal, host)
    host._complete = MethodType(operator_type._complete, host)
    wavefunction_import._ACTIVE_IMPORTS.append(host)
    return host


try:
    assert settings.field_kind == "UNSET"
    assert settings.structure_id == "NONE"
    settings.structure_id = str(structure.id)
    assert settings.structure_uuid == str(structure.id)
    # Enum ordinals cannot silently bind another Structure after registry edits.
    session.project.structures.pop(structure.id)
    assert settings.structure_id == "NONE"
    assert settings.structure_uuid == str(structure.id)
    session.project.structures[structure.id] = structure
    assert settings.structure_id == str(structure.id)
    settings.cpreport_file = str(cp)
    settings.field_kind = "ELECTRON_DENSITY_AU"
    assert bpy.ops.chemblender.import_topology() == {"FINISHED"}
    base_id = session.active_entity_id
    assert session.project.datasets[base_id].paths == ()
    settings.fluxprint_file = str(flux)
    assert bpy.ops.chemblender.import_topology() == {"FINISHED"}
    graph = session.project.datasets[session.active_entity_id]
    assert len(session.project.datasets) == 2
    assert scene.chemblender_project_browser.active_entity_id == str(graph.id)
    numpy.testing.assert_allclose(graph.paths[0].samples.values, samples)
    sidecar = private / "topology.cbq"
    save_project(sidecar, session.project)
    reopened = open_project(sidecar)
    try:
        numpy.testing.assert_array_equal(reopened.datasets[graph.id].paths[0].samples.values, graph.paths[0].samples.values)
        assert reopened.provenance[graph.provenance_ids[-1]].parent_ids == (base_id,)
    finally:
        close_project(reopened)
    assert not wavefunction_import._ACTIVE_IMPORTS
    print("TOPOLOGY_IMPORT_PASSED: explicit RNA, parent extension, units, sidecar")

    for operator_type in operator_types:
        for action in ("escape", "cancel", "session_cleanup", "reader_cancel"):
            host = finished_host(operator_type,
                error=ImportCancelled("reader cancelled") if action == "reader_cancel" else None)
            if action != "reader_cancel":
                assert host._job.task.snapshot().state is TaskState.SUCCEEDED
            if action == "escape":
                result = operator_type.modal(host, bpy.context, SimpleNamespace(type="ESC"))
            else:
                if action == "cancel":
                    operator_type.cancel(host, bpy.context)
                elif action == "session_cleanup":
                    wavefunction_import._cancel_session_imports(session)
                result = host._complete(bpy.context)
            assert result == {"CANCELLED"}, (operator_type.__name__, action)
            host.commit_batch.assert_not_called()
            host._manager.event_timer_remove.assert_called_once()
            assert host not in wavefunction_import._ACTIVE_IMPORTS
        host = finished_host(operator_type)
        assert host._complete(bpy.context) == {"FINISHED"}
        host.commit_batch.assert_called_once_with(bpy.context, host._job.result)
        assert host not in wavefunction_import._ACTIVE_IMPORTS
    print("EXTERNAL_IMPORT_CANCEL_PASSED: four actual operator classes, four cancellation paths, normal completion")
finally:
    topology_import.unregister()
    topology_import.unregister()
    wavefunction_import.unregister()
    session_ui.close_scene_session(scene)
    del bpy.types.Scene.chemblender_project_browser
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
