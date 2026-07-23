# ChemBlender 2.3.0 Wave 0 Reader API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce Reader API 0.x with plugin metadata, public batches, canonical documents, worker artifacts and conformance tests while preserving existing built-in readers.

**Architecture:** Existing ReaderDescriptor is wrapped, then gradually adapted. Public Python objects and canonical JSON represent one schema. Plugins cannot mutate QCProject or Blender data. Worker results use safe relative NPY artifacts and are revalidated in the main process.

**Tech Stack:** Python typing Protocol, dataclasses, JSON, TOML via `tomllib`, NPY, existing worker protocol, `unittest`.

## Global Constraints

- API is experimental 0.x until beta.1.
- No plugin import may prevent main extension registration.
- No pickle, arbitrary callable, dynamic module path from documents or absolute artifact path.
- Existing readers continue to work through a built-in adapter.
- Public API cannot expose private model module paths as requirements.

---

### Task 1: Define plugin manifest and runtime descriptors

**Files:**
- Create: `ChemBlender/reader_api/__init__.py`
- Create: `ChemBlender/reader_api/version.py`
- Create: `ChemBlender/reader_api/manifest.py`
- Create: `ChemBlender/reader_api/descriptors.py`
- Create: `tests/test_reader_plugin_manifest.py`

**Interfaces:**
- Produces: `READER_API_VERSION="0.1"`, `ReaderPluginManifest`, `ReaderManifestEntry`, `ExecutionMode`, `ReaderAvailability`, `PublicReaderDescriptor`.

- [ ] **Step 1: Write manifest validation tests**

Test valid TOML, invalid plugin ID, incompatible API range, duplicate reader IDs, unknown execution mode, empty license and non-dot extension normalization.

- [ ] **Step 2: Implement manifest parsing**

Use `tomllib.loads`. API range supports the explicit forms used by ChemBlender, parsed into min/max tuples; do not introduce packaging dependency. Reject unrecognized keys in 0.x to surface mistakes.

- [ ] **Step 3: Implement availability**

Availability includes available bool, reason code and detail. It is evaluated without importing the optional dependency where possible using `importlib.util.find_spec` or worker environment probes.

- [ ] **Step 4: Run and commit**

Run manifest and existing reader tests, then commit.

### Task 2: Define public import model and built-in conversion

**Files:**
- Create: `ChemBlender/reader_api/public_model.py`
- Create: `ChemBlender/reader_api/builtin_bridge.py`
- Create: `tests/test_public_import_batch.py`

**Interfaces:**
- Produces: `PublicImportBatch`, `public_batch_from_internal()`, `internal_batch_from_public()`.

- [ ] **Step 1: Write round-trip tests using XYZ and Cube**

Parse existing fixtures with internal readers, convert to public and back, and compare entity IDs, revisions, dims, units, values and report issues.

- [ ] **Step 2: Implement public types**

For source-tree tests, public types are imported through `ChemBlender.reader_api`. Installed third-party extensions resolve the actual module through the versioned Blender API handle described in Task 6; they do not hardcode the source-tree name or a `bl_ext` repository namespace. PublicImportBatch includes sources, entities, diagnostics and parser report.

- [ ] **Step 3: Validate before conversion**

`internal_batch_from_public` constructs an isolated QCProject and commits the batch to prove references before returning.

- [ ] **Step 4: Run and commit**

Run public batch, source, core and sidecar tests.

### Task 3: Implement canonical document serialization

**Files:**
- Create: `ChemBlender/reader_api/canonical_document.py`
- Create: `tests/test_reader_canonical_document.py`
- Create: `docs/quantum-visualization/2.3.0/specs/reader-import-document-v0.1.md`

**Interfaces:**
- Produces: `public_batch_document()`, `public_batch_from_document()`, `write_public_batch_bundle()`, `read_public_batch_bundle()`.

- [ ] **Step 1: Write scalar and array round-trip tests**

Use structure, topology, categorical property, frame property and grid arrays. Assert document bytes are identical regardless of dict insertion order.

- [ ] **Step 2: Implement tagged canonical values**

Use stable type tags, UUID strings, enums, tuples and array descriptors. JSON uses UTF-8, sorted keys, compact separators and `allow_nan=False`.

- [ ] **Step 3: Implement safe NPY artifacts**

Artifacts live under `artifacts/{content_sha256}.npy`; descriptor includes shape, dtype, content hash and file hash. Reject object dtype, absolute path, `..`, symlink escape and hash mismatch.

- [ ] **Step 4: Run security tests**

Add malformed documents for unknown type, extra/missing fields, path traversal, non-finite value and pickle-like payload. Expected: typed compatibility/integrity errors.

- [ ] **Step 5: Commit**

Commit code, spec and tests together.

### Task 4: Define plugin protocol and built-in registry bridge

