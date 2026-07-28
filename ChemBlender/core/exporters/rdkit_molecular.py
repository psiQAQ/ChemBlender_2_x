"""Deterministic MOL, SDF and SMILES exports from core molecular entities.

RDKit is deliberately imported only by the functions which construct or write a
molecule.  A bound raw record may supply syntax absent from the model, but the
authoritative entities still define all exported molecular semantics.
"""

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid5

from ..model import ArrayData, ConformerSet, ImportBatch, MolecularRecord, Structure, TopologyRecord
from .xyz import (
    ExportCancelled,
    ExportReport,
    ExportReportEntry,
    _cancelled,
    atomic_write_chunks,
)


@dataclass(frozen=True, slots=True)
class MolecularExport:
    text: str
    report: ExportReport


@dataclass(frozen=True, slots=True)
class SDFExportEntry:
    """One selected authoritative molecular record, in caller-selected order."""

    structure: Structure
    topology: TopologyRecord
    record: MolecularRecord | None = None
    loss_entries: tuple[ExportReportEntry, ...] = ()
    seed_record: MolecularRecord | None = None


def sdf_entries_from_conformer_set(conformer_set, reference_structure, topology, records_by_id):
    """Project already-reference-ordered conformers into ordered derived SDF entries."""
    if not isinstance(conformer_set, ConformerSet):
        raise TypeError("conformer_set must be a ConformerSet")
    if not isinstance(reference_structure, Structure) or not isinstance(topology, TopologyRecord):
        raise TypeError("reference_structure and topology must have their declared model types")
    if conformer_set.reference_structure_id != reference_structure.id or conformer_set.reference_topology_id not in {None, topology.id}:
        raise ValueError("conformer set is not bound to the selected structure and topology")
    if not isinstance(records_by_id, dict):
        raise TypeError("records_by_id must be a dict")
    reference_seed = records_by_id.get(conformer_set.record_ids[0])
    if reference_seed is not None:
        if not isinstance(reference_seed, MolecularRecord):
            raise TypeError("records_by_id values must be MolecularRecord values")
        if (
            reference_seed.id != conformer_set.record_ids[0]
            or reference_seed.record_key != conformer_set.record_keys[0]
            or reference_seed.structure_id != reference_structure.id
            or reference_seed.topology_id not in {None, topology.id}
        ):
            raise ValueError("reference seed lineage does not match the conformer reference")
    coordinates = _values(conformer_set.data)
    if coordinates.shape[1:] != (len(reference_structure.atomic_numbers), 3):
        raise ValueError("conformer coordinates do not match the reference atom count")
    entries = []
    for index, (record_id, record_key, row) in enumerate(zip(
        conformer_set.record_ids, conformer_set.record_keys, coordinates, strict=True
    )):
        source_record = records_by_id.get(record_id)
        if source_record is not None and not isinstance(source_record, MolecularRecord):
            raise TypeError("records_by_id values must be MolecularRecord values")
        if source_record is not None and (source_record.id != record_id or source_record.record_key != record_key):
            raise ValueError("records_by_id lineage does not match conformer record_ids and record_keys")
        structure_id = uuid5(reference_structure.id, f"sdf-conformer:{record_id}:{index}")
        topology_id = uuid5(topology.id, f"sdf-conformer:{record_id}:{index}")
        structure = replace(
            reference_structure, id=structure_id, revision=str(structure_id),
            coordinates=ArrayData(row, ("atom", "xyz"), conformer_set.data.unit),
            topology_ids=(topology_id,),
        )
        derived_topology = replace(topology, id=topology_id, revision=str(topology_id), structure_id=structure_id)
        title = f"derived-{record_key}"
        copied_properties = ()
        losses = ()
        if source_record is not None:
            copied_properties = source_record.ordered_raw_properties
        else:
            losses = (ExportReportEntry("conformer_properties_omitted", "no matching source record was available for derived conformer properties"),)
        record = MolecularRecord(
            uuid5(structure_id, "sdf-record"), str(structure_id),
            source_record.source_revision_id if source_record is not None else reference_structure.id,
            f"derived:{record_key}", structure_id, topology_id, b"", title, index,
            None, None, None, copied_properties, (),
        )
        entries.append(SDFExportEntry(structure, derived_topology, record, losses, reference_seed))
    return tuple(entries)


