"""MOL2 P1 export representability checks; this module does not write files."""

from dataclasses import dataclass
from enum import Enum

import numpy

from ..model import (
    ArrayData,
    AtomicProperty,
    CategoricalData,
    DatasetStatus,
    QualityStatus,
)


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


def _complete_numeric(property_value, kinds):
    if (
        not isinstance(property_value, AtomicProperty)
        or property_value.status is not DatasetStatus.COMPLETE
        or not isinstance(property_value.data, ArrayData)
    ):
        return False
    values = numpy.asarray(property_value.data.values)
    return (
        numpy.dtype(property_value.data.dtype).kind in kinds
        and bool(numpy.all(numpy.isfinite(values)))
    )


def _bond_types_are_mappable(topology):
    aromatic_flags = (
        (False,) * len(topology.stereo_labels)
        if topology.aromatic_flags is None
        else topology.aromatic_flags.values
    )
    return all(
        label in ("", "amide")
        and (
            bool(aromatic)
            or label == "amide"
            or float(order) in (1.0, 2.0, 3.0)
        )
        for order, aromatic, label in zip(
            topology.bond_orders.values,
            aromatic_flags,
            topology.stereo_labels,
        )
    )


def _one(values, missing_token, ambiguous_token, missing):
    values = tuple(values)
    if len(values) == 1:
        return values[0]
    missing.add(ambiguous_token if len(values) > 1 else missing_token)
    return None


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
        topology_ids = tuple(structure.topology_ids)
        if len(topology_ids) != 1:
            missing.add("topology.ambiguous" if topology_ids else "topology")
            topology = None
        else:
            topology = _one(
                (
                    value
                    for value in topologies
                    if value.id == topology_ids[0]
                    and value.structure_id == structure.id
                    and value.quality_status is QualityStatus.COMPLETE
                ),
                "topology",
                "topology.ambiguous",
                missing,
            )
        if topology is not None and not _bond_types_are_mappable(topology):
            missing.add("topology.bond_type_mapping")

        properties = lambda role: _one(
            (
                value
                for value in datasets
                if isinstance(value, AtomicProperty)
                and value.structure_id == structure.id
                and value.semantic_role == role
            ),
            f"dataset.{role}",
            f"dataset.{role}.ambiguous",
            missing,
        )
        atom_type = properties("atom_type")
        if atom_type is not None and not _complete_categorical(atom_type):
            missing.add("dataset.atom_type")
        substructure_id = properties("substructure_id")
        if substructure_id is not None and not _complete_numeric(substructure_id, "iu"):
            missing.add("dataset.substructure_id")
        substructure_name = properties("substructure_name")
        if substructure_name is not None and not _complete_categorical(substructure_name):
            missing.add("dataset.substructure_name")

        annotation = lambda key: _one(
            (
                value
                for value in annotations
                if value.target_entity_id == structure.id
                and value.namespace == "tripos"
                and value.key == key
            ),
            f"annotation.{key}",
            f"annotation.{key}.ambiguous",
            missing,
        )
        charge_type = annotation("charge_type")
        molecule_type = annotation("molecule_type")
        if charge_type is not None and not isinstance(charge_type.value, str):
            missing.add("annotation.charge_type")
        if molecule_type is not None and not isinstance(molecule_type.value, str):
            missing.add("annotation.molecule_type")
        partial_charge = properties("partial_charge")
        if charge_type is not None and charge_type.value != "NO_CHARGES" and (
            partial_charge is None or not _complete_numeric(partial_charge, "iuf")
        ):
            missing.add("dataset.partial_charge")
        _one(
            (
                value
                for value in records
                if value.structure_id == structure.id
                and value.topology_id in topology_ids
                and value.raw_block.startswith(b"@<TRIPOS>MOLECULE")
            ),
            "molecular_record.raw_tripos",
            "molecular_record.ambiguous",
            missing,
        )

    fields = tuple(sorted(missing))
    unsupported = {
        "structure",
        "structure.atomic_identity.atom_names",
        "topology",
        "topology.ambiguous",
        "topology.bond_type_mapping",
        "dataset.atom_type",
        "dataset.atom_type.ambiguous",
    }
    status = (
        Mol2ExportStatus.UNSUPPORTED
        if unsupported.intersection(fields)
        else Mol2ExportStatus.PARTIAL
        if fields
        else Mol2ExportStatus.COMPLETE
    )
    return Mol2ExportReadiness(status, fields)
