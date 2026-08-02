"""Background export for the active Project Browser entity."""

from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from uuid import UUID

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)

from ..core import (
    AtomicProperty,
    CIFEnvelope,
    ConformerSet,
    DatasetStatus,
    FrameSet,
    Grid3D,
    MolecularRecord,
    Structure,
    TopologyRecord,
)
from ..core.exporters import (
    ExportReport,
    ExportReportEntry,
    PoscarExportSettings,
    export_extxyz,
    export_cif,
    export_cube,
    export_xyz,
    export_mol,
    export_mol2,
    export_pdb,
    export_pqr,
    export_poscar,
    export_sdf,
    export_smiles,
    preview_extxyz_export,
    preview_cube_export,
    preview_molecular_export,
    preview_mol2_export,
    preview_pdb_export,
    preview_pqr_export,
    plan_cif_export,
    sdf_entries_from_conformer_set,
)
from ..core.formats.poscar import PoscarLatticeVelocityBlock
from .session import get_scene_session


_FORMAT_ITEMS = (
    ("xyz", "XYZ", "Export one Structure"),
    ("extxyz", "extXYZ", "Export a Structure or trajectory with properties"),
    ("cube", "Cube", "Export one selected Grid3D dataset"),
    ("mol", "MOL", "Export a molecular Structure"),
    ("mol2", "MOL2", "Export a molecular Structure with Tripos metadata"),
    ("pdb", "PDB", "Export a biological Structure"),
    ("pqr", "PQR", "Export a biological Structure with charges and radii"),
    ("sdf", "SDF", "Export molecular records or conformers"),
    ("smiles", "SMILES", "Export a molecular Structure"),
    ("cif", "CIF", "Export a periodic Structure"),
    ("poscar", "POSCAR/CONTCAR", "Export a periodic Structure for VASP"),
)
_CIF_ACTION_LABELS = {
    "preserve": "Preserved",
    "replace": "Changed",
    "add": "Added",
    "omit": "Omitted",
}
_FATAL_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    MemoryError,
)


def _merge_cleanup_failure(failure, error, label):
    if failure is None:
        return error
    if isinstance(error, _FATAL_EXCEPTIONS) and not isinstance(
        failure,
        _FATAL_EXCEPTIONS,
    ):
        error.add_note(f"earlier cleanup failed: {failure}")
        return error
    failure.add_note(f"{label}: {error}")
    return failure


@dataclass(frozen=True, slots=True)
class ExportSelection:
    structure: Structure
    frame_set: FrameSet | None
    properties: tuple
    topology: TopologyRecord | None = None
    record: MolecularRecord | None = None
    conformer_set: ConformerSet | None = None
    records_by_id: dict | None = None
    cif_envelope: CIFEnvelope | None = None
    provenance: tuple = ()
    source_structure_id: UUID | None = None
    annotations: tuple = ()
    biological_hierarchies: tuple = ()
    associated_topologies: tuple = ()
    grid: Grid3D | None = None


def _with_structure_origin(project, selection):
    source_id = next(
        (
            result.structure_id
            for result in getattr(project, "symmetry_results", {}).values()
            if result.standardized_structure_id == selection.structure.id
        ),
        None,
    )
    biological_hierarchies = tuple(
        value
        for value in getattr(project, "biological_hierarchies", {}).values()
        if value.structure_id == selection.structure.id
    )
    associated_topologies = tuple(
        value
        for value in getattr(project, "topologies", {}).values()
        if value.structure_id == selection.structure.id
    )
    return replace(
        selection,
        source_structure_id=source_id,
        biological_hierarchies=biological_hierarchies,
        associated_topologies=associated_topologies,
    )


def _structure_context(project, structure):
    created_ids = set()
    for revision in getattr(project, "source_revisions", {}).values():
        if structure.id in revision.created_entity_ids:
            created_ids.update(revision.created_entity_ids)
    direct = tuple(
        value
        for value in getattr(project, "datasets", {}).values()
        if (
            getattr(value, "structure_id", None) == structure.id
            or value.id in created_ids
        )
    )
    provenance_ids = created_ids.union(
        provenance_id
        for value in direct
        for provenance_id in getattr(value, "provenance_ids", ())
    )
    direct_ids = {value.id for value in direct}
    properties = tuple(
        value
        for value in getattr(project, "datasets", {}).values()
        if (
            value.id in direct_ids
            or provenance_ids.intersection(
                getattr(value, "provenance_ids", ())
            )
        )
    )
    provenance = tuple(
        value
        for value in getattr(project, "provenance", {}).values()
        if value.id in provenance_ids
    )
    return properties, provenance