def _values(array):
    """Copy a possibly-lazy model array and promptly release its backing file."""
    import numpy

    value = array.values
    unloaded = getattr(value, "loaded", None) is False
    try:
        return numpy.asarray(value).copy()
    finally:
        if unloaded:
            value.close()


def _categories(data):
    codes = _values(data.codes)
    return tuple(
        None if int(code) == data.missing_code else data.categories[int(code)]
        for code in codes
    )


def _check_cancel(is_cancelled):
    if _cancelled(is_cancelled):
        raise ExportCancelled("export cancelled")


def _validate_inputs(structure, topology):
    import numpy

    if not isinstance(structure, Structure) or not isinstance(topology, TopologyRecord):
        raise TypeError("structure and topology must have their declared model types")
    if topology.structure_id != structure.id:
        raise ValueError("topology is not bound to the structure")
    if topology.id not in structure.topology_ids:
        raise ValueError("topology id is not selected by the structure")
    identity = structure.atomic_identity
    if identity is None:
        raise ValueError("molecular export requires atomic identity")
    if identity.atom_count != len(structure.atomic_numbers):
        raise ValueError("atomic identity count does not match the structure")
    if any(number == 0 for number in structure.atomic_numbers):
        raise ValueError("dummy atoms are not representable by the supported molecular exporters")
    if topology.quality_status.value != "complete":
        raise ValueError("molecular export requires a complete topology")
    if structure.coordinates.unit != "angstrom":
        raise ValueError("molecular export requires angstrom coordinates")
    coordinates = _values(structure.coordinates)
    if (
        coordinates.shape != (len(structure.atomic_numbers), 3)
        or numpy.iscomplexobj(coordinates)
        or not numpy.all(numpy.isfinite(coordinates))
    ):
        raise ValueError("molecular export requires finite (atom, xyz) coordinates")
    shifts = topology.bond_lattice_shifts
    if shifts is not None and numpy.any(_values(shifts)):
        raise ValueError("periodic bond lattice shifts are not representable")
    charges = _values(identity.formal_charges)
    if structure.molecular_charge is not None and int(charges.sum()) != structure.molecular_charge:
        raise ValueError("molecular_charge does not match atomic formal charges")
    indices = _values(topology.bond_indices)
    if indices.shape != (len(topology.stereo_labels), 2):
        raise ValueError("topology bond dimensions are inconsistent")
    if indices.size and (numpy.any(indices < 0) or numpy.any(indices >= len(structure.atomic_numbers))):
        raise ValueError("topology bond endpoint is out of range")
    return identity, coordinates, indices


