# Physical quantity visualization and SOP

## Authority and boundary

Implement the user's approved physical-quantity panel workflows, Research/Teaching materials, Cycles outputs, real examples and Chinese SOP. The previous workbench at `3c80892` is the starting point, not a substitute for this task's validation.

The current plan and five-layer quantity matrix are maintained in [.planning/task_plan.md](../../.planning/2026-09-08-physical-quantity-visualization-sop/task_plan.md); [progress.md](../../.planning/2026-09-08-physical-quantity-visualization-sop/progress.md) records material changes and observed failures. Verify current Git and runtime state when resuming.

## Delivered and ongoing

- Shared public scientific import, View creation/update/rebuild, materials, native plots, trajectory/phonon phase controls and transactional Cycles/PNG/MP4 export are implemented.
- Real molecular fields have 22 formal images and three `.blend + .cbq` workbenches. Lifecycle validation preserves 40 total Views and 61 scientific arrays through Save As, move, VDB deletion, rebuild and reopen.
- PQR charges and rMD17 configurations/forces have 6 formal stills, 128 sequence PNGs, 4 MP4s and two saved workbenches. Save As, whole-folder move, independent process reopen, public LOAD/REBUILD and all 32 frames Passed; 14 scientific NPY files are unchanged.
- [Chinese SOP](../../docs/quantum-visualization/scientific-visualization/README.md) includes 11 actual Blender window screenshots and an offline HTML page. It distinguishes verified real workflows from implementation-only or synthetic coverage.
- Full unittest-06 Passed 2504 tests, 36 optional skips. Native material, quantitative-color update, affine cloud, transactional export and project-ownership regressions Passed. Qualification and full-smoke identities are recorded in [local delivery verification](../../docs/quantum-visualization/scientific-visualization/VERIFICATION.md).
- Source implementation is committed locally as `67ace73`; no remote write or release was performed. All Blender installs and UI operations use private profiles; the shared actual-user installation is unchanged.

## Required continuation

1. Resolve the already-presented cache-only dependency proposal before actual cclib/periodic/Fermi/critic2 computation. An implemented adapter or synthetic render does not complete these quantity gates.
2. After approval, validate each backend with the pinned real inputs, finish any runtime integration gaps (including explicit Windows-to-WSL critic2 invocation), then generate the remaining per-quantity Cycles images/animations and GUI SOP sections.
3. Keep the full plan open until these real scientific, panel, render and lifecycle gates pass. Run shared-user installation or remote release gates only with their corresponding authorization.

New package installations require approval under root `AGENTS.md`. The existing cache environment was approved; the [hash-locked package and Fortran-toolchain proposal](../../examples/scientific-visualization/dependencies/PROPOSAL.md) remains pending. Do not install into global Blender Python, change a shared Blender profile, push, run remote CI or publish without corresponding authorization.
