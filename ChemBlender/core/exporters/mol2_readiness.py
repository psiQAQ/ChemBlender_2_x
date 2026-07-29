"""MOL2 P1 export representability checks; this module does not write files."""

from dataclasses import dataclass
from enum import Enum

from ..model import AtomicProperty, CategoricalData, DatasetStatus, QualityStatus


class Mol2ExportStatus(str, Enum):
    COMPLETE = "Complete"
    PARTIAL = "Partial"
    UNSUPPORTED = "Unsupported"


@dataclass(frozen=True, slots=True)
class Mol2ExportReadiness:
    status: Mol2ExportStatus
    missing_fields: tuple[str, ...]


def _entities(project_entities, name):
    values = getattr(project_entities, name)
    return tuple(values.values() if isinstance(values, dict) else values)


def _complete_categorical(property_value):
    if (
        not isinstance(property_value, AtomicProperty)
        or property_value.status is not DatasetStatus.COMPLETE
        or not isinstance(property_value.data, CategoricalData)
    ):
        return False
    return all(
        int(code) != property_value.data.missing_code
        for code in property_value.data.codes.values
    )


def _complete_property(property_value):
    return (
        isinstance(property_value, AtomicProperty)
        and property_value.status is DatasetStatus.COMPLETE
    )


def _bond_types_are_mappable(topology):
    if any(label not in ("", "amide") for label in topology.stereo_labels):
        return False
    if topology.aromatic_flags is not None:
        return True
    return all(float(order) in (1.0, 2.0, 3.0) for order in topology.bond_orders.values)


def mol2_export_readiness(project_entities):
    """Return the project-wide P1 MOL2 export boundary without serializing it."""
    structures = _entities(project_entities, "structures")
    topologies = _entities(project_entities, "topologies")
    records = _entities(project_entities, "molecular_records")
    annotations = _entities(project_entities, "annotations")
    datasets = _entities(project_entities, "datasets")
    missing = set()

    if not structures:
        missing.add("structure")
    for structure in structures:
        identity = structure.atomic_identity
        if identity is None or any(
            int(code) == identity.atom_names.missing_code
            for code in identity.atom_names.codes.values
        ):
            missing.add("structure.atomic_identity.atom_names")
        topology = next(
            (
                value
                for value in topologies
                if value.structure_id == structure.id
                and value.quality_status is QualityStatus.COMPLETE
            ),
            None,
        )
        if topology is None:
            missing.add("topology")
        elif not _bond_types_are_mappable(topology):
            missing.add("topology.bond_type_mapping")

        properties = {
            value.semantic_role: value
            for value in datasets
            if isinstance(value, AtomicProperty) and value.structure_id == structure.id
        }
        if not _complete_categorical(properties.get("atom_type")):
            missing.add("dataset.atom_type")
        if not _complete_property(properties.get("substructure_id")):
            missing.add("dataset.substructure_id")
        if not _complete_categorical(properties.get("substructure_name")):
            missing.add("dataset.substructure_name")

        tripos_annotations = {
            value.key: value.value
            for value in annotations
            if value.target_entity_id == structure.id and value.namespace == "tripos"
        }
        for key in ("charge_type", "molecule_type"):
            if not isinstance(tripos_annotations.get(key), str):
                missing.add(f"annotation.{key}")
        if tripos_annotations.get("charge_type") != "NO_CHARGES" and not _complete_property(
            properties.get("partial_charge")
        ):
            missing.add("dataset.partial_charge")
        if not any(
            value.structure_id == structure.id
            and (topology is None or value.topology_id == topology.id)
            and value.raw_block.startswith(b"@<TRIPOS>MOLECULE")
            for value in records
        ):
            missing.add("molecular_record.raw_tripos")

    fields = tuple(sorted(missing))
    unsupported = {
        "structure",
        "structure.atomic_identity.atom_names",
        "topology",
        "topology.bond_type_mapping",
        "dataset.atom_type",
    }
    status = (
        Mol2ExportStatus.UNSUPPORTED
        if unsupported.intersection(fields)
        else Mol2ExportStatus.PARTIAL
        if fields
        else Mol2ExportStatus.COMPLETE
    )
    return Mol2ExportReadiness(status, fields)