def _molecule(structure, topology, *, record=None, seed_record=None):
    """Rebuild an RDKit molecule from authoritative Structure and Topology data."""
    identity, coordinates, indices = _validate_inputs(structure, topology)
    effective_seed = seed_record if seed_record is not None else record
    from rdkit import Chem
    from rdkit.Geometry import Point3D

    isotopes = _values(identity.isotopes)
    charges = _values(identity.formal_charges)
    maps = _values(identity.atom_map_numbers)
    atom_stereo = _categories(identity.stereo_labels)
    molecule = Chem.RWMol()
    for number, isotope, charge, atom_map, chirality in zip(
        structure.atomic_numbers, isotopes, charges, maps, atom_stereo, strict=True
    ):
        atom = Chem.Atom(int(number))
        atom.SetIsotope(int(isotope))
        atom.SetFormalCharge(int(charge))
        atom.SetAtomMapNum(int(atom_map))
        if chirality is not None:
            try:
                atom.SetChiralTag(getattr(Chem.ChiralType, chirality))
            except AttributeError as error:
                raise ValueError(f"unsupported atom chirality: {chirality}") from error
        molecule.AddAtom(atom)

    orders = _values(topology.bond_orders)
    aromatic = (
        (False,) * len(orders)
        if topology.aromatic_flags is None
        else tuple(bool(value) for value in _values(topology.aromatic_flags))
    )
    stereo_bonds = []
    for position, ((left, right), order, is_aromatic, label) in enumerate(
        zip(indices, orders, aromatic, topology.stereo_labels, strict=True)
    ):
        left, right = int(left), int(right)
        if is_aromatic:
            if float(order) != 1.5:
                raise ValueError("aromatic bonds must use order 1.5")
            bond_type = Chem.BondType.AROMATIC
        else:
            try:
                bond_type = {
                    1.0: Chem.BondType.SINGLE,
                    2.0: Chem.BondType.DOUBLE,
                    3.0: Chem.BondType.TRIPLE,
                }[float(order)]
            except KeyError as error:
                raise ValueError(f"unsupported bond order: {order}") from error
        molecule.AddBond(left, right, bond_type)
        bond = molecule.GetBondBetweenAtoms(left, right)
        bond.SetIsAromatic(is_aromatic)
        if is_aromatic:
            molecule.GetAtomWithIdx(left).SetIsAromatic(True)
            molecule.GetAtomWithIdx(right).SetIsAromatic(True)
        if label in ("", None):
            continue
        if label.startswith("bond_dir:"):
            name = label.removeprefix("bond_dir:").upper()
            try:
                bond.SetBondDir(getattr(Chem.BondDir, name))
            except AttributeError as error:
                raise ValueError(f"unsupported bond direction: {label}") from error
        elif label in {"E", "Z"}:
            stereo_bonds.append((position, bond, label))
        else:
            raise ValueError(f"unsupported bond stereo: {label}")

    for _position, bond, label in stereo_bonds:
        left = bond.GetBeginAtomIdx()
        right = bond.GetEndAtomIdx()
        left_neighbors = sorted(
            atom.GetIdx() for atom in molecule.GetAtomWithIdx(left).GetNeighbors()
            if atom.GetIdx() != right
        )
        right_neighbors = sorted(
            atom.GetIdx() for atom in molecule.GetAtomWithIdx(right).GetNeighbors()
            if atom.GetIdx() != left
        )
        if len(left_neighbors) != 1 or len(right_neighbors) != 1:
            if effective_seed is not None:
                return _seeded_molecule(effective_seed, structure, topology, coordinates, validate_binding=effective_seed is record)
            raise ValueError("E/Z bond stereo requires exactly one explicit neighbor per endpoint")
        bond.SetStereoAtoms(left_neighbors[0], right_neighbors[0])
        bond.SetStereo(Chem.BondStereo.STEREOE if label == "E" else Chem.BondStereo.STEREOZ)

    conformer = Chem.Conformer(len(structure.atomic_numbers))
    # Input models carry Cartesian points but not a 3D-conformer assertion.
    # Mark an exactly planar conformer as 2D so V2000 keeps its stereo marks.
    conformer.Set3D(bool(any(float(row[2]) != 0.0 for row in coordinates)))
    for index, row in enumerate(coordinates):
        conformer.SetAtomPosition(index, Point3D(*(float(value) for value in row)))
    molecule.AddConformer(conformer)
    result = molecule.GetMol()
    try:
        Chem.SanitizeMol(result)
    except (RuntimeError, ValueError) as error:
        if effective_seed is None:
            raise ValueError("topology requires a bound MolecularRecord seed for unsupported implicit hydrogen or stereo semantics") from error
        result = _seeded_molecule(effective_seed, structure, topology, coordinates, validate_binding=effective_seed is record)
    Chem.AssignStereochemistry(result, cleanIt=False, force=True)
    return result


