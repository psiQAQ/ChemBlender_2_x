# ChemBlender 2.3.0 Wave 0 Import Transaction and Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build staged imports, detailed diagnostics, duplicate decisions, grouping suggestions and atomic project publication.

**Architecture:** Pure-Python import pipeline modules wrap existing readers. Parsing writes only to a staging session. User decisions convert staged public batches into a single ProjectTransaction. View creation occurs after verified scientific publication.

**Tech Stack:** Python 3.13, dataclasses, concurrent futures only where safe, existing ReaderRegistry/QCProject/sidecar and standard-library `unittest`.

## Global Constraints

- Default validation mode is Balanced Recovery.
- Parser failure must not leave project entities, sidecar generations or Blender objects.
- Batch cancel is atomic.
- Diagnostics distinguish source absence, unsupported reader capability and ambiguous scientific meaning.
- No Blender import in pipeline modules.
- No directory auto-scan.

---

### Task 1: Add quality and detailed diagnostic models

**Files:**
- Create: `ChemBlender/core/model/quality.py`
- Modify: `ChemBlender/core/model/diagnostics.py`
- Modify: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/model/__init__.py`
- Modify: `ChemBlender/core/model_registry.py`
- Modify: `ChemBlender/core/sidecar.py`
- Modify: `ChemBlender/core/sidecar_migrations.py`
- Modify: `ChemBlender/core/__init__.py`
- Create: `tests/test_import_diagnostics.py`
- Modify: `tests/test_model_registry.py`
- Modify: `tests/test_model_public_surface.py`
- Modify: `tests/test_core_public_api.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_sidecar_storage.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `QualityStatus`, `DiagnosticSeverity`, `DiagnosticValue`, `ImportDiagnostic` and project diagnostic registry.

- [ ] **Step 1: Write validation tests**

```python
def test_import_diagnostic_requires_stable_code_and_consequence(self):
    with self.assertRaises(ValueError):
        ImportDiagnostic(
            id=uuid4(), severity=DiagnosticSeverity.WARNING,
            quality_status=QualityStatus.PARTIAL,
            source_revision_id=uuid4(), record_key=None, entity_id=None,
            field_path="atom.charge", code="Invalid Code", message="bad",
            original_value=None, normalized_value=None,
            recovery_action=None, scientific_consequence="", suggested_action=None,
        )
```

Add tests for canonical JSON-safe diagnostic values and quality ordering used for summaries.

- [ ] **Step 2: Implement models**

Diagnostic code uses `[a-z][a-z0-9_.-]*`. `DiagnosticValue` allows None, bool, int, finite float, str and recursively tuples of the same; reject bytes, dict with non-string keys and non-finite numbers.

- [ ] **Step 3: Add legacy ParserIssue conversion**

`diagnostic_from_parser_issue(issue, source_revision_id)` maps existing issues to stable codes prefixed by reader ID while retaining the original message. Existing readers need not change in this task.

- [ ] **Step 4: Run and commit**

Run diagnostics, model registry/public façade, sidecar, documentation and
existing reader tests. Confirm a fresh `ChemBlender.core` import loads neither
`bpy` nor optional scientific stacks. Update the architecture guide in the
same implementation commit, then commit.

### Task 2: Add import request, source preview and staged session types

**Files:**
- Create: `ChemBlender/core/import_pipeline/request.py`
- Create: `ChemBlender/core/import_pipeline/preview.py`
- Create: `ChemBlender/core/import_pipeline/staging.py`
- Create: `ChemBlender/core/import_pipeline/__init__.py`
- Create: `tests/test_import_request_preview.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `ValidationMode`, `ImportSource`, `ReaderOverride`, `ImportRequest`, `SourcePreview`, `ImportPreview`, `StagedImportSession`.

- [ ] **Step 1: Write request validation tests**

Test non-empty source list, unique canonical source paths, no directories, valid recovery mode and reader override targeting an included source.

- [ ] **Step 2: Write staging ownership tests**

A StagedImportSession creates an ownership marker, artifact root and result registry. `discard()` removes only its owned root and is idempotent.

- [ ] **Step 3: Implement immutable preview types**

A Preview contains source rows, staged batch IDs, conflict IDs, grouping suggestion IDs, diagnostics and view plan IDs. It does not contain Blender objects or mutable QCProject references.

- [ ] **Step 4: Run and commit**

Run import request/preview, path safety and documentation-contract tests.
Confirm a fresh `ChemBlender.core.import_pipeline` import loads neither `bpy`
nor optional scientific stacks. Update the architecture guide for every new
source module in the same implementation commit.

### Task 3: Implement reader preflight and staged parse for existing readers

**Files:**
- Create: `ChemBlender/core/import_pipeline/preflight.py`
- Create: `ChemBlender/core/import_pipeline/parse.py`
- Modify: `ChemBlender/core/import_pipeline/__init__.py`
- Modify: `ChemBlender/core/readers.py`
- Create: `tests/test_import_preflight.py`
- Modify: `tests/test_import_request_preview.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_quantum_readers.py`
- Test: `tests/test_xyz_reader.py`
- Test: `tests/test_cube_reader.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `preflight_import(request, registry, session) -> ImportPreview`.

