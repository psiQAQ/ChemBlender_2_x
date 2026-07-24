# ChemBlender 2.3.0 Wave 0 Reader API Task 1 Final Conformance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze Reader API Task 1 metadata values by returning canonical string execution modes, rejecting multiple leading extension dots, and routing license normalization through one shared helper.

**Architecture:** Keep the existing public `ReaderAvailability` class and manifest dataclasses. Apply the smallest corrections at the two shared normalization boundaries in `descriptors.py` and `manifest.py`; no new public type, dependency, or Reader API Task 2 source is introduced.

**Tech Stack:** Python 3.13 standard library (`dataclasses`, `enum`, `importlib`, `re`, `tomllib`, `unittest`) and existing ChemBlender Reader API contracts.

## Global Constraints

- Work only on `feat/2.3.0-wave0-platform-foundation`.
- Reviewed baseline is `dfd38ef1f40b73d938d797df0254fcf36885eae4`.
- Do not modify `ChemBlender/core/readers.py`.
- Do not create `ChemBlender/reader_api/public_model.py`, `ChemBlender/reader_api/builtin_bridge.py`, or `ChemBlender/reader_api/canonical_document.py`.
- Do not begin Reader API Task 2, Registration/UI, or Wave 1–4.
- Do not add or install dependencies.
- Keep `ChemBlender.reader_api` importable without `bpy` or optional scientific stacks.
- Use one implementation commit and one separate completion checkpoint.
- Do not push without a new explicit user authorization.

---

### Task 1: Canonical availability execution mode

**Files:**
- Modify: `ChemBlender/reader_api/descriptors.py`
- Test: `tests/test_reader_plugin_manifest.py`

**Interfaces:**
- Consumes: `ExecutionMode` or its accepted string value.
- Produces: `ReaderAvailability.execution_mode` as exact `str` for every `_probe_availability()` outcome.

- [ ] **Step 1: Write failing probe tests**

Cover available, dependency-missing, and dependency-probe-failed outcomes:

```python
self.assertIs(type(result.execution_mode), str)
self.assertEqual(result.execution_mode, "extension")
```

Add a descriptor boundary test proving that a `ReaderAvailability` whose
`execution_mode` is an `ExecutionMode` instance is rejected with `TypeError`.

- [ ] **Step 2: Run RED**

```powershell
& $pythonBin -m unittest tests.test_reader_plugin_manifest -v
```

Expected: failures show `_probe_availability()` returns `ExecutionMode`, and
`PublicReaderDescriptor` accepts that non-canonical concrete type.

- [ ] **Step 3: Implement the minimum correction**

In `_probe_availability()` derive:

```python
mode = ExecutionMode(execution_mode)
mode_value = mode.value
```

Pass `mode_value` to all three `ReaderAvailability` results. In
`PublicReaderDescriptor.__post_init__()`, require:

```python
if type(self.availability.execution_mode) is not str:
    raise TypeError("availability execution_mode must be a string")
if self.availability.execution_mode != mode.value:
    raise ValueError("availability execution_mode must match descriptor")
```

Do not change the core `ReaderAvailability` type.

- [ ] **Step 4: Run focused GREEN**

```powershell
& $pythonBin -m unittest tests.test_reader_plugin_manifest -v
```

Expected: all Reader API manifest tests pass.

---

### Task 2: Strict single-dot extension normalization

**Files:**
- Modify: `ChemBlender/reader_api/manifest.py`
- Test: `tests/test_reader_plugin_manifest.py`

**Interfaces:**
- Consumes: a non-empty list/tuple of extension strings.
- Produces: sorted, deduplicated lowercase suffixes with exactly one optional added leading dot.

- [ ] **Step 1: Write failing extension tests**

Accept:

```python
("XYZ", ".xyz", "TAR.GZ", ".tar.gz", ".molden.input")
```

Reject:

```python
(".", "..", "..xyz", "...xyz", "..TAR.GZ", "../xyz",
 "folder/xyz", "x yz", "/", "\\", "*", "?", ";")
```

Assert `["tar.gz", ".TAR.GZ"]` becomes `(".tar.gz",)`.

- [ ] **Step 2: Run RED**

```powershell
& $pythonBin -m unittest tests.test_reader_plugin_manifest -v
```

Expected: the multiple-leading-dot cases are incorrectly accepted.