def _molecular_selection(
    project,
    structure,
    *,
    record=None,
    conformer_set=None,
):
    explicit_record = record is not None
    topologies = tuple(
        project.topologies[topology_id]
        for topology_id in structure.topology_ids
        if topology_id in project.topologies
        and project.topologies[topology_id].quality_status.value == "complete"
    )
    if not topologies:
        if explicit_record:
            raise ValueError(
                "selected MolecularRecord has no matching complete topology"
            )
        raise ValueError("selected Structure has no complete molecular topology")
    if record is None:
        record = next(
            (
                item
                for item in project.molecular_records.values()
                if item.structure_id == structure.id
            ),
            None,
        )
    required_topology_id = (
        conformer_set.reference_topology_id
        if conformer_set is not None
        else record.topology_id if explicit_record else None
    )
    topology = next(
        (
            item
            for item in topologies
            if item.id == required_topology_id
        ),
        topologies[0] if required_topology_id is None else None,
    )
    if topology is None:
        if conformer_set is not None:
            raise ValueError(
                "selected ConformerSet has no matching complete topology"
            )
        raise ValueError(
            "selected MolecularRecord has no matching complete topology"
        )
    if conformer_set is not None:
        record = None
    elif record is not None and record.topology_id not in {None, topology.id}:
        record = None
    properties, provenance = _structure_context(project, structure)
    properties = tuple(
        value
        for value in properties
        if getattr(value, "structure_id", None) == structure.id
    )
    annotation_targets = {
        structure.id,
        topology.id,
        *(value.id for value in properties),
    }
    if record is not None:
        annotation_targets.add(record.id)
    annotations = tuple(
        value
        for value in getattr(project, "annotations", {}).values()
        if value.target_entity_id in annotation_targets
    )
    return ExportSelection(
        structure, None, properties, topology, record, conformer_set,
        {item.id: item for item in project.molecular_records.values()},
        getattr(project, "cif_envelopes", {}).get(
            getattr(structure.periodic, "cif_envelope_id", None)
            if structure.periodic is not None
            else None
        ),
        provenance,
        annotations=annotations,
    )


def _mol2_entities(selection):
    if selection.conformer_set is not None:
        raise ValueError("ConformerSet export requires SDF")
    return SimpleNamespace(
        structures=(selection.structure,),
        topologies=(() if selection.topology is None else (selection.topology,)),
        molecular_records=(() if selection.record is None else (selection.record,)),
        annotations=selection.annotations,
        datasets=selection.properties,
    )


def _pdb_entities(selection):
    datasets = []
    seen = set()
    for value in (
        *((selection.frame_set,) if selection.frame_set is not None else ()),
        *selection.properties,
    ):
        if (
            getattr(value, "structure_id", None) != selection.structure.id
            or value.id in seen
        ):
            continue
        seen.add(value.id)
        datasets.append(value)
    return SimpleNamespace(
        structures=(selection.structure,),
        biological_hierarchies=selection.biological_hierarchies,
        datasets=tuple(datasets),
        topologies=selection.associated_topologies,
        sources=(),
        source_revisions=(),
    )


def _cube_entities(selection):
    if selection.grid is None:
        raise ValueError("Cube export requires a Grid3D selection")
    charges = tuple(
        value
        for value in selection.properties
        if isinstance(value, AtomicProperty)
        and value.structure_id == selection.structure.id
        and value.semantic_role == "nuclear_charge"
    )
    return SimpleNamespace(
        structures=(selection.structure,),
        datasets=(selection.grid, *charges),
        provenance=selection.provenance,
        topologies=selection.associated_topologies,
    )


def _extxyz_properties(selection):
    if selection.frame_set is None:
        return selection.properties
    return tuple(
        value
        for value in selection.properties
        if getattr(value, "frame_set_id", None) == selection.frame_set.id
    )


def resolve_export_selection(project, entity_id):
    if type(entity_id) is not UUID:
        raise TypeError("select a Structure, FrameSet or Grid3D before exporting")
    structure = project.structures.get(entity_id)
    if structure is not None:
        properties, provenance = _structure_context(project, structure)
        try:
            selection = _molecular_selection(project, structure)
        except ValueError:
            envelope = getattr(project, "cif_envelopes", {}).get(
                getattr(structure.periodic, "cif_envelope_id", None)
                if structure.periodic is not None
                else None
            )
            selection = ExportSelection(
                structure,
                None,
                properties,
                cif_envelope=envelope,
                provenance=provenance,
            )
        return _with_structure_origin(project, selection)
    record = project.molecular_records.get(entity_id)
    if record is not None:
        structure = project.structures.get(record.structure_id)
        if structure is None:
            raise ValueError("selected MolecularRecord has no Structure")
        return _with_structure_origin(
            project,
            _molecular_selection(project, structure, record=record),
        )
    frame_set = project.datasets.get(entity_id)
    if isinstance(frame_set, Grid3D):
        structure = project.structures.get(frame_set.structure_id)
        if structure is None or structure.id != frame_set.structure_id:
            raise ValueError("selected Grid3D has no matching Structure")
        charges = tuple(
            value
            for value in project.datasets.values()
            if isinstance(value, AtomicProperty)
            and value.structure_id == structure.id
            and value.semantic_role == "nuclear_charge"
        )
        provenance_ids = {
            provenance_id
            for value in (frame_set, *charges)
            for provenance_id in value.provenance_ids
        }
        return _with_structure_origin(
            project,
            ExportSelection(
                structure,
                None,
                charges,
                provenance=tuple(
                    value
                    for value in project.provenance.values()
                    if value.id in provenance_ids
                ),
                grid=frame_set,
            ),
        )
    if isinstance(frame_set, ConformerSet):
        structure = project.structures.get(frame_set.reference_structure_id)
        if structure is None:
            raise ValueError("selected ConformerSet has no Structure")
        return _with_structure_origin(
            project,
            _molecular_selection(
                project,
                structure,
                conformer_set=frame_set,
            ),
        )
    if not isinstance(frame_set, FrameSet):
        raise ValueError(
            "selected entity is not an exportable Structure, FrameSet or Grid3D"
        )
    structure = project.structures.get(frame_set.structure_id)
    if structure is None:
        raise ValueError("selected FrameSet has no Structure")
    return _with_structure_origin(
        project,
        ExportSelection(
            structure,
            frame_set,
            tuple(
                dataset
                for dataset in project.datasets.values()
                if (
                    getattr(dataset, "frame_set_id", None) == frame_set.id
                    or isinstance(dataset, AtomicProperty)
                    and dataset.structure_id == structure.id
                )
            ),
        ),
    )


