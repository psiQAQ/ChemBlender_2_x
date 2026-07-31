"""Cube/Grid preview, semantic resolution and Scene Preset controls."""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from ..core import (
    DatasetStatus,
    Grid3D,
    ProjectSession,
    builtin_grid_semantic_presets,
    builtin_scene_presets,
    default_grid_isovalue,
    grids_share_affine,
    plan_scene_preset,
    resolve_grid_semantics,
)
from .tasks import Task, TaskWorker


_SCENE_PROPERTY_NAME = "chemblender_grid"
_OWNED_SCENE_PROPERTY = None
_PREVIEW_DATASET_LIMIT = 32
_ACTIVE_VOLUME_OPERATORS = []


def _register_active_volume_operator(operator):
    if operator not in _ACTIVE_VOLUME_OPERATORS:
        _ACTIVE_VOLUME_OPERATORS.append(operator)


def _release_active_volume_operator(operator):
    try:
        _ACTIVE_VOLUME_OPERATORS.remove(operator)
    except ValueError:
        pass


def _cancel_active_volume_operators():
    failure = None
    for operator in tuple(_ACTIVE_VOLUME_OPERATORS):
        for operation in (
            lambda: operator.cancel(None),
            lambda: operator._cache_job.join(None),
            operator._finish_modal,
        ):
            try:
                operation()
            except BaseException as error:
                if failure is None:
                    failure = error
        _release_active_volume_operator(operator)
    if failure is not None:
        raise failure


@dataclass(frozen=True, slots=True)
class GridPreviewSummary:
    dataset_count: int
    source_dataset_ids: tuple[str, ...]
    sample_ranges: tuple[tuple[float, float], ...]
    grid_shape: tuple[int, int, int]
    coordinate_unit: str
    value_unit: str
    quality: str
    default_dataset_index: int = 0


@dataclass(frozen=True, slots=True)
class GridActionAvailability:
    volume: bool
    signed_surface: bool
    property_grid_ids: tuple[UUID, ...]


def _grid_datasets(batch):
    return tuple(value for value in batch.datasets if isinstance(value, Grid3D))


def _source_dataset_ids(batch, grid, count):
    provenance = {value.id: value for value in batch.provenance}
    for provenance_id in grid.provenance_ids:
        record = provenance.get(provenance_id)
        if record is None:
            continue
        identifiers = dict(record.parameters).get("dataset_ids")
        if isinstance(identifiers, (tuple, list)) and len(identifiers) == count:
            values = tuple(
                str(value) for value in identifiers[:_PREVIEW_DATASET_LIMIT]
            )
            return values + (("…",) if count > len(values) else ())
    values = tuple(str(index) for index in range(min(count, _PREVIEW_DATASET_LIMIT)))
    return values + (("…",) if count > len(values) else ())


def _sample_range(values, *, limit=1024):
    import numpy

    flat = numpy.asarray(values).reshape(-1)
    if flat.size > limit:
        indices = numpy.linspace(0, flat.size - 1, limit, dtype=numpy.int64)
        flat = flat[indices]
    return float(numpy.min(flat)), float(numpy.max(flat))


def grid_preview_summary(batch):
    """Return a bounded RNA-safe summary of the first staged Grid3D."""
    grids = _grid_datasets(batch)
    if not grids:
        return None
    grid = grids[0]
    if grid.data.dims[0] == "dataset":
        import numpy

        values = numpy.asarray(grid.data.values)
        count = grid.data.shape[0]
        ranges = tuple(
            _sample_range(values[index])
            for index in range(min(count, _PREVIEW_DATASET_LIMIT))
        )
    else:
        count = 1
        ranges = (_sample_range(grid.data.values),)
    return GridPreviewSummary(
        count,
        _source_dataset_ids(batch, grid, count),
        ranges,
        grid.grid_shape,
        grid.coordinate_unit,
        grid.data.unit,
        grid.status.value,
    )


def _grid(project, grid_id):
    grid = project.datasets.get(grid_id)
    if not isinstance(grid, Grid3D):
        raise ValueError("selected entity is not a Grid3D")
    return grid


def grid_action_availability(project, grid_id):
    grid = _grid(project, grid_id)
    complete = grid.status is DatasetStatus.COMPLETE
    surface_preview = grid.status in {
        DatasetStatus.COMPLETE,
        DatasetStatus.AMBIGUOUS,
    }
    property_ids = (
        tuple(
            value.id
            for value in project.datasets.values()
            if (
                isinstance(value, Grid3D)
                and value.id != grid.id
                and value.status is DatasetStatus.COMPLETE
                and grids_share_affine(grid, value)
            )
        )
        if complete
        else ()
    )
    return GridActionAvailability(
        volume=True,
        signed_surface=surface_preview,
        property_grid_ids=tuple(sorted(property_ids, key=str)),
    )


