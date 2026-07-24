# ChemBlender Reader API Alpha Conformance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, machine-readable conformance runner for Reader API 0.x and prove the built-in XYZ and Cube readers satisfy the alpha contract.

**Architecture:** `conformance.py` is a thin public verification layer over the existing `ReaderPluginRegistry`, public batch conversion, and canonical bundle APIs. It does not create another parser, registry, validator, serializer, timeout service, or project mutation path; each check returns immutable structured evidence, and reader failures are reported rather than escaping the runner.

**Tech Stack:** Python 3.13 standard library, `dataclasses`, `hashlib`, `tempfile`, existing ChemBlender Reader API 0.x.

## Global Constraints

- Keep `ChemBlender.reader_api` importable without `bpy` or optional reader stacks.
- Use relative imports inside `ChemBlender/reader_api/`.
- Do not add dependencies, pickle, dynamic imports, module/callable paths, `QCProject`, or Blender datablocks to the public boundary.
- Reuse `ReaderPluginRegistry`, `internal_batch_from_public()`, and canonical document functions as the single validation authorities.
- Do not start Registration/UI, Release Groundwork, or Wave 1–4.
- Update `.agents/reference/code-architecture-guide.md` in the implementation commit because a Python source module is added.

---

### Task 1: Reader API 0.x alpha conformance

**Files:**
- Create: `ChemBlender/reader_api/conformance.py`
- Modify: `ChemBlender/reader_api/__init__.py`
- Create: `tests/test_reader_conformance.py`
- Modify: `tests/test_reader_plugin_manifest.py`
- Create: `docs/quantum-visualization/2.3.0/reader-api-0.x.md`
- Modify: `docs/quantum-visualization/2.3.0/README.md`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: `ReaderPluginRegistry.select()`, `ReaderPluginRegistry.parse()`, `SniffRequest`, `ParseRequest`, `PublicImportBatch`, `internal_batch_from_public()`, `write_public_batch_bundle()`, and `read_public_batch_bundle()`.
- Produces: `ReaderConformanceCase`, `ReaderConformanceCheck`, `ReaderConformanceResult`, and `run_reader_conformance()`.
- `ReaderConformanceCase` is `@dataclass(frozen=True, slots=True)` with exact fields `name`, `registry`, `reader_id`, `source_path`, `expected_capabilities`, `validation_mode="balanced"`, and `canonical_parameters={}` normalized to immutable deterministic values.
- `ReaderConformanceCheck` is `@dataclass(frozen=True, slots=True)` with exact fields `name`, `passed`, and `detail`.
- `ReaderConformanceResult` is `@dataclass(frozen=True, slots=True)` with exact fields `schema_version`, `case_name`, `reader_id`, and `checks`; its `passed` property is true only when every check passed, and `as_dict()` returns only JSON-safe primitives with deterministic check order.
- `run_reader_conformance(case)` accepts only an exact `ReaderConformanceCase`, never raises a reader/plugin exception, and returns an exact `ReaderConformanceResult`.

- [ ] **Step 1: Write the failing public contract tests**

Create `tests/test_reader_conformance.py` before `conformance.py`. Assert the new imports fail because the module does not exist, then specify frozen/slots case and result types, exact field normalization, deterministic `as_dict()`, and exact public `__all__` additions.

Run:

```powershell
& $pythonBin -m unittest discover -s tests -p "test_reader_conformance.py" -v
```

Expected: non-zero exit with `ModuleNotFoundError` or `ImportError` for `ChemBlender.reader_api.conformance`.

- [ ] **Step 2: Specify conformance behavior with failing tests**

Add tests that require the following ordered checks:

```python
(
    "manifest",
    "bounded_sniff",
    "deterministic_sniff",
    "availability",
    "parse_output",
    "source_identity",
    "entity_references",
    "required_units",
    "diagnostics",
    "canonical_round_trip",
    "cancellation",
    "exception_isolation",
)
```

The tests must prove:

