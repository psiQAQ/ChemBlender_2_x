# Quantum visualization workbench

## Goal
Implement approved first-release A-D in ChemBlender: wavefunction/Cube, orbitals, density/ESP, slices/profiles, export and recovery. Later scientific/periodic/GPU work remains a roadmap.

## Success criteria
Real fixtures pass core/Blender checks; density-only geometry, explicit old-view rebuild, safe cancellation, save/reopen/Save As and cache recovery pass.

## Constraints
Reuse QCProject, .cbq/.npy, worker, Grid3D and native Blender views. No new runtime dependency without approval. Reference submodules stay outside Extension ZIP. No remote writes or publishing. Preserve encoding and line endings.

## Phases
- [x] A: Density-only surface geometry, versioned rebuild, parent structure identity; core and real Blender regressions passed. Status: complete
- [x] B: Bounded MO/RDM/ESP and orbital/import UI passed real FCHK/Molden/UHF numerical and Blender gates. Status: complete
- [x] C: Affine sampling, dataset/range controls, slices/profiles/colorbar and atomic CSV passed core and Blender gates. Status: complete
- [ ] D: Persistent views, export, real example and lifecycle validation. Status: in_progress
- [x] References: Added MolecularNodes, MOrbVis and PySCF at reviewed commits; recorded later candidates; 37 documentation contracts passed. Status: complete
- [ ] Qualification: local core, Blender failure lifecycle and validate/build/ZIP passed; scientific success and install gates pending. Status: in_progress

## Verification
Track model, adapter, real-file, UI and reopen evidence separately. Reuse existing unittest and Blender smoke infrastructure. External CI/publication requires separate authorization.

| Layer | Current evidence | State |
| --- | --- | --- |
| Model | A identity; B blocks, cancellation and orbital metadata tested | Local regressions passed |
| Adapter | A surface/rebuild; B atomic worker/import, independent input lifetime tested | Local regressions passed |
| Real files | Pinned FCHK/Molden hashes verified | Cartesian/pure/UHF, FCHK/Molden, ghost charges, RDM and ESP passed |
| UI | Blender 5.1.1 selection, grid fit, failures, cancellation and reload passed | Real numerical success, same-project source switching and cleanup passed |
| Save/reopen | A cache/rebuild contracts passed | Complete workflow remains Phase D |

## Ownership
Root owns this plan and findings/progress. Agents edit only assigned code and tests; stage gates remain sequential.

## Next step
User approved the project-cache environment. Python 3.12.13 and all eight existing pinned packages are installed; uv pip check passed. B real-file/UI checks passed. C core and Blender gates passed. Finish D batch export, real example and lifecycle, then package qualification.
