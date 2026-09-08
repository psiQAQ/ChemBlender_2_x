# Physical quantity visualization and SOP

## Goal
Implement the approved all-quantity panel workflow, research/teaching materials, Cycles renders, real examples and Chinese Markdown/offline HTML SOP on top of 3c80892. The earlier A-D workbench is complete and its plan stays unchanged.

## Success criteria
Each quantity has a real input, validated scientific interpretation, public panel operations, two material-template renders, durable View parameters and a replayable illustrated SOP. Dynamic quantities also have PNG frames and MP4. An adapter or synthetic test alone is not completion.

## Constraints
- Reuse QCProject, ImportBatch, .cbq/.npy, workers, Grid3D and scene presets. No new quantum solver or .cbq storage format.
- Scientific arrays and provenance remain authoritative; display transforms, opacity, camera, lighting and background are View settings.
- No implicit grid alignment/resampling; true-zero legends; negative fields never feed negative extinction.
- All runtime tests/screenshots use private BLENDER_USER_RESOURCES. Never factory-reset a shared profile or alter shared wheels/preferences.
- Existing cache Python environment is approved. New dependency installations require explicit approval before installation. No global Blender packages.
- Source references remain pinned and outside the Extension ZIP. No push/remote CI/publication.
- Root owns this plan and shared progress; agents own explicitly assigned source files.

## Phases
- [ ] 1. Real inputs and common View/material/render foundation Passed; optional package/toolchain installation awaits approval.
- [ ] 2. Wavefunction scalar fields, volumes, atomic scalar/vector workflows Passed; real ELF/LOL/NCI output awaits optional toolchain.
- [ ] 3. Real trajectories/forces, PNG and MP4 Passed; vibration/spectrum real-backend gate awaits optional parser installation.
- [ ] 4. Band/DOS/PDOS, phonons, Fermi and QTAIM. Status: in_progress; real computations await optional-dependency approval
- [ ] 5. Current real quantities delivered with 28 stills, 128 frames, 4 MP4, five workbenches, 11 real GUI screenshots and offline SOP; remaining quantity artifacts await optional environments.
- [ ] 6. Available local gates Passed: full unittest-06, qualification-08, exact-package full Blender smoke-06, all five workbench Save As/move/reopen checks. Optional real-backend gates, shared actual-user installation and remote release checks remain open.

## Quantity acceptance matrix
| Quantity | Model | Adapter | Real file | UI/render | Reopen/SOP |
| --- | --- | --- | --- | --- | --- |
| MO alpha/beta | Passed | Passed | water/CH3 FCHK | 8 formal images | Reopen and illustrated SOP Passed |
| Electron density | Passed | native signed volume/surface | water FCHK | 4 formal images | Reopen and illustrated SOP Passed |
| Spin density | Passed | signed surface/volume | CH3 FCHK | 2 formal images | Reopen and SOP Passed |
| Difference density | Passed | strict same-grid subtraction | N atom MP2-SCF | 2 formal images | Reopen and SOP Passed |
| ESP / local potential | Passed | surface/slice/profile | water FCHK ESP | 6 formal images | Reopen Passed; periodic input pending |
| ELF / LOL | range validation Passed | native grid templates | external output pending | synthetic adapters Passed | dependency approval pending |
| RDG / sign-lambda2-rho / NCI | pair validation Passed | native Grid to Mesh recipe | external output pending | native UI Passed | dependency approval pending |
| Atomic charges / populations | Passed | native point colors | PQR998 | 2 formal Cycles images | saved Views, reopen and illustrated SOP Passed |
| Forces / gradients | binding/sign Passed | native arrows | rMD17 | 2 formal stills + 64 PNG/2 MP4 | saved Views, reopen and illustrated SOP Passed |
| Vibration / IR / Raman | Passed | native molecule/Curve | pinned Gaussian/ORCA | synthetic UI Passed | optional parser installation pending |
| UV-Vis / ECD | verified Gaussian ECD units | native Curve | pinned Gaussian/ORCA | synthetic UI Passed | optional parser installation pending |
| Band / DOS / PDOS | Passed | native Curve/PDOS selection | pinned Si VASP | synthetic UI Passed | optional parser installation pending |
| Fermi / surface properties | Passed | worker + native mesh/arrows | pinned SrVO3 VASP | synthetic UI Passed | optional worker installation pending |
| QTAIM / rho / Laplacian | Passed | FLUXPRINT samples + CP glyphs | external output pending | synthetic import/UI Passed | toolchain approval pending |
| Phonons | complex modes Passed | file worker + native phase | pinned NaCl VASP | synthetic UI Passed | optional parser installation pending |
| Trajectories / frame properties | Passed | bounded native frame update | rMD17 32 frames | 2 formal stills + 64 PNG/2 MP4 | saved Views, reopen and illustrated SOP Passed |

