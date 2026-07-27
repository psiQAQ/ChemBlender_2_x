"""Native single-record MDL MOL V2000/V3000 reader backed by RDKit."""

import hashlib
from dataclasses import replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ..model import (
    DiagnosticSeverity,
    ImportBatch,
    ImportDiagnostic,
    IssueKind,
    ParserIssue,
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


def _decode_mol(raw_block):
    try:
        return raw_block.decode("utf-8-sig"), False
    except UnicodeDecodeError:
        return raw_block.decode("utf-8-sig", errors="replace"), True


def _v2000_blocks(lines, end, counts):
    try:
        atom_count = int(counts[:3])
        bond_count = int(counts[3:6])
    except ValueError as error:
        raise ValueError("MOL V2000 counts line is invalid") from error
    if atom_count <= 0 or bond_count < 0:
        raise ValueError("MOL V2000 counts are invalid")
    atom_end = 4 + atom_count
    bond_end = atom_end + bond_count
    if end < bond_end or len(lines) < bond_end:
        raise ValueError("MOL V2000 declared atom or bond block is incomplete")
    for line in lines[4:atom_end]:
        try:
            tuple(float(line[index : index + 10]) for index in (0, 10, 20))
        except ValueError as error:
            raise ValueError("MOL V2000 atom coordinates are invalid") from error
        if not line[31:34].strip().isalpha():
            raise ValueError("MOL V2000 atom symbol is invalid")
    for line in lines[atom_end:bond_end]:
        try:
            first, second, order = (int(line[index : index + 3]) for index in (0, 3, 6))
        except ValueError as error:
            raise ValueError("MOL V2000 bond line is invalid") from error
        if not 0 < first <= atom_count or not 0 < second <= atom_count or order <= 0:
            raise ValueError("MOL V2000 bond references are invalid")


def _v3000_blocks(lines, end):
    def section(name):
        begin = f"M  V30 BEGIN {name}"
        finish = f"M  V30 END {name}"
        try:
            start = next(index for index, line in enumerate(lines) if line.strip() == begin) + 1
            stop = next(index for index, line in enumerate(lines[start:], start) if line.strip() == finish)
        except StopIteration as error:
            raise ValueError(f"MOL V3000 {name.lower()} block is incomplete") from error
        if stop > end:
            raise ValueError(f"MOL V3000 {name.lower()} block is incomplete")
        return lines[start:stop]

    try:
        counts_line = next(line for line in lines if line.startswith("M  V30 COUNTS "))
        atom_count, bond_count = (int(value) for value in counts_line.split()[3:5])
    except (StopIteration, ValueError) as error:
        raise ValueError("MOL V3000 counts line is invalid") from error
    atoms = section("ATOM")
    bonds = section("BOND")
    if atom_count <= 0 or bond_count < 0 or len(atoms) != atom_count or len(bonds) != bond_count:
        raise ValueError("MOL V3000 declared atom or bond block is incomplete")
    for line in atoms:
        fields = line.split()
        try:
            int(fields[2])
            tuple(float(value) for value in fields[4:7])
        except (IndexError, ValueError) as error:
            raise ValueError("MOL V3000 atom line is invalid") from error
        if not fields[3].isalpha():
            raise ValueError("MOL V3000 atom symbol is invalid")
    for line in bonds:
        fields = line.split()
        try:
            _index, order, first, second = (int(value) for value in fields[2:6])
        except (ValueError, IndexError) as error:
            raise ValueError("MOL V3000 bond line is invalid") from error
        if order <= 0 or not 0 < first <= atom_count or not 0 < second <= atom_count:
            raise ValueError("MOL V3000 bond references are invalid")


def _mol_version(text):
    lines = text.splitlines()
    if any(line.strip() == "$$$$" for line in lines):
        raise ValueError("SDF delimiters are reserved for the future SDF reader")
    if len(lines) < 4:
        raise ValueError("MOL source is missing its counts line")
    counts = lines[3]
    if "V2000" in counts[6:]:
        version = "V2000"
    elif "V3000" in counts:
        version = "V3000"
    else:
        raise ValueError("MOL counts line is neither V2000 nor V3000")
    try:
        end = next(index for index, line in enumerate(lines) if line.strip() == "M  END")
    except StopIteration as error:
        raise ValueError("MOL source is missing M  END") from error
    if any(line.strip() for line in lines[end + 1 :]):
        raise ValueError("MOL source contains more than one record")
    if version == "V2000":
        _v2000_blocks(lines, end, counts)
    else:
        _v3000_blocks(lines, end)
    return version, lines


def sniff_mol(source, prefix):
    source = Path(source)
    if source.suffix.lower() != ".mol":
        return SniffResult(SniffMatch.NONE, "MOL reader only considers .mol files")
    text, _ = _decode_mol(prefix)
    try:
        version, _ = _mol_version(text)
    except ValueError as error:
        return SniffResult(SniffMatch.NONE, str(error))
    try:
        complete = source.stat().st_size <= len(prefix)
    except OSError:
        complete = False
    return SniffResult(
        SniffMatch.EXACT if complete else SniffMatch.PROBABLE,
        f"complete MOL {version} record" if complete else f"MOL {version} prefix",
    )


def _decode_diagnostic(context, raw_block):
    raw_hash = hashlib.sha256(raw_block).hexdigest()
    return ImportDiagnostic(
        id=uuid5(context.source_revision_id, f"mol:decode-replacement:{raw_hash}"),
        severity=DiagnosticSeverity.WARNING,
        quality_status=QualityStatus.PARTIAL,
        source_revision_id=context.source_revision_id,
        record_key=context.record_key,
        entity_id=None,
        field_path="source.encoding",
        code="mol.decode_replacement",
        message="Non-UTF-8 source bytes were replaced only for RDKit parsing.",
        original_value=None,
        normalized_value=None,
        recovery_action="raw MOL bytes were preserved unchanged",
        scientific_consequence="Non-text byte values may not be interpreted by RDKit.",
        suggested_action="Review the original MOL bytes and source encoding.",
    )


def _report(reader_id, reader_version, adaptation):
    created = []
    capabilities = []
    if adaptation.structure is not None:
        created.append(adaptation.structure.id)
        capabilities.extend(("structure", "atomic_identity"))
    if adaptation.topologies:
        created.extend(topology.id for topology in adaptation.topologies)
        capabilities.append("topology")
    if adaptation.molecular_record is not None:
        created.append(adaptation.molecular_record.id)
        capabilities.append("molecular_record")
    created.append(adaptation.provenance.id)
    return ParserReport(
        reader_id=reader_id,
        reader_version=reader_version,
        created_entity_ids=tuple(created),
        parsed_capabilities=tuple(capabilities),
        issues=(),
    )


def _parse(source, *, source_revision_id, source_hash, validation_mode, is_cancelled, reader_id, reader_version, required_version=None):
    source = Path(source)
    raw_block = source.read_bytes()
    text, replaced = _decode_mol(raw_block)
    block_version, lines = _mol_version(text)
    if required_version is not None and block_version != required_version:
        raise ValueError(f"MOL reader only accepts {required_version}")
    from .rdkit_common import RDKitMoleculeContext, adapt_rdkit_molecule

    context = RDKitMoleculeContext(
        source_revision_id=source_revision_id,
        source_hash=source_hash,
        record_key="0",
        source_record_index=0,
        title=lines[0],
        block_version=block_version,
        writer_name=lines[1] or None,
        validation_mode=validation_mode,
    )
    from rdkit import Chem

    molecule = Chem.MolFromMolBlock(
        text,
        sanitize=False,
        removeHs=False,
        strictParsing=True,
    )
    if molecule is None:
        raise ValueError("RDKit could not parse the MOL record")
    adaptation = adapt_rdkit_molecule(
        molecule,
        raw_block,
        context,
        is_cancelled=is_cancelled,
    )
    diagnostics = adaptation.diagnostics + ((_decode_diagnostic(context, raw_block),) if replaced else ())
    return ImportBatch(
        structures=(() if adaptation.structure is None else (adaptation.structure,)),
        topologies=adaptation.topologies,
        molecular_records=(
            () if adaptation.molecular_record is None else (adaptation.molecular_record,)
        ),
        provenance=(adaptation.provenance,),
        diagnostics=diagnostics,
        report=_report(reader_id, reader_version, adaptation),
    )


def parse_mol(source):
    raw_block = Path(source).read_bytes()
    source_hash = hashlib.sha256(raw_block).hexdigest()
    return _parse(
        source,
        source_revision_id=uuid5(NAMESPACE_URL, f"chemblender:mol:{source_hash}"),
        source_hash=source_hash,
        validation_mode="balanced",
        is_cancelled=None,
        reader_id="mol",
        reader_version="2",
    )


def parse_mol_request(request):
    return _parse(
        request.source_path,
        source_revision_id=request.source_revision_id,
        source_hash=request.source_content_hash,
        validation_mode=request.validation_mode,
        is_cancelled=request.is_cancelled,
        reader_id="mol",
        reader_version="2",
    )


def parse_mol_v2000(source):
    raw_block = Path(source).read_bytes()
    source_hash = hashlib.sha256(raw_block).hexdigest()
    return _deprecated_v2000_alias(_parse(
        source,
        source_revision_id=uuid5(NAMESPACE_URL, f"chemblender:mol-v2000:{source_hash}"),
        source_hash=source_hash,
        validation_mode="balanced",
        is_cancelled=None,
        reader_id="mol-v2000",
        reader_version="2",
        required_version="V2000",
    ))


def parse_mol_v2000_request(request):
    return _deprecated_v2000_alias(_parse(
        request.source_path,
        source_revision_id=request.source_revision_id,
        source_hash=request.source_content_hash,
        validation_mode=request.validation_mode,
        is_cancelled=request.is_cancelled,
        reader_id="mol-v2000",
        reader_version="2",
        required_version="V2000",
    ))


def _deprecated_v2000_alias(batch):
    return replace(
        batch,
        report=replace(
            batch.report,
            issues=(
                ParserIssue(
                    IssueKind.WARNING,
                    "reader.replacement",
                    "mol-v2000 is deprecated; use mol",
                ),
            ),
        ),
    )


MOL_READER = ReaderDescriptor(
    reader_id="mol",
    reader_version="2",
    extensions=(".mol",),
    capabilities=_CAPABILITIES,
    priority=100,
    sniff=sniff_mol,
    parse=parse_mol,
    parse_request=parse_mol_request,
)
