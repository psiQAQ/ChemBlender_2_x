# ChemBlender 2.3.0 Wave 1 Topology Final Conformance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the immediate-topology, explicit-registration, canonical-edge and periodic representation gaps before starting Native XYZ/extXYZ, and correct the extXYZ implementation plan so its later runtime work has complete model, streaming and registration contracts.

**Architecture:** Built-in readers publish first-class `TopologyRecord` entities immediately. The immutable model rejects non-canonical graph payloads while producers normalize before construction. Periodic inference derives its authoritative fractional coordinates from Cartesian coordinates and wraps only enabled PBC axes. Blender registration remains an explicit root list, and this gate changes only the future extXYZ plan—not its runtime.

**Tech Stack:** Python 3.13 standard library, NumPy from Blender 5.1.2, existing `ImportBatch`/`QCProject`/sidecar and Blender registration contracts, `unittest`.

## Global Constraints

- Do not create `ChemBlender/core/formats/extxyz.py` or `ChemBlender/ui/export.py` in this gate.
- Do not start Native XYZ/extXYZ runtime, RDKit MOL/SDF/SMILES or Cube UX.
- Do not change manifest version, tag, Release, dependencies or remotes.
- Preserve v0.1/v0.2 embedded-topology migration and current CJSON envelope export.
- Keep `ChemBlender/core/` importable without `bpy`.
- Use TDD: record a real RED before each runtime change and run focused GREEN before commit.
- No push until the Native XYZ/extXYZ goal is fully complete and explicitly authorized by the user.

## Reviewed Baseline Evidence

`main..HEAD` contains nine linear commits:

1. `cb8fc02` — activate ChemBlender 2.3.0 Wave 1.
2. `8b989ce` — start the topology implementation plan.
3. `6b1051e` — add versioned topology records.
4. `a8719e8` — infer nonperiodic structure topology.
5. `3136152` — infer periodic topology images.
6. `e82ca5b` — build topology-aware structure views.
7. `8cc86a2` — add topology selection workflow.
8. `2e8274e` — derive structures from scientific edits.
9. `16d8dc2` — checkpoint the topology/structure-view plan.

The three commits outside the six product Tasks are the Wave 1 activation, plan/cursor activation and final checkpoint. Reviewed local/remote HEAD is `16d8dc25e7343b4b1e647ae188bb9a281a145433`; fresh baseline is `Ran 1049 tests, 28 skipped, 0 failed`.

---

### Task 1: Immediate explicit-topology normalization

**Files:**
- Modify: `ChemBlender/core/cjson_adapter.py`
- Modify: `tests/test_cjson_adapter.py`
- Modify: `tests/test_topology_record.py`
- Test: existing sidecar migration and Structure View contracts

**Interfaces:**
- Consumes: CJSON `bonds.connections.index`, `bonds.order`, parser source SHA-256 and parser provenance.
- Produces: `Structure(topology=None, topology_ids=(topology.id,))`, `ImportBatch.topologies=(topology,)`, complete `ParserReport.created_entity_ids`.

- [x] **Step 1: Write and run RED tests**

Add tests proving `parse_cjson()` immediately returns one deterministic `TopologyRecord`, `QCProject.commit()` exposes it to `topology_choices()`, `_structure_view_data()` accepts it, and report IDs exactly match all entities. Run:

```powershell
& $pythonBin -m unittest tests.test_cjson_adapter tests.test_topology_record -v
```

**Expected RED:** the batch has no topology record, the Structure still embeds `MolecularTopology`, and report IDs omit topology identity.

- [x] **Step 2: Implement the minimal reader normalization**

Canonicalize CJSON endpoints/orders before construction; derive revision and UUID from adapter version, source hash and canonical arrays; create `TopologyRecord` with `EXPLICIT_FILE`, `COMPLETE`, empty stereo labels and parser provenance. Keep the raw envelope unchanged.

- [x] **Step 3: Verify compatibility**

Run CJSON, topology, project, sidecar migration and Structure View tests. Confirm legacy v0.1/v0.2 embedded topology still migrates and CJSON envelope bytes export unchanged.

**Blender verification:** final product smoke imports CJSON without save/reopen, lists explicit topology and builds a Structure View.

**Commit boundary:** fold into `fix: close topology and extXYZ preflight contracts`.

**Stop boundary:** do not add or modify extXYZ runtime.

