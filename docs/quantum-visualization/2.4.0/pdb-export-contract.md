# Native PDB export contract

ChemBlender 2.4.0 Task 3 adds a dependency-free normalized PDB core writer.
It consumes the existing `Structure`, `BiologicalHierarchy`, optional
`FrameSet`, occupancy and B-factor entities. It does not introduce a PDB
model, preserve parser objects, or create Blender data.

## Public API

```python
preview_pdb_export(project_entities) -> ExportReport

export_pdb(
    project_entities,
    *,
    confirm_loss=False,
    destination=None,
    is_cancelled=None,
) -> MolecularExport
```

`confirm_loss` must be an exact `bool`. Unsupported readiness raises
`ValueError` with the frozen `PDBPQRExportStatus` value and readiness tokens.
A preview never writes. Export returns empty text and leaves the destination
untouched while a loss report is unconfirmed.

## Normalized record set

A single output model contains only 80-column `ATOM`/`HETATM` records and
`END`. Multiple output models use normalized `MODEL 1..N`/`ENDMDL` wrappers
and one final `END`. Atom serials are preserved only when the readiness
contract permits; otherwise the writer assigns `1..N` in Structure atom
order. Numeric formatting is locale-independent, negative zero is normalized,
and every record ends with LF.

This core slice is intentionally **No CONECT** and **No UI**. It does not emit
`CRYST1`, formal charge, secondary structure, assemblies, comments, or raw
source records. The preview reports these real omissions using stable codes:

- `atom_serials_renumbered`;
- `topology_omitted`;
- `cell_omitted`;
- `formal_charge_omitted`;
- `source_records_omitted`.

Any such entry requires `confirm_loss=True` before publication. UUIDs,
provenance IDs, raw whitespace and regenerated revisions are not compared as
scientific semantics.

## Safety and round-trip boundary

The writer revalidates live arrays and fixed-column widths immediately before
formatting. Non-finite data, invalid units/shapes/status, control characters,
or overflow fail before destination replacement. Publication reuses
`atomic_write_chunks`; cancellation and writer errors leave neither a partial
destination nor a sibling temporary file.

Semantic native re-import compares atomic numbers, coordinates, atom and
hierarchy identity, model/frame count, occupancy and B-factor masks and values
within PDB output precision. It does not claim byte-preserving or lossless
round-trip behavior.
