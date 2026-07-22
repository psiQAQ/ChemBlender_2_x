# Wavefunction Derived Fields

## Result

ChemBlender can derive molecular-orbital and electron-density `Grid3D` datasets from normalized `Structure`/`BasisSet`/`OrbitalSet` entities with GBasis 0.1.0, then pass the result to the existing OpenVDB Volume adapter without loading the numerical backend in Blender.

## Delivered

- Fixed `submodules/gbasis` at official `v0.1.0` commit `6440c84f3fcf8d42cbd9b5de53ae8d70bed4cd4f`.
- Recorded GBasis/Grid/ORBKIT API, license and Windows/Python compatibility comparison in ADR 0007.
- Added affine-grid MO and density derivation with restricted/unrestricted channels, explicit convention/sign handling, deterministic revision hashes, units and provenance.
- Kept generalized spinors, missing occupations, wrong references/units and invalid grids as explicit failures.
- Added pure-basis comparison against GBasis's official IOData wrapper.
- Kept GBasis, SciPy and IOData outside the Blender Extension package.

## Verification Evidence

- Blender Python standard suite: 97 tests passed, 3 optional integrations skipped.
- Python 3.12 worker integration: 7 wavefunction-grid tests passed.
- Python 3.13/NumPy 2.5.1 compatibility probe: the same 7 tests passed, but this is not the supported dependency-resolution path.
- `water_sto3g_hf_g03.fchk`: MO 0 discrete norm `1.0045725101`; density integral `10.0097251825` electrons for 0.1-bohr sampling and 6-bohr margins.
- `water_ccpvdz_pure_hf_g03.fchk`: normalized-model evaluation matched the official IOData wrapper at `rtol=atol=1e-12`.
- Blender 5.1.2 Extension validate/build passed; isolated lifecycle and real `user_default` install passed; OpenVDB cache retained `molecular_orbital` role and value unit.
- ZIP audit through lifecycle smoke confirmed the only wheel is pinned RDKit and development submodules are excluded.

## Known Constraints

- GBasis 0.1.0 declares `numpy<2` on Windows, so the supported worker baseline is Python 3.12/NumPy 1.26.4; it is not bundled into Blender 5.1/Python 3.13.
- Density currently reconstructs the 1-RDM from real MO coefficients and occupations. Direct RDM, spin density, ESP, derivatives and complex spinors remain follow-up work.
- Uniform grids evaluate in one array; chunking, adaptive grids and worker IPC remain deferred until scale baselines require them.
- Existing menu-ID, regex escape and loaded-wheel DLL cleanup warnings are unchanged legacy behavior.

## References

- [Backend decision](../decisions/0007-wavefunction-grid-backend.md)
- [Design](../../docs/superpowers/specs/2026-07-22-wavefunction-grid-design.md)
- [Implementation plan](../../docs/superpowers/plans/2026-07-22-wavefunction-grid.md)
