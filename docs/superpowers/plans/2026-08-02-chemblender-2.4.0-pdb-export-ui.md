# ChemBlender 2.4.0 PDB Export UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` task by task.

**Goal:** Expose the completed native PDB core exporter through the existing
Project Browser export workflow with selected-entity projection, explicit loss
confirmation, background cancellation and installed Blender re-import proof.

**Architecture:** Extend only the existing `ChemBlender.ui.export` selection,
format table, preview dispatcher and `ExportJob`. Project the selected
Structure, its BiologicalHierarchy, related datasets and optional topology into
the attribute collection expected by the core PDB writer. Reuse the existing
operator, RNA, registration root and worker lifecycle. No new operator.

**Tech Stack:** Python 3.13, standard-library `dataclasses`,
`types.SimpleNamespace` and `unittest`, existing ChemBlender PDB core exporter,
Blender 5.1.2 Extensions.

## Global constraints

- Start only after `.agents/queued/2.4.0-pdb-export-ui.md` is explicitly
  activated.
- Baseline is the completed Task 4 Scope Discovery checkpoint, itself based on
  merge commit `79a93f52053fdf809c28c24800366010577a1984`.
- Preserve the model, sidecar schema, Reader API token and dependency set.
- Reuse `CHEMBLENDER_OT_export_project_entity`; add no class, registration root,
  RNA collection or second export lifecycle.
- Do not extend the core PDB record set or implement PQR/Cube export.
- Do not change manifest version, CHANGELOG release version, tag or Release.

### Task 1: Activate and persist the implementation boundary

**Files:**
- Move: `.agents/queued/2.4.0-pdb-export-ui.md`
- Create: `.agents/active/2.4.0-pdb-export-ui.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Persist goal `CB240-PDB-EXPORT-UI-T4`; no runtime change.

- [x] Add the routing/documentation RED.
- [x] Activate the queued cursor and record approved plan/baseline.
- [x] Run focused documentation GREEN and commit the activation checkpoint.

### Task 2: Project exactly one PDB export selection

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `tests/test_extxyz_workflow.py`

**Interfaces:** `ExportSelection` gains immutable
`biological_hierarchies: tuple = ()` and
`associated_topologies: tuple = ()` fields. A private
`_pdb_entities(selection)` returns a `SimpleNamespace` with `structures`,
`biological_hierarchies`, `datasets`, `topologies`, `sources=()` and
`source_revisions=()` for the single selected Structure. `datasets` contains
`selection.frame_set` when present plus exact Structure-bound properties,
deduplicated by entity ID; `topologies` contains every topology associated with
the exact Structure, including ambiguous CONECT records needed by loss preview.
The generic singular `selection.topology` remains complete-only for molecular
writers. Unrelated entities are excluded. Source ordering metadata is
unnecessary for one output Structure.

- [x] **RED:** prove a PDB fixture selection cannot currently project its
  BiologicalHierarchy into the core writer contract.
- [x] **Expected RED:** selection lacks the hierarchy field/helper and PDB
  readiness reports `MissingHierarchy`.
- [x] Project every hierarchy with the exact selected `structure_id` (normally
  zero or one); preserve absence or ambiguity for fail-closed core readiness
  rather than picking by order.
- [x] Include `selection.frame_set` when present plus only properties bound to
  the selected Structure, deduplicate by entity ID, and project all exact
  Structure-associated topologies for PDB loss reporting without changing the
  molecular complete-topology selection; exclude unrelated project entities.
- [x] Prove a FrameSet selection emits all `MODEL` blocks with no duplicate base frame.
- [x] Prove generic XYZ/crystal/molecular selection behavior does not regress.
- [x] Run selection-focused workflow and PDB readiness tests.

### Task 3: Add PDB choice, preview and explicit confirmation

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `tests/test_extxyz_workflow.py`

**Interfaces:** Add `pdb` to `_FORMAT_ITEMS`, `*.pdb` to `filter_glob`, and
delegate `preview_export_selection(selection, "pdb")` to
`preview_pdb_export(_pdb_entities(selection))`.

- [x] **RED:** prove the enum/filter omit PDB and preview reaches the unsupported
  format branch.
- [x] Add one explicit format choice; do not infer PDB from source bytes or
  change the current default-format heuristic.
- [x] Prove preview returns the core loss entries unchanged, writes nothing and
  blocks job start until the exact bool confirmation is set.
- [x] Prove missing/ambiguous hierarchy and invalid live arrays fail closed.
- [x] Run preview/operator-focused workflow tests.

### Task 4: Dispatch background atomic PDB export

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `tests/test_extxyz_workflow.py`

**Interfaces:** `ExportJob._run()` delegates PDB to
`export_pdb(_pdb_entities(selection), confirm_loss=..., destination=...,
is_cancelled=...)` and stores the returned report.

- [x] **RED:** prove `ExportJob(format_name="pdb")` with a valid destination
  currently reaches the unsupported-format branch and produces no file.
- [x] Add one dispatch branch and update only the shared allowed-format error.
- [x] Prove loss-bearing output is blocked without confirmation and succeeds
  with it.
- [x] Prove cancellation/failure leaves an existing destination byte-identical
  and no sibling temporary file.
- [x] Prove fatal exceptions remain unwrapped and UI timer/progress ownership is
  released once.
- [x] Run workflow, PDB exporter and registration contract tests.
- [x] Commit the runtime slice as `feat: add native PDB export UI`.

### Task 5: Publish and prove the product capability

**Files:**
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `docs/quantum-visualization/reader-capability-matrix.json`
- Modify: `docs/user/format-capabilities.json`
- Modify: `docs/user/formats.md`
- Modify: `tests/test_generated_docs_fresh.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:** Change PDB export execution mode from `core` to
`project_browser`; maturity/loss policy remain `F5 / preview_confirmation`.

