"""Preview Blender mesh edits and commit explicit derived Structures."""

from pathlib import Path
from uuid import UUID

from ..core import ArrayData, QCProject
from ..core.edits.structure import (
    commit_structure_edits,
    preview_structure_edits,
)


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


def _structure_edit_arguments(project, obj):
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
            "angstrom",
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


def preview_structure_object_edits(project, obj):
    source, topology, arguments = _structure_edit_arguments(project, obj)
    return preview_structure_edits(
        project,
        source,
        topology,
        **arguments,
    )


try:
    import bpy
    from bpy.props import (
        BoolProperty,
        FloatProperty,
        IntProperty,
        StringProperty,
    )
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    def _active_values(context):
        from .session import get_scene_session

        session = get_scene_session(context.scene)
        obj = context.active_object
        if obj is None:
            raise ValueError("select a ChemBlender Structure view")
        source, topology, arguments = _structure_edit_arguments(
            session.project,
            obj,
        )
        return session, obj, source, topology, arguments


    def _write_xyz(path, structure):
        from ..Chem_data import ELEMENTS_DEFAULT
        from ..output import xyz_block

        symbols = {
            values[0]: symbol
            for symbol, values in ELEMENTS_DEFAULT.items()
        }
        atoms = tuple(
            (
                *map(float, coordinate),
                atomic_number,
                symbols.get(atomic_number, "X"),
            )
            for atomic_number, coordinate in zip(
                structure.atomic_numbers,
                structure.coordinates.values,
            )
        )
        path.write_text(
            "\n".join(xyz_block(f"Derived {structure.id}", atoms)) + "\n",
            encoding="utf-8",
        )


    class CHEMBLENDER_OT_apply_scientific_edits(bpy.types.Operator):
        bl_idname = "chemblender.apply_scientific_edits"
        bl_label = "Apply Scientific Edits"
        bl_description = "Create a derived Structure from edited mesh science"
        bl_options = {"REGISTER"}

        export_xyz: BoolProperty(name="Export derived XYZ", default=False)
        export_path: StringProperty(
            name="XYZ Path",
            subtype="FILE_PATH",
            options={"SKIP_SAVE"},
        )
        atom_count_before: IntProperty(options={"HIDDEN", "SKIP_SAVE"})
        atom_count_after: IntProperty(options={"HIDDEN", "SKIP_SAVE"})
        coordinate_change_count: IntProperty(options={"HIDDEN", "SKIP_SAVE"})
        element_change_count: IntProperty(options={"HIDDEN", "SKIP_SAVE"})
        bond_change_count: IntProperty(options={"HIDDEN", "SKIP_SAVE"})
        affected_dataset_count: IntProperty(options={"HIDDEN", "SKIP_SAVE"})
        max_displacement_angstrom: FloatProperty(
            options={"HIDDEN", "SKIP_SAVE"}
        )
        cell_changed: BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

        def invoke(self, context, _event):
            try:
                session, obj, _source, _topology, _arguments = _active_values(
                    context
                )
                preview = preview_structure_object_edits(
                    session.project,
                    obj,
                )
                if not preview.has_changes:
                    raise ValueError("no scientific edits were detected")
                self.atom_count_before = preview.atom_count_before
                self.atom_count_after = preview.atom_count_after
                self.coordinate_change_count = preview.coordinate_change_count
                self.element_change_count = preview.element_change_count
                self.bond_change_count = (
                    preview.bond_added_count
                    + preview.bond_removed_count
                    + preview.bond_order_change_count
                )
                self.affected_dataset_count = len(
                    preview.affected_result_ids
                )
                self.max_displacement_angstrom = (
                    preview.max_displacement_angstrom
                )
                self.cell_changed = preview.cell_changed
                return context.window_manager.invoke_props_dialog(
                    self,
                    width=440,
                )
            except Exception as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}

        def draw(self, _context):
            layout = self.layout
            layout.label(
                text=(
                    f"Atoms: {self.atom_count_before} → "
                    f"{self.atom_count_after}"
                )
            )
            layout.label(
                text=(
                    f"Moved: {self.coordinate_change_count}; "
                    f"elements: {self.element_change_count}; "
                    f"bonds: {self.bond_change_count}"
                )
            )
            layout.label(
                text=(
                    "Maximum displacement: "
                    f"{self.max_displacement_angstrom:.6g} Å"
                )
            )
            layout.label(
                text=(
                    f"Cell changed: {'yes' if self.cell_changed else 'no'}"
                )
            )
            layout.label(
                text=(
                    f"Source-linked results not inherited: "
                    f"{self.affected_dataset_count}"
                ),
                icon="INFO",
            )
            layout.prop(self, "export_xyz")
            if self.export_xyz:
                layout.prop(self, "export_path")

        def execute(self, context):
            view = None
            try:
                session, source_obj, source, topology, arguments = (
                    _active_values(context)
                )
                if self.export_xyz and not self.export_path:
                    raise ValueError("choose an XYZ export path")
                batch = commit_structure_edits(
                    session.project,
                    source,
                    topology,
                    **arguments,
                )
                derived = batch.structures[0]
                derived_topology = (
                    None if not batch.topologies else batch.topologies[0]
                )
                from ..views import create_structure_view, remove_structure_view

                collection = (
                    source_obj.users_collection[0]
                    if source_obj.users_collection
                    else context.collection
                )
                view = create_structure_view(
                    derived,
                    derived_topology,
                    name=f"{source_obj.name} Derived",
                    collection=collection,
                )
                try:
                    session.project.commit(batch)
                except Exception:
                    remove_structure_view(view)
                    view = None
                    raise
                session.mark_dirty("scientific_edit")
                session.active_entity_id = derived.id
                session.active_view_object_name = view.name
                source_obj.select_set(False)
                view.select_set(True)
                context.view_layer.objects.active = view
                from .properties import advance_browser_revision

                advance_browser_revision(session)
                if self.export_xyz:
                    path = Path(bpy.path.abspath(self.export_path))
                    if path.suffix.lower() != ".xyz":
                        path = path.with_suffix(".xyz")
                    try:
                        _write_xyz(path, derived)
                    except OSError as error:
                        self.report(
                            {"WARNING"},
                            f"Derived Structure applied; XYZ export failed: {error}",
                        )
                self.report({"INFO"}, "Derived Structure created")
                return {"FINISHED"}
            except Exception as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}


    def draw_scientific_edit_controls(layout, context, session):
        obj = context.active_object
        if (
            obj is None
            or obj.get("cb_structure_contract") != _STRUCTURE_CONTRACT
            or obj.get("cb_structure_id")
            not in {str(value) for value in session.project.structures}
        ):
            return
        layout.separator()
        layout.operator(
            CHEMBLENDER_OT_apply_scientific_edits.bl_idname,
            icon="DUPLICATE",
        )


__all__ = ("preview_structure_object_edits",)
if bpy is not None:
    __all__ += (
        "CHEMBLENDER_OT_apply_scientific_edits",
        "draw_scientific_edit_controls",
    )
