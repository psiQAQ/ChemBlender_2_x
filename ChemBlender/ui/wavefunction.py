"""Browse prepared orbital grids without invoking scientific backends."""

from uuid import UUID

from cbq_core.model import AtomicProperty, Grid3D
from cbq_core.orbital_browser import orbital_rows

_SCENE_PROPERTY_NAME = "chemblender_wavefunction"
_OWNED_SCENE_PROPERTY = None
_ENUM_ITEMS = {}

def _selected_orbitals(session, settings):
    selected = session.project.orbital_sets.get(session.active_entity_id)
    if selected is not None:
        return selected
    identity = getattr(settings, "orbital_source_uuid", "")
    if not identity:
        identity = getattr(settings, "orbital_source", "")
    if not identity:
        return next(iter(session.project.orbital_sets.values()), None)
    try:
        return session.project.orbital_sets.get(UUID(identity))
    except (ValueError, TypeError, AttributeError):
        return None


def select_wavefunction_source(settings, orbitals, *, reset=True):
    """Keep the selected scientific source when a derived grid becomes active."""
    identity = str(orbitals.id)
    if getattr(settings, "orbital_source_uuid", "") != identity:
        settings.orbital_source_uuid = identity
        if reset:
            settings.orbital_number = 1
    if settings.channel not in {value.label for value in orbitals.channels}:
        settings.channel = orbitals.channels[0].label


def _enum_number(items, identity, *, default=0):
    return next((index for index, value in enumerate(items) if value[0] == identity), default)


def _grid_parameters(settings):
    from math import isfinite
    spacing = float(settings.spacing)
    origin = [float(value) for value in settings.origin]
    shape = [int(value) for value in settings.shape]
    if (not isfinite(spacing) or spacing <= 0 or not all(map(isfinite, origin))
            or any(value < 2 for value in shape)):
        raise ValueError("Grid origin, spacing and counts are invalid")
    return {
        "origin": origin,
        "step_vectors": [[spacing, 0., 0.], [0., spacing, 0.], [0., 0., spacing]],
        "shape": shape,
        "chunk_size": 4096,
    }


def prepare_wavefunction_request(session, settings, operation_id, source_id):
    from .processor_operations import wavefunction_inputs
    charge_id = getattr(settings, "nuclear_charge_uuid", "")
    inputs = wavefunction_inputs(
        session.project, operation_id, source_id,
        nuclear_charge_id=UUID(charge_id) if charge_id else None,
    )
    parameters = _grid_parameters(settings)
    if operation_id == "wavefunction.mo_grid":
        channel = settings.channel or inputs[2].channels[0].label
        rows = orbital_rows(session.project, inputs[2], channel)
        index = settings.orbital_number - 1
        if not 0 <= index < len(rows):
            raise ValueError("Orbital number is outside the selected spin channel")
        if rows[index].evaluation_error:
            raise ValueError(rows[index].evaluation_error)
        parameters.update(channel=channel, orbital_index=index)
    elif operation_id == "wavefunction.esp_from_orbitals_grid":
        if settings.density_level == "UNSET":
            raise ValueError("Select the source density level explicitly")
        parameters["density_level"] = settings.density_level
    return inputs, parameters