def resolve_grid_selection(
    session,
    grid_id,
    *,
    dataset_index,
    preset_id,
    value_unit,
):
    if not isinstance(session, ProjectSession):
        raise TypeError("session must be a ProjectSession")
    source = _grid(session.project, grid_id)
    batch = resolve_grid_semantics(
        source,
        dataset_index=dataset_index,
        preset_id=preset_id,
        value_unit=value_unit,
    )
    resolved = batch.datasets[0]
    existing = session.project.datasets.get(resolved.id)
    if existing is None:
        session.project.commit(batch)
        session.mark_dirty("grid_semantics")
        created = True
    else:
        if (
            not isinstance(existing, Grid3D)
            or existing.revision != resolved.revision
        ):
            raise RuntimeError("deterministic grid semantic identity collision")
        resolved = existing
        created = False
    session.active_entity_id = resolved.id
    return resolved, created


def plan_grid_view(
    project,
    grid_id,
    *,
    mode,
    dataset_index=0,
    property_grid_id=None,
    isovalue=0.05,
):
    actions = grid_action_availability(project, grid_id)
    presets = builtin_scene_presets()
    if mode == "volume" and actions.volume:
        return plan_scene_preset(
            presets["grid_volume"],
            project,
            {"grid": grid_id},
            {"dataset_index": dataset_index},
        )
    if mode == "signed_surface" and actions.signed_surface:
        return plan_scene_preset(
            presets["signed_isosurface"],
            project,
            {"grid": grid_id},
            {"dataset_index": dataset_index, "isovalue": isovalue},
        )
    if (
        mode == "property_surface"
        and property_grid_id in actions.property_grid_ids
    ):
        return plan_scene_preset(
            presets["property_on_surface"],
            project,
            {
                "surface_grid": grid_id,
                "property_grid": property_grid_id,
            },
            {
                "surface_dataset_index": dataset_index,
                "property_dataset_index": 0,
                "surface_isovalue": isovalue,
            },
        )
    raise ValueError("selected Grid3D does not support this view")


