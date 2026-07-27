"""Private RDKit-to-core model conversion shared by molecular readers."""

from dataclasses import dataclass
import hashlib
from uuid import UUID, uuid5

import numpy

from ..model import (
    ArrayData,
    AtomicIdentityData,
    CategoricalData,
    DiagnosticSeverity,
    ImportDiagnostic,
    MolecularRecord,
    ProvenanceRecord,
    QualityStatus,
    Structure,
    TopologyRecord,
    TopologySource,
)


ADAPTER_VERSION = "1"


@dataclass(frozen=True, slots=True)
class RDKitMoleculeContext:
    source_revision_id: UUID
    source_hash: str
    record_key: str
    source_record_index: int
    title: str
    block_version: str | None

    def __post_init__(self):
        if type(self.source_revision_id) is not UUID:
            raise TypeError("source_revision_id must be a UUID")
        if (
            not isinstance(self.source_hash, str)
            or len(self.source_hash) != 64
            or any(character not in "0123456789abcdef" for character in self.source_hash)
        ):
            raise ValueError("source_hash must be SHA-256 hex")
        if not isinstance(self.record_key, str) or not self.record_key:
            raise ValueError("record_key must be non-empty")
        if type(self.source_record_index) is not int or self.source_record_index < 0:
            raise ValueError("source_record_index must be non-negative")
        if not isinstance(self.title, str):
            raise TypeError("title must be a string")
        if self.block_version not in (None, "V2000", "V3000"):
            raise ValueError("block_version must be V2000, V3000 or None")


@dataclass(frozen=True, slots=True)
class RDKitMoleculeAdaptation:
    raw_block: bytes
    structure: Structure | None
    topologies: tuple[TopologyRecord, ...]
    molecular_record: MolecularRecord | None
    provenance: ProvenanceRecord
    diagnostics: tuple[ImportDiagnostic, ...]


def _identity(context, raw_block, kind):
    raw_hash = hashlib.sha256(raw_block).hexdigest()
    return uuid5(
        context.source_revision_id,
        f"rdkit-adapter:{ADAPTER_VERSION}:{context.source_hash}:{raw_hash}:"
        f"{context.record_key}:{context.source_record_index}:{kind}",
    )


def _categorical(values):
    categories = tuple(dict.fromkeys(value for value in values if value is not None))
    index = {value: position for position, value in enumerate(categories)}
    return CategoricalData(
        ArrayData(
            numpy.asarray([index.get(value, -1) for value in values], dtype=numpy.int64),
            ("atom",),
            "dimensionless",
        ),
        categories,
        -1,
    )


def _atom_name(atom):
    for name in ("atomName", "_TriposAtomName"):
        if atom.HasProp(name):
            return atom.GetProp(name)
    return None


def _bond_label(bond):
    label = str(bond.GetStereo())
    return {"STEREOE": "E", "STEREOZ": "Z", "STEREOCIS": "cis", "STEREOTRANS": "trans"}.get(label, "")


def _topology(mol, structure_id, topology_id, source_kind, provenance_id):
    bonds = sorted(
        (
            min(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()),
            max(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()),
            float(1.5 if bond.GetIsAromatic() else bond.GetBondTypeAsDouble()),
            bool(bond.GetIsAromatic()),
            _bond_label(bond),
        )
        for bond in mol.GetBonds()
    )
    return TopologyRecord(
        id=topology_id,
        revision=str(topology_id),
        structure_id=structure_id,
        bond_indices=ArrayData(
            numpy.asarray([item[:2] for item in bonds], dtype=numpy.int64).reshape((-1, 2)),
            ("bond", "endpoint"),
            "dimensionless",
        ),
        bond_orders=ArrayData(
            numpy.asarray([item[2] for item in bonds], dtype=numpy.float64),
            ("bond",),
            "dimensionless",
        ),
        aromatic_flags=ArrayData(
            numpy.asarray([item[3] for item in bonds], dtype=numpy.bool_),
            ("bond",),
            "dimensionless",
        ),
        stereo_labels=tuple(item[4] for item in bonds),
        source_kind=source_kind,
        quality_status=QualityStatus.COMPLETE,
        inference_parameters=(),
        provenance_ids=(provenance_id,),
    )


def _topology_signature(topology):
    return (
        tuple(map(tuple, topology.bond_indices.values.tolist())),
        tuple(topology.bond_orders.values.tolist()),
        tuple(topology.aromatic_flags.values.tolist()),
        topology.stereo_labels,
    )


def _diagnostic(context, raw_block, code, quality_status, message):
    return ImportDiagnostic(
        id=_identity(context, raw_block, f"diagnostic:{code}"),
        severity=DiagnosticSeverity.WARNING,
        quality_status=quality_status,
        source_revision_id=context.source_revision_id,
        record_key=context.record_key,
        entity_id=None,
        field_path="molecule",
        code=code,
        message=message,
        original_value=None,
        normalized_value=None,
        recovery_action=None,
        scientific_consequence=message,
        suggested_action=None,
    )