- [x] **RED:** generated-document contract still reports PDB as core-only.
- [x] Update the catalog source once, regenerate/check canonical user documents,
  and avoid hand-maintained divergent capability claims.
- [x] Extend the existing biological/PDB installed smoke: select the imported
  Structure, preview loss, run `ExportJob`, parse with native `parse_pdb()` and
  compare representable structure/hierarchy/frame/property semantics.
- [x] Prove register/unregister/reload x2 without new classes or RNA growth.
- [x] Commit capability/product proof with the implementation or one focused
  follow-up commit.

### Task 6: Full qualification, reviews and checkpoint

**Files:**
- Modify only in-scope files required by findings.
- Modify: `.agents/active/2.4.0-pdb-export-ui.md`
- Modify: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-pdb-export-ui.md`

**Interfaces:** No public model/API addition. Completion evidence is persisted
in the cursor.

- [ ] Run focused export/PDB/registration/generated-doc tests.
- [ ] Run full unittest discovery, `compileall`, optional-import audit and
  `git diff --check`.
- [ ] Run Blender 5.1.2 preflight, validate/build, ZIP audit, isolated install,
  PDB export/re-import and lifecycle smoke.
- [ ] Run independent specification and code-quality reviews; fix all Critical,
  Important and task-related Minor findings and rerun affected checks.
- [ ] Record RED/GREEN/Blender/review evidence and commit the checkpoint.

### Task 7: Remote integration gate

**Files:**
- Modify only the active cursor when exact remote evidence must be persisted.

**Interfaces:** Only the exact pushed head is valid CI evidence; integration is
an ordinary merge commit.

- [ ] Push normally and create a ready PDB UI PR to `main`.
- [ ] Wait for required `extension-package` and `optional-qc-core` checks whose
  `headSha` equals the exact feature head.
- [ ] Diagnose any failure minimally; every new head invalidates prior CI.
- [ ] Merge by ordinary merge commit only after exact-head CI and independent
  review are Ready.
- [ ] Fetch and prove the exact head is an ancestor of `origin/main`; do not
  rebase, force-push, delete branches, tag or release.

## Stop boundary

Complete only PDB Export UI and its integration gate. Native PQR export, native
Cube export, Reader API stable, dependency/schema/version and Release work stay
unstarted.
