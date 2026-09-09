"""Grid inspection, sampling and Scene Preset controls."""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from cbq_core.model import DatasetStatus
from cbq_core.model import Grid3D
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import grids_share_affine
from cbq_core.scene_preset import plan_scene_preset
from .tasks import Task, TaskState, TaskWorker
from cbq_core.scene_preset import GRID_SAMPLE_POINT_LIMIT


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


def plan_grid_view(
    project,
    grid_id,
    *,
    mode,
    dataset_index=0,
    property_grid_id=None,
    property_dataset_index=0,
    isovalue=0.05,
    color_min=-0.1,
    color_max=0.1,
    symmetric=True,
    sample_settings=None,
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
                "property_dataset_index": property_dataset_index,
                "surface_isovalue": isovalue,
                "color_min": color_min,
                "color_max": color_max,
                "symmetric": symmetric,
            },
        )
    if mode in {"slice", "profile", "colorbar"}:
        return plan_scene_preset(
            presets[f"grid_{mode}"], project, {"grid": grid_id},
            {**(sample_settings or {}), "dataset_index": dataset_index},
        )
    raise ValueError("selected Grid3D does not support this view")


def _color_settings(settings):
    maximum = settings.color_max
    return {"color_min": -maximum if settings.symmetric else settings.color_min,
            "color_max": maximum, "symmetric": settings.symmetric, "colormap": "coolwarm"}


def _sample_settings(settings, kind):
    if kind == "slice":
        return {"origin": tuple(settings.slice_origin), "u_vector": tuple(settings.slice_u),
                "v_vector": tuple(settings.slice_v), "counts": tuple(settings.slice_counts),
                **_color_settings(settings)}
    if kind == "profile":
        return {"start": tuple(settings.profile_start), "end": tuple(settings.profile_end),
                "sample_count": settings.profile_samples, "radius": settings.profile_radius}
    if kind == "colorbar":
        return {"width": settings.colorbar_width, "height": settings.colorbar_height,
                **_color_settings(settings)}
    return None


def _draw_sample_button(layout, settings, kind):
    from math import prod

    count = (prod(getattr(settings, "slice_counts", (65, 65))) if kind == "slice"
             else getattr(settings, "profile_samples", 129))
    layout.label(text=f"{count:,} points; samples ≈ {41 * count / 1024**2:.2f} MiB + Blender geometry")
    row = layout.row()
    row.enabled = count <= GRID_SAMPLE_POINT_LIMIT
    if not row.enabled:
        layout.label(text=f"Limit: {GRID_SAMPLE_POINT_LIMIT:,} points", icon="ERROR")
    operator = row.operator("chemblender.create_grid_view", text=f"Create {kind.title()}")
    operator.mode = kind


def fit_grid_sampling(settings, grid):
    """Choose a central affine plane and a grid diagonal without reading values."""
    import numpy

    spans = numpy.asarray(grid.step_vectors) * (numpy.asarray(grid.grid_shape) - 1)[:, None]
    axes = sorted(range(3), key=lambda axis: float(numpy.linalg.norm(spans[axis])), reverse=True)
    if numpy.linalg.norm(spans[axes[1]]) == 0:
        raise ValueError("A fitted slice requires two nonzero grid extents")
    settings.slice_origin = tuple(numpy.asarray(grid.origin) + spans[axes[2]] / 2)
    settings.slice_u, settings.slice_v = tuple(spans[axes[0]]), tuple(spans[axes[1]])
    settings.profile_start = grid.origin
    settings.profile_end = tuple(numpy.asarray(grid.origin) + spans.sum(axis=0))


def load_grid_view_settings(settings, plan):
    """Load saved settings into controls without changing the saved View or grid."""
    values = dict(plan.settings)
    mapping = {
        "dataset_index": "dataset_index", "surface_dataset_index": "dataset_index",
        "property_dataset_index": "property_dataset_index", "surface_isovalue": "isovalue",
        "isovalue": "isovalue", "color_min": "color_min", "color_max": "color_max",
        "symmetric": "symmetric", "origin": "slice_origin", "u_vector": "slice_u",
        "v_vector": "slice_v", "counts": "slice_counts", "start": "profile_start",
        "end": "profile_end", "sample_count": "profile_samples", "radius": "profile_radius",
        "width": "colorbar_width", "height": "colorbar_height",
    }
    for name, field_name in mapping.items():
        if name in values:
            setattr(settings, field_name, values[name])