def _poscar_parts(selection, settings=None):
    properties = {
        value.semantic_role: value
        for value in selection.properties
        if hasattr(value, "semantic_role")
    }
    provenance = next(
        (
            value
            for value in selection.provenance
            if value.producer == "ChemBlender POSCAR adapter"
        ),
        None,
    )
    parameters = {} if provenance is None else dict(provenance.parameters)
    scale = parameters.get("scale")
    inferred_settings = PoscarExportSettings(
        comment=str(parameters.get("comment") or "ChemBlender"),
        coordinate_mode=str(
            parameters.get("coordinate_mode") or "direct"
        ),
        scale_policy=(
            "preserve_source"
            if isinstance(scale, (int, float)) and not isinstance(scale, bool)
            else "unit"
        ),
        source_scale=(
            float(scale)
            if isinstance(scale, (int, float)) and not isinstance(scale, bool)
            else None
        ),
        velocity_mode=str(parameters.get("velocity_mode") or "cartesian"),
    )
    if settings is None:
        settings = inferred_settings
    elif not isinstance(settings, PoscarExportSettings):
        raise TypeError("poscar_settings must be PoscarExportSettings or None")
    lattice = None
    lattice_property = properties.get("lattice_velocity")
    lattice_vectors = parameters.get("lattice_velocity_vectors")
    initialization = parameters.get(
        "lattice_velocity_initialization_state"
    )
    if (
        lattice_property is not None
        and lattice_vectors is not None
        and initialization is not None
    ):
        lattice = PoscarLatticeVelocityBlock(
            float(initialization),
            tuple(
                tuple(map(float, row))
                for row in lattice_property.data.values
            ),
            tuple(tuple(map(float, row)) for row in lattice_vectors),
        )
    return (
        settings,
        (
            properties.get("selective_dynamics")
            if settings.include_selective_dynamics
            else None
        ),
        properties.get("atomic_velocity"),
        lattice,
    )


def _poscar_preview(selection, settings=None):
    import numpy

    settings, selective, velocities, lattice = _poscar_parts(
        selection,
        settings,
    )
    periodic = selection.structure.periodic
    if selection.frame_set is not None or periodic is None:
        raise ValueError("POSCAR export requires one periodic Structure")
    entries = [
        ExportReportEntry(
            f"scale_{settings.scale_policy}",
            f"POSCAR scale policy: {settings.scale_policy}",
        ),
        ExportReportEntry(
            f"coordinates_{settings.coordinate_mode}",
            f"POSCAR coordinates: {settings.coordinate_mode}",
        ),
    ]
    loss = []
    occupancies = numpy.asarray(periodic.occupancies.values, dtype=float)
    if not numpy.allclose(occupancies, 1.0, rtol=0.0, atol=1.0e-12):
        loss.append(
            ExportReportEntry(
                "occupancy_omitted",
                "POSCAR omits partial or missing occupancies",
            )
        )
    if (
        periodic.isotropic_displacements is not None
        or periodic.anisotropic_displacements is not None
    ):
        loss.append(
            ExportReportEntry(
                "adp_omitted",
                "POSCAR omits atomic displacement parameters",
            )
        )
    if (
        periodic.declared_symmetry.name is not None
        or periodic.declared_symmetry.operations
    ):
        loss.append(
            ExportReportEntry(
                "symmetry_omitted",
                "POSCAR omits declared symmetry metadata",
            )
        )
    if selective is not None:
        entries.append(
            ExportReportEntry(
                "selective_dynamics",
                "Selective Dynamics will be exported",
            )
        )
    elif settings.include_selective_dynamics is False and any(
        getattr(value, "semantic_role", None) == "selective_dynamics"
        for value in selection.properties
    ):
        loss.append(
            ExportReportEntry(
                "selective_dynamics_omitted",
                "POSCAR Selective Dynamics flags will be omitted",
            )
        )
    if velocities is not None or lattice is not None:
        entries.append(
            ExportReportEntry(
                "velocities",
                "Selected POSCAR velocity data will be exported",
            )
        )
    return ExportReport(
        "poscar",
        False,
        1,
        bool(loss),
        tuple((*loss, *entries)),
    )


