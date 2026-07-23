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
- Modify: `ChemBlender/core/model_registry.py`
- Create: `tests/test_import_diagnostics.py`

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

Run diagnostics, sidecar and existing reader tests, then commit.

### Task 2: Add import request, source preview and staged session types

**Files:**
- Create: `ChemBlender/core/import_pipeline/request.py`
- Create: `ChemBlender/core/import_pipeline/preview.py`
- Create: `ChemBlender/core/import_pipeline/staging.py`
- Create: `ChemBlender/core/import_pipeline/__init__.py`
- Create: `tests/test_import_request_preview.py`

**Interfaces:**
- Produces: `ValidationMode`, `ImportSource`, `ReaderOverride`, `ImportRequest`, `SourcePreview`, `ImportPreview`, `StagedImportSession`.

- [ ] **Step 1: Write request validation tests**

Test non-empty source list, unique canonical source paths, no directories, valid recovery mode and reader override targeting an included source.

- [ ] **Step 2: Write staging ownership tests**

A StagedImportSession creates an ownership marker, artifact root and result registry. `discard()` removes only its owned root and is idempotent.

- [ ] **Step 3: Implement immutable preview types**

A Preview contains source rows, staged batch IDs, conflict IDs, grouping suggestion IDs, diagnostics and view plan IDs. It does not contain Blender objects or mutable QCProject references.

- [ ] **Step 4: Run and commit**

Run import request/preview and path safety tests.

### Task 3: Implement reader preflight and staged parse for existing readers

**Files:**
- Create: `ChemBlender/core/import_pipeline/preflight.py`
- Create: `ChemBlender/core/import_pipeline/parse.py`
- Modify: `ChemBlender/core/readers.py`
- Create: `tests/test_import_preflight.py`

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

Run existing reader selection tests plus new preflight tests.

### Task 4: Implement duplicate and revision conflict analysis

**Files:**
- Create: `ChemBlender/core/import_pipeline/conflicts.py`
- Create: `tests/test_import_conflicts.py`

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

Run conflict, source model and transaction precursor tests.

### Task 5: Implement evidence-driven grouping suggestions

**Files:**
- Create: `ChemBlender/core/import_pipeline/grouping.py`
- Create: `tests/test_source_grouping.py`

**Interfaces:**
- Produces: `GroupingEvidence`, `SourceGroupSuggestion`, `CalculationGroup`, `suggest_source_groups()`.

- [ ] **Step 1: Write evidence score tests**

Assert explicit internal reference > exact mapped structure > Kabsch RMSD > metadata > filename/directory. Time alone cannot produce High confidence.

- [ ] **Step 2: Implement molecular structure signatures**

Compute composition and centered-distance signatures without changing coordinates. Exact atom mapping uses atomic numbers and topology when available. Kabsch alignment is optional only when NumPy is available, which it is in Blender; keep the module pure from `bpy`.

- [ ] **Step 3: Implement periodic signatures**

Use cell metric tensor, composition and fractional coordinates modulo periodicity. Do not claim primitive/conventional equivalence without optional symmetry support; report it as a conflict requiring user review.

- [ ] **Step 4: Implement user confirmation**

Suggestions are not stored as CalculationGroup until confirmed. The confirmed group records evidence IDs and `confirmed_by="user"`.

- [ ] **Step 5: Run and commit**

Run grouping tests with exact, near, conflict and filename-only cases.

### Task 6: Implement ProjectTransaction

**Files:**
- Create: `ChemBlender/core/import_pipeline/transaction.py`
- Modify: `ChemBlender/core/session.py`
- Create: `tests/test_project_transaction.py`

**Interfaces:**
- Produces: `commit_import_preview(session, preview, decisions) -> ImportCommitResult`.

- [ ] **Step 1: Write atomic failure tests**

Create two staged batches, make the second contain a dangling reference, and assert no source/entity/diagnostic from either is committed and session dirty state is unchanged.

- [ ] **Step 2: Write success tests**

Assert source records, revisions, diagnostics, entities and confirmed groups are committed, session is dirty, and the temporary sidecar can reopen.

- [ ] **Step 3: Implement transaction assembly**

Resolve conflicts, allocate new IDs where required, merge batches, create source/revision entities, validate through a copy of QCProject, publish the session sidecar, reopen and only then replace the live session project.

- [ ] **Step 4: Add view failure status contract**

The pure transaction does not create views. It returns default view plans and a committed project state. Blender caller handles view application and reports data committed/view failed separately.

- [ ] **Step 5: Run and commit**

Run transaction, project, sidecar, conflict and grouping tests.

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
