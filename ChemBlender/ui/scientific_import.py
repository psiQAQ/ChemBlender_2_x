"""Explicit external readers for molecular outputs, VASP and phonopy files."""

import json
import math
import time
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from . import wavefunction_import as imports


def load_fermi_batch(
    directory, *, python_executable, repository, project_id, schema_version,
    temp_parent, spin_index=0, interpolation_factor=1,
    is_cancelled=lambda: False, progress=lambda _stage, _value: None,
):
    """Evaluate a copied text bundle; detach only the declared Fermi outputs."""
    from ..core import QCProject, close_project, open_project, save_project
    from ..core.pyprocar_file import OPTIONAL_FILES, REQUIRED_FILES
    from ..core.worker_protocol import WORKER_VERSION, WorkerRequest, WorkerStatus
    from .wavefunction import _worker_progress

    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("select a VASP Fermi input directory")
    if type(spin_index) is not int or spin_index not in (0, 1) or type(interpolation_factor) is not int or interpolation_factor != 1:
        raise ValueError("Fermi extraction supports spin 0/1 and interpolation factor 1")
    paths = {name: root / name for name in sorted(REQUIRED_FILES | OPTIONAL_FILES)
             if name in REQUIRED_FILES or (root / name).is_file()}
    if any(path.is_symlink() or not path.is_file() for path in paths.values()):
        raise ValueError("Fermi input requires regular INCAR/KPOINTS/POSCAR/OUTCAR/PROCAR files")
    hashes = {name: imports._source_hash(path, is_cancelled) for name, path in paths.items()}
    artifacts = {name: {"path": name, "sha256": hashes[name]} for name in paths}
    if is_cancelled():
        raise imports.ImportCancelled("Fermi import cancelled")
    with TemporaryDirectory(prefix="fm-", dir=temp_parent) as workspace:
        request = WorkerRequest(uuid4(), str(Path(workspace) / "project.cbq"), project_id,
            schema_version, "periodic.fermi_surface", "1", (),
            {"source_artifacts": artifacts, "spin_index": spin_index,
             "interpolation_factor": interpolation_factor})
        save_project(request.project_locator, QCProject(project_id, schema_version))
        handle = imports.start_worker(request, workspace, python_executable=python_executable,
                                      working_directory=repository, staged_inputs=paths)
        try:
            progress("extract Fermi surface", .1)
            while True:
                if is_cancelled():
                    handle.request_cancel()
                    raise imports.ImportCancelled("Fermi import cancelled")
                result = handle.poll()
                if result is not None:
                    break
                current = _worker_progress(handle.request_path.parent / "progress.json")
                if current is not None:
                    progress("extract Fermi surface", .1 + .7 * current)
                time.sleep(.05)
            handle.wait(timeout=5)
            if is_cancelled():
                raise imports.ImportCancelled("Fermi import cancelled")
            if result.request_id != request.request_id or result.worker_version != WORKER_VERSION:
                raise ValueError("Fermi worker result identity mismatch")
            if result.status is not WorkerStatus.SUCCESS:
                message = result.error.message if result.error is not None else result.status.value
                raise RuntimeError(f"Fermi worker ({python_executable}): {message}")
            for name, original in paths.items():
                if imports._source_hash(original, is_cancelled) != hashes[name] or imports._source_hash(
                    handle.request_path.parent / name, is_cancelled
                ) != hashes[name]:
                    raise ValueError("Fermi source changed during import")
            project = open_project(request.project_locator, expected_project_id=project_id,
                                   expected_schema_version=schema_version)
            try:
                progress("verify Fermi data", .9)
                return _fermi_output(project, request, result, root, paths)
            finally:
                close_project(project)
        finally:
            handle.terminate()


def _fermi_output(project, request, result, directory, source_paths):
    from ..core import BandStructure, FermiSurfaceMesh, ImportBatch
    from .wavefunction import _entities, _freeze_inputs

    entities = _entities(project)
    output_ids = {item.entity_id for item in result.outputs}
    if result.artifacts or len(result.outputs) != len(output_ids) or output_ids != set(entities):
        raise ValueError("Fermi worker returned an unexpected entity inventory")
    if any(entities[item.entity_id].revision != item.revision for item in result.outputs):
        raise ValueError("Fermi output revision mismatch")
    bands = tuple(item for item in project.datasets.values() if isinstance(item, BandStructure))
    surfaces = tuple(item for item in project.datasets.values() if isinstance(item, FermiSurfaceMesh))
    if len(project.structures) != 1 or len(bands) != 1 or len(surfaces) != 1 or len(project.datasets) != 2 or len(project.provenance) != 2:
        raise ValueError("Fermi output must contain a structure, mesh bands, surface and provenance")
    structure, band, surface = next(iter(project.structures.values())), bands[0], surfaces[0]
    if len(entities) != 5 or result.metadata != {
        "operation": "periodic.fermi_surface@1", "structure_id": str(structure.id),
        "band_structure_id": str(band.id), "fermi_surface_id": str(surface.id),
    } or result.cache_key != band.revision:
        raise ValueError("Fermi worker output identity or metadata mismatch")
    if surface.band_structure_id != band.id or band.structure_id != structure.id or surface.spin_index != request.parameters["spin_index"]:
        raise ValueError("Fermi surface does not match its declared bands or requested spin")
    if band.branches or band.status.value != "complete" or surface.status.value != "complete":
        raise ValueError("Fermi output requires complete data on a uniform mesh")
    expected = request.parameters["source_artifacts"]
    if any(dict(record.parameters).get("source_artifacts") != expected for record in project.provenance.values()):
        raise ValueError("Fermi provenance omits frozen source artifacts")
    frozen = _freeze_inputs(project, tuple(entities.values()))
    originals = {name: {"path": str(path), "sha256": expected[name]["sha256"]}
                 for name, path in source_paths.items()}
    provenance = tuple(replace(record, source=str(directory), parameters=tuple(
        (name, originals if name == "source_artifacts" else value) for name, value in record.parameters
    )) for record in frozen.provenance.values())
    return ImportBatch(structures=tuple(frozen.structures.values()),
                       datasets=tuple(frozen.datasets.values()), provenance=provenance)