### Task 2: Explicit UI registration roots

**Files:**
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `ChemBlender/ui/project_browser/panel.py`
- Modify: `tests/test_registration_contract.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Consumes: `REGISTER_MODULE_NAMES`, `auto_load.get_ordered_classes_to_register()`.
- Produces: `.ui.topology` and `.ui.scientific_edit` as exact registration roots without class re-export through the Project Browser module.

- [x] **Step 1: Write and run RED tests**

Assert both roots are present, every discovered Blender class belongs to its declared root, panel exposes no imported topology/scientific-edit classes, and the existing atomic callback rollback harness still succeeds.

```powershell
& $pythonBin -m unittest tests.test_registration_contract tests.test_project_browser_model -v
```

**Expected RED:** the two roots are absent and panel re-exports their Blender classes.

- [x] **Step 2: Implement root ownership**

Add the two root names and import their modules in panel via private module aliases. Keep `Scene.chemblender_topology` property ownership in panel and reference its type through the alias.

- [x] **Step 3: Verify lifecycle**

Run registration, Project Browser and Blender lifecycle tests, including partial registration failure and register/unregister/reload twice. Verify optional scientific stacks are not imported.

**Blender verification:** class inventory includes topology/scientific-edit classes once under their own modules; Scene topology property is created and removed by the existing owner.

**Commit boundary:** fold into the gate implementation commit.

**Stop boundary:** do not add a second registration path.

### Task 3: Canonical TopologyRecord edge contract

**Files:**
- Modify: `ChemBlender/core/model/molecular_topology.py`
- Modify: `ChemBlender/core/model/project.py` only if graph-level reference validation needs adjustment
- Modify: `ChemBlender/core/cjson_adapter.py`
- Modify: `ChemBlender/core/topology/periodic.py`
- Modify: `ChemBlender/core/edits/structure.py` if its producer requires canonicalization
- Modify: `ChemBlender/core/sidecar_migrations.py` if legacy payloads need producer-side normalization
- Modify: `tests/test_topology_record.py`
- Modify: `tests/test_periodic_topology_inference.py`
- Modify: `tests/test_cjson_adapter.py`

**Interfaces:**
- Produces: one canonical edge key `(left, right, lattice_shift)` where absent shift equals `(0,0,0)`.
- Producer rule: reverse `left > right` and negate shift; self-image first nonzero shift is positive; sort all parallel bond fields by the same key.
- Model rule: reject reversed/non-canonical edges, zero-shift self edges and exact/reversed duplicates; continue accepting `bond_order=0.0`.

- [x] **Step 1: Write and run RED tests**

Add literal cases for reversed zero-shift edge, exact/reversed duplicate, zero-shift self edge, reversed periodic edge and reversed self-image. Include accepted canonical periodic/self-image and zero bond order.

```powershell
& $pythonBin -m unittest tests.test_topology_record tests.test_periodic_topology_inference tests.test_cjson_adapter -v
```

**Expected RED:** current `TopologyRecord` accepts malformed graph payloads.

- [x] **Step 2: Implement one shared canonicalizer and strict model validation**

Reuse one pure helper from the model boundary in CJSON, periodic inference, scientific-edit producer and legacy migration as required. The frozen model validates only; it never silently reorders its arrays.

- [x] **Step 3: Verify graph compatibility**

Run model, reader, migration, sidecar, inference and Structure View tests. Confirm all parallel arrays keep the same sorted permutation.

**Blender verification:** explicit and inferred topology views still construct and switch successfully.

**Commit boundary:** fold into the gate implementation commit.

**Stop boundary:** no new topology source kind or schema version.

### Task 4: Periodic representation invariance

**Files:**
- Modify: `ChemBlender/core/topology/periodic.py`
- Modify: `tests/test_periodic_topology_inference.py`
- Modify: `ChemBlender/scripts/benchmark_topology.py` only if recorded parameters/output require the new strategy

**Interfaces:**
- Consumes: Cartesian coordinates, cell and `PeriodicSiteData.pbc`.
- Produces: fractional search coordinates normalized with `fractional[:, axis] -= floor(fractional[:, axis])` only where `pbc[axis]` is true, plus an explicit inference parameter naming the normalization strategy.

- [x] **Step 1: Write and run RED tests**

Cover whole-structure integer translation, one atom moved by more than one cell, skew cell, partial PBC, self-image and canonical shifts. Assert exact topology identity for physically equivalent PBC representations.

```powershell
& $pythonBin -m unittest tests.test_periodic_topology_inference -v
```

**Expected RED:** a single atom unwrapped by multiple cells loses its edge or changes identity.

- [x] **Step 2: Implement Cartesian-authoritative PBC wrapping**

Compute fractional values only from Cartesian coordinates and cell; wrap enabled axes, preserve non-periodic axes, then rebuild Cartesian search coordinates. Record `fractional_normalization=cartesian_pbc_modulo_one`.

- [x] **Step 3: Verify performance**

Run periodic/nonperiodic focused tests and topology benchmark. Compare median/p95 and scaling with the recorded Wave 1 budget.

**Blender verification:** smoke creates and displays topology for an unwrapped periodic structure.

**Commit boundary:** fold into the gate implementation commit.

**Stop boundary:** do not redefine stored `PeriodicSiteData` coordinates.

### Task 5: Correct the Native XYZ/extXYZ implementation plan

**Files:**
- Modify: `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-1-extxyz.md`
- Modify: `tests/test_quantum_visualization_docs.py` only for executable plan/document coverage

**Interfaces:**
- Produces: complete contracts for frame validity masks, typed metadata/raw lexemes, exact lattice vector order and PBC defaults, package creation, explicit export UI registration, bounded staging/cancellation and compatibility fixtures.

- [x] **Step 1: Amend Task 1 model contract**

Define boolean dimensionless validity masks with exact prefixes: `FrameProperty ("frame",)`, `AtomFrameProperty ("frame","atom")`, `CellFrameProperty ("frame",)`. Define categorical integer codes, unique categories and explicit missing code.

- [x] **Step 2: Amend parser/mapping contracts**

Add `ChemBlender/core/formats/__init__.py`; preserve string/integer/real/logical/1-D/2-D per-config values plus raw lexeme/diagnostic when safe typing fails; require exact lattice sequence `ax ay az bx by bz cx cy cz`; set PBC defaults to false without Lattice and true with Lattice unless explicitly overridden.

- [x] **Step 3: Amend UI and scale contracts**

Make `ui.export` an explicit registration root and list registration/document tests. Require bounded frame iterator, staged memmap/NPY owner, cancellation cleanup, publication rollback and no all-frame nested tuple. Add libAtoms/ASE/OVITO-compatible fixtures without an ASE runtime dependency.

- [x] **Step 4: Verify the plan**

Run documentation contracts and self-review for missing placeholders, type/name consistency and all eight requested corrections.

**Blender verification:** Not Run for plan-only changes; later Task 5 owns export UI runtime smoke.

**Commit boundary:** fold into the gate implementation commit.

**Stop boundary:** plan changes only; do not create extXYZ or export modules.

### Task 6: Full verification and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-1-native-molecular-and-grid.md`
- Modify: this plan

