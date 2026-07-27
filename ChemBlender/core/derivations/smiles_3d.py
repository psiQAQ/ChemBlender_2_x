"""Deterministic ETKDGv3 coordinates derived from authoritative SMILES entities."""

import hashlib
import json
from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

from ..model import (
    CalculationRecord, CalculationStatus, DiagnosticSeverity, ImportBatch,
    ImportDiagnostic, MolecularRecord, ParserReport, ProvenanceRecord,
    QualityStatus, SourceRevision, Structure, TopologyRecord, TopologySource,
    source_parse_identity,
)


_VERSION = "1"
_SEED = 0xC0FFEE
_SIGNED_INT_MAX = 2_147_483_647


class Smiles3DCancelled(RuntimeError):
    pass


def _identity(revision, kind):
    return uuid5(NAMESPACE_URL, f"chemblender:smiles-3d:{_VERSION}:{revision}:{kind}")


def _check_cancelled(is_cancelled):
    if is_cancelled is None:
        return
    cancelled = is_cancelled()
    if type(cancelled) is not bool:
        raise TypeError("is_cancelled must return bool")
    if cancelled:
        raise Smiles3DCancelled("SMILES 3D derivation was cancelled")


def _parameters(*, add_hydrogens, force_field, random_seed, num_threads, max_iterations):
    if type(add_hydrogens) is not bool:
        raise TypeError("add_hydrogens must be a bool")
    if force_field not in {"MMFF94", "UFF"}:
        raise ValueError("force_field must be MMFF94 or UFF")
    if type(random_seed) is not int or not 0 <= random_seed <= _SIGNED_INT_MAX:
        raise ValueError("random_seed must be a non-negative signed 32-bit integer")
    if type(num_threads) is not int or num_threads != 1:
        raise ValueError("num_threads must be exactly 1 for deterministic embedding")
    if type(max_iterations) is not int or not 0 < max_iterations <= _SIGNED_INT_MAX:
        raise ValueError("max_iterations must be a positive signed 32-bit integer")
    return (("add_hydrogens", add_hydrogens), ("clear_conformers", True),
            ("embedding", "ETKDGv3"), ("force_field", force_field),
            ("max_iterations", max_iterations), ("num_threads", num_threads),
            ("preserve_chirality", True), ("random_seed", random_seed))


def _revision(structure, topology, record, source_revision, parameters):
    document = {"parameters": parameters, "source_record": (str(record.id), record.revision, str(record.source_revision_id)),
                "source_revision": (str(source_revision.id), source_revision.parse_identity),
                "source_structure": (str(structure.id), structure.revision),
                "source_topology": (str(topology.id), topology.revision), "version": _VERSION}
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _array_values(array):
    import numpy
    values = array.values
    unloaded = getattr(values, "loaded", None) is False
    try:
        return numpy.asarray(values).tolist()
    finally:
        if unloaded:
            values.close()


def _categorical_values(data):
    return tuple(
        None if code == data.missing_code else data.categories[code]
        for code in _array_values(data.codes)
    )


def _bond_label(bond):
    stereo = str(bond.GetStereo())
    if stereo != "STEREONONE":
        return {"STEREOE": "E", "STEREOZ": "Z", "STEREOCIS": "cis", "STEREOTRANS": "trans"}.get(
            stereo, f"stereo:{stereo.removeprefix('STEREO').lower()}"
        )
    direction = str(bond.GetBondDir())
    return "" if direction == "NONE" else f"bond_dir:{direction.lower()}"