def reader_options(settings):
    """Freeze small UI values before starting a worker; never read source arrays."""
    reader = settings.reader_id
    companions, parameters = {}, {}
    if reader == "pymatgen-vasprun-electronic":
        if settings.line_mode not in {"auto", "true", "false"}:
            raise ValueError("invalid VASP calculation mode")
        parameters["line_mode"] = settings.line_mode
        if settings.kpoints_file.strip():
            companions["kpoints"] = settings.kpoints_file
        elif settings.line_mode == "true":
            raise ValueError("line-mode bands require the matching KPOINTS file")
    elif reader == "phonopy-file":
        if not settings.force_sets_file.strip():
            raise ValueError("select the matching FORCE_SETS file")
        companions["force_sets"] = settings.force_sets_file
        points = []
        for row in settings.qpoints.split(";"):
            vector = tuple(float(item.strip()) for item in row.split(","))
            if len(vector) != 3 or not all(math.isfinite(value) for value in vector):
                raise ValueError("q-points require finite fractional triples separated by semicolons")
            points.append(vector)
        parameters["qpoints"] = json.dumps(points, allow_nan=False, separators=(",", ":"))
        parameters["with_group_velocities"] = "true" if settings.with_group_velocities else "false"
        if settings.born_file.strip():
            companions["born"] = settings.born_file
            if settings.use_nac_direction:
                direction = tuple(settings.nac_direction)
                if len(direction) != 3 or not all(math.isfinite(value) for value in direction) or not any(direction):
                    raise ValueError("NAC direction must be finite and nonzero")
                parameters["nac_q_direction"] = json.dumps(direction, allow_nan=False)
            elif any(not any(point) for point in points):
                raise ValueError("Gamma with BORN requires an explicit NAC direction")
        elif settings.use_nac_direction:
            raise ValueError("NAC direction requires an explicit BORN file")
    elif reader != "cclib_output":
        raise ValueError("unsupported external scientific reader")
    return {"reader_id": reader, "canonical_parameters": parameters, "companions": companions}