def _crystal_plan_entries(selection, target, destination):
    entries = [
        ExportReportEntry(
            f"target:{target}",
            f"Target format: {target.replace('_', ' ')}",
        ),
        ExportReportEntry(
            (
                "structure:derived"
                if selection.source_structure_id is not None
                else "structure:source"
            ),
            (
                f"Derived Structure {selection.structure.id} from "
                f"{selection.source_structure_id}"
                if selection.source_structure_id is not None
                else f"Source Structure: {selection.structure.id}"
            ),
        ),
    ]
    if destination is not None:
        entries.append(
            ExportReportEntry(
                "output_path",
                f"Output path: {Path(destination)}",
            )
        )
    quality = {
        status
        for value in selection.properties
        if (
            (status := getattr(value, "status", None))
            in {DatasetStatus.PARTIAL, DatasetStatus.AMBIGUOUS}
        )
    }
    entries.extend(
        ExportReportEntry(
            f"quality:{status.value}",
            f"Related data quality: {status.value}",
        )
        for status in sorted(quality, key=lambda value: value.value)
    )
    return tuple(entries), bool(quality)


def preview_export_selection(
    selection,
    format_name,
    missing_value_token=None,
    *,
    cif_mode=None,
    poscar_settings=None,
    destination=None,
    dataset_index=None,
):
    if type(selection) is not ExportSelection:
        raise TypeError("selection must be an ExportSelection")
    if format_name == "cube":
        return preview_cube_export(
            _cube_entities(selection),
            dataset_index=dataset_index,
        )
    if format_name == "xyz":
        if selection.frame_set is not None:
            raise ValueError("FrameSet export requires extXYZ")
        return ExportReport("xyz", False, 1, False)
    if format_name == "cif":
        if selection.frame_set is not None or selection.structure.periodic is None:
            raise ValueError("CIF export requires one periodic Structure")
        mode = cif_mode or (
            "preserve"
            if selection.cif_envelope is not None
            else "normalized"
        )
        plan = plan_cif_export(
            selection.structure,
            envelope=selection.cif_envelope,
            mode=mode,
        )
        context_entries, quality_warning = _crystal_plan_entries(
            selection,
            f"cif_{mode}",
            destination,
        )
        omitted_source_content = (
            selection.cif_envelope is not None
            and any(
                field.name == "unknown_content" and field.action == "omit"
                for field in plan.fields
            )
        )
        return ExportReport(
            "cif",
            False,
            1,
            quality_warning or omitted_source_content,
            context_entries
            + tuple(
                ExportReportEntry(
                    f"{field.action}:{field.name}",
                    f"{_CIF_ACTION_LABELS[field.action]}: {field.detail}",
                )
                for field in plan.fields
            ),
        )
    if format_name == "poscar":
        report = _poscar_preview(selection, poscar_settings)
        context_entries, quality_warning = _crystal_plan_entries(
            selection,
            "poscar",
            destination,
        )
        return replace(
            report,
            requires_confirmation=(
                report.requires_confirmation or quality_warning
            ),
            entries=context_entries + report.entries,
        )
    if format_name == "mol2":
        if selection.topology is None:
            raise ValueError("molecular export requires a complete topology")
        return preview_mol2_export(_mol2_entities(selection))
    if format_name == "pdb":
        return preview_pdb_export(_pdb_entities(selection))
    if format_name == "pqr":
        return preview_pqr_export(_pdb_entities(selection))
    if format_name in {"mol", "sdf", "smiles"}:
        if selection.topology is None:
            raise ValueError("molecular export requires a complete topology")
        if selection.conformer_set is not None and format_name != "sdf":
            raise ValueError("ConformerSet export requires SDF")
        frame_count = (
            len(selection.conformer_set.record_ids)
            if selection.conformer_set is not None
            else 1
        )
        extra_entries = ()
        if selection.conformer_set is not None:
            records = selection.records_by_id or {}
            missing_count = sum(
                record_id not in records
                for record_id in selection.conformer_set.record_ids
            )
            if missing_count:
                extra_entries = (
                    ExportReportEntry(
                        "conformer_properties_omitted",
                        (
                            f"{missing_count} conformer(s) have no matching "
                            "source record for properties"
                        ),
                    ),
                )
        return preview_molecular_export(
            selection.structure,
            selection.topology,
            record=(
                None
                if selection.conformer_set is not None
                else selection.record
            ),
            format_name=format_name,
            frame_count=frame_count,
            extra_loss_entries=extra_entries,
        )
    if format_name != "extxyz":
        raise ValueError(
            "format_name must be xyz, extxyz, cube, mol, mol2, pdb, pqr, sdf, "
            "smiles, cif or poscar"
        )
    return preview_extxyz_export(
        selection.structure,
        frame_set=selection.frame_set,
        properties=_extxyz_properties(selection),
        missing_value_token=missing_value_token or None,
    )


