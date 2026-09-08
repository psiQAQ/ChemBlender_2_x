# Quantum visualization workbench

## Goal
Implement approved first-release A-D in ChemBlender: wavefunction/Cube, orbitals, density/ESP, slices/profiles, image export and recovery. Later scientific/periodic/GPU work remains a roadmap.

## Success criteria
Real fixtures pass core/Blender checks; density-only geometry, explicit old-view rebuild, cancellation, save/reopen/Save As and cache recovery pass.

## Constraints
Reuse QCProject, .cbq/.npy, worker, Grid3D and native Blender views. The user approved the independent project-cache Python environment; existing pinned constraints are unchanged. Reference sources stay outside the Extension ZIP. No remote writes or publication. Preserve scientific artifact bytes.

## Phases
- [x] A: Density-only property geometry, versioned rebuild and structure identity. Status: complete
- [x] B: Bounded MO/RDM/ESP worker and orbital/import UI. Status: complete
- [x] C: Affine sampling, independent datasets/ranges, slices/profiles/colorbar and CSV. Status: complete
- [x] D: Persistent views, sequential image export, real water example and complete lifecycle. Status: complete
- [x] References: MolecularNodes, MOrbVis and PySCF pinned; later candidates indexed. Status: complete
- [x] Qualification: Local unittest, numerical comparisons, native validate/build/ZIP, isolated and actual-user installation passed. Status: complete

## Verification

| Layer | Evidence | State |
| --- | --- | --- |
| Model | Structure identity, bounded evaluation/cancellation, conservative orbital metadata, affine analytical fields | Passed |
| Adapter | Atomic ImportBatch/report/export, density-only geometry, independent input lifetime and rollback | Passed |
| Real files | Cartesian/pure/UHF, FCHK/Molden, ghost charges, RDM/ESP; independent PySCF water comparison at 12 points | Passed |
| UI | Real Blender 5.1.1 import/selection/calculation/cancel/reload, scientific slice/profile and sequential image export | Passed |
| Save/reopen | Both Save As remap modes, moved .blend/.cbq pair, deleted VDB cache; scientific arrays/CSV and view parameters unchanged | Passed |

Final unittest: 2,410 ran; 2,379 passed, 31 optional/environment skips, zero failures/errors. Dedicated numerical and real Blender checks cover their relevant optional paths separately. Remote CI and publication: Not Run, outside current authorization.

## Delivery
See examples/quantum-workbench/README.md and .agents/completed/quantum-visualization-workbench.md. The example contains .blend, .cbq, PNG, CSV, provenance and PySCF comparison. Original shared extension dependencies and user preferences were verified after installation; the interactive scene remains unchanged. No required first-release work remains.