try:
    import bpy
    from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty
    from bpy_extras.io_utils import ImportHelper
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    _SCENE_PROPERTY_NAME = "chemblender_scientific_import"
    _OWNED_SCENE_PROPERTY = None

    class CHEMBLENDER_PG_scientific_import(bpy.types.PropertyGroup):
        worker_python: StringProperty(name="Scientific Worker Python", subtype="FILE_PATH")
        worker_repository: StringProperty(name="Worker Repository", subtype="DIR_PATH")
        fermi_python: StringProperty(name="Fermi Worker Python", subtype="FILE_PATH")
        fermi_directory: StringProperty(name="Fermi Input Directory", subtype="DIR_PATH")
        fermi_spin: IntProperty(name="Fermi Spin Index", default=0, min=0, max=1)
        reader_id: EnumProperty(name="Input", items=(
            ("cclib_output", "Gaussian / ORCA Output", "Vibrations, excitations and available atom properties"),
            ("pymatgen-vasprun-electronic", "VASP Bands / DOS", "One vasprun calculation and its explicit KPOINTS"),
            ("phonopy-file", "Phonopy Displacements", "VASP-unit YAML, FORCE_SETS and optional BORN"),
        ))
        kpoints_file: StringProperty(name="KPOINTS", subtype="FILE_PATH")
        line_mode: EnumProperty(name="Calculation", default="auto", items=(
            ("auto", "From KPOINTS", "Let the reader recognize the declared path"),
            ("true", "Band Path", "Requires matching line-mode KPOINTS"),
            ("false", "Uniform DOS Mesh", "Keep this calculation separate from a band-path run"),
        ))
        force_sets_file: StringProperty(name="FORCE_SETS", subtype="FILE_PATH")
        born_file: StringProperty(name="BORN (optional)", subtype="FILE_PATH")
        qpoints: StringProperty(name="Fractional q-points", default="0,0,0",
            description="Comma-separated triples; separate q-points with semicolons")
        use_nac_direction: BoolProperty(name="Explicit NAC Direction", default=False)
        nac_direction: FloatVectorProperty(name="NAC Direction", size=3, default=(1, 0, 0))
        with_group_velocities: BoolProperty(name="Group Velocities", default=False)

    class CHEMBLENDER_OT_import_scientific_file(imports.ExternalReaderImportOperator, bpy.types.Operator, ImportHelper):
        bl_idname = "chemblender.import_scientific_file"
        bl_label = "Import Scientific File"
        bl_description = "Parse in the configured external Python and commit the verified result"
        filter_glob: StringProperty(default="*.out;*.log;*.xml;*.gz;*.yaml;*.yml", options={"HIDDEN"})

        def worker_settings(self, context):
            return context.scene.chemblender_scientific_import

        def reader_options(self, context):
            options = reader_options(self.worker_settings(context))
            options["companions"] = {role: bpy.path.abspath(path) for role, path in options["companions"].items()}
            return imports.load_reader_batch, options

        def commit_batch(self, context, batch):
            imports.commit_reader_batch(self._session, batch)
            context.scene.chemblender_scientific_view.preset_id = "AUTO"

        def draw(self, context):
            _draw_reader_options(self.layout, self.worker_settings(context))

    class CHEMBLENDER_OT_import_fermi(imports.ExternalReaderImportOperator, bpy.types.Operator):
        bl_idname = "chemblender.import_fermi"
        bl_label = "Import Fermi Directory"
        bl_description = "Extract a uniform-mesh Fermi surface using explicit VASP text files"
        filepath: StringProperty(options={"HIDDEN"})

        def execute(self, context):
            self.filepath = bpy.path.abspath(context.scene.chemblender_scientific_import.fermi_directory)
            return super().execute(context)

        def worker_settings(self, context):
            settings = context.scene.chemblender_scientific_import
            return SimpleNamespace(worker_python=bpy.path.abspath(settings.fermi_python),
                                   worker_repository=bpy.path.abspath(settings.worker_repository))

        def reader_options(self, context):
            return load_fermi_batch, {"spin_index": context.scene.chemblender_scientific_import.fermi_spin}

        def commit_batch(self, context, batch):
            from ..core import FermiSurfaceMesh
            surface = next(item for item in batch.datasets if isinstance(item, FermiSurfaceMesh))
            self._session.project.commit(batch)
            self._session.mark_dirty("Fermi import")
            self._session.active_entity_id = surface.id
            context.scene.chemblender_scientific_view.preset_id = "AUTO"

    def _draw_reader_options(layout, settings):
        layout.prop(settings, "reader_id")
        if settings.reader_id == "pymatgen-vasprun-electronic":
            layout.prop(settings, "line_mode")
            layout.prop(settings, "kpoints_file")
            layout.label(text="Bands and DOS from separate runs stay separate")
        elif settings.reader_id == "phonopy-file":
            for field in ("force_sets_file", "born_file", "qpoints", "with_group_velocities", "use_nac_direction"):
                layout.prop(settings, field)
            if settings.use_nac_direction:
                layout.prop(settings, "nac_direction")
            layout.label(text="Main file: phonopy_disp.yaml with VASP units")

    def draw_scientific_import(layout, context, session):
        box = layout.box()
        box.label(text="Import Scientific Output")
        settings = context.scene.chemblender_scientific_import
        box.prop(settings, "worker_python")
        box.prop(settings, "worker_repository")
        _draw_reader_options(box, settings)
        row = box.row()
        active = [operator for operator in imports._ACTIVE_IMPORTS if operator._session is session]
        row.enabled = not active
        row.operator("chemblender.import_scientific_file", icon="IMPORT")
        for operator in active:
            snapshot = operator._job.task.snapshot()
            box.label(text=f"{snapshot.stage}: {snapshot.progress:.0%} (Esc to cancel)")
        box.separator()
        for field in ("fermi_python", "fermi_directory", "fermi_spin"):
            box.prop(settings, field)
        row = box.row()
        row.enabled = not active
        row.operator("chemblender.import_fermi", icon="IMPORT")
        box.label(text="Uniform 3D mesh; interpolation factor 1")

    def register():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        current = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if _OWNED_SCENE_PROPERTY is not None and _same_scene_property(current, _OWNED_SCENE_PROPERTY):
            return
        if current is not None:
            raise RuntimeError(f"Scene.{_SCENE_PROPERTY_NAME} is already owned")
        setattr(bpy.types.Scene, _SCENE_PROPERTY_NAME, PointerProperty(type=CHEMBLENDER_PG_scientific_import))
        _OWNED_SCENE_PROPERTY = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if _OWNED_SCENE_PROPERTY is None:
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
            raise RuntimeError("scientific import settings registration failed")

    def unregister():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        for operator in tuple(imports._ACTIVE_IMPORTS):
            if isinstance(operator, (CHEMBLENDER_OT_import_scientific_file, CHEMBLENDER_OT_import_fermi)):
                operator.cancel(None)
        if _OWNED_SCENE_PROPERTY is not None and _same_scene_property(_scene_property_identity(_SCENE_PROPERTY_NAME), _OWNED_SCENE_PROPERTY):
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
        _OWNED_SCENE_PROPERTY = None