def export_grid_view_sample(project, obj, destination):
    """Recompute CSV from validated saved scientific settings, never object transforms."""
    from .view_cache import plan_grid_sample_view
    from cbq_core.grid_sampling import export_grid_sample

    plan = plan_grid_sample_view(obj, project, require_geometry=False)
    kind = {"grid_slice": "plane", "grid_profile": "profile"}.get(plan.view_kind)
    if kind is None:
        raise ValueError("CSV export requires a slice or profile View")
    binding, = plan.bindings
    return export_grid_sample(destination, project.datasets[binding.entity_id],
                              kind=kind, settings=dict(plan.settings))


def rebuild_grid_sample_view(session, obj):
    """Prepare a complete sample View before swapping owned data and annotations."""
    from .view_cache import plan_grid_sample_view
    from ..scene_preset_view import apply_scene_preset
    from ..grid_sample_view import remove_grid_sample_view

    plan = plan_grid_sample_view(obj, session.project, require_geometry=False, rebuild=True)
    if getattr(obj, "library", None) is not None or not obj.users_collection:
        raise ValueError("sample View must be local and linked to a collection")
    prepared_objects = apply_scene_preset(plan, session.project, collection=obj.users_collection[0])
    prepared = next(value for value in prepared_objects if value.get("cb_grid_sample_root") is True)
    old_data, new_data = obj.data, prepared.data
    old_metadata = dict(obj.items())
    old_children = tuple(child for child in obj.children if child.get("cb_grid_sample_component"))
    new_children = tuple(prepared.children)
    old_transforms = tuple((child, child.matrix_parent_inverse.copy(), child.matrix_basis.copy())
                           for child in old_children)
    new_transforms = tuple((child, child.matrix_parent_inverse.copy(), child.matrix_basis.copy())
                           for child in new_children)
    parent_change = prepared.matrix_world.inverted() @ obj.matrix_world
    try:
        obj.data, prepared.data = new_data, old_data
        for child, inverse, basis in old_transforms:
            child.parent = prepared
            # User objects can be attached below an owned annotation. Keep its
            # full parent transform, including shear, until it is removed.
            child.matrix_parent_inverse = parent_change @ inverse
            child.matrix_basis = basis
        for child in new_children:
            child.parent = obj
        for key in tuple(obj.keys()):
            if key.startswith("cb_") and key not in prepared:
                del obj[key]
        for key, value in prepared.items():
            obj[key] = value
        obj["cb_view_stale"] = False
        obj.pop("cb_view_diagnostic", None)
    except BaseException:
        obj.data, prepared.data = old_data, new_data
        for child, inverse, basis in old_transforms:
            child.parent = obj
            child.matrix_parent_inverse, child.matrix_basis = inverse, basis
        for child, inverse, basis in new_transforms:
            child.parent = prepared
            child.matrix_parent_inverse, child.matrix_basis = inverse, basis
        for key in tuple(obj.keys()):
            if key not in old_metadata:
                del obj[key]
        for key, value in old_metadata.items():
            obj[key] = value
        remove_grid_sample_view(prepared)
        raise
    remove_grid_sample_view(prepared)
    session.active_view_object_name = obj.name
    session.mark_dirty("view_cache")
    return obj


