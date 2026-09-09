"""Local molecular Mesh editing; scientific publication requires explicit Apply."""

from math import acos, degrees, isfinite, sqrt

from uuid import UUID

from cbq_core.model import ArrayData, QCProject
from cbq_core.element_data import ELEMENTS_DEFAULT


_STRUCTURE_CONTRACT = "structure_view_v1"


def _uuid(value, name):
    if type(value) is not str:
        raise ValueError(f"{name} is missing")
    try:
        return UUID(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a UUID") from error


def _attribute_values(mesh, name, count, *, fallback=None):
    attribute = mesh.attributes.get(name)
    if attribute is None:
        if fallback is None:
            raise ValueError(f"Structure view is missing {name}")
        return tuple(fallback)
    values = [0.0] * count
    attribute.data.foreach_get("value", values)
    return tuple(values)


def structure_edit_arguments(project, obj):
    """Freeze local Mesh values for explicit preparation without changing CBQ."""
    import numpy

    if not isinstance(project, QCProject):
        raise TypeError("project must be a QCProject")
    if obj.get("cb_structure_contract") != _STRUCTURE_CONTRACT:
        raise ValueError("active object is not a ChemBlender Structure view")
    structure_id = _uuid(obj.get("cb_structure_id"), "cb_structure_id")
    try:
        source = project.structures[structure_id]
    except KeyError as error:
        raise ValueError("Structure view source is not in the project") from error
    if obj.get("cb_structure_revision") != source.revision:
        raise ValueError("Structure view revision is stale")

    topology_id = obj.get("cb_topology_id")
    if topology_id is None:
        topology = None
    else:
        topology_id = _uuid(topology_id, "cb_topology_id")
        try:
            topology = project.topologies[topology_id]
        except KeyError as error:
            raise ValueError("Structure view topology is not in the project") from error
        if (
            topology.structure_id != source.id
            or obj.get("cb_topology_revision") != topology.revision
        ):
            raise ValueError("Structure view topology revision is stale")

    if getattr(obj, "mode", "OBJECT") != "OBJECT":
        raise ValueError("Leave Edit Mode before freezing Mesh edits")
    unit = obj.get("cb_display_coordinate_unit", "angstrom")
    if unit not in {"angstrom", "bohr"}:
        raise ValueError("Unsupported display coordinate unit")
    mesh = obj.data
    coordinates = [0.0] * (len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", coordinates)
    coordinates = numpy.asarray(coordinates, dtype=float).reshape((-1, 3))
    atomic_numbers = tuple(
        int(value)
        for value in _attribute_values(
            mesh,
            "atomic_num",
            len(mesh.vertices),
        )
    )
    raw_atom_ids = tuple(
        int(value)
        for value in _attribute_values(
            mesh,
            "cbq_atom_id",
            len(mesh.vertices),
        )
    )
    seen_atom_ids = set()
    source_atom_indices = []
    for atom_id in raw_atom_ids:
        if (
            0 <= atom_id < len(source.atomic_numbers)
            and atom_id not in seen_atom_ids
        ):
            source_atom_indices.append(atom_id)
            seen_atom_ids.add(atom_id)
        else:
            source_atom_indices.append(None)
    edges = [tuple(map(int, edge.vertices)) for edge in mesh.edges]
    orders = _attribute_values(
        mesh,
        "cbq_bond_order",
        len(edges),
        fallback=(
            float(value)
            for value in _attribute_values(
                mesh,
                "bond_order",
                len(edges),
                fallback=(1.0,) * len(edges),
            )
        ),
    )
    shifts = [(0, 0, 0)] * len(edges)

    if topology is not None and topology.bond_lattice_shifts is not None:
        current_atom_index = {
            source_index: edited_index
            for edited_index, source_index in enumerate(source_atom_indices)
            if source_index is not None
        }
        source_indices = numpy.asarray(topology.bond_indices.values, dtype=int)
        source_orders = numpy.asarray(topology.bond_orders.values, dtype=float)
        source_shifts = numpy.asarray(
            topology.bond_lattice_shifts.values,
            dtype=int,
        )
        for endpoints, order, shift in zip(
            source_indices,
            source_orders,
            source_shifts,
        ):
            left, right = map(int, endpoints)
            if (
                numpy.any(shift)
                and left in current_atom_index
                and right in current_atom_index
            ):
                edges.append(
                    (
                        current_atom_index[left],
                        current_atom_index[right],
                    )
                )
                orders += (float(order),)
                shifts.append(tuple(map(int, shift)))

    cell_values = obj.get("cb_periodic_cell")
    if cell_values is None and source.cell is not None:
        scale = {"angstrom": 1.0, "bohr": 0.529177210903}[
            source.cell.unit
        ]
        cell_values = tuple(
            float(value) * scale
            for row in source.cell.values
            for value in row
        )
    cell = (
        None
        if cell_values is None
        else ArrayData(
            numpy.asarray(cell_values, dtype=float).reshape((3, 3)),
            ("cell_vector", "xyz"),
            "angstrom",
        )
    )
    return source, topology, {
        "atomic_numbers": atomic_numbers,
        "source_atom_indices": tuple(source_atom_indices),
        # Mesh vertices are object-local, so Object transforms remain view-only.
        "coordinates": ArrayData(
            coordinates,
            ("atom", "xyz"),
            unit,
        ),
        "bond_indices": (
            None
            if topology is None and not edges
            else ArrayData(
                numpy.asarray(edges, dtype=numpy.int64).reshape((-1, 2)),
                ("bond", "endpoint"),
                "dimensionless",
            )
        ),
        "bond_orders": (
            None
            if topology is None and not edges
            else ArrayData(
                numpy.asarray(orders, dtype=float),
                ("bond",),
                "dimensionless",
            )
        ),
        "bond_lattice_shifts": (
            None
            if topology is None and not edges
            else ArrayData(
                numpy.asarray(shifts, dtype=numpy.int64).reshape((-1, 3)),
                ("bond", "xyz"),
                "dimensionless",
            )
        ),
        "cell": cell,
    }


def measure_points(points):
    """Measure local display coordinates, independent of object placement."""
    points = tuple(tuple(float(value) for value in point) for point in points)
    if len(points) not in (2, 3) or any(
        len(point) != 3 or not all(map(isfinite, point)) for point in points
    ):
        raise ValueError("Select two or three atoms with finite coordinates")
    if len(points) == 2:
        return sqrt(sum((a - b) ** 2 for a, b in zip(*points))), "distance"
    first = tuple(a - b for a, b in zip(points[0], points[1]))
    second = tuple(a - b for a, b in zip(points[2], points[1]))
    norm = sqrt(sum(v * v for v in first) * sum(v * v for v in second))
    if norm == 0:
        raise ValueError("An angle requires two nonzero bonds")
    cosine = sum(a * b for a, b in zip(first, second)) / norm
    return degrees(acos(max(-1.0, min(1.0, cosine)))), "angle"


try:
    import bpy
    import bmesh
    from bpy.props import EnumProperty, FloatProperty, IntProperty
except ImportError:
    bpy = None


if bpy is not None:
    class CHEMBLENDER_OT_mesh_edit(bpy.types.Operator):
        bl_idname = "chemblender.mesh_edit"
        bl_label = "Edit Molecular Mesh"
        bl_options = {'REGISTER', 'UNDO'}

        action: EnumProperty(items=[
            ('SELECT', 'Select Element', ''),
            ('ATOM', 'Set Selected Atoms', ''),
            ('BOND', 'Set Selected Bonds', ''),
            ('MEASURE', 'Measure Selection', ''),
        ])
        atomic_number: IntProperty(name="Atomic Number", default=6, min=1, max=118)
        scale: FloatProperty(name="Display Scale", default=1.0, min=0.01, max=20.0)
        bond_order: IntProperty(name="Bond Order", default=1, min=1, max=3)

        @classmethod
        def poll(cls, context):
            obj = context.active_object
            return (obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'
                    and bool(obj.get('cb_structure_id')) and not obj.get('cb_periodic'))

        def invoke(self, context, event):
            if self.action == 'MEASURE' or bpy.app.background:
                return self.execute(context)
            return context.window_manager.invoke_props_dialog(self)

        def draw(self, context):
            if self.action in {'SELECT', 'ATOM'}:
                self.layout.prop(self, 'atomic_number')
            if self.action == 'BOND':
                self.layout.prop(self, 'bond_order')
            if self.action in {'ATOM', 'BOND'}:
                self.layout.prop(self, 'scale')

        def execute(self, context):
            obj = context.active_object
            # from_edit_mesh is borrowed: Blender owns its lifetime.
            bm = bmesh.from_edit_mesh(obj.data)
            atoms = bm.verts.layers.int.get('atomic_num')
            if atoms is None:
                self.report({'ERROR'}, "Mesh has no atomic numbers")
                return {'CANCELLED'}
            try:
                if self.action == 'MEASURE':
                    selected = [v for v in bm.select_history if isinstance(v, bmesh.types.BMVert) and v.select]
                    if len(selected) not in (2, 3):
                        selected = [v for v in bm.verts if v.select]
                    value, kind = measure_points(v.co for v in selected)
                    unit = 'degrees' if kind == 'angle' else obj.get('cb_display_coordinate_unit', 'Blender units')
                    self.report({'INFO'}, f"{kind}: {value:.6g} {unit}")
                    return {'FINISHED'}
                if self.action == 'SELECT':
                    for edge in bm.edges:
                        edge.select_set(False)
                    for face in bm.faces:
                        face.select_set(False)
                    for vertex in bm.verts:
                        vertex.select_set(vertex[atoms] == self.atomic_number)
                elif self.action == 'ATOM':
                    selected = [v for v in bm.verts if v.select]
                    if not selected:
                        raise ValueError("Select atoms first")
                    element = next(data for data in ELEMENTS_DEFAULT.values() if data[0] == self.atomic_number)
                    names = ('radius', 'vdw_radius', 'atom_scale_f')
                    layers = [bm.verts.layers.float.get(name) or bm.verts.layers.float.new(name) for name in names]
                    color = bm.verts.layers.float_color.get('colour')
                    # Adding custom-data layers can invalidate existing BMesh element wrappers.
                    for vertex in (value for value in bm.verts if value.select):
                        vertex[atoms] = self.atomic_number
                        for layer, value in zip(layers, (element[5], element[7], self.scale)):
                            vertex[layer] = value
                        if color is not None:
                            vertex[color] = element[3]
                elif self.action == 'BOND':
                    selected = [e for e in bm.edges if e.select]
                    if not selected:
                        raise ValueError("Select bonds first")
                    order = bm.edges.layers.int.get('bond_order') or bm.edges.layers.int.new('bond_order')
                    exact = bm.edges.layers.float.get('cbq_bond_order') or bm.edges.layers.float.new('cbq_bond_order')
                    scale = bm.edges.layers.float.get('bond_scale_f') or bm.edges.layers.float.new('bond_scale_f')
                    aromatic = bm.edges.layers.bool.get('is_aromatic')
                    # Reacquire selected edges after creating any missing layers.
                    for edge in (value for value in bm.edges if value.select):
                        edge[order] = self.bond_order
                        edge[exact] = float(self.bond_order)
                        edge[scale] = self.scale
                        if aromatic is not None:
                            edge[aromatic] = 0
                if self.action in {'ATOM', 'BOND'}:
                    obj['cbq_mesh_edit_pending'] = True
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
                return {'FINISHED'}
            except (ValueError, StopIteration) as error:
                self.report({'ERROR'}, str(error) or "Unsupported element")
                return {'CANCELLED'}


    class CHEMBLENDER_OT_apply_mesh_edits(bpy.types.Operator):
        bl_idname = "chemblender.apply_mesh_edits"
        bl_label = "Apply Mesh as New Structure"
        bl_description = "Save local atom and bond edits as a new CBQ structure; retain the original"

        @classmethod
        def poll(cls, context):
            obj = context.active_object
            return (obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'
                    and obj.get('cb_structure_contract') == _STRUCTURE_CONTRACT
                    and not obj.get('cb_periodic'))

        def execute(self, context):
            from cbq_core.structure_edit import commit_structure_edits
            from cbq_core.package_import import commit_session_batch
            from cbq_core.project_service import (
                sync_project_session_links_for_scenes, ProjectServiceStatus,
            )
            from .session import get_scene_session, _notify_session_mutation, _record_result
            from .orbital_export import _EXPORTS
            from .grid import _ACTIVE_VOLUME_OPERATORS
            from cbq_core.scene_preset import builtin_scene_presets, plan_scene_preset
            from ..scene_preset_view import apply_scene_preset
            from .scientific_view import _select_root

            session = get_scene_session(context.scene)
            committed = False
            try:
                if session.id in _EXPORTS or _ACTIVE_VOLUME_OPERATORS:
                    raise ValueError("Finish or cancel the current display task before applying edits")
                obj = context.active_object
                source, topology, arguments = structure_edit_arguments(session.project, obj)
                batch = commit_structure_edits(session.project, source, topology, **arguments)
                previous_hash = None
                if bpy.data.filepath and session.sidecar_path is not None:
                    link = sync_project_session_links_for_scenes(
                        session=session, scenes=tuple(bpy.data.scenes), blend_path=bpy.data.filepath)
                    if link.status is not ProjectServiceStatus.CONNECTED:
                        raise ValueError(link.message or "Repair the current CBQ project link first")
                    previous_hash = link.manifest_sha256
                warnings = commit_session_batch(session, batch)
                committed = True
                obj['cbq_mesh_edit_pending'] = False
                derived_id = batch.structures[0].id
                session.active_entity_id = derived_id
                context.scene.chemblender_project_browser.active_entity_id = str(derived_id)
                if bpy.data.filepath:
                    link = sync_project_session_links_for_scenes(
                        session=session, scenes=tuple(bpy.data.scenes), blend_path=bpy.data.filepath,
                        previous_manifest_sha256=previous_hash)
                    _record_result(link)
                    if link.status is not ProjectServiceStatus.CONNECTED:
                        self.report({'WARNING'}, "Structure saved; project link needs repair: " + link.message)
                _notify_session_mutation(session)
                derived = session.project.structures[derived_id]
                preset = builtin_scene_presets()["structure_publication"]
                plan = plan_scene_preset(preset, session.project,
                    {"structure": derived.id}, dict(preset.default_settings))
                view = apply_scene_preset(plan, session.project, collection=context.collection)[0]
                view.matrix_world = obj.matrix_world.copy()
                _select_root(context, session, view)
                for warning in warnings:
                    self.report({'WARNING'}, warning)
                self.report({'INFO'}, "New structure saved; original structure and View retained")
                return {'FINISHED'}
            except (OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError) as error:
                if committed:
                    self.report({'WARNING'}, "Structure saved; refresh or rebuild its View: " + str(error))
                    return {'FINISHED'}
                self.report({'ERROR'}, str(error))
                return {'CANCELLED'}


    class CHEMBLENDER_PT_mesh_edit(bpy.types.Panel):
        bl_label = "Molecular Mesh Editing"
        bl_idname = "CHEMBLENDER_PT_mesh_edit"
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'ChemBlender'

        @classmethod
        def poll(cls, context):
            obj = context.active_object
            return obj is not None and obj.type == 'MESH' and bool(obj.get('cb_structure_id')) and not obj.get('cb_periodic')

        def draw(self, context):
            layout = self.layout
            if context.active_object.mode != 'EDIT':
                layout.label(text="Enter Edit Mode to edit atoms and bonds")
                layout.operator('object.editmode_toggle', text="Edit Mesh")
                layout.operator('chemblender.apply_mesh_edits')
                layout.label(text="Apply saves a new structure and retains the original")
                scene = getattr(context, "scene", None)
                if scene is not None and hasattr(
                        scene, "chemblender_processor_operation"):
                    from .processor_operations import draw_molecule_controls
                    from .session import get_scene_session
                    draw_molecule_controls(
                        layout, context, get_scene_session(scene),
                        context.active_object,
                    )
                return
            for action, label in (
                ('SELECT', 'Select Element'), ('ATOM', 'Set Atoms'),
                ('BOND', 'Set Bonds'), ('MEASURE', 'Measure 2 / 3 Atoms'),
            ):
                layout.operator('chemblender.mesh_edit', text=label).action = action
            layout.label(text="Mesh edits are drafts; CBQ data is unchanged")
