"""Public scientific representations backed by the shared scene preset contract."""

from math import isfinite, tau
from types import SimpleNamespace
from uuid import UUID

from cbq_core.model import ArrayData
from cbq_core.model import SpectrumKind
from cbq_core.model import SpectrumProfile
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import grids_share_affine
from cbq_core.scene_preset import plan_scene_preset
from .default_views import default_grid_preset


_SCENE_PROPERTY_NAME = "chemblender_scientific_view"
_OWNED_SCENE_PROPERTY = None
_ENUM_ITEMS = {}
_PREVIEW_PENDING = {}
_SELECTION_FIELDS = {"atom_indices", "orbital_labels", "spin_indices"}
_COMMON_SETTINGS = {"template", "shaded", "material_opacity"}
_PRESETS_BY_TYPE = {
    "Structure": ("structure_publication",),
    "Grid3D": ("grid_volume", "signed_isosurface", "property_on_surface",
               "grid_slice", "grid_profile", "grid_colorbar"),
    "VibrationalModeSet": ("vibration_mode", "vibration_spectrum_linked"),
    "ExcitedStateSet": ("electronic_spectrum_linked",),
    "Spectrum": ("spectrum_plot", "vibration_spectrum_linked", "electronic_spectrum_linked"),
    "BandStructure": ("band_structure", "band_dos_linked"),
    "DensityOfStates": ("density_of_states", "band_dos_linked"),
    "FermiSurfaceMesh": ("fermi_surface",),
    "TopologyGraph": ("topology_graph",),
    "PhononModeSet": ("phonon_mode",),
    "FrameSet": ("trajectory", "trajectory_force"),
}


def selected_entity(project, identity):
    for name in ("datasets", "structures", "orbital_sets", "density_matrices"):
        entity = getattr(project, name).get(identity)
        if entity is not None:
            return entity
    return None


def available_presets(entity):
    """Inspect only type/shape metadata; never materialize a scientific array."""
    name = type(entity).__name__
    if name == "Grid3D" and entity.semantic_role == "reduced_density_gradient":
        return ("nci_surface",) + _PRESETS_BY_TYPE[name]
    if name == "Grid3D":
        preferred = default_grid_preset(entity)
        return (preferred,) + tuple(value for value in _PRESETS_BY_TYPE[name] if value != preferred)
    if name == "AtomFrameProperty":
        return ("trajectory_force",) if entity.semantic_role == "atomic_force" and entity.data.dims == ("frame", "atom", "xyz") else ()
    if name == "AtomicProperty":
        if not isinstance(entity.data, ArrayData):
            return ()
        dims = entity.data.dims
        return ("atomic_scalar",) if dims == ("atom",) else (("atomic_vector",) if dims == ("atom", "xyz") else ())
    if name == "Spectrum":
        linked = "vibration_spectrum_linked" if entity.kind in {SpectrumKind.IR, SpectrumKind.RAMAN} else "electronic_spectrum_linked"
        return ("spectrum_plot", linked) if entity.profile is SpectrumProfile.STICK else ("spectrum_plot",)
    return _PRESETS_BY_TYPE.get(name, ())


def selected_preset(entity, settings):
    choices = available_presets(entity)
    if not choices:
        raise ValueError("selected entity has no scientific scene representation")
    identity = choices[0] if settings.preset_id == "AUTO" else settings.preset_id
    if identity not in choices:
        raise ValueError("representation does not match the selected entity; choose Automatic")
    return builtin_scene_presets()[identity]