try:
    import bpy
    from bpy.props import (
        EnumProperty,
        FloatProperty,
        IntProperty,
        PointerProperty,
        StringProperty,
    )
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    _PRESET_ITEMS = tuple(
        (
            preset.preset_id,
            preset.semantic_role.replace("_", " ").title(),
            "",
        )
        for preset in builtin_grid_semantic_presets().values()
    )


    def _unit_items(self, _context):
        preset = builtin_grid_semantic_presets().get(self.preset_id)
        if preset is None:
            return ()
        return tuple(
            (value, value.replace("_", " ").title(), "")
            for value in preset.value_units
        )


    class CHEMBLENDER_PG_grid_settings(bpy.types.PropertyGroup):
        dataset_index: IntProperty(name="Dataset", default=0, min=0)
        preset_id: EnumProperty(
            name="Semantic Preset",
            items=_PRESET_ITEMS,
            default="generic_scalar",
        )
        value_unit: EnumProperty(name="Value Unit", items=_unit_items)
        isovalue: FloatProperty(
            name="Isovalue",
            default=0.05,
            min=1.0e-12,
        )


    def _operator_context(context):
        from .session import get_scene_session

        session = get_scene_session(context.scene)
        grid = _grid(session.project, session.active_entity_id)
        return session, grid, getattr(context.scene, _SCENE_PROPERTY_NAME)


    class CHEMBLENDER_OT_resolve_grid_semantics(bpy.types.Operator):
        bl_idname = "chemblender.resolve_grid_semantics"
        bl_label = "Resolve Grid Semantics"

        def execute(self, context):
            try:
                session, source, settings = _operator_context(context)
                settings.isovalue = default_grid_isovalue(
                    source,
                    dataset_index=settings.dataset_index,
                    preset_id=settings.preset_id,
                )
                _resolved, created = resolve_grid_selection(
                    session,
                    source.id,
                    dataset_index=settings.dataset_index,
                    preset_id=settings.preset_id,
                    value_unit=settings.value_unit,
                )
                from .properties import advance_browser_revision

                advance_browser_revision(session)
                self.report(
                    {"INFO"},
                    "Grid semantics resolved"
                    if created
                    else "Matching resolved Grid3D already exists",
                )
                return {"FINISHED"}
            except Exception as error:
                if isinstance(error, MemoryError):
                    raise
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}


    class CHEMBLENDER_OT_create_grid_view(bpy.types.Operator):
        bl_idname = "chemblender.create_grid_view"
        bl_label = "Create Grid View"

        mode: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        property_grid_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

        @staticmethod
        def _cache_root(session):
            if session.sidecar_path is None:
                root = Path(session.temporary_root) / "view-cache"
                root.mkdir(exist_ok=True)
                return root
            from .view_cache import _durable_cache_root

            return _durable_cache_root(session.sidecar_path)

        def _values(self, context):
            session, grid, settings = _operator_context(context)
            property_grid_id = (
                UUID(self.property_grid_id)
                if self.property_grid_id
                else None
            )
            plan = plan_grid_view(
                session.project,
                grid.id,
                mode=self.mode,
                dataset_index=(
                    settings.dataset_index
                    if grid.data.dims[0] == "dataset"
                    else 0
                ),
                property_grid_id=property_grid_id,
                isovalue=settings.isovalue,
            )
            return session, grid, plan, self._cache_root(session)

        @staticmethod
        def _apply(context, session, plan, cache_root):
            from ..scene_preset_view import apply_scene_preset

            created = apply_scene_preset(
                plan,
                session.project,
                collection=context.collection,
                cache_root=cache_root,
            )
            if created:
                session.active_view_object_name = created[-1].name
            session.mark_dirty("view_cache")
            return created

        def execute(self, context):
            try:
                session, _grid, plan, cache_root = self._values(context)
                created = self._apply(
                    context,
                    session,
                    plan,
                    cache_root,
                )
                self.report({"INFO"}, f"Created {len(created)} Grid view object(s)")
                return {"FINISHED"}
            except Exception as error:
                if isinstance(error, MemoryError):
                    raise
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}

        def invoke(self, context, _event):
            if self.mode != "volume" or bpy.app.background:
                return self.execute(context)
            try:
                session, grid, plan, cache_root = self._values(context)
                dataset_index = dict(plan.settings)["dataset_index"]
                from ..core.grid_cache_service import (
                    VolumeCacheRequest,
                    prepare_volume_cache,
                )
                from ..grid_volume import (
                    _OPENVDB_WRITER,
                    volume_cache_path,
                )

                request = VolumeCacheRequest(
                    volume_cache_path(
                        cache_root,
                        grid,
                        dataset_index=dataset_index,
                    ),
                    dataset_index,
                )
                self._cache_values = (session, plan, cache_root)

                def prepare(cancelled, progress):
                    return prepare_volume_cache(
                        grid,
                        request,
                        writer=_OPENVDB_WRITER,
                        cancelled=cancelled,
                        progress=progress,
                    )

                self._cache_task = Task()
                self._cache_job = TaskWorker(
                    self._cache_task,
                    prepare,
                )
                manager = context.window_manager
                self._cache_window_manager = manager
                self._cache_timer = None
                self._cache_progress_started = False
                try:
                    manager.progress_begin(0, 100)
                    self._cache_progress_started = True
                    self._cache_timer = manager.event_timer_add(
                        0.1,
                        window=context.window,
                    )
                    manager.modal_handler_add(self)
                    self._cache_job.start("vdb.prepare")
                    _register_active_volume_operator(self)
                except BaseException:
                    self.cancel(context)
                    self._cache_job.join(None)
                    self._finish_modal()
                    raise
                return {"RUNNING_MODAL"}
            except Exception as error:
                if isinstance(error, MemoryError):
                    raise
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}

        def _finish_modal(self):
            manager = getattr(self, "_cache_window_manager", None)
            timer = getattr(self, "_cache_timer", None)
            if manager is not None and timer is not None:
                try:
                    manager.event_timer_remove(timer)
                except (RuntimeError, ValueError):
                    pass
            self._cache_timer = None
            if (
                manager is not None
                and getattr(self, "_cache_progress_started", False)
            ):
                try:
                    manager.progress_end()
                except (RuntimeError, ValueError):
                    pass
            self._cache_progress_started = False
            _release_active_volume_operator(self)

        def cancel(self, _context):
            job = getattr(self, "_cache_job", None)
            if job is not None:
                job.request_cancel()

        def modal(self, context, event):
            if event.type == "ESC":
                self.cancel(context)
            if event.type != "TIMER":
                return {"RUNNING_MODAL"}
            manager = context.window_manager
            manager.progress_update(
                int(self._cache_task.snapshot().progress * 100)
            )
            if not self._cache_job.done:
                return {"RUNNING_MODAL"}
            self._cache_job.join(0)
            self._finish_modal()
            error = self._cache_job.error
            if error is not None:
                if isinstance(
                    error,
                    (KeyboardInterrupt, SystemExit, GeneratorExit, MemoryError),
                ):
                    raise error
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            if self._cache_task.snapshot().state is not TaskState.SUCCEEDED:
                self.report({"INFO"}, "Grid cache creation cancelled")
                return {"CANCELLED"}
            result = self._cache_job.result
            if result.status == "cancelled":
                self.report({"INFO"}, "Grid cache creation cancelled")
                return {"CANCELLED"}
            try:
                session, plan, cache_root = self._cache_values
                created = self._apply(
                    context,
                    session,
                    plan,
                    cache_root,
                )
            except Exception as error:
                if isinstance(error, MemoryError):
                    raise
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            self.report(
                {"INFO"},
                f"Created {len(created)} Grid view object(s)",
            )
            return {"FINISHED"}


    def draw_grid_controls(layout, context, session):
        grid = session.project.datasets.get(session.active_entity_id)
        if not isinstance(grid, Grid3D):
            return
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        actions = grid_action_availability(session.project, grid.id)
        layout.separator()
        layout.label(text="Grid3D", icon="VOLUME_DATA")
        layout.label(
            text=(
                f"{grid.grid_shape} · {grid.coordinate_unit} · "
                f"{grid.semantic_role} · {grid.status.value}"
            )
        )
        if grid.status is DatasetStatus.AMBIGUOUS:
            if grid.data.dims[0] == "dataset":
                layout.prop(settings, "dataset_index")
            layout.prop(settings, "preset_id")
            layout.prop(settings, "value_unit")
            layout.operator(
                CHEMBLENDER_OT_resolve_grid_semantics.bl_idname,
                icon="CHECKMARK",
            )
        layout.prop(settings, "isovalue")
        row = layout.row(align=True)
        row.enabled = actions.volume
        operator = row.operator(
            CHEMBLENDER_OT_create_grid_view.bl_idname,
            text="Volume",
        )
        operator.mode = "volume"
        row = layout.row(align=True)
        row.enabled = actions.signed_surface
        operator = row.operator(
            CHEMBLENDER_OT_create_grid_view.bl_idname,
            text="Signed Surface",
        )
        operator.mode = "signed_surface"
        for property_grid_id in actions.property_grid_ids:
            prop = session.project.datasets[property_grid_id]
            operator = layout.operator(
                CHEMBLENDER_OT_create_grid_view.bl_idname,
                text=f"Map {prop.semantic_role.replace('_', ' ').title()}",
            )
            operator.mode = "property_surface"
            operator.property_grid_id = str(property_grid_id)


    def register():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity

        current = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if _OWNED_SCENE_PROPERTY is not None:
            if _same_scene_property(current, _OWNED_SCENE_PROPERTY):
                return
            raise RuntimeError(
                f"Scene.{_SCENE_PROPERTY_NAME} is no longer owned by ChemBlender"
            )
        if current is not None:
            raise RuntimeError(
                f"Scene.{_SCENE_PROPERTY_NAME} is already owned"
            )
        created = PointerProperty(type=CHEMBLENDER_PG_grid_settings)
        setattr(bpy.types.Scene, _SCENE_PROPERTY_NAME, created)
        identity = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if identity is None:
            try:
                delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
            finally:
                raise RuntimeError("Grid Scene property registration failed")
        _OWNED_SCENE_PROPERTY = identity


    def unregister():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity

        _cancel_active_volume_operators()
        if (
            _OWNED_SCENE_PROPERTY is not None
            and _same_scene_property(
                _scene_property_identity(_SCENE_PROPERTY_NAME),
                _OWNED_SCENE_PROPERTY,
            )
        ):
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
        _OWNED_SCENE_PROPERTY = None


__all__ = (
    "GridActionAvailability",
    "GridPreviewSummary",
    "grid_action_availability",
    "grid_preview_summary",
    "plan_grid_view",
    "resolve_grid_selection",
)
if bpy is not None:
    __all__ += (
        "CHEMBLENDER_OT_create_grid_view",
        "CHEMBLENDER_OT_resolve_grid_semantics",
        "CHEMBLENDER_PG_grid_settings",
        "draw_grid_controls",
    )
