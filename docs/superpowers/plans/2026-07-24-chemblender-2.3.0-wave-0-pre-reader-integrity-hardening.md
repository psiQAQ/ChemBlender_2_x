# ChemBlender 2.3.0 Wave 0 Pre-Reader Integrity Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Follow
> superpowers:test-driven-development for every behavior change and
> superpowers:verification-before-completion before each commit.

**Goal:** Strengthen the canonical sidecar boundary, complete-project graph
validation, parse identity semantics and session persistence state before the
Reader API accepts third-party documents.

**Architecture:** Keep validation in the existing pure-Python core. Decode
canonical tagged objects with exact schemas, reuse `QCProject.commit()` as the
single scientific graph validator, derive parse identity only from
science-affecting inputs, and mark a session clean only after a verified
persistence transition.

**Tech Stack:** Python 3.13, standard-library `dataclasses`, `json`, `hashlib`
and `unittest`; existing `QCProject`, sidecar, import pipeline and project
service modules.

## Global Constraints

- Do not create `ChemBlender/reader_api/` or begin Reader API Task 1.
- Do not change the `.cbq` v0.1/v0.2 wire format.
- Preserve `allow_pickle=False`, lazy memory mapping, SHA-256 validation and
  relative-path containment.
- Do not introduce dependencies or import `bpy`/optional scientific stacks.
- Do not duplicate scientific relationship rules outside `QCProject.commit()`.
- `solidify_session()` remains a low-level storage primitive and must not mark
  a session clean.
- Update `.agents/reference/code-architecture-guide.md` with any changed module
  responsibility in the same implementation commit.

---

### Task 1: Strict sidecar tagged-object decoding

**Files:**
- Modify: `ChemBlender/core/sidecar.py`
- Modify: `tests/test_sidecar_storage.py`

**Interfaces:**
- Preserves: `save_project()`, `open_project()`, `SidecarIntegrityError`
- Strengthens: private canonical tagged-object and array descriptor decoding

- [x] **Step 1: Write strict decoder tests**

Create a valid v0.2 sidecar, mutate `manifest.json`, and recompute its valid
`manifest_sha256`. Cover:

- `$uuid`, `$enum`, `$bytes`, `$tuple`, `$list` and `$dict` exact field sets;
- list payload requirements for tuple/list/dict;
- duplicate decoded dictionary keys;
- multiple tags on one object;
- exact `ArrayData` and `$array` descriptor fields;
- missing array descriptor fields;
- shape entries that are bool, string, float or negative integer;
- object dtype.

All cases must raise `SidecarIntegrityError`, demonstrating decoder rejection
rather than a manifest-hash failure.

- [x] **Step 2: Run the RED test**

Run:

```powershell
& $pythonBin -m unittest tests.test_sidecar_storage -v
```

Record the non-zero exit code and representative accepted-invalid cases.

- [x] **Step 3: Implement the minimum strict decoder**

Require these exact field sets:

```text
$uuid      {"$uuid"}
$enum      {"$enum", "value"}
$bytes     {"$bytes"}
$tuple     {"$tuple"}
$list      {"$list"}
$dict      {"$dict"}
ArrayData  {"$type", "values", "dims", "unit"}
$array     {"$array", "path", "content_sha256", "file_sha256", "shape", "dtype"}
```

Require list payloads, reject duplicate decoded keys, and accept only
non-negative values whose exact type is `int` for array shape entries. Convert
all malformed canonical representations to `SidecarIntegrityError`.

- [x] **Step 4: Run GREEN and regression tests**

Run:

```powershell
& $pythonBin -m unittest tests.test_sidecar_storage -v
```

Confirm v0.1 migration, v0.2 lazy mmap and all path/hash safeguards remain
covered.

---

### Task 2: Full QCProject graph revalidation

**Files:**
- Modify: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/sidecar.py`
- Create: `tests/test_project_graph_integrity.py`
- Modify: `tests/test_sidecar_storage.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Adds private core helper:
  `ChemBlender.core.model.project.validate_project_graph(project) -> None`
- Preserves public `ChemBlender.core` façade

- [x] **Step 1: Write graph-integrity tests**

Tamper valid v0.2 sidecars, recompute a valid manifest hash, and verify
`open_project()` rejects:

- `AtomicProperty.structure_id` referencing no `Structure`;
- `CalculationRecord.dataset_ids` referencing no dataset;
- `Spectrum.source_dataset_id` referencing no dataset or a wrong dataset type;
- `OrbitalSet.basis_set_id` referencing no `BasisSet`;
- `Grid3D.structure_id` referencing no `Structure`.

Also construct an invalid in-memory `QCProject` registry directly and verify
`save_project()` fails before a valid sidecar tree is published.

- [x] **Step 2: Run the RED tests**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_project_graph_integrity `
  tests.test_sidecar_storage -v
```

Record the non-zero exit code and the invalid graphs that were accepted.

- [x] **Step 3: Implement one reusable graph validator**

In `model/project.py`, validate an exact `QCProject` by:

1. constructing an empty project with the same ID and schema version;
2. collecting the original registries into one `ImportBatch`;
3. calling existing `QCProject.commit()` once;
4. calling `commit_calculation_groups()` once;
5. leaving the original project and array values untouched.