## Design decisions
- Extend Browser -> representation -> parameters -> Create/Update View -> Research/Teaching -> Render/Export.
- View instance UUID and root/component ownership are distinct from reproducible render identity. Atomic rebuild preserves unrelated user objects and old views on failure.
- Research: light neutral background, orthographic camera, matte lit structures and unlit quantitative layers/legends, Standard/exposure 0/gamma 1.
- Teaching: dark neutral background, perspective, soft key/fill/rim, volume and transparent layers; lit quantitative surfaces are explicitly morphology mode with a quantitative-color alternative.
- Still defaults 2400x1800, Cycles 256 samples adaptive+denoise; preview 32 samples. Animation 24 fps at 1280x720, PNG sequence plus MP4.
- Fermi requires real 3D k mesh and original band/E_F identity; QTAIM requires FLUXPRINT TEXT samples, not straight CP connectivity.
- Generalize sequential orbital export transactions to owned View roots; retain progress/cancel and publish only complete output bundles.
- SOP is one Markdown source with stable anchors, native screenshots and local assets; offline HTML built with existing marked.

## Verification
Use narrow scientific tests, actual-file comparisons, native Blender materials/geometry/UI, save/reopen/Save As/move/cache rebuild, then full unittest, validate/build/ZIP and isolated/actual installation. Track Passed/Failed/Not Run honestly.

## Errors
- Initial contract/test-double failures are resolved: full unittest-06 Passed 2504 tests, 36 optional skips. Final full smoke-06 Passed against qualification-08, with all 198 current extension Python files matched to the ZIP before and after execution.
- Real-render QA exposed evaluated Volume bounds and flat-camera roll; both corrected and native geometry regression passed.
- Trajectory export leaked one unused arrow node group; fixed at its creation/ownership boundary and full-resource rollback regression passed.
- Python 3.13 TemporaryDirectory ACL survived Windows output publication. Export staging now inherits the selected folder ACL; native scientific/orbital/trajectory export reruns Passed.
- GUI save/reopen exposed LazyNpyArray lacking NumPy .size/.flat in optional cloud camera focus. The renderer now obtains its read-only mmap view; native reopened-array cloud render, bounded cancellation and cleanup Passed.
- Biological point material specialization and scalar/category shader updates are fixed; native geometry, ownership, rollback and actual Cycles color regressions Passed.
- Explicit foreign-project Views retain rebuild diagnostics without keeping an unrelated current project dirty. Native PDB-to-MOL2 Save As/reopen and invalid current-binding recovery Passed.
- Optional scientific/fermi package installation and cache-only Fortran extraction remain pending explicit approval. No packages or toolchain installed.

## Delivery and continuation
- Source implementation: local commit 67ace73. [Illustrated SOP](../../docs/quantum-visualization/scientific-visualization/README.md), [examples](../../examples/scientific-visualization/README.md) and [verification](../../docs/quantum-visualization/scientific-visualization/VERIFICATION.md) form the concrete reviewable delivery.
- Final package SHA-256: fa66bc9f407b3e87d894fd8fc9d0069a470c3e0cc690ae33f009190ca6867995. GUI screenshots accurately record qualification05; later changes are validated runtime fixes and EOF cleanup.
- Next required action is approval of the already-presented hash-locked Python/Fortran proposal. After approval, finish actual optional backend execution, remaining per-quantity renders/animations and corresponding real GUI/lifecycle SOP gates. The complete all-quantity plan is not marked complete.
