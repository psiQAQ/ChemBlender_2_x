# Quantum visualization workbench

## Goal
Implement the approved first release A-D in ChemBlender: wavefunction/Cube input, orbital selection, density/ESP, slices/profiles, reproducible export and project recovery. Later professional analysis, periodic and GPU work remains a roadmap.

## Success criteria
Real scientific fixtures pass core and Blender checks; fixed density with changed property preserves geometry; old views rebuild explicitly; computations cancel safely; project save/reopen/Save As/cache reconstruction works. No unverified completion claims.

## Constraints
Reuse QCProject, .cbq/.npy, worker, Grid3D and native Blender views. No new runtime dependency without approval. Reference submodules stay outside Extension ZIP. No remote writes or publishing. Preserve encoding and line endings.

## Phases
- [x] A: Density-only surface geometry, versioned rebuild, parent structure identity; core and real Blender regressions passed. Status: complete
- [ ] B: Orbital browser, bounded wavefunction computation and RDM/ESP worker adapters. Status: in_progress
- [ ] C: Property settings, affine sampling, slices/profiles and colorbar. Status: pending
- [ ] D: Persistent views, export, real example and lifecycle validation. Status: pending
- [x] References: Added MolecularNodes, MOrbVis and PySCF at reviewed commits; recorded later candidates; 37 documentation contracts passed. Status: complete
- [ ] Qualification: core tests, Blender runtime, Extension validate/build/ZIP/install and final diff. Status: pending

## Verification
Track model, adapter, real-file, UI and reopen evidence separately. Reuse existing unittest and Blender smoke infrastructure. External CI/publication requires separate authorization.

## Ownership
Root owns this plan and findings/progress. Agents edit only assigned code and tests; stage gates remain sequential.

## Next step
Implement bounded wavefunction worker operations and orbital UI; optional numerical environment installation awaits user approval.
