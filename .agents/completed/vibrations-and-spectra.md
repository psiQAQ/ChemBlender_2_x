# Vibrations and Spectra

## Result

ChemBlender can normalize cclib harmonic vibration results, derive linked IR/Raman stick and peak-normalized broadened spectra, and render a selected molecular mode through one Mesh, named attributes and one instanced-arrow Geometry Nodes modifier.

## Delivered

- Added `VibrationalModeSet` with signed frequencies, Cartesian displacements, optional reduced masses, force constants, IR intensities, Raman activities and symmetry labels.
- Added linked `Spectrum` datasets for IR/Raman stick, Gaussian and Lorentzian profiles with explicit axis units, FWHM and imaginary-mode policy.
- Advanced the cclib adapter to schema 2 and mapped `vibfreqs`, `vibdisps`, `vibrmasses`, `vibfconsts`, `vibirs`, `vibramans` and `vibsyms`; missing auxiliary fields remain explicit parser issues.
- Added a Blender adapter that writes POINT-domain displacement/magnitude/reference attributes, instances one cone arrow per atom in Geometry Nodes and updates display coordinates with `sin(phase)` without modifying the authoritative `Structure`.
- Kept cclib outside the Blender Extension and introduced no new runtime dependency.

## Verification Evidence

- Blender Python full suite: 120 tests passed; 6 optional integrations skipped.
- Isolated cclib 1.8.1 full suite: 120 tests passed; 4 unrelated optional integrations skipped.
- Gaussian 16 and ORCA 5.0 IR/Raman fixtures each mapped 20 atoms and 54 modes; first-frequency and optional-field coverage matched cclib output.
- Gaussian/Lorentzian FWHM tests reached half peak at half-width; stick spectra preserved signed imaginary frequencies and source intensities.
- Blender 5.1.2 Extension validate/build and short-path isolated lifecycle passed; evaluated Geometry Nodes output contained instantiated arrow geometry and phase-coordinate checks passed.
- ZIP audit retained only the pinned RDKit wheel and excluded cclib, submodules, tests and development caches.

## Known Constraints

- This slice covers real molecular harmonic modes. Complex phonon eigenvectors, VCD, anharmonic corrections and temperature-dependent spectra remain later work.
- Raman activity is preserved as activity; no laser-frequency/temperature-dependent experimental Raman intensity is inferred.
- The adapter exposes callable mode/phase functions but no final panel, timeline handler, 2D plotting widget or sidecar session recovery yet.
- The real `user_default` package is not overwritten while the connected clean Blender process has ChemBlender/RDKit loaded.

## References

- [Design](../../docs/superpowers/specs/2026-07-22-vibrations-and-spectra-design.md)
- [Implementation plan](../../docs/superpowers/plans/2026-07-22-vibrations-and-spectra.md)
- [Semantic model decision](../decisions/0003-quantum-chemistry-semantic-model.md)
