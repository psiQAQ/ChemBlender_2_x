# ChemBlender 2.3.0 Wave 4 Performance and UX Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure and enforce the approved scale/timing budgets, eliminate UI blocking and resource leaks, and make quality/revision/project states understandable for RC users.

**Architecture:** Benchmarks isolate parse, sidecar, cache, view and browser stages. Long operations use cancellable modal tasks or fixed workers. UI performance uses cached projections and never touches large arrays during draw. UX testing follows defined task scripts and records completion/error evidence.

**Tech Stack:** Python timing/statistics, Blender timers/modal operators, existing sidecar/worker/cache services, deterministic generators and Blender smoke.

## Global Constraints

- Optimize only measured bottlenecks.
- Performance changes cannot weaken scientific validation or diagnostics.
- CI tracks trends; absolute SLA uses documented reference hardware.
- Cancellation removes staging/temp resources and leaves project state valid.
- No GPU or new heavy dependency in 2.3.0.
- RC adds fixes only.

---

### Task 1: Create a unified benchmark harness and datasets

**Files:**
- Create: `ChemBlender/scripts/benchmark_230.py`
- Create: `ChemBlender/benchmarks/datasets.py`
- Create: `tests/test_benchmark_harness.py`
- Create: `docs/quantum-visualization/2.3.0/benchmarks/README.md`

**Interfaces:**
- Produces: canonical JSON benchmark results with median/p95 and environment metadata.

- [ ] **Step 1: Define deterministic dataset generators**

Generators create structures at 50k/250k atoms, trajectories at 1k/100k frames using lazy arrays, 128³/256³ grids and SDF index fixtures at 10k/100k records. Seeds and hashes are fixed.

- [ ] **Step 2: Implement benchmark cases**

Cases: extension enable (separate Blender launch), preflight first feedback, parse, project commit, sidecar save/open, VDB cache, default view, trajectory frame, browser projection/filter and cancel cleanup.

- [ ] **Step 3: Implement statistics**

Warmup count, sample count, median, p95, min/max, cold/hot cache flag and failure count. Reject non-finite timing and missing environment fields.

- [ ] **Step 4: Test harness and commit**

Unit-test JSON and small generators, then commit.

### Task 2: Establish reference baseline and regression policy

**Files:**
- Create: `docs/quantum-visualization/2.3.0/benchmarks/2.3.0-rc-reference.md`
- Create: `ChemBlender/benchmarks/budget.json`
- Create: `tests/test_performance_budget.py`

**Interfaces:**
- Produces: approved budgets and comparison function.

- [ ] **Step 1: Record reference environment**

Use Windows x64, Blender 5.1.2, CPU/RAM/storage and clean user resources. Run cold and warm cases. Store raw JSON as a release artifact or tracked small baseline if stable.

- [ ] **Step 2: Encode budgets**

Use approved targets: enable 2s, feedback 0.5s, common view 3s, Cube 10s, cached frame 100ms, browser filter 200ms. Trend thresholds for cloud CI are documented separately.

- [ ] **Step 3: Add comparison tests**

A result over hard local budget fails reference qualification. CI trend regression over the approved percentage fails unless baseline change is reviewed with evidence.

- [ ] **Step 4: Commit**

Commit budgets, tests and observed reference document.

### Task 3: Remove UI-thread blocking in import and cache flows

**Files:**
- Create: `ChemBlender/ui/tasks.py`
- Modify: Quick Import, Cube cache, SDF indexing and save operators
- Create: `tests/test_task_state_machine.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: `TaskState`, progress events, cancel and completion callbacks.

- [ ] **Step 1: Define task state machine**

States: pending, running, cancelling, cancelled, failed, succeeded. Progress is monotonic 0–1 with stage text. Invalid transitions raise in tests.

- [ ] **Step 2: Implement modal operator bridge**

Pure work runs in chunks/timer or worker. Completion enqueues Blender mutations on the main thread. UI shows progress and Cancel.

- [ ] **Step 3: Add cancellation leak tests**

Cancel during hash, parse, sidecar save and VDB preparation. Assert no staging roots, temp files, orphan objects, duplicate handlers or dirty project mutation.

- [ ] **Step 4: Run and commit**

Blender smoke and pure state tests pass; commit.

### Task 4: Optimize Project Browser projection and search

**Files:**
- Modify: `ChemBlender/ui/project_browser/model.py`
- Create: `tests/test_project_browser_performance.py`
- Modify: `ChemBlender/ui/project_browser/panel.py`

**Interfaces:**
- Produces: revision-keyed row cache, normalized search index and paged/virtualized data rows.

- [ ] **Step 1: Measure current projection**

Build projects with 10k/100k record rows and capture projection/filter timings. Confirm lazy arrays are not loaded.

- [ ] **Step 2: Implement cached normalized index**

Index display names, types, status and source names when project revision changes. Search uses casefolded tokens. Expansion changes rebuild only affected subtrees.

- [ ] **Step 3: Page large record groups**

UI rows represent pages/summary and materialize a bounded range. Provide total counts and jump/filter, not 100k RNA collection entries.

- [ ] **Step 4: Verify budget and commit**

Filter median/p95 meet 200ms on reference case. Commit.

### Task 5: Improve quality, revision and recovery UX

**Files:**
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/ui/project_browser/panel.py`
- Modify: `ChemBlender/ui/properties.py`
- Create: `ChemBlender/ui/diagnostics.py`
- Create: `tests/test_quality_ui_contract.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: consistent badges, revision prompts, diagnostic detail, recovery actions and export confirmations.

- [ ] **Step 1: Standardize status presentation**

Use one mapping for Complete/Partial/Ambiguous/Incomplete/Invalid icons/text. Color is supplementary, not the only signal.

- [ ] **Step 2: Revision available flow**

Existing views show current/new revision IDs and actions Update Selected Views, Comparison View, Keep Current. No automatic switching.

- [ ] **Step 3: Diagnostic detail**

Show severity, source/record/entity, field, original/normalized values, recovery, scientific consequence and suggested action. Copy/export buttons use canonical report service.

- [ ] **Step 4: Project recovery actions**

Missing/mismatch/incompatible/invalid link states offer Relink, Verify, Open Read-only/diagnostics or Detach according to safety. Existing objects remain.

- [ ] **Step 5: Verify and commit**

Blender smoke covers each state and export confirmation; commit.

### Task 6: Conduct scripted usability acceptance

**Files:**
- Create: `docs/quantum-visualization/2.3.0/usability-test-script.md`
- Create: `docs/quantum-visualization/2.3.0/usability-results-rc1.md`
- Modify: `.agents/active/2.3.0-wave-4-migration-release.md`

**Interfaces:**
- Produces: repeatable user-task evidence for RC.

- [ ] **Step 1: Define tasks**

Install, import XYZ/SDF/Cube/CIF/PDB, inspect diagnostics, resolve Cube semantic, group SDF conformers, save/reopen, update revision, derive edited structure, export and migrate legacy scene.

- [ ] **Step 2: Record measurable outcomes**

Completion, time, errors, help required and scientific misunderstanding. Do not collect only subjective satisfaction.

- [ ] **Step 3: Classify issues**

Release blocker: data loss/corruption, wrong scientific mapping, inability to recover/save, crash or core task failure. Major/minor classification is documented.

- [ ] **Step 4: Fix blockers only after RC scope freeze**

Each fix has regression test and focused commit. Record results and remaining known limits.
