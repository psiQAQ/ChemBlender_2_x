"""SMILES reader with byte-preserving file and inline-text entry points."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ..model import (
    DiagnosticSeverity,
    ImportBatch,
    ImportDiagnostic,
    ParserReport,
    QualityStatus,
)
from ..readers import CapabilitySupport, ReaderDescriptor, SniffMatch, SniffResult


_CAPABILITIES = {
    "atomic_identity": CapabilitySupport.SUPPORTED,
    "molecular_record": CapabilitySupport.SUPPORTED,
    "structure": CapabilitySupport.SUPPORTED,
    "topology": CapabilitySupport.SUPPORTED,
}
_READER_ID = "smiles"
_READER_VERSION = "1"


def _source_line(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("SMILES source must be valid UTF-8") from error
    lines = text.splitlines()
    if len(lines) != 1 or not lines[0].strip():
        raise ValueError("SMILES source must contain exactly one non-empty line")
    fields = lines[0].strip().split(maxsplit=1)
    return fields[0], "" if len(fields) == 1 else fields[1]


def _identity(source_hash, kind):
    return uuid5(NAMESPACE_URL, f"chemblender:smiles:{source_hash}:{kind}")


def _diagnostic(source_revision_id, code, message):
    return ImportDiagnostic(
        id=uuid5(source_revision_id, f"smiles:{code}"),
        severity=DiagnosticSeverity.ERROR,
        quality_status=QualityStatus.INVALID,
        source_revision_id=source_revision_id,
        record_key="0",
        entity_id=None,
        field_path="smiles",
        code=code,
        message=message,
        original_value=None,
        normalized_value=None,
        recovery_action=None,
        scientific_consequence=message,
        suggested_action=None,
    )


def _check_cancelled(is_cancelled):
    if is_cancelled is None:
        return
    cancelled = is_cancelled()
    if type(cancelled) is not bool:
        raise TypeError("is_cancelled must return bool")
    if cancelled:
        from .rdkit_common import RDKitMoleculeCancelled
        raise RDKitMoleculeCancelled()


def _report(adaptation):
    created = [adaptation.provenance.id]
    capabilities = []
    if adaptation.structure is not None:
        created.insert(0, adaptation.structure.id)
        created[1:1] = [item.id for item in adaptation.topologies]
        capabilities.extend(("structure", "atomic_identity", "topology"))
    if adaptation.molecular_record is not None:
        created.insert(-1, adaptation.molecular_record.id)
        capabilities.append("molecular_record")
    return ParserReport(
        reader_id=_READER_ID,
        reader_version=_READER_VERSION,
        created_entity_ids=tuple(created),
        parsed_capabilities=tuple(capabilities),
        issues=(),
    )


def _generated_2d_diagnostic(source_revision_id):
    return ImportDiagnostic(
        id=uuid5(source_revision_id, "smiles:generated-planar-2d"),
        severity=DiagnosticSeverity.WARNING,
        quality_status=QualityStatus.COMPLETE,
        source_revision_id=source_revision_id,
        record_key="0",
        entity_id=None,
        field_path="coordinates",
        code="smiles.planar_2d_generated",
        message="RDKit generated planar 2D coordinates from the SMILES graph; they are not source conformer coordinates.",
        original_value=None,
        normalized_value=None,
        recovery_action=None,
        scientific_consequence="Coordinates encode a deterministic 2D depiction, not an observed or optimized conformer.",
        suggested_action="Run the SMILES 3D derivation when a deterministic conformer is required.",
    )


def _parse_bytes(raw, *, source_revision_id, validation_mode, is_cancelled=None):
    if not isinstance(raw, bytes):
        raise TypeError("raw must be bytes")
    source_hash = hashlib.sha256(raw).hexdigest()
    _check_cancelled(is_cancelled)
    try:
        smiles, title = _source_line(raw)
    except ValueError as error:
        batch = ImportBatch(diagnostics=(_diagnostic(source_revision_id, "smiles.invalid", str(error)),))
        return batch
    _check_cancelled(is_cancelled)
    from rdkit import Chem, rdBase

    molecule = Chem.MolFromSmiles(smiles)
    _check_cancelled(is_cancelled)
    if molecule is None:
        batch = ImportBatch(
            diagnostics=(_diagnostic(source_revision_id, "smiles.invalid", "RDKit could not parse the SMILES source."),)
        )
        return batch
    if (
        any(atom.GetAtomicNum() == 0 or atom.GetNumRadicalElectrons() for atom in molecule.GetAtoms())
        or any(str(bond.GetBondType()) == "UNSPECIFIED" for bond in molecule.GetBonds())
    ):
        batch = ImportBatch(
            diagnostics=(_diagnostic(source_revision_id, "smiles.unsupported_chemistry", "SMILES radicals, dummy atoms, and unspecified bonds are unsupported."),)
        )
        return batch
    from rdkit.Chem import rdDepictor
    from .rdkit_common import RDKitMoleculeContext, adapt_rdkit_molecule

    rdDepictor.Compute2DCoords(molecule)
    _check_cancelled(is_cancelled)
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=False)
    isomeric = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    _check_cancelled(is_cancelled)
    entity_revision = hashlib.sha256(
        json.dumps(
            {
                "canonical": canonical,
                "charge": Chem.GetFormalCharge(molecule),
                "coordinates": molecule.GetConformer().GetPositions().tolist(),
                "isomeric": isomeric,
                "rdkit_version": rdBase.rdkitVersion,
                "source_hash": source_hash,
                "source_revision_id": str(source_revision_id),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    adaptation = adapt_rdkit_molecule(
        molecule,
        raw,
        RDKitMoleculeContext(
            source_revision_id=source_revision_id,
            source_hash=source_hash,
            record_key="0",
            source_record_index=0,
            title=title,
            block_version=None,
            writer_name="SMILES",
            validation_mode=validation_mode,
        ),
        is_cancelled=is_cancelled,
    )
    structure_id = _identity(entity_revision, "structure")
    topology_id = _identity(entity_revision, "topology")
    record_id = _identity(entity_revision, "molecular-record")
    provenance_id = _identity(entity_revision, "provenance")
    provenance = replace(
        adaptation.provenance,
        id=provenance_id,
        revision=entity_revision,
        source_hash=source_hash,
        parameters=tuple(sorted((*adaptation.provenance.parameters, (
            "canonical_smiles", canonical,
        ), ("coordinate_mode", "generated_planar_2d"), ("isomeric_smiles", isomeric), ("rdkit_version", rdBase.rdkitVersion)))),
        parent_ids=(record_id, structure_id, topology_id),
    )
    topology = replace(
        adaptation.topologies[0], id=topology_id, revision=entity_revision,
        structure_id=structure_id, provenance_ids=(provenance_id,),
    )
    record = replace(
        adaptation.molecular_record, id=record_id, revision=entity_revision,
        structure_id=structure_id, topology_id=topology_id, provenance_ids=(provenance_id,),
    )
    structure = replace(
        adaptation.structure, id=structure_id, revision=entity_revision,
        molecular_charge=Chem.GetFormalCharge(molecule), topology_ids=(topology_id,),
    )
    diagnostics = tuple(item for item in adaptation.diagnostics if item.code != "mol.coordinates_2d")
    diagnostics += (_generated_2d_diagnostic(source_revision_id),)
    batch = ImportBatch(
        structures=(structure,),
        topologies=(topology,),
        molecular_records=(record,),
        provenance=(provenance,),
        diagnostics=diagnostics,
        report=ParserReport(
            reader_id=_READER_ID, reader_version=_READER_VERSION,
            created_entity_ids=(structure_id, topology_id, record_id, provenance_id),
            parsed_capabilities=("structure", "atomic_identity", "topology", "molecular_record"), issues=(),
        ),
    )
    return batch


def parse_smiles_text(text):
    if type(text) is not str:
        raise TypeError("text must be a string")
    raw = text.encode("utf-8")
    source_hash = hashlib.sha256(raw).hexdigest()
    source_revision_id = _identity(source_hash, "revision")
    return _parse_bytes(
        raw,
        source_revision_id=source_revision_id,
        validation_mode="balanced",
    )


def parse_smiles(source):
    raw = Path(source).read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    return _parse_bytes(
        raw,
        source_revision_id=_identity(source_hash, "revision"),
        validation_mode="balanced",
    )


def parse_smiles_request(request):
    raw = Path(request.source_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != request.source_content_hash:
        raise ValueError("SMILES source content hash does not match ParseRequest")
    return _parse_bytes(
        raw,
        source_revision_id=request.source_revision_id,
        validation_mode=request.validation_mode,
        is_cancelled=request.is_cancelled,
    )


def sniff_smiles(source, prefix):
    source = Path(source)
    try:
        _smiles, _title = _source_line(prefix)
    except ValueError as error:
        return SniffResult(SniffMatch.NONE, str(error))
    if source.suffix.lower() not in SMILES_READER.extensions:
        return SniffResult(SniffMatch.NONE, "SMILES suffix is required")
    return SniffResult(
        SniffMatch.PROBABLE,
        "single-line UTF-8 text with a SMILES suffix",
    )


SMILES_READER = ReaderDescriptor(
    reader_id=_READER_ID,
    reader_version=_READER_VERSION,
    extensions=(".smi", ".smiles"),
    capabilities=_CAPABILITIES,
    priority=100,
    sniff=sniff_smiles,
    parse=parse_smiles,
    parse_request=parse_smiles_request,
)


__all__ = ("SMILES_READER", "parse_smiles", "parse_smiles_request", "parse_smiles_text", "sniff_smiles")
