# ChemBlender 2.3.0 Wave 0 Reader API Task 1 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Reader API Task 1 metadata boundary safe under Blender's installed extension namespace while preserving tri-state reader capabilities and rejecting ambiguous extension/license metadata.

**Architecture:** The public package uses only relative imports and re-exports the exact trusted `CapabilitySupport` and `ReaderAvailability` classes from the installed package instance. `PublicReaderDescriptor` preserves immutable tri-state capability metadata, while the existing manifest parser remains the single normalization boundary for extensions and licenses.

**Tech Stack:** Python 3.13 standard library (`ast`, `dataclasses`, `enum`, `importlib`, `re`, `tomllib`, `types`, `unittest`), existing ChemBlender core reader contracts.

## Global Constraints

- Work only on `feat/2.3.0-wave0-platform-foundation`.
- Reviewed baseline is `1548570ed83a60e75022be0d2d23e0a58f6cdd61`.
- Do not create `ChemBlender/reader_api/public_model.py` or `ChemBlender/reader_api/builtin_bridge.py`.
- Do not begin Reader API Task 2, Registration/UI, or Wave 1–4.
- Do not add or install dependencies.
- Do not hardcode `ChemBlender`, `bl_ext.user_default`, or any extension repository namespace inside `ChemBlender/reader_api/*.py`.
- Keep `ChemBlender.reader_api` importable without `bpy` or optional scientific stacks.
- Use one implementation commit and one separate completion checkpoint.
- Do not push without a new explicit user authorization.

---

### Task 1: Namespace-safe Reader API imports

**Files:**
- Modify: `ChemBlender/reader_api/__init__.py`
- Modify: `ChemBlender/reader_api/descriptors.py`
- Modify: `tests/test_reader_plugin_manifest.py`

**Interfaces:**
- Consumes: the installed package's `..core.readers` module.
- Produces: a `reader_api` package that works as both `ChemBlender.reader_api` and `<repository>.chemblender.reader_api`.

- [ ] **Step 1: Add the failing absolute-import AST contract**

Add a test that parses every `ChemBlender/reader_api/*.py` with `ast.parse()`.
Reject `ast.Import` names and level-zero `ast.ImportFrom` modules whose first
component is `ChemBlender` or `bl_ext`.

- [ ] **Step 2: Add the failing installed-namespace subprocess test**

In a fresh subprocess:

1. Remove the repository root and empty entry from `sys.path`.
2. Create only a synthetic parent package in `sys.modules`.
3. Load `ChemBlender/__init__.py` as `synthetic_repository.chemblender` with
   `spec_from_file_location(..., submodule_search_locations=[package_root])`.
4. Import `synthetic_repository.chemblender.reader_api`.
5. Assert top-level `ChemBlender` and `bpy`, `cclib`, `iodata`, `gbasis`,
   `ase`, and `pymatgen` are absent from `sys.modules`.

- [ ] **Step 3: Verify RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_reader_plugin_manifest -v
```

Expected: the AST test reports the two current absolute imports and the
synthetic namespace import fails because top-level `ChemBlender` is absent.

- [ ] **Step 4: Replace the absolute imports**

Use one relative core import in `descriptors.py`:

```python
from ..core.readers import CapabilitySupport, ReaderAvailability
```

Re-export both exact classes from `descriptors.py` through `reader_api/__init__.py`.
Do not add aliases, dynamic imports, or repository-name configuration.

---

### Task 2: Tri-state capability preservation

**Files:**
- Modify: `ChemBlender/reader_api/__init__.py`
- Modify: `ChemBlender/reader_api/descriptors.py`
- Modify: `tests/test_reader_plugin_manifest.py`
- Modify: `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-0-reader-api.md`

**Interfaces:**
- Consumes: exact `CapabilitySupport` values from `..core.readers`.
- Produces: `PublicReaderDescriptor.capabilities: Mapping[str, CapabilitySupport]`.

- [ ] **Step 1: Add failing exact-identity and tri-state tests**

Assert:

```python
api.CapabilitySupport is core_readers.CapabilitySupport
descriptor.capabilities == {
    "atomic_property": api.CapabilitySupport.PARTIAL,
    "structure": api.CapabilitySupport.SUPPORTED,
    "topology": api.CapabilitySupport.UNSUPPORTED,
}
```

Also assert bool, string, a different enum with matching serialized values,
and a duck-typed object are rejected rather than coerced.

- [ ] **Step 2: Add a current capability-matrix regression**

Read `docs/quantum-visualization/reader-capability-matrix.json`, select current
entries containing `partial` and `unsupported`, convert the values through
the exact public enum, and prove `PublicReaderDescriptor` preserves every
entry without dropping or promoting it.

- [ ] **Step 3: Implement the minimal type correction**

Change only the annotation and exact value check:

```python
capabilities: Mapping[str, CapabilitySupport]

if type(support) is not CapabilitySupport:
    raise TypeError("capability values must be CapabilitySupport")