- [ ] **Step 3: Replace dot stripping**

Use:

```python
normalized = value.lower()
if not normalized.startswith("."):
    normalized = "." + normalized
```

Then apply the existing `_EXTENSION_PATTERN.fullmatch(normalized)` and
deterministic deduplication. Do not broaden the regex.

- [ ] **Step 4: Run focused GREEN**

```powershell
& $pythonBin -m unittest tests.test_reader_plugin_manifest -v
```

Expected: valid compound suffixes normalize and every multiple-dot case fails.

---

### Task 3: Shared license normalization

**Files:**
- Modify: `ChemBlender/reader_api/manifest.py`
- Test: `tests/test_reader_plugin_manifest.py`

**Interfaces:**
- Consumes: a non-empty list/tuple of license strings.
- Produces: `tuple(sorted(set(values)))` after exact-string and whitespace validation.

- [ ] **Step 1: Add a helper contract test**

Import the private helper inside the test and assert:

```python
self.assertEqual(
    _licenses(["MIT OR Apache-2.0", "Apache-2.0", "Apache-2.0"]),
    ("Apache-2.0", "MIT OR Apache-2.0"),
)
```

Reuse the existing invalid and mutable-input manifest tests to cover exact
strings, empty/whitespace values, leading/trailing whitespace, internal
spaces, deduplication, sorting, and input isolation.

- [ ] **Step 2: Run RED**

```powershell
& $pythonBin -m unittest tests.test_reader_plugin_manifest -v
```

Expected: importing `_licenses` fails because the helper does not exist.

- [ ] **Step 3: Extract the existing rule once**

Add:

```python
def _licenses(values):
    values = _sequence(values, "license")
    if any(type(item) is not str or not item or item != item.strip() for item in values):
        raise ValueError("license must contain non-empty strings")
    return tuple(sorted(set(values)))
```

Make `ReaderPluginManifest.__post_init__()` call `_licenses(self.license)`;
remove its duplicate inline validation and normalization.

- [ ] **Step 4: Run related GREEN**

```powershell
& $pythonBin -m unittest `
  tests.test_reader_plugin_manifest `
  tests.test_quantum_visualization_docs -v
```

Expected: all focused and documentation-contract tests pass.

---

### Task 4: Full regression and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: `docs/superpowers/plans/2026-07-24-chemblender-2.3.0-wave-0-reader-api-task1-final-conformance.md`

**Interfaces:**
- Produces: one reviewed implementation commit and one completed execution cursor.

- [ ] **Step 1: Commit the implementation**

```powershell
git add `
  ChemBlender/reader_api/descriptors.py `
  ChemBlender/reader_api/manifest.py `
  tests/test_reader_plugin_manifest.py
git commit -m "fix: canonicalize reader API metadata values"
```

- [ ] **Step 2: Complete task and broad reviews**

Run one task-scoped specification/code-quality review and one independent
broad review. Fix every Critical/Important finding and every directly related
Minor finding, then repeat the affected review.

- [ ] **Step 3: Run fresh full verification**

```powershell
& $pythonBin -m unittest `
  tests.test_reader_plugin_manifest `
  tests.test_quantum_visualization_docs -v
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
& $pythonBin -c "import sys; import ChemBlender.reader_api as api; from ChemBlender.reader_api.descriptors import _probe_availability; result = _probe_availability('sys', api.ExecutionMode.EXTENSION); assert type(result.execution_mode) is str; assert result.execution_mode == 'extension'; assert not any(name in sys.modules for name in ('bpy','cclib','iodata','gbasis','ase','pymatgen'))"
git diff --check
git status --short
```

- [ ] **Step 4: Record and commit the completion checkpoint**

Record planning and implementation full SHAs, RED/GREEN evidence, the three
contract results, `Not Run: pure-Python Reader API contract cleanup`, the
Task 2 stop boundary, and no-push policy. Then commit:

```powershell
git add `
  .agents/active/2.3.0-wave-0-platform-foundation.md `
  docs/superpowers/plans/2026-07-24-chemblender-2.3.0-wave-0-reader-api-task1-final-conformance.md
git commit -m "chore: checkpoint reader API task 1 final conformance"
```

Confirm `public_model.py`, `builtin_bridge.py`, and `canonical_document.py`
remain absent and stop before Task 2.