def _seeded_molecule(record, structure, topology, coordinates, *, validate_binding=True):
    """Use raw provenance only to recover syntax absent from the core model."""
    if validate_binding:
        _validate_record(record, structure, topology)
    from rdkit import Chem
    from rdkit.Geometry import Point3D

    raw = record.raw_block.decode("utf-8", "strict")
    seed = (
        Chem.MolFromSmiles(raw.strip())
        if record.block_version is None
        else Chem.MolFromMolBlock(raw, sanitize=True, removeHs=False)
    )
    if seed is None or seed.GetNumAtoms() != len(structure.atomic_numbers):
        raise ValueError("MolecularRecord seed does not exactly match authoritative atoms")
    identity = structure.atomic_identity
    for atom, number, isotope, charge, atom_map in zip(seed.GetAtoms(), structure.atomic_numbers, _values(identity.isotopes), _values(identity.formal_charges), _values(identity.atom_map_numbers), strict=True):
        if (atom.GetAtomicNum(), atom.GetIsotope(), atom.GetFormalCharge(), atom.GetAtomMapNum()) != (int(number), int(isotope), int(charge), int(atom_map)):
            raise ValueError("MolecularRecord seed does not exactly match authoritative atom identity")
        if atom.GetNumRadicalElectrons():
            raise ValueError("radicals are not representable by the supported molecular exporters")
    edges = _edge_map(topology)
    seed_edges = {
        tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))): (float(1.5 if bond.GetIsAromatic() else bond.GetBondTypeAsDouble()), bool(bond.GetIsAromatic()), "")
        for bond in seed.GetBonds()
    }
    if set(edges) != set(seed_edges) or any(edges[key][:2] != seed_edges[key][:2] for key in edges):
        raise ValueError("MolecularRecord seed does not exactly match authoritative bonds")
    for atom, label in zip(seed.GetAtoms(), _categories(identity.stereo_labels), strict=True):
        try:
            atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED if label is None else getattr(Chem.ChiralType, label))
        except AttributeError as error:
            raise ValueError(f"unsupported authoritative atom chirality: {label}") from error
    ez_bonds = []
    for endpoints, label in zip(_values(topology.bond_indices), topology.stereo_labels, strict=True):
        bond = seed.GetBondBetweenAtoms(*map(int, endpoints))
        if label in ("", None):
            bond.SetBondDir(Chem.BondDir.NONE)
            bond.SetStereo(Chem.BondStereo.STEREONONE)
        elif label.startswith("bond_dir:"):
            try:
                bond.SetBondDir(getattr(Chem.BondDir, label.removeprefix("bond_dir:").upper()))
            except AttributeError as error:
                raise ValueError(f"unsupported authoritative bond direction: {label}") from error
        elif label in {"E", "Z"}:
            stereo_atoms = tuple(bond.GetStereoAtoms())
            if len(stereo_atoms) != 2 or any(atom < 0 for atom in stereo_atoms):
                raise ValueError("MolecularRecord seed lacks stereo atoms required by authoritative E/Z")
            bond.SetStereo(Chem.BondStereo.STEREOE if label == "E" else Chem.BondStereo.STEREOZ)
            ez_bonds.append(bond)
        else:
            raise ValueError(f"unsupported authoritative bond stereo: {label}")
    for bond in ez_bonds:
        left, right = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        for atom_index, other in ((left, right), (right, left)):
            for neighbor in seed.GetAtomWithIdx(atom_index).GetBonds():
                if neighbor.GetOtherAtomIdx(atom_index) != other:
                    neighbor.SetBondDir(Chem.BondDir.NONE)
    if ez_bonds:
        Chem.SetDoubleBondNeighborDirections(seed)
    conformer = Chem.Conformer(len(structure.atomic_numbers))
    conformer.Set3D(bool(any(float(row[2]) != 0.0 for row in coordinates)))
    for index, row in enumerate(coordinates):
        conformer.SetAtomPosition(index, Point3D(*(float(value) for value in row)))
    seed.RemoveAllConformers()
    seed.AddConformer(conformer)
    return seed


