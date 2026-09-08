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
parser.add_argument("--worker-python")
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
    assert not list(Path(session.temporary_root).glob("wf-*"))
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


def check_real_ui():
    """Exercise the actual import and calculation operators with real files."""
    results = {}
    scene = bpy.context.scene
    for name in ("water_sto3g_hf_g03.fchk", "h2o.molden.input", "ch3_hf_sto3g.fchk"):
        settings = scene.chemblender_wavefunction
        settings.worker_python = args.worker_python
        settings.worker_repository = str(ROOT)
        fixture = ROOT / "submodules/iodata/iodata/test/data" / name
        assert bpy.ops.chemblender.import_wavefunction(filepath=str(fixture)) == {"FINISHED"}
        session = session_ui.get_scene_session(scene)
        orbitals = session.project.orbital_sets[session.active_entity_id]
        assert settings.orbital_source == str(orbitals.id)
        settings.channel = orbitals.channels[-1].label
        settings.orbital_number = 1
        # Offset from nuclei: ESP is undefined at nuclear coordinates.
        settings.origin, settings.spacing, settings.shape = (-2.13, -1.87, -2.07), .5, (9, 9, 9)
        settings.nuclear_charge = str(next(value.id for value in session.project.datasets.values()
            if value.semantic_role == "nuclear_charge" and value.structure_id == orbitals.structure_id))
        settings.density_level = "scf"

        def compute(operation, source):
            before = set(session.project.datasets)
            assert bpy.ops.chemblender.wavefunction(action="compute",
                operation_id=operation, source_id=str(source.id)) == {"FINISHED"}
            added = set(session.project.datasets) - before
            assert len(added) == 1, added
            grid = session.project.datasets[added.pop()]
            assert grid.structure_id == orbitals.structure_id
            assert grid.status.value == "complete"
            assert numpy.isfinite(grid.data.values).all()
            assert not ui._JOBS and not list(Path(session.temporary_root).glob("wavefunction-*"))
            return grid

        mo = compute("wavefunction.mo_grid", orbitals)
        assert ui._selected_orbitals(session, settings).id == orbitals.id
        density = compute("wavefunction.electron_density_grid", orbitals)
        matrices = tuple(value for value in session.project.density_matrices.values()
                         if value.structure_id == orbitals.structure_id)
        total = next((value for value in matrices if value.spin_role.value == "total"), None)
        esp = compute("wavefunction.esp_grid", total) if total else compute(
            "wavefunction.esp_from_orbitals_grid", orbitals)
        if total:
            matrix_density = compute("wavefunction.density_matrix_grid", total)
            numpy.testing.assert_allclose(density.data.values, matrix_density.data.values,
                                          rtol=2.e-5, atol=2.e-6)
        for matrix in matrices:
            if matrix.spin_role.value == "spin":
                compute("wavefunction.density_matrix_grid", matrix)
        results[name] = {"spin": settings.channel, "points": int(numpy.size(mo.data.values)),
                         "density_max": float(numpy.max(density.data.values)),
                         "esp_min": float(numpy.min(esp.data.values))}
        assert session.dirty
    assert len(session.project.orbital_sets) == 3
    # A Browser switch must not reset the orbital just selected by the user.
    orbitals = next(iter(session.project.orbital_sets.values()))
    session.active_entity_id = orbitals.id
    settings.orbital_number = 2
    selected = compute("wavefunction.mo_grid", orbitals)
    assert settings.orbital_number == 2
    record = session.project.provenance[selected.provenance_ids[0]]
    assert dict(record.parameters)["orbital_index"] == 1
    session.mark_clean()  # Only this test's disposable project.
    session_ui.close_scene_session(scene)
    return results


results = {}
for iteration in range(2):
    ChemBlender.register()
    try:
        results[f"cycle_{iteration + 1}"] = check_ui_and_tasks()
        if iteration == 0 and args.worker_python:
            results["real_files"] = check_real_ui()
    finally:
        ChemBlender.unregister()
    assert not hasattr(bpy.types.Scene, "chemblender_wavefunction")
    assert not ui._JOBS
print("WORKBENCH_PHASE_B_UI_PASSED " + json.dumps(results, sort_keys=True))