class ExportJob:
    def __init__(
        self,
        destination,
        selection,
        *,
        format_name,
        confirm_loss,
        missing_value_token,
        dataset_index=None,
        cif_mode=None,
        poscar_settings=None,
    ):
        self.destination = Path(destination)
        self.selection = selection
        self.format_name = format_name
        self.confirm_loss = confirm_loss
        self.missing_value_token = missing_value_token
        self.dataset_index = dataset_index
        self.cif_mode = cif_mode
        self.poscar_settings = poscar_settings
        self.result = None
        self.error = None
        self._cancelled = Event()
        self._done = Event()
        self._started = False
        self._thread = Thread(target=self._run, daemon=True)
        self._window_manager = None
        self._timer = None
        self._progress_started = False

    def _run(self):
        try:
            if self.format_name in {"cif", "poscar"}:
                preview = preview_export_selection(
                    self.selection,
                    self.format_name,
                    cif_mode=self.cif_mode,
                    poscar_settings=self.poscar_settings,
                    destination=self.destination,
                )
                if preview.requires_confirmation and not self.confirm_loss:
                    raise ValueError(
                        "Loss/Partial/Ambiguous export requires explicit "
                        "confirmation"
                    )
            if self.format_name == "xyz":
                self.result = export_xyz(
                    self.destination,
                    self.selection.structure,
                    is_cancelled=self._cancelled.is_set,
                )
            elif self.format_name == "extxyz":
                self.result = export_extxyz(
                    self.destination,
                    self.selection.structure,
                    frame_set=self.selection.frame_set,
                    properties=_extxyz_properties(self.selection),
                    confirm_loss=self.confirm_loss,
                    missing_value_token=self.missing_value_token or None,
                    is_cancelled=self._cancelled.is_set,
                )
            elif self.format_name == "cube":
                self.result = export_cube(
                    _cube_entities(self.selection),
                    dataset_index=self.dataset_index,
                    confirm_loss=self.confirm_loss,
                    destination=self.destination,
                    is_cancelled=self._cancelled.is_set,
                ).report
            elif self.format_name == "mol":
                self.result = export_mol(
                    self.selection.structure,
                    self.selection.topology,
                    record=self.selection.record,
                    confirm_loss=self.confirm_loss,
                    destination=self.destination,
                    is_cancelled=self._cancelled.is_set,
                ).report
            elif self.format_name == "mol2":
                self.result = export_mol2(
                    _mol2_entities(self.selection),
                    confirm_loss=self.confirm_loss,
                    destination=self.destination,
                    is_cancelled=self._cancelled.is_set,
                ).report
            elif self.format_name == "pdb":
                self.result = export_pdb(
                    _pdb_entities(self.selection),
                    confirm_loss=self.confirm_loss,
                    destination=self.destination,
                    is_cancelled=self._cancelled.is_set,
                ).report
            elif self.format_name == "pqr":
                self.result = export_pqr(
                    _pdb_entities(self.selection),
                    confirm_loss=self.confirm_loss,
                    destination=self.destination,
                    is_cancelled=self._cancelled.is_set,
                ).report
            elif self.format_name == "sdf":
                if self.selection.conformer_set is not None:
                    entries = sdf_entries_from_conformer_set(
                        self.selection.conformer_set,
                        self.selection.structure,
                        self.selection.topology,
                        self.selection.records_by_id or {},
                    )
                    self.result = export_sdf(
                        entries=entries,
                        confirm_loss=self.confirm_loss,
                        destination=self.destination,
                        is_cancelled=self._cancelled.is_set,
                    ).report
                else:
                    self.result = export_sdf(
                        self.selection.structure,
                        self.selection.topology,
                        record=self.selection.record,
                        confirm_loss=self.confirm_loss,
                        destination=self.destination,
                        is_cancelled=self._cancelled.is_set,
                    ).report
            elif self.format_name == "smiles":
                self.result = export_smiles(
                    self.selection.structure,
                    self.selection.topology,
                    record=self.selection.record,
                    confirm_loss=self.confirm_loss,
                    destination=self.destination,
                    is_cancelled=self._cancelled.is_set,
                ).report
            elif self.format_name == "cif":
                mode = self.cif_mode or (
                    "preserve"
                    if self.selection.cif_envelope is not None
                    else "normalized"
                )
                self.result = export_cif(
                    self.destination,
                    self.selection.structure,
                    envelope=self.selection.cif_envelope,
                    mode=mode,
                    is_cancelled=self._cancelled.is_set,
                )
            elif self.format_name == "poscar":
                (
                    settings,
                    selective,
                    velocities,
                    lattice,
                ) = _poscar_parts(
                    self.selection,
                    self.poscar_settings,
                )
                self.result = export_poscar(
                    self.destination,
                    self.selection.structure,
                    settings,
                    selective_dynamics=selective,
                    velocities=velocities,
                    lattice_velocities=lattice,
                    is_cancelled=self._cancelled.is_set,
                )
            else:
                raise ValueError(
                    "format_name must be xyz, extxyz, cube, mol, mol2, pdb, pqr, "
                    "sdf, smiles, cif or poscar"
                )
        except BaseException as error:
            self.error = error
        finally:
            self._done.set()

    def start(self):
        try:
            self._thread.start()
        except BaseException:
            self._started = self._thread.is_alive()
            raise
        else:
            self._started = True

    def cancel(self):
        self._cancelled.set()

    def join(self, timeout):
        if not self._started:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @property
    def done(self):
        return self._done.is_set()

    @property
    def timer_pending(self):
        return self._timer is not None

    def attach_ui(self, manager, timer):
        self._window_manager = manager
        self._timer = timer

    def mark_progress_started(self):
        self._progress_started = True

    def release_ui(self):
        manager = self._window_manager
        if manager is None:
            return
        failure = None
        if self._progress_started:
            try:
                manager.progress_end()
            except BaseException as error:
                failure = error
            else:
                self._progress_started = False
        if self._timer is not None:
            try:
                manager.event_timer_remove(self._timer)
            except BaseException as error:
                failure = _merge_cleanup_failure(
                    failure,
                    error,
                    "timer cleanup failed",
                )
            else:
                self._timer = None
        if self._timer is None and not self._progress_started:
            self._window_manager = None
        if failure is not None:
            raise failure

    def abandon_ui(self):
        self._window_manager = None
        self._timer = None
        self._progress_started = False


