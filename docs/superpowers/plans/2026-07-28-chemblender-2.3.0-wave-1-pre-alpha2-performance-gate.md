# ChemBlender 2.3.0 Wave 1 Pre-alpha.2 Performance Gate

> **Goal:** Close Wave 1 with fresh reference-hardware performance, cancellation,
> package and Blender lifecycle evidence without adding a new feature surface.

**Architecture:** Reuse the committed extXYZ, topology, Cube and Blender product
benchmarks. Treat every budget as fail-closed; make only a measured root-cause
fix when an existing gate fails. Keep all scientific work outside Blender
datablocks until the existing main-thread view boundary.

**Tech Stack:** Python 3.13, `unittest`, NumPy, Blender 5.1.2 Extension CLI,
OpenVDB, bundled RDKit.

**Stop boundary:** Complete and checkpoint Wave 1. Do not activate Wave 2,
change release metadata, push, tag or publish.

## Task 1 — Run the reference performance matrix

**Files:**
- Inspect: `ChemBlender/scripts/benchmark_extxyz.py`
- Inspect: `ChemBlender/scripts/benchmark_topology.py`
- Inspect: `ChemBlender/scripts/benchmark_cube_flow.py`
- Inspect: `tests/blender_smoke.py`
- Modify only measured benchmark/runtime files if a gate fails

**Verification:**
- Run extXYZ 1,000 frames × 1,000 atoms plus the larger metadata-only case.
- Run non-periodic topology at 50,000 atoms.
- Run the real Blender/OpenVDB Cube 128³ path.
- Run the real 10,000-record SDF/RDKit and Project Browser budgets.
- Record workload, hardware, samples, median, p95, memory and cache state.

## Task 2 — Audit long-operation ownership

**Files:**
- Inspect: import staging, background job, cancellation and cache services
- Inspect: the benchmarked reader, topology, RDKit, sidecar and view callers
- Modify only the shared root boundary when evidence proves a gap

**Verification:**
- Every product operation expected to exceed one second has visible progress,
  cancellation or an already-established background-job boundary.
- Cancellation leaves no owned staging directory, handler, Blender object,
  project mutation or mapped array leak.
- Fatal exceptions retain their existing fail-closed behavior.

## Task 3 — Run repository and Blender release-quality checks

**Files:**
- Verify: current repository tests and documentation contracts
- Verify: built Extension ZIP and isolated/user runtime

**Verification:**
- Run focused performance/contracts, full `unittest` discovery, `compileall`,
  documentation contracts and `git diff --check`.
- Run native validate/build and audit ZIP paths, CRC and wheel inventory.
- Run isolated install, product smoke and two independent lifecycle cycles.
- Record the built package SHA-256.

## Task 4 — Review and checkpoint

**Files:**
- Modify: this plan
- Modify: `.agents/active/2.3.0-wave-1-native-molecular-and-grid.md`
- Modify: measured baseline documentation only when fresh evidence changes it

**Verification:**
- Perform separate specification-compliance and code-quality reviews.
- Fix every Critical, Important and Wave-related Minor finding and repeat the
  affected verification.
- Record all Cube task commits, performance results and `Remote CI: Not Run`.
- Confirm Wave 2 remains queued and the worktree is clean.

**Commit boundary:** `chore: close Wave 1 performance gate`, followed by
`chore: checkpoint Wave 1 native molecular and grid`.
