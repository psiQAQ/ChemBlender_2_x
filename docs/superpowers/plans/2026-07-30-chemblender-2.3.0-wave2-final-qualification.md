# ChemBlender 2.3.0 Wave 2 Final Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the merged Wave 2 crystal schema/API/dependency boundary, qualify fixed CIF/POSCAR round trips, and record reproducible crystal performance evidence before Wave 3 starts.

**Architecture:** Qualification reuses the shipped unified model instead of adding another crystal hierarchy: `Structure.cell` is the persisted unit-cell authority, `PeriodicSiteData` stores source periodic-site semantics, periodic bonds remain `TopologyRecord.bond_lattice_shifts`, and `SymmetryResult` stores derived symmetry. The gate adds contracts, fixtures, capability/performance evidence and product verification; runtime model changes are allowed only if a new RED test exposes a real regression.

**Tech Stack:** Python 3.13, NumPy, Gemmi 0.7.5, optional spglib, standard-library `unittest`, Blender 5.1.2 Extensions, PowerShell.

## Global Constraints

- Start from merged `main` commit `644b83edf6f63f352615240296b6a060866a98c6` in an isolated worktree.
- Do not add `CrystalStructure`, persisted `UnitCell`, or `PeriodicTopology`; ADR 0042 remains authoritative.
- Do not change Reader API `1.0-rc1`, sidecar schema `1.0`, manifest version, dependencies, workflows, tags or releases.
- Gemmi and spglib objects must never enter public model entities, canonical documents or sidecars.
- Do not activate or implement Wave 3.
- Do not push without a new explicit authorization.

---

### Task 1: Persist the qualification gate

**Files:**
- Create: `docs/superpowers/plans/2026-07-30-chemblender-2.3.0-wave2-final-qualification.md`
- Modify: `.agents/active/2.3.0-wave-2-native-crystal.md`

**Interfaces:**
- Consumes: merged Wave 2 evidence at `644b83edf6f63f352615240296b6a060866a98c6`.
- Produces: one in-progress `W2-FINAL-QUALIFICATION-GATE` execution cursor.

- [x] **Step 1: Record the live baseline**

Record the branch, worktree, merged main SHA, exact post-merge CI run
`30438386040`, Blender 5.1.2 executable/Python/runtime and the 34-test
focused baseline.

- [x] **Step 2: Record scope and stop boundary**

Set required subgoals to `schema-api-freeze-audit`,
`optional-dependency-isolation`, `crystal-capability-matrix`,
`fixed-crystal-roundtrip`, `wave2-performance-baseline` and
`blender-product-qualification`. State that Wave 3 remains queued.

- [x] **Step 3: Verify documentation and commit**

Run:

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
git diff --check
git status --short
```

Commit:

```powershell
git add docs/superpowers/plans/2026-07-30-chemblender-2.3.0-wave2-final-qualification.md .agents/active/2.3.0-wave-2-native-crystal.md
git commit -m "docs: start Wave 2 final qualification"
```

### Task 2: Freeze public and dependency boundaries

**Files:**
- Create: `tests/test_wave2_crystal_qualification.py`
- Create: `docs/quantum-visualization/crystal-capability-matrix-v1.json`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: `ChemBlender.core.__all__`, `ChemBlender.reader_api.__all__`, ADR 0042 and live built-in reader descriptors.
- Produces: a checked-in crystal capability declaration and executable public/dependency audit.

- [x] **Step 1: Write the RED contract**

Add tests that load the not-yet-created matrix and assert:

```python
expected_model = {
    "Structure",
    "PeriodicSiteData",
    "TopologyRecord",
    "SymmetryResult",
}
forbidden_parallel_model = {"CrystalStructure", "UnitCell", "PeriodicTopology"}
```

The matrix must describe CIF/POSCAR structure, fractional coordinates,
symmetry, periodic topology, occupancy, ADP, Selective Dynamics, velocity
and export support with only `supported`, `partial` or `unsupported` values.
The RED failure is `FileNotFoundError` for
`crystal-capability-matrix-v1.json`.

- [x] **Step 2: Run and capture RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_wave2_crystal_qualification -v
```

Expected: the matrix test fails because the file is absent; existing public
surface and import-isolation assertions remain green.

- [x] **Step 3: Add the minimal matrix and lazy-import audit**