- registration validates the plugin manifest/descriptor boundary;
- sniff receives no more than 65,536 bytes and two calls select the same reader;
- availability is explicit and available;
- parse returns exact `PublicImportBatch`;
- provenance or explicit `SourceRevision` binds the parsed entities to the source SHA-256 and reader metadata;
- `internal_batch_from_public()` accepts the graph and exact report-created entity IDs;
- every reachable `ArrayData.unit` and coordinate-unit field is a non-empty canonical token;
- the report reader/version/capabilities and diagnostic references are complete;
- canonical write/read/write preserves canonical document bytes and artifact hashes;
- a pre-cancelled request does not call the reader and yields the stable cancellation report;
- a sniffing or parsing exception becomes a failed machine-readable check and does not escape.

Use `tests/fixtures/xyz/water.xyz` and `tests/fixtures/cube/sheared.cube`. Expected capabilities are `("structure",)` for XYZ and `("grid", "structure")` for Cube.

- [ ] **Step 3: Implement the minimum conformance runner**

Create `ChemBlender/reader_api/conformance.py` with relative imports only. Use one small private helper per shared check, `hashlib.sha256()` for source identity, `TemporaryDirectory()` for canonical round-trip, and the existing public bridge for graph validation. Catch `Exception` only at individual check boundaries so the result records `type(error).__name__` without exposing tracebacks or aborting later checks.

Do not add wall-clock timeout threads or processes. “Bounded sniff” means the request prefix is capped at the existing 65,536-byte protocol limit; long-running work remains governed by the existing progress/cancellation protocol.

- [ ] **Step 4: Make XYZ and Cube GREEN**

Run:

```powershell
& $pythonBin -m unittest discover -s tests -p "test_reader_conformance.py" -v
& $pythonBin -m unittest discover -s tests -p "test_reader_api_registry.py" -v
& $pythonBin -m unittest discover -s tests -p "test_reader_canonical_document.py" -v
```

Expected: all tests pass; both built-in conformance results have `passed is True`.

- [ ] **Step 5: Publish the alpha imports and documentation**

Re-export only:

```python
ReaderConformanceCase
ReaderConformanceCheck
ReaderConformanceResult
run_reader_conformance
```

Update the exact `reader_api.__all__` test. Document that API `0.x` is experimental through alpha, the conformance result schema is `0.1`, the exact supported import path is resolved from the Blender Reader API handle, and third-party experiments may use only the documented public imports. State that conformance success is not permission to mutate `QCProject`, use `bpy`, import optional dependencies during discovery, or bypass main-process validation.

- [ ] **Step 6: Update architecture coverage and run regression**

Add the exact responsibility of `ChemBlender/reader_api/conformance.py` to `.agents/reference/code-architecture-guide.md`, link the alpha document from the 2.3.0 README, then run:

```powershell
& $pythonBin -m unittest discover -s tests -p "test_reader_conformance.py" -v
& $pythonBin -m unittest discover -s tests -p "test_reader_plugin_manifest.py" -v
& $pythonBin -m unittest discover -s tests -p "test_reader_api_registry.py" -v
& $pythonBin -m unittest discover -s tests -p "test_reader_canonical_document.py" -v
& $pythonBin -m unittest discover -s tests -p "test_worker_protocol.py" -v
& $pythonBin -m unittest discover -s tests -p "test_worker_reader_operation.py" -v
& $pythonBin -m unittest discover -s tests -p "test_quantum_visualization_docs.py" -v
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
```

Expected: zero failures. Blender validate/build/smoke are not rerun for this pure-Python Task 7; Task 6 supplies the fresh Blender handle lifecycle evidence for the complete Reader API plan.

- [ ] **Step 7: Review and commit**

Perform independent specification-compliance and code-quality reviews. Fix all Critical/Important findings and in-scope Minor findings, rerun the covering tests, then commit the implementation:

```powershell
git add ChemBlender/reader_api/conformance.py ChemBlender/reader_api/__init__.py tests/test_reader_conformance.py tests/test_reader_plugin_manifest.py docs/quantum-visualization/2.3.0/reader-api-0.x.md docs/quantum-visualization/2.3.0/README.md .agents/reference/code-architecture-guide.md
git commit -m "feat: add reader API alpha conformance"
```

