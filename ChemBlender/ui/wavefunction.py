"""Orbital controls and isolated, cancellable external wavefunction work."""

import os
import json
import time
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from ..core import (
    ArrayData, AtomicProperty, DensityMatrix, DensityMatrixSpin,
    Grid3D, ImportBatch, close_project, open_project, save_project,
)
from ..core.orbital_browser import orbital_rows, suggest_grid, estimate_grid_memory
from ..core.worker_protocol import EntityReference, WorkerRequest, WorkerStatus
from ..worker_client import start_worker
from .tasks import Task, TaskState, TaskWorker


_SCENE_PROPERTY_NAME = "chemblender_wavefunction"
_OWNED_SCENE_PROPERTY = None
_JOBS = {}
_ENUM_ITEMS = {}
_GRID_OPERATIONS = {
    "wavefunction.mo_grid": ("molecular_orbital", "inverse_bohr_to_three_halves", "mo"),
    "wavefunction.electron_density_grid": ("electron_density", "electron_per_cubic_bohr", "density"),
    "wavefunction.density_matrix_grid": (None, "electron_per_cubic_bohr", "density"),
    "wavefunction.esp_grid": ("electrostatic_potential", "hartree_per_elementary_charge", "esp"),
    "wavefunction.esp_from_orbitals_grid": ("electrostatic_potential", "hartree_per_elementary_charge", "esp"),
}


def worker_configuration(settings):
    """Resolve the user's external interpreter and checkout without installing."""
    if not settings.worker_python or not settings.worker_repository:
        raise ValueError("Set Worker Python and Worker Repository before computing")
    executable = Path(settings.worker_python).expanduser().resolve(strict=True)
    repository = Path(settings.worker_repository).expanduser().resolve(strict=True)
    if not executable.is_file():
        raise ValueError("Worker Python must be an executable file")
    if not (repository / "worker" / "runner.py").is_file() or not (
        repository / "ChemBlender" / "core"
    ).is_dir():
        raise ValueError("Worker Repository must contain worker/runner.py and ChemBlender/core")
    return executable, repository


def _entities(project):
    return {
        identity: entity
        for field in fields(project)
        if isinstance(registry := getattr(project, field.name), dict)
        for identity, entity in registry.items()
    }


