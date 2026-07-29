# ADR 0042: Native Crystal Contract Reuses the Unified Structure Model

## Status

Accepted for the Wave 2 Crystal Pre-Gate on 2026-07-28.

## Context

Wave 1 completed a unified scientific model in which molecular and periodic
structures share identity, provenance, datasets and topology references.
The existing periodic boundary is already represented by:

- `Structure.cell` for authoritative lattice vectors;
- `PeriodicSiteData` for fractional coordinates, PBC, occupancy, disorder,
  displacement data and file-declared symmetry;
- `TopologyRecord.bond_lattice_shifts` for canonical periodic connections;
- `SymmetryResult` for derived rotation/translation matrices, space-group
  identity and standardized-structure references.

Adding parallel `CrystalStructure`, `PeriodicTopology` or persisted
`UnitCell` registries would duplicate structure identity and require a
sidecar/schema migration before a reader needs them.

## Decision

- A crystal is a `Structure` with non-`None` `cell` and `periodic`; no
  `CrystalStructure` subclass or parallel project registry is introduced.
- `Structure.cell` remains the only persisted lattice authority. Cell
  lengths and angles are deterministic derived values: lengths use the
  lattice unit and angles use degrees.
- Cartesian and fractional coordinates remain stored together.
  Reader/adaptor boundaries must validate their numerical consistency before
  publication; legacy sidecars remain readable and are not reinterpreted on
  open.
- File-declared symmetry remains source data on `PeriodicSiteData`.
  Derived structured operations remain the integer rotations and
  dimensionless translations of `SymmetryResult`; third-party objects are
  never persisted.
- Periodic bonds remain `TopologyRecord` entities with canonical integer
  `bond_lattice_shifts`.
- Wave 2 may add pure model helpers and validation, but the Pre-Gate does not
  implement CIF, Gemmi, POSCAR, crystal UI or symmetry expansion.

## Consequences

- Existing `.cbq` schema versions and canonical Reader API documents remain
  compatible.
- CIF and POSCAR readers can share one project structure identity.
- Cell parameters cannot silently diverge from lattice vectors.
- Gemmi, spglib, ASE and pymatgen remain optional/late-import boundaries.

## Verification Contract

The gate must prove cell validation and parameter derivation, Cartesian /
fractional round trips, periodic topology canonicality, symmetry matrix
validation, atomic project rollback, sidecar/canonical round trips and core
import isolation.