def _report_text(report):
    return "; ".join(entry.message for entry in report.entries) or "No data loss"


def _export_preview_changed(self, context):
    self.confirm_loss = False
    if getattr(self, "_suppress_preview_update", False):
        return
    preview = getattr(self, "_selection_and_preview", None)
    if preview is None:
        return
    try:
        preview(context)
    except (TypeError, ValueError) as error:
        self._preview_report = None
        self.loss_preview = str(error)


class CHEMBLENDER_OT_export_project_entity(bpy.types.Operator):
    bl_idname = "chemblender.export_project_entity"
    bl_label = "Export Selected Data"
    bl_description = "Export the selected Structure, FrameSet or Grid3D"

    filepath: StringProperty(
        subtype="FILE_PATH",
        update=_export_preview_changed,
    )
    filter_glob: StringProperty(
        default=(
            "*.xyz;*.extxyz;*.cube;*.mol;*.mol2;*.pdb;*.pqr;*.sdf;*.smi;"
            "*.smiles;*.cif;*.vasp;*.poscar;*.contcar"
        ),
        options={"HIDDEN"},
    )
    format_name: EnumProperty(
        items=_FORMAT_ITEMS,
        default="extxyz",
        update=_export_preview_changed,
    )
    cif_mode: EnumProperty(
        name="CIF Mode",
        items=(
            ("preserve", "Preserve", "Patch the bound source CIF envelope"),
            ("normalized", "Normalized", "Write a normalized CIF document"),
        ),
        default="normalized",
        update=_export_preview_changed,
    )
    poscar_coordinate_mode: EnumProperty(
        name="Coordinates",
        items=(
            ("direct", "Direct", "Write fractional coordinates"),
            ("cartesian", "Cartesian", "Write Cartesian coordinates"),
        ),
        default="direct",
        update=_export_preview_changed,
    )
    poscar_scale_policy: EnumProperty(
        name="Scale",
        items=(
            ("unit", "Unit", "Write a unit POSCAR scale"),
            (
                "preserve_source",
                "Preserve Source",
                "Reuse the verified source POSCAR scale",
            ),
            (
                "target_volume",
                "Target Volume",
                "Write the verified cell volume as a negative scale",
            ),
        ),
        default="unit",
        update=_export_preview_changed,
    )
    poscar_include_selective_dynamics: BoolProperty(
        name="Selective Dynamics",
        default=True,
        update=_export_preview_changed,
    )
    poscar_comment: StringProperty(
        name="Comment",
        default="ChemBlender",
        update=_export_preview_changed,
    )
    poscar_target_volume: FloatProperty(
        name="Target Volume",
        min=0.0,
        precision=8,
        update=_export_preview_changed,
    )
    poscar_velocity_mode: EnumProperty(
        name="Velocity Coordinates",
        items=(
            ("cartesian", "Cartesian", "Write Cartesian ion velocities"),
            ("direct", "Direct", "Write direct ion velocities"),
        ),
        default="cartesian",
        update=_export_preview_changed,
    )
    missing_value_token: StringProperty(
        name="Missing Value Token",
        update=_export_preview_changed,
    )
    cube_dataset_index: IntProperty(
        name="Dataset Index",
        default=-1,
        min=-1,
        update=_export_preview_changed,
    )
    confirm_loss: BoolProperty(
        name="Confirm Loss/Partial/Ambiguous Export",
        default=False,
    )
    loss_preview: StringProperty(name="Loss Preview")

    def _poscar_settings(self, selection):
        inferred, _selective, _velocities, _lattice = _poscar_parts(selection)
        scale_policy = getattr(
            self,
            "poscar_scale_policy",
            inferred.scale_policy,
        )
        target_volume = (
            getattr(self, "poscar_target_volume", 0.0)
            if scale_policy == "target_volume"
            else None
        )
        return PoscarExportSettings(
            comment=getattr(self, "poscar_comment", inferred.comment),
            coordinate_mode=getattr(
                self,
                "poscar_coordinate_mode",
                inferred.coordinate_mode,
            ),
            scale_policy=scale_policy,
            source_scale=(
                inferred.source_scale
                if scale_policy == "preserve_source"
                else None
            ),
            target_volume=target_volume,
            include_selective_dynamics=getattr(
                self,
                "poscar_include_selective_dynamics",
                inferred.include_selective_dynamics,
            ),
            velocity_mode=getattr(
                self,
                "poscar_velocity_mode",
                inferred.velocity_mode,
            ),
        )

    def _selection_and_preview(self, context, *, default_format=False):
        session = get_scene_session(context.scene)
        selection = resolve_export_selection(
            session.project,
            session.active_entity_id,
        )
        if default_format:
            self._suppress_preview_update = True
            try:
                if selection.grid is not None:
                    self.format_name = "cube"
                elif (
                    selection.conformer_set is not None
                    or selection.record is not None
                ):
                    self.format_name = "sdf"
                elif selection.frame_set is not None:
                    self.format_name = "extxyz"
                elif selection.structure.periodic is not None:
                    self.format_name = (
                        "poscar"
                        if any(
                            value.producer == "ChemBlender POSCAR adapter"
                            for value in selection.provenance
                        )
                        else "cif"
                    )
                if self.format_name == "cif":
                    self.cif_mode = (
                        "preserve"
                        if selection.cif_envelope is not None
                        else "normalized"
                    )
                elif self.format_name == "poscar":
                    settings, _selective, _velocities, _lattice = _poscar_parts(
                        selection
                    )
                    self.poscar_coordinate_mode = settings.coordinate_mode
                    self.poscar_scale_policy = settings.scale_policy
                    self.poscar_comment = settings.comment
                    import numpy

                    self.poscar_target_volume = abs(
                        float(numpy.linalg.det(selection.structure.cell.values))
                    )
                    self.poscar_include_selective_dynamics = (
                        settings.include_selective_dynamics
                    )
                    self.poscar_velocity_mode = settings.velocity_mode
            finally:
                self._suppress_preview_update = False
        cube_requires_dataset_index = (
            selection.grid is not None
            and selection.grid.data.dims == ("dataset", "x", "y", "z")
        )
        self._cube_requires_dataset_index = cube_requires_dataset_index
        if (
            self.format_name == "cube"
            and cube_requires_dataset_index
            and getattr(self, "cube_dataset_index", -1) == -1
            and default_format
        ):
            self.loss_preview = "Select Dataset Index"
            self._preview_report = None
            return selection, None
        keywords = {}
        if self.format_name == "cif":
            keywords = {
                "cif_mode": getattr(self, "cif_mode", "normalized"),
                "destination": getattr(self, "filepath", None) or None,
            }
        elif self.format_name == "poscar":
            keywords = {
                "poscar_settings": self._poscar_settings(selection),
                "destination": getattr(self, "filepath", None) or None,
            }
        elif self.format_name == "cube":
            keywords = {
                "dataset_index": (
                    None
                    if not cube_requires_dataset_index
                    or getattr(self, "cube_dataset_index", -1) == -1
                    else getattr(self, "cube_dataset_index", -1)
                ),
            }
        report = preview_export_selection(
            selection,
            self.format_name,
            self.missing_value_token,
            **keywords,
        )
        self.loss_preview = _report_text(report)
        self._preview_report = report
        return selection, report

    def invoke(self, context, _event):
        try:
            self._selection_and_preview(context, default_format=True)
        except (TypeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "format_name")
        if self.format_name == "cif":
            layout.prop(self, "cif_mode")
        elif (
            self.format_name == "cube"
            and getattr(self, "_cube_requires_dataset_index", False)
        ):
            layout.prop(self, "cube_dataset_index")
        elif self.format_name == "poscar":
            layout.prop(self, "poscar_comment")
            layout.prop(self, "poscar_coordinate_mode")
            layout.prop(self, "poscar_scale_policy")
            if self.poscar_scale_policy == "target_volume":
                layout.prop(self, "poscar_target_volume")
            layout.prop(self, "poscar_include_selective_dynamics")
            layout.prop(self, "poscar_velocity_mode")
        report = getattr(self, "_preview_report", None)
        if report is None:
            layout.label(text=self.loss_preview or "No data loss")
        else:
            for entry in report.entries:
                layout.label(text=entry.message)
        layout.prop(self, "confirm_loss")
        if self.format_name == "extxyz":
            layout.prop(self, "missing_value_token")

    def _clear_job_ownership(self, job):
        if getattr(self, "_job", None) is job:
            self._job = None
            self._timer = None

    def _cancel_and_release_job(self, job):
        failure = None
        job.cancel()
        try:
            if not job.join(None):
                raise RuntimeError("export worker did not stop")
        except BaseException as error:
            failure = error
        try:
            job.release_ui()
        except BaseException as error:
            failure = _merge_cleanup_failure(
                failure,
                error,
                "export UI cleanup failed",
            )
        self._clear_job_ownership(job)
        if failure is not None:
            job.abandon_ui()
            raise failure

    def execute(self, context):
        try:
            selection, preview = self._selection_and_preview(context)
            if preview.requires_confirmation and not self.confirm_loss:
                raise ValueError(
                    "Loss/Partial/Ambiguous export requires explicit "
                    "confirmation"
                )
            destination = Path(self.filepath)
            if not destination.name:
                raise ValueError("choose an export destination")
            job = ExportJob(
                destination,
                selection,
                format_name=self.format_name,
                confirm_loss=self.confirm_loss,
                missing_value_token=self.missing_value_token or None,
                dataset_index=(
                    getattr(self, "cube_dataset_index", -1)
                    if self.format_name == "cube"
                    and getattr(self, "_cube_requires_dataset_index", False)
                    else None
                ),
                cif_mode=(
                    getattr(self, "cif_mode", None)
                    if self.format_name == "cif"
                    else None
                ),
                poscar_settings=(
                    self._poscar_settings(selection)
                    if self.format_name == "poscar"
                    else None
                ),
            )
            if getattr(bpy.app, "background", False):
                job.start()
                job.join(None)
                return self._finish_job(job)
            manager = context.window_manager
            self._job = job
            self._timer = None
            timer = manager.event_timer_add(0.1, window=context.window)
            self._timer = timer
            job.attach_ui(manager, timer)
            manager.progress_begin(0, 100)
            job.mark_progress_started()
            manager.progress_update(10)
            manager.modal_handler_add(self)
            job.start()
            return {"RUNNING_MODAL"}
        except BaseException as error:
            if "job" in locals() and getattr(self, "_job", None) is job:
                try:
                    self._cancel_and_release_job(job)
                except BaseException as cleanup_error:
                    if isinstance(cleanup_error, _FATAL_EXCEPTIONS):
                        raise
                    error.add_note(
                        f"export setup cleanup failed: {cleanup_error}"
                    )
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

    def _finish_job(self, job):
        if job.error is not None:
            if isinstance(job.error, _FATAL_EXCEPTIONS):
                raise job.error
            self.report({"ERROR"}, str(job.error))
            return {"CANCELLED"}
        if not job.result.written:
            self.report({"ERROR"}, _report_text(job.result))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {job.result.frame_count} frame(s)")
        return {"FINISHED"}

    def modal(self, context, event):
        job = getattr(self, "_job", None)
        if job is None:
            return {"CANCELLED"}
        if event.type == "ESC":
            job.cancel()
        if event.type != "TIMER" or not job.done:
            return {"RUNNING_MODAL"}
        if not getattr(job, "_completion_checked", False):
            failure = None
            try:
                job.join(0)
            except BaseException as error:
                failure = error
            if failure is None:
                try:
                    context.window_manager.progress_update(100)
                except BaseException as error:
                    failure = error
            job._completion_error = failure
            job._completion_checked = True
        failure = job._completion_error
        try:
            job.release_ui()
        except BaseException as error:
            if (
                not isinstance(error, _FATAL_EXCEPTIONS)
                and job.timer_pending
            ):
                self.report(
                    {"WARNING"},
                    f"Export cleanup retry pending: {error}",
                )
                return {"RUNNING_MODAL"}
            job.abandon_ui()
            failure = _merge_cleanup_failure(
                failure,
                error,
                "export UI cleanup failed",
            )
        self._clear_job_ownership(job)
        if failure is not None:
            if isinstance(failure, _FATAL_EXCEPTIONS):
                raise failure
            self.report({"ERROR"}, str(failure))
            return {"CANCELLED"}
        return self._finish_job(job)

    def cancel(self, _context):
        job = getattr(self, "_job", None)
        if job is not None:
            try:
                self._cancel_and_release_job(job)
            except BaseException as error:
                if isinstance(error, _FATAL_EXCEPTIONS):
                    raise
                self.report({"ERROR"}, f"Export cleanup failed: {error}")


__all__ = ("CHEMBLENDER_OT_export_project_entity",)