def binding_candidates(project, entity, preset):
    """Return explicit bindings and choices for the one optional second source."""
    source = selected_entity(project, getattr(entity, "source_dataset_id", None)
                             or getattr(entity, "frame_set_id", None))
    structure_id = getattr(source or entity, "structure_id", None)
    if type(entity).__name__ == "Structure":
        structure_id = entity.id
    bound, choices = {}, {}
    for spec in preset.bindings:
        if spec.entity_kind == "structure":
            if structure_id not in project.structures:
                raise ValueError("selected dataset has no current Structure")
            bound[spec.name] = structure_id
            continue
        if spec.name != "property_grid" and type(entity).__name__ in spec.entity_types:
            bound[spec.name] = entity.id
            continue
        if source is not None and type(source).__name__ in spec.entity_types:
            bound[spec.name] = source.id
            continue
        candidates = []
        for value in project.datasets.values():
            if type(value).__name__ not in spec.entity_types:
                continue
            if spec.semantic_roles and value.semantic_role not in spec.semantic_roles:
                continue
            if spec.name == "force" and value.frame_set_id != entity.id:
                continue
            if spec.name == "property_grid" and not grids_share_affine(entity, value):
                continue
            if spec.name == "spectrum" and getattr(value, "source_dataset_id", None) != entity.id:
                continue
            if spec.name in {"band", "dos"} and value.structure_id != structure_id:
                continue
            candidates.append(value)
        choices[spec.name] = tuple(candidates)
    return bound, choices


def scientific_bindings(project, entity, preset, secondary_uuid=""):
    bound, choices = binding_candidates(project, entity, preset)
    secondary = UUID(secondary_uuid) if secondary_uuid else None
    for name, candidates in choices.items():
        if secondary not in {value.id for value in candidates}:
            raise ValueError(f"select a compatible {name.replace('_', ' ')} source")
        bound[name] = secondary
    return bound


def preset_settings(settings, preset):
    result = {}
    for name, default in preset.default_settings:
        value = getattr(settings, name, default)
        if name in _SELECTION_FIELDS:
            if value is None or not value.strip():
                value = None
            else:
                parts = tuple(part.strip() for part in value.split(","))
                if any(not part for part in parts):
                    raise ValueError(f"{name} contains an empty selection")
                value = parts if name == "orbital_labels" else tuple(int(part) for part in parts)
                if len(set(value)) != len(value):
                    raise ValueError(f"{name} contains duplicate selections")
        elif name == "color_property" and default == "kind" and not value:
            value = default
        elif isinstance(default, tuple):
            value = tuple(value)
        result[name] = value
    return result


def load_settings(settings, plan):
    """Project an already validated plan into small RNA fields."""
    settings.preset_id = plan.preset_id
    for name, value in plan.settings:
        if hasattr(settings, name):
            if name in _SELECTION_FIELDS:
                value = "" if value is None else ", ".join(str(part) for part in value)
            setattr(settings, name, value)


def timeline_phase(frame, start, frames_per_cycle, base_phase=0.):
    if type(start) is not int or type(frames_per_cycle) is not int or frames_per_cycle < 2:
        raise ValueError("animation requires an integer start and at least two frames per cycle")
    if not isfinite(frame) or not isfinite(base_phase):
        raise ValueError("animation frame and phase must be finite")
    return base_phase + tau * (frame - start) / frames_per_cycle