**Interfaces:**
- Produces: completed conformance cursor with planning/implementation/review/checkpoint SHAs and exact local evidence.

- [x] **Step 1: Run focused and full verification**

```powershell
& $pythonBin -m unittest `
  tests.test_topology_record `
  tests.test_topology_inference `
  tests.test_periodic_topology_inference `
  tests.test_cjson_adapter `
  tests.test_registration_contract `
  tests.test_topology_ui_contract `
  tests.test_structure_view_contract `
  tests.test_quantum_visualization_docs -v
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
```

- [x] **Step 2: Run Blender 5.1.2 product regression**

Run native validate/build, ZIP audit, isolated install, two lifecycle loops, immediate CJSON topology/UI/Structure View, unwrapped periodic topology and scientific-edit regression.

- [x] **Step 3: Perform two independent reviews**

Run specification-compliance and code-quality reviews. Fix all Critical, Important and gate-related Minor findings, then re-run covering and full verification.

- [x] **Step 4: Commit and checkpoint**

Commit runtime/test/plan changes as `fix: close topology and extXYZ preflight contracts`; update cursor with exact evidence and commit `chore: checkpoint topology final conformance`.

**Blender verification:** all required smoke paths Passed.

**Commit boundary:** checkpoint commit contains only cursor/plan completion evidence.

**Stop boundary:** Native XYZ/extXYZ runtime remains unstarted after this gate.
