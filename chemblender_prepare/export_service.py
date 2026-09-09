"""Native export selection and loss reporting, extracted from the Blender panel."""
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from cbq_core.model import AtomicProperty
from cbq_core.model import CIFEnvelope
from cbq_core.model import ConformerSet
from cbq_core.model import DatasetStatus
from cbq_core.model import FrameSet
from cbq_core.model import Grid3D
from cbq_core.model import MolecularRecord
from cbq_core.model import Structure
from cbq_core.model import TopologyRecord
from chemblender_prepare.core.exporters import ExportReport
from chemblender_prepare.core.exporters import ExportReportEntry
from chemblender_prepare.core.exporters import PoscarExportSettings
from chemblender_prepare.core.exporters import export_extxyz
from chemblender_prepare.core.exporters import export_cif
from chemblender_prepare.core.exporters import export_cube
from chemblender_prepare.core.exporters import export_xyz
from chemblender_prepare.core.exporters import export_mol
from chemblender_prepare.core.exporters import export_mol2
from chemblender_prepare.core.exporters import export_pdb
from chemblender_prepare.core.exporters import export_pqr
from chemblender_prepare.core.exporters import export_poscar
from chemblender_prepare.core.exporters import export_sdf
from chemblender_prepare.core.exporters import export_smiles
from chemblender_prepare.core.exporters import preview_extxyz_export
from chemblender_prepare.core.exporters import preview_cube_export
from chemblender_prepare.core.exporters import preview_molecular_export
from chemblender_prepare.core.exporters import preview_mol2_export
from chemblender_prepare.core.exporters import preview_pdb_export
from chemblender_prepare.core.exporters import preview_pqr_export
from chemblender_prepare.core.exporters import plan_cif_export
from chemblender_prepare.core.exporters import sdf_entries_from_conformer_set
from chemblender_prepare.core.formats.poscar import PoscarLatticeVelocityBlock

_CIF_ACTION_LABELS = {
    "preserve": "Preserved", "replace": "Changed", "add": "Added", "omit": "Omitted",
}


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
        structure = selection.structure
        omissions = (
            (structure.cell is not None or structure.periodic is not None,
             "cell_pbc", "unit cell, periodic sites and PBC"),
            (structure.molecular_charge is not None
             or structure.molecular_multiplicity is not None,
             "charge_spin", "molecular charge and multiplicity"),
            (structure.topology is not None or structure.topology_ids
             or selection.topology is not None or selection.associated_topologies,
             "topology", "bonds and topology"),
            (structure.atomic_identity is not None,
             "atomic_identity", "formal charges, isotopes and atom identities"),
            (selection.properties, "datasets", "associated scientific datasets"),
            (selection.biological_hierarchies, "hierarchy", "biological hierarchy"),
            (selection.record is not None or selection.conformer_set is not None
             or selection.annotations or selection.cif_envelope is not None,
             "metadata", "record, annotation and source-envelope metadata"),
        )
        entries = tuple(
            ExportReportEntry(f"omit:{code}", f"Omitted: {message}")
            for present, code, message in omissions if present
        )
        return ExportReport("xyz", False, 1, bool(entries), entries)
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


def export_selection(destination, selection, *, format_name, confirm_loss=False,
                     missing_value_token=None, dataset_index=None, cif_mode=None,
                     poscar_settings=None, is_cancelled=lambda: False):
    """Use the existing format dispatch and loss policy outside Blender."""
    destination = Path(destination)
    if format_name in {'xyz', 'cif', 'poscar'}:
        preview = preview_export_selection(selection, format_name, cif_mode=cif_mode, poscar_settings=poscar_settings, destination=destination)
        if preview.requires_confirmation and (not confirm_loss):
            raise ValueError('Loss/Partial/Ambiguous export requires explicit confirmation')
    if format_name == 'xyz':
        report = export_xyz(destination, selection.structure, is_cancelled=is_cancelled)
    elif format_name == 'extxyz':
        report = export_extxyz(destination, selection.structure, frame_set=selection.frame_set, properties=_extxyz_properties(selection), confirm_loss=confirm_loss, missing_value_token=missing_value_token or None, is_cancelled=is_cancelled)
    elif format_name == 'cube':
        report = export_cube(_cube_entities(selection), dataset_index=dataset_index, confirm_loss=confirm_loss, destination=destination, is_cancelled=is_cancelled).report
    elif format_name == 'mol':
        report = export_mol(selection.structure, selection.topology, record=selection.record, confirm_loss=confirm_loss, destination=destination, is_cancelled=is_cancelled).report
    elif format_name == 'mol2':
        report = export_mol2(_mol2_entities(selection), confirm_loss=confirm_loss, destination=destination, is_cancelled=is_cancelled).report
    elif format_name == 'pdb':
        report = export_pdb(_pdb_entities(selection), confirm_loss=confirm_loss, destination=destination, is_cancelled=is_cancelled).report
    elif format_name == 'pqr':
        report = export_pqr(_pdb_entities(selection), confirm_loss=confirm_loss, destination=destination, is_cancelled=is_cancelled).report
    elif format_name == 'sdf':
        if selection.conformer_set is not None:
            entries = sdf_entries_from_conformer_set(selection.conformer_set, selection.structure, selection.topology, selection.records_by_id or {})
            report = export_sdf(entries=entries, confirm_loss=confirm_loss, destination=destination, is_cancelled=is_cancelled).report
        else:
            report = export_sdf(selection.structure, selection.topology, record=selection.record, confirm_loss=confirm_loss, destination=destination, is_cancelled=is_cancelled).report
    elif format_name == 'smiles':
        report = export_smiles(selection.structure, selection.topology, record=selection.record, confirm_loss=confirm_loss, destination=destination, is_cancelled=is_cancelled).report
    elif format_name == 'cif':
        mode = cif_mode or ('preserve' if selection.cif_envelope is not None else 'normalized')
        report = export_cif(destination, selection.structure, envelope=selection.cif_envelope, mode=mode, is_cancelled=is_cancelled)
    elif format_name == 'poscar':
        settings, selective, velocities, lattice = _poscar_parts(selection, poscar_settings)
        report = export_poscar(destination, selection.structure, settings, selective_dynamics=selective, velocities=velocities, lattice_velocities=lattice, is_cancelled=is_cancelled)
    else:
        raise ValueError('format_name must be xyz, extxyz, cube, mol, mol2, pdb, pqr, sdf, smiles, cif or poscar')
    return report