def adapt_rdkit_molecule(mol, raw_block, context):
    """Convert one temporary RDKit ``Mol`` without retaining it in the result."""
    if not isinstance(raw_block, bytes):
        raise TypeError("raw_block must be bytes")
    if not isinstance(context, RDKitMoleculeContext):
        raise TypeError("context must be RDKitMoleculeContext")

    from rdkit import Chem

    provenance_id = _identity(context, raw_block, "provenance")
    structure_id = _identity(context, raw_block, "structure")
    explicit = _topology(
        mol,
        structure_id,
        _identity(context, raw_block, "topology:explicit"),
        TopologySource.EXPLICIT_FILE,
        provenance_id,
    )
    topologies = [explicit]
    diagnostics = []
    sanitized = Chem.Mol(mol)
    if int(Chem.SanitizeMol(sanitized, catchErrors=True)):
        diagnostics.append(
            _diagnostic(
                context,
                raw_block,
                "mol.sanitize_failed",
                QualityStatus.PARTIAL,
                "RDKit sanitization failed; explicit-file topology was retained.",
            )
        )
    else:
        interpreted = _topology(
            sanitized,
            structure_id,
            _identity(context, raw_block, "topology:sanitized"),
            TopologySource.RDKIT_SANITIZED,
            provenance_id,
        )
        if _topology_signature(interpreted) != _topology_signature(explicit):
            topologies.append(interpreted)

    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=hashlib.sha256(raw_block).hexdigest(),
        producer="ChemBlender RDKit molecule adapter",
        producer_version=ADAPTER_VERSION,
        source="",
        source_hash=context.source_hash,
        parent_ids=(),
        operation="adapt",
        parameters=(("record_key", context.record_key), ("rdkit_sanitized", not diagnostics)),
    )
    if not mol.GetNumConformers():
        diagnostics.append(
            _diagnostic(
                context,
                raw_block,
                "mol.coordinates_missing",
                QualityStatus.INCOMPLETE,
                "The source molecule has no conformer; no coordinates were invented.",
            )
        )
        return RDKitMoleculeAdaptation(
            raw_block, None, tuple(topologies), None, provenance, tuple(diagnostics)
        )

    conformer = mol.GetConformer()
    coordinates = numpy.asarray(
        [tuple(conformer.GetAtomPosition(index)) for index in range(mol.GetNumAtoms())],
        dtype=numpy.float64,
    )
    identity = AtomicIdentityData(
        isotopes=ArrayData(numpy.asarray([atom.GetIsotope() for atom in mol.GetAtoms()], dtype=numpy.int64), ("atom",), "dimensionless"),
        formal_charges=ArrayData(numpy.asarray([atom.GetFormalCharge() for atom in mol.GetAtoms()], dtype=numpy.int64), ("atom",), "dimensionless"),
        atom_map_numbers=ArrayData(numpy.asarray([atom.GetAtomMapNum() for atom in mol.GetAtoms()], dtype=numpy.int64), ("atom",), "dimensionless"),
        atom_names=_categorical([_atom_name(atom) for atom in mol.GetAtoms()]),
        stereo_labels=_categorical([str(atom.GetChiralTag()) if str(atom.GetChiralTag()) != "CHI_UNSPECIFIED" else None for atom in mol.GetAtoms()]),
    )
    if not conformer.Is3D():
        diagnostics.append(
            _diagnostic(
                context,
                raw_block,
                "mol.coordinates_2d",
                QualityStatus.COMPLETE,
                "The source conformer is planar 2D coordinates.",
            )
        )
    structure = Structure(
        id=structure_id,
        revision=hashlib.sha256(raw_block).hexdigest(),
        atomic_numbers=tuple(atom.GetAtomicNum() for atom in mol.GetAtoms()),
        coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"),
        topology_ids=tuple(topology.id for topology in topologies),
        atomic_identity=identity,
    )
    record = MolecularRecord(
        id=_identity(context, raw_block, "record"),
        revision=hashlib.sha256(raw_block).hexdigest(),
        source_revision_id=context.source_revision_id,
        record_key=context.record_key,
        structure_id=structure.id,
        topology_id=explicit.id,
        raw_block=raw_block,
        title=context.title,
        source_record_index=context.source_record_index,
        block_version=context.block_version,
        writer_name=None,
        writer_version=None,
        ordered_raw_properties=(),
        provenance_ids=(provenance.id,),
    )
    return RDKitMoleculeAdaptation(
        raw_block, structure, tuple(topologies), record, provenance, tuple(diagnostics)
    )