def timeline_frame(frame, start, step, count):
    """Map native frames to bounded source indices, without inventing physical time."""
    if any(type(value) is not int for value in (frame, start, step, count)) or step < 1 or count < 1:
        raise ValueError("trajectory timeline requires integer frames, positive step and count")
    return min(max((frame - start) // step, 0), count - 1)


try:
    import bpy
    from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                           IntProperty, IntVectorProperty, PointerProperty, StringProperty)
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    _PRESET_ITEMS = (("AUTO", "Automatic", "Match the selected scientific entity"),) + tuple(
        (item.preset_id, item.title, "") for item in builtin_scene_presets().values())

    def _secondary_items(self, context):
        items = [("NONE", "Select linked dataset", "")]
        if context is not None:
            from .session import get_scene_session
            session = get_scene_session(context.scene)
            entity = selected_entity(session.project, session.active_entity_id)
            try:
                preset = selected_preset(entity, self)
                _, choices = binding_candidates(session.project, entity, preset)
                for values in choices.values():
                    items.extend((str(value.id), f"{value.semantic_role} · {str(value.id)[:8]}", str(value.id)) for value in values)
            except (AttributeError, TypeError, ValueError):
                pass
        result = tuple(items)
        return _ENUM_ITEMS.setdefault(result, result)

    def _secondary_get(self):
        return next((index for index, item in enumerate(_secondary_items(self, bpy.context))
                     if item[0] == self.secondary_source_uuid), 0)

    def _secondary_set(self, index):
        items = _secondary_items(self, bpy.context)
        if not 0 <= index < len(items):
            raise ValueError("linked source selection is stale")
        self.secondary_source_uuid = "" if index == 0 else items[index][0]

    def _flush_local_previews():
        pending = tuple(_PREVIEW_PENDING.values())
        _PREVIEW_PENDING.clear()
        from .session import get_scene_session
        from ..scene_preset_view import apply_scientific_frame, apply_scientific_phase
        for scene, action in pending:
            settings = getattr(scene, _SCENE_PROPERTY_NAME, None)
            obj = scene.objects.get(settings.loaded_view_name) if settings else None
            if obj is None:
                continue
            try:
                project = get_scene_session(scene).project
                if action == "PHASE":
                    apply_scientific_phase(obj, project, settings.phase)
                else:
                    apply_scientific_frame(obj, project, settings.frame_index)
                    obj["cb_scientific_playback"] = False
            except (KeyError, ReferenceError, AttributeError, RuntimeError,
                    TypeError, ValueError) as error:
                obj["cb_view_diagnostic"] = str(error)
        return None

    def _queue_local_preview(self, context, action):
        scene = getattr(context, "scene", None)
        if scene is None or not self.loaded_view_name:
            return
        _PREVIEW_PENDING[scene.as_pointer()] = (scene, action)
        if not bpy.app.timers.is_registered(_flush_local_previews):
            bpy.app.timers.register(_flush_local_previews, first_interval=.1)

    def _queue_phase_preview(self, context):
        _queue_local_preview(self, context, "PHASE")

    def _queue_frame_preview(self, context):
        _queue_local_preview(self, context, "FRAME")


    class CHEMBLENDER_PG_scientific_view(bpy.types.PropertyGroup):
        preset_id: EnumProperty(name="Representation", items=_PRESET_ITEMS, default="AUTO")
        secondary_source_uuid: StringProperty(options={"HIDDEN"})
        secondary_source: EnumProperty(name="Linked Dataset", items=_secondary_items, get=_secondary_get, set=_secondary_set)
        loaded_view_name: StringProperty(options={"HIDDEN"})
        template: EnumProperty(name="Template", items=(("research", "Research", ""), ("teaching", "Teaching", "")))
        shaded: BoolProperty(name="Light Quantitative Colors", default=False,
                             description="Lighting changes displayed colors; disable for quantitative color matching")
        material_opacity: FloatProperty(name="Material Opacity", default=1., min=0., max=1.)
        dataset_index: IntProperty(name="Dataset Index", default=0, min=0)
        surface_dataset_index: IntProperty(name="Surface Dataset Index", default=0, min=0)
        property_dataset_index: IntProperty(name="Property Dataset Index", default=0, min=0)
        isovalue: FloatProperty(name="Isovalue", default=.05, min=1.e-12, precision=6)
        surface_isovalue: FloatProperty(name="Surface Isovalue", default=.001, min=1.e-12, precision=6)
        opacity: FloatProperty(name="Surface Opacity", default=1., min=0., max=1.)
        density_scale: FloatProperty(name="Volume Density Scale", default=10., min=1.e-6)
        signed: BoolProperty(name="Separate Positive / Negative Volume", default=False)
        positive_color: FloatVectorProperty(name="Positive Color", subtype="COLOR", size=4, min=0., max=1., default=(.04,.45,.8,1.))
        negative_color: FloatVectorProperty(name="Negative Color", subtype="COLOR", size=4, min=0., max=1., default=(1.,.3,.04,1.))
        color_min: FloatProperty(name="Color Minimum", default=-.1, precision=6)
        color_max: FloatProperty(name="Color Maximum", default=.1, precision=6)
        symmetric: BoolProperty(name="Symmetric Color Range", default=True)
        colormap: EnumProperty(name="Colormap", items=(("coolwarm", "Coolwarm", ""), ("viridis", "Viridis", ""), ("nci", "NCI Blue / Green / Red", "")))
        pairing_confirmed: BoolProperty(name="Confirm Same Density Analysis", default=False,
            description="For independent grid files, confirm RDG and sign(lambda2) rho came from the same density analysis")
        origin: FloatVectorProperty(name="Plane Origin (Grid Unit)", size=3, default=(-1.,-1.,0.))
        u_vector: FloatVectorProperty(name="Full Plane Span U", size=3, default=(2.,0.,0.))
        v_vector: FloatVectorProperty(name="Full Plane Span V", size=3, default=(0.,2.,0.))
        counts: IntVectorProperty(name="Plane Samples", size=2, default=(65,65), min=2)
        start: FloatVectorProperty(name="Profile Start (Grid Unit)", size=3, default=(-1.,0.,0.))
        end: FloatVectorProperty(name="Profile End (Grid Unit)", size=3, default=(1.,0.,0.))
        sample_count: IntProperty(name="Profile Samples", default=129, min=2, max=1_000_000)
        radius: FloatProperty(name="Profile Radius (Å)", default=.015, min=1.e-6)
        width: FloatProperty(name="Colorbar Width (Å)", default=2., min=1.e-6)
        height: FloatProperty(name="Colorbar Height (Å)", default=.2, min=1.e-6)
        vector_scale: FloatProperty(name="Vector Display Scale", default=1., min=1.e-9)
        as_force: BoolProperty(name="Display Force = −Gradient", default=False)
        selection_index: IntProperty(name="Mode / State Index", default=0, min=0)
        qpoint_index: IntProperty(name="q-point Index", default=0, min=0)
        arrow_scale: FloatProperty(name="Arrow Scale", default=1., min=1.e-9)
        amplitude_scale: FloatProperty(name="Displacement Amplitude", default=.4)
        phase: FloatProperty(name="Phase (radians)", default=0., update=_queue_phase_preview)
        repetitions: IntVectorProperty(name="Supercell Repetitions", size=3, default=(1,1,1), min=1, max=12)
        line_radius: FloatProperty(name="Line Radius", default=.01, min=1.e-6)
        axes: BoolProperty(name="Show Axes", default=True)
        energy_reference: EnumProperty(name="Energy Reference", items=(("fermi_shifted", "E − E_F", ""), ("absolute", "Absolute", "")))
        mirror_beta: BoolProperty(name="Mirror Beta DOS", default=True)
        atom_indices: StringProperty(name="PDOS Atom Indices", description="Comma-separated zero-based indices; blank uses all")
        orbital_labels: StringProperty(name="PDOS Orbital Labels", description="Comma-separated source labels; blank with no atoms selects total DOS")
        spin_indices: StringProperty(name="Spin Indices", description="Comma-separated zero-based indices; blank uses all")
        color_property: StringProperty(name="Color Property", description="Fermi source property name, or QTAIM: kind / field_value / laplacian")
        vector_property: StringProperty(name="Vector Property")
        vector_stride: IntProperty(name="Vector Stride", default=1, min=1)
        point_radius: FloatProperty(name="Critical Point Radius", default=.1, min=1.e-6)
        path_radius: FloatProperty(name="Gradient Path Radius", default=.025, min=1.e-6)
        frame_start: IntProperty(name="Animation Start Frame", default=1)
        frame_index: IntProperty(name="Source Frame Index (0-based)", default=0, min=0,
                                 update=_queue_frame_preview)
        frame_step: IntProperty(name="Timeline Frames Per Source Frame", default=1, min=1)
        frames_per_cycle: IntProperty(name="Frames Per Cycle", default=48, min=2)

    def _context(context):
        from .session import get_scene_session
        session = get_scene_session(context.scene)
        return session, selected_entity(session.project, session.active_entity_id), getattr(context.scene, _SCENE_PROPERTY_NAME)

    def _view_root(context, session):
        from .properties import active_session_view
        obj = active_session_view(context, session)
        while obj is not None:
            if obj.get("cb_scene_preset_id") and obj.get("cb_view_instance_id") and obj.get("cb_view_root") is True:
                return obj
            obj = obj.parent
        raise ValueError("select an owned scientific View root or component")

    def _select_root(context, session, obj):
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        session.active_view_object_name = obj.name
        session.mark_dirty("view_cache")


    @bpy.app.handlers.persistent
    def _scientific_frame_change(scene, _depsgraph=None):
        roots = tuple(obj for obj in scene.objects if obj.get("cb_view_root") is True
                      and obj.get("cb_scientific_playback") is True)
        if not roots:
            return
        from .session import get_scene_session
        from .view_cache import scene_plan_from_view
        from ..scene_preset_view import apply_scientific_phase, apply_scientific_frame
        session = get_scene_session(scene)
        for obj in roots:
            try:
                plan = scene_plan_from_view(obj, session.project)
                settings = dict(plan.settings)
                if plan.view_kind in {"trajectory", "trajectory_force"}:
                    frames = session.project.datasets[next(b.entity_id for b in plan.bindings if b.name == "frames")]
                    apply_scientific_frame(obj, session.project, timeline_frame(scene.frame_current,
                        settings["frame_start"], settings["frame_step"], frames.data.shape[0]))
                else:
                    phase = timeline_phase(scene.frame_current, settings["frame_start"],
                                           settings["frames_per_cycle"], settings["phase"])
                    apply_scientific_phase(obj, session.project, phase)
            except (KeyError, ReferenceError, AttributeError, RuntimeError, TypeError, ValueError) as error:
                obj["cb_scientific_playback"] = False
                obj["cb_view_diagnostic"] = str(error)

    def clear_scientific_playback(_session=None):
        for scene in bpy.data.scenes:
            for obj in scene.objects:
                if obj.get("cb_view_root") is True and obj.get("cb_scientific_playback") is True:
                    obj["cb_scientific_playback"] = False

    class CHEMBLENDER_OT_scientific_view(bpy.types.Operator):
        bl_idname = "chemblender.scientific_view"
        bl_label = "Scientific View"
        action: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

        def execute(self, context):
            from .session import _notify_session_mutation
            from .view_cache import scene_plan_from_view, rebuild_scene_view
            from .grid import CHEMBLENDER_OT_create_grid_view
            from ..scene_preset_view import apply_scene_preset
            session, entity, settings = _context(context)
            try:
                if self.action == "DEFAULTS":
                    preset = selected_preset(entity, settings)
                    load_settings(settings, SimpleNamespace(preset_id=preset.preset_id, settings=preset.default_settings))
                    return {"FINISHED"}
                if self.action in {"LOAD", "REBUILD", "UPDATE", "PHASE", "FRAME", "PLAY", "PAUSE"}:
                    obj = _view_root(context, session)
                    old_plan = scene_plan_from_view(obj, session.project, require_geometry=False, rebuild=True)
                    if self.action == "LOAD":
                        load_settings(settings, old_plan)
                        primary = next((binding for binding in old_plan.bindings if binding.entity_kind != "structure"), old_plan.bindings[0])
                        session.active_entity_id = primary.entity_id
                        context.scene.chemblender_project_browser.active_entity_id = str(primary.entity_id)
                        _, choices = binding_candidates(session.project, selected_entity(session.project, primary.entity_id), builtin_scene_presets()[old_plan.preset_id])
                        settings.secondary_source_uuid = next((str(binding.entity_id) for binding in old_plan.bindings if binding.name in choices), "")
                        settings.loaded_view_name = obj.name
                        _notify_session_mutation(session)
                        return {"FINISHED"}
                    if self.action == "PHASE":
                        from ..scene_preset_view import apply_scientific_phase
                        apply_scientific_phase(obj, session.project, settings.phase)
                        return {"FINISHED"}
                    if self.action == "FRAME":
                        from ..scene_preset_view import apply_scientific_frame
                        apply_scientific_frame(obj, session.project, settings.frame_index)
                        obj["cb_scientific_playback"] = False
                        return {"FINISHED"}
                    if self.action == "PAUSE":
                        obj["cb_scientific_playback"] = False
                        if context.screen is not None and context.screen.is_animation_playing:
                            bpy.ops.screen.animation_play()
                        return {"FINISHED"}
                    if self.action == "PLAY":
                        trajectory = old_plan.view_kind in {"trajectory", "trajectory_force"}
                        if not trajectory and old_plan.view_kind not in {"vibration_mode", "vibration_spectrum_linked", "phonon_mode"}:
                            raise ValueError("selected View has no supported animation")
                        saved = dict(old_plan.settings)
                        fields = ("frame_start", "frame_step") if trajectory else ("frame_start", "frames_per_cycle", "phase")
                        if any(getattr(settings, name) != saved[name] for name in fields):
                            raise ValueError("Update View to save the timeline settings before playback")
                        if trajectory:
                            from ..scene_preset_view import apply_scientific_frame
                            frames = session.project.datasets[next(b.entity_id for b in old_plan.bindings if b.name == "frames")]
                            apply_scientific_frame(obj, session.project, 0)
                            length = (frames.data.shape[0] - 1) * saved["frame_step"] + 1
                        else:
                            from ..scene_preset_view import apply_scientific_phase
                            apply_scientific_phase(obj, session.project, saved["phase"])
                            length = saved["frames_per_cycle"]
                        obj["cb_scientific_playback"] = True
                        context.scene.frame_start = saved["frame_start"]
                        context.scene.frame_end = saved["frame_start"] + length - 1
                        context.scene.frame_set(saved["frame_start"])
                        session.mark_dirty("view_cache")
                        if not bpy.app.background and context.screen is not None and not context.screen.is_animation_playing:
                            bpy.ops.screen.animation_play()
                        return {"FINISHED"}
                    new_plan = None
                    if self.action == "UPDATE":
                        if settings.loaded_view_name != obj.name:
                            raise ValueError("load this View before changing its parameters")
                        preset = builtin_scene_presets()[old_plan.preset_id]
                        new_plan = plan_scene_preset(preset, session.project, {b.name: b.entity_id for b in old_plan.bindings}, preset_settings(settings, preset))
                    obj = rebuild_scene_view(obj, session.project, cache_root=CHEMBLENDER_OT_create_grid_view._cache_root(session), plan=new_plan)
                elif self.action == "CREATE":
                    preset = selected_preset(entity, settings)
                    bindings = scientific_bindings(session.project, entity, preset, settings.secondary_source_uuid)
                    plan = plan_scene_preset(preset, session.project, bindings, preset_settings(settings, preset))
                    obj = apply_scene_preset(plan, session.project, cache_root=CHEMBLENDER_OT_create_grid_view._cache_root(session))[0]
                else:
                    raise ValueError("unknown scientific View action")
                _select_root(context, session, obj)
                settings.loaded_view_name = obj.name
                _notify_session_mutation(session)
            except (KeyError, AttributeError, RuntimeError, TypeError, ValueError) as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            return {"FINISHED"}


    def _button(layout, label, action):
        operator = layout.operator(CHEMBLENDER_OT_scientific_view.bl_idname, text=label)
        operator.action = action

    def draw_scientific_controls(layout, context, session, entity=None):
        entity = entity or selected_entity(session.project, session.active_entity_id)
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        box = layout.box()
        box.label(text="Scientific Representation")
        name = type(entity).__name__
        choices = available_presets(entity)
        if not choices:
            reason = ("Select a prepared grid in Orbital Results; add missing quantities in Prepare" if name in {"OrbitalSet", "DensityMatrix"}
                      else "Select a supported Structure or scientific dataset in Project Browser")
            box.label(text=reason, icon="INFO")
            _button(box, "Load Selected View", "LOAD")
            _button(box, "Rebuild Selected View", "REBUILD")
            return
        box.prop(settings, "preset_id")
        try:
            preset = selected_preset(entity, settings)
            _, linked = binding_candidates(session.project, entity, preset)
            if linked:
                box.prop(settings, "secondary_source")
                if not all(linked.values()):
                    box.label(text="Linked dataset is missing from CBQ; prepare and import it first", icon="INFO")
            box.label(text=preset.title)
            for field in ("template", "shaded", "material_opacity"):
                box.prop(settings, field)
            if name == "Grid3D":
                box.label(text=f"Coordinates: {entity.coordinate_unit}")
                if "property_grid" in linked:
                    box.label(text=f"Surface isovalue: {entity.data.unit}")
                    property_grid = next((value for value in linked["property_grid"]
                                          if str(value.id) == settings.secondary_source_uuid), None)
                    unit = property_grid.data.unit if property_grid is not None else "select Linked Dataset"
                    box.label(text=f"Color values: {unit}")
                else:
                    box.label(text=f"Values: {entity.data.unit}")
            for field, _ in preset.default_settings:
                if field not in _COMMON_SETTINGS and hasattr(settings, field):
                    box.prop(settings, field)
            if preset.view_kind == "density_of_states":
                box.label(text="Blank atom / orbital selection uses total DOS; indices start at 0")
            if preset.view_kind == "topology_graph":
                box.label(text="Path curves require sampled gradient paths")
            if preset.view_kind == "nci_surface":
                box.label(text="Independent files require an explicit pairing confirmation")
                box.label(text="Color limits map colors; no high-density cutoff is applied")
            row = box.row(align=True)
            _button(row, "Preset Defaults", "DEFAULTS")
            _button(row, "Create View", "CREATE")
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            box.label(text=str(error), icon="INFO")
        row = box.row(align=True)
        _button(row, "Load Selected View", "LOAD")
        _button(row, "Update Style / Parameters", "UPDATE")
        _button(box, "Rebuild Selected View", "REBUILD")
        if name in {"VibrationalModeSet", "PhononModeSet"}:
            _button(box, "Apply Phase", "PHASE")
            box.prop(settings, "frame_start")
            box.prop(settings, "frames_per_cycle")
            row = box.row(align=True)
            _button(row, "Play", "PLAY")
            _button(row, "Pause", "PAUSE")
        if name in {"FrameSet", "AtomFrameProperty"}:
            box.label(text="Source frames retain their labels and explicit time units")
            box.label(text="Apply Frame previews; Update View saves the static frame")
            _button(box, "Apply Frame", "FRAME")
            row = box.row(align=True)
            _button(row, "Play", "PLAY")
            _button(row, "Pause", "PAUSE")

    def register():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        current = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if _OWNED_SCENE_PROPERTY is not None and _same_scene_property(current, _OWNED_SCENE_PROPERTY):
            return
        if current is not None:
            raise RuntimeError(f"Scene.{_SCENE_PROPERTY_NAME} is already owned")
        setattr(bpy.types.Scene, _SCENE_PROPERTY_NAME, PointerProperty(type=CHEMBLENDER_PG_scientific_view))
        _OWNED_SCENE_PROPERTY = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if _OWNED_SCENE_PROPERTY is None:
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
            raise RuntimeError("scientific View settings registration failed")
        from .session import register_session_cleanup
        register_session_cleanup(clear_scientific_playback)
        if _scientific_frame_change not in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.append(_scientific_frame_change)

    def unregister():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        from .session import unregister_session_cleanup
        clear_scientific_playback()
        unregister_session_cleanup(clear_scientific_playback)
        while _scientific_frame_change in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.remove(_scientific_frame_change)
        if bpy.app.timers.is_registered(_flush_local_previews):
            bpy.app.timers.unregister(_flush_local_previews)
        _PREVIEW_PENDING.clear()
        if _OWNED_SCENE_PROPERTY is not None and _same_scene_property(_scene_property_identity(_SCENE_PROPERTY_NAME), _OWNED_SCENE_PROPERTY):
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
        _OWNED_SCENE_PROPERTY = None
        _ENUM_ITEMS.clear()