try:
    import bpy
    from bpy.props import (EnumProperty, FloatProperty, FloatVectorProperty,
                           IntProperty, IntVectorProperty, PointerProperty,
                           StringProperty)
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


    def _orbital_get(self):
        return _enum_number(_orbital_items(self, bpy.context), self.orbital_source_uuid)


    def _orbital_set(self, value):
        from .session import get_scene_session
        items = _orbital_items(self, bpy.context)
        if not 0 <= value < len(items):
            raise ValueError("orbital source selection is stale")
        orbitals = get_scene_session(bpy.context.scene).project.orbital_sets[UUID(items[value][0])]
        select_wavefunction_source(self, orbitals)


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
            if isinstance(value, AtomicProperty)
            and value.semantic_role == "nuclear_charge"
            and value.status.value == "complete"
            and source is not None
            and value.structure_id == source.structure_id
            and value.data.unit == "elementary_charge"
        ))


    def _charge_get(self):
        return _enum_number(_charge_items(self, bpy.context), self.nuclear_charge_uuid)


    def _charge_set(self, value):
        items = _charge_items(self, bpy.context)
        if not 0 <= value < len(items):
            raise ValueError("nuclear charge selection is stale")
        self.nuclear_charge_uuid = "" if value == 0 else items[value][0]


    class CHEMBLENDER_PG_wavefunction(bpy.types.PropertyGroup):
        orbital_source_uuid: StringProperty(options={"HIDDEN"})
        nuclear_charge_uuid: StringProperty(options={"HIDDEN"})
        orbital_source: EnumProperty(name="Orbital Set", items=_orbital_items,
                                     get=_orbital_get, set=_orbital_set)
        channel: EnumProperty(name="Spin", items=_channel_items)
        orbital_number: IntProperty(name="Orbital", default=1, min=1)
        origin: FloatVectorProperty(name="Origin (bohr)", size=3, default=(-6., -6., -6.))
        spacing: FloatProperty(name="Step (bohr)", default=.25, min=1.e-5)
        shape: IntVectorProperty(name="Grid Counts", size=3, default=(49, 49, 49), min=2)
        nuclear_charge: EnumProperty(
            name="Effective Nuclear Charges", items=_charge_items,
            get=_charge_get, set=_charge_set,
        )
        density_level: EnumProperty(name="Density Level", default="UNSET", items=(
            ("UNSET", "Select density level", "Do not infer occupations"),
            ("scf", "SCF", "Identify the source as SCF"),
            ("post_scf", "Post SCF", "Identify the source as post-SCF"),
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
        bl_label = "Orbital Results"
        action: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        source_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
        orbital_index: IntProperty(options={"HIDDEN", "SKIP_SAVE"})

        def execute(self, context):
            from .session import get_scene_session
            from .properties import advance_browser_revision
            session = get_scene_session(context.scene)
            settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
            try:
                orbitals = _selected_orbitals(session, settings)
                if orbitals is None:
                    raise ValueError("Select an orbital set")
                channel = settings.channel or orbitals.channels[0].label
                rows = orbital_rows(session.project, orbitals, channel)
                if self.action == "select":
                    if not 0 <= self.orbital_index < len(rows):
                        raise ValueError("Orbital number is outside the selected spin channel")
                    select_wavefunction_source(settings, orbitals, reset=False)
                    settings.orbital_number = self.orbital_index + 1
                elif self.action == "use_grid":
                    index = settings.orbital_number - 1
                    grid_id = UUID(self.source_id)
                    if not 0 <= index < len(rows) or grid_id not in rows[index].cached_dataset_ids:
                        raise ValueError("The prepared grid does not belong to the selected orbital")
                    if not isinstance(session.project.datasets.get(grid_id), Grid3D):
                        raise ValueError("The prepared grid is no longer available")
                    select_wavefunction_source(settings, orbitals, reset=False)
                    session.active_entity_id = grid_id
                    context.scene.chemblender_project_browser.active_entity_id = str(grid_id)
                    advance_browser_revision(session)
                else:
                    raise ValueError("Unsupported orbital display action")
            except (AttributeError, KeyError, TypeError, ValueError) as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            return {"FINISHED"}

    def _button(layout, text, *, action="select", source_id="", index=0):
        button = layout.operator(CHEMBLENDER_OT_wavefunction.bl_idname, text=text)
        button.action = action
        button.source_id, button.orbital_index = str(source_id), index


    def _operation_button(layout, text, operation_id, source_id):
        button = layout.operator(
            "chemblender.processor_operation", text=text, icon="PLAY"
        )
        button.action = "WAVEFUNCTION"
        button.operation_id = operation_id
        button.source_id = str(source_id)

    def draw_wavefunction_controls(layout, context, session):
        from .orbital_export import _EXPORTS, draw_orbital_export
        settings = getattr(context.scene, _SCENE_PROPERTY_NAME)
        orbitals = _selected_orbitals(session, settings)
        matrix = session.project.density_matrices.get(session.active_entity_id)
        if orbitals is None:
            if matrix is not None:
                pass
            elif session.project.orbital_sets:
                layout.label(text="Selected orbital set is unavailable", icon="ERROR")
                layout.prop(settings, "orbital_source")
            else:
                layout.label(text="No orbital metadata in CBQ", icon="INFO")
                layout.label(text="Prepare orbitals, density and ESP externally, then import CBQ.")
                return
        controls = layout.column()
        controls.enabled = session.id not in _EXPORTS
        if orbitals is not None and session.active_entity_id not in session.project.orbital_sets:
            controls.prop(settings, "orbital_source")
        for name in ("origin", "spacing", "shape"):
            controls.prop(settings, name)
        source = matrix or orbitals
        controls.label(text=f"Grid end (bohr): {tuple(round(a + settings.spacing * (n - 1), 5) for a, n in zip(settings.origin, settings.shape))}")
        if matrix is not None:
            row = controls.row(align=True)
            _operation_button(row, "Compute Density Grid",
                              "wavefunction.density_matrix_grid", matrix.id)
            controls.prop(settings, "nuclear_charge")
            _operation_button(controls, "Compute ESP Grid",
                              "wavefunction.esp_grid", matrix.id)
            return
        controls.prop(settings, "channel")
        channel = settings.channel or orbitals.channels[0].label
        try:
            rows = orbital_rows(session.project, orbitals, channel)
        except (KeyError, TypeError, ValueError) as error:
            controls.label(text=str(error), icon="ERROR")
            return
        controls.label(text=f"Source: {rows[0].source}" if rows else "No orbitals")
        controls.prop(settings, "orbital_number")
        start = ((settings.orbital_number - 1) // 12) * 12
        controls.label(text="Orbital / Energy (hartree) / Occupation / Spin / Grid")
        for row in rows[start:start + 12]:
            energy = "unknown" if row.energy is None else f"{row.energy:.6f}"
            occupation = "unknown" if row.occupation is None else f"{row.occupation:g}"
            cached = "prepared" if row.cached_dataset_ids else "missing"
            _button(controls, f"{row.index + 1}  {energy}  {occupation}  {row.spin}  {cached} {' '.join(row.labels)}",
                    index=row.index)
        frontier = controls.row(align=True)
        for label in ("HOMO", "LUMO", "SOMO"):
            match = next((row for row in rows if label in row.labels), None)
            if match is not None:
                _button(frontier, label, index=match.index)
        selected = settings.orbital_number - 1
        if 0 <= selected < len(rows):
            grids = rows[selected].cached_dataset_ids
            for identity in grids:
                grid = session.project.datasets[identity]
                _button(controls, f"Select MO Grid {grid.grid_shape} · {str(identity)[:8]}",
                        action="use_grid", source_id=identity)
            if not grids:
                controls.label(text="This orbital has no prepared grid in CBQ", icon="INFO")
                if rows[selected].evaluation_error:
                    controls.label(text=rows[selected].evaluation_error, icon="INFO")
                _operation_button(controls, "Compute Selected MO Grid",
                                  "wavefunction.mo_grid", orbitals.id)
        else:
            controls.label(text="Orbital number is outside the selected spin channel", icon="ERROR")
        _operation_button(controls, "Compute Electron Density",
                          "wavefunction.electron_density_grid", orbitals.id)
        controls.prop(settings, "nuclear_charge")
        controls.prop(settings, "density_level")
        _operation_button(controls, "Compute ESP from Orbitals",
                          "wavefunction.esp_from_orbitals_grid", orbitals.id)
        draw_orbital_export(layout, context, session)

    def register():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
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


    def unregister():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        if _OWNED_SCENE_PROPERTY is not None and _same_scene_property(
            _scene_property_identity(_SCENE_PROPERTY_NAME), _OWNED_SCENE_PROPERTY
        ):
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
        _OWNED_SCENE_PROPERTY = None
        _ENUM_ITEMS.clear()


__all__ = ("prepare_wavefunction_request", "select_wavefunction_source")
if bpy is not None:
    __all__ += ("CHEMBLENDER_PG_wavefunction", "CHEMBLENDER_OT_wavefunction", "draw_wavefunction_controls")
