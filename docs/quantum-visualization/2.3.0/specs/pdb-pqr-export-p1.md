# PDB/PQR export P1 readiness boundary

## Scope

P1 defines only:

- `pdb_export_readiness(project_entities)`
- `pqr_export_readiness(project_entities)`

Both are pure Python, project-wide representability checks. They do not write
files, add UI, register an exporter, or change reader capabilities. The frozen
`PDBPQRExportReadiness` report contains:

| field | contract |
| --- | --- |
| `status` | one `PDBPQRExportStatus` value |
| `tokens` | ordinally sorted, duplicate-free machine tokens |

The inputs are the existing `Structure`/embedded `AtomicIdentityData`,
`BiologicalHierarchy`, `AtomicProperty`, and `FrameSet` groups on an
`ImportBatch` or `QCProject`. No PDB/PQR-specific model is introduced; a PQR
report explicitly rejects, rather than ignores, any matching `FrameSet`.

## Deterministic association

A hierarchy, atomic property, or frame set belongs to a structure only through
its exact `structure_id`. Properties additionally match an exact
`semantic_role`. Entity revisions are independent versions, not foreign keys:
readiness never assumes that a hierarchy/property revision must equal the
Structure revision and never uses a revision string as a tiebreaker.

Exactly one matching hierarchy is required. PQR requires exactly one
`partial_charge`, one `radius` property, exactly one project-wide Structure,
and no matching `FrameSet`. PDB `occupancy`, `b_factor`, and one matching
`FrameSet` are optional; more than one matching PDB entity is ambiguous.
Duplicate Structure IDs, or multiple otherwise independent Structures in a
PQR input, are ambiguous. Candidate enumeration order, UUID spelling, category
whitespace, and dictionary insertion order do not choose a winner. Every
ambiguity produces a stable `.ambiguous` token.

## Status contract

| status | meaning |
| --- | --- |
| `Ready` | every required value is present and directly representable |
| `ReadyWithRenumbering` | only source atom serials change; deterministic allocation is available |
| `MissingHierarchy` | at least one Structure has no matching hierarchy |
| `MissingProperty` | required atom identity or PQR charge/radius is absent |
| `Invalid` | shape, unit, status, value, record kind, PQR altloc, or PQR FrameSet is invalid/unsupported |
| `FieldOverflow` | a required formatted field exceeds the P1 budget |
| `Ambiguous` | an explicit association has multiple candidates |

Precedence is `Ambiguous`, `MissingHierarchy`, `MissingProperty`, then
`FieldOverflow`. `ReadyWithRenumbering` applies only when `serial.renumber` is
the sole token; other remaining tokens are `Invalid`, and no tokens is
`Ready`. Tokens are collected independently, so one blocker does not hide
another.

## Identity and serial allocation

PDB and PQR require:

- finite `Structure.coordinates` in `angstrom`;
- complete embedded atom names;
- one `atom` or `hetatm` record kind per atom;
- explicit chain, residue number, insertion code, residue name, altloc, and
  residue-to-atom association from `BiologicalHierarchy`.

PDB permits blank altlocs or one-character altlocs. PQR P1 permits only blank
altlocs because the validated PQR reader dialect has no altloc field.

Every call revalidates the live atom-site numeric and categorical arrays
before decoding them: actual dims, shape, dtype, unit, categorical code bounds,
record-kind completeness, residue-index bounds, and residue-to-chain bounds.
This is a trust-boundary check, not a cache or graph copy. A hierarchy array
mutated after model construction returns stable `hierarchy.shape` or
`identity.<field>.invalid` tokens instead of becoming Ready or raising an
indexing exception.

Source serials are preserved only when all are positive, unique, and fit five
decimal columns. Otherwise readiness reports `ReadyWithRenumbering` plus
`serial.renumber` and the future writer must allocate `1..atom_count` in
Structure atom order. This is deterministic because serial is not the
seven-field atom identity. More than 99,999 atoms is `serial.overflow`; it is
not reported as Ready.

## P1 field budget

P1 uses the following boundary checks. Floating-point checks use the stated
decimal formatting, including rounding that can create a new leading digit.

| field | PDB | PQR P1 |
| --- | --- | --- |
| record kind | `ATOM`/`HETATM`, 6 columns | same tokens |
| atom serial | decimal width 5 | decimal width 5 |
| atom name | width 4 | width 4 |
| altloc | width 1 | blank only |
| residue name | width 3 | width 3 |
| chain ID | width 1; blank allowed | width 1; blank allowed |
| residue number | signed decimal width 4 | signed decimal width 4 |
| insertion code | width 1; blank allowed | width 1; blank allowed |
| MODEL number | decimal width 4 | not emitted; any matching FrameSet is unsupported |
| x/y/z | each `8.3` | each `8.3` |
| occupancy | optional `6.2`, `dimensionless` | not emitted |
| B-factor | optional `6.2`, `angstrom_squared` | not emitted |
| charge | not this P1 field | required `8.4`, `elementary_charge` |
| radius | not emitted | required `7.4`, `angstrom` |

The PQR widths are a conservative future-writer contract for the validated
whitespace dialect; they do not claim that PQR is a fixed-column standard.

If a PDB occupancy/B-factor property is absent, the future field is blank.
`Complete` values must be finite. `Partial` may use `NaN` as the explicit blank
marker, while finite entries still receive range/width checks. Occupancy must
be from 0 to 1. PQR charge/radius must be real atom-aligned `ArrayData`, have
exact shape, exact units, `DatasetStatus.COMPLETE`, and contain only finite
values; radius must be positive. Missing, `NaN`, `Inf`, wrong-unit, wrong-shape,
or non-complete PQR data is never replaced with zero.

For PDB, one matching `FrameSet` may supply MODEL coordinates. It must be
complete, atom-aligned, finite, and in `angstrom`; more than 9,999 output
frames is `model.overflow`. Multiple matching PDB frame sets are
`dataset.coordinates.ambiguous`.

PQR has no MODEL or other frame/Structure delimiter in the validated 10/11
field dialect. Therefore any matching `FrameSet` is
`dataset.coordinates.unsupported`, and more than one project-wide Structure is
`structure.ambiguous`. Readiness never silently drops frames, concatenates
Structures, or invents MODEL records.

## Stable token families

- association: `structure.*`, `hierarchy.*`,
  `dataset.<role>.ambiguous`, `dataset.coordinates.ambiguous`;
- required data: `identity.atom_name.missing`,
  `dataset.partial_charge.missing`, `dataset.radius.missing`;
- invalid data: `coordinates.*`, `hierarchy.shape`, `identity.record_kind`,
  `identity.atom_name.invalid`, `identity.altloc.invalid`,
  `identity.altloc.unsupported`, `dataset.<role>.shape|unit|status|values`,
  `dataset.coordinates.invalid|unsupported`;
- width/allocation: `serial.renumber`, `serial.overflow`, `model.overflow`,
  `identity.<field>.overflow`, `coordinates.overflow`,
  `dataset.<role>.overflow`.

## Non-goals

P1 does not provide `export_pdb()`/`export_pqr()`, line formatting, file IO,
UI, topology/CONECT emission, secondary structure, ribbon/cartoon,
biological assembly, crystallographic assembly expansion, or source-record
reconstruction. It makes no byte-preserving, semantic round-trip, or lossless
round-trip claim.