Create one deterministic JSON object with schema name/version and exact CIF
and POSCAR capability objects. In fresh subprocesses prove:

```python
import ChemBlender.core
assert "gemmi" not in sys.modules
assert "spglib" not in sys.modules

import ChemBlender.reader_api
assert "gemmi" not in sys.modules
assert "spglib" not in sys.modules
```

When Gemmi is available, invoke `parse_cif()` and assert Gemmi then loads
while spglib remains absent. Public exported objects must not have
`__module__` roots `gemmi` or `spglib`.

- [x] **Step 4: Run GREEN and commit**

Run:

```powershell
& $pythonBin -m unittest tests.test_wave2_crystal_qualification tests.test_core_public_api tests.test_reader_api_v1_rc tests.test_sidecar_v1_schema tests.test_quantum_visualization_docs -v
git diff --check
```

Commit:

```powershell
git add tests/test_wave2_crystal_qualification.py tests/test_quantum_visualization_docs.py docs/quantum-visualization/crystal-capability-matrix-v1.json
git commit -m "test: freeze Wave 2 crystal boundaries"
```

### Task 3: Qualify fixed scientific round trips

**Files:**
- Create: `tests/fixtures/cif/quartz.cif`
- Create: `tests/fixtures/cif/nacl.cif`
- Create: `tests/fixtures/poscar/si.POSCAR`
- Create: `tests/fixtures/poscar/fe-bcc.POSCAR`
- Modify: `tests/test_wave2_crystal_qualification.py`

**Interfaces:**
- Consumes: `parse_cif()`, `parse_poscar()`, `QCProject.commit()`, `save_project()`, `open_project()`, `export_cif()`, `export_poscar()` and `semantic_poscar_differences()`.
- Produces: a fixed qualification inventory covering quartz, NaCl, disorder, multi-block CIF, Si, bcc Fe, Selective Dynamics and velocity POSCAR/CONTCAR.

- [x] **Step 1: Write fixture-inventory RED tests**

Define literal fixture tables:

```python
CIF_CASES = ("quartz.cif", "nacl.cif", "partial-disorder.cif", "multi-block.cif")
POSCAR_CASES = ("si.POSCAR", "fe-bcc.POSCAR", "cscl-selective.vasp", "velocities.CONTCAR")
```

Require each case to parse, commit, save as sidecar schema `1.0`, reopen,
export and reparse. Compare atom identity, cell, fractional coordinates and
PBC for all cases; additionally compare declared symmetry, occupancy,
disorder and ADP when present. POSCAR comparison must include matching
Selective Dynamics and selected velocity datasets.

- [x] **Step 2: Run and capture RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_wave2_crystal_qualification -v
```

Expected: missing quartz/NaCl/Si/Fe fixture failures.

- [x] **Step 3: Add the smallest valid fixtures**

Add UTF-8/LF deterministic scientific fixtures:

- quartz: trigonal cell, fractional Si/O sites and declared space group;
- NaCl: cubic cell, fractional Na/Cl sites and declared `Fm-3m`;
- Si: two-atom direct-coordinate diamond cell;
- bcc Fe: two-atom direct-coordinate conventional cubic cell.

Reuse the existing disorder, multi-block, Selective Dynamics and velocity
fixtures instead of duplicating them.

- [x] **Step 4: Run GREEN and commit**

Run:

```powershell
& $pythonBin -m unittest tests.test_wave2_crystal_qualification tests.test_cif_controlled_roundtrip tests.test_cif_site_data tests.test_poscar_roundtrip tests.test_sidecar_v1_schema -v
git diff --check
```

Commit:

```powershell
git add tests/test_wave2_crystal_qualification.py tests/fixtures/cif/quartz.cif tests/fixtures/cif/nacl.cif tests/fixtures/poscar/si.POSCAR tests/fixtures/poscar/fe-bcc.POSCAR
git commit -m "test: qualify crystal scientific round trips"
```

### Task 4: Record a reproducible Wave 2 performance baseline

**Files:**
- Create: `ChemBlender/scripts/benchmark_crystal.py`
- Create: `docs/performance/wave2-crystal-baseline.md`
- Modify: `tests/test_wave2_crystal_qualification.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Consumes: fixed fixtures, `parse_cif()`, `parse_poscar()`, periodic derived-site preparation and Blender periodic view creation.
- Produces: deterministic benchmark JSON containing hardware/runtime, workload size, sample count, warmup, median, p95 and peak memory.