def _freeze_inputs(project, inputs):
    """Detach the required entity graph before other UI actions can close its maps."""
    import numpy

    entities = _entities(project)

    def references(value):
        if isinstance(value, UUID):
            if value in entities:
                yield value
        elif isinstance(value, ArrayData):
            return
        elif is_dataclass(value):
            for field in fields(value):
                yield from references(getattr(value, field.name))
        elif isinstance(value, dict):
            for item in value.values():
                yield from references(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                yield from references(item)

    required = set()
    pending = [value.id for value in inputs]
    if any(value.id not in entities or entities[value.id].revision != value.revision
           for value in inputs):
        raise ValueError("wavefunction inputs are missing or stale")
    while pending:
        identity = pending.pop()
        if identity not in required:
            required.add(identity)
            pending.extend(references(entities[identity]))

    def detach(value):
        if isinstance(value, ArrayData):
            values = value.values
            was_unloaded = getattr(values, "loaded", None) is False
            try:
                return replace(value, values=numpy.asarray(values).copy())
            finally:
                if was_unloaded:
                    values.close()
        if is_dataclass(value):
            return replace(value, **{field.name: detach(getattr(value, field.name))
                                    for field in fields(value) if field.init})
        if isinstance(value, tuple):
            return tuple(map(detach, value))
        if isinstance(value, list):
            return list(map(detach, value))
        if isinstance(value, dict):
            return {key: detach(item) for key, item in value.items()}
        return value

    return replace(project, **{
        field.name: {identity: detach(entity) for identity, entity in registry.items()
                     if identity in required}
        for field in fields(project)
        if isinstance(registry := getattr(project, field.name), dict)
    })


def wavefunction_inputs(project, operation_id, source_id, *, nuclear_charge_id=None):
    if operation_id not in _GRID_OPERATIONS:
        raise ValueError("unsupported wavefunction operation")
    registry = (
        project.density_matrices
        if operation_id in {"wavefunction.density_matrix_grid", "wavefunction.esp_grid"}
        else project.orbital_sets
    )
    source = registry.get(source_id)
    if source is None:
        raise ValueError("select a compatible orbital set or density matrix")
    structure = project.structures[source.structure_id]
    basis = project.basis_sets[source.basis_set_id]
    if structure.coordinates.unit != "bohr":
        raise ValueError("wavefunction inputs must use bohr coordinates")
    inputs = (structure, basis, source)
    if operation_id in {"wavefunction.esp_grid", "wavefunction.esp_from_orbitals_grid"}:
        if isinstance(source, DensityMatrix) and source.spin_role is not DensityMatrixSpin.TOTAL:
            raise ValueError("ESP requires a total density matrix")
        charges = project.datasets.get(nuclear_charge_id)
        if (
            not isinstance(charges, AtomicProperty)
            or charges.structure_id != structure.id
            or charges.semantic_role != "nuclear_charge"
            or charges.data.unit != "elementary_charge"
            or charges.status.value != "complete"
        ):
            raise ValueError("Select an explicit effective nuclear-charge dataset; atomic numbers are not a substitute")
        inputs += (charges,)
    return inputs


def _detached_output(project, request, result):
    """Accept only the operation's declared new scientific data and provenance."""
    import numpy

    if result.request_id != request.request_id or result.status is not WorkerStatus.SUCCESS:
        raise ValueError("worker result does not match the successful request")
    if result.artifacts:
        raise ValueError("wavefunction worker must return scientific entities, not artifacts")
    entities = _entities(project)
    if any(entities.get(value.entity_id) is None
           or entities[value.entity_id].revision != value.revision for value in request.inputs):
        raise ValueError("worker changed its frozen input revisions")
    outputs = []
    for reference in result.outputs:
        entity = entities.get(reference.entity_id)
        if entity is None or entity.revision != reference.revision:
            raise ValueError("worker output is missing or stale")
        outputs.append(entity)
    grids = tuple(value for value in outputs if isinstance(value, Grid3D))
    matrices = tuple(value for value in outputs if isinstance(value, DensityMatrix))
    provenance = tuple(value for value in outputs if value.id in project.provenance)
    if len(grids) != 1 or len(outputs) != len(grids) + len(matrices) + len(provenance):
        raise ValueError("worker output must contain one Grid3D and its provenance")
    derived_rdm = request.operation_id == "wavefunction.esp_from_orbitals_grid"
    if len(matrices) != int(derived_rdm):
        raise ValueError("unexpected worker density matrix output")
    if len(provenance) != 1 + int(derived_rdm):
        raise ValueError("worker must return the complete derivation provenance")
    grid = grids[0]
    role, unit, _operation = _GRID_OPERATIONS[request.operation_id]
    if role is None:
        source = project.density_matrices[request.inputs[2].entity_id]
        role = "spin_density" if source.spin_role is DensityMatrixSpin.SPIN else "electron_density"
    if (
        grid.semantic_role != role or grid.data.unit != unit
        or grid.structure_id != request.inputs[0].entity_id
        or grid.coordinate_unit != "bohr" or grid.status.value != "complete"
        or result.metadata.get("dataset_id") != str(grid.id)
        or result.cache_key != grid.revision
    ):
        raise ValueError("worker grid semantics or identity do not match the request")
    for name, actual in (("origin", grid.origin), ("step_vectors", grid.step_vectors),
                         ("shape", grid.grid_shape)):
        if not numpy.array_equal(actual, request.parameters[name]):
            raise ValueError("worker changed the requested grid geometry")
    references = set(grid.provenance_ids)
    for matrix in matrices:
        if (matrix.structure_id != request.inputs[0].entity_id
                or matrix.basis_set_id != request.inputs[1].entity_id
                or matrix.spin_role is not DensityMatrixSpin.TOTAL
                or matrix.level.value != request.parameters["density_level"]):
            raise ValueError("derived density matrix does not match the explicit request")
        references.update(matrix.provenance_ids)
    if references != {value.id for value in provenance}:
        raise ValueError("worker provenance inventory is incomplete")
    allowed_parents = {value.entity_id for value in request.inputs} | {value.id for value in matrices}
    if any(not set(value.parent_ids) <= allowed_parents for value in provenance):
        raise ValueError("worker provenance refers to unrelated inputs")
    if not {value.entity_id for value in request.inputs} <= {
        identity for value in provenance for identity in value.parent_ids
    }:
        raise ValueError("worker provenance omits requested inputs")

    def detach(value):
        values = numpy.array(value.data.values, copy=True)
        if numpy.iscomplexobj(values) or not numpy.isfinite(values).all():
            raise ValueError("worker output must contain finite real values")
        return replace(value, data=replace(value.data, values=values))

    return ImportBatch(datasets=(detach(grid),), density_matrices=tuple(map(detach, matrices)),
                       provenance=provenance)


class WavefunctionJob:
    """Freeze needed inputs on the main thread; write only to a private sidecar."""

    def __init__(self, session, operation_id, inputs, parameters, *, python_executable,
                 working_directory):
        if operation_id not in _GRID_OPERATIONS:
            raise ValueError("unsupported wavefunction operation")
        if session.id in _JOBS:
            raise ValueError("A wavefunction task is already running for this project")
        self.session_id = session.id
        self.project = session.project
        self._input_ids = frozenset(_entities(self.project))
        self._owner_root = Path(session.temporary_root).resolve(strict=True)
        request = WorkerRequest(
            uuid4(), str(self._owner_root / "project.cbq"), self.project.id,
            self.project.schema_version, operation_id, "1",
            tuple(EntityReference(value.id, value.revision) for value in inputs), parameters,
        )
        self.snapshot = _freeze_inputs(self.project, inputs)
        self._temporary = TemporaryDirectory(prefix="wavefunction-", dir=self._owner_root)
        self.root = Path(self._temporary.name)
        self.request = replace(request, project_locator=str(self.root / "project.cbq"))
        self.python_executable = Path(python_executable)
        self.working_directory = Path(working_directory)
        self.task = Task()
        self.worker = TaskWorker(self.task, self._run)
        self._closed = self._published = False
        self._cancel_requested = False
        self._manager = self._timer = None

    def start(self):
        if self.session_id in _JOBS:
            raise RuntimeError("A wavefunction task is already running for this project")
        _JOBS[self.session_id] = self
        try:
            self.worker.start("saving isolated project")
        except BaseException:
            self.close()
            raise

    def _run(self, cancelled, progress):
        if cancelled():
            return None
        save_project(self.request.project_locator, self.snapshot)
        progress("evaluating wavefunction", 0.1)
        if cancelled():
            return None
        handle = start_worker(self.request, self.root, python_executable=self.python_executable,
                              working_directory=self.working_directory)
        cancel_started = None
        previous_progress = 0.1
        try:
            while True:
                if cancelled():
                    if cancel_started is None:
                        handle.request_cancel()
                        cancel_started = time.monotonic()
                    elif time.monotonic() - cancel_started >= 2.0:
                        handle.terminate()
                        return None
                result = handle.poll()
                if result is not None:
                    break
                current_progress = _worker_progress(handle.request_path.parent / "progress.json")
                if current_progress is not None and current_progress > previous_progress:
                    progress("evaluating wavefunction", current_progress)
                    previous_progress = current_progress
                time.sleep(0.05)
            if cancelled() or result.status is WorkerStatus.CANCELLED:
                self.worker.request_cancel()
                return None
            if result.status is not WorkerStatus.SUCCESS:
                raise RuntimeError(result.error.message)
            handle.wait(timeout=5)
            progress("validating derived data", 0.9)
            output_project = open_project(
                self.request.project_locator, expected_project_id=self.request.project_id,
                expected_schema_version=self.request.project_schema_version,
            )
            try:
                if any(value.entity_id in self._input_ids for value in result.outputs):
                    raise ValueError("worker must not replace preexisting project entities")
                return _detached_output(output_project, self.request, result)
            finally:
                close_project(output_project)
        finally:
            if handle.process.poll() is None:
                handle.terminate()

    def publish(self, session):
        if self._closed or self._published or not self.worker.done:
            raise RuntimeError("wavefunction result is not available for publication")
        if self._cancel_requested:
            raise RuntimeError("wavefunction task was cancelled")
        self.worker.raise_if_failed()
        if self.task.snapshot().state is not TaskState.SUCCEEDED or self.worker.result is None:
            raise RuntimeError("wavefunction task was cancelled")
        if session.id != self.session_id or session.project is not self.project:
            raise ValueError("the active project changed while the worker was running")
        current = _entities(session.project)
        if any(current.get(value.entity_id) is None
               or current[value.entity_id].revision != value.revision
               for value in self.request.inputs):
            raise ValueError("wavefunction inputs changed while the worker was running")
        session.project.commit(self.worker.result)
        self._published = True
        grid = self.worker.result.datasets[0]
        session.active_entity_id = grid.id
        session.mark_dirty("wavefunction")
        return grid

    def cancel(self):
        self._cancel_requested = True
        self.worker.request_cancel()

    def close(self):
        if self._closed:
            return
        self.cancel()
        self.worker.join(None)
        if self._manager is not None:
            if self._timer is not None:
                try:
                    self._manager.event_timer_remove(self._timer)
                except (ReferenceError, RuntimeError, ValueError):
                    pass
                self._timer = None
            try:
                self._manager.progress_end()
            except (ReferenceError, RuntimeError):
                pass
            self._manager = None
        if self.root.is_symlink() or self.root.is_junction() or (
            self.root.resolve(strict=True).parent != self._owner_root
        ):
            raise RuntimeError("refusing to remove an unowned wavefunction workspace")
        self._temporary.cleanup()
        self._closed = True
        if _JOBS.get(self.session_id) is self:
            del _JOBS[self.session_id]


def clear_wavefunction_jobs(session=None):
    failure = None
    for job in tuple(_JOBS.values()):
        if session is None or job.session_id == session.id:
            try:
                job.close()
            except BaseException as error:
                if failure is None:
                    failure = error
    if failure is not None:
        raise failure


def _worker_progress(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(1025)
        if len(raw) > 1024:
            return None
        document = json.loads(raw)
        completed, total = document["completed"], document["total"]
        if type(completed) is not int or type(total) is not int or not 0 <= completed <= total or total <= 0:
            return None
        return 0.1 + 0.75 * completed / total
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _selected_orbitals(session, settings):
    selected = session.project.orbital_sets.get(session.active_entity_id)
    if selected is not None:
        return selected
    try:
        identity = getattr(settings, "orbital_source_uuid", "") or settings.orbital_source
        return session.project.orbital_sets.get(UUID(identity)) or next(
            iter(session.project.orbital_sets.values()), None
        )
    except (ValueError, AttributeError):
        return next(iter(session.project.orbital_sets.values()), None)


def select_wavefunction_source(settings, orbitals, *, reset=True):
    """Keep the selected scientific source when a derived grid becomes active."""
    identity = str(orbitals.id)
    if getattr(settings, "orbital_source_uuid", "") != identity:
        settings.orbital_source_uuid = identity
        if reset:
            settings.orbital_number = 1
            settings.nuclear_charge_uuid = ""
            settings.density_level = "UNSET"
    if settings.channel not in {value.label for value in orbitals.channels}:
        settings.channel = orbitals.channels[0].label


def _enum_number(items, identity, *, default=0):
    return next((index for index, value in enumerate(items) if value[0] == identity), default)


def _grid_parameters(settings):
    from math import isfinite

    spacing = float(settings.spacing)
    origin = [float(value) for value in settings.origin]
    if not isfinite(spacing) or spacing <= 0 or not all(map(isfinite, origin)):
        raise ValueError("Grid origin and spacing must be finite; spacing must be positive")
    return {"origin": origin,
            "step_vectors": [[spacing, 0., 0.], [0., spacing, 0.], [0., 0., spacing]],
            "shape": list(settings.shape), "chunk_size": 4096}


def operation_memory(project, source, operation_id, parameters):
    return estimate_grid_memory(parameters["shape"],
        project.basis_sets[source.basis_set_id].basis_function_count,
        block_size=parameters["chunk_size"], operation=_GRID_OPERATIONS[operation_id][2],
        orbital_count=max(value.coefficients.shape[0] for value in source.channels)
        if operation_id == "wavefunction.electron_density_grid" else 1)


try:
    import bpy
    from bpy.props import (
        BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty,
        IntVectorProperty, PointerProperty, StringProperty,
    )
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    def _enum_items(items):
        # Blender retains pointers to dynamic enum strings between redraws.
        return _ENUM_ITEMS.setdefault(items, items)

    def _orbital_items(_self, context):
        if context is None:
            return ()
        from .session import get_scene_session
        return _enum_items(tuple((str(value.id), f"{value.kind.value} · {str(value.id)[:8]}", "")
                     for value in get_scene_session(context.scene).project.orbital_sets.values()))

    def _channel_items(self, context):
        if context is None:
            return ()
        from .session import get_scene_session
        orbitals = _selected_orbitals(get_scene_session(context.scene), self)
        numbers = {"restricted": 0, "alpha": 1, "beta": 2, "generalized": 3}
        return _enum_items(tuple((value.label, value.label, "", numbers[value.label])
                                for value in orbitals.channels)) if orbitals else ()

    def _charge_items(self, context):
        if context is None:
            return ()
        from .session import get_scene_session
        session = get_scene_session(context.scene)
        source = session.project.density_matrices.get(session.active_entity_id)
        source = source or _selected_orbitals(session, self)
        return _enum_items((("NONE", "Select effective nuclear charges", ""),) + tuple(
            (str(value.id), f"Nuclear charges · {str(value.id)[:8]}", "")
            for value in session.project.datasets.values()
            if isinstance(value, AtomicProperty) and value.semantic_role == "nuclear_charge"
            and value.status.value == "complete" and source is not None
            and value.structure_id == source.structure_id
            and value.data.unit == "elementary_charge"
        ))

    def _orbital_get(self):
        return _enum_number(_orbital_items(self, bpy.context), self.orbital_source_uuid)

    def _orbital_set(self, value):
        from .session import get_scene_session
        items = _orbital_items(self, bpy.context)
        if not 0 <= value < len(items):
            raise ValueError("orbital source selection is stale")
        orbitals = get_scene_session(bpy.context.scene).project.orbital_sets[UUID(items[value][0])]
        select_wavefunction_source(self, orbitals)

    def _charge_get(self):
        return _enum_number(_charge_items(self, bpy.context), self.nuclear_charge_uuid)

    def _charge_set(self, value):
        items = _charge_items(self, bpy.context)
        if not 0 <= value < len(items):
            raise ValueError("nuclear charge selection is stale")
        self.nuclear_charge_uuid = "" if value == 0 else items[value][0]

    class CHEMBLENDER_PG_wavefunction(bpy.types.PropertyGroup):
        worker_python: StringProperty(name="Worker Python", subtype="FILE_PATH",
                                     default=os.environ.get("CHEMBLENDER_WORKER_PYTHON", ""))
        worker_repository: StringProperty(name="Worker Repository", subtype="DIR_PATH",
            default=str(Path(__file__).resolve().parents[2])
            if (Path(__file__).resolve().parents[2] / "worker" / "runner.py").is_file() else "")
        show_worker: BoolProperty(name="Worker Setup", default=False)
        orbital_source_uuid: StringProperty(options={"HIDDEN"})
        nuclear_charge_uuid: StringProperty(options={"HIDDEN"})
        orbital_source: EnumProperty(name="Orbital Set", items=_orbital_items,
                                     get=_orbital_get, set=_orbital_set)
        channel: EnumProperty(name="Spin", items=_channel_items)
        orbital_number: IntProperty(name="Orbital", default=1, min=1)
        origin: FloatVectorProperty(name="Origin (bohr)", size=3, default=(-6., -6., -6.))
        spacing: FloatProperty(name="Step (bohr)", default=.25, min=1.e-5)
        shape: IntVectorProperty(name="Grid Counts", size=3, default=(49, 49, 49), min=2)
        padding: FloatProperty(name="Padding (bohr)", default=6., min=0.)
        memory_limit_mb: IntProperty(name="Memory Budget (MiB)", default=1024, min=64)
        nuclear_charge: EnumProperty(name="Effective Nuclear Charges", items=_charge_items,
                                     get=_charge_get, set=_charge_set)
        density_level: EnumProperty(name="Density Level", default="UNSET", items=(
            ("UNSET", "Select density level", "Do not infer from orbital occupations"),
            ("scf", "SCF", "Explicitly identify the source as SCF"),
            ("post_scf", "Post SCF", "Explicitly identify the source as post-SCF"),
        ))
        export_orbitals: StringProperty(name="Orbitals (1-based)", default="1",
            description="Explicit numbers and ranges, for example 5,6 or 3-6; current spin only")
        export_directory: StringProperty(name="New Output Directory", subtype="DIR_PATH")
        export_isovalue: FloatProperty(name="Phase Isovalue", default=.05, min=1.e-8)
        export_positive_color: FloatVectorProperty(name="Positive Phase", subtype="COLOR",
            size=4, default=(.15, .35, .95, 1.), min=0., max=1.)
        export_negative_color: FloatVectorProperty(name="Negative Phase", subtype="COLOR",
            size=4, default=(.95, .20, .15, 1.), min=0., max=1.)
        export_opacity: FloatProperty(name="Phase Opacity", default=1., min=0., max=1.)

    class CHEMBLENDER_OT_wavefunction(bpy.types.Operator):
        bl_idname = "chemblender.wavefunction"
        bl_label = "Wavefunction"
        action: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        operation_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        source_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        orbital_index: IntProperty(options={"HIDDEN", "SKIP_SAVE"})

        def _start(self, context):
            from .session import get_scene_session
            from .orbital_export import _EXPORTS
            session = get_scene_session(context.scene)
            if session.id in _EXPORTS:
                raise ValueError("Wait for the current orbital image export")
            settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
            executable, repository = worker_configuration(settings)
            orbitals = session.project.orbital_sets.get(UUID(self.source_id))
            if orbitals is not None:
                select_wavefunction_source(settings, orbitals, reset=False)
            inputs = wavefunction_inputs(session.project, self.operation_id, UUID(self.source_id),
                nuclear_charge_id=UUID(settings.nuclear_charge)
                if settings.nuclear_charge not in {"", "NONE"} else None)
            parameters = _grid_parameters(settings)
            if self.operation_id == "wavefunction.mo_grid":
                channel = settings.channel or inputs[2].channels[0].label
                rows = orbital_rows(session.project, inputs[2], channel)
                index = settings.orbital_number - 1
                if not 0 <= index < len(rows):
                    raise ValueError("Orbital number is outside the selected spin channel")
                if rows[index].evaluation_error:
                    raise ValueError(rows[index].evaluation_error)
                parameters.update(channel=channel, orbital_index=index)
            if self.operation_id == "wavefunction.esp_from_orbitals_grid":
                if settings.density_level == "UNSET":
                    raise ValueError("Select the source density level explicitly")
                parameters["density_level"] = settings.density_level
            estimate = operation_memory(session.project, inputs[2], self.operation_id, parameters)
            if estimate["estimated_bytes"] > settings.memory_limit_mb * 1024 ** 2:
                raise ValueError("Grid estimate exceeds the configured memory budget")
            job = WavefunctionJob(session, self.operation_id, inputs, parameters,
                python_executable=executable, working_directory=repository)
            self._session, self._job = session, job
            job.start()
            return job

        def _finish(self, context):
            from .properties import advance_browser_revision
            job = self._job
            try:
                if job._closed or job._cancel_requested or job.task.snapshot().state is TaskState.CANCELLED:
                    self.report({"INFO"}, "Wavefunction task cancelled")
                    return {"CANCELLED"}
                grid = job.publish(self._session)
                context.scene.chemblender_project_browser.active_entity_id = str(grid.id)
                advance_browser_revision(self._session)
                self.report({"INFO"}, f"Created {grid.semantic_role.replace('_', ' ')}")
                return {"FINISHED"}
            finally:
                job.close()

        def execute(self, context):
            from .session import get_scene_session
            try:
                session = get_scene_session(context.scene)
                settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
                if self.action == "select":
                    settings.orbital_number = self.orbital_index + 1
                    return {"FINISHED"}
                if self.action == "use_grid":
                    from .properties import advance_browser_revision
                    grid_id = UUID(self.source_id)
                    if not isinstance(session.project.datasets.get(grid_id), Grid3D):
                        raise ValueError("The cached Grid3D is no longer available")
                    session.active_entity_id = grid_id
                    context.scene.chemblender_project_browser.active_entity_id = str(grid_id)
                    advance_browser_revision(session)
                    return {"FINISHED"}
                if self.action == "cancel":
                    job = _JOBS.get(session.id)
                    if job is not None:
                        job.cancel()
                    return {"FINISHED"}
                if self.action == "fit":
                    source = session.project.density_matrices.get(session.active_entity_id)
                    source = source or _selected_orbitals(session, settings)
                    if source is None:
                        raise ValueError("Select an orbital set or density matrix")
                    values = suggest_grid(session.project.structures[source.structure_id],
                                          spacing=settings.spacing, padding=settings.padding)
                    settings.origin, settings.shape = values["origin"], values["shape"]
                    return {"FINISHED"}
                job = self._start(context)
                job.worker.join(None)
                return self._finish(context)
            except Exception as error:
                if isinstance(error, MemoryError):
                    raise
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}

        def invoke(self, context, _event):
            if self.action != "compute" or bpy.app.background:
                return self.execute(context)
            try:
                job = self._start(context)
                job._manager = context.window_manager
                job._manager.progress_begin(0, 100)
                job._timer = job._manager.event_timer_add(.1, window=context.window)
                job._manager.modal_handler_add(self)
                return {"RUNNING_MODAL"}
            except Exception as error:
                if hasattr(self, "_job"):
                    self._job.close()
                if isinstance(error, MemoryError):
                    raise
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}

        def modal(self, context, event):
            if self._job._closed:
                return {"CANCELLED"}
            if event.type == "ESC":
                self._job.cancel()
            if event.type != "TIMER":
                return {"RUNNING_MODAL"}
            if not self._job.worker.done:
                context.window_manager.progress_update(int(self._job.task.snapshot().progress * 100))
                return {"RUNNING_MODAL"}
            try:
                return self._finish(context)
            except Exception as error:
                if isinstance(error, MemoryError):
                    raise
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}

        def cancel(self, _context):
            if hasattr(self, "_job"):
                self._job.close()

    def _button(layout, text, *, action="compute", operation_id="", source_id="", index=0):
        button = layout.operator(CHEMBLENDER_OT_wavefunction.bl_idname, text=text)
        button.action, button.operation_id = action, operation_id
        button.source_id, button.orbital_index = str(source_id), index

    def _compute_button(layout, text, *, project, settings, operation_id, source):
        memory = operation_memory(project, source, operation_id, _grid_parameters(settings))
        row = layout.row()
        row.enabled = memory["estimated_bytes"] <= settings.memory_limit_mb * 1024 ** 2
        _button(row, f"{text} ({memory['estimated_bytes'] / 1024**2:.1f} MiB est.)",
                operation_id=operation_id, source_id=source.id)

    def draw_wavefunction_controls(layout, context, session):
        from .wavefunction_import import draw_wavefunction_import
        from .orbital_export import _EXPORTS, draw_orbital_export
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        layout.separator()
        layout.label(text="Wavefunction")
        layout.prop(settings, "show_worker")
        if settings.show_worker:
            layout.prop(settings, "worker_python")
            layout.prop(settings, "worker_repository")
        draw_wavefunction_import(layout, context, session)
        orbitals = _selected_orbitals(session, settings)
        selected_matrix = session.project.density_matrices.get(session.active_entity_id)
        if orbitals is None and selected_matrix is None:
            return
        if orbitals is not None and session.active_entity_id not in session.project.orbital_sets:
            layout.prop(settings, "orbital_source")
        for name in ("origin", "spacing", "shape", "padding"):
            layout.prop(settings, name)
        _button(layout, "Fit Grid to Molecule", action="fit")
        layout.prop(settings, "memory_limit_mb")
        source = selected_matrix or orbitals
        try:
            parameters = _grid_parameters(settings)
            estimate = estimate_grid_memory(parameters["shape"],
                session.project.basis_sets[source.basis_set_id].basis_function_count,
                block_size=parameters["chunk_size"])
            layout.label(text=f"{estimate['point_count']:,} points; MO estimate {estimate['estimated_bytes'] / 1024**2:.1f} MiB")
            end = tuple(round(a + settings.spacing * (n - 1), 5)
                        for a, n in zip(settings.origin, settings.shape))
            layout.label(text=f"Grid end (bohr): {end}")
        except (TypeError, ValueError) as error:
            layout.label(text=str(error), icon="ERROR")
            return
        job = _JOBS.get(session.id)
        if job is not None:
            status = job.task.snapshot()
            layout.label(text=f"{status.stage}: {status.state.value}")
            _button(layout, "Cancel Calculation", action="cancel")
        controls = layout.column()
        controls.enabled = job is None and session.id not in _EXPORTS
        if orbitals is not None:
            controls.prop(settings, "channel")
            channel = settings.channel or orbitals.channels[0].label
            rows = orbital_rows(session.project, orbitals, channel, grid_parameters=parameters)
            controls.label(text=f"Source: {rows[0].source}" if rows else "No orbitals")
            controls.prop(settings, "orbital_number")
            start = ((settings.orbital_number - 1) // 12) * 12
            controls.label(text="Orbital / Energy (hartree) / Occupation / Spin / Grid cache")
            for row in rows[start:start + 12]:
                energy = "unknown" if row.energy is None else f"{row.energy:.6f}"
                occupation = "unknown" if row.occupation is None else f"{row.occupation:g}"
                cached = "cached" if row.cached_dataset_ids else "not computed"
                _button(controls, f"{row.index + 1}  {energy}  {occupation}  {row.spin}  {cached} {' '.join(row.labels)}",
                        action="select", index=row.index)
            frontier = controls.row(align=True)
            for label in ("HOMO", "LUMO", "SOMO"):
                match = next((row for row in rows if label in row.labels), None)
                if match is not None:
                    _button(frontier, label, action="select", index=match.index)
            compute = controls.column()
            compute.enabled = bool(rows) and not rows[0].evaluation_error
            if rows and rows[0].evaluation_error:
                controls.label(text=rows[0].evaluation_error, icon="ERROR")
            selected = settings.orbital_number - 1
            if 0 <= selected < len(rows) and rows[selected].cached_dataset_ids:
                _button(compute, "Use Cached MO Grid", action="use_grid",
                        source_id=rows[selected].cached_dataset_ids[0])
            _compute_button(compute, "Evaluate Selected MO", project=session.project, settings=settings,
                            operation_id="wavefunction.mo_grid", source=orbitals)
            density = compute.column()
            density.enabled = all(value.occupations is not None for value in orbitals.channels)
            _compute_button(density, "Electron Density from Occupations", project=session.project, settings=settings,
                            operation_id="wavefunction.electron_density_grid", source=orbitals)
        matrices = (selected_matrix,) if selected_matrix is not None else tuple(
            value for value in session.project.density_matrices.values()
            if value.structure_id == source.structure_id and value.basis_set_id == source.basis_set_id
        )
        controls.prop(settings, "nuclear_charge")
        for matrix in matrices:
            _compute_button(controls, f"{matrix.spin_role.value.title()} Density · {matrix.level.value} · {str(matrix.id)[:8]}",
                    project=session.project, settings=settings,
                    operation_id="wavefunction.density_matrix_grid", source=matrix)
            if matrix.spin_role is DensityMatrixSpin.TOTAL:
                esp = controls.row()
                esp.enabled = settings.nuclear_charge not in {"", "NONE"}
                _compute_button(esp, f"ESP · {matrix.level.value} · {str(matrix.id)[:8]}",
                        project=session.project, settings=settings,
                        operation_id="wavefunction.esp_grid", source=matrix)
        if orbitals is not None and not any(matrix.spin_role is DensityMatrixSpin.TOTAL for matrix in matrices):
            controls.label(text="ESP will derive a total density matrix from occupations.")
            controls.prop(settings, "density_level")
            derived = controls.row()
            derived.enabled = (settings.density_level != "UNSET"
                               and settings.nuclear_charge not in {"", "NONE"}
                               and bool(rows) and not rows[0].evaluation_error)
            _compute_button(derived, "ESP from Occupations", project=session.project, settings=settings,
                            operation_id="wavefunction.esp_from_orbitals_grid", source=orbitals)
        if orbitals is not None:
            draw_orbital_export(layout, context, session)

    def register():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        from .session import register_session_cleanup
        current = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if _OWNED_SCENE_PROPERTY is not None:
            if not _same_scene_property(current, _OWNED_SCENE_PROPERTY):
                raise RuntimeError("Wavefunction Scene property is no longer owned")
        elif current is not None:
            raise RuntimeError("Wavefunction Scene property is already owned")
        else:
            setattr(bpy.types.Scene, _SCENE_PROPERTY_NAME,
                    PointerProperty(type=CHEMBLENDER_PG_wavefunction))
            _OWNED_SCENE_PROPERTY = _scene_property_identity(_SCENE_PROPERTY_NAME)
        register_session_cleanup(clear_wavefunction_jobs)

    def unregister():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        from .session import unregister_session_cleanup
        clear_wavefunction_jobs()
        unregister_session_cleanup(clear_wavefunction_jobs)
        if _OWNED_SCENE_PROPERTY is not None and _same_scene_property(
            _scene_property_identity(_SCENE_PROPERTY_NAME), _OWNED_SCENE_PROPERTY
        ):
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
        _OWNED_SCENE_PROPERTY = None
        _ENUM_ITEMS.clear()


__all__ = ("WavefunctionJob", "clear_wavefunction_jobs", "wavefunction_inputs", "worker_configuration",
           "select_wavefunction_source")
if bpy is not None:
    __all__ += ("CHEMBLENDER_PG_wavefunction", "CHEMBLENDER_OT_wavefunction", "draw_wavefunction_controls")