def rebuild_property_view(session, obj, cache_root):
    """Replace owned derived data only after a complete new view is available."""
    from .view_cache import plan_property_view_rebuild
    from ..scene_preset_view import apply_scene_preset
    from ..surface_view import remove_surface_object

    plan = plan_property_view_rebuild(obj, session.project)
    if getattr(obj, "library", None) is not None:
        raise ValueError("linked property surfaces cannot be rebuilt in place")
    modifiers = tuple(
        modifier for modifier in obj.modifiers
        if modifier.type == "NODES"
        and modifier.node_group is not None
        and modifier.node_group.get("cbq_contract")
        in {"property_surface_v1", "property_surface_v2"}
    )
    if len(modifiers) != 1 or not obj.users_collection:
        raise ValueError("property surface must have one owned surface modifier")
    modifier = modifiers[0]
    prepared, = apply_scene_preset(
        plan,
        session.project,
        collection=obj.users_collection[0],
        cache_root=cache_root,
    )
    prepared_modifier = prepared.modifiers[0]
    old_data, old_group = obj.data, modifier.node_group
    new_data, new_group = prepared.data, prepared_modifier.node_group
    old_metadata = dict(obj.items())
    old_contract = modifier.get("cbq_contract")
    try:
        # Keep object identity, transforms, collections and user modifiers intact.
        obj.data = new_data
        modifier.node_group = new_group
        modifier["cbq_contract"] = prepared_modifier["cbq_contract"]
        for key, value in prepared.items():
            obj[key] = value
        obj["cb_view_stale"] = False
        obj.pop("cb_view_diagnostic", None)
        prepared.data = old_data
        prepared_modifier.node_group = old_group
    except BaseException:
        obj.data = old_data
        modifier.node_group = old_group
        if old_contract is None:
            modifier.pop("cbq_contract", None)
        else:
            modifier["cbq_contract"] = old_contract
        for key in tuple(obj.keys()):
            if key not in old_metadata:
                del obj[key]
        for key, value in old_metadata.items():
            obj[key] = value
        prepared.data = new_data
        prepared_modifier.node_group = new_group
        remove_surface_object(prepared)
        raise
    remove_surface_object(prepared)
    session.active_view_object_name = obj.name
    session.mark_dirty("view_cache")
    return obj