def _identity_differences(source, parsed):
    import numpy

    differences = []
    if parsed is None or source.GetNumAtoms() != parsed.GetNumAtoms():
        return ("atom inventory differs",)
    for index, (left, right) in enumerate(zip(source.GetAtoms(), parsed.GetAtoms(), strict=True)):
        if (left.GetAtomicNum(), left.GetIsotope(), left.GetFormalCharge(), left.GetAtomMapNum()) != (
            right.GetAtomicNum(), right.GetIsotope(), right.GetFormalCharge(), right.GetAtomMapNum()
        ):
            differences.append(f"atom {index} identity differs")
        if left.GetChiralTag() != right.GetChiralTag():
            differences.append(f"atom {index} chirality differs")
    if source.GetNumBonds() != parsed.GetNumBonds():
        differences.append("bond inventory differs")
    for bond in source.GetBonds():
        other = parsed.GetBondBetweenAtoms(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
        if other is None or (bond.GetIsAromatic(), bond.GetBondType(), bond.GetStereo()) != (
            other.GetIsAromatic(), other.GetBondType(), other.GetStereo()
        ):
            differences.append("bond semantics differ")
            break
    if source.GetNumConformers() and parsed.GetNumConformers():
        left = numpy.asarray(source.GetConformer().GetPositions())
        right = numpy.asarray(parsed.GetConformer().GetPositions())
        # V2000 coordinates carry four decimal places.
        if not numpy.allclose(left, right, rtol=0.0, atol=5.1e-5):
            differences.append("coordinates differ")
    return tuple(differences)


def _v2000_representable(molecule):
    if molecule.GetNumAtoms() > 999 or molecule.GetNumBonds() > 999:
        return False
    # V2000 atom-map and isotope fields are fixed-width; never let RDKit truncate.
    return all(
        atom.GetAtomMapNum() <= 999 and atom.GetIsotope() <= 999
        for atom in molecule.GetAtoms()
    )


def _mol_text(molecule, version):
    from rdkit import Chem

    text = Chem.MolToMolBlock(molecule, forceV3000=version == "V3000")
    parsed = Chem.MolFromMolBlock(text, sanitize=True, removeHs=False)
    differences = _identity_differences(molecule, parsed)
    if differences:
        raise ValueError(f"{version} cannot preserve molecular identity: {', '.join(differences)}")
    if version == "V3000":
        in_bonds, bond_ids = False, []
        for line in text.splitlines():
            if line == "M  V30 BEGIN BOND":
                in_bonds = True
            elif line == "M  V30 END BOND":
                in_bonds = False
            elif in_bonds:
                tokens = line.split()
                if len(tokens) >= 6 and tokens[2].isdigit() and tokens[3] in {"1", "2", "3", "4"}:
                    bond_ids.append(int(tokens[2]))
        if bond_ids and bond_ids != list(range(1, len(bond_ids) + 1)):
            raise ValueError("V3000 writer did not emit one-based consecutive bond IDs")
    return text


def _write(destination, chunks, is_cancelled):
    if destination is not None:
        atomic_write_chunks(Path(destination), chunks, is_cancelled=is_cancelled)


def _loss_entries(structure, topology, *, record=None, isomeric=True):
    entries = [
        ExportReportEntry("coordinates_omitted", "SMILES omits coordinates and conformer data"),
        ExportReportEntry("atom_order_canonicalized", "canonical SMILES does not preserve atom order"),
    ]
    if record is not None:
        entries.extend((
            ExportReportEntry("title_omitted", "SMILES omits the record title"),
            ExportReportEntry("raw_record_omitted", "SMILES omits raw record bytes"),
            ExportReportEntry("properties_omitted", "SMILES omits ordered raw properties"),
        ))
    if not isomeric:
        identity = structure.atomic_identity
        if identity is not None and any(_values(identity.isotopes)):
            entries.append(ExportReportEntry("isotopes_omitted", "non-isomeric SMILES omits isotopes"))
        if identity is not None and any(value is not None for value in _categories(identity.stereo_labels)):
            entries.append(ExportReportEntry("atom_stereo_omitted", "non-isomeric SMILES omits atom stereo"))
        if any(label not in ("", None) for label in topology.stereo_labels):
            entries.append(ExportReportEntry("bond_stereo_omitted", "non-isomeric SMILES omits bond stereo"))
    return tuple(entries)


def _format_loss_entries(structure, topology, *, record=None, format_name):
    identity = structure.atomic_identity
    entries = []
    if identity is not None and any(value is not None for value in _categories(identity.atom_names)):
        entries.append(ExportReportEntry("atom_names_omitted", f"{format_name} does not preserve atom names"))
    if structure.molecular_multiplicity is not None:
        entries.append(ExportReportEntry("multiplicity_omitted", f"{format_name} does not preserve molecular multiplicity"))
    if format_name == "MOL" and record is not None and record.ordered_raw_properties:
        entries.append(ExportReportEntry("properties_omitted", "MOL does not preserve ordered raw SD properties"))
    if structure.cell is not None or structure.periodic is not None:
        entries.append(ExportReportEntry("periodicity_omitted", f"{format_name} does not preserve cell or periodicity"))
    if topology.source_kind.value == "distance_inferred":
        entries.append(ExportReportEntry("inferred_connectivity", "distance-inferred connectivity requires confirmation before export"))
    return tuple(entries)


def preview_molecular_export(
    structure,
    topology,
    *,
    record=None,
    format_name,
    frame_count=1,
    isomeric=True,
    extra_loss_entries=(),
):
    """Validate molecular bindings and report loss without invoking RDKit writers."""
    if format_name not in {"mol", "sdf", "smiles"}:
        raise ValueError("format_name must be mol, sdf or smiles")
    if type(frame_count) is not int or frame_count < 1:
        raise ValueError("frame_count must be a positive int")
    if type(isomeric) is not bool:
        raise TypeError("isomeric must be bool")
    extra_loss_entries = tuple(extra_loss_entries)
    if any(
        not isinstance(entry, ExportReportEntry)
        for entry in extra_loss_entries
    ):
        raise TypeError("extra_loss_entries must contain ExportReportEntry values")
    _validate_inputs(structure, topology)
    if record is not None:
        _validate_record(record, structure, topology)
    entries = _format_loss_entries(
        structure,
        topology,
        record=record,
        format_name=format_name.upper(),
    )
    if format_name == "smiles":
        entries += _loss_entries(
            structure,
            topology,
            record=record,
            isomeric=isomeric,
        )
    entries += extra_loss_entries
    return ExportReport(
        format_name,
        False,
        frame_count,
        bool(entries),
        entries,
    )


def export_mol(structure, topology, *, record=None, seed_record=None, version="auto", confirm_loss=False, destination=None, is_cancelled=None):
    if version not in {"auto", "V2000", "V3000"}:
        raise ValueError("version must be auto, V2000, or V3000")
    if type(confirm_loss) is not bool:
        raise TypeError("confirm_loss must be bool")
    preview = preview_molecular_export(
        structure,
        topology,
        record=record,
        format_name="mol",
    )
    entries = preview.entries
    if preview.requires_confirmation and not confirm_loss:
        return MolecularExport("", preview)
    _check_cancel(is_cancelled)
    molecule = _molecule(structure, topology, record=record, seed_record=record if seed_record is None else seed_record)
    if version == "V2000" and not _v2000_representable(molecule):
        raise ValueError("V2000 cannot represent this molecule without truncation")
    selected = "V3000" if version == "auto" and not _v2000_representable(molecule) else ("V2000" if version == "auto" else version)
    try:
        text = _mol_text(molecule, selected)
    except ValueError:
        if version != "auto" or selected == "V3000":
            raise
        selected = "V3000"
        text = _mol_text(molecule, selected)
    _check_cancel(is_cancelled)
    if record is not None:
        text = _with_title(text, record.title)
    _write(destination, (text,), is_cancelled)
    return MolecularExport(
        text,
        ExportReport("mol", destination is not None, 1, bool(entries), entries),
    )


def _validate_record(record, structure, topology):
    if not isinstance(record, MolecularRecord):
        raise TypeError("record must be a MolecularRecord")
    if record.structure_id != structure.id or (
        record.topology_id is not None and record.topology_id != topology.id
    ):
        raise ValueError("record is not bound to the selected structure and topology")
    if any(character in record.title for character in "\r\n\x00"):
        raise ValueError("SDF record title must fit on one safe line")


def _record_title(record, structure, topology, derived_index):
    if record is None:
        return f"derived-{structure.id}-{derived_index}"
    _validate_record(record, structure, topology)
    return record.title


def _property_lines(record, duplicate_policy):
    if record is None:
        return
    names = set()
    for prop in record.ordered_raw_properties:
        if not prop.name or any(character in prop.name for character in "\r\n<>\x00"):
            raise ValueError("SDF property name is unsafe")
        if "\x00" in prop.value or any(line == "$$$$" for line in prop.value.splitlines()):
            raise ValueError("SDF property value contains an unsafe record separator")
        if "\r" in prop.value or "\n> " in prop.value or (prop.value and any(not line for line in prop.value.split("\n"))):
            raise ValueError("SDF property value could inject a new property")
        if duplicate_policy == "error" and prop.name in names:
            raise ValueError("SDF duplicate property names are not allowed")
        names.add(prop.name)
        yield f">  <{prop.name}>\n"
        yield f"{prop.value}\n"
        yield "\n"


def _with_title(text, title):
    lines = text.splitlines(keepends=True)
    lines[0] = title + "\n"
    return "".join(lines)


def _sdf_entries(structure, topology, record, records, entries):
    if entries is not None:
        if record is not None or records is not None:
            raise ValueError("entries cannot be combined with record or records")
        selected = tuple(entries)
    else:
        if record is not None and records is not None:
            raise ValueError("use record or records, not both")
        selected_records = (record,) if records is None else tuple(records)
        selected = tuple(SDFExportEntry(structure, topology, item) for item in selected_records)
    if not selected or any(not isinstance(item, SDFExportEntry) for item in selected):
        raise ValueError("entries must contain at least one SDFExportEntry")
    for item in selected:
        _validate_inputs(item.structure, item.topology)
        if item.record is not None:
            _validate_record(item.record, item.structure, item.topology)
    return selected


def _sdf_chunks(entries, is_cancelled, duplicate_policy):
    for index, entry in enumerate(entries, start=1):
        _check_cancel(is_cancelled)
        mol = export_mol(
            entry.structure, entry.topology, record=entry.record, seed_record=entry.seed_record, version="auto", confirm_loss=True,
            is_cancelled=is_cancelled,
        ).text
        yield _with_title(mol, _record_title(entry.record, entry.structure, entry.topology, index))
        yield from _property_lines(entry.record, duplicate_policy)
        yield "$$$$\n"


def export_sdf(structure=None, topology=None, *, record=None, records=None, entries=None, duplicate_policy="preserve", confirm_loss=False, destination=None, is_cancelled=None):
    if type(confirm_loss) is not bool:
        raise TypeError("confirm_loss must be bool")
    if duplicate_policy not in {"preserve", "error"}:
        raise ValueError("duplicate_policy must be preserve or error")
    if entries is None and (not isinstance(structure, Structure) or not isinstance(topology, TopologyRecord)):
        raise TypeError("structure and topology are required without entries")
    selected = _sdf_entries(structure, topology, record, records, entries)
    loss_entries = tuple(
        loss for entry in selected
        for loss in _format_loss_entries(entry.structure, entry.topology, record=entry.record, format_name="SDF") + entry.loss_entries
    )
    preview = ExportReport("sdf", False, len(selected), bool(loss_entries), loss_entries)
    if preview.requires_confirmation and not confirm_loss:
        return MolecularExport("", preview)
    _check_cancel(is_cancelled)
    if destination is not None:
        from io import StringIO

        captured = StringIO()
        def writing_chunks():
            for chunk in _sdf_chunks(selected, is_cancelled, duplicate_policy):
                captured.write(chunk)
                yield chunk
        _write(destination, writing_chunks(), is_cancelled)
        text = captured.getvalue()
    else:
        text = "".join(_sdf_chunks(selected, is_cancelled, duplicate_policy))
        _check_cancel(is_cancelled)
    return MolecularExport(
        text,
        ExportReport("sdf", destination is not None, len(selected), bool(loss_entries), loss_entries),
    )


def export_smiles(structure, topology, *, record=None, isomeric=True, confirm_loss=False, destination=None, is_cancelled=None):
    if type(isomeric) is not bool or type(confirm_loss) is not bool:
        raise TypeError("isomeric and confirm_loss must be bool")
    preview = preview_molecular_export(
        structure,
        topology,
        record=record,
        format_name="smiles",
        isomeric=isomeric,
    )
    entries = preview.entries
    if not confirm_loss:
        return MolecularExport("", preview)
    _check_cancel(is_cancelled)
    from rdkit import Chem

    text = Chem.MolToSmiles(_molecule(structure, topology, record=record), canonical=True, isomericSmiles=isomeric) + "\n"
    _check_cancel(is_cancelled)
    _write(destination, (text,), is_cancelled)
    return MolecularExport(text, ExportReport("smiles", destination is not None, 1, True, entries))


def _primary_topology(batch, structure):
    candidates = tuple(topology for topology in batch.topologies if topology.structure_id == structure.id)
    sanitized = tuple(topology for topology in candidates if topology.source_kind.value == "rdkit_sanitized")
    if sanitized:
        return sanitized[0]
    return candidates[0] if candidates else None


def _bound_record(batch, structure, topology):
    return next((record for record in batch.molecular_records if record.structure_id == structure.id and record.topology_id in {None, topology.id}), None)


def _structure_seed_record(batch, structure):
    return next(
        (record for record in batch.molecular_records if record.structure_id == structure.id),
        None,
    )


def _edge_map(topology, *, allow_smiles_loss=False):
    aromatic = (
        (False,) * len(topology.stereo_labels)
        if topology.aromatic_flags is None
        else tuple(bool(value) for value in _values(topology.aromatic_flags))
    )
    return {
        tuple(sorted(map(int, endpoints))): (float(order), flag, "" if allow_smiles_loss else label)
        for endpoints, order, flag, label in zip(
            _values(topology.bond_indices), _values(topology.bond_orders), aromatic,
            topology.stereo_labels, strict=True,
        )
    }

def semantic_molecular_differences(left, right, *, allow_smiles_loss=False, allow_nonisomeric_smiles_loss=False, rtol=0.0, atol=5.1e-5):
    """Compare molecular graphs, allowing SMILES' documented non-graph losses."""
    import numpy

    if type(allow_smiles_loss) is not bool or type(allow_nonisomeric_smiles_loss) is not bool:
        raise TypeError("SMILES loss flags must be bool")
    if not isinstance(left, ImportBatch) or not isinstance(right, ImportBatch):
        raise TypeError("semantic comparator requires two ImportBatch values")
    if len(left.structures) != len(right.structures):
        return ("molecular inventory differs",)
    differences = []
    for index, (a, b) in enumerate(zip(left.structures, right.structures, strict=True)):
        left_topology, right_topology = _primary_topology(left, a), _primary_topology(right, b)
        if left_topology is None or right_topology is None:
            differences.append(f"structure {index} topology is missing")
            continue
        def molecular_charge(structure):
            if structure.molecular_charge is not None:
                return structure.molecular_charge
            identity = structure.atomic_identity
            return None if identity is None else int(_values(identity.formal_charges).sum())

        if molecular_charge(a) != molecular_charge(b):
            differences.append(f"structure {index} molecular charge differs")
        if a.molecular_multiplicity != b.molecular_multiplicity:
            differences.append(f"structure {index} molecular multiplicity differs")
        from rdkit import Chem
        left_record = _bound_record(left, a, left_topology)
        right_record = _bound_record(right, b, right_topology)
        left_molecule = _molecule(
            a, left_topology, record=left_record,
            seed_record=_structure_seed_record(left, a),
        )
        right_molecule = _molecule(
            b, right_topology, record=right_record,
            seed_record=_structure_seed_record(right, b),
        )
        if Chem.MolToSmiles(left_molecule, canonical=True, isomericSmiles=not allow_nonisomeric_smiles_loss) != Chem.MolToSmiles(right_molecule, canonical=True, isomericSmiles=not allow_nonisomeric_smiles_loss):
            differences.append(f"structure {index} molecular graph differs")
            continue
        if not allow_smiles_loss:
            if not numpy.allclose(_values(a.coordinates), _values(b.coordinates), rtol=rtol, atol=atol):
                differences.append(f"structure {index} coordinates differ")
    if not allow_smiles_loss:
        if len(left.molecular_records) != len(right.molecular_records):
            differences.append("molecular record count differs")
        for index, (a, b) in enumerate(zip(left.molecular_records, right.molecular_records)):
            if a.title != b.title:
                differences.append(f"record {index} title differs")
            if a.ordered_raw_properties != b.ordered_raw_properties:
                differences.append(f"record {index} ordered raw properties differ")
    return tuple(differences)


__all__ = ("MolecularExport", "SDFExportEntry", "export_mol", "export_sdf", "export_smiles", "preview_molecular_export", "sdf_entries_from_conformer_set", "semantic_molecular_differences")