Do not reimplement relationship rules and do not export this helper through
`ChemBlender.core`.

Call the helper before sidecar encoding and after sidecar decoding. At the
sidecar boundary convert validation `TypeError`/`ValueError` to
`SidecarIntegrityError`; close a decoded project if validation fails.

- [x] **Step 4: Run GREEN and regression tests**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_project_graph_integrity `
  tests.test_sidecar_storage `
  tests.test_quantum_core -v
```

Update the architecture guide for the strengthened `project.py` and
`sidecar.py` responsibilities.

---

### Task 3: Parse identity semantic correction

**Files:**
- Modify: `ChemBlender/core/import_pipeline/parse.py`
- Modify: `tests/test_import_preflight.py`
- Modify: `tests/test_import_conflicts.py`

**Interfaces:**
- Preserves: `SourcePreview.selected_reader_id`
- Preserves: `SourceRevision.reader_plugin_id`, `reader_id`, `reader_version`
  and `reader_api_version`
- Corrects: `SourceRevision.parse_identity` and `import_parameters_hash`

- [x] **Step 1: Write semantic identity tests**

For the same source bytes, plugin, reader, version, validation mode and source
content state, verify automatic selection and an explicit override selecting
that same reader produce identical parse identities and parameter hashes.
Verify `detect_import_conflicts()` returns `SAME_PARSE_IDENTITY`.

Also verify selecting a genuinely different reader ID changes parse identity.

- [x] **Step 2: Run the RED tests**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_import_preflight `
  tests.test_import_conflicts -v
```

Record the non-zero exit code and identity mismatch.

- [x] **Step 3: Remove selection/deployment metadata from identity**

Keep only parameters that affect scientific parsing:

```text
validation_mode
source_content_state
future reader-specific canonical parameters
```

Remove `reader_override` and `execution_mode`. Plugin ID, reader ID and reader
version remain independent inputs to `source_parse_identity()` and must not be
duplicated in parameter pairs.

- [x] **Step 4: Run GREEN and regression tests**

Run the two focused modules again and confirm different readers remain
distinct.

---

### Task 4: ProjectSession clean/dirty state transition

**Files:**
- Modify: `ChemBlender/core/session.py`
- Modify: `ChemBlender/core/project_service.py`
- Modify: `tests/test_project_session.py`
- Modify: `tests/test_project_service.py`
- Test: `tests/test_project_transaction.py`
- Test: `tests/test_sidecar_publication.py`

**Interfaces:**
- Adds: `ProjectSession.mark_clean() -> None`
- Preserves: `ProjectSession.mark_dirty()` and `clear_dirty()`

- [x] **Step 1: Write persistence-state tests**

Cover:

- import transactions leave the session dirty;
- `solidify_session()` does not clear dirty reasons;
- `save_project_session()` marks clean only after sidecar publication and
  Scene-link write both succeed;
- a Scene-link write failure leaves dirty reasons intact and is not connected;
- successful verify/relink adopts the disk project and marks clean;
- missing/mismatch/incompatible/invalid paths preserve project and dirty
  reasons;
- clearing derived cache does not affect dirty state.

- [x] **Step 2: Run the RED tests**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_project_session `
  tests.test_project_service `
  tests.test_project_transaction `
  tests.test_sidecar_publication -v
```

Record the non-zero exit code and stale dirty state.

- [x] **Step 3: Implement explicit clean transitions**

`mark_clean()` clears every dirty reason. Call it after the complete successful
`save_project_session()` transition and after successful disk-project adoption
used by verify/relink. Do not call it from `solidify_session()`.

- [x] **Step 4: Run GREEN and regression tests**

Run the four focused modules again and verify all failure paths preserve the
prior project and dirty reasons.

---

### Task 5: Full regression, review and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Verify: `tests/fixtures/sidecar/model-v01/README.md`

- [x] **Step 1: Run the focused suite**

```powershell
& $pythonBin -m unittest `
  tests.test_sidecar_storage `
  tests.test_project_graph_integrity `
  tests.test_import_preflight `
  tests.test_import_conflicts `
  tests.test_project_session `
  tests.test_project_service -v
```

- [x] **Step 2: Run the complete regression**

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
& $pythonBin -c @"
import sys
import ChemBlender.core
for name in ("bpy", "cclib", "iodata", "gbasis", "ase", "pymatgen"):
    assert name not in sys.modules, name
"@
git diff --check
git status --short
```

Recompute all seven SHA-256 values listed in
`tests/fixtures/sidecar/model-v01/README.md`.

- [x] **Step 3: Review**

Perform specification-compliance and code-quality reviews. Fix every Critical
or Important finding and rerun the complete verification.

- [x] **Step 4: Commit the implementation**

Stage only files changed by Tasks 1–4 and the architecture guide:

```powershell
git commit -m "fix: harden project import integrity"
```

Do not include the active checkpoint in this implementation commit.

- [x] **Step 5: Record and commit the checkpoint**

Update the active Execution Cursor with the implementation commit, actual RED
and GREEN evidence, fixture verification and:

```text
Blender runtime verification:
Not Run: pure Python integrity hardening
```

Then commit:

```powershell
git commit -m "chore: checkpoint pre-reader integrity hardening"
```

Stop with Reader API Task 1 unstarted and do not push.