try:
    import bpy
    from bpy.props import (
        BoolProperty,
        FloatProperty,
        FloatVectorProperty,
        IntProperty,
        IntVectorProperty,
        PointerProperty,
        StringProperty,
    )
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    class CHEMBLENDER_PG_grid_settings(bpy.types.PropertyGroup):
        dataset_index: IntProperty(name="Dataset", default=0, min=0)
        property_dataset_index: IntProperty(name="Property Dataset", default=0, min=0)
        color_min: FloatProperty(name="Color Minimum", default=-0.1, precision=6)
        color_max: FloatProperty(name="Color Maximum", default=0.1, precision=6)
        symmetric: BoolProperty(name="Symmetric Colors", default=True)
        slice_origin: FloatVectorProperty(name="Slice Origin", size=3, default=(0., 0., 0.))
        slice_u: FloatVectorProperty(name="Slice Span U", size=3, default=(1., 0., 0.))
        slice_v: FloatVectorProperty(name="Slice Span V", size=3, default=(0., 1., 0.))
        slice_counts: IntVectorProperty(name="Slice Samples", size=2, default=(65, 65), min=2,
                                       max=GRID_SAMPLE_POINT_LIMIT)
        profile_start: FloatVectorProperty(name="Profile Start", size=3, default=(0., 0., 0.))
        profile_end: FloatVectorProperty(name="Profile End", size=3, default=(1., 1., 1.))
        profile_samples: IntProperty(name="Profile Samples", default=129, min=2, max=GRID_SAMPLE_POINT_LIMIT)
        profile_radius: FloatProperty(name="Path Radius (Å)", default=0.015, min=1.e-6)
        colorbar_width: FloatProperty(name="Colorbar Width (Å)", default=2.0, min=1.e-6)
        colorbar_height: FloatProperty(name="Colorbar Height (Å)", default=0.2, min=1.e-6)
        isovalue: FloatProperty(
            name="Isovalue",
            default=0.05,
            min=1.0e-12,
            precision=6,
        )


    def _operator_context(context):
        from .session import get_scene_session

        session = get_scene_session(context.scene)
        grid = _grid(session.project, session.active_entity_id)
        return session, grid, getattr(context.scene, _SCENE_PROPERTY_NAME)


    class CHEMBLENDER_OT_create_grid_view(bpy.types.Operator):
        bl_idname = "chemblender.create_grid_view"
        bl_label = "Create Grid View"

        mode: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        property_grid_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        object_name: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})
        filter_glob: StringProperty(default="*.csv", options={"HIDDEN", "SKIP_SAVE"})
        check_existing: BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})

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
            prop = session.project.datasets.get(property_grid_id)
            use_property = self.mode == "colorbar" and prop is not None
            if use_property:
                grid = prop
            colors = _color_settings(settings)
            plan = plan_grid_view(
                session.project,
                grid.id,
                mode=self.mode,
                dataset_index=(
                    (settings.property_dataset_index if use_property else settings.dataset_index)
                    if grid.data.dims[0] == "dataset"
                    else 0
                ),
                property_grid_id=property_grid_id,
                property_dataset_index=settings.property_dataset_index
                if prop is not None and prop.data.dims[0] == "dataset" else 0,
                isovalue=settings.isovalue,
                color_min=colors["color_min"], color_max=colors["color_max"],
                symmetric=colors["symmetric"], sample_settings=_sample_settings(settings, self.mode),
            )
            cache_root = None if self.mode in {"slice", "profile", "colorbar"} else self._cache_root(session)
            return session, grid, plan, cache_root

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
                root = next((obj for obj in created if obj.get("cb_grid_sample_root") is True), created[-1])
                session.active_view_object_name = root.name
            session.mark_dirty("view_cache")
            return created

        def execute(self, context):
            try:
                if self.mode in {"load_view", "rebuild_sample", "export_sample"}:
                    from .session import get_scene_session
                    from .properties import advance_browser_revision
                    from .view_cache import plan_grid_sample_view, plan_property_view_rebuild

                    session = get_scene_session(context.scene)
                    obj = context.scene.objects.get(self.object_name)
                    if self.mode == "rebuild_sample":
                        rebuild_grid_sample_view(session, obj)
                        advance_browser_revision(session)
                        self.report({"INFO"}, "Grid sample View rebuilt")
                    elif self.mode == "export_sample":
                        if not self.filepath:
                            raise ValueError("Choose a CSV destination")
                        export_grid_view_sample(session.project, obj, self.filepath)
                        self.report({"INFO"}, "Grid samples exported from saved scientific settings")
                    else:
                        plan = (plan_property_view_rebuild(obj, session.project)
                                if obj is not None and obj.get("cb_scene_preset_id") == "property_on_surface"
                                else plan_grid_sample_view(obj, session.project, require_geometry=False))
                        load_grid_view_settings(getattr(context.scene, _SCENE_PROPERTY_NAME), plan)
                        binding = next(value for value in plan.bindings if value.name in {"grid", "surface_grid"})
                        session.active_entity_id = binding.entity_id
                        context.scene.chemblender_project_browser.active_entity_id = str(binding.entity_id)
                        session.active_view_object_name = obj.name
                        advance_browser_revision(session)
                        self.report({"INFO"}, "Saved View parameters loaded")
                    return {"FINISHED"}
                if self.mode == "fit_sampling":
                    _session, grid, settings = _operator_context(context)
                    fit_grid_sampling(settings, grid)
                    return {"FINISHED"}
                if self.mode == "rebuild_property":
                    from .session import get_scene_session
                    from .properties import advance_browser_revision

                    session = get_scene_session(context.scene)
                    obj = context.scene.objects.get(self.object_name)
                    rebuild_property_view(session, obj, self._cache_root(session))
                    advance_browser_revision(session)
                    self.report({"INFO"}, "Property surface rebuilt")
                    return {"FINISHED"}
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
            if self.mode == "export_sample" and not bpy.app.background:
                self.filepath = self.filepath or (self.object_name + ".csv")
                context.window_manager.fileselect_add(self)
                return {"RUNNING_MODAL"}
            if self.mode != "volume" or bpy.app.background:
                return self.execute(context)
            try:
                session, grid, plan, cache_root = self._values(context)
                dataset_index = dict(plan.settings)["dataset_index"]
                from cbq_core.grid_cache_service import VolumeCacheRequest
                from cbq_core.grid_cache_service import prepare_volume_cache
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
        for obj in getattr(context.scene, "objects", ()):
            if (
                obj.get("cb_scene_preset_id") == "property_on_surface"
                and (
                    obj.get("cb_view_stale")
                    or obj.get("cb_scene_preset_version")
                    != builtin_scene_presets()["property_on_surface"].version
                )
            ):
                layout.label(text=f"{obj.name}: view needs rebuilding", icon="ERROR")
                diagnostic = obj.get("cb_view_diagnostic")
                if diagnostic:
                    layout.label(text=diagnostic)
                operator = layout.operator(
                    CHEMBLENDER_OT_create_grid_view.bl_idname,
                    text="Rebuild View",
                )
                operator.mode = "rebuild_property"
                operator.object_name = obj.name
            if obj.get("cb_grid_sample_root") is True:
                layout.label(text=f"Saved View: {obj.name}")
                if obj.get("cb_view_stale"):
                    layout.label(text=obj.get("cb_view_diagnostic", "View needs rebuilding"), icon="ERROR")
                row = layout.row(align=True)
                for text, mode in (("Load Parameters", "load_view"), ("Rebuild View", "rebuild_sample")):
                    operator = row.operator(CHEMBLENDER_OT_create_grid_view.bl_idname, text=text)
                    operator.mode, operator.object_name = mode, obj.name
                if obj.get("cb_scene_preset_id") in {"grid_slice", "grid_profile"}:
                    operator = layout.operator(CHEMBLENDER_OT_create_grid_view.bl_idname, text="Export Samples CSV")
                    operator.mode, operator.object_name = "export_sample", obj.name
            elif obj.get("cb_scene_preset_id") == "property_on_surface" and not obj.get("cb_view_stale"):
                operator = layout.operator(CHEMBLENDER_OT_create_grid_view.bl_idname,
                                           text=f"Load {obj.name} Parameters")
                operator.mode, operator.object_name = "load_view", obj.name
        grid = session.project.datasets.get(session.active_entity_id)
        if not isinstance(grid, Grid3D):
            return
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        actions = grid_action_availability(session.project, grid.id)
        layout.separator()
        layout.label(text="Grid3D", icon="VOLUME_DATA")
        layout.label(text=f"Shape: {grid.grid_shape}")
        layout.label(text=f"Coordinate unit: {grid.coordinate_unit}")
        layout.label(text=f"Semantic: {grid.semantic_role}")
        layout.label(text=f"Value unit: {grid.data.unit}")
        layout.label(text=f"Quality: {grid.status.value}")
        if grid.data.dims[0] == "dataset":
            layout.prop(settings, "dataset_index")
        if grid.status is DatasetStatus.AMBIGUOUS:
            layout.label(text="Resolve grid units and meaning in Prepare, then import the CBQ", icon="ERROR")
        layout.prop(settings, "isovalue")
        # Float controls have bounded precision; keep tiny thresholds readable.
        layout.label(text=f"Threshold: {settings.isovalue:.6g}")
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
        if grid.status is DatasetStatus.COMPLETE:
            layout.prop(settings, "symmetric")
            if not getattr(settings, "symmetric", True):
                layout.prop(settings, "color_min")
            layout.prop(settings, "color_max", text="Color Limit ±" if getattr(settings, "symmetric", True) else "Color Maximum")
            if any(session.project.datasets[value].data.dims[0] == "dataset"
                   for value in actions.property_grid_ids):
                layout.prop(settings, "property_dataset_index")
        for property_grid_id in actions.property_grid_ids:
            prop = session.project.datasets[property_grid_id]
            layout.label(text=f"Property: {prop.semantic_role} · {prop.data.unit}")
            row = layout.row(align=True)
            operator = row.operator(
                CHEMBLENDER_OT_create_grid_view.bl_idname,
                text=f"Map {prop.semantic_role.replace('_', ' ').title()}",
            )
            operator.mode = "property_surface"
            operator.property_grid_id = str(property_grid_id)
            operator = row.operator(CHEMBLENDER_OT_create_grid_view.bl_idname, text="Colorbar")
            operator.mode, operator.property_grid_id = "colorbar", str(property_grid_id)
        if grid.status is DatasetStatus.COMPLETE:
            layout.separator()
            layout.label(text=f"Sampling coordinates: {grid.coordinate_unit}; values: {grid.data.unit}")
            operator = layout.operator(CHEMBLENDER_OT_create_grid_view.bl_idname, text="Fit Slice / Profile to Grid")
            operator.mode = "fit_sampling"
            for name in ("slice_origin", "slice_u", "slice_v", "slice_counts"):
                layout.prop(settings, name)
            layout.label(text="U / V are full spans; samples include endpoints")
            _draw_sample_button(layout, settings, "slice")
            for name in ("profile_start", "profile_end", "profile_samples", "profile_radius"):
                layout.prop(settings, name)
            _draw_sample_button(layout, settings, "profile")
            for name in ("colorbar_width", "colorbar_height"):
                layout.prop(settings, name)
            operator = layout.operator(CHEMBLENDER_OT_create_grid_view.bl_idname, text="Create Grid Colorbar")
            operator.mode = "colorbar"


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
    "fit_grid_sampling",
    "load_grid_view_settings",
    "export_grid_view_sample",
    "rebuild_grid_sample_view",
    "rebuild_property_view",
)
if bpy is not None:
    __all__ += (
        "CHEMBLENDER_OT_create_grid_view",
        "CHEMBLENDER_PG_grid_settings",
        "draw_grid_controls",
    )
