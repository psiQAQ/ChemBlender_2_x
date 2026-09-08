"""Background Blender UI/lifecycle regression; no optional packages are installed.

Pass -- --existing-libraries PATH to reuse an existing RDKit/Gemmi installation.
The missing-backend case deliberately uses Blender's standalone Python.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--existing-libraries")
args = parser.parse_args(arguments)
if args.existing_libraries:
    sys.path.append(args.existing_libraries)

import ChemBlender
from ChemBlender.core import ImportBatch, OrbitalKind
from ChemBlender.ui import session as session_ui
from ChemBlender.ui import wavefunction as ui
from ChemBlender.ui import wavefunction_import as importer
from tests.test_wavefunction_grid import entities


def check_ui_and_tasks():
    scene = bpy.context.scene
    session = session_ui.get_scene_session(scene)
    structure, basis, orbitals = entities(OrbitalKind.UNRESTRICTED)
    session.project.commit(ImportBatch(structures=(structure,), basis_sets=(basis,),
                                       orbital_sets=(orbitals,)))
    session.active_entity_id = orbitals.id
    settings = scene.chemblender_wavefunction
    settings.worker_python = str(Path(sys.prefix) / "bin" / "python.exe")
    settings.worker_repository = str(ROOT)
    settings.orbital_source = str(orbitals.id)
    settings.channel = "beta"
    settings.spacing = 1.
    settings.padding = 1.
    assert bpy.ops.chemblender.wavefunction(action="fit") == {"FINISHED"}
    assert tuple(settings.shape) == (3, 3, 3)
    assert tuple(settings.origin) == (-1., -1., -1.)
    assert bpy.ops.chemblender.wavefunction(action="select", orbital_index=1) == {"FINISHED"}
    assert settings.orbital_number == 2 and settings.channel == "beta"
    settings.orbital_number = 1
    settings.origin = (1., 2., 3.)
    settings.shape = (2, 2, 2)
    inputs = ui.wavefunction_inputs(session.project, "wavefunction.mo_grid", orbitals.id)
    parameters = {"origin": list(settings.origin), "step_vectors":
                  [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], "shape": [2, 2, 2],
                  "channel": "beta", "orbital_index": 0}
    before = (set(session.project.datasets), set(session.project.provenance))
    # A real child process runs from a private project; absent GBasis must not publish.
    if importlib.util.find_spec("gbasis") is not None:
        raise AssertionError("This missing-dependency regression requires Blender without GBasis")
    try:
        outcome = bpy.ops.chemblender.wavefunction(action="compute",
            operation_id="wavefunction.mo_grid", source_id=str(orbitals.id))
    except RuntimeError as error:
        assert "gbasis" in str(error).lower(), str(error)
    else:
        assert outcome == {"CANCELLED"}, outcome
    assert before == (set(session.project.datasets), set(session.project.provenance))
    assert not ui._JOBS
    assert not list(Path(session.temporary_root).glob("wavefunction-*"))

    fixture = ROOT / "submodules/iodata/iodata/test/data/water_sto3g_hf_g03.fchk"
    assert fixture.is_file(), "initialize the pinned IOData fixture submodule"
    try:
        outcome = bpy.ops.chemblender.import_wavefunction(filepath=str(fixture))
    except RuntimeError as error:
        assert "iodata" in str(error).lower(), str(error)
    else:
        assert outcome == {"CANCELLED"}, outcome
    assert not importer._ACTIVE_IMPORTS
    assert not list(Path(session.temporary_root).glob("chemblender-wavefunction-*"))
    assert before == (set(session.project.datasets), set(session.project.provenance))

    job = ui.WavefunctionJob(session, "wavefunction.mo_grid", inputs, parameters,
        python_executable=settings.worker_python, working_directory=ROOT)
    job.start()
    operator = SimpleNamespace(_job=job)
    ui.CHEMBLENDER_OT_wavefunction.cancel(operator, bpy.context)
    assert ui.CHEMBLENDER_OT_wavefunction.modal(
        operator, bpy.context, SimpleNamespace(type="MOUSEMOVE")) == {"CANCELLED"}
    assert job.worker.join(15), "cancel did not stop the owned job"
    try:
        job.publish(session)
    except RuntimeError:
        pass
    else:
        raise AssertionError("cancelled task published a grid")
    job.close()
    assert not job.root.exists() and not ui._JOBS
    assert before == (set(session.project.datasets), set(session.project.provenance))
    assert not session.dirty
    session_ui.close_scene_session(scene)
    return {"orbital_selection": "passed", "spin_switch": "passed",
            "grid_preflight": "passed", "missing_backend_atomicity": "passed",
            "missing_parser_atomicity": "passed",
            "cancel_cleanup": "passed"}


results = {}
for iteration in range(2):
    ChemBlender.register()
    try:
        results[f"cycle_{iteration + 1}"] = check_ui_and_tasks()
    finally:
        ChemBlender.unregister()
    assert not hasattr(bpy.types.Scene, "chemblender_wavefunction")
    assert not ui._JOBS
print("WORKBENCH_PHASE_B_UI_PASSED " + json.dumps(results, sort_keys=True))
