# Wavefunction Observables

## Result

ChemBlender can normalize IOData one-particle density matrices and effective nuclear charges, then derive electron-density, spin-density and electrostatic-potential `Grid3D` datasets with explicit semantics, units and provenance.

## Delivered

- Added versioned `DensityMatrix` and structure-linked `AtomicProperty` entities with stable basis, spin-role and source-calculation references.
- Mapped IOData `scf`, `scf_spin`, `post_scf` and `post_scf_spin` one-RDM keys; unknown roles are reported instead of silently imported.
- Added total- and spin-density evaluation through general AO-matrix contraction so spin density may be negative.
- Added GBasis ESP evaluation with explicit nuclear-charge input, Cartesian-convention correction and nuclear-singularity rejection.
- Kept worker-only IOData/GBasis dependencies outside the Blender Extension and reused the existing affine `Grid3D`/OpenVDB path.

## Verification Evidence

- Standard core suite: 108 tests passed under Blender Python; optional worker integrations were skipped when unavailable.
- Python 3.12 worker suite: 108 tests passed with IOData 1.0.1, GBasis 0.1.0 and NumPy 1.26.4.
- `water_sto3g_hf_g03.fchk`: RDM density integral `10.00972518995233` electrons; maximum difference from occupation-derived density `8.3482376567e-8`.
- `ch3_uhf_sto3g_g03.fchk`: total density integral `8.999748772940842`; spin-density integral `0.9999988480353136`; sampled values span negative and positive regions.
- Water ESP fixed-point values matched GBasis's official API at three off-nuclear coordinates.
- Blender 5.1.2 Extension validate/build, short-path isolated lifecycle and ZIP-content audit passed. The real `user_default` install was not overwritten because the connected clean scene had ChemBlender/RDKit loaded; the preceding GBasis stage had already verified that installation path.

## Known Constraints

- This slice supports finite, real, symmetric AO-basis one-RDMs. Complex/generalized spinors, transition density and two-RDMs remain out of scope.
- ESP requires an explicit normalized nuclear-charge property and rejects sampling points inside the configured nuclear exclusion radius.
- Field-on-surface interpolation, derivative fields, adaptive grids and chunked evaluation remain later wavefunction work.
- Windows isolated extension installation needs a short temporary profile path because the bundled RDKit wheel contains deeply nested files.

## References

- [Design](../../docs/superpowers/specs/2026-07-22-wavefunction-observables-design.md)
- [Implementation plan](../../docs/superpowers/plans/2026-07-22-wavefunction-observables.md)
- [Wavefunction backend decision](../decisions/0007-wavefunction-grid-backend.md)