- [x] **Step 1: Write the benchmark contract RED**

Import `ChemBlender.scripts.benchmark_crystal` and require:

```python
result = benchmark_crystal(
    samples=2,
    cif_atom_count=10,
    supercell=(2, 2, 2),
    include_blender_view=False,
)
```

The result must contain `environment` and metrics named
`cif_preview`, `symmetry_expansion`, `supercell`,
`poscar_import` and `crystal_view_creation`; every metric contains
`samples`, `median_seconds`, `p95_seconds`, `peak_bytes` and workload
metadata. With `include_blender_view=False`, the view metric is explicitly
`Not Run`, never fabricated.

- [x] **Step 2: Run and capture RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_wave2_crystal_qualification -v
```

Expected: import failure because `benchmark_crystal.py` is absent.

- [x] **Step 3: Implement the minimal benchmark**

Use only `argparse`, `json`, `platform`, `statistics`, `time`,
`tracemalloc`, `tempfile` and existing ChemBlender APIs. Generate bounded
synthetic CIF input without nested full-project duplication. Use a lazy
Blender-only import for actual view creation and delete created objects after
each sample. Output canonical UTF-8 JSON with sorted keys and one trailing LF.

- [x] **Step 4: Measure the release workloads**

Run at least five samples after one warmup for:

- 1000-site CIF preflight/preview;
- symmetry expansion;
- 10×10×10 supercell derivation;
- POSCAR import;
- actual Blender periodic view creation.

Record CPU, RAM, Windows version, Blender/Python/NumPy/Gemmi versions,
sample count, median, p95, peak memory and comparison with
`docs/quantum-visualization/2.3.0/performance-budget.md`.

- [x] **Step 5: Run GREEN and commit**

Run:

```powershell
& $pythonBin -m unittest tests.test_wave2_crystal_qualification tests.test_periodic_view_settings -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
```

Commit:

```powershell
git add ChemBlender/scripts/benchmark_crystal.py docs/performance/wave2-crystal-baseline.md tests/test_wave2_crystal_qualification.py .agents/reference/code-architecture-guide.md
git commit -m "perf: record Wave 2 crystal baseline"
```

### Task 5: Run the final product gate and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-2-native-crystal.md`
- Modify: `docs/superpowers/plans/2026-07-30-chemblender-2.3.0-wave2-final-qualification.md`

**Interfaces:**
- Consumes: Tasks 1–4 commits.
- Produces: completed gate evidence and a clean local branch stopped before Wave 3.

- [x] **Step 1: Run focused and full Python verification**

Run the qualification, CIF, POSCAR, symmetry, periodic view, Reader API,
sidecar and documentation modules, then:

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
```

- [x] **Step 2: Run Blender 5.1.2 qualification**

Run native extension validate/build, exact ZIP safe-path/duplicate/CRC/wheel
audit, isolated official-ZIP install, CIF/POSCAR save/reopen/export, crystal
view creation and register/unregister/reload ×2. Confirm the built artifact
contains exact pinned Gemmi/RDKit wheels and no spglib wheel.

- [x] **Step 3: Request two independent reviews**

Review 1 checks requirements/specification compliance. Review 2 checks code
quality, fixture correctness, benchmark honesty and over-engineering. Fix all
Critical/Important and gate-related Minor findings, then rerun affected and
full verification.

- [x] **Step 4: Complete the cursor and plan**

Record all commit SHAs, RED/GREEN counts, fixture inventory, matrix status,
actual performance metrics, package SHA/size, Blender evidence, post-merge
CI provenance and `Remote CI: Not Run` for this local qualification branch.
Set next task to `Wave 3 Exchange Pre-Gate` but keep Wave 3 queued.

- [x] **Step 5: Commit checkpoint and stop**

```powershell
git add .agents/active/2.3.0-wave-2-native-crystal.md docs/superpowers/plans/2026-07-30-chemblender-2.3.0-wave2-final-qualification.md
git commit -m "chore: checkpoint Wave 2 final qualification"
git status --short
```

Stop with a clean worktree. Do not push, activate Wave 3, tag or release.