def _molecule(structure, topology, record):
    from rdkit import Chem
    if structure.atomic_identity is None or topology.structure_id != structure.id:
        raise ValueError("SMILES 3D derivation requires bound atomic identity and topology")
    try:
        lines = record.raw_block.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("SMILES record bytes must be UTF-8") from error
    if len(lines) != 1 or not lines[0].strip():
        raise ValueError("SMILES record must contain one non-empty line")
    molecule = Chem.MolFromSmiles(lines[0].strip().split(maxsplit=1)[0])
    if molecule is None:
        raise ValueError("SMILES record cannot be reconstructed")
    identity = structure.atomic_identity
    if (tuple(atom.GetAtomicNum() for atom in molecule.GetAtoms()) != structure.atomic_numbers or
            tuple(atom.GetFormalCharge() for atom in molecule.GetAtoms()) != tuple(_array_values(identity.formal_charges)) or
            tuple(atom.GetIsotope() for atom in molecule.GetAtoms()) != tuple(_array_values(identity.isotopes)) or
            tuple(atom.GetAtomMapNum() for atom in molecule.GetAtoms()) != tuple(_array_values(identity.atom_map_numbers)) or
            tuple(None if str(atom.GetChiralTag()) == "CHI_UNSPECIFIED" else str(atom.GetChiralTag()) for atom in molecule.GetAtoms()) != _categorical_values(identity.stereo_labels)):
        raise ValueError("SMILES record and Structure atomic identity disagree")
    expected = tuple(zip(
        map(tuple, _array_values(topology.bond_indices)), _array_values(topology.bond_orders),
        _array_values(topology.aromatic_flags), topology.stereo_labels,
    ))
    actual = tuple(sorted(
        ((min(b.GetBeginAtomIdx(), b.GetEndAtomIdx()), max(b.GetBeginAtomIdx(), b.GetEndAtomIdx())),
         float(1.5 if b.GetIsAromatic() else b.GetBondTypeAsDouble()), bool(b.GetIsAromatic()),
         _bond_label(b))
        for b in molecule.GetBonds()
    ))
    if expected != actual:
        raise ValueError("SMILES record and Topology bonds disagree")
    return molecule


def _coordinates_digest(molecule):
    if not molecule.GetNumConformers():
        return None
    import numpy
    positions = numpy.asarray(molecule.GetConformer().GetPositions(), dtype="<f8")
    return hashlib.sha256(positions.tobytes(order="C")).hexdigest()


def _diagnostic(source_revision_id, provenance_id, code, status, message):
    return ImportDiagnostic(id=uuid5(provenance_id, code), severity=DiagnosticSeverity.ERROR if status is QualityStatus.INVALID else DiagnosticSeverity.WARNING,
        quality_status=status, source_revision_id=source_revision_id, record_key=None, entity_id=None,
        field_path="derivation.smiles_3d", code=code, message=message, original_value=None,
        normalized_value=None, recovery_action=None, scientific_consequence=message, suggested_action=None)


def _provenance(provenance_id, revision, structure, topology, record, parameters):
    return ProvenanceRecord(id=provenance_id, revision=revision, producer="ChemBlender SMILES 3D derivation",
        producer_version=_VERSION, source="", source_hash=revision, parent_ids=(record.id, structure.id, topology.id),
        operation="derive_smiles_3d", parameters=parameters)


def _derived_source_revision(source, revision, created, diagnostics):
    parameters = (("derivation", "smiles_3d"), ("derivation_revision", revision))
    encoded = json.dumps(parameters, separators=(",", ":")).encode("utf-8")
    return SourceRevision(id=_identity(revision, "source_revision"), source_id=source.source_id, content_hash=source.content_hash,
        byte_size=source.byte_size, locator=source.locator, locator_kind=source.locator_kind, original_filename=source.original_filename,
        reader_plugin_id="chemblender.builtin", reader_id="smiles-3d", reader_version=_VERSION, reader_api_version="0.1",
        import_parameters_hash=hashlib.sha256(encoded).hexdigest(),
        parse_identity=source_parse_identity(source.content_hash, "chemblender.builtin", "smiles-3d", _VERSION, parameters),
        created_entity_ids=created, diagnostic_ids=tuple(item.id for item in diagnostics))