- [ ] **Step 1: Add availability-aware reader descriptor fields through a compatibility wrapper**

Do not break existing ReaderDescriptor constructors yet. Create `ReaderRuntimeDescriptor` containing the existing descriptor plus plugin ID, API version, execution mode and an availability callable.

- [ ] **Step 2: Write XYZ/Cube preview tests**

For valid fixtures, assert selected reader, capabilities, source hash, byte size, staged batch and zero blocking diagnostics. For an optional unavailable fake reader, assert Preview reports dependency unavailable before parse.

- [ ] **Step 3: Implement bounded preflight**

Hash files in chunks, use existing sniff prefix bound, call parse into staging, wrap ParserIssues as diagnostics and never commit. Expected parse exceptions become Invalid diagnostics with stable codes.

- [ ] **Step 4: Add progress callbacks**

The pure function accepts `progress(stage, completed, total)` and `is_cancelled()` callables. Cancellation raises a typed `ImportCancelled` caught by the caller, which discards staging.

- [ ] **Step 5: Run and commit**

Run existing reader selection, XYZ/Cube, request/preview, preflight and
documentation-contract tests. Confirm the expanded import-pipeline package
still imports without `bpy` or optional scientific stacks. Update the
architecture guide for the two new modules and the changed `readers.py`
responsibility in the same implementation commit.

### Task 4: Implement duplicate and revision conflict analysis

**Files:**
- Create: `ChemBlender/core/import_pipeline/conflicts.py`
- Modify: `ChemBlender/core/import_pipeline/__init__.py`
- Create: `tests/test_import_conflicts.py`
- Modify: `tests/test_import_request_preview.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_import_preflight.py`
- Test: `tests/test_source_model.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `ImportConflict`, `DuplicateAction`, `detect_import_conflicts()` and `apply_conflict_decisions()`.

- [ ] **Step 1: Write three conflict category tests**

Use projects containing SourceRevision records to test:

- same parse identity;
- same normalized locator with different content;
- same content with different locator.

Assert defaults Reuse Existing, New Revision and Link Existing respectively.

- [ ] **Step 2: Implement conflict detection**

Comparison uses parse identity, content hash and normalized locator. Do not use mtime as identity.

- [ ] **Step 3: Implement decisions**

Each decision produces a new immutable preview. Reuse references existing entities; Independent Copy assigns new project entity IDs only during transaction; Ignore removes the staged source from confirmed input.

- [ ] **Step 4: Run and commit**

Run conflict, source model, preflight/request and transaction-precursor tests,
plus the documentation contract. Confirm the expanded import-pipeline package
still imports without `bpy` or optional scientific stacks. Update the package
exports and architecture guide in the same implementation commit.

### Task 5: Implement evidence-driven grouping suggestions

**Files:**
- Create: `ChemBlender/core/import_pipeline/grouping.py`
- Modify: `ChemBlender/core/import_pipeline/__init__.py`
- Create: `tests/test_source_grouping.py`
- Modify: `tests/test_import_request_preview.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_import_preflight.py`
- Test: `tests/test_import_conflicts.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `GroupingEvidence`, `SourceGroupSuggestion`, `CalculationGroup`, `suggest_source_groups()`.
- `suggest_source_groups(preview, session)` reads immutable source rows and their staged `ImportBatch` values and returns immutable suggestions without mutating the preview, staging session or a project.
- Confirming a `SourceGroupSuggestion` produces a new `CalculationGroup` with the selected evidence IDs and `confirmed_by="user"`; a suggestion is never promoted to scientific fact implicitly.

- [ ] **Step 1: Write evidence score tests**

Assert explicit internal reference > exact mapped structure > Kabsch RMSD > metadata > filename/directory. Time alone cannot produce High confidence.

- [ ] **Step 2: Implement molecular structure signatures**

Compute composition and centered-distance signatures without changing coordinates. Exact atom mapping uses atomic numbers and topology when available. Kabsch alignment is optional only when NumPy is available, which it is in Blender; keep the module pure from `bpy`.

- [ ] **Step 3: Implement periodic signatures**

Use cell metric tensor, composition and fractional coordinates modulo periodicity. Do not claim primitive/conventional equivalence without optional symmetry support; report it as a conflict requiring user review.

- [ ] **Step 4: Implement user confirmation**