**Files:**
- Create: `ChemBlender/reader_api/protocol.py`
- Create: `ChemBlender/reader_api/registry.py`
- Modify: `ChemBlender/core/reader_catalog.py`
- Create: `tests/test_reader_api_registry.py`

**Interfaces:**
- Produces: `SniffRequest`, `ParseRequest`, `ProgressEvent`, `ReaderPlugin` Protocol, `ReaderPluginRegistry` and built-in registration.

- [ ] **Step 1: Write deterministic selection tests**

Register built-in XYZ/Cube through the new registry. Assert identical selection to existing registry and dependency-unavailable readers remain selectable for Preview but cannot parse.

- [ ] **Step 2: Implement protocol request objects**

ParseRequest contains source path, source hash, validation mode, canonical parameters, staging root, progress callback and cancellation callback. It exposes no QCProject or Blender context.

- [ ] **Step 3: Implement exception isolation**

Registry catches plugin sniff exceptions, records plugin diagnostic and continues other readers. If a selected plugin parse raises, it returns a failed staged result rather than disabling the extension.

- [ ] **Step 4: Bridge existing descriptors**

Wrap the 11 existing descriptors with `plugin_id="chemblender.builtin"` and appropriate execution/availability metadata. Do not change their parse code yet.

- [ ] **Step 5: Run and commit**

Run old and new catalog tests and update capability document generation to include execution mode and availability contract fields.

### Task 5: Add worker reader bridge

**Files:**
- Create: `worker/reader_operation.py`
- Modify: `worker/runner.py`
- Create: `ChemBlender/reader_api/worker_bridge.py`
- Create: `tests/test_worker_reader_operation.py`

**Interfaces:**
- Produces: fixed operation `reader.parse@0.1` and main-process `parse_with_worker()`.

- [ ] **Step 1: Write operation whitelist tests**

Assert request cannot specify module, callable, shell or argv. It can specify registered worker reader ID, source artifact and canonical parameters.

- [ ] **Step 2: Implement worker operation**

Worker reads request, resolves a reader from its fixed registry, parses into its task directory, writes canonical bundle and result hashes, then reopens the bundle before success.

- [ ] **Step 3: Implement main-process revalidation**

Main process verifies WorkerResult, artifact paths and hashes, reads public batch document and validates through internal QCProject before staging.

- [ ] **Step 4: Run cancellation/failure tests**

Cover missing reader, dependency unavailable, cancel, malformed output, stale artifact and success.

- [ ] **Step 5: Commit**

Commit worker and bridge with protocol docs.

### Task 6: Publish a versioned Blender Reader API handle

**Files:**
- Create: `ChemBlender/runtime/reader_api_bridge.py`
- Modify: `ChemBlender/runtime/registration.py`
- Create: `tests/test_reader_api_bridge_contract.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: versioned `ReaderAPIHandle` publication and safe removal.

- [ ] **Step 1: Write bridge contract tests**

Assert the handle key is versioned, the module name is derived from the live package root, and owner-token mismatch prevents removal. Static tests reject hardcoded `bl_ext.user_default.chemblender` in public plugin code.

- [ ] **Step 2: Implement the pure handle type and Blender bridge**

The handle contains API version, actual module name, opaque owner token and registration callbacks. `register_reader_api_handle(package_root)` writes to `bpy.app.driver_namespace`; an existing incompatible owner produces a controlled registration error rather than silent overwrite.

- [ ] **Step 3: Integrate explicit lifecycle**

Publish after the core Reader registry is ready and remove before module cleanup. Two disable/enable cycles produce exactly one current handle.

- [ ] **Step 4: Blender smoke and commit**

Assert the installed module name begins with the actual extension key, importing `handle.module_name` returns the public API module, and unregister removes only the owned handle. Commit.

### Task 7: Add conformance tests for alpha readers

**Files:**
- Create: `ChemBlender/reader_api/conformance.py`
- Create: `tests/test_reader_conformance.py`
- Create: `docs/quantum-visualization/2.3.0/reader-api-0.x.md`

**Interfaces:**
- Produces: `ReaderConformanceCase`, `run_reader_conformance()` and machine-readable result.

- [ ] **Step 1: Define conformance checks**

Checks include manifest, bounded sniff, deterministic sniff, availability, parse output type, source identity, entity references, units, diagnostics, canonical round-trip, cancellation and exception isolation.

- [ ] **Step 2: Run conformance on built-in XYZ and Cube**

Write test cases with fixed fixtures and expected capabilities. Both must pass.

- [ ] **Step 3: Document alpha instability**

The doc states 0.x can change through alpha and identifies exact imports third-party experiments may use.

- [ ] **Step 4: Verify and commit**

Run conformance, reader catalog, worker protocol and full pure suite.