def _result(*, source_revision, provenance, status, source_structure, structure=(), topology=(), diagnostics=()):
    calculation = CalculationRecord(id=_identity(provenance.revision, "calculation"), revision=provenance.revision, status=status,
        input_structure_ids=(source_structure.id,), result_structure_ids=tuple(item.id for item in structure), dataset_ids=(), provenance_ids=(provenance.id,))
    created = tuple(item.id for group in (structure, topology, (calculation,), (provenance,)) for item in group)
    return ImportBatch(source_revisions=(_derived_source_revision(source_revision, provenance.revision, created, diagnostics),), structures=structure,
        topologies=topology, calculations=(calculation,), provenance=(provenance,), diagnostics=diagnostics,
        report=ParserReport(reader_id="smiles-3d", reader_version=_VERSION, created_entity_ids=created,
        parsed_capabilities=("structure", "topology") if structure else (), issues=()))


def derive_smiles_3d(structure, topology, record, source_revision, *, add_hydrogens=True, force_field="MMFF94", random_seed=_SEED, num_threads=1, max_iterations=200, is_cancelled=None):
    """Return a deterministic immutable 3D result; source entities remain untouched."""
    if not all((isinstance(structure, Structure), isinstance(topology, TopologyRecord), isinstance(record, MolecularRecord), isinstance(source_revision, SourceRevision))):
        raise TypeError("structure, topology, record, and source_revision must have their declared model types")
    if record.structure_id != structure.id or record.topology_id != topology.id or source_revision.id != record.source_revision_id:
        raise ValueError("record and source revision must bind the source entities")
    _check_cancelled(is_cancelled)
    parameters = _parameters(add_hydrogens=add_hydrogens, force_field=force_field, random_seed=random_seed, num_threads=num_threads, max_iterations=max_iterations)
    molecule = _molecule(structure, topology, record)
    _check_cancelled(is_cancelled)
    from rdkit import Chem, rdBase
    from rdkit.Chem import AllChem
    parameters = tuple(sorted((*parameters, ("heavy_atom_mapping", tuple(range(molecule.GetNumAtoms()))), ("rdkit_version", rdBase.rdkitVersion))))

    def finish(status, *, embed_code, optimize_code, diagnostic=None, molecule_result=None, outcome_exception=None):
        digest = _coordinates_digest(molecule_result) if molecule_result is not None else None
        outcome_code = "smiles_3d.success" if diagnostic is None else diagnostic[0]
        final = tuple(sorted((*parameters, ("coordinates_digest", digest), ("embed_code", embed_code), ("optimizer_code", optimize_code), ("outcome_code", outcome_code), ("outcome_exception", outcome_exception), ("status", status.value))))
        revision = _revision(structure, topology, record, source_revision, final)
        provenance_id = _identity(revision, "provenance")
        provenance = _provenance(provenance_id, revision, structure, topology, record, final)
        diagnostics = () if diagnostic is None else (_diagnostic(_identity(revision, "source_revision"), provenance_id, *diagnostic),)
        if molecule_result is None:
            return _result(source_revision=source_revision, provenance=provenance, status=status, source_structure=structure, diagnostics=diagnostics)
        from ..formats.rdkit_common import RDKitMoleculeContext, adapt_rdkit_molecule
        _check_cancelled(is_cancelled)
        adapted = adapt_rdkit_molecule(molecule_result, record.raw_block, RDKitMoleculeContext(source_revision_id=record.source_revision_id,
            source_hash=revision, record_key="0", source_record_index=0, title="SMILES 3D derivation", block_version=None, writer_name="RDKit"), is_cancelled=is_cancelled)
        _check_cancelled(is_cancelled)
        structure_id, topology_id = _identity(revision, "structure"), _identity(revision, "topology")
        derived_topology = replace(adapted.topologies[0], id=topology_id, revision=revision, structure_id=structure_id,
            source_kind=TopologySource.RDKIT_SANITIZED, provenance_ids=(provenance.id,))
        derived_structure = replace(adapted.structure, id=structure_id, revision=revision, topology_ids=(topology_id,), molecular_charge=Chem.GetFormalCharge(molecule_result))
        return _result(source_revision=source_revision, provenance=provenance, status=status, source_structure=structure,
            structure=(derived_structure,), topology=(derived_topology,), diagnostics=diagnostics)

    if len(Chem.GetMolFrags(molecule)) != 1:
        return finish(CalculationStatus.FAILED, embed_code=None, optimize_code=None,
            diagnostic=("smiles_3d.disconnected", QualityStatus.INVALID, "Disconnected molecules are not embedded as one 3D structure."))
    _check_cancelled(is_cancelled)
    if add_hydrogens:
        molecule = AllChem.AddHs(molecule)
    _check_cancelled(is_cancelled)
    molecule.RemoveAllConformers()
    embedding = AllChem.ETKDGv3(); embedding.clearConfs = True; embedding.randomSeed = random_seed; embedding.numThreads = num_threads; embedding.enforceChirality = True
    try:
        embed_code = AllChem.EmbedMolecule(molecule, embedding)
    except (ValueError, RuntimeError) as error:
        return finish(CalculationStatus.FAILED, embed_code=None, optimize_code=None,
            diagnostic=("smiles_3d.embedding_runtime_failed", QualityStatus.INVALID, f"ETKDGv3 embedding failed with {type(error).__name__}."),
            outcome_exception=type(error).__name__)
    _check_cancelled(is_cancelled)
    if embed_code < 0 or not molecule.GetNumConformers():
        code = "smiles_3d.embedding_failed" if embed_code < 0 else "smiles_3d.embedding_missing_conformer"
        return finish(CalculationStatus.FAILED, embed_code=embed_code, optimize_code=None,
            diagnostic=(code, QualityStatus.INVALID, "ETKDGv3 embedding did not produce a usable conformer; source data was unchanged."))
    try:
        available = AllChem.MMFFHasAllMoleculeParams(molecule) if force_field == "MMFF94" else AllChem.UFFHasAllMoleculeParams(molecule)
    except (ValueError, RuntimeError) as error:
        return finish(CalculationStatus.INCOMPLETE, embed_code=embed_code, optimize_code=None, molecule_result=molecule,
            diagnostic=("smiles_3d.force_field_setup_failed", QualityStatus.PARTIAL, f"Force-field parameter setup failed with {type(error).__name__}."),
            outcome_exception=type(error).__name__)
    _check_cancelled(is_cancelled)
    if not available:
        return finish(CalculationStatus.INCOMPLETE, embed_code=embed_code, optimize_code=None, molecule_result=molecule,
            diagnostic=("smiles_3d.force_field_unavailable", QualityStatus.PARTIAL, "Force-field parameters were unavailable; deterministic embedded coordinates were retained."))
    try:
        optimize_code = AllChem.MMFFOptimizeMolecule(molecule, mmffVariant=force_field, maxIters=max_iterations) if force_field == "MMFF94" else AllChem.UFFOptimizeMolecule(molecule, maxIters=max_iterations)
    except (ValueError, RuntimeError) as error:
        return finish(CalculationStatus.INCOMPLETE, embed_code=embed_code, optimize_code=None, molecule_result=molecule,
            diagnostic=("smiles_3d.optimization_setup_failed", QualityStatus.PARTIAL, f"Force-field setup failed with {type(error).__name__}."),
            outcome_exception=type(error).__name__)
    _check_cancelled(is_cancelled)
    if optimize_code == 0:
        return finish(CalculationStatus.SUCCESS, embed_code=embed_code, optimize_code=optimize_code, molecule_result=molecule)
    code = "smiles_3d.optimization_incomplete" if optimize_code == 1 else "smiles_3d.optimization_failed" if optimize_code == -1 else "smiles_3d.optimization_unexpected_status"
    return finish(CalculationStatus.INCOMPLETE, embed_code=embed_code, optimize_code=optimize_code, molecule_result=molecule,
        diagnostic=(code, QualityStatus.PARTIAL, "Force-field optimization did not converge; the latest deterministic coordinates were retained."))


__all__ = ("Smiles3DCancelled", "derive_smiles_3d")