Suggestions are not stored as CalculationGroup until confirmed. The confirmed group records evidence IDs and `confirmed_by="user"`.

- [ ] **Step 5: Run and commit**

Run grouping tests with exact, near, periodic-conflict and filename-only cases,
plus request/preview, preflight, conflict and documentation-contract tests.
Confirm the expanded package imports without `bpy` or optional scientific
stacks. Update package exports and the architecture guide in the same
implementation commit.

### Task 6: Implement ProjectTransaction

**Files:**
- Create: `ChemBlender/core/model/grouping.py`
- Modify: `ChemBlender/core/model/__init__.py`
- Modify: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/model_registry.py`
- Modify: `ChemBlender/core/sidecar_migrations.py`
- Modify: `ChemBlender/core/__init__.py`
- Create: `ChemBlender/core/import_pipeline/transaction.py`
- Modify: `ChemBlender/core/import_pipeline/grouping.py`
- Modify: `ChemBlender/core/import_pipeline/__init__.py`
- Modify: `ChemBlender/core/session.py`
- Create: `tests/test_project_transaction.py`
- Modify: `tests/test_source_grouping.py`
- Modify: `tests/test_import_request_preview.py`
- Modify: `tests/test_model_public_surface.py`
- Modify: `tests/test_model_registry.py`
- Modify: `tests/test_quantum_core.py`
- Modify: `tests/test_sidecar_storage.py`
- Test: `tests/test_import_conflicts.py`
- Test: `tests/test_sidecar_publication.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `GroupingDecision`, `ImportCommitDecisions`, `ImportCommitResult` and
  `commit_import_preview(project_session, staged_session, preview, decisions)
  -> ImportCommitResult`.
- `GroupingDecision` carries the complete immutable `SourceGroupSuggestion`
  snapshot plus selected evidence IDs. The transaction recomputes suggestions
  from the live staging session and requires complete object equality before
  confirmation; UUID equality alone is insufficient.
- `CalculationGroup` is a model entity stored in
  `QCProject.calculation_groups` and serialized in `.cbq`. The import-pipeline
  façade continues to re-export it for compatibility.
- Adding the empty `calculation_groups` registry does not change the current
  `0.2` manifest or project schema version. Migration must add the missing
  registry when opening existing `0.2` documents and the committed `0.1`
  fixture.

- [ ] **Step 1: Write atomic failure tests**

Create two staged batches, make the second contain a dangling reference, and
assert no source/entity/diagnostic/group from either is committed, the live
project object and session dirty state are unchanged, and no temporary sidecar
is published.

- [ ] **Step 2: Write success tests**

Assert source records, revisions, diagnostics, entities and confirmed groups
are committed, session is dirty, and the temporary sidecar can reopen with the
same concrete entities and confirmed groups. Existing `0.2` sidecars and the
committed `0.1` fixture must reopen with an empty `calculation_groups`
registry.

- [ ] **Step 3: Implement transaction assembly**

Resolve conflicts against the live `QCProject` and staging session, allocate
new IDs where required, merge batches, recompute and validate complete grouping
suggestions, and validate through a copy of `QCProject`. Publish that candidate
to the current session sidecar, or to a controlled temporary `.cbq` beneath the
session root when the session has not yet been solidified. Reopen the published
sidecar and only then replace the live session project and mark it dirty.
Neither validation nor a failed publication may mutate the live project,
session dirty state, or sidecar locator.

- [ ] **Step 4: Add view failure status contract**

The pure transaction does not create views. It returns the immutable default
view plan IDs and a committed project state. Blender caller handles view
application and reports data committed/view failed separately.

- [ ] **Step 5: Run and commit**

Run transaction, project, sidecar storage/publication, conflict, grouping,
public façade, registry and documentation-contract tests. Confirm
`ChemBlender.core.import_pipeline` remains importable without `bpy` or optional
scientific stacks. Update the architecture guide in the same implementation
commit for the new model and transaction modules.

### Task 7: Add deterministic diagnostic summaries and exports

**Files:**
- Create: `ChemBlender/core/import_pipeline/report.py`
- Create: `tests/test_import_report.py`
- Create: `docs/quantum-visualization/2.3.0/specs/import-report-v1.md`

**Interfaces:**
- Produces: `import_summary()`, `diagnostics_document()` and `render_diagnostics_markdown()`.

- [ ] **Step 1: Write stable-order tests**

Input diagnostics in reversed orders and assert identical canonical JSON and Markdown sorted by severity, source, record, field and code.

- [ ] **Step 2: Implement summary counts**

Return counts for Complete, Partial, Ambiguous, Incomplete and Invalid by source and entity. Invalid staged entities not committed still appear in import report.

- [ ] **Step 3: Verify and commit**

Run report and canonical JSON tests, update architecture guide and commit.
