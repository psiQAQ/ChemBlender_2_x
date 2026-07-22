# Gemmi/spglib Crystal Foundation

Completed on 2026-07-22.

## Delivered

- Added `CIFEnvelope`, `PeriodicSiteData` and `SymmetryResult` plus atomic project registries and reference validation.
- Added a late-import Gemmi 0.7.5 CIF reader preserving raw source, tags, uncertainty-normalized cell values, fractional/cartesian coordinates, occupancy, Uiso/Uij, ADP and disorder.
- Added a late-import spglib 2.7.0 derivation adapter preserving operations, Hall/IT identity, Wyckoff/equivalent-atom mappings, change-of-basis/origin data and a separate standardized structure.
- Fixed official source references at Gemmi `5cc1c23c6007e0e6cbd69289c6f7c0bff50e943e` and spglib `12355c77fb7c505a55f52cae36341d73b781a065`.
- Added CIF/POSCAR golden fixtures and retained the legacy Blender reader behavior as a migration baseline.

## Verification

- Blender Python full suite: 151 tests passed, 15 skipped for unavailable optional dependencies.
- Gemmi/spglib Python 3.13 full suite: 151 tests passed, 9 skipped for unrelated optional backends.
- CsCl integration verified space group 221, Hall 517, 48 operations, standard structure, bohr conversion and a nonzero origin-shift change-of-basis formula.
- Blender 5.1.2 native validate/build and isolated install/lifecycle passed with `--python-exit-code 1`.
- Extension ZIP includes only the two lightweight adapter modules, not Gemmi, spglib, submodules or tests.

## Deferred Boundaries

- Existing Blender CIF/POSCAR UI still uses the legacy reader; migration to normalized core is a later adapter task.
- Multi-block selection, magnetic/modulated CIF, dictionary validation and occupancy-aware symmetry are not implemented.
- ASE/pymatgen structure exchange and periodic scalar fields begin in the next Phase 2 slice.