```

Keep the sorted `MappingProxyType` output. Do not implement the Task 4
built-in registry bridge.

- [ ] **Step 4: Update the parent plan contract**

Add `CapabilitySupport` to Task 1's produced public API and state:

```text
Manifest capability lists imply SUPPORTED.
Runtime PublicReaderDescriptor uses CapabilitySupport and preserves
SUPPORTED/PARTIAL/UNSUPPORTED for built-in and derived descriptors.
```

Repeat that relationship in Task 4's bridge step so later work cannot collapse
the three states.

---

### Task 3: Extension and license validation

**Files:**
- Modify: `ChemBlender/reader_api/manifest.py`
- Modify: `ChemBlender/reader_api/descriptors.py`
- Modify: `tests/test_reader_plugin_manifest.py`

**Interfaces:**
- Consumes: manifest/direct-constructor extension and license sequences.
- Produces: deterministic immutable extension and license tuples.

- [ ] **Step 1: Add failing extension-boundary tests**

Accept and normalize:

```python
("XYZ", ".molden.input", ".tar.gz") == (".molden.input", ".tar.gz", ".xyz")
```

Reject each of:

```python
("/", "\\", "*", "?", ";", " ", ".", "..", "../xyz", "folder/xyz", "x yz")
```

The canonical token must fully match:

```text
\.[a-z0-9][a-z0-9._+-]*
```

- [ ] **Step 2: Add failing license-boundary tests**

Reject non-strings, empty strings, pure whitespace, and leading/trailing
whitespace. Accept internal spaces such as `MIT OR Apache-2.0`. Assert
duplicates are removed, output is ordinally sorted, and later mutation of the
input list cannot affect the frozen manifest.

- [ ] **Step 3: Implement the shared normalization boundaries**

Compile one `_EXTENSION_PATTERN` and call `fullmatch()` after lowercasing and
adding one leading dot. Normalize licenses once in a small helper that exact-
type checks, rejects surrounding whitespace, returns `tuple(sorted(set(...)))`,
and is used by `ReaderPluginManifest.__post_init__()`.

Do not require an `SPDX:` prefix.

---

### Task 4: Public surface and dynamic-package documentation

**Files:**
- Modify: `ChemBlender/reader_api/__init__.py`
- Modify: `tests/test_reader_plugin_manifest.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Produces: exact deterministic `reader_api.__all__` including
  `CapabilitySupport`, with existing Task 1 names unchanged.

- [ ] **Step 1: Update the exact public-surface test**

Expected public names:

```python
(
    "READER_API_VERSION",
    "ExecutionMode",
    "CapabilitySupport",
    "ReaderAvailability",
    "ReaderManifestEntry",
    "ReaderPluginManifest",
    "PublicReaderDescriptor",
)
```

- [ ] **Step 2: Update the architecture guide**

Document that `reader_api` uses namespace-relative imports, re-exports the
exact installed core enum/availability types, and preserves
`SUPPORTED`/`PARTIAL`/`UNSUPPORTED`. Keep the existing no-callable,
no-`QCProject`, and no-optional-import boundaries.

- [ ] **Step 3: Verify focused GREEN and commit**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_reader_plugin_manifest `
  tests.test_quantum_visualization_docs -v
```

Then commit only the actual runtime/test/docs changes:

```powershell
git commit -m "fix: harden reader API metadata contract"
```

---

### Task 5: Full regression and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: `docs/superpowers/plans/2026-07-24-chemblender-2.3.0-wave-0-reader-api-task1-hardening.md`

**Interfaces:**
- Produces: a completed hardening cursor with exact commits and fresh evidence.

- [ ] **Step 1: Run the full verification**

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
& $pythonBin -c "import sys; import ChemBlender.reader_api as api; from ChemBlender.core.readers import CapabilitySupport, ReaderAvailability; assert api.CapabilitySupport is CapabilitySupport; assert api.ReaderAvailability is ReaderAvailability; assert not any(name in sys.modules for name in ('bpy','cclib','iodata','gbasis','ase','pymatgen'))"
git diff --check
git status --short
```

- [ ] **Step 2: Complete independent reviews**

Run one specification-compliance review and one independent code-quality
review. Fix every Critical/Important finding and every Minor finding directly
related to this hardening scope, then rerun the covering and full verification.

- [ ] **Step 3: Record the completed cursor**

Record planning and implementation full SHAs, RED/GREEN evidence, namespace
alias and tri-state results, `Not Run: pure-Python Reader API metadata task`,
the Task 2 stop boundary, and the no-push policy.

- [ ] **Step 4: Commit the completion checkpoint**

```powershell
git add `
  .agents/active/2.3.0-wave-0-platform-foundation.md `
  docs/superpowers/plans/2026-07-24-chemblender-2.3.0-wave-0-reader-api-task1-hardening.md
git commit -m "chore: checkpoint reader API task 1 hardening"
```

Confirm `public_model.py` and `builtin_bridge.py` remain absent and stop.
