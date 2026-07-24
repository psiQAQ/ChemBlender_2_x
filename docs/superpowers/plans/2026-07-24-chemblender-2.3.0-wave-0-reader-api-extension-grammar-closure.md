# ChemBlender 2.3.0 Wave 0 Reader API Extension Grammar Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the final Reader API Task 1 extension-suffix grammar gap by preserving valid simple and compound suffixes while rejecting trailing dots and empty segments.

**Architecture:** Keep the existing shared `_extensions()` normalization boundary and replace only its regular expression with a segmented suffix grammar. Add direct-construction and TOML-parsing characterization tests so all manifest entry paths enforce the same rule.

**Tech Stack:** Python 3.13 standard library (`re`, `tomllib`, `unittest`) and the existing ChemBlender Reader API manifest contracts.

## Global Constraints

- Work only on `feat/2.3.0-wave0-platform-foundation`.
- Reviewed baseline is `10686d7e22fd5529eba7d696c2bcf83664f4a1d9`.
- Modify runtime code only in `ChemBlender/reader_api/manifest.py`.
- Do not create `ChemBlender/reader_api/public_model.py`, `ChemBlender/reader_api/builtin_bridge.py`, or `ChemBlender/reader_api/canonical_document.py`.
- Do not begin Reader API Task 2, Registration/UI, or Wave 1–4.
- Do not add or install dependencies.
- Keep `ChemBlender.reader_api` importable without `bpy` or optional scientific stacks.
- Use one implementation commit and one separate completion checkpoint.
- Do not push without a new explicit user authorization.

---

### Task 1: Segmented extension grammar

**Files:**
- Modify: `ChemBlender/reader_api/manifest.py`
- Test: `tests/test_reader_plugin_manifest.py`

**Interfaces:**
- Consumes: simple or compound extension suffix strings with at most one optional leading dot.
- Produces: sorted, deduplicated lowercase suffixes whose dot-delimited segments are non-empty and start with an ASCII letter or digit.

- [ ] **Step 1: Confirm the shared boundary**

Verify both `ReaderManifestEntry(...)` and `ReaderPluginManifest.from_toml(...)`
route extension values through `_extensions()`. Do not add a second validator.

- [ ] **Step 2: Implement the minimum grammar correction**

Replace `_EXTENSION_PATTERN` with:

```python
re.compile(
    r"\.[a-z0-9][a-z0-9_+-]*(?:\.[a-z0-9][a-z0-9_+-]*)*",
    re.ASCII,
)
```

Keep:

```python
normalized = value.lower()
if not normalized.startswith("."):
    normalized = "." + normalized
```

Do not use `lstrip(".")`.

---

### Task 2: Positive and negative compatibility fixtures

**Files:**
- Test: `tests/test_reader_plugin_manifest.py`

**Interfaces:**
- Valid: `xyz`, `.xyz`, `tar.gz`, `.TAR.GZ`, `molden.input`, `.c++`, and `x-y+z`.
- Invalid: `.xyz.`, `.tar..gz`, `.molden..input`, `.x...`, `.x..y`, `.x.`, `..xyz`, `...xyz`, `..`, and `.`.

- [ ] **Step 1: Write failing tests before runtime changes**

Cover the exact valid and invalid tables through direct
`ReaderManifestEntry` construction. Add TOML parsing cases that prove the
same shared rule accepts compound suffixes and rejects trailing-dot and
empty-segment suffixes.

- [ ] **Step 2: Run RED**

```powershell
& $pythonBin -m unittest tests.test_reader_plugin_manifest -v
```

Expected: the new invalid cases are accepted by the current regex, so the
test command exits nonzero for the intended assertions.

- [ ] **Step 3: Apply Task 1's minimal regex change and run GREEN**

```powershell
& $pythonBin -m unittest tests.test_reader_plugin_manifest -v
```

Expected: all Reader API manifest tests pass with deterministic normalization
and deduplication unchanged.

---

### Task 3: Full regression

**Files:**
- Verify: `ChemBlender/reader_api/manifest.py`
- Verify: `tests/test_reader_plugin_manifest.py`

- [ ] **Step 1: Run related contracts**

```powershell
& $pythonBin -m unittest `
  tests.test_reader_plugin_manifest `
  tests.test_quantum_visualization_docs -v
```

- [ ] **Step 2: Run full repository verification**

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
& $pythonBin -c "import sys; import ChemBlender.reader_api; assert not any(name in sys.modules for name in ('bpy','cclib','iodata','gbasis','ase','pymatgen'))"
git diff --check
git status --short
```

- [ ] **Step 3: Complete two independent reviews**

Run one task-scoped specification/code-quality review and one independent
broad review. Fix all findings related to this task and rerun affected
verification.

Blender validate/build/smoke is:
`Not Run: pure-Python manifest grammar correction`.

---

### Task 4: Execution checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: `docs/superpowers/plans/2026-07-24-chemblender-2.3.0-wave-0-reader-api-extension-grammar-closure.md`

- [ ] **Step 1: Commit implementation**

```powershell
git add `
  ChemBlender/reader_api/manifest.py `
  tests/test_reader_plugin_manifest.py
git commit -m "fix: reject ambiguous reader extension suffixes"
```

- [ ] **Step 2: Record completion evidence**

Record planning and implementation full SHAs, RED/GREEN evidence, full test
counts, compound-extension acceptance, trailing-dot rejection, empty-segment
rejection, review results, the Blender `Not Run` reason, the Task 2 stop
boundary, and the no-push policy.

- [ ] **Step 3: Commit checkpoint**

```powershell
git add `
  .agents/active/2.3.0-wave-0-platform-foundation.md `
  docs/superpowers/plans/2026-07-24-chemblender-2.3.0-wave-0-reader-api-extension-grammar-closure.md
git commit -m "chore: checkpoint reader extension grammar closure"
```

Confirm `public_model.py`, `builtin_bridge.py`, and `canonical_document.py`
remain absent and stop before Reader API Task 2.
