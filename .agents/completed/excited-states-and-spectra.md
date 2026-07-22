# Excited States and Electronic Spectra

## Result

ChemBlender can normalize cclib vertical excited states, preserve signed configuration and ECD data, derive linked UV-Vis/ECD spectra, and reserve typed dataset references for transition-density and NTO/hole-electron views.

## Delivered

- Added `ExcitationContribution`, `ExcitedStateReferences` and `ExcitedStateSet` with explicit state, spin, unit, status and reference validation.
- Advanced the cclib adapter to schema 3 for `etenergies`, `etoscs`, `etsyms`, `etsecs`, `etrotats`, `etdips`, `etveldips` and `etmagdips`.
- Preserved cclib's unknown cross-parser rotatory-strength unit as `unknown`/`ambiguous`; malformed configurations are reported without discarding valid state energies.
- Generalized `Spectrum` source and selection contracts and added UV-Vis/ECD stick, Gaussian and Lorentzian derivation on a wavenumber axis.
- Kept cclib and scientific parser dependencies outside the Blender Extension.

## Verification Evidence

- Full isolated cclib 1.8.1 suite: 134 tests passed; 4 unrelated optional integrations skipped.
- Gaussian 16/09 and ORCA 5.0 TD/ADC2 fixtures matched expected state counts, first excitation energies, transition-dipole coverage, rotatory strengths and configuration structures.
- Electronic spectrum tests preserved signed ECD values, source UUIDs, deterministic revisions and peak-normalized FWHM behavior.
- Ruff and `git diff --check` passed for the changed Python surface.
- Blender 5.1.2 Extension validate/build and short-path isolated lifecycle passed; the ZIP contained only the pinned RDKit wheel and excluded cclib/submodules/tests.

## Known Constraints

- This slice does not execute TDDFT/EOM-CC or derive transition density/NTO data.
- ECD is a relative unknown-unit display until a source-specific adapter supplies a validated unit.
- Final 2D plotting UI and state-to-3D linked selection are part of the Phase 1 Blender-adapter closure.
- The real `user_default` package was not overwritten while the connected Blender process had ChemBlender/RDKit loaded; the short-path isolated lifecycle covered the package runtime gate.

## References

- [Decision](../decisions/0008-excited-state-and-spectrum-contract.md)
- [Design](../../docs/superpowers/specs/2026-07-22-excited-states-and-spectra-design.md)
- [Implementation plan](../../docs/superpowers/plans/2026-07-22-excited-states-and-spectra.md)
