"""Explicit critic2 text import, bound to a verified existing Structure."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from ..core.critic2_adapter import _load, parse_critic2_cpreport
from ..core.critic2_paths import parse_critic2_paths
from ..core.grid_cache_service import _ANGSTROM_SCALE
from ..core.import_pipeline import ImportCancelled
from ..core.model import ImportBatch, ParserReport, Structure, TopologyGraph
from . import wavefunction_import as imports
from .tasks import Task, TaskWorker


_BINDING_TOLERANCE_ANGSTROM = 1.e-5


def _cancel(is_cancelled):
    if is_cancelled():
        raise ImportCancelled("topology import cancelled")


def _structure_hash(structure):
    import numpy

    digest = hashlib.sha256()
    digest.update(repr((structure.id, structure.revision, structure.atomic_numbers,
                        structure.coordinates.unit,
                        None if structure.periodic is None else structure.periodic.pbc)).encode())
    for array in (structure.coordinates, structure.cell):
        if array is not None:
            digest.update(array.unit.encode())
            digest.update(numpy.asarray(array.values, dtype="<f8").tobytes())
    return digest.hexdigest()


def _validate_structure(document, structure, is_cancelled):
    """Match explicit species and atom coordinates; never infer atom IDs from CPs."""
    import numpy

    unit = document.get("units")
    section = document.get("structure")
    if unit not in _ANGSTROM_SCALE or not isinstance(section, dict) or type(section.get("is_molecule")) is not bool:
        raise ValueError("CPREPORT must contain explicit units and the complete structure section")
    if not isinstance(structure, Structure) or not structure.atomic_numbers:
        raise ValueError("select an existing nonempty Structure")
    atoms, species = section.get("cell_atoms"), section.get("species")
    if not isinstance(atoms, list) or not isinstance(species, list) or len(atoms) != len(structure.atomic_numbers) or section.get("number_of_cell_atoms") != len(atoms):
        raise ValueError("CPREPORT cell atom count does not match the bound Structure")
    species_map = {}
    for item in species:
        if (not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] <= 0
                or item["id"] in species_map or type(item.get("atomic_number")) is not int
                or not 0 <= item["atomic_number"] <= 118):
            raise ValueError("CPREPORT species must have unique explicit IDs and atomic numbers")
        species_map[item["id"]] = item["atomic_number"]
    if section.get("number_of_species") != len(species):
        raise ValueError("CPREPORT species count is inconsistent")

    def real(values, shape, label):
        array = numpy.asarray(values)
        if (array.shape != shape or array.dtype.kind not in "iuf"
                or not numpy.all(numpy.isfinite(array))):
            raise ValueError(f"CPREPORT {label} must contain finite real values")
        return array.astype(float)

    molecule = section["is_molecule"]
    periodic = structure.periodic is not None and any(structure.periodic.pbc)
    if molecule == periodic:
        raise ValueError("CPREPORT molecular/periodic identity differs from the Structure")
    scale = _ANGSTROM_SCALE[unit]
    centering = real(section.get("molecule_centering_vector"), (3,), "centering vector") if molecule else numpy.zeros(3)
    cell = None
    if not molecule:
        if structure.cell is None or (structure.periodic is not None and not all(structure.periodic.pbc)):
            raise ValueError("periodic CPREPORT currently requires a fully periodic Structure")
        matrix = real(section.get("crys_to_cart_matrix"), (9,), "crystal matrix").reshape((3, 3), order="F")
        cell = matrix.T * scale
        expected = numpy.asarray(structure.cell.values) * _ANGSTROM_SCALE[structure.cell.unit]
        if not numpy.allclose(cell, expected, atol=_BINDING_TOLERANCE_ANGSTROM, rtol=0):
            raise ValueError("CPREPORT lattice does not match the bound Structure")
    positions = numpy.asarray(structure.coordinates.values) * _ANGSTROM_SCALE[structure.coordinates.unit]
    used, atom_ids, mapping = set(), set(), []
    for item in atoms:
        _cancel(is_cancelled)
        if (not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] <= 0
                or item["id"] in atom_ids or type(item.get("species")) is not int
                or item["species"] not in species_map):
            raise ValueError("CPREPORT cell atoms require unique IDs and known species")
        atom_ids.add(item["id"])
        position = (real(item.get("cartesian_coordinates"), (3,), "atom coordinates") + centering) * scale
        difference = positions - position
        if cell is not None:
            fractions = real(item.get("fractional_coordinates"), (3,), "fractional coordinates")
            if not numpy.allclose(fractions @ cell, position, atol=_BINDING_TOLERANCE_ANGSTROM, rtol=0):
                raise ValueError("CPREPORT fractional and Cartesian atom coordinates disagree")
            reduced = numpy.linalg.solve(cell.T, difference.T).T
            difference = (reduced - numpy.rint(reduced)) @ cell
        candidates = [index for index, (number, delta) in enumerate(zip(structure.atomic_numbers, difference))
                      if index not in used and number == species_map[item["species"]]
                      and numpy.linalg.norm(delta) <= _BINDING_TOLERANCE_ANGSTROM]
        if len(candidates) != 1:
            raise ValueError("CPREPORT atom identities/coordinates do not uniquely match the Structure")
        used.add(candidates[0])
        mapping.append({"cell_atom_id": item["id"], "structure_atom_index": candidates[0]})
    return mapping


def load_topology_batch(cpreport_path, *, structure, field_kind, fluxprint_path=None,
                        endpoint_tolerance_bohr=.02, temp_parent, is_cancelled=lambda: False,
                        progress=lambda _stage, _value: None):
    """Freeze selected text files, parse off-thread and return a complete detached batch."""
    if field_kind != "ELECTRON_DENSITY_AU":
        raise ValueError("explicitly select electron density in atomic units for QTAIM")
    if not isinstance(structure, Structure):
        raise ValueError("select the Structure that produced the critic2 result")
    binding_hash = _structure_hash(structure)
    sources = {"cpreport.json": Path(cpreport_path).resolve(strict=True)}
    if fluxprint_path:
        sources["flux.txt"] = Path(fluxprint_path).resolve(strict=True)
    if any(not path.is_file() for path in sources.values()):
        raise ValueError("select regular CPREPORT JSON and optional FLUXPRINT TEXT files")
    hashes = {name: imports._source_hash(path, is_cancelled) for name, path in sources.items()}
    progress("freeze critic2 files", .1)
    with TemporaryDirectory(prefix="topology-", dir=temp_parent) as temporary:
        root = Path(temporary)
        for name, source in sources.items():
            with source.open("rb") as reader, (root / name).open("xb") as writer:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    _cancel(is_cancelled)
                    writer.write(chunk)
            if imports._source_hash(root / name, is_cancelled) != hashes[name]:
                raise ValueError("critic2 source changed while freezing input")
        _, _, document = _load(root / "cpreport.json")
        mapping = _validate_structure(document, structure, is_cancelled)
        progress("parse critical points", .3)
        base = parse_critic2_cpreport(
            root / "cpreport.json", structure_id=structure.id,
            coordinate_unit=structure.coordinates.unit, field_semantic_role="electron_density",
            field_unit="inverse_cubic_bohr", laplacian_unit="inverse_bohr_fifth",
        )
        _cancel(is_cancelled)
        derived = None
        if "flux.txt" in sources:
            progress("parse ordered gradient paths", .6)
            derived = parse_critic2_paths(root / "flux.txt", graph=base.datasets[0],
                cpreport_path=root / "cpreport.json", endpoint_tolerance=endpoint_tolerance_bohr)
        _cancel(is_cancelled)
        progress("verify frozen sources", .85)
        for name, source in sources.items():
            if (imports._source_hash(source, is_cancelled) != hashes[name]
                    or imports._source_hash(root / name, is_cancelled) != hashes[name]):
                raise ValueError("critic2 source changed during import")
        if _structure_hash(structure) != binding_hash:
            raise ValueError("bound Structure changed during topology import")
        provenance = base.provenance + (() if derived is None else derived.provenance)
        binding = {
            "structure_id": str(structure.id), "structure_revision": structure.revision,
            "structure_hash": binding_hash, "field_kind": field_kind,
            "atom_mapping": mapping, "atom_tolerance_angstrom": _BINDING_TOLERANCE_ANGSTROM,
            "field_document": document.get("field"),
            "files": {name: {"path": str(path), "sha256": hashes[name]} for name, path in sources.items()},
        }
        provenance = tuple(replace(record,
            source=str(sources[Path(record.source).name]),
            parameters=(*record.parameters, ("topology_import_binding", binding))) for record in provenance)
        datasets = base.datasets + (() if derived is None else derived.datasets)
        reports = (base.report,) if derived is None else (base.report, derived.report)
        return ImportBatch(datasets=datasets, provenance=provenance, report=ParserReport(
            reader_id="critic2-topology-import", reader_version="1",
            parsed_capabilities=("topology",) if derived is None else ("topology", "ordered_gradient_paths"),
            created_entity_ids=tuple(item.id for item in (*datasets, *provenance)),
            issues=tuple(issue for report in reports for issue in report.issues),
        ))


def commit_topology_batch(session, batch, *, is_cancelled=lambda: False):
    """Verify the frozen binding again, then publish all new graph entities once."""
    _cancel(is_cancelled)
    if (not isinstance(batch, ImportBatch) or not batch.datasets or not batch.provenance
            or any(not isinstance(value, TopologyGraph) for value in batch.datasets)):
        raise ValueError("topology import requires a complete graph batch")
    binding = dict(batch.provenance[0].parameters).get("topology_import_binding")
    if not isinstance(binding, dict):
        raise ValueError("topology import is missing its frozen source binding")
    structure = session.project.structures.get(UUID(binding["structure_id"]))
    if (structure is None or structure.revision != binding["structure_revision"]
            or _structure_hash(structure) != binding["structure_hash"]):
        raise ValueError("bound Structure changed before topology publication")
    if any(graph.structure_id != structure.id for graph in batch.datasets):
        raise ValueError("topology graph refers to another Structure")
    for item in binding["files"].values():
        if imports._source_hash(Path(item["path"]), is_cancelled) != item["sha256"]:
            raise ValueError("critic2 source changed before topology publication")
    # A CP-only import can later acquire paths without replacing its parent.
    def new(values, registry):
        result = []
        for item in values:
            existing = registry.get(item.id)
            if existing is None:
                result.append(item)
            elif existing.revision != item.revision:
                raise ValueError("topology entity identity conflicts with the current project")
        return tuple(result)
    fresh = replace(batch, datasets=new(batch.datasets, session.project.datasets),
                    provenance=new(batch.provenance, session.project.provenance))
    if not fresh.datasets:
        raise ValueError("this topology result is already imported")
    fresh = replace(fresh, report=replace(fresh.report,
        created_entity_ids=tuple(item.id for item in (*fresh.datasets, *fresh.provenance))))
    _cancel(is_cancelled)
    session.project.commit(fresh)
    session.mark_dirty("topology import")
    session.active_entity_id = batch.datasets[-1].id
    return fresh


try:
    import bpy
    from bpy.props import EnumProperty, FloatProperty, PointerProperty, StringProperty
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    _SCENE_PROPERTY_NAME = "chemblender_topology_import"
    _OWNED_SCENE_PROPERTY = None
    _STRUCTURE_ITEMS = {}

    def _structure_items(self, context):
        from .session import get_scene_session
        values = () if context is None else get_scene_session(context.scene).project.structures.values()
        key = tuple((str(value.id), len(value.atomic_numbers)) for value in values)
        if key not in _STRUCTURE_ITEMS:
            _STRUCTURE_ITEMS[key] = [("NONE", "Select Structure", "Explicitly bind the critic2 calculation")]
            _STRUCTURE_ITEMS[key].extend((identity, f"{count} atoms · {identity[:8]}", identity) for identity, count in key)
        return _STRUCTURE_ITEMS[key]

    def _structure_get(self):
        return next((index for index, item in enumerate(_structure_items(self, bpy.context))
                     if item[0] == self.structure_uuid), 0)

    def _structure_set(self, index):
        items = _structure_items(self, bpy.context)
        if not 0 <= index < len(items):
            raise ValueError("invalid Structure selection")
        self.structure_uuid = "" if index == 0 else items[index][0]

    class CHEMBLENDER_PG_topology_import(bpy.types.PropertyGroup):
        structure_uuid: StringProperty(options={"HIDDEN"})
        structure_id: EnumProperty(name="Structure", items=_structure_items, get=_structure_get, set=_structure_set)
        cpreport_file: StringProperty(name="CPREPORT JSON", subtype="FILE_PATH")
        fluxprint_file: StringProperty(name="FLUXPRINT TEXT (optional)", subtype="FILE_PATH")
        field_kind: EnumProperty(name="Analyzed Field", default="UNSET", items=(
            ("UNSET", "Select Field and Units", "Confirm what critic2 analyzed"),
            ("ELECTRON_DENSITY_AU", "Electron Density (atomic units)", "rho in bohr^-3; Laplacian and Hessian in bohr^-5"),
        ))
        endpoint_tolerance_bohr: FloatProperty(name="Path Endpoint Tolerance (bohr)", default=.02, min=1.e-8, max=.1)

    class CHEMBLENDER_OT_import_topology(imports.ExternalReaderImportOperator, bpy.types.Operator):
        bl_idname = "chemblender.import_topology"
        bl_label = "Import QTAIM Files"
        bl_description = "Import explicit critic2 critical points and sampled paths bound to an existing Structure"

        def execute(self, context):
            from .session import get_scene_session
            self._cancel_requested = False
            self._timer = None
            self._manager = context.window_manager
            self._session = get_scene_session(context.scene)
            if any(operator._session is self._session for operator in imports._ACTIVE_IMPORTS):
                self.report({"ERROR"}, "a scientific file import is already running")
                return {"CANCELLED"}
            try:
                settings = context.scene.chemblender_topology_import
                if not settings.structure_uuid:
                    raise ValueError("select the Structure that produced the critic2 result")
                structure = self._session.project.structures.get(UUID(settings.structure_uuid))
                if structure is None:
                    raise ValueError("select the Structure that produced the critic2 result")
                source = bpy.path.abspath(settings.cpreport_file)
                flux = bpy.path.abspath(settings.fluxprint_file) if settings.fluxprint_file.strip() else None
                options = {"structure": structure, "field_kind": settings.field_kind,
                           "fluxprint_path": flux, "endpoint_tolerance_bohr": settings.endpoint_tolerance_bohr,
                           "temp_parent": self._session.temporary_root}
                self._job = TaskWorker(Task(), lambda cancelled, progress: load_topology_batch(
                    source, is_cancelled=cancelled, progress=progress, **options))
                imports._ACTIVE_IMPORTS.append(self)
                self._job.start("import QTAIM files")
                if bpy.app.background:
                    self._job.join()
                    return self._complete(context)
                self._timer = self._manager.event_timer_add(.1, window=context.window)
                self._manager.modal_handler_add(self)
                return {"RUNNING_MODAL"}
            except Exception as error:
                self.cancel(context)
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}

        def commit_batch(self, context, batch):
            commit_topology_batch(self._session, batch, is_cancelled=lambda: self._cancel_requested)

    def draw_topology_import(layout, context, session):
        settings = context.scene.chemblender_topology_import
        box = layout.box()
        box.label(text="QTAIM / critic2")
        box.prop(settings, "structure_id")
        box.prop(settings, "cpreport_file")
        box.prop(settings, "fluxprint_file")
        box.prop(settings, "field_kind")
        if settings.fluxprint_file:
            box.prop(settings, "endpoint_tolerance_bohr")
        row = box.row()
        row.enabled = not any(operator._session is session for operator in imports._ACTIVE_IMPORTS)
        row.operator("chemblender.import_topology", icon="IMPORT")
        for operator in imports._ACTIVE_IMPORTS:
            if isinstance(operator, CHEMBLENDER_OT_import_topology) and operator._session is session:
                snapshot = operator._job.task.snapshot()
                box.label(text=f"{snapshot.stage}: {snapshot.progress:.0%} (Esc to cancel)")
        box.label(text="Connections require sampled TEXT paths to draw tubes")

    def register():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        current = _scene_property_identity(_SCENE_PROPERTY_NAME)
        if _OWNED_SCENE_PROPERTY is not None and _same_scene_property(current, _OWNED_SCENE_PROPERTY):
            return
        if current is not None:
            raise RuntimeError(f"Scene.{_SCENE_PROPERTY_NAME} is already owned")
        setattr(bpy.types.Scene, _SCENE_PROPERTY_NAME, PointerProperty(type=CHEMBLENDER_PG_topology_import))
        _OWNED_SCENE_PROPERTY = _scene_property_identity(_SCENE_PROPERTY_NAME)

    def unregister():
        global _OWNED_SCENE_PROPERTY
        from .properties import _same_scene_property, _scene_property_identity
        for operator in tuple(imports._ACTIVE_IMPORTS):
            if isinstance(operator, CHEMBLENDER_OT_import_topology):
                operator.cancel(None)
        if _OWNED_SCENE_PROPERTY is not None and _same_scene_property(_scene_property_identity(_SCENE_PROPERTY_NAME), _OWNED_SCENE_PROPERTY):
            delattr(bpy.types.Scene, _SCENE_PROPERTY_NAME)
        _OWNED_SCENE_PROPERTY = None
        _STRUCTURE_ITEMS.clear()
